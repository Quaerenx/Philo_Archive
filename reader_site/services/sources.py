from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, unquote

from rendering.documents import markdown_to_reading_html, title_from_markdown
from rendering.static_pages import render_reading_page_html, render_source_page_html


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", SITE.parents[0])).resolve()
TEMPLATES = SITE / "templates"

CORPUS_ROOTS = [
    ROOT / "니체_원서수집",
    ROOT / "비트겐슈타인_원서수집",
    ROOT / "성경_원서수집",
    ROOT / "키르케고르_원서수집",
]

SOURCE_SUFFIXES = {".md", ".html", ".json", ".pdf", ".txt", ".csv"}


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


def work_href(corpus_id: str, work_id: str) -> str:
    return f"/work/{quote(corpus_id, safe='')}/{quote(work_id, safe='')}"


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


def render_reading_viewer_html(target: Path) -> str:
    text = target.read_text(encoding="utf-8", errors="replace")
    rel_path = relative_source_path(target)
    content = markdown_to_reading_html(text)
    template = (TEMPLATES / "reading.html").read_text(encoding="utf-8")
    return render_reading_page_html(template, title_from_markdown(target), rel_path, source_href(target), content)


def render_source_viewer_html(target: Path) -> str:
    text = target.read_text(encoding="utf-8", errors="replace")
    rel_path = relative_source_path(target)
    reading_href = read_href(target) if target.suffix.lower() == ".md" else ""
    template = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    return render_source_page_html(template, target.name, rel_path, text, reading_href)


def build_read_response(path_value: str) -> dict:
    target = resolve_source_path(path_value)
    if target.suffix.lower() != ".md":
        return {"kind": "html", "body": render_source_viewer_html(target)}
    return {"kind": "html", "body": render_reading_viewer_html(target)}


def build_source_response(path_value: str) -> dict:
    target = resolve_source_path(path_value)
    if target.suffix.lower() == ".pdf":
        return {"kind": "file", "target": target, "inline": True}
    return {"kind": "html", "body": render_source_viewer_html(target)}
