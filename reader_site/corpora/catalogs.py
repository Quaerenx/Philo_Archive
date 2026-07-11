from __future__ import annotations

import json
import re
from pathlib import Path

from path_config import NIETZSCHE_OUTPUT, ROOT, SITE
from services.bounded_cache import TTLBoundedCache

DATA = SITE / "data"

NIETZSCHE_CATALOG = DATA / "nietzsche_catalog.json"
NIETZSCHE_METADATA = DATA / "nietzsche_metadata.json"
NIETZSCHE_CONCEPTS = DATA / "nietzsche_concepts.json"
BIBLE_METADATA = DATA / "bible_metadata.json"
BIBLE_SEGMENTS = DATA / "bible_segments.jsonl"
KIERKEGAARD_METADATA = DATA / "kierkegaard_metadata.json"
WITTGENSTEIN_METADATA = DATA / "wittgenstein_metadata.json"

METADATA_CACHE_MAX_ENTRIES = 8
METADATA_CACHE_TTL_SECONDS = 300
BIBLE_WORK_SEGMENTS_CACHE_MAX_ENTRIES = 24
BIBLE_WORK_SEGMENTS_CACHE_TTL_SECONDS = 300
METADATA_CACHE: TTLBoundedCache[tuple[str, int, int], dict] = TTLBoundedCache(
    max_entries=METADATA_CACHE_MAX_ENTRIES,
    ttl_seconds=METADATA_CACHE_TTL_SECONDS,
)
BIBLE_WORK_SEGMENTS_CACHE: TTLBoundedCache[tuple[str, int, int], list[dict]] = TTLBoundedCache(
    max_entries=BIBLE_WORK_SEGMENTS_CACHE_MAX_ENTRIES,
    ttl_seconds=BIBLE_WORK_SEGMENTS_CACHE_TTL_SECONDS,
)


def file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return (int(stat.st_mtime_ns), int(stat.st_size))


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def cached_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return dict(fallback)
    signature = file_signature(path)

    def load_or_fallback() -> dict:
        try:
            return read_json(path)
        except (OSError, json.JSONDecodeError):
            return dict(fallback)

    return METADATA_CACHE.get_or_set((str(path), signature[0], signature[1]), load_or_fallback)


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_nietzsche_catalog() -> dict:
    if not NIETZSCHE_CATALOG.exists():
        return {"sections": []}
    return read_json(NIETZSCHE_CATALOG)


def nietzsche_catalog_record(work_id: str) -> dict:
    file_name = f"{work_id}.md"
    catalog = load_nietzsche_catalog()
    for section in catalog.get("sections", []):
        for work in section.get("works", []):
            if work.get("file") == file_name:
                record = dict(work)
                record["section_title"] = section.get("title", "")
                record["section_id"] = section.get("id", "")
                return record
    return {}


def load_nietzsche_metadata() -> dict:
    return cached_json(NIETZSCHE_METADATA, {"schema_version": 1, "corpus_id": "nietzsche", "works": {}})


def nietzsche_metadata_record(work_id: str) -> dict:
    return load_nietzsche_metadata().get("works", {}).get(work_id, {})


def load_nietzsche_concepts() -> dict:
    if not NIETZSCHE_CONCEPTS.exists():
        return {"concepts": []}
    return read_json(NIETZSCHE_CONCEPTS)


def load_bible_metadata() -> dict:
    return cached_json(BIBLE_METADATA, {"schema_version": 1, "corpus_id": "bible", "works": {}})


def load_kierkegaard_metadata() -> dict:
    return cached_json(KIERKEGAARD_METADATA, {"schema_version": 1, "corpus_id": "kierkegaard", "works": {}})


def load_wittgenstein_metadata() -> dict:
    return cached_json(WITTGENSTEIN_METADATA, {"schema_version": 1, "corpus_id": "wittgenstein", "works": {}})


def bible_metadata_record(work_id: str) -> dict:
    return load_bible_metadata().get("works", {}).get(work_id, {})


def kierkegaard_metadata_record(work_id: str) -> dict:
    return load_kierkegaard_metadata().get("works", {}).get(work_id, {})


def wittgenstein_metadata_record(work_id: str) -> dict:
    return load_wittgenstein_metadata().get("works", {}).get(work_id, {})


def bible_segments_for_work(work_id: str) -> list[dict]:
    if not BIBLE_SEGMENTS.exists():
        return []
    signature = file_signature(BIBLE_SEGMENTS)

    def load_work_segments() -> list[dict]:
        return [segment for segment in iter_jsonl(BIBLE_SEGMENTS) if segment.get("work_id") == work_id]

    return BIBLE_WORK_SEGMENTS_CACHE.get_or_set((work_id, signature[0], signature[1]), load_work_segments)


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def bible_segments_payload_from_query(query: dict[str, list[str]]) -> dict:
    work_id = first_query_value(query, "work_id")
    if not work_id:
        return {"segments": []}
    resolve_bible_work(work_id)
    return {"segments": bible_segments_for_work(work_id)}


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
