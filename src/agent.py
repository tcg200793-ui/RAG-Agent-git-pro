"""Pro Git 知识库助手 —— 带工具调用的 RAG 问答 Agent。

链路：
    用户问题 → 对话模型（qwen-plus）
                 ↓ 自主决定调用 search_git_docs 工具（可多轮、可改写查询）
              向量检索（data/embeddings.npy，numpy 精确最近邻）
                 ↓ 返回「[章节路径 | 页码 | 相似度] 原文」
              模型基于原文作答，带出处引用

与一次性「检索→拼接→生成」的区别：检索次数和检索词由模型自己决定，
答非所问时可以换说法再检一次，这正是 prompts/system_prompt.md 里要求的行为。

用法：
    .venv/bin/python src/agent.py                     # 交互模式（多轮对话）
    .venv/bin/python src/agent.py "如何撤销已推送的提交"  # 单次问答
    .venv/bin/python src/agent.py -v                  # 交互模式 + 打印命中的原文块

交互模式内命令：
    /reset   清空对话历史（保留系统提示词）
    /debug   切换是否打印检索原文

依赖：data/chunks.jsonl、data/embeddings.npy（由 src/embed.py 生成）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILE = ROOT / "prompts" / "system_prompt.md"

# 让 `python src/agent.py` 能 import 同目录的 vector_search
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vector_search import VectorIndex, embed_query, load_env  # noqa: E402

# 工具调用循环上限：防止模型反复检索不收敛（每轮最多 1 次检索，正常 1-2 轮就够）
MAX_TOOL_ROUNDS = 4
# 单次检索返回块数上限，防止模型传个 top_k=50 把上下文撑爆
MAX_TOP_K = 8
# 发请求前保留的历史消息条数（不含 system）。裁剪点会对齐到 user 消息，避免 tool/assistant 配对断裂
HISTORY_KEEP = 10

# 追加到系统提示词后面的工具说明。
# 提示词本身只写了「调用检索工具」，具体工具名和返回格式得让模型知道，
# 否则它不知道叫什么、也不知道返回的字符串长什么样。
TOOL_GUIDE = """
# 检索工具

工具名 `search_git_docs`，参数：

- `query`（必填）：检索语句。用用户问题原文；若首次结果答非所问，换成书里更可能出现的说法再检一次。
- `top_k`（可选，默认 5）：返回块数，1–8。判断需要多角度比对时可调大。

每次调用返回若干条文本块，格式：

```
[章节路径 | 页码范围 | 相似度]
原文……
```

补充判断依据：相似度是该块与问题的余弦相似度，0–1 之间。

- 0.75 以上：大概率对题。
- 0.5–0.75：相关但可能是相邻主题，要读原文确认是不是你要的那节。
- 0.5 以下：基本不相关，别拿它硬答，考虑换检索词重试，或者直接说没找到。

# 参数边界（硬约束）

- 代码块里出现的命令、短选项（`-f`、`-n`）、长选项（`--force`）必须能在检索原文中找到。
  本节对应 Git 2.x 早期，书里没有的新参数（例如后来才流行的 `--force-with-lease`）一律不得补充，
  哪怕你在别处见过、哪怕它确实更安全。
- 需要提示某个更安全的做法而书中没写时，只能说「书中未涉及，建议查官方文档」，
  不要写出具体参数名，否则等于编造。

# 额外约束（运行时补充，实测中发现的偏离）

- 不要在答案结尾反问「是否需要我帮你…」或主动提供知识库之外的延伸服务，答完即止。
- 判定「知识库里没有」时，只说检索到的片段不涉及该主题；不要推断该书为什么没收录、
  成书年代与某个 Git 版本的先后关系——这些也是书外断言。
- 涉及版本时统一说「本书对应 Git 2.x 早期」，不要给出更精确的版本号。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_git_docs",
            "description": (
                "在《Pro Git》中文版知识库中做语义检索，返回最相关的原文片段。"
                "回答任何涉及 Git 命令、操作步骤、内部机制的问题前都必须先调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索语句，用自然语言描述要查的内容",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回块数，默认 5，范围 1-8",
                        "minimum": 1,
                        "maximum": MAX_TOP_K,
                    },
                },
                "required": ["query"],
            },
        },
    }
]


class GitDocsAgent:
    """封装：索引 + 检索工具 + 对话模型 + 工具调用循环。"""

    def __init__(self, debug: bool = False) -> None:
        env = load_env()
        self.base = env.get("API_BASE_URL", "").rstrip("/")
        self.key = env.get("API_KEY", "")
        self.chat_model = env.get("CHAT_MODEL", "qwen-plus")
        self.embed_model = env.get("EMBED_MODEL", "text-embedding-v4")
        if not self.key:
            raise SystemExit("API_KEY 为空：请先填好 .env 里的 API_KEY")
        if not self.base:
            raise SystemExit("API_BASE_URL 为空：请检查 .env")

        self.index = VectorIndex.load()
        self.debug = debug
        self.system_prompt = PROMPT_FILE.read_text(encoding="utf-8") + TOOL_GUIDE
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        # 本轮问答检索到的全部原文，用于事后核对答案里的参数是否真的在材料中
        self._turn_context: list[str] = []
        # 检索轨迹回调：CLI 不设（走 stderr），Web 端设成把轨迹推进 SSE 队列
        self.trace_hook: Callable[[dict], None] | None = None
        # 最近一次答案的参数核对告警，供调用方展示
        self.last_warnings: list[str] = []

    # ---------- 检索工具 ----------

    def search_git_docs(self, query: str, top_k: int = 5) -> str:
        """工具实现：向量检索并把结果格式化成模型能读的字符串。"""
        top_k = max(1, min(int(top_k), MAX_TOP_K))
        qv = embed_query(self.base, self.key, self.embed_model, query)
        hits = self.index.search(qv, top_k=top_k)

        if not hits:
            return "没有检索到任何内容。"

        blocks: list[str] = []
        for score, idx in hits:
            c = self.index.chunks[idx]
            path = " > ".join(x for x in (c["chapter"], c["section"], c["subsection"]) if x)
            pages = c["pages"]
            page_str = f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]}"
            blocks.append(f"[{path} | {page_str} | 相似度 {score:.2f}]\n{c['text'].strip()}")

        if self.debug:
            print(f"\n\033[2m  ↳ 检索「{query}」(top_k={top_k})", file=sys.stderr)
            for score, idx in hits:
                c = self.index.chunks[idx]
                path = " > ".join(x for x in (c["chapter"], c["section"], c["subsection"]) if x)
                print(f"     {c['id']} {score:.3f} {path}", file=sys.stderr)
            print("\033[0m", file=sys.stderr, end="")

        if self.trace_hook:
            self.trace_hook(
                {
                    "query": query,
                    "top_k": top_k,
                    "hits": [
                        {
                            "id": self.index.chunks[i]["id"],
                            "score": round(s, 3),
                            "path": " > ".join(
                                x
                                for x in (
                                    self.index.chunks[i]["chapter"],
                                    self.index.chunks[i]["section"],
                                    self.index.chunks[i]["subsection"],
                                )
                                if x
                            ),
                            "pages": self.index.chunks[i]["pages"],
                        }
                        for s, i in hits
                    ],
                }
            )

        self._turn_context.extend(blocks)
        return "\n\n---\n\n".join(blocks)

    # ---------- 模型调用 ----------

    def _post_chat(self, messages: list[dict]) -> dict:
        """一次 chat/completions 请求，返回 choice 里的 message 与 finish_reason。"""
        payload = json.dumps(
            {
                "model": self.chat_model,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                # 事实型问答压低随机性，减少「编一个参数名」的概率
                "temperature": 0.2,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=payload, method="POST"
        )
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        choice = body["choices"][0]
        return {"message": choice["message"], "finish_reason": choice.get("finish_reason")}

    def _run_tool_calls(self, tool_calls: list[dict]) -> None:
        """执行模型请求的工具调用，把结果以 role=tool 消息追加进历史。"""
        for call in tool_calls:
            fn = call["function"]
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                # 参数不是合法 JSON 时回一句错误，让模型自己修正后重试
                result = f"参数解析失败（不是合法 JSON）：{args_raw}"
            else:
                query = str(args.get("query", "")).strip()
                if not query:
                    result = "缺少 query 参数，请重新调用并传入检索语句。"
                else:
                    result = self.search_git_docs(query, args.get("top_k", 5))
            self.messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result}
            )

    def ask(self, question: str) -> str:
        """对外入口：裁剪历史 → 清空本轮材料 → 走工具调用循环 → 核对答案参数 → 返回。

        裁剪放在这里而不是调用方：CLI 和 Web 都走 ask()，只有一处需要保证就不容易漏。
        """
        self.trim_history()
        self._turn_context = []
        answer = self._answer(question)
        self._audit(answer)
        return answer

    def _answer(self, question: str) -> str:
        """主循环：提问 → 模型 → 可能调工具 → 再问模型 → 直到给出最终答案。"""
        self.messages.append({"role": "user", "content": question})

        for round_no in range(MAX_TOOL_ROUNDS):
            resp = self._post_chat(self.messages)
            msg = resp["message"]
            tool_calls = msg.get("tool_calls") or []

            # 保留 assistant 原始消息（含 tool_calls），否则 tool 消息会成为孤儿被接口拒绝
            self.messages.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                }
            )

            if not tool_calls:
                return msg.get("content") or "（模型返回了空内容）"

            self._run_tool_calls(tool_calls)

            if round_no == MAX_TOOL_ROUNDS - 1:
                # 到上限还没收敛：逼它基于已有材料作答，而不是继续无限检索
                self.messages.append(
                    {
                        "role": "user",
                        "content": "已达到检索次数上限。请仅基于上面已有的检索结果作答；"
                        "材料不足就直接说知识库里没有相关内容。",
                    }
                )
                final = self._post_chat(self.messages)
                content = final["message"].get("content") or "（模型返回了空内容）"
                self.messages.append({"role": "assistant", "content": content})
                return content

        return "（超出工具调用轮次上限）"

    # ---------- 会话管理 ----------

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def trim_history(self) -> None:
        """裁剪历史控制 token：保留 system + 最近若干条，裁剪点对齐到 user 消息。"""
        if len(self.messages) <= HISTORY_KEEP + 1:
            return
        cut = len(self.messages) - HISTORY_KEEP
        # 往前找一个 user 消息作为边界，保证 assistant(tool_calls) 和 tool 消息不被拆开
        while cut < len(self.messages) and self.messages[cut]["role"] != "user":
            cut += 1
        if cut < len(self.messages):
            self.messages = [self.messages[0]] + self.messages[cut:]

    def _audit(self, answer: str) -> None:
        """事后核对：答案里出现的长选项是否真在本轮检索原文中。

        这一步防的是「模型用预训练记忆补参数」——比提示词警告更硬的兜底。
        只做提示不改答案：可能是模型自己归纳出的等价说法，也可能是真编造，交给人判断。
        """
        flags = sorted(set(re.findall(r"(?<![\w-])--[a-zA-Z][a-zA-Z0-9-]*", answer)))
        self.last_warnings = []
        if not flags:
            return
        context = "\n".join(self._turn_context)
        missing = [f for f in flags if f not in context]
        if missing:
            msg = f"以下参数未在本轮检索到的原文中出现，可能是模型凭记忆补的，请自行核对：{'、'.join(missing)}"
            self.last_warnings = [msg]
            print(f"\033[33m⚠ {msg}\033[0m", file=sys.stderr)


def print_answer(text: str) -> None:
    print("\n" + "─" * 74)
    print(text.strip())
    print("─" * 74 + "\n")


def repl(agent: GitDocsAgent) -> None:
    print(f"Pro Git 知识库助手（模型 {agent.chat_model}，知识库 {len(agent.index.chunks)} 块）")
    print("直接输入问题；/reset 清空对话，/debug 切换检索追踪，/quit 退出。\n")
    while True:
        try:
            line = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("/quit", "/exit", "/q"):
            return
        if line == "/reset":
            agent.reset()
            print("（对话已清空）\n")
            continue
        if line == "/debug":
            agent.debug = not agent.debug
            print(f"（检索追踪：{'开' if agent.debug else '关'}）\n")
            continue

        try:
            print_answer(agent.ask(line))
        except RuntimeError as exc:
            print(f"\n请求失败：{exc}\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pro Git 知识库助手")
    parser.add_argument("question", nargs="*", help="单次提问；不传则进入交互模式")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印检索命中的块")
    args = parser.parse_args()

    agent = GitDocsAgent(debug=args.verbose)

    if args.question:
        print_answer(agent.ask(" ".join(args.question)))
    else:
        repl(agent)


if __name__ == "__main__":
    main()
