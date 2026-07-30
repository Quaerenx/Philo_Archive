from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from services.sources import is_inside


SITE = Path(__file__).resolve().parents[1]
ASSETS = SITE / "assets"
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".md", ".txt", ".csv"}
PUBLIC_ROOT_FILES = {"app.js", "styles.css"}
PUBLIC_ASSET_SUFFIXES = {
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
}
STATIC_ENTRYPOINTS = {
    "/search": "search.html",
    "/notes": "notes.html",
    "/study": "study.html",
    "/translations": "translations.html",
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
        relative = target.relative_to(SITE.resolve())
        is_public_root_file = len(relative.parts) == 1 and relative.name in PUBLIC_ROOT_FILES
        is_public_asset = (
            len(relative.parts) > 1
            and relative.parts[0] == ASSETS.name
            and is_inside(target, ASSETS.resolve())
            and target.suffix.lower() in PUBLIC_ASSET_SUFFIXES
        )
        if not is_public_root_file and not is_public_asset:
            raise PermissionError("static path is not public")
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
