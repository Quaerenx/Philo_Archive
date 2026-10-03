from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from path_config import NIETZSCHE_OUTPUT, ROOT, SITE
from services.segment_offsets import SEGMENT_OFFSET_INDEX, indexed_work_segment_locations, read_indexed_segment_records

DATA = SITE / "data"

NIETZSCHE_CATALOG = DATA / "nietzsche_catalog.json"
NIETZSCHE_METADATA = DATA / "nietzsche_metadata.json"
NIETZSCHE_CONCEPTS = DATA / "nietzsche_concepts.json"
BIBLE_METADATA = DATA / "bible_metadata.json"
BIBLE_SEGMENTS = DATA / "bible_segments.jsonl"
KIERKEGAARD_METADATA = DATA / "kierkegaard_metadata.json"
WITTGENSTEIN_METADATA = DATA / "wittgenstein_metadata.json"

BIBLE_SEGMENTS_CACHE: tuple[float, list[dict]] | None = None
_METADATA_LOCK = threading.RLock()
_BIBLE_SEGMENTS_LOCK = threading.Lock()
_BIBLE_WORK_LOCK = threading.Lock()
_BIBLE_WORK_CACHE: OrderedDict[tuple, tuple[int, tuple[dict, ...]]] = OrderedDict()
BIBLE_WORK_CACHE_SIZE = 4
BIBLE_WORK_CACHE_BYTES = 16 * 1024 * 1024


def metadata_signature(path: Path) -> tuple[str, int, int, int, int]:
    info = path.stat()
    return str(path.resolve()), info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino


@lru_cache(maxsize=16)
def _read_metadata_snapshot(path_value: str, _size: int, _mtime_ns: int, _ctime_ns: int, _inode: int) -> dict:
    with Path(path_value).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_snapshot(path: Path) -> dict:
    with _METADATA_LOCK:
        for _attempt in range(3):
            signature = metadata_signature(path)
            value = _read_metadata_snapshot(*signature)
            if metadata_signature(path) == signature:
                return value
    raise RuntimeError("metadata changed repeatedly while loading")


def read_json(path: Path) -> dict:
    # Callers may decorate metadata without changing the cached snapshot.
    return deepcopy(_metadata_snapshot(path))


def metadata_record(path: Path, work_id: str) -> dict:
    if not path.exists():
        return {}
    return deepcopy(_metadata_snapshot(path).get("works", {}).get(work_id, {}))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


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
    if not NIETZSCHE_METADATA.exists():
        return {"works": {}}
    return read_json(NIETZSCHE_METADATA)


def nietzsche_metadata_record(work_id: str) -> dict:
    return metadata_record(NIETZSCHE_METADATA, work_id)


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
    return metadata_record(BIBLE_METADATA, work_id)


def kierkegaard_metadata_record(work_id: str) -> dict:
    return metadata_record(KIERKEGAARD_METADATA, work_id)


def wittgenstein_metadata_record(work_id: str) -> dict:
    return metadata_record(WITTGENSTEIN_METADATA, work_id)


def load_bible_segments() -> list[dict]:
    global BIBLE_SEGMENTS_CACHE
    if not BIBLE_SEGMENTS.exists():
        return []
    with _BIBLE_SEGMENTS_LOCK:
        mtime = BIBLE_SEGMENTS.stat().st_mtime
        if BIBLE_SEGMENTS_CACHE is None or BIBLE_SEGMENTS_CACHE[0] != mtime:
            BIBLE_SEGMENTS_CACHE = (mtime, read_jsonl(BIBLE_SEGMENTS))
        return BIBLE_SEGMENTS_CACHE[1]


def bible_segments_for_work(work_id: str) -> list[dict]:
    work = resolve_bible_work(work_id)
    variant_id = str(work.get("variant_id") or "")

    def key() -> tuple:
        return work_id, variant_id, metadata_signature(BIBLE_SEGMENTS), metadata_signature(SEGMENT_OFFSET_INDEX)

    with _BIBLE_WORK_LOCK:
        try:
            signature = key()
        except OSError:
            # Preserve the index service's rebuild guidance for missing artifacts.
            locations = indexed_work_segment_locations("bible", work_id, variant_id)
            return read_indexed_segment_records("bible", locations)
        cached = _BIBLE_WORK_CACHE.get(signature)
        if cached is not None:
            _BIBLE_WORK_CACHE.move_to_end(signature)
            return [dict(record) for record in cached[1]]
        locations = indexed_work_segment_locations("bible", work_id, variant_id)
        records = tuple(read_indexed_segment_records("bible", locations))
        source_bytes = sum(int(location["byte_length"]) for location in locations)
        if source_bytes <= BIBLE_WORK_CACHE_BYTES and key() == signature:
            _BIBLE_WORK_CACHE[signature] = source_bytes, records
            while len(_BIBLE_WORK_CACHE) > BIBLE_WORK_CACHE_SIZE or sum(entry[0] for entry in _BIBLE_WORK_CACHE.values()) > BIBLE_WORK_CACHE_BYTES:
                _BIBLE_WORK_CACHE.popitem(last=False)
        return [dict(record) for record in records]


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
