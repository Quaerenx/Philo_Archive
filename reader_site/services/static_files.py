from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from services.sources import is_inside


SITE = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".md", ".txt", ".csv"}
STATIC_ENTRYPOINTS = {
    "/search": "search.html",
    "/notes": "notes.html",
    "/study": "study.html",
}


@dataclass(frozen=True)
class FilePayload:
    body: bytes
    content_type: str
    content_disposition: str = ""


def resolve_static_file(request_path: str) -> Path:
    if request_path in {"", "/"} or request_path.startswith("/category/"):
        target = SITE / "index.html"
    elif request_path in STATIC_ENTRYPOINTS:
        target = SITE / STATIC_ENTRYPOINTS[request_path]
    else:
        clean = unquote(request_path).lstrip("/")
        target = (SITE / clean).resolve()
        if not is_inside(target, SITE.resolve()):
            raise PermissionError("static path is outside site root")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("static file not found")
    return target


def build_file_payload(target: Path, inline: bool = False) -> FilePayload:
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix == ".md":
        content_type = "text/plain"
    if target.suffix in TEXT_SUFFIXES:
        content_type += "; charset=utf-8"
    disposition = f'inline; filename="{target.name}"' if inline else ""
    return FilePayload(target.read_bytes(), content_type, disposition)
