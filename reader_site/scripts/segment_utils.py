from __future__ import annotations

import re


def clean_reading_inline(value: str) -> str:
    value = re.sub(r"\[\[([^\]]+)\]\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = value.replace("*Erratum:*", "Erratum:")
    value = value.replace("*lies:*", "lies:")
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip()
    if re.fullmatch(r"\[[0-9]+\.?\]", value):
        value = value.strip("[]")
    return value


def anchor_slug(value: str) -> str:
    value = value.lower()
    value = value.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def unique_anchor(base: str, used: set[str]) -> str:
    anchor = base or "section"
    if anchor not in used:
        used.add(anchor)
        return anchor
    index = 2
    while f"{anchor}-{index}" in used:
        index += 1
    anchor = f"{anchor}-{index}"
    used.add(anchor)
    return anchor


def text_preview(value: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def chunk_text(value: str, max_chars: int = 1400) -> list[str]:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return []
    sentences = re.split(r"(?<=[.!?;:»])\s+", value)
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks or [value]


def markdown_segments(text: str, prefix: str = "p") -> list[dict]:
    records = []
    paragraph: list[str] = []
    paragraph_count = 0
    heading_count = 0
    used_anchors: set[str] = set()

    def flush_paragraph() -> None:
        nonlocal paragraph_count
        if not paragraph:
            return
        paragraph_count += 1
        segment_id = f"{prefix}-{paragraph_count:04d}"
        text_raw = " ".join(paragraph).strip()
        records.append(
            {
                "segment_id": segment_id,
                "segment_type": "paragraph",
                "order": len(records) + 1,
                "label": f"Paragraph {paragraph_count}",
                "text_raw": text_raw,
                "text_preview": text_preview(text_raw),
            }
        )
        paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if "about_the_edition" in line:
            continue
        if re.fullmatch(r"[-*_ ]{3,}", line):
            flush_paragraph()
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                continue
            line = " ".join(cell for cell in cells if cell)

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            heading_count += 1
            value = clean_reading_inline(heading.group(2)).strip(".")
            if re.fullmatch(r"[0-9]+", value):
                anchor_base = f"sec-{value}"
                value = f"§ {value}"
            else:
                anchor_base = anchor_slug(value) or f"section-{heading_count:03d}"
            if value:
                segment_id = unique_anchor(anchor_base, used_anchors)
                records.append(
                    {
                        "segment_id": segment_id,
                        "segment_type": "section",
                        "order": len(records) + 1,
                        "label": value,
                        "text_raw": value,
                        "text_preview": text_preview(value),
                    }
                )
            continue

        if line.startswith(">"):
            flush_paragraph()
            value = clean_reading_inline(line.lstrip("> "))
            if value:
                segment_id = f"quote-{len(records) + 1:04d}"
                records.append(
                    {
                        "segment_id": segment_id,
                        "segment_type": "quote",
                        "order": len(records) + 1,
                        "label": f"Quote {len(records) + 1}",
                        "text_raw": value,
                        "text_preview": text_preview(value),
                    }
                )
            continue

        cleaned = clean_reading_inline(line)
        if cleaned:
            paragraph.append(cleaned)

    flush_paragraph()
    return records


def readable_markdown_chunks(text: str, prefix: str = "p", max_chars: int = 1400) -> list[dict]:
    lines = []
    in_front_matter = False
    saw_front_matter = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# ") and not lines and not saw_front_matter:
            in_front_matter = True
            continue
        if in_front_matter and line.startswith("- "):
            saw_front_matter = True
            continue
        if in_front_matter and re.fullmatch(r"[-*_ ]{3,}", line):
            in_front_matter = False
            continue
        if in_front_matter and saw_front_matter:
            continue
        if re.fullmatch(r"[-*_ ]{3,}", line):
            continue
        if line in {"Collapse", "Drag"}:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            line = heading.group(1)
        cleaned = clean_reading_inline(line)
        if cleaned:
            lines.append(cleaned)

    records = []
    for index, chunk in enumerate(chunk_text(" ".join(lines), max_chars=max_chars), start=1):
        segment_id = f"{prefix}-{index:04d}"
        records.append(
            {
                "segment_id": segment_id,
                "segment_type": "paragraph",
                "order": index,
                "label": f"Paragraph {index}",
                "text_raw": chunk,
                "text_preview": text_preview(chunk),
            }
        )
    return records
