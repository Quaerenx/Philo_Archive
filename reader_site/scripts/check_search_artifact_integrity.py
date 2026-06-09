from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"

SEGMENT_FILES = {
    "nietzsche": DATA / "nietzsche_segments.jsonl",
    "bible": DATA / "bible_segments.jsonl",
    "kierkegaard": DATA / "kierkegaard_segments.jsonl",
    "wittgenstein": DATA / "wittgenstein_segments.jsonl",
}
SEARCH_INDEX = DATA / "search_index.jsonl"
SEARCH_DB = DATA / "search_index.sqlite"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    require(path.exists(), f"missing JSONL artifact: {path.relative_to(SITE).as_posix()}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{path.relative_to(SITE).as_posix()}:{line_number} is not valid JSON") from exc
            require(
                isinstance(record, dict),
                f"{path.relative_to(SITE).as_posix()}:{line_number} must be a JSON object",
            )
            records.append(record)
    require(records, f"{path.relative_to(SITE).as_posix()} has no records")
    return records


def target_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("corpus_id", "")),
        str(record.get("work_id", "")),
        str(record.get("variant_id", "")),
        str(record.get("segment_id", "")),
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def segment_lookup() -> dict[tuple[str, str, str, str], dict[str, Any]]:
    records_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for expected_corpus_id, path in SEGMENT_FILES.items():
        records = iter_jsonl(path)
        for record in records:
            corpus_id = str(record.get("corpus_id", ""))
            require(
                corpus_id == expected_corpus_id,
                f"{path.relative_to(SITE).as_posix()} contains unexpected corpus_id {corpus_id!r}",
            )
            require(str(record.get("text_raw", "")).strip(), f"{expected_corpus_id} segment has empty text_raw")
            key = target_key(record)
            require(key not in records_by_key, f"duplicate segment target key: {key}")
            records_by_key[key] = record
            counts[corpus_id] += 1
    require(records_by_key, "no segment target records found")
    return records_by_key


def search_index_lookup(segments: dict[tuple[str, str, str, str], dict[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    records_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for record in iter_jsonl(SEARCH_INDEX):
        corpus_id = str(record.get("corpus_id", ""))
        require(corpus_id in SEGMENT_FILES, f"search index contains unexpected corpus_id {corpus_id!r}")
        for field in ("work_id", "segment_id", "url", "text"):
            require(str(record.get(field, "")).strip(), f"search index record missing {field}")
        key = target_key(record)
        require(key in segments, f"search index target key is missing from segments: {key}")
        require(key not in records_by_key, f"duplicate search index target key: {key}")
        segment = segments[key]
        require(record.get("url") == segment.get("url"), f"search index URL mismatch for {key}")
        require(
            str(record.get("text", "")) == normalize_text(str(segment.get("text_raw", ""))),
            f"search index text mismatch for {key}",
        )
        records_by_key[key] = record
        counts[corpus_id] += 1
    require(records_by_key, "no search index records found")
    return records_by_key


def sqlite_lookup() -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], int, int]:
    require(SEARCH_DB.exists(), "missing search SQLite database")
    connection = sqlite3.connect(SEARCH_DB)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT corpus_id, work_id, variant_id, segment_id, url, snippet
            FROM search_segments
            """
        ).fetchall()
        records_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for row in rows:
            record = dict(row)
            key = target_key(record)
            require(key not in records_by_key, f"duplicate SQLite search target key: {key}")
            records_by_key[key] = record
        total = int(connection.execute("SELECT COUNT(*) FROM search_segments").fetchone()[0])
        has_fts = bool(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'search_segments_fts'"
            ).fetchone()
        )
        require(has_fts, "search SQLite database is missing FTS5 table")
        fts_total = int(connection.execute("SELECT COUNT(*) FROM search_segments_fts").fetchone()[0])
    finally:
        connection.close()
    require(records_by_key, "no SQLite search records found")
    return records_by_key, total, fts_total


def corpus_counts(records: dict[tuple[str, str, str, str], dict[str, Any]]) -> Counter[str]:
    return Counter(key[0] for key in records)


def compare_keys(
    label: str,
    expected: dict[tuple[str, str, str, str], dict[str, Any]],
    actual: dict[tuple[str, str, str, str], dict[str, Any]],
) -> None:
    expected_keys = set(expected)
    actual_keys = set(actual)
    missing = sorted(expected_keys - actual_keys)[:10]
    extra = sorted(actual_keys - expected_keys)[:10]
    require(not missing, f"{label} missing target keys: {missing}")
    require(not extra, f"{label} has extra target keys: {extra}")


def compare_sqlite_records(
    index: dict[tuple[str, str, str, str], dict[str, Any]],
    db: dict[tuple[str, str, str, str], dict[str, Any]],
) -> None:
    compare_keys("search SQLite", index, db)
    mismatches: list[str] = []
    for key, index_record in index.items():
        db_record = db[key]
        if db_record.get("url") != index_record.get("url"):
            mismatches.append(f"{key}: url")
        if db_record.get("snippet") != index_record.get("text_preview"):
            mismatches.append(f"{key}: snippet")
        if len(mismatches) >= 10:
            break
    require(not mismatches, "search SQLite record mismatches: " + "; ".join(mismatches))


def main() -> None:
    segments = segment_lookup()
    index = search_index_lookup(segments)
    db, db_total, fts_total = sqlite_lookup()

    compare_keys("search index", segments, index)
    compare_sqlite_records(index, db)
    segment_counts = corpus_counts(segments)
    index_counts = corpus_counts(index)
    db_counts = corpus_counts(db)
    require(segment_counts == index_counts, f"search index counts mismatch: {segment_counts} != {index_counts}")
    require(segment_counts == db_counts, f"search SQLite counts mismatch: {segment_counts} != {db_counts}")
    segment_total = len(segments)
    require(db_total == segment_total, f"search SQLite total mismatch: expected {segment_total}, got {db_total}")
    require(fts_total == db_total, f"search FTS total mismatch: expected {db_total}, got {fts_total}")
    print(f"search artifact integrity ok ({segment_total} records)")


if __name__ == "__main__":
    main()
