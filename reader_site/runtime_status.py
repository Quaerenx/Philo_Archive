from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

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
from services.segment_offsets import SEGMENT_OFFSET_INDEX

DATA = SITE / "data"

SEARCH_INDEX = DATA / "search_index.jsonl"
SEARCH_DB = DATA / "search_index.sqlite"
ARCHIVE_CATALOG = DATA / "archive_catalog.local.json"
GEMMA_BASE_URL = os.environ.get("PHILO_GEMMA_BASE_URL", "http://127.0.0.1:9999")
GEMMA_STATE_PATH = Path(
    os.environ.get("PHILO_GEMMA_STATE_PATH", str(DATA / "runtime.local" / "gemma-state.json"))
)
GEMMA_STARTING_TTL_SECONDS = 180
GEMMA_PUBLIC_STATES = {"starting", "ready", "failed", "unavailable"}
STATIC_HEALTH_TTL_SECONDS = 3.0
STATIC_HEALTH_FAILURE_TTL_SECONDS = 1.0
GEMMA_HEALTH_TTL_SECONDS = 1.0
GEMMA_HEALTH_FAILURE_TTL_SECONDS = 0.5

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
]


@dataclass(frozen=True)
class TimedSnapshot:
    value: Any
    expires_at: float
    builder_token: int


class TTLCache:
    def __init__(self) -> None:
        self._snapshot: TimedSnapshot | None = None
        self._lock = threading.Lock()

    def get(self, builder: Callable[[], Any], ttl_for_value: Callable[[Any], float]) -> Any:
        now = monotonic()
        snapshot = self._snapshot
        builder_token = id(builder)
        if snapshot is not None and snapshot.builder_token == builder_token and now < snapshot.expires_at:
            return deepcopy(snapshot.value)
        with self._lock:
            now = monotonic()
            snapshot = self._snapshot
            if snapshot is not None and snapshot.builder_token == builder_token and now < snapshot.expires_at:
                return deepcopy(snapshot.value)
            value = builder()
            ttl_seconds = max(0.0, float(ttl_for_value(value)))
            self._snapshot = TimedSnapshot(deepcopy(value), now + ttl_seconds, builder_token)
            return deepcopy(value)

    def clear(self) -> None:
        with self._lock:
            self._snapshot = None


_CORPUS_HEALTH_CACHE = TTLCache()
_SEARCH_HEALTH_CACHE = TTLCache()
_GEMMA_HEALTH_CACHE = TTLCache()


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


def read_gemma_launcher_state(
    path: Path = GEMMA_STATE_PATH,
    base_url: str = GEMMA_BASE_URL,
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size > 16 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if str(payload.get("base_url") or "").rstrip("/") != base_url.rstrip("/"):
        return {}
    state = str(payload.get("state") or "")
    if state not in {"starting", "ready", "failed", "stopped"}:
        return {}
    if state == "starting":
        try:
            updated_at = datetime.fromisoformat(str(payload.get("updated_at") or "").replace("Z", "+00:00"))
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return {}
        current = now or datetime.now(timezone.utc)
        if (current - updated_at.astimezone(timezone.utc)).total_seconds() > GEMMA_STARTING_TTL_SECONDS:
            return {"state": "unavailable"}
    return {"state": "unavailable" if state == "stopped" else state}


def gemma_runtime_summary() -> dict[str, Any]:
    launcher_state = read_gemma_launcher_state()
    state = str(launcher_state.get("state") or "unavailable")
    if state == "ready":
        state = "unavailable"
    summary: dict[str, Any] = {
        "base_url": GEMMA_BASE_URL,
        "reachable": False,
        "model_count": 0,
        "models": [],
        "state": state,
    }
    try:
        with urlopen(f"{GEMMA_BASE_URL.rstrip('/')}/v1/models", timeout=0.8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        summary["error"] = str(exc)
        return summary
    models = payload.get("data") or payload.get("models") or []
    if not isinstance(models, list):
        models = []
    summary["state"] = "ready"
    summary["reachable"] = True
    summary["model_count"] = len(models)
    summary["models"] = [
        str(model.get("id") or model.get("name") or model.get("model") or "")
        for model in models
        if isinstance(model, dict)
    ][:5]
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


def public_corpus_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "corpus_id": status["corpus_id"],
        "title": status["title"],
        "source_ready": bool(status["source_root_exists"] and status["primary_output_exists"]),
        "metadata_ready": bool(status["metadata"]["exists"] and not status.get("metadata_error")),
        "segments_ready": bool(status["segments"]["exists"]),
    }


def public_search_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "ready": bool(summary.get("exists")),
        "fts5": bool(summary.get("fts5")),
    }


def build_corpus_statuses() -> list[dict[str, Any]]:
    return [corpus_status(config) for config in CORPORA]


def corpus_statuses_ttl(statuses: list[dict[str, Any]]) -> float:
    ready = all(
        status.get("source_root_exists")
        and status.get("primary_output_exists")
        and status.get("metadata", {}).get("exists")
        and status.get("segments", {}).get("exists")
        and not status.get("metadata_error")
        for status in statuses
    )
    return STATIC_HEALTH_TTL_SECONDS if ready else STATIC_HEALTH_FAILURE_TTL_SECONDS


def search_status_ttl(summary: dict[str, Any]) -> float:
    ready = bool(summary.get("exists") and not summary.get("error"))
    return STATIC_HEALTH_TTL_SECONDS if ready else STATIC_HEALTH_FAILURE_TTL_SECONDS


def gemma_status_ttl(summary: dict[str, Any]) -> float:
    return GEMMA_HEALTH_TTL_SECONDS if summary.get("reachable") else GEMMA_HEALTH_FAILURE_TTL_SECONDS


def cached_corpus_statuses() -> list[dict[str, Any]]:
    return _CORPUS_HEALTH_CACHE.get(build_corpus_statuses, corpus_statuses_ttl)


def cached_search_database_summary() -> dict[str, Any]:
    return _SEARCH_HEALTH_CACHE.get(search_database_summary, search_status_ttl)


def cached_gemma_runtime_summary() -> dict[str, Any]:
    return _GEMMA_HEALTH_CACHE.get(gemma_runtime_summary, gemma_status_ttl)


def clear_runtime_health_caches() -> None:
    _CORPUS_HEALTH_CACHE.clear()
    _SEARCH_HEALTH_CACHE.clear()
    _GEMMA_HEALTH_CACHE.clear()


def public_gemma_summary(gemma: dict[str, Any]) -> dict[str, Any]:
    state = str(gemma.get("state"))
    return {
        "reachable": bool(gemma.get("reachable")),
        "model_count": int(gemma.get("model_count") or 0),
        "state": state if state in GEMMA_PUBLIC_STATES else "unavailable",
    }


def build_artifact_manifest(include_checksums: bool = False) -> dict[str, Any]:
    artifacts = []
    for config in CORPORA:
        corpus_id = config["corpus_id"]
        artifacts.append(file_record(f"{corpus_id}_metadata", config["metadata"], "metadata", "work catalog", include_checksums))
        artifacts.append(file_record(f"{corpus_id}_segments", config["segments"], "segments", "research index", include_checksums))
    for name, path in SMALL_METADATA:
        artifacts.append(file_record(name, path, "metadata", "supporting data", include_checksums))
    artifacts.append(
        file_record(
            "segment_offset_index.sqlite",
            SEGMENT_OFFSET_INDEX,
            "index",
            "source target byte-offset index",
            include_checksums,
        )
    )
    artifacts.append(
        file_record(
            "archive_catalog.local.json",
            ARCHIVE_CATALOG,
            "index",
            "versioned archive response catalog",
            include_checksums,
        )
    )
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
            "python .\\scripts\\build_nietzsche_segments.py",
            "python .\\scripts\\build_segment_offset_index.py",
            "python .\\scripts\\build_archive_catalog.py",
            "python .\\scripts\\build_search_index.py",
            "python .\\scripts\\build_search_db.py",
            "python .\\scripts\\build_artifact_manifest.py",
        ],
    }


def build_public_artifact_manifest() -> dict[str, Any]:
    manifest = build_artifact_manifest()
    return {
        "schema_version": manifest["schema_version"],
        "generated_at": manifest["generated_at"],
        "corpora": [public_corpus_status(status) for status in manifest["corpora"]],
        "artifacts": [
            {
                "name": artifact["name"],
                "kind": artifact["kind"],
                "role": artifact["role"],
                "ready": bool(artifact["exists"]),
            }
            for artifact in manifest["artifacts"]
        ],
        "search": public_search_summary(manifest["search"]),
    }


def build_runtime_health() -> dict[str, Any]:
    corpora = cached_corpus_statuses()
    search = cached_search_database_summary()
    gemma = cached_gemma_runtime_summary()
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
    if not gemma.get("reachable"):
        gemma_state = str(gemma.get("state") or "unavailable")
        if gemma_state == "starting":
            issues.append("Gemma runtime is starting")
        elif gemma_state == "failed":
            issues.append("Gemma runtime failed to start")
        else:
            issues.append("Gemma runtime is not reachable")

    next_upgrades = [
        "Use the automated visual smoke script plus targeted browser review for future layout changes.",
        "Add a dedicated local cache management page for generated Gemma sentence translations.",
        "Revisit the documented corpus display policy only when new source families or representation types are added.",
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
        "gemma": gemma,
        "issues": issues,
        "next_recommended_upgrades": next_upgrades,
    }


def build_public_runtime_health() -> dict[str, Any]:
    health = build_runtime_health()
    return {
        "status": health["status"],
        "generated_at": health["generated_at"],
        "corpora": [public_corpus_status(status) for status in health["corpora"]],
        "search": public_search_summary(health["search"]),
        "gemma": public_gemma_summary(health["gemma"]),
        "issues": list(health["issues"]),
    }


def build_public_gemma_health() -> dict[str, Any]:
    gemma = cached_gemma_runtime_summary()
    return {
        "status": "ok" if gemma.get("reachable") else "warning",
        "generated_at": utc_now(),
        "gemma": public_gemma_summary(gemma),
    }
