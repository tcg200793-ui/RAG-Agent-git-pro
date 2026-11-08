"""把 Pro Git 中文 PDF 切成适合向量化的语义块。

策略（依据 scripts/inspect_pdf.py 的实测结构）：
  - 用字号重建层级：22pt=章 18pt=节 13pt=小节 10.5pt=正文 11pt=代码 9pt=页码
  - 段落就是 block，block 内多行按中英文规则合并
  - 页码（9pt 纯数字）直接丢弃
  - 先按"小节"分组，组内按段落打包成 <=800 字的块，末尾保留约 100 字重叠
  - 每个块开头拼上「书名 > 章 > 节 > 小节」路径，给向量一个语境锚点

运行：.venv/bin/python src/build_chunks.py
产出：data/chunks.jsonl
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "progit-zh.pdf"
OUT = ROOT / "data" / "chunks.jsonl"

BOOK_TITLE = "Pro Git"

# 实测得到的字号 → 语义角色映射
HEADING_BY_SIZE = {22.0: "h1", 18.0: "h2", 13.0: "h3"}
BODY_SIZE = 10.5
CODE_SIZE = 11.0
PAGENUM_SIZE = 9.0

MAX_CHARS = 800      # 单块目标长度（中文按字数）
OVERLAP_CHARS = 120  # 块间重叠
MIN_CHUNK_CHARS = 150  # 短于此的块并入前一块

PAGE_NUM_RE = re.compile(r"^\d{1,3}$")
FIGURE_RE = re.compile(r"^Figure\s+\d+\.")  # 图注：图片本身没进文本，留着只是噪声
SENT_END = "。！？；：”」）.!?"


def join_lines(lines) -> str:
    """把一个 block 内的多行合并成一段，中文直接拼、英文之间补空格。"""
    out = ""
    for line in lines:
        piece = "".join(span["text"] for span in line["spans"])
        if not piece:
            continue
        if not out:
            out = piece
        elif out.endswith("-") and piece[:1].islower():
            # 英文单词被连字符断行：git-\ncommit -> gitcommit 的坑，这里保留连字符前的部分
            out = out[:-1] + piece
        elif (
            out[-1].isascii()
            and out[-1].isalnum()
            and piece[0].isascii()
            and piece[0].isalnum()
        ):
            out += " " + piece
        else:
            out += piece
    return out


def classify(block) -> dict | None:
    """判断一个 block 的角色，返回 {kind, text, size}；无关内容返回 None。"""
    lines = block["lines"]
    spans = [s for line in lines for s in line["spans"]]
    raw = "".join(s["text"] for s in spans)
    if not raw.strip():
        return None

    sizes = {round(s["size"], 1) for s in spans}
    max_size = max(sizes)

    # 页码：页脚区的纯数字小块
    if sizes == {PAGENUM_SIZE} and PAGE_NUM_RE.match(raw.strip()):
        return None

    # 代码块：绝大多数行的字体都是等宽
    mono_lines = sum(
        1 for line in lines if all("Mono" in s["font"] for s in line["spans"])
    )
    if mono_lines / len(lines) >= 0.6 or sizes == {CODE_SIZE}:
        text = "\n".join(
            "".join(s["text"] for s in line["spans"]).rstrip() for line in lines
        )
        return {"kind": "code", "text": text.strip("\n"), "size": max_size}

    if max_size in HEADING_BY_SIZE:
        return {
            "kind": HEADING_BY_SIZE[max_size],
            "text": join_lines(lines).strip(),
            "size": max_size,
        }

    text = join_lines(lines).strip()
    if not text:
        return None
    if FIGURE_RE.match(text):
        return None
    kind = "list" if text[:1] in "•·-–*" else "p"
    return {"kind": kind, "text": text, "size": max_size}


def extract_items(doc, start_page: int, end_page: int) -> list[dict]:
    """按页序抽出所有语义单元，附带来源页码。"""
    items: list[dict] = []
    for pno in range(start_page, end_page + 1):
        page = doc[pno]
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            item = classify(block)
            if item is None:
                continue
            item["page"] = pno + 1
            items.append(item)
    return items


def split_by_heading(items: list[dict]) -> list[dict]:
    """按 h2/h3 分组：每组是一个 {path, items} 的切块单元。"""
    chapter = section = subsection = ""
    groups: list[dict] = []
    current = {"chapter": "", "section": "", "subsection": "", "items": []}
    groups.append(current)

    for item in items:
        kind = item["kind"]
        if kind == "h1":
            chapter, section, subsection = item["text"], "", ""
            current = {"chapter": chapter, "section": "", "subsection": "", "items": []}
            groups.append(current)
            continue
        if kind == "h2":
            section, subsection = item["text"], ""
            current = {
                "chapter": chapter,
                "section": section,
                "subsection": "",
                "items": [],
            }
            groups.append(current)
            continue
        if kind == "h3":
            subsection = item["text"]
            current = {
                "chapter": chapter,
                "section": section,
                "subsection": subsection,
                "items": [],
            }
            groups.append(current)
            continue
        current["items"].append(item)
    return [g for g in groups if g["items"]]


def split_long_item(item: dict) -> list[dict]:
    """超长段落按句子切开，避免单条撑爆一个块。"""
    text = item["text"]
    if len(text) <= MAX_CHARS * 1.5:
        return [item]
    pieces, buf = [], ""
    for sent in re.split(r"(?<=[。！？!?])", text):
        if buf and len(buf) + len(sent) > MAX_CHARS:
            pieces.append(buf)
            buf = sent
        else:
            buf += sent
    if buf:
        pieces.append(buf)
    return [{**item, "text": p} for p in pieces if p.strip()]


def wrap_code(text: str) -> str:
    """用围栏包住代码。围栏长度取文本中最长连续反引号 +1，避免嵌套破坏 Markdown。"""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def pack_group(group: dict) -> list[dict]:
    """把一组 items 打包成若干 <=MAX_CHARS 的块，块间保留尾部重叠。"""
    flat: list[dict] = []
    for item in group["items"]:
        flat.extend(split_long_item(item))

    chunks: list[list[dict]] = []
    buf: list[dict] = []
    buf_len = 0

    def flush() -> None:
        """收掉当前缓冲，并把尾部若干条留作下一块的重叠上下文。"""
        nonlocal buf, buf_len
        if not buf:
            return
        chunks.append(list(buf))
        tail: list[dict] = []
        tail_len = 0
        for prev in reversed(buf):
            if tail_len + len(prev["text"]) > OVERLAP_CHARS:
                break
            tail.insert(0, prev)
            tail_len += len(prev["text"])
        buf, buf_len = tail, tail_len

    for item in flat:
        # 代码块不会被从中间劈开，但连续多个代码块堆叠时同样要在这里断开
        if buf and buf_len + len(item["text"]) > MAX_CHARS:
            flush()
        buf.append(item)
        buf_len += len(item["text"])
    flush()

    # 过短的碎块并入同组前一块，避免「总结」这类 70 字独占一个向量位
    merged: list[list[dict]] = []
    for c in chunks:
        if merged and sum(len(it["text"]) for it in c) < MIN_CHUNK_CHARS:
            merged[-1].extend(c)
        else:
            merged.append(list(c))

    path = " > ".join(x for x in (group["chapter"], group["section"], group["subsection"]) if x)
    result = []
    for c in merged:
        body = "\n\n".join(wrap_code(it["text"]) if it["kind"] == "code" else it["text"] for it in c)
        if len(body.strip()) < 40:
            continue
        result.append(
            {
                "text": f"《{BOOK_TITLE}》{path}\n\n{body}",
                "chapter": group["chapter"],
                "section": group["section"],
                "subsection": group["subsection"],
                "pages": sorted({it["page"] for it in c}),
                "has_code": any(it["kind"] == "code" for it in c),
            }
        )
    return result


def main() -> None:
    doc = pymupdf.open(PDF)

    # 正文范围：从「引言」到「索引」之前，跳过封面/目录/许可证/索引
    toc = doc.get_toc(simple=True)
    by_title = {title.strip(): page for _, title, page in toc}
    start = by_title.get("引言", 17)
    index_page = next(
        (page for lv, title, page in toc if lv == 1 and title.strip() == "索引"),
        len(doc),
    )
    print(f"正文范围：PDF 第 {start} 页 ~ 第 {index_page - 1} 页（共 {len(doc)} 页）")

    items = extract_items(doc, start - 1, index_page - 2)
    print(f"语义单元：{len(items)} 个，分布 {dict(Counter(i['kind'] for i in items))}")

    groups = split_by_heading(items)
    all_chunks: list[dict] = []
    for group in groups:
        all_chunks.extend(pack_group(group))

    with OUT.open("w", encoding="utf-8") as f:
        for idx, chunk in enumerate(all_chunks, 1):
            chunk["id"] = f"pg-{idx:04d}"
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    lens = [len(c["text"]) for c in all_chunks]
    lens.sort()
    print(f"\n切块完成：{len(all_chunks)} 块 -> {OUT.relative_to(ROOT)}")
    print(f"  字数 中位数 {lens[len(lens) // 2]} / 最短 {lens[0]} / 最长 {lens[-1]} / 总字数 {sum(lens)}")
    print(f"  含代码块 {sum(c['has_code'] for c in all_chunks)} 块")
    print(f"  覆盖章节 {len({c['chapter'] for c in all_chunks})} 章")


if __name__ == "__main__":
    main()
