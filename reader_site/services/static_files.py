from __future__ import annotations

import gzip
import mimetypes
from dataclasses import dataclass
from email.utils import formatdate, parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from services.sources import is_inside


SITE = Path(__file__).resolve().parents[1]
ASSETS = SITE / "assets"
SITE_RESOLVED = SITE.resolve()
ASSETS_RESOLVED = ASSETS.resolve()
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".md", ".txt", ".csv"}
COMPRESSIBLE_SUFFIXES = frozenset({".html", ".css", ".js", ".svg", ".md", ".txt", ".csv"})
LONG_CACHE_SUFFIXES = frozenset({".css", ".js"})
MIN_GZIP_BYTES = 512
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
    content_length: int | None
    status: int = 200
    content_disposition: str = ""
    cache_control: str = "no-cache"
    etag: str = ""
    last_modified: str = ""
    content_encoding: str = ""
    vary_accept_encoding: bool = False


def resolve_static_file(request_path: str) -> Path:
    if request_path in {"", "/"} or request_path.startswith("/category/"):
        target = SITE / "index.html"
    elif request_path in STATIC_ENTRYPOINTS:
        target = SITE / STATIC_ENTRYPOINTS[request_path]
    else:
        clean = unquote(request_path).lstrip("/")
        target = (SITE / clean).resolve()
        if not is_inside(target, SITE_RESOLVED):
            raise PermissionError("static path is outside site root")
        relative = target.relative_to(SITE_RESOLVED)
        is_public_root_file = len(relative.parts) == 1 and relative.name in PUBLIC_ROOT_FILES
        is_public_asset = (
            len(relative.parts) > 1
            and relative.parts[0] == ASSETS.name
            and is_inside(target, ASSETS_RESOLVED)
            and target.suffix.lower() in PUBLIC_ASSET_SUFFIXES
        )
        if not is_public_root_file and not is_public_asset:
            raise PermissionError("static path is not public")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("static file not found")
    return target


def static_cache_control(target: Path, versioned: bool) -> str:
    if versioned and target.suffix.lower() in LONG_CACHE_SUFFIXES:
        return "public, max-age=31536000, immutable"
    return "no-cache"


def accepts_gzip(value: str) -> bool:
    wildcard_quality: float | None = None
    for raw_item in str(value or "").split(","):
        parts = [part.strip() for part in raw_item.split(";")]
        encoding = parts[0].lower()
        if not encoding:
            continue
        quality = 1.0
        for parameter in parts[1:]:
            if not parameter.lower().startswith("q="):
                continue
            try:
                quality = float(parameter.split("=", 1)[1])
            except ValueError:
                quality = 0.0
        if encoding == "gzip":
            return quality > 0
        if encoding == "*":
            wildcard_quality = quality
    return bool(wildcard_quality and wildcard_quality > 0)


def etag_matches(header_value: str, etag: str) -> bool:
    def opaque(value: str) -> str:
        value = value.strip()
        return value[2:].strip() if value.startswith("W/") else value

    for candidate in str(header_value or "").split(","):
        if candidate.strip() == "*" or opaque(candidate) == opaque(etag):
            return True
    return False


def modified_since_matches(header_value: str, modified_timestamp: float) -> bool:
    if not header_value:
        return False
    try:
        timestamp = parsedate_to_datetime(header_value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return False
    return int(modified_timestamp) <= int(timestamp)


@lru_cache(maxsize=64)
def gzip_file(path_value: str, _size: int, _modified_ns: int) -> bytes:
    return gzip.compress(Path(path_value).read_bytes(), compresslevel=6, mtime=0)


def build_file_payload(
    target: Path,
    inline: bool = False,
    *,
    accept_encoding: str = "",
    if_none_match: str = "",
    if_modified_since: str = "",
    cache_control: str = "no-cache",
    allow_compression: bool = False,
    head_only: bool = False,
) -> FilePayload:
    info = target.stat()
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix == ".md":
        content_type = "text/plain"
    if target.suffix in TEXT_SUFFIXES:
        content_type += "; charset=utf-8"
    disposition = f'inline; filename="{target.name}"' if inline else ""
    gzip_eligible = (
        allow_compression
        and target.suffix.lower() in COMPRESSIBLE_SUFFIXES
        and info.st_size >= MIN_GZIP_BYTES
    )
    use_gzip = gzip_eligible and accepts_gzip(accept_encoding)
    representation = "gzip" if use_gzip else "identity"
    etag = f'W/"{info.st_mtime_ns:x}-{info.st_size:x}-{representation}"'
    last_modified = formatdate(info.st_mtime, usegmt=True)
    not_modified = (
        etag_matches(if_none_match, etag)
        if if_none_match
        else modified_since_matches(if_modified_since, info.st_mtime)
    )
    if not_modified:
        return FilePayload(
            body=b"",
            content_type=content_type,
            content_length=None,
            status=304,
            content_disposition=disposition,
            cache_control=cache_control,
            etag=etag,
            last_modified=last_modified,
            content_encoding="gzip" if use_gzip else "",
            vary_accept_encoding=gzip_eligible,
        )

    if use_gzip:
        representation_body = gzip_file(str(target), info.st_size, info.st_mtime_ns)
        content_length = len(representation_body)
    else:
        representation_body = b"" if head_only else target.read_bytes()
        content_length = info.st_size
    return FilePayload(
        body=b"" if head_only else representation_body,
        content_type=content_type,
        content_length=content_length,
        content_disposition=disposition,
        cache_control=cache_control,
        etag=etag,
        last_modified=last_modified,
        content_encoding="gzip" if use_gzip else "",
        vary_accept_encoding=gzip_eligible,
    )
