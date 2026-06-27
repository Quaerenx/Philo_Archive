from __future__ import annotations

import html
import json
import re
from pathlib import Path

from sentence_units import render_sentence_spans


def strip_markdown_links(value: str) -> str:
    value = re.sub(r"\[\[([^\n()]+?)\]\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\n()]+)\]\([^)]*\)", r"\1", value)
    return value


def strip_inert_markdown_links(value: str) -> str:
    value = re.sub(r"\[\[([^\n()]+?)\]\]\(javascript:;\)", r"\1", value)
    value = re.sub(r"\[([^\n()]+)\]\(javascript:;\)", r"\1", value)
    return value


def clean_source_markdown_display(text: str) -> str:
    return "\n".join(strip_inert_markdown_links(line) for line in text.splitlines())


def clean_markdown_title(value: str) -> str:
    value = re.sub(r"^#+\s*", "", value.strip())
    value = strip_markdown_links(value)
    value = value.replace("_", "").strip()
    return value


def title_from_markdown(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(40):
                line = handle.readline()
                if not line:
                    break
                if not line.lstrip().startswith("#"):
                    continue
                if "about_the_edition" in line or "$about" in line:
                    continue
                title = clean_markdown_title(line)
                if title:
                    return title
    except OSError:
        pass
    return path.stem


def clean_reading_inline(value: str) -> str:
    value = strip_markdown_links(value)
    value = value.replace("*Erratum:*", "Erratum:")
    value = value.replace("*lies:*", "lies:")
    value = re.sub(r"\s{2,}", " ", value)
    value = value.strip()
    if re.fullmatch(r"\d+\[\d+\]", value):
        value = value.replace("[", ".").rstrip("]")
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


def render_reading_document(text: str) -> dict:
    output: list[str] = []
    toc: list[dict[str, int | str]] = []
    paragraph: list[str] = []
    paragraph_count = 0
    heading_count = 0
    used_anchors: set[str] = set()

    def flush_paragraph() -> None:
        nonlocal paragraph_count
        if not paragraph:
            return
        paragraph_count += 1
        paragraph_id = f"p-{paragraph_count:04d}"
        label = f"문단 {paragraph_count}"
        value = render_sentence_spans(paragraph_id, " ".join(paragraph))
        output.append(
            f'<p id="{paragraph_id}" data-label="{html.escape(label, quote=True)}" data-target-type="paragraph">'
            f'<a class="segment-anchor" href="#{paragraph_id}" '
            f'aria-label="{html.escape(label, quote=True)}">&#182;</a>{value}</p>'
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
            output.append("<hr>")
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                continue
            line = " ".join(cell for cell in cells if cell)

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            heading_level = len(heading.group(1))
            flush_paragraph()
            heading_count += 1
            level = min(heading_level, 4)
            value = clean_reading_inline(heading.group(2)).strip(".")
            if re.fullmatch(r"[0-9]+", value):
                anchor_base = f"sec-{value}"
                value = f"§ {value}"
            else:
                anchor_base = anchor_slug(value) or f"section-{heading_count:03d}"
            if value:
                anchor = unique_anchor(anchor_base, used_anchors)
                toc.append({"id": anchor, "label": value, "level": level})
                output.append(
                    f'<h{level} id="{anchor}" data-label="{html.escape(value, quote=True)}" data-target-type="section">'
                    f'<a class="segment-anchor" href="#{anchor}" '
                    f'aria-label="구역 링크">#</a>{html.escape(value)}</h{level}>'
                )
            continue

        if line.startswith(">"):
            flush_paragraph()
            value = clean_reading_inline(line.lstrip("> "))
            output.append(f"<blockquote>{html.escape(value)}</blockquote>")
            continue

        cleaned = clean_reading_inline(line)
        if cleaned:
            paragraph.append(cleaned)

    flush_paragraph()
    return {
        "html": "\n".join(output),
        "toc": toc,
        "paragraph_count": paragraph_count,
        "heading_count": heading_count,
    }


def markdown_to_reading_html(text: str) -> str:
    return str(render_reading_document(text)["html"])


def chunk_text(value: str, max_chars: int = 1400) -> list[str]:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return []
    sentences = re.split(r"(?<=[.!?;:\u00bb])\s+", value)
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


def render_segments_from_texts(texts: list[str], prefix: str = "p") -> dict:
    output = []
    paragraph_count = 0
    for text in texts:
        for chunk in chunk_text(text):
            paragraph_count += 1
            segment_id = f"{prefix}-{paragraph_count:04d}"
            escaped_id = html.escape(segment_id, quote=True)
            escaped = render_sentence_spans(segment_id, chunk)
            label = f"문단 {paragraph_count}"
            output.append(
                f'<p id="{escaped_id}" data-label="{html.escape(label, quote=True)}" data-target-type="paragraph">'
                f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{html.escape(label, quote=True)}">&#182;</a>{escaped}</p>'
            )
    return {
        "html": "\n".join(output),
        "toc": [],
        "paragraph_count": paragraph_count,
        "heading_count": 0,
    }


def readable_markdown_text(text: str) -> str:
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
    return " ".join(lines)


def kierkegaard_extract_texts(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    document = payload.get("response", {}).get("document", {})
    for key in ("prose_extract_tesim", "verse_extract_tesim", "performance_extract_tesim", "text_tesim"):
        value = document.get(key)
        if isinstance(value, list):
            texts = [str(item).strip() for item in value if str(item).strip()]
        elif value and str(value).strip():
            texts = [str(value).strip()]
        else:
            texts = []
        if texts:
            return texts
    return []


def render_bible_work_document(work: dict, segments: list[dict]) -> dict:
    output: list[str] = []
    toc: list[dict[str, int | str]] = []
    current_chapter = None
    chapter_count = 0
    text_dir = "rtl" if work.get("language") == "hbo" else "ltr"
    book_title = work.get("title") or work.get("book_name_en") or work.get("book_id") or work.get("work_id", "")

    for segment in segments:
        segment_id = str(segment.get("segment_id", ""))
        chapter = segment.get("chapter")
        if chapter != current_chapter:
            current_chapter = chapter
            chapter_count += 1
            chapter_id = f"{work.get('book_id', work.get('work_id', 'book'))}.{chapter}"
            label = f"Chapter {chapter}"
            toc.append({"id": chapter_id, "label": label, "level": 2})
            output.append(
                f'<h2 id="{html.escape(chapter_id, quote=True)}" data-label="{html.escape(label, quote=True)}" '
                f'data-target-type="chapter"><a class="segment-anchor" href="#{html.escape(chapter_id, quote=True)}" '
                f'aria-label="{html.escape(label, quote=True)}">#</a>{html.escape(label)}</h2>'
            )
        label = str(segment.get("label") or segment_id)
        text = render_sentence_spans(segment_id, str(segment.get("text_raw") or ""))
        escaped_id = html.escape(segment_id, quote=True)
        output.append(
            f'<p id="{escaped_id}" class="verse" data-label="{html.escape(label, quote=True)}" data-target-type="verse">'
            f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{html.escape(label, quote=True)}">&#182;</a>'
            f'<span class="verse-label">{html.escape(segment_id)}</span>'
            f'<span class="verse-text" dir="{text_dir}">{text}</span></p>'
        )

    return {
        "html": "\n".join(output),
        "toc": toc,
        "paragraph_count": len(segments),
        "heading_count": chapter_count,
        "title_for_citation": book_title,
    }
