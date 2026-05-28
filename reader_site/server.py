from __future__ import annotations

import argparse
import csv
import heapq
import hashlib
import html
import json
import mimetypes
import os
import re
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4


SITE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[1])).resolve()
TEMPLATES = SITE / "templates"
NIETZSCHE_CATALOG = SITE / "data" / "nietzsche_catalog.json"
NIETZSCHE_METADATA = SITE / "data" / "nietzsche_metadata.json"
NIETZSCHE_CONCEPTS = SITE / "data" / "nietzsche_concepts.json"
NOTES_DIR = SITE / "data" / "notes"
NIETZSCHE_NOTES = NOTES_DIR / "nietzsche_notes.jsonl"
BIBLE_METADATA = SITE / "data" / "bible_metadata.json"
BIBLE_SEGMENTS = SITE / "data" / "bible_segments.jsonl"
KIERKEGAARD_METADATA = SITE / "data" / "kierkegaard_metadata.json"
WITTGENSTEIN_METADATA = SITE / "data" / "wittgenstein_metadata.json"
SEARCH_INDEX = SITE / "data" / "search_index.jsonl"
SEARCH_DB = SITE / "data" / "search_index.sqlite"

NIETZSCHE_OUTPUT = ROOT / "니체_원서수집" / "nietzsche" / "nietzsche" / "output"
WITTGENSTEIN_OUTPUT = ROOT / "비트겐슈타인_원서수집" / "wittgenstein" / "wittgenstein" / "output"
BIBLE_OUTPUT = ROOT / "성경_원서수집" / "bible" / "bible" / "output"
KIERKEGAARD_TEXTS = (
    ROOT
    / "키르케고르_원서수집"
    / "kierkegaard"
    / "kierkegaard"
    / "data"
    / "kierkegaard"
    / "raw"
    / "texts"
)

CORPUS_ROOTS = [
    ROOT / "니체_원서수집",
    ROOT / "비트겐슈타인_원서수집",
    ROOT / "성경_원서수집",
    ROOT / "키르케고르_원서수집",
]

SOURCE_SUFFIXES = {".md", ".html", ".json", ".pdf", ".txt", ".csv"}
ARCHIVE_CACHE: dict | None = None
BIBLE_SEGMENTS_CACHE: tuple[float, list[dict]] | None = None


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def render_template(name: str, values: dict[str, str]) -> str:
    template = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "", value.strip())


def notes_path(corpus_id: str) -> Path:
    corpus_id = safe_slug(corpus_id)
    if not corpus_id:
        raise ValueError("missing corpus id")
    return NOTES_DIR / f"{corpus_id}_notes.jsonl"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def relative_source_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def source_href(path: Path) -> str:
    return "/source?path=" + quote(relative_source_path(path), safe="")


def read_href(path: Path) -> str:
    return "/read?path=" + quote(relative_source_path(path), safe="")


def work_href(author: str, work_id: str) -> str:
    return f"/work/{quote(author, safe='')}/{quote(work_id, safe='')}"


def viewer_href(path: Path) -> str:
    if path.suffix.lower() == ".md":
        return read_href(path)
    return source_href(path)


def clean_markdown_title(value: str) -> str:
    value = re.sub(r"^#+\s*", "", value.strip())
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
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


def first_value(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return ""


def file_link(path: Path, label: str | None = None, meta: str | None = None) -> dict:
    return {
        "label": label or path.stem,
        "href": viewer_href(path),
        "source_href": source_href(path),
        "path": relative_source_path(path),
        "meta": meta or "",
    }


def work_link(path: Path, work_id: str, label: str | None = None, meta: str | None = None) -> dict:
    link = file_link(path, label, meta)
    link["href"] = work_href("nietzsche", work_id)
    link["work_id"] = work_id
    return link


def count_bytes(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def corpus_counts(sections: list[dict], files: list[Path]) -> dict:
    return {
        "files": len(files),
        "links": sum(len(section["links"]) for section in sections),
        "bytes": count_bytes(files),
    }


def build_nietzsche() -> dict:
    sections = []
    all_files: list[Path] = []
    work_files = sorted((NIETZSCHE_OUTPUT / "works").glob("*.md"), key=lambda item: item.name.lower())
    all_files.extend(work_files)
    work_by_name = {path.name: path for path in work_files}
    catalogued: set[str] = set()

    if NIETZSCHE_CATALOG.exists():
        catalog = read_json(NIETZSCHE_CATALOG)
        for section in catalog.get("sections", []):
            links = []
            for work in section.get("works", []):
                path = work_by_name.get(work.get("file", ""))
                if not path:
                    continue
                catalogued.add(path.name)
                work_id = path.stem
                links.append(work_link(path, work_id, work.get("label") or title_from_markdown(path), work.get("meta") or path.stem))
            sections.append(
                {
                    "title": section.get("title") or section.get("id") or "Works",
                    "meta": section.get("meta", ""),
                    "count": len(links),
                    "links": links,
                }
            )

    uncatalogued = [path for path in work_files if path.name not in catalogued]
    if uncatalogued:
        links = [work_link(path, path.stem, title_from_markdown(path), path.name) for path in uncatalogued]
        sections.append({"title": "기타 works", "count": len(links), "links": links})

    for folder, title, meta in [
        ("nachlass", "유고 단상", "Nachlass 파일을 연도별로 정리한 영역입니다."),
        ("briefe", "편지", "Briefe 파일을 연도별로 정리한 영역입니다."),
    ]:
        files = sorted((NIETZSCHE_OUTPUT / folder).glob("*.md"), key=lambda item: item.name.lower())
        all_files.extend(files)
        links = [file_link(path, title_from_markdown(path), path.name) for path in files]
        sections.append({"title": title, "meta": meta, "count": len(files), "links": links})
    return {
        "id": "nietzsche",
        "title": "니체",
        "subtitle": "eKGWB markdown exports, grouped for reading",
        "counts": corpus_counts(sections, all_files),
        "links": [link for section in sections for link in section["links"][:4]],
        "sections": sections,
    }


def build_wittgenstein() -> dict:
    metadata = load_wittgenstein_metadata()
    works = metadata.get("works", {})
    if works:
        grouped = {
            "idp_groups": {"title": "IDP Groups", "links": []},
            "source_items": {"title": "Source Items", "links": []},
        }
        files = []
        for work in works.values():
            variants = work.get("variants", [])
            if variants:
                files.extend((ROOT / variant["source_path"]).resolve() for variant in variants if variant.get("source_path"))
            meta = " / ".join(variant.get("label", "") for variant in variants[:4] if variant.get("label"))
            link = {
                "label": work.get("display_title") or work.get("title") or work.get("work_id"),
                "href": work.get("work_url") or work_href("wittgenstein", work.get("work_id", "")),
                "source_href": variants[0].get("source_url", "") if variants else "",
                "path": variants[0].get("source_path", "") if variants else "",
                "meta": meta,
                "work_id": work.get("work_id", ""),
            }
            grouped.setdefault(work.get("category_id", "source_items"), {"title": work.get("category_title", "Works"), "links": []})
            grouped[work.get("category_id", "source_items")]["links"].append(link)
        sections = []
        for key in ("idp_groups", "source_items"):
            links = sorted(grouped.get(key, {}).get("links", []), key=lambda item: item["label"].lower())
            sections.append({"title": grouped.get(key, {}).get("title", key), "count": len(links), "links": links})
        return {
            "id": "wittgenstein",
            "title": "비트겐슈타인",
            "subtitle": "Wittgenstein Archive exports grouped by siglum",
            "counts": corpus_counts(sections, files + ([WITTGENSTEIN_OUTPUT / "_manifest.json"] if (WITTGENSTEIN_OUTPUT / "_manifest.json").exists() else [])),
            "links": [link for section in sections for link in section["links"][:3]],
            "sections": sections,
        }

    manifest_path = WITTGENSTEIN_OUTPUT / "_manifest.json"
    kind_titles = {
        "idp_transcription_diplomatic": "IDP diplomatic",
        "idp_transcription_linear": "IDP linear",
        "source_transcription_normalized": "Source normalized",
        "source_transcription_diplomatic": "Source diplomatic",
        "source_metadata": "Metadata",
    }
    grouped = {kind: [] for kind in kind_titles}
    files: list[Path] = []

    if manifest_path.exists():
        manifest = read_json(manifest_path)
        for record in manifest.get("records", []):
            kind = record.get("kind")
            if kind not in grouped:
                continue
            output_name = record.get("output_md") or record.get("output_html")
            if not output_name:
                continue
            path = WITTGENSTEIN_OUTPUT / output_name
            if not path.exists():
                continue
            files.append(path)
            label = record.get("siglum") or path.stem
            meta = record.get("variant") or kind_titles[kind]
            grouped[kind].append(file_link(path, label, meta))

    sections = []
    for kind, title in kind_titles.items():
        links = sorted(grouped[kind], key=lambda item: item["label"].lower())
        sections.append({"title": title, "count": len(links), "links": links})

    return {
        "id": "wittgenstein",
        "title": "비트겐슈타인",
        "subtitle": "Wittgenstein Archive exports",
        "counts": corpus_counts(sections, files + ([manifest_path] if manifest_path.exists() else [])),
        "links": [link for section in sections for link in section["links"][:3]],
        "sections": sections,
    }


def bible_section_stats(source_id: str) -> dict[str, int]:
    rows = read_csv_rows(BIBLE_OUTPUT / "mapping" / "source_inventory.csv")
    scoped = [row for row in rows if row.get("source_id") == source_id]
    return {
        "chapters": sum(int(row.get("chapter_count") or 0) for row in scoped),
        "verses": sum(int(row.get("verse_count") or 0) for row in scoped),
        "tokens": sum(int(row.get("token_count") or 0) for row in scoped),
    }


def build_bible() -> dict:
    markdown_root = BIBLE_OUTPUT / "markdown"
    bible_metadata = load_bible_metadata()
    works_by_path = {
        work.get("source_path", ""): work
        for work in bible_metadata.get("works", {}).values()
        if work.get("source_path")
    }
    section_specs = [
        ("Hebrew Bible", "oshb_morphhb", markdown_root / "core_original" / "hebrew_bible_oshb"),
        ("Greek New Testament", "sblgnt", markdown_root / "core_original" / "greek_nt_sblgnt"),
        ("LXX / Deuterocanon", "lxx_swete", markdown_root / "lxx_and_deuterocanon" / "lxx_swete"),
    ]
    sections = []
    all_files: list[Path] = []
    for title, source_id, folder in section_specs:
        files = sorted(
            [path for path in folder.glob("*.md") if path.name.lower() != "readme.md"],
            key=lambda item: item.name.lower(),
        )
        all_files.extend(files)
        stats = bible_section_stats(source_id)
        links = []
        for path in files:
            rel_path = relative_source_path(path)
            work = works_by_path.get(rel_path)
            if work:
                meta_bits = [work.get("source_label") or source_id]
                if work.get("verse_count"):
                    meta_bits.append(f"{int(work['verse_count']):,} verses")
                link = file_link(path, work.get("display_title") or title_from_markdown(path), " · ".join(meta_bits))
                link["href"] = work.get("work_url") or link["href"]
                link["work_id"] = work.get("work_id", "")
                links.append(link)
            else:
                links.append(file_link(path, title_from_markdown(path), path.name))
        meta = f"{stats['verses']:,} verses"
        sections.append({"title": title, "count": len(files), "links": links, "meta": meta})
    readme = markdown_root / "README.md"
    if readme.exists():
        all_files.append(readme)

    return {
        "id": "bible",
        "title": "성경",
        "subtitle": "Hebrew, Greek, and LXX markdown exports",
        "counts": corpus_counts(sections, all_files),
        "links": [link for section in sections for link in section["links"][:3]],
        "sections": sections,
    }


def kierkegaard_label(path: Path) -> tuple[str, str]:
    try:
        payload = read_json(path)
        document = payload.get("response", {}).get("document", {})
        title = (
            first_value(document.get("work_title_tesim"))
            or document.get("sort_title_ssi")
            or first_value(document.get("volume_title_tesim"))
            or document.get("id")
            or path.stem
        )
        meta = document.get("id") or path.stem
        return title, meta
    except (OSError, json.JSONDecodeError):
        return path.stem, path.stem


def build_kierkegaard() -> dict:
    metadata = load_kierkegaard_metadata()
    works = metadata.get("works", {})
    if works:
        links = []
        files = []
        for work in works.values():
            variants = work.get("variants", [])
            if variants:
                files.extend((ROOT / variant["source_path"]).resolve() for variant in variants if variant.get("source_path"))
            meta = " / ".join(variant.get("label", "") for variant in variants if variant.get("label"))
            links.append(
                {
                    "label": work.get("display_title") or work.get("title") or work.get("work_id"),
                    "href": work.get("work_url") or work_href("kierkegaard", work.get("work_id", "")),
                    "source_href": variants[0].get("source_url", "") if variants else "",
                    "path": variants[0].get("source_path", "") if variants else "",
                    "meta": meta,
                    "work_id": work.get("work_id", ""),
                }
            )
        links = sorted(links, key=lambda item: item["label"].lower())
        sections = [
            {
                "title": "Works with variants",
                "meta": "Text, commentary, and textual account are grouped inside each work page.",
                "count": len(links),
                "links": links,
            }
        ]
        return {
            "id": "kierkegaard",
            "title": "키르케고르",
            "subtitle": "Soren Kierkegaards Skrifter grouped by work",
            "counts": corpus_counts(sections, files),
            "links": links[:6],
            "sections": sections,
        }

    section_titles = {
        "text": "Text",
        "commentary": "Commentary",
        "textual_account": "Textual Account",
    }
    grouped = {key: [] for key in section_titles}
    files = sorted(KIERKEGAARD_TEXTS.glob("**/*.json"), key=lambda item: item.as_posix().lower())

    for path in files:
        section_key = path.parent.name
        if section_key not in grouped:
            continue
        title, meta = kierkegaard_label(path)
        grouped[section_key].append(file_link(path, title, meta))

    sections = []
    for key, title in section_titles.items():
        links = sorted(grouped[key], key=lambda item: (item["label"].lower(), item["meta"].lower()))
        sections.append({"title": title, "count": len(links), "links": links})

    return {
        "id": "kierkegaard",
        "title": "키르케고르",
        "subtitle": "Soren Kierkegaards Skrifter raw JSON exports",
        "counts": corpus_counts(sections, files),
        "links": [link for section in sections for link in section["links"][:3]],
        "sections": sections,
    }


def build_archive() -> dict:
    global ARCHIVE_CACHE
    if ARCHIVE_CACHE is not None:
        return ARCHIVE_CACHE
    ARCHIVE_CACHE = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpora": [
            build_nietzsche(),
            build_bible(),
            build_kierkegaard(),
            build_wittgenstein(),
        ],
    }
    return ARCHIVE_CACHE


def resolve_source_path(value: str) -> Path:
    if not value:
        raise ValueError("missing source path")
    raw = unquote(value)
    requested = Path(raw)
    target = requested.resolve() if requested.is_absolute() else (ROOT / requested).resolve()
    if target.suffix.lower() not in SOURCE_SUFFIXES:
        raise PermissionError("unsupported source file type")
    allowed = any(is_inside(target, root.resolve()) for root in CORPUS_ROOTS)
    if not allowed:
        raise PermissionError("source path is outside allowed corpus roots")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("source file not found")
    return target


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
        value = html.escape(" ".join(paragraph))
        output.append(
            f'<p id="{paragraph_id}" data-label="Paragraph {paragraph_count}" data-target-type="paragraph">'
            f'<a class="segment-anchor" href="#{paragraph_id}" '
            f'aria-label="Paragraph {paragraph_count}">¶</a>{value}</p>'
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
            nonlocal_heading_level = len(heading.group(1))
            flush_paragraph()
            heading_count += 1
            level = min(nonlocal_heading_level, 4)
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
                    f'aria-label="Section link">#</a>{html.escape(value)}</h{level}>'
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


def nietzsche_catalog_record(work_id: str) -> dict:
    file_name = f"{work_id}.md"
    if not NIETZSCHE_CATALOG.exists():
        return {}
    catalog = read_json(NIETZSCHE_CATALOG)
    for section in catalog.get("sections", []):
        for work in section.get("works", []):
            if work.get("file") == file_name:
                record = dict(work)
                record["section_title"] = section.get("title", "")
                record["section_id"] = section.get("id", "")
                return record
    return {}


def load_nietzsche_metadata() -> dict:
    if not NIETZSCHE_METADATA.exists():
        return {"works": {}}
    return read_json(NIETZSCHE_METADATA)


def nietzsche_metadata_record(work_id: str) -> dict:
    return load_nietzsche_metadata().get("works", {}).get(work_id, {})


def load_nietzsche_concepts() -> dict:
    if not NIETZSCHE_CONCEPTS.exists():
        return {"concepts": []}
    return read_json(NIETZSCHE_CONCEPTS)


def load_bible_metadata() -> dict:
    if not BIBLE_METADATA.exists():
        return {"schema_version": 1, "corpus_id": "bible", "works": {}}
    return read_json(BIBLE_METADATA)


def load_kierkegaard_metadata() -> dict:
    if not KIERKEGAARD_METADATA.exists():
        return {"schema_version": 1, "corpus_id": "kierkegaard", "works": {}}
    return read_json(KIERKEGAARD_METADATA)


def load_wittgenstein_metadata() -> dict:
    if not WITTGENSTEIN_METADATA.exists():
        return {"schema_version": 1, "corpus_id": "wittgenstein", "works": {}}
    return read_json(WITTGENSTEIN_METADATA)


def bible_metadata_record(work_id: str) -> dict:
    return load_bible_metadata().get("works", {}).get(work_id, {})


def kierkegaard_metadata_record(work_id: str) -> dict:
    return load_kierkegaard_metadata().get("works", {}).get(work_id, {})


def wittgenstein_metadata_record(work_id: str) -> dict:
    return load_wittgenstein_metadata().get("works", {}).get(work_id, {})


def load_bible_segments() -> list[dict]:
    global BIBLE_SEGMENTS_CACHE
    if not BIBLE_SEGMENTS.exists():
        return []
    mtime = BIBLE_SEGMENTS.stat().st_mtime
    if BIBLE_SEGMENTS_CACHE is None or BIBLE_SEGMENTS_CACHE[0] != mtime:
        BIBLE_SEGMENTS_CACHE = (mtime, read_jsonl(BIBLE_SEGMENTS))
    return BIBLE_SEGMENTS_CACHE[1]


def bible_segments_for_work(work_id: str) -> list[dict]:
    return [segment for segment in load_bible_segments() if segment.get("work_id") == work_id]


def normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def search_snippet(text: str, terms: list[str], radius: int = 90) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - radius)
    end = min(len(text), center + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def score_search_result(text: str, title: str, label: str, terms: list[str]) -> int:
    haystack = normalize_search_text(f"{title} {label} {text}")
    title_haystack = normalize_search_text(f"{title} {label}")
    score = sum(haystack.count(term) for term in terms)
    score += sum(5 for term in terms if term in title_haystack)
    return score


def search_records_sqlite(query: str, corpus_id: str, work_id: str, variant_id: str, limit: int) -> dict:
    terms = [term for term in normalize_search_text(query).split(" ") if term]
    if not terms:
        return {"query": normalize_search_text(query), "count": 0, "results": []}
    clauses = ["search_text LIKE ?"]
    params: list[str] = [f"%{terms[0]}%"]
    for term in terms[1:]:
        clauses.append("search_text LIKE ?")
        params.append(f"%{term}%")
    if corpus_id:
        clauses.append("corpus_id = ?")
        params.append(corpus_id)
    if work_id:
        clauses.append("work_id = ?")
        params.append(work_id)
    if variant_id:
        clauses.append("variant_id = ?")
        params.append(variant_id)
    where = " AND ".join(clauses)
    scan_limit = max(limit * 30, 500)

    connection = sqlite3.connect(SEARCH_DB)
    connection.row_factory = sqlite3.Row
    try:
        total = connection.execute(f"SELECT COUNT(*) FROM search_segments WHERE {where}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT corpus_id, work_id, variant_id, segment_id, segment_type, label, title, url, snippet, search_text
            FROM search_segments
            WHERE {where}
            LIMIT ?
            """,
            [*params, scan_limit],
        ).fetchall()
    finally:
        connection.close()

    ranked = []
    for index, row in enumerate(rows):
        score = score_search_result(row["search_text"], row["title"], row["label"], terms)
        ranked.append(
            (
                score,
                -index,
                {
                    "corpus_id": row["corpus_id"],
                    "work_id": row["work_id"],
                    "variant_id": row["variant_id"],
                    "segment_id": row["segment_id"],
                    "segment_type": row["segment_type"],
                    "title": row["title"],
                    "label": row["label"],
                    "url": row["url"],
                    "snippet": search_snippet(row["snippet"], terms),
                    "score": score,
                },
            )
        )
    results = [item[2] for item in sorted(ranked, reverse=True)[:limit]]
    return {"query": normalize_search_text(query), "count": total, "results": results}


def search_records(query: str, corpus_id: str = "", work_id: str = "", variant_id: str = "", limit: int = 30) -> dict:
    query = normalize_search_text(query)
    terms = [term for term in query.split(" ") if term]
    if not terms:
        return {"query": query, "count": 0, "results": []}
    limit = max(1, min(int(limit), 100))
    if SEARCH_DB.exists():
        return search_records_sqlite(query, corpus_id, work_id, variant_id, limit)
    if not SEARCH_INDEX.exists():
        return {"query": query, "count": 0, "results": [], "error": "search index not found"}

    total_matches = 0
    heap: list[tuple[int, int, dict]] = []
    order = 0
    with SEARCH_INDEX.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if corpus_id and record.get("corpus_id") != corpus_id:
                continue
            if work_id and record.get("work_id") != work_id:
                continue
            if variant_id and record.get("variant_id") != variant_id:
                continue
            haystack = normalize_search_text(
                " ".join(
                    [
                        str(record.get("title", "")),
                        str(record.get("label", "")),
                        str(record.get("text", "")),
                    ]
                )
            )
            if not all(term in haystack for term in terms):
                continue
            text = str(record.get("text", ""))
            title = str(record.get("title", ""))
            label = str(record.get("label", ""))
            score = score_search_result(text, title, label, terms)
            total_matches += 1
            order += 1
            result = {
                "corpus_id": record.get("corpus_id", ""),
                "work_id": record.get("work_id", ""),
                "variant_id": record.get("variant_id", ""),
                "segment_id": record.get("segment_id", ""),
                "segment_type": record.get("segment_type", ""),
                "title": title,
                "label": label,
                "url": record.get("url", ""),
                "snippet": search_snippet(text, terms),
                "score": score,
            }
            item = (score, -order, result)
            if len(heap) < limit:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

    results = [item[2] for item in sorted(heap, reverse=True)]
    return {"query": query, "count": total_matches, "results": results}


def concepts_for_work(work_id: str) -> list[dict]:
    concepts = []
    for concept in load_nietzsche_concepts().get("concepts", []):
        if work_id in concept.get("works", []):
            concepts.append(concept)
    return concepts


def resolve_nietzsche_work(work_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", work_id):
        raise ValueError("invalid work id")
    target = (NIETZSCHE_OUTPUT / "works" / f"{work_id}.md").resolve()
    if not is_inside(target, (NIETZSCHE_OUTPUT / "works").resolve()):
        raise PermissionError("source path is outside allowed corpus roots")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("work not found")
    return target


def resolve_bible_work(work_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", work_id):
        raise ValueError("invalid work id")
    record = bible_metadata_record(work_id)
    if not record:
        raise FileNotFoundError("work not found")
    return record


def resolve_metadata_work(corpus_id: str, work_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", work_id):
        raise ValueError("invalid work id")
    if corpus_id == "kierkegaard":
        record = kierkegaard_metadata_record(work_id)
    elif corpus_id == "wittgenstein":
        record = wittgenstein_metadata_record(work_id)
    else:
        record = {}
    if not record:
        raise FileNotFoundError("work not found")
    return record


def selected_variant(work: dict, variant_id: str, preferred: list[str]) -> dict:
    variants = work.get("variants", [])
    if variant_id:
        for variant in variants:
            if variant.get("variant_id") == variant_id:
                return variant
    for preferred_id in preferred:
        for variant in variants:
            current_id = variant.get("variant_id", "")
            if current_id == preferred_id or current_id.startswith(f"{preferred_id}."):
                return variant
    if not variants:
        raise FileNotFoundError("variant not found")
    return variants[0]


def variant_source_path(variant: dict) -> Path:
    source_path = variant.get("source_path", "")
    if not source_path:
        raise FileNotFoundError("variant source not found")
    target = (ROOT / source_path).resolve()
    if not any(is_inside(target, root.resolve()) for root in CORPUS_ROOTS):
        raise PermissionError("source path is outside allowed corpus roots")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("variant source not found")
    return target


def validate_work_target(corpus_id: str, work_id: str) -> None:
    if corpus_id == "nietzsche":
        resolve_nietzsche_work(work_id)
        return
    if corpus_id == "bible":
        resolve_bible_work(work_id)
        return
    if corpus_id in {"kierkegaard", "wittgenstein"}:
        resolve_metadata_work(corpus_id, work_id)
        return
    raise FileNotFoundError("unknown corpus")


def toc_markup(toc: list[dict[str, int | str]]) -> str:
    if not toc:
        return ""
    links = []
    for item in toc:
        level = int(item["level"])
        anchor = html.escape(str(item["id"]), quote=True)
        label = html.escape(str(item["label"]))
        links.append(f'<a class="toc-link level-{level}" href="#{anchor}">{label}</a>')
    return (
        f'<details class="toc"><summary>Contents ({len(toc)})</summary>'
        f'<div class="toc-links">{"".join(links)}</div></details>'
    )


def concept_markup(concepts: list[dict]) -> str:
    if not concepts:
        return ""
    items = []
    for concept in concepts:
        label = html.escape(concept.get("label", concept.get("id", "")))
        german = html.escape(concept.get("german", ""))
        description = html.escape(concept.get("description", ""))
        text = f"<strong>{label}</strong>"
        if german:
            text += f" <span>{german}</span>"
        if description:
            text += f"<small>{description}</small>"
        items.append(f"<li>{text}</li>")
    return f'<section class="research-card"><h2>Concepts</h2><ul class="concept-list">{"".join(items)}</ul></section>'


def variant_tabs_markup(variants: list[dict] | list[str]) -> str:
    if not variants:
        return ""
    items = []
    for variant in variants:
        if isinstance(variant, dict):
            label = html.escape(str(variant.get("label") or variant.get("id") or "Variant"))
            active = " active" if variant.get("active", True) else ""
            href = variant.get("href", "")
        else:
            label = html.escape(str(variant))
            active = " active"
            href = ""
        if href:
            items.append(f'<a class="variant-tab{active}" href="{html.escape(str(href), quote=True)}">{label}</a>')
        else:
            items.append(f'<span class="variant-tab{active}">{label}</span>')
    return f'<nav class="variant-tabs" aria-label="Text variants">{"".join(items)}</nav>'


def source_notice_markup(title: str, lines: list[str]) -> str:
    clean_lines = [line for line in lines if line]
    if not clean_lines:
        return ""
    items = "".join(f"<li>{html.escape(line)}</li>" for line in clean_lines)
    return f'<section class="research-card"><h2>{html.escape(title)}</h2><ul class="source-notes">{items}</ul></section>'


def variant_tabs_for_work(corpus_id: str, work_id: str, variants: list[dict], active_variant_id: str) -> str:
    tabs = []
    for variant in variants:
        variant_id = variant.get("variant_id", "")
        href = work_href(corpus_id, work_id)
        if variant_id:
            href += "?variant=" + quote(variant_id, safe="")
        tabs.append(
            {
                "label": variant.get("label") or variant_id,
                "href": href,
                "active": variant_id == active_variant_id,
            }
        )
    return variant_tabs_markup(tabs)


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


def render_segments_from_texts(texts: list[str], prefix: str = "p") -> dict:
    output = []
    paragraph_count = 0
    for text in texts:
        for chunk in chunk_text(text):
            paragraph_count += 1
            segment_id = f"{prefix}-{paragraph_count:04d}"
            escaped_id = html.escape(segment_id, quote=True)
            escaped = html.escape(chunk)
            label = f"Paragraph {paragraph_count}"
            output.append(
                f'<p id="{escaped_id}" data-label="{html.escape(label, quote=True)}" data-target-type="paragraph">'
                f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{html.escape(label, quote=True)}">¶</a>{escaped}</p>'
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
    payload = read_json(path)
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
        text = html.escape(str(segment.get("text_raw") or ""))
        escaped_id = html.escape(segment_id, quote=True)
        output.append(
            f'<p id="{escaped_id}" class="verse" data-label="{html.escape(label, quote=True)}" data-target-type="verse">'
            f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{html.escape(label, quote=True)}">¶</a>'
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


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonalArchiveReader/1.0"

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/archive":
            self.send_json(build_archive())
            return
        if parsed.path == "/api/nietzsche/metadata":
            self.send_json(load_nietzsche_metadata())
            return
        if parsed.path == "/api/nietzsche/concepts":
            self.send_json(load_nietzsche_concepts())
            return
        if parsed.path == "/api/bible/metadata":
            self.send_json(load_bible_metadata())
            return
        if parsed.path == "/api/bible/segments":
            self.handle_bible_segments_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/kierkegaard/metadata":
            self.send_json(load_kierkegaard_metadata())
            return
        if parsed.path == "/api/wittgenstein/metadata":
            self.send_json(load_wittgenstein_metadata())
            return
        if parsed.path == "/api/search":
            self.handle_search_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/notes":
            self.handle_notes_get(parse_qs(parsed.query))
            return
        work_match = re.fullmatch(r"/work/([^/]+)/([^/]+)/?", parsed.path)
        if work_match:
            self.handle_work(unquote(work_match.group(1)), unquote(work_match.group(2)), parse_qs(parsed.query))
            return
        if parsed.path == "/read":
            self.handle_read(parse_qs(parsed.query))
            return
        if parsed.path == "/source":
            self.handle_source(parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/notes":
            self.handle_notes_post()
            return
        self.send_error(404)

    def handle_notes_get(self, query: dict[str, list[str]]) -> None:
        corpus_id = query.get("corpus_id", query.get("author", [""]))[0]
        work_id = query.get("work_id", [""])[0]
        target_id = query.get("target_id", [""])[0]
        corpus_id = safe_slug(corpus_id)
        if not corpus_id or not work_id:
            self.send_json({"notes": []})
            return
        try:
            path = notes_path(corpus_id)
        except ValueError:
            self.send_json({"notes": []})
            return
        notes = [
            self.normalize_note_record(note, corpus_id)
            for note in read_jsonl(path)
            if (note.get("corpus_id") or note.get("author")) == corpus_id and note.get("work_id") == work_id
        ]
        if target_id:
            notes = [note for note in notes if note.get("target_id") == target_id]
        self.send_json({"notes": notes})

    def handle_notes_post(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 65536:
            self.send_error(400, "invalid note payload")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return
        corpus_id = safe_slug(str(payload.get("corpus_id") or payload.get("author") or "").strip())
        work_id = str(payload.get("work_id", "")).strip()
        variant_id = str(payload.get("variant_id", "")).strip()
        note_text = str(payload.get("note", "")).strip()
        target_id = str(payload.get("target_id", "")).strip() or "work"
        target_type = str(payload.get("target_type", "")).strip() or "segment"
        target_label = str(payload.get("target_label", "")).strip() or target_id
        quote_text = str(payload.get("quote", "")).strip()
        tags = payload.get("tags", [])
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",") if item.strip()]
        if not corpus_id or not note_text:
            self.send_error(400, "missing required note fields")
            return
        try:
            validate_work_target(corpus_id, work_id)
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            self.send_error(400, str(exc))
            return
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "corpus_id": corpus_id,
            "work_id": work_id,
            "variant_id": variant_id[:120],
            "target_id": target_id[:120],
            "target_type": target_type[:80],
            "target_label": target_label[:240],
            "quote": quote_text[:2000],
            "note": note_text[:5000],
            "tags": [str(tag)[:80] for tag in tags[:12]],
            "url": f"{work_href(corpus_id, work_id)}#{quote(target_id, safe='')}",
        }
        if corpus_id == "nietzsche":
            record["author"] = "nietzsche"
        append_jsonl(notes_path(corpus_id), record)
        self.send_json({"ok": True, "note": record}, status=201)

    def normalize_note_record(self, note: dict, fallback_corpus_id: str) -> dict:
        record = dict(note)
        record["corpus_id"] = record.get("corpus_id") or record.get("author") or fallback_corpus_id
        record["target_type"] = record.get("target_type") or "segment"
        record["variant_id"] = record.get("variant_id") or ""
        return record

    def handle_bible_segments_get(self, query: dict[str, list[str]]) -> None:
        work_id = query.get("work_id", [""])[0]
        if not work_id:
            self.send_json({"segments": []})
            return
        try:
            resolve_bible_work(work_id)
        except (ValueError, FileNotFoundError) as exc:
            self.send_error(404, str(exc))
            return
        self.send_json({"segments": bible_segments_for_work(work_id)})

    def handle_search_get(self, query: dict[str, list[str]]) -> None:
        q = query.get("q", [""])[0]
        corpus_id = safe_slug(query.get("corpus_id", [""])[0])
        work_id = query.get("work_id", [""])[0]
        variant_id = query.get("variant_id", [""])[0]
        try:
            limit = int(query.get("limit", ["30"])[0])
        except ValueError:
            limit = 30
        self.send_json(search_records(q, corpus_id, work_id, variant_id, limit))

    def handle_work(self, corpus_id: str, work_id: str, query: dict[str, list[str]] | None = None) -> None:
        if corpus_id == "bible":
            self.send_bible_work_viewer(work_id)
            return
        if corpus_id == "kierkegaard":
            self.send_kierkegaard_work_viewer(work_id, first_value((query or {}).get("variant", [""])))
            return
        if corpus_id == "wittgenstein":
            self.send_wittgenstein_work_viewer(work_id, first_value((query or {}).get("variant", [""])))
            return
        if corpus_id != "nietzsche":
            self.send_error(404, "unknown corpus")
            return
        try:
            target = resolve_nietzsche_work(work_id)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_nietzsche_work_viewer(work_id, target)

    def handle_read(self, query: dict[str, list[str]]) -> None:
        try:
            target = resolve_source_path(query.get("path", [""])[0])
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        if target.suffix.lower() != ".md":
            self.send_source_viewer(target)
            return
        self.send_reading_viewer(target)

    def handle_source(self, query: dict[str, list[str]]) -> None:
        try:
            target = resolve_source_path(query.get("path", [""])[0])
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        if target.suffix.lower() == ".pdf":
            self.send_file(target, inline=True)
            return
        self.send_source_viewer(target)

    def serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"} or request_path.startswith("/category/"):
            target = SITE / "index.html"
        elif request_path == "/search":
            target = SITE / "search.html"
        else:
            clean = unquote(request_path).lstrip("/")
            target = (SITE / clean).resolve()
            if not is_inside(target, SITE.resolve()):
                self.send_error(403)
                return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        self.send_file(target)

    def send_file(self, target: Path, inline: bool = False) -> None:
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".md":
            content_type = "text/plain"
        if target.suffix in {".html", ".css", ".js", ".svg", ".md", ".txt", ".csv"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if inline:
            self.send_header("Content-Disposition", f'inline; filename="{target.name}"')
        self.end_headers()
        self.wfile.write(body)

    def send_nietzsche_work_viewer(self, work_id: str, target: Path) -> None:
        record = nietzsche_catalog_record(work_id)
        metadata = nietzsche_metadata_record(work_id)
        concepts = concepts_for_work(work_id)
        text = target.read_text(encoding="utf-8", errors="replace")
        document = render_reading_document(text)
        rel_path = relative_source_path(target)
        title_raw = metadata.get("title") or record.get("label") or title_from_markdown(target)
        research_payload = {
            "author": "Friedrich Nietzsche",
            "author_id": "nietzsche",
            "work_id": work_id,
            "title": title_raw,
            "meta": record.get("meta") or work_id,
            "section": record.get("section_title") or "Works",
            "source_path": rel_path,
        }
        model = {
            "corpus_id": "nietzsche",
            "corpus_title": "Nietzsche",
            "category_href": "/category/nietzsche",
            "title": title_raw,
            "work_id": work_id,
            "section": record.get("section_title") or "Works",
            "meta": record.get("meta") or work_id,
            "source_path": rel_path,
            "source_href": source_href(target),
            "toc": toc_markup(document["toc"]),
            "concepts": concept_markup(concepts),
            "variant_tabs": "",
            "heading_count": str(int(document["heading_count"])),
            "segment_count": str(int(document["paragraph_count"])),
            "content": str(document["html"]),
            "body_class": "nietzsche-work",
            "text_direction": "ltr",
            "research": research_payload,
        }
        self.send_work_viewer(model)

    def send_bible_work_viewer(self, work_id: str) -> None:
        try:
            work = resolve_bible_work(work_id)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        segments = bible_segments_for_work(work_id)
        if not segments:
            self.send_error(404, "segments not found")
            return
        document = render_bible_work_document(work, segments)
        source_path = work.get("source_path", "")
        research_payload = {
            "author": work.get("source_label") or work.get("source_id") or "Bible",
            "author_id": "bible",
            "corpus_id": "bible",
            "corpus_title": "Bible",
            "work_id": work_id,
            "variant_id": work.get("variant_id") or work.get("source_id") or "",
            "title": work.get("display_title") or work.get("title") or work_id,
            "citation_title": document["title_for_citation"],
            "source_label": work.get("source_label") or work.get("source_id") or "",
            "default_target_type": "verse",
            "source_path": source_path,
        }
        model = {
            "corpus_id": "bible",
            "corpus_title": "Bible",
            "category_href": "/category/bible",
            "title": work.get("display_title") or work.get("title") or work_id,
            "work_id": work_id,
            "section": work.get("category_title") or "Bible",
            "meta": work.get("source_label") or work.get("source_id") or work_id,
            "source_path": source_path,
            "source_href": work.get("source_url") or "#",
            "toc": toc_markup(document["toc"]),
            "concepts": "",
            "variant_tabs": variant_tabs_markup([{"id": work.get("variant_id"), "label": work.get("source_label") or work.get("source_id")}]),
            "heading_count": str(int(document["heading_count"])),
            "segment_count": str(int(document["paragraph_count"])),
            "content": str(document["html"]),
            "body_class": "bible-work",
            "text_direction": "ltr",
            "research": research_payload,
        }
        self.send_work_viewer(model)

    def send_kierkegaard_work_viewer(self, work_id: str, variant_id: str = "") -> None:
        try:
            work = resolve_metadata_work("kierkegaard", work_id)
            variant = selected_variant(work, variant_id, ["text", "commentary", "textual_account"])
            target = variant_source_path(variant)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        texts = kierkegaard_extract_texts(target)
        document = render_segments_from_texts(texts, "sks")
        active_variant_id = variant.get("variant_id", "")
        source_path = variant.get("source_path", "")
        research_payload = {
            "author": work.get("author") or "Søren Kierkegaard",
            "author_id": "kierkegaard",
            "corpus_id": "kierkegaard",
            "corpus_title": "Kierkegaard",
            "work_id": work_id,
            "variant_id": active_variant_id,
            "title": work.get("display_title") or work.get("title") or work_id,
            "source_label": variant.get("label") or active_variant_id,
            "default_target_type": "paragraph",
            "source_path": source_path,
        }
        notice = source_notice_markup(
            "Source",
            [
                work.get("volume", ""),
                variant.get("label", ""),
                work.get("license", ""),
                variant.get("source_xml", ""),
            ],
        )
        model = {
            "corpus_id": "kierkegaard",
            "corpus_title": "Kierkegaard",
            "category_href": "/category/kierkegaard",
            "title": work.get("display_title") or work.get("title") or work_id,
            "work_id": work_id,
            "section": work.get("category_title") or "Søren Kierkegaards Skrifter",
            "meta": variant.get("label") or active_variant_id,
            "source_path": source_path,
            "source_href": variant.get("source_url") or source_href(target),
            "toc": toc_markup(document["toc"]),
            "concepts": notice,
            "variant_tabs": variant_tabs_for_work("kierkegaard", work_id, work.get("variants", []), active_variant_id),
            "heading_count": str(int(document["heading_count"])),
            "segment_count": str(int(document["paragraph_count"])),
            "content": str(document["html"]),
            "body_class": "kierkegaard-work",
            "text_direction": "ltr",
            "research": research_payload,
        }
        self.send_work_viewer(model)

    def send_wittgenstein_work_viewer(self, work_id: str, variant_id: str = "") -> None:
        try:
            work = resolve_metadata_work("wittgenstein", work_id)
            variant = selected_variant(
                work,
                variant_id,
                [
                    "source_transcription_normalized",
                    "source_transcription_diplomatic",
                    "idp_transcription_linear",
                    "idp_transcription_diplomatic",
                    "source_metadata",
                ],
            )
            target = variant_source_path(variant)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        text = target.read_text(encoding="utf-8", errors="replace")
        document = render_segments_from_texts([readable_markdown_text(text)], "p")
        active_variant_id = variant.get("variant_id", "")
        source_path = variant.get("source_path", "")
        title = work.get("display_title") or work.get("title") or work_id
        research_payload = {
            "author": work.get("author") or "Ludwig Wittgenstein",
            "author_id": "wittgenstein",
            "corpus_id": "wittgenstein",
            "corpus_title": "Wittgenstein",
            "work_id": work_id,
            "variant_id": active_variant_id,
            "title": title,
            "source_label": variant.get("label") or active_variant_id,
            "default_target_type": "paragraph",
            "source_path": source_path,
        }
        notice = source_notice_markup(
            "Rights",
            [
                variant.get("label", ""),
                variant.get("license", ""),
                variant.get("rights_note", ""),
                variant.get("external_source_url", ""),
            ],
        )
        model = {
            "corpus_id": "wittgenstein",
            "corpus_title": "Wittgenstein",
            "category_href": "/category/wittgenstein",
            "title": title,
            "work_id": work_id,
            "section": work.get("category_title") or "Wittgenstein Archive",
            "meta": variant.get("label") or active_variant_id,
            "source_path": source_path,
            "source_href": variant.get("source_url") or source_href(target),
            "toc": toc_markup(document["toc"]),
            "concepts": notice,
            "variant_tabs": variant_tabs_for_work("wittgenstein", work_id, work.get("variants", []), active_variant_id),
            "heading_count": str(int(document["heading_count"])),
            "segment_count": str(int(document["paragraph_count"])),
            "content": str(document["html"]),
            "body_class": "wittgenstein-work",
            "text_direction": "ltr",
            "research": research_payload,
        }
        self.send_work_viewer(model)

    def send_work_viewer(self, model: dict) -> None:
        research_json = json.dumps(model["research"], ensure_ascii=False).replace("</", "<\\/")
        body = render_template(
            "work.html",
            {
                "TITLE": html.escape(str(model.get("title", ""))),
                "CORPUS_TITLE": html.escape(str(model.get("corpus_title", ""))),
                "CORPUS_ID": html.escape(str(model.get("corpus_id", ""))),
                "WORK_ID": html.escape(str(model.get("work_id", ""))),
                "SECTION": html.escape(str(model.get("section", ""))),
                "META": html.escape(str(model.get("meta", ""))),
                "SOURCE_PATH": html.escape(str(model.get("source_path", ""))),
                "SOURCE_HREF": html.escape(str(model.get("source_href", "#")), quote=True),
                "CATEGORY_HREF": html.escape(str(model.get("category_href", "/")), quote=True),
                "TOC": str(model.get("toc", "")),
                "CONCEPTS": str(model.get("concepts", "")),
                "VARIANT_TABS": str(model.get("variant_tabs", "")),
                "HEADING_COUNT": str(model.get("heading_count", "0")),
                "SEGMENT_COUNT": str(model.get("segment_count", "0")),
                "CONTENT": str(model.get("content", "")),
                "BODY_CLASS": html.escape(str(model.get("body_class", ""))),
                "TEXT_DIRECTION": html.escape(str(model.get("text_direction", "ltr"))),
                "RESEARCH_JSON": html.escape(research_json, quote=False),
            },
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_reading_viewer(self, target: Path) -> None:
        text = target.read_text(encoding="utf-8", errors="replace")
        rel_path = relative_source_path(target)
        title = html.escape(title_from_markdown(target))
        escaped_path = html.escape(rel_path)
        escaped_source_href = html.escape(source_href(target), quote=True)
        content = markdown_to_reading_html(text)
        body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: #d9d9d9;
      color: #000;
      font-family: Verdana, Arial, Helvetica, sans-serif;
      font-size: 10px;
      letter-spacing: 0;
    }}
    a {{ color: #ff0000; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{
      position: relative;
      width: 100%;
      max-width: 1000px;
      min-height: calc(100vh - 48px);
      margin: 24px auto;
      padding: 0;
      overflow: hidden;
      background-image: url("/assets/header-strip.svg?v=nietzsche-portrait");
      background-repeat: repeat-x;
      background-color: #eeeeee;
      border: 1px solid #bdbdbd;
      box-shadow: 0 2px 18px rgba(0, 0, 0, 0.12);
    }}
    .page::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 440px;
      height: 128px;
      pointer-events: none;
      background-image: url("/assets/nietzsche-header-left.png?v=1882");
      background-repeat: no-repeat;
      background-position: left top;
      background-size: 440px 128px;
    }}
    .page > * {{
      position: relative;
      z-index: 1;
    }}
    .spacer {{ height: 160px; }}
    .reader {{
      width: 764px;
      margin: 0 auto 32px;
      padding: 28px 36px 40px;
      background: #ffffff;
      border: 1px solid #d4d4d4;
      min-height: 420px;
    }}
    .reader-header {{
      margin-bottom: 26px;
      padding-bottom: 14px;
      border-bottom: 1px solid #d4d4d4;
    }}
    h1 {{
      margin: 0 0 6px 0;
      font-size: 16px;
      font-family: Verdana, Arial, Helvetica, sans-serif;
      line-height: 1.35;
    }}
    .path {{
      color: #555;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .toolbar {{
      margin-top: 10px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .reading-body {{
      font-family: Georgia, "Times New Roman", serif;
      font-size: 16px;
      line-height: 1.72;
    }}
    .reading-body h1,
    .reading-body h2,
    .reading-body h3,
    .reading-body h4 {{
      position: relative;
      margin: 28px 0 10px;
      font-family: Verdana, Arial, Helvetica, sans-serif;
      line-height: 1.35;
    }}
    .reading-body h1 {{ font-size: 18px; }}
    .reading-body h2 {{ font-size: 16px; }}
    .reading-body h3,
    .reading-body h4 {{ font-size: 13px; }}
    .reading-body p {{
      position: relative;
      margin: 0 0 1em;
    }}
    .segment-anchor {{
      position: absolute;
      margin-left: -22px;
      width: 18px;
      color: #999;
      opacity: 0;
      text-align: right;
    }}
    .reading-body :hover > .segment-anchor,
    .segment-anchor:focus {{
      opacity: 0.7;
    }}
    .reading-body blockquote {{
      margin: 0 0 1em 18px;
      padding-left: 14px;
      border-left: 2px solid #d4d4d4;
      color: #333;
    }}
    .reading-body hr {{
      margin: 28px 0;
      border: 0;
      border-top: 1px solid #d4d4d4;
    }}
    @media (max-width: 860px) {{
      .page {{
        margin: 0 auto;
        border-left: 0;
        border-right: 0;
      }}
      .reader {{
        width: auto;
        margin: 0 10px 24px;
        padding: 22px 18px 30px;
      }}
      .reading-body {{
        font-size: 15px;
      }}
      .segment-anchor {{
        position: static;
        margin-left: 0;
        margin-right: 6px;
        opacity: 0.35;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="spacer"></div>
    <main class="reader">
      <header class="reader-header">
        <h1>{title}</h1>
        <div class="path">{escaped_path}</div>
        <nav class="toolbar" aria-label="Reader navigation">
          <a href="/">Archive index</a>
          <a href="{escaped_source_href}">Source mode</a>
        </nav>
      </header>
      <article class="reading-body">{content}</article>
    </main>
  </div>
</body>
</html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_source_viewer(self, target: Path) -> None:
        text = target.read_text(encoding="utf-8", errors="replace")
        rel_path = relative_source_path(target)
        title = html.escape(target.name)
        escaped_path = html.escape(rel_path)
        escaped_text = html.escape(text)
        mode_links = '<a href="/">Personal Archive of Literature</a>'
        if target.suffix.lower() == ".md":
            escaped_read_href = html.escape(read_href(target), quote=True)
            mode_links += f' / <a href="{escaped_read_href}">Reading mode</a>'
        body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: #d9d9d9;
      color: #000;
      font-family: Verdana, Arial, Helvetica, sans-serif;
      font-size: 10px;
      letter-spacing: 0;
    }}
    a {{ color: #ff0000; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{
      position: relative;
      width: 100%;
      max-width: 1000px;
      min-height: calc(100vh - 48px);
      margin: 24px auto;
      padding: 0;
      overflow: hidden;
      background-image: url("/assets/header-strip.svg?v=nietzsche-portrait");
      background-repeat: repeat-x;
      background-color: #eeeeee;
      border: 1px solid #bdbdbd;
      box-shadow: 0 2px 18px rgba(0, 0, 0, 0.12);
    }}
    .page::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      width: 440px;
      height: 128px;
      pointer-events: none;
      background-image: url("/assets/nietzsche-header-left.png?v=1882");
      background-repeat: no-repeat;
      background-position: left top;
      background-size: 440px 128px;
    }}
    .page > * {{
      position: relative;
      z-index: 1;
    }}
    .spacer {{ height: 160px; }}
    .reader {{
      width: 764px;
      margin: 0 auto 32px;
      padding: 24px 28px 32px;
      background: #ffffff;
      border: 1px solid #d4d4d4;
      min-height: 420px;
    }}
    h1 {{
      margin: 0 0 4px 0;
      font-size: 12px;
      font-family: Verdana, Arial, Helvetica, sans-serif;
      line-height: 1.35;
    }}
    .path {{
      margin-bottom: 24px;
      color: #555;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: "Courier New", Courier, monospace;
      font-size: 13px;
      line-height: 1.65;
    }}
    @media (max-width: 860px) {{
      .page {{
        margin: 0 auto;
        border-left: 0;
        border-right: 0;
      }}
      .reader {{
        width: auto;
        margin: 0 10px 24px;
        padding: 18px 16px 24px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="spacer"></div>
    <main class="reader">
      <h1>{title}</h1>
      <div class="path">{mode_links}<br>{escaped_path}</div>
      <pre>{escaped_text}</pre>
    </main>
  </div>
</body>
</html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Personal Archive of Literature reader running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
