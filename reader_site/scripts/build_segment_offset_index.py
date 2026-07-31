from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from sentence_units import split_sentence_texts  # noqa: E402
from services.segment_offsets import (  # noqa: E402
    INDEX_SCHEMA_VERSION,
    SEGMENT_FILES,
    SEGMENT_OFFSET_INDEX,
    validate_segment_offset_index,
)


INSERT_SQL = """
INSERT INTO segment_offsets (
  corpus_id,
  work_id,
  variant_id,
  segment_id,
  byte_offset,
  byte_length,
  record_order,
  sentence_count,
  text_chars
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(f"PRAGMA user_version={INDEX_SCHEMA_VERSION}")
    connection.execute(
        """
        CREATE TABLE index_sources (
          corpus_id TEXT PRIMARY KEY,
          schema_version INTEGER NOT NULL,
          source_name TEXT NOT NULL,
          source_size INTEGER NOT NULL,
          source_mtime_ns INTEGER NOT NULL,
          source_sha256 TEXT NOT NULL,
          record_count INTEGER NOT NULL,
          built_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE segment_offsets (
          corpus_id TEXT NOT NULL,
          work_id TEXT NOT NULL,
          variant_id TEXT NOT NULL,
          segment_id TEXT NOT NULL,
          byte_offset INTEGER NOT NULL,
          byte_length INTEGER NOT NULL,
          record_order INTEGER NOT NULL,
          sentence_count INTEGER NOT NULL,
          text_chars INTEGER NOT NULL,
          PRIMARY KEY (corpus_id, work_id, variant_id, segment_id)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_segment_offsets_without_variant
        ON segment_offsets (corpus_id, work_id, segment_id, record_order)
        """
    )


def index_source(
    connection: sqlite3.Connection,
    corpus_id: str,
    source_path: Path,
    built_at: str,
) -> int:
    if not source_path.is_file():
        raise FileNotFoundError(f"missing segment file for {corpus_id}: {source_path}")
    start_stat = source_path.stat()
    digest = hashlib.sha256()
    rows: list[tuple[str, str, str, str, int, int, int, int, int]] = []
    byte_offset = 0
    record_order = 0

    with source_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            byte_length = len(raw_line)
            digest.update(raw_line)
            if raw_line.strip():
                try:
                    record = json.loads(raw_line.decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"{source_path.name}:{line_number}: invalid UTF-8 JSON") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"{source_path.name}:{line_number}: JSONL record must be an object")
                record_corpus_id = str(record.get("corpus_id", ""))
                work_id = str(record.get("work_id", ""))
                variant_id = str(record.get("variant_id", ""))
                segment_id = str(record.get("segment_id", ""))
                if record_corpus_id != corpus_id:
                    raise ValueError(
                        f"{source_path.name}:{line_number}: expected corpus_id {corpus_id!r}, "
                        f"got {record_corpus_id!r}"
                    )
                if not work_id or not segment_id:
                    raise ValueError(f"{source_path.name}:{line_number}: missing work_id or segment_id")
                text_raw = str(record.get("text_raw", ""))
                if not text_raw.strip():
                    raise ValueError(f"{source_path.name}:{line_number}: missing text_raw")
                rows.append(
                    (
                        corpus_id,
                        work_id,
                        variant_id,
                        segment_id,
                        byte_offset,
                        byte_length,
                        record_order,
                        len(split_sentence_texts(text_raw)),
                        len(text_raw),
                    )
                )
                record_order += 1
                if len(rows) >= 5000:
                    try:
                        connection.executemany(INSERT_SQL, rows)
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(f"{source_path.name}: duplicate segment target key") from exc
                    rows.clear()
            byte_offset += byte_length

    if rows:
        try:
            connection.executemany(INSERT_SQL, rows)
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{source_path.name}: duplicate segment target key") from exc

    end_stat = source_path.stat()
    if (
        start_stat.st_size != end_stat.st_size
        or start_stat.st_mtime_ns != end_stat.st_mtime_ns
        or byte_offset != end_stat.st_size
    ):
        raise RuntimeError(f"{source_path.name} changed while the offset index was being built")
    connection.execute(
        """
        INSERT INTO index_sources (
          corpus_id,
          schema_version,
          source_name,
          source_size,
          source_mtime_ns,
          source_sha256,
          record_count,
          built_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            corpus_id,
            INDEX_SCHEMA_VERSION,
            source_path.name,
            end_stat.st_size,
            end_stat.st_mtime_ns,
            digest.hexdigest(),
            record_order,
            built_at,
        ),
    )
    return record_order


def replace_with_retry(source: Path, destination: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(20):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            last_error = exc
            if attempt == 19:
                break
            time.sleep(0.1)
    assert last_error is not None
    raise last_error


def build_segment_offset_index(
    output: Path = SEGMENT_OFFSET_INDEX,
    segment_files: Mapping[str, Path] | None = None,
) -> dict[str, int]:
    sources = dict(segment_files or SEGMENT_FILES)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    counts: dict[str, int] = {}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=MEMORY")
        create_schema(connection)
        built_at = utc_now()
        with connection:
            for corpus_id, source_path in sources.items():
                counts[corpus_id] = index_source(connection, corpus_id, source_path, built_at)
            connection.execute("ANALYZE")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if not quick_check or quick_check[0] != "ok":
            raise RuntimeError("new segment offset index failed SQLite quick_check")
        connection.close()
        connection = None
        replace_with_retry(temporary, output)
    except BaseException:
        if connection is not None:
            connection.close()
        temporary.unlink(missing_ok=True)
        raise
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or verify the SQLite byte-offset index for segment JSONL artifacts.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SEGMENT_OFFSET_INDEX,
        help="SQLite output path. Defaults to data/segment_offset_index.sqlite.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify schema, counts, stat signatures, and full source SHA-256 values without writing.",
    )
    args = parser.parse_args()

    if args.check:
        summary = validate_segment_offset_index(args.output, verify_hashes=True)
        print(
            f"segment offset index ok ({summary['records']} records, "
            f"{len(summary['by_corpus'])} corpora, hashes_verified=True)"
        )
        return

    counts = build_segment_offset_index(args.output)
    print(f"wrote {args.output} ({sum(counts.values())} records across {len(counts)} corpora)")


if __name__ == "__main__":
    main()
