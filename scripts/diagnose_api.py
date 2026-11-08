"""一键诊断 API 配置：搞清楚 key 能用哪些模型、embedding 到底通不通。

用法：
    cp .env.example .env      # 然后把 API_KEY 填进去
    .venv/bin/python scripts/diagnose_api.py

依次检查：
    1. GET  /models           列出这个 key 实际可访问的模型
    2. POST /embeddings       对候选向量模型逐个试，看哪个真的能出向量
    3. POST /chat/completions 试一个对话模型，确认 key 有对话权限
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# /models 不可用时，退回到逐个试这些名字
EMBED_CANDIDATES = [
    "text-embedding-v4",
    "text-embedding-v3",
    "qwen3.7-text-embedding",
    "qwen3.7-text-embedding-flash",
    "text-embedding-v2",
]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("API_BASE_URL", "API_KEY", "EMBED_MODEL", "CHAT_MODEL"):
        if os.getenv(key):
            env[key] = os.environ[key]
    return env


def call(url: str, key: str, payload: dict | None = None, timeout: int = 30):
    """返回 (状态码, 解析后的内容或错误文本)。"""
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method="POST" if payload else "GET")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:300]
    except Exception as exc:  # 网络层错误：DNS、超时、证书
        return None, f"{type(exc).__name__}: {exc}"


def explain(code) -> str:
    return {
        401: "认证失败 —— key 无效或已过期",
        403: "无权限 —— key 有效但没开通这个模型",
        404: "模型不存在 —— 名字写错了",
        429: "限流 —— 请求太频繁或额度用尽",
        None: "网络不通 —— 域名、代理或证书问题",
    }.get(code, f"服务端返回 {code}")


def main() -> None:
    env = load_env()
    base = env.get("API_BASE_URL", "").rstrip("/")
    key = env.get("API_KEY", "")

    if not key:
        print("请先复制 .env.example 为 .env，并填写 API_KEY")
        return
    print(f"地址：{base}")
    print(f"密钥：{key[:6]}…{key[-4:]}（共 {len(key)} 位）\n")

    # --- 1. 模型列表 ---
    print("[1/3] 查询可用模型列表")
    code, body = call(f"{base}/models", key)
    available: list[str] = []
    if code == 200 and isinstance(body, dict):
        available = [m.get("id", "") for m in body.get("data", [])]
        print(f"  可用 {len(available)} 个模型")
        emb = [m for m in available if "embed" in m.lower()]
        chat = [m for m in available if m not in emb]
        print(f"  向量模型: {emb if emb else '无'}")
        print(f"  对话模型: 前 8 个 {chat[:8]}")
    else:
        print(f"  失败（{explain(code)}）: {str(body)[:200]}")

    # --- 2. 向量接口 ---
    print("\n[2/3] 测试 embedding 接口")
    models = [env["EMBED_MODEL"]] if env.get("EMBED_MODEL") else []
    models += [m for m in available if "embed" in m.lower() and m not in models]
    models += [m for m in EMBED_CANDIDATES if m not in models]

    ok_models = []
    for model in models:
        code, body = call(
            f"{base}/embeddings", key, {"model": model, "input": "版本控制是一种记录文件变化的系统"}
        )
        if code == 200 and isinstance(body, dict) and body.get("data"):
            vec = body["data"][0]["embedding"]
            ok_models.append(model)
            print(f"  ✓ {model:<32} 维度 {len(vec)}")
        else:
            print(f"  ✗ {model:<32} {explain(code)} | {str(body)[:110]}")

    # --- 3. 对话接口 ---
    print("\n[3/3] 测试对话接口")
    chat_model = env.get("CHAT_MODEL") or ("qwen-plus" if "qwen-plus" in available else "")
    if chat_model:
        code, body = call(
            f"{base}/chat/completions",
            key,
            {"model": chat_model, "messages": [{"role": "user", "content": "只回复两个字：可用"}],
             "max_tokens": 16},
        )
        if code == 200 and isinstance(body, dict):
            reply = body["choices"][0]["message"]["content"].strip()
            print(f"  ✓ {chat_model:<32} 回复：{reply}")
        else:
            print(f"  ✗ {chat_model:<32} {explain(code)} | {str(body)[:110]}")
    else:
        print("  跳过：.env 里没有 CHAT_MODEL，且模型列表里没找到 qwen-plus")

    # --- 结论 ---
    print("\n" + "=" * 60)
    if ok_models:
        print(f"结论：key 可用。向量模型请填 {ok_models[0]}")
        print("      （若客户端仍显示连接失败，是因为它用对话接口在测向量模型）")
    else:
        print("结论：没有任何向量模型可用，需要换 key 或联系服务商开通。")


if __name__ == "__main__":
    main()
