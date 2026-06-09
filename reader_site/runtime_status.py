from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from path_config import (
    BIBLE_OUTPUT,
    BIBLE_SOURCE_ROOT,
    CORPUS_ROOT_ENV,
    KIERKEGAARD_SOURCE_ROOT,
    KIERKEGAARD_TEXTS,
    NIETZSCHE_OUTPUT,
    NIETZSCHE_SOURCE_ROOT,
    ROOT,
    SITE,
    WITTGENSTEIN_OUTPUT,
    WITTGENSTEIN_SOURCE_ROOT,
)

DATA = SITE / "data"

SEARCH_INDEX = DATA / "search_index.jsonl"
SEARCH_DB = DATA / "search_index.sqlite"

CORPORA = [
    {
        "corpus_id": "nietzsche",
        "title": "Nietzsche",
        "source_root": NIETZSCHE_SOURCE_ROOT,
        "primary_output": NIETZSCHE_OUTPUT,
        "metadata": DATA / "nietzsche_metadata.json",
        "segments": DATA / "nietzsche_segments.jsonl",
        "notes": DATA / "notes" / "nietzsche_notes.jsonl",
    },
    {
        "corpus_id": "bible",
        "title": "Bible",
        "source_root": BIBLE_SOURCE_ROOT,
        "primary_output": BIBLE_OUTPUT,
        "metadata": DATA / "bible_metadata.json",
        "segments": DATA / "bible_segments.jsonl",
        "notes": DATA / "notes" / "bible_notes.jsonl",
    },
    {
        "corpus_id": "kierkegaard",
        "title": "Kierkegaard",
        "source_root": KIERKEGAARD_SOURCE_ROOT,
        "primary_output": KIERKEGAARD_TEXTS,
        "metadata": DATA / "kierkegaard_metadata.json",
        "segments": DATA / "kierkegaard_segments.jsonl",
        "notes": DATA / "notes" / "kierkegaard_notes.jsonl",
    },
    {
        "corpus_id": "wittgenstein",
        "title": "Wittgenstein",
        "source_root": WITTGENSTEIN_SOURCE_ROOT,
        "primary_output": WITTGENSTEIN_OUTPUT,
        "metadata": DATA / "wittgenstein_metadata.json",
        "segments": DATA / "wittgenstein_segments.jsonl",
        "notes": DATA / "notes" / "wittgenstein_notes.jsonl",
    },
]

SMALL_METADATA = [
    ("nietzsche_catalog", DATA / "nietzsche_catalog.json"),
    ("nietzsche_concepts", DATA / "nietzsche_concepts.json"),
    ("nietzsche_encoding_report", DATA / "nietzsche_encoding_report.json"),
    ("nietzsche_notes_schema", DATA / "nietzsche_notes_schema.json"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_path(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(SITE).as_posix()
    except ValueError:
        pass
    try:
        return "../" + path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def file_record(name: str, path: Path, kind: str, role: str, include_checksum: bool = False) -> dict[str, Any]:
    exists = path.exists()
    record: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "role": role,
        "path": display_path(path),
        "exists": exists,
    }
    if exists:
        stat = path.stat()
        record["bytes"] = stat.st_size
        record["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
        if include_checksum and path.is_file():
            record["sha256"] = sha256_file(path)
    return record


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_metadata_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "works": 0, "variants": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"exists": True, "error": str(exc), "works": 0, "variants": 0}

    works = data.get("works") or []
    work_items = list(works.values()) if isinstance(works, dict) else list(works)
    variants = 0
    for work in work_items:
        if not isinstance(work, dict):
            continue
        work_variants = work.get("variants") or []
        variants += len(work_variants) if isinstance(work_variants, (list, dict)) else 0
    return {"exists": True, "works": len(work_items), "variants": variants}


def search_database_summary() -> dict[str, Any]:
    summary: dict[str, Any] = file_record("search_index.sqlite", SEARCH_DB, "search", "query database")
    if not SEARCH_DB.exists():
        summary["records"] = 0
        summary["fts5"] = False
        return summary

    connection = sqlite3.connect(SEARCH_DB)
    try:
        summary["records"] = connection.execute("SELECT COUNT(*) FROM search_segments").fetchone()[0]
        summary["by_corpus"] = {
            corpus_id: count
            for corpus_id, count in connection.execute(
                "SELECT corpus_id, COUNT(*) FROM search_segments GROUP BY corpus_id ORDER BY corpus_id"
            )
        }
        summary["fts5"] = bool(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND sql LIKE '%VIRTUAL TABLE%' AND sql LIKE '%fts5%'"
            ).fetchone()
        )
    except sqlite3.Error as exc:
        summary["error"] = str(exc)
        summary["records"] = 0
        summary["fts5"] = False
    finally:
        connection.close()
    return summary


def corpus_status(config: dict[str, Any]) -> dict[str, Any]:
    metadata = read_metadata_summary(config["metadata"])
    return {
        "corpus_id": config["corpus_id"],
        "title": config["title"],
        "source_root": display_path(config["source_root"]),
        "source_root_exists": config["source_root"].exists(),
        "primary_output": display_path(config["primary_output"]),
        "primary_output_exists": config["primary_output"].exists(),
        "metadata": file_record(f"{config['corpus_id']}_metadata", config["metadata"], "metadata", "work catalog"),
        "segments": file_record(f"{config['corpus_id']}_segments", config["segments"], "segments", "research index"),
        "notes": file_record(f"{config['corpus_id']}_notes", config["notes"], "notes", "personal notes"),
        "work_count": metadata.get("works", 0),
        "variant_count": metadata.get("variants", 0),
        "metadata_error": metadata.get("error", ""),
    }


def build_artifact_manifest(include_checksums: bool = False) -> dict[str, Any]:
    artifacts = []
    for config in CORPORA:
        corpus_id = config["corpus_id"]
        artifacts.append(file_record(f"{corpus_id}_metadata", config["metadata"], "metadata", "work catalog", include_checksums))
        artifacts.append(file_record(f"{corpus_id}_segments", config["segments"], "segments", "research index", include_checksums))
    for name, path in SMALL_METADATA:
        artifacts.append(file_record(name, path, "metadata", "supporting data", include_checksums))
    artifacts.append(file_record("search_index.jsonl", SEARCH_INDEX, "search", "portable search records", include_checksums))
    artifacts.append(file_record("search_index.sqlite", SEARCH_DB, "search", "query database", include_checksums))

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "site_root": str(SITE),
        "corpus_root": str(ROOT),
        "uses_env_corpus_root": CORPUS_ROOT_ENV in os.environ,
        "corpora": [corpus_status(config) for config in CORPORA],
        "artifacts": artifacts,
        "search": search_database_summary(),
        "regeneration_commands": [
            "python .\\scripts\\rebuild_all.py",
            "python .\\scripts\\build_nietzsche_metadata.py",
            "python .\\scripts\\build_bible_metadata.py",
            "python .\\scripts\\build_bible_segments.py",
            "python .\\scripts\\build_kierkegaard_metadata.py",
            "python .\\scripts\\build_kierkegaard_segments.py",
            "python .\\scripts\\build_wittgenstein_metadata.py",
            "python .\\scripts\\build_wittgenstein_segments.py",
            "python .\\scripts\\build_search_index.py",
            "python .\\scripts\\build_search_db.py",
            "python .\\scripts\\build_artifact_manifest.py",
        ],
    }


def build_runtime_health() -> dict[str, Any]:
    corpora = [corpus_status(config) for config in CORPORA]
    search = search_database_summary()
    issues = []
    for corpus in corpora:
        if not corpus["source_root_exists"]:
            issues.append(f"missing source root: {corpus['corpus_id']}")
        if not corpus["metadata"]["exists"]:
            issues.append(f"missing metadata: {corpus['corpus_id']}")
        if not corpus["segments"]["exists"]:
            issues.append(f"missing segment artifact: {corpus['corpus_id']}")
        if corpus.get("metadata_error"):
            issues.append(f"metadata parse error: {corpus['corpus_id']}")
    if not search["exists"]:
        issues.append("missing search sqlite database")
    elif not search.get("fts5"):
        issues.append("search database is LIKE-based; FTS5 upgrade is still pending")

    next_upgrades = [
        "Use the automated visual smoke script plus targeted browser review for future layout changes.",
        "Prototype AI/Gemma interpretation only after implementing the documented provenance gates.",
        "Split route dispatch into a dedicated route module only if the HTTP handler grows again.",
    ]
    if search.get("fts5"):
        next_upgrades.insert(1, "Collect real study queries for further search relevance calibration.")
    else:
        next_upgrades.insert(1, "Replace LIKE-based search with SQLite FTS5.")

    return {
        "status": "ok" if not issues else "warning",
        "generated_at": utc_now(),
        "site_root": str(SITE),
        "corpus_root": str(ROOT),
        "corpora": corpora,
        "search": search,
        "issues": issues,
        "next_recommended_upgrades": next_upgrades,
    }
