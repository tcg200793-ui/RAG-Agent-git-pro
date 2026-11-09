"""把 data/chunks.jsonl 的每个文本块生成向量嵌入。

调用阿里百炼 DashScope 的 OpenAI 兼容接口 text-embedding-v4，
批量生成 805 个块的 1024 维向量，写入 data/embeddings.npy。

运行：
    .venv/bin/python src/embed.py
产出：
    data/embeddings.npy   (805 x 1024 的 float32 矩阵，行序与 chunks.jsonl 一致)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks.jsonl"
OUT = ROOT / "data" / "embeddings.npy"

# 每批文本数：text-embedding-v4 接口上限为 10 条/批
BATCH_SIZE = 10
# 单条最长 token：超长块截断（text-embedding-v4 上限 8192 token，这里保守截到 4000 字）
MAX_CHARS_PER_ITEM = 4000
RETRY = 3


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


def embed_batch(base: str, key: str, model: str, texts: list[str]) -> list[list[float]]:
    """调用 /embeddings 批量嵌入，返回按输入顺序排列的向量列表。"""
    payload = json.dumps(
        {"model": model, "input": texts, "encoding_format": "float"}
    ).encode()
    req = urllib.request.Request(
        f"{base}/embeddings", data=payload, method="POST"
    )
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    last_err: Exception | None = None
    for attempt in range(RETRY):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode())
            # 返回的 data 数组按 input 顺序排列；接口保证顺序，但这里稳妥起见不依赖
            return [d["embedding"] for d in body["data"]]
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")[:200]
            # 4xx 不重试（key/模型/权限问题重试无用），5xx 才退避重试
            if exc.code < 500:
                raise RuntimeError(f"HTTP {exc.code}: {err}") from exc
            last_err = exc
        except Exception as exc:  # 网络层错误
            last_err = exc
        time.sleep(2 ** attempt)

    raise RuntimeError(f"重试 {RETRY} 次仍失败: {last_err}")


def main() -> None:
    env = load_env()
    base = env.get("API_BASE_URL", "").rstrip("/")
    key = env.get("API_KEY", "")
    model = env.get("EMBED_MODEL", "text-embedding-v4")

    if not key:
        raise SystemExit("API_KEY 为空：请先填好 .env 里的 API_KEY 再运行")

    chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
    print(f"待嵌入 {len(chunks)} 块，模型 {model}，批大小 {BATCH_SIZE}")

    all_vecs: list[list[float]] = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"][:MAX_CHARS_PER_ITEM] for c in batch]
        try:
            vecs = embed_batch(base, key, model, texts)
        except RuntimeError as exc:
            raise SystemExit(f"第 {i // BATCH_SIZE + 1} 批失败，终止：{exc}") from exc
        all_vecs.extend(vecs)
        print(f"  已完成 {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)}")

    matrix = np.asarray(all_vecs, dtype=np.float32)
    # L2 归一化：让后续内积 == 余弦相似度
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / norms

    np.save(OUT, matrix)
    print(f"\n完成：向量矩阵 {matrix.shape} 已写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
