from __future__ import annotations

import json
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


def segment_counts() -> Counter[str]:
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
            counts[corpus_id] += 1
    return counts


def search_index_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in iter_jsonl(SEARCH_INDEX):
        corpus_id = str(record.get("corpus_id", ""))
        require(corpus_id in SEGMENT_FILES, f"search index contains unexpected corpus_id {corpus_id!r}")
        for field in ("work_id", "segment_id", "url", "text"):
            require(str(record.get(field, "")).strip(), f"search index record missing {field}")
        counts[corpus_id] += 1
    return counts


def sqlite_counts() -> tuple[Counter[str], int, int]:
    require(SEARCH_DB.exists(), "missing search SQLite database")
    connection = sqlite3.connect(SEARCH_DB)
    try:
        db_counts = Counter(
            {
                str(corpus_id): int(count)
                for corpus_id, count in connection.execute(
                    "SELECT corpus_id, COUNT(*) FROM search_segments GROUP BY corpus_id"
                )
            }
        )
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
    return db_counts, total, fts_total


def compare_counts(label: str, expected: Counter[str], actual: Counter[str]) -> None:
    require(
        set(actual) == set(expected),
        f"{label} corpus set mismatch: expected {sorted(expected)}, got {sorted(actual)}",
    )
    mismatches = [
        f"{corpus_id}: expected {expected[corpus_id]}, got {actual[corpus_id]}"
        for corpus_id in sorted(expected)
        if expected[corpus_id] != actual[corpus_id]
    ]
    require(not mismatches, f"{label} counts mismatch: " + "; ".join(mismatches))


def main() -> None:
    segments = segment_counts()
    index = search_index_counts()
    db, db_total, fts_total = sqlite_counts()

    compare_counts("search index", segments, index)
    compare_counts("search SQLite", segments, db)
    segment_total = sum(segments.values())
    require(db_total == segment_total, f"search SQLite total mismatch: expected {segment_total}, got {db_total}")
    require(fts_total == db_total, f"search FTS total mismatch: expected {db_total}, got {fts_total}")
    print(f"search artifact integrity ok ({segment_total} records)")


if __name__ == "__main__":
    main()
