"""语义向量检索：加载预生成的向量矩阵，按余弦相似度返回 top-k 文本块。

索引结构：numpy 内存矩阵（805 x 1024，float32，已 L2 归一化）。
检索时 query 向量归一化后与矩阵做一次内积（等价余弦相似度），
805 块规模下微秒级完成，是「精确最近邻」，无召回损失。

用法：
    .venv/bin/python src/vector_search.py "如何撤销已经推送的提交"
    .venv/bin/python src/vector_search.py                # 跑内置示例问题

依赖：embed.py 已生成 data/embeddings.npy
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks.jsonl"
VECS = ROOT / "data" / "embeddings.npy"

DEMO_QUERIES = [
    "如何撤销已经推送的提交",
    "rebase 和 merge 有什么区别",
    "git stash 有什么用",
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


def embed_query(base: str, key: str, model: str, query: str) -> np.ndarray:
    """把查询文本编码成单个归一化向量。"""
    payload = json.dumps({"model": model, "input": [query]}).encode()
    req = urllib.request.Request(f"{base}/embeddings", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
    vec = np.asarray(body["data"][0]["embedding"], dtype=np.float32)
    return vec / np.linalg.norm(vec)


class VectorIndex:
    """内存向量索引：矩阵内积即余弦相似度。"""

    def __init__(self, chunks: list[dict], matrix: np.ndarray) -> None:
        assert len(chunks) == matrix.shape[0], "块数与向量行数不一致"
        self.chunks = chunks
        self.matrix = matrix

    @classmethod
    def load(cls) -> "VectorIndex":
        chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
        matrix = np.load(VECS)
        return cls(chunks, matrix)

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> list[tuple[float, int]]:
        scores = self.matrix @ query_vec  # (N,) 余弦相似度
        top = np.argsort(-scores)[:top_k]
        return [(float(scores[i]), int(i)) for i in top]


def main() -> None:
    if not VECS.exists():
        raise SystemExit("找不到 data/embeddings.npy：请先运行 .venv/bin/python src/embed.py")

    env = load_env()
    base = env.get("API_BASE_URL", "").rstrip("/")
    key = env.get("API_KEY", "")
    model = env.get("EMBED_MODEL", "text-embedding-v4")
    if not key:
        raise SystemExit("API_KEY 为空")

    index = VectorIndex.load()
    print(f"已加载向量索引：{len(index.chunks)} 块，维度 {index.matrix.shape[1]}\n")

    queries = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else DEMO_QUERIES
    for query in queries:
        qv = embed_query(base, key, model, query)
        print("=" * 74)
        print(f"问题：{query}")
        for rank, (score, idx) in enumerate(index.search(qv, top_k=5), 1):
            c = index.chunks[idx]
            path = " > ".join(x for x in (c["chapter"], c["section"], c["subsection"]) if x)
            snippet = c["text"].split("\n\n", 1)[-1].replace("\n", " ")[:150]
            print(f"  {rank}. [相似度 {score:.4f}] {c['id']}  页{c['pages'][0]}+  {path}")
            print(f"     {snippet}")
        print()


if __name__ == "__main__":
    main()
