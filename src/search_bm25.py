"""零依赖 BM25 关键词检索：不需要 embedding、不需要 API key、不需要向量库。

设计要点：
  - 不引入 jieba：中文用「相邻二字」切片（bigram），英文/命令按符号切
  - BM25 只用标准库实现，805 个块全量打分在毫秒级
  - 命令名（git rebase、cherry-pick）走英文切片，天然是精确匹配

运行：
    .venv/bin/python src/search_bm25.py "如何撤销已经推送的提交"
    .venv/bin/python src/search_bm25.py            # 跑内置示例问题
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks.jsonl"

CN_RE = re.compile(r"[\u4e00-\u9fff]+")
EN_RE = re.compile(r"[a-z0-9][a-z0-9_.\-/]*")

DEMO_QUERIES = [
    "如何撤销已经推送的提交",
    "rebase 和 merge 有什么区别",
    "git stash 有什么用",
]


def tokenize(text: str) -> list[str]:
    """中英分开切：英文保留命令式整词，中文切二字组。"""
    text = text.lower()
    tokens = [w for w in EN_RE.findall(text) if len(w) >= 2]
    for seg in CN_RE.findall(text):
        # 单字区间退化为单字，避免"的""了"这种也要单独成词
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
    return tokens


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.n)
        self.tf = [Counter(d) for d in docs]
        self.df: dict[str, int] = defaultdict(int)
        for d in docs:
            for term in set(d):
                self.df[term] += 1

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.n - df + 0.5) / (df + 0.5) + 1)

    def score(self, q_terms: list[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        total = 0.0
        for term in q_terms:
            f = tf.get(term, 0)
            if not f:
                continue
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            total += self.idf(term) * f * (self.k1 + 1) / denom
        return total

    def search(self, query: str, top_k: int = 3) -> list[tuple[float, int]]:
        q_terms = tokenize(query)
        scored = [(self.score(q_terms, i), i) for i in range(self.n)]
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]


def main() -> None:
    chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
    bm25 = BM25([tokenize(c["text"]) for c in chunks])
    print(f"已索引 {len(chunks)} 块，平均每块 {bm25.avgdl:.0f} 个检索词\n")

    queries = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else DEMO_QUERIES
    for query in queries:
        print("=" * 74)
        print(f"问题：{query}")
        for rank, (score, idx) in enumerate(bm25.search(query, top_k=3), 1):
            c = chunks[idx]
            path = " > ".join(x for x in (c["chapter"], c["section"], c["subsection"]) if x)
            snippet = c["text"].split("\n\n", 1)[-1].replace("\n", " ")[:150]
            print(f"  {rank}. [{score:5.2f}] {c['id']}  页{c['pages'][0]}+  {path}")
            print(f"     {snippet}")
        print()


if __name__ == "__main__":
    main()
