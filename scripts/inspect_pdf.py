"""探查 Pro Git 中文 PDF 的内部结构，为切块策略提供依据。

只读，不产出中间文件。运行：
    .venv/bin/python scripts/inspect_pdf.py
"""
import collections
from pathlib import Path

import pymupdf

PDF = Path(__file__).resolve().parent.parent / "data" / "progit-zh.pdf"


def main() -> None:
    doc = pymupdf.open(PDF)
    print(f"页数: {len(doc)}\n")

    # ---- 书签树 ----
    toc = doc.get_toc(simple=True)
    levels = collections.Counter(lv for lv, _, _ in toc)
    print(f"书签条目数: {len(toc)}，各层级条数: {dict(sorted(levels.items()))}")
    print("前 12 条书签:")
    for lv, title, page in toc[:12]:
        print(f"  L{lv} p{page:>3}  {'  ' * (lv - 1)}{title}")
    print("后 6 条书签:")
    for lv, title, page in toc[-6:]:
        print(f"  L{lv} p{page:>3}  {'  ' * (lv - 1)}{title}")

    # ---- 字号与字体分布 ----
    sizes: collections.Counter = collections.Counter()
    fonts: collections.Counter = collections.Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes[round(span["size"], 1)] += len(span["text"])
                        fonts[span["font"]] += len(span["text"])

    print("\n字号分布（按字符数，前 8）:")
    for size, cnt in sizes.most_common(8):
        print(f"  {size:>5}pt  {cnt:>7} 字")
    print("\n字体分布（按字符数，前 6）:")
    for font, cnt in fonts.most_common(6):
        print(f"  {font:<34} {cnt:>7} 字")

    # ---- 页眉页脚候选：位于页面上下边缘的文本 ----
    edge_text = collections.Counter()
    for page in doc:
        h = page.rect.height
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            top, bottom = block["bbox"][1], block["bbox"][3]
            if bottom < h * 0.07 or top > h * 0.93:
                text = "".join(
                    s["text"] for line in block["lines"] for s in line["spans"]
                ).strip()
                if text:
                    edge_text[text] += 1

    print(f"\n页边区域出现的文本种类: {len(edge_text)}（列出频次最高的 12 个）")
    for text, cnt in edge_text.most_common(12):
        print(f"  {cnt:>4} 次  {text[:60]!r}")


if __name__ == "__main__":
    main()
