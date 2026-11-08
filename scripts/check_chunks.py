"""抽样检查 chunks.jsonl 的质量。

运行：.venv/bin/python scripts/check_chunks.py [条数]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "chunks.jsonl"


def load() -> list[dict]:
    return [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]


def show(chunk: dict, title: str) -> None:
    print("=" * 78)
    print(f"{title} | {chunk['id']} | {len(chunk['text'])} 字 | 页 {chunk['pages']}")
    print("-" * 78)
    print(chunk["text"][:700])
    print("..." if len(chunk["text"]) > 700 else "")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    chunks = load()

    # 均匀抽 n 条，避免只看开头
    step = max(1, len(chunks) // n)
    for i in list(range(0, len(chunks), step))[:n]:
        show(chunks[i], "均匀抽样")

    longest = max(chunks, key=lambda c: len(c["text"]))
    show(longest, "最长块")

    shortest = min(chunks, key=lambda c: len(c["text"]))
    show(shortest, "最短块")

    # 检查噪声残留
    bad = [c for c in chunks if any(k in c["text"] for k in ("..........", "章节译者审校者"))]
    print("=" * 78)
    print(f"疑似目录/页脚残留：{len(bad)} 块")
    for c in bad[:3]:
        print(f"  {c['id']} {c['text'][:60]!r}")


if __name__ == "__main__":
    main()
