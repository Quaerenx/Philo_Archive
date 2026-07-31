from __future__ import annotations

import csv
import fnmatch
import json
import os
import stat as stat_module
import threading
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from types import MappingProxyType
from typing import Mapping
from urllib.parse import quote

from corpora.catalogs import load_bible_metadata, load_kierkegaard_metadata, load_nietzsche_catalog, load_wittgenstein_metadata
from path_config import (
    BIBLE_OUTPUT,
    KIERKEGAARD_TEXTS,
    NIETZSCHE_OUTPUT,
    ROOT,
    SITE,
    WITTGENSTEIN_OUTPUT,
)
from rendering.documents import title_from_markdown


ARCHIVE_SCHEMA_VERSION = 1
ARCHIVE_CATALOG = SITE / "data" / "archive_catalog.local.json"
ARCHIVE_CACHE_CHECK_TTL_SECONDS = 5.0
ROOT_RESOLVED = ROOT
WITTGENSTEIN_METADATA_PATH = SITE / "data" / "wittgenstein_metadata.json"
ARCHIVE_METADATA_FILES = (
    SITE / "data" / "nietzsche_catalog.json",
    SITE / "data" / "nietzsche_metadata.json",
    SITE / "data" / "bible_metadata.json",
    SITE / "data" / "kierkegaard_metadata.json",
    WITTGENSTEIN_METADATA_PATH,
    BIBLE_OUTPUT / "mapping" / "source_inventory.csv",
    WITTGENSTEIN_OUTPUT / "_manifest.json",
)
ARCHIVE_INPUT_TREES = (
    (NIETZSCHE_OUTPUT / "works", "*.md"),
    (NIETZSCHE_OUTPUT / "nachlass", "*.md"),
    (NIETZSCHE_OUTPUT / "briefe", "*.md"),
    (BIBLE_OUTPUT / "markdown", "*.md"),
    (KIERKEGAARD_TEXTS, "*.json"),
    (WITTGENSTEIN_OUTPUT, "*.md"),
)
ROOT_PATH_VALUE = os.fspath(ROOT_RESOLVED)
ROOT_PATH_PREFIX = ROOT_PATH_VALUE.rstrip("\\/") + os.sep
ROOT_PATH_PREFIX_CASEFOLD = ROOT_PATH_PREFIX.casefold()
ArchiveInputSignature = tuple[tuple[str, str, int, int, int, int], ...]


@dataclass(frozen=True)
class ArchiveInputSnapshot:
    signature: ArchiveInputSignature
    file_sizes: Mapping[str, int]


@dataclass(frozen=True)
class ArchiveCacheState:
    payload: dict
    signature: ArchiveInputSignature
    validate_after: float


ARCHIVE_CACHE: dict | None = None
_ARCHIVE_CACHE_STATE: ArchiveCacheState | None = None
_ARCHIVE_CACHE_LOCK = threading.Lock()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def relative_source_path(path: Path) -> str:
    source_path = path if path.is_absolute() else ROOT_RESOLVED / path
    return source_path.relative_to(ROOT_RESOLVED).as_posix()


def source_href(path: Path) -> str:
    return "/source?path=" + quote(relative_source_path(path), safe="")


def read_href(path: Path) -> str:
    return "/read?path=" + quote(relative_source_path(path), safe="")


def work_href(corpus_id: str, work_id: str) -> str:
    return f"/work/{quote(corpus_id, safe='')}/{quote(work_id, safe='')}"


def viewer_href(path: Path) -> str:
    if path.suffix.lower() == ".md":
        return read_href(path)
    return source_href(path)


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


def work_link(path: Path, corpus_id: str, work_id: str, label: str | None = None, meta: str | None = None) -> dict:
    link = file_link(path, label, meta)
    link["href"] = work_href(corpus_id, work_id)
    link["work_id"] = work_id
    return link


def archive_input_key(path: Path) -> str:
    path_value = os.fspath(path)
    if not os.path.isabs(path_value):
        path_value = os.path.join(ROOT_PATH_VALUE, path_value)
    if path_value.casefold().startswith(ROOT_PATH_PREFIX_CASEFOLD):
        return path_value[len(ROOT_PATH_PREFIX) :].replace(os.sep, "/")
    relative = os.path.relpath(path_value, ROOT_PATH_VALUE)
    if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
        return relative.replace(os.sep, "/")
    return path_value.replace(os.sep, "/")


def archive_tree_records(root: Path, pattern: str) -> list[tuple[str, Path, os.stat_result | None]]:
    records: list[tuple[str, Path, os.stat_result | None]] = []
    try:
        root_info = root.stat()
    except OSError:
        return [(archive_input_key(root), root, None)]
    records.append((archive_input_key(root), root, root_info))
    if not stat_module.S_ISDIR(root_info.st_mode):
        return records

    pending = [root]
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                            continue
                        if not fnmatch.fnmatch(entry.name, pattern):
                            continue
                        path = Path(entry.path)
                        records.append((archive_input_key(path), path, entry.stat()))
                    except OSError:
                        path = Path(entry.path)
                        records.append((archive_input_key(path), path, None))
        except OSError:
            records.append((archive_input_key(folder), folder, None))
    return records


def archive_input_records() -> list[tuple[str, Path, os.stat_result | None]]:
    records: dict[str, tuple[Path, os.stat_result | None]] = {}
    for path in ARCHIVE_METADATA_FILES:
        try:
            info = path.stat()
        except OSError:
            info = None
        records[archive_input_key(path)] = (path, info)
    for root, pattern in ARCHIVE_INPUT_TREES:
        for key, path, info in archive_tree_records(root, pattern):
            records.setdefault(key, (path, info))
    if not WITTGENSTEIN_METADATA_PATH.is_file():
        for key, path, info in archive_tree_records(WITTGENSTEIN_OUTPUT, "*.html"):
            records.setdefault(key, (path, info))
    return [(key, *records[key]) for key in sorted(records)]


def archive_input_paths() -> list[tuple[str, Path]]:
    return [(key, path) for key, path, _info in archive_input_records()]


def archive_input_snapshot() -> ArchiveInputSnapshot:
    signature = []
    file_sizes: dict[str, int] = {}
    for key, _path, info in archive_input_records():
        if info is None:
            signature.append((key, "missing", -1, -1, -1, -1))
            continue
        kind = "file" if stat_module.S_ISREG(info.st_mode) else "directory"
        signature.append((key, kind, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino))
        if kind == "file":
            file_sizes[key] = info.st_size
    return ArchiveInputSnapshot(tuple(signature), MappingProxyType(file_sizes))


def count_bytes(paths: list[Path], file_sizes: Mapping[str, int] | None = None) -> int:
    total = 0
    for path in paths:
        if file_sizes is not None:
            size = file_sizes.get(archive_input_key(path))
            if size is not None:
                total += size
                continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def corpus_counts(
    sections: list[dict],
    files: list[Path],
    file_sizes: Mapping[str, int] | None = None,
) -> dict:
    return {
        "files": len(files),
        "links": sum(len(section["links"]) for section in sections),
        "bytes": count_bytes(files, file_sizes),
    }


def build_nietzsche_archive(file_sizes: Mapping[str, int] | None = None) -> dict:
    sections = []
    all_files: list[Path] = []
    work_files = sorted((NIETZSCHE_OUTPUT / "works").glob("*.md"), key=lambda item: item.name.lower())
    all_files.extend(work_files)
    work_by_name = {path.name: path for path in work_files}
    catalogued: set[str] = set()

    catalog = load_nietzsche_catalog()
    for section in catalog.get("sections", []):
        links = []
        for work in section.get("works", []):
            path = work_by_name.get(work.get("file", ""))
            if not path:
                continue
            catalogued.add(path.name)
            work_id = path.stem
            links.append(work_link(path, "nietzsche", work_id, work.get("label") or title_from_markdown(path), work.get("meta") or path.stem))
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
        links = [work_link(path, "nietzsche", path.stem, title_from_markdown(path), path.name) for path in uncatalogued]
        sections.append({"title": "기타 works", "count": len(links), "links": links})

    for folder, title, meta in [
        ("nachlass", "유고 단상", "Nachlass 파일은 연도별로 정리된 영역입니다."),
        ("briefe", "편지", "Briefe 파일은 연도별로 정리된 영역입니다."),
    ]:
        files = sorted((NIETZSCHE_OUTPUT / folder).glob("*.md"), key=lambda item: item.name.lower())
        all_files.extend(files)
        links = [file_link(path, title_from_markdown(path), path.name) for path in files]
        sections.append({"title": title, "meta": meta, "count": len(files), "links": links})
    return {
        "id": "nietzsche",
        "title": "니체",
        "subtitle": "eKGWB markdown exports, grouped for reading",
        "counts": corpus_counts(sections, all_files, file_sizes),
        "links": [link for section in sections for link in section["links"][:4]],
        "sections": sections,
    }


def build_wittgenstein_archive(file_sizes: Mapping[str, int] | None = None) -> dict:
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
                files.extend(ROOT_RESOLVED / variant["source_path"] for variant in variants if variant.get("source_path"))
            meta = " / ".join(variant.get("label", "") for variant in variants[:4] if variant.get("label"))
            link = {
                "label": work.get("display_title") or work.get("title") or work.get("work_id"),
                "href": work.get("work_url") or work_href("wittgenstein", work.get("work_id", "")),
                "source_href": variants[0].get("source_url", "") if variants else "",
                "path": variants[0].get("source_path", "") if variants else "",
                "meta": meta,
                "work_id": work.get("work_id", ""),
            }
            group_id = work.get("category_id", "source_items")
            grouped.setdefault(group_id, {"title": work.get("category_title", "Works"), "links": []})
            grouped[group_id]["links"].append(link)
        sections = []
        for key in ("idp_groups", "source_items"):
            links = sorted(grouped.get(key, {}).get("links", []), key=lambda item: item["label"].lower())
            sections.append({"title": grouped.get(key, {}).get("title", key), "count": len(links), "links": links})
        manifest = WITTGENSTEIN_OUTPUT / "_manifest.json"
        return {
            "id": "wittgenstein",
            "title": "비트겐슈타인",
            "subtitle": "Wittgenstein Archive exports grouped by siglum",
            "counts": corpus_counts(sections, files + ([manifest] if manifest.exists() else []), file_sizes),
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
        "counts": corpus_counts(sections, files + ([manifest_path] if manifest_path.exists() else []), file_sizes),
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


def build_bible_archive(file_sizes: Mapping[str, int] | None = None) -> dict:
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
        "counts": corpus_counts(sections, all_files, file_sizes),
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


def build_kierkegaard_archive(file_sizes: Mapping[str, int] | None = None) -> dict:
    metadata = load_kierkegaard_metadata()
    works = metadata.get("works", {})
    if works:
        links = []
        files = []
        for work in works.values():
            variants = work.get("variants", [])
            if variants:
                files.extend(ROOT_RESOLVED / variant["source_path"] for variant in variants if variant.get("source_path"))
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
            "counts": corpus_counts(sections, files, file_sizes),
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
        "counts": corpus_counts(sections, files, file_sizes),
        "links": [link for section in sections for link in section["links"][:3]],
        "sections": sections,
    }


def build_archive_payload(file_sizes: Mapping[str, int] | None = None) -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpora": [
            build_nietzsche_archive(file_sizes),
            build_bible_archive(file_sizes),
            build_kierkegaard_archive(file_sizes),
            build_wittgenstein_archive(file_sizes),
        ],
    }


def build_archive_catalog(initial_snapshot: ArchiveInputSnapshot | None = None) -> dict:
    snapshot = initial_snapshot
    for _attempt in range(3):
        before = snapshot or archive_input_snapshot()
        archive = build_archive_payload(before.file_sizes)
        after = archive_input_snapshot()
        if before.signature == after.signature:
            return {
                "schema_version": ARCHIVE_SCHEMA_VERSION,
                "input_signature": after.signature,
                "archive": archive,
            }
        snapshot = after
    raise RuntimeError("archive inputs changed repeatedly while building the catalog")


def load_archive_catalog(snapshot: ArchiveInputSnapshot) -> dict | None:
    if not ARCHIVE_CATALOG.is_file():
        return None
    try:
        catalog = read_json(ARCHIVE_CATALOG)
        stored_signature = tuple(tuple(item) for item in catalog.get("input_signature", []))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    archive = catalog.get("archive")
    if (
        catalog.get("schema_version") != ARCHIVE_SCHEMA_VERSION
        or stored_signature != snapshot.signature
        or not isinstance(archive, dict)
        or not isinstance(archive.get("corpora"), list)
    ):
        return None
    return archive


def build_archive_summary() -> dict:
    return {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpora": [
            {"id": "nietzsche", "title": "니체", "subtitle": "eKGWB markdown exports, grouped for reading"},
            {"id": "bible", "title": "성경", "subtitle": "Hebrew, Greek, and LXX markdown exports"},
            {"id": "kierkegaard", "title": "키르케고르", "subtitle": "Soren Kierkegaards Skrifter grouped by work"},
            {"id": "wittgenstein", "title": "비트겐슈타인", "subtitle": "Wittgenstein Archive exports grouped by siglum"},
        ],
    }


def build_archive() -> dict:
    global ARCHIVE_CACHE, _ARCHIVE_CACHE_STATE
    now = monotonic()
    state = _ARCHIVE_CACHE_STATE if ARCHIVE_CACHE is not None else None
    if state is not None and now < state.validate_after:
        return state.payload

    with _ARCHIVE_CACHE_LOCK:
        now = monotonic()
        state = _ARCHIVE_CACHE_STATE if ARCHIVE_CACHE is not None else None
        if state is not None and now < state.validate_after:
            return state.payload

        snapshot = archive_input_snapshot()
        active_signature = snapshot.signature
        if state is not None and state.signature == snapshot.signature:
            payload = state.payload
        else:
            payload = load_archive_catalog(snapshot)
            if payload is None:
                catalog = build_archive_catalog(snapshot)
                payload = catalog["archive"]
                active_signature = tuple(tuple(item) for item in catalog["input_signature"])
        state = ArchiveCacheState(
            payload=payload,
            signature=active_signature,
            validate_after=monotonic() + ARCHIVE_CACHE_CHECK_TTL_SECONDS,
        )
        ARCHIVE_CACHE = payload
        _ARCHIVE_CACHE_STATE = state
        return payload
