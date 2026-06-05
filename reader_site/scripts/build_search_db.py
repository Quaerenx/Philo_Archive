from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
JSONL = SITE / "data" / "search_index.jsonl"
OUTPUT = SITE / "data" / "search_index.sqlite"


def normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def iter_records():
    with JSONL.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_database() -> int:
    if not JSONL.exists():
        raise SystemExit("missing data/search_index.jsonl; run build_search_index.py first")
    if OUTPUT.exists():
        OUTPUT.unlink()
    connection = sqlite3.connect(OUTPUT)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute(
            """
            CREATE TABLE search_segments (
              id INTEGER PRIMARY KEY,
              corpus_id TEXT NOT NULL,
              work_id TEXT NOT NULL,
              variant_id TEXT NOT NULL,
              segment_id TEXT NOT NULL,
              segment_type TEXT NOT NULL,
              label TEXT NOT NULL,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              snippet TEXT NOT NULL,
              search_text TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE search_segments_fts USING fts5(
              title,
              label,
              search_text,
              content='search_segments',
              content_rowid='id',
              tokenize='unicode61'
            )
            """
        )
        rows = []
        count = 0
        for record in iter_records():
            search_text = normalize_search_text(
                " ".join(
                    [
                        str(record.get("title", "")),
                        str(record.get("label", "")),
                        str(record.get("text", "")),
                    ]
                )
            )
            rows.append(
                (
                    record.get("corpus_id", ""),
                    record.get("work_id", ""),
                    record.get("variant_id", ""),
                    record.get("segment_id", ""),
                    record.get("segment_type", ""),
                    record.get("label", ""),
                    record.get("title", ""),
                    record.get("url", ""),
                    record.get("text_preview", ""),
                    search_text,
                )
            )
            count += 1
            if len(rows) >= 5000:
                connection.executemany(
                    """
                    INSERT INTO search_segments
                    (corpus_id, work_id, variant_id, segment_id, segment_type, label, title, url, snippet, search_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                rows.clear()
        if rows:
            connection.executemany(
                """
                INSERT INTO search_segments
                (corpus_id, work_id, variant_id, segment_id, segment_type, label, title, url, snippet, search_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        connection.execute("CREATE INDEX idx_search_corpus ON search_segments(corpus_id)")
        connection.execute("CREATE INDEX idx_search_work ON search_segments(corpus_id, work_id)")
        connection.execute("CREATE INDEX idx_search_variant ON search_segments(corpus_id, work_id, variant_id)")
        connection.execute(
            """
            INSERT INTO search_segments_fts(rowid, title, label, search_text)
            SELECT id, title, label, search_text FROM search_segments
            """
        )
        connection.commit()
        return count
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not OUTPUT.exists():
            raise SystemExit("search sqlite db is missing")
        connection = sqlite3.connect(OUTPUT)
        try:
            count = connection.execute("SELECT COUNT(*) FROM search_segments").fetchone()[0]
            has_fts = bool(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'search_segments_fts'"
                ).fetchone()
            )
        finally:
            connection.close()
        print(f"search sqlite db exists ({count} records, fts5={has_fts})")
        return
    count = build_database()
    print(f"wrote {OUTPUT} ({count} records)")


if __name__ == "__main__":
    main()
