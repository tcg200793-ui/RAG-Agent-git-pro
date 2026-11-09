"""第二轮探查：完整书签 + 典型页的块结构（字体/字号/文本）。

运行：.venv/bin/python scripts/inspect_pdf2.py
"""
import collections
from pathlib import Path

import pymupdf

PDF = Path(__file__).resolve().parent.parent / "data" / "progit-zh.pdf"


def dump_page(doc, pno: int, limit: int = 10) -> None:
    page = doc[pno]
    print(f"\n--- PDF 第 {pno + 1} 页（0-based {pno}）---")
    blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
    for block in blocks[:limit]:
        fonts, sizes, parts = set(), set(), []
        for line in block["lines"]:
            line_fonts = set()
            for span in line["spans"]:
                fonts.add(span["font"])
                line_fonts.add(span["font"])
                sizes.add(round(span["size"], 1))
                parts.append(span["text"])
            kind = "MONO-ONLY" if line_fonts == {"RobotoMono-Regular"} else "mixed"
            parts.append(f" [{kind}]")
        text = "".join(parts).replace("\n", " ")
        print(f"  y={block['bbox'][1]:>6.1f} size={sorted(sizes)} font={sorted(fonts)}")
        print(f"      {text[:100]}")


def main() -> None:
    doc = pymupdf.open(PDF)
    toc = doc.get_toc(simple=True)

    print("=== 完整书签树 ===")
    for lv, title, page in toc:
        print(f"  L{lv} p{page:>3}  {'    ' * (lv - 1)}{title}")

    for pno in (18, 22, 60, 120, 300):
        dump_page(doc, pno)


if __name__ == "__main__":
    main()
