from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from scripts import build_segment_offset_index as index_builder  # noqa: E402
from scripts.build_segment_offset_index import build_segment_offset_index  # noqa: E402
from services.segment_offsets import (  # noqa: E402
    BUILD_COMMAND,
    INDEX_SCHEMA_VERSION,
    SegmentOffsetIndexError,
    resolve_indexed_segment_record,
    sha256_file,
    validate_segment_offset_index,
)


CORPORA = ("nietzsche", "bible", "kierkegaard", "wittgenstein")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def record(corpus_id: str, work_id: str, variant_id: str, segment_id: str, text: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "corpus_id": corpus_id,
        "work_id": work_id,
        "variant_id": variant_id,
        "segment_id": segment_id,
        "segment_type": "paragraph",
        "label": f"{work_id} / {segment_id}",
        "url": f"/work/{corpus_id}/{work_id}#{segment_id}",
        "text_raw": text,
        "text_preview": text[:220],
    }


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in records),
        encoding="utf-8",
        newline="\n",
    )


def fixture_sources(root: Path) -> tuple[dict[str, Path], dict[str, list[dict[str, object]]]]:
    sources: dict[str, Path] = {}
    records_by_corpus: dict[str, list[dict[str, object]]] = {}
    for index, corpus_id in enumerate(CORPORA):
        records = [
            record(corpus_id, "work-shared", "v1", "shared", f"{corpus_id} 첫 문장 — 철학 {index}"),
            record(corpus_id, "work-shared", "v2", "shared", f"{corpus_id} second variant"),
            record(corpus_id, "work-middle", "main", "middle", f"{corpus_id} 가운데 문장"),
            record(corpus_id, "work-last", "main", "last", f"{corpus_id} 마지막 문장 Ω"),
        ]
        path = root / f"{corpus_id}_segments.jsonl"
        write_jsonl(path, records)
        sources[corpus_id] = path
        records_by_corpus[corpus_id] = records
    return sources, records_by_corpus


def check_schema(index_path: Path, expected_records: int) -> None:
    connection = sqlite3.connect(index_path)
    try:
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        require(user_version == INDEX_SCHEMA_VERSION, "segment offset index user_version mismatch")
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(segment_offsets)")
        }
        require(
            {
                "corpus_id",
                "work_id",
                "variant_id",
                "segment_id",
                "byte_offset",
                "byte_length",
                "record_order",
                "sentence_count",
                "text_chars",
            }
            <= columns,
            "segment offset index schema is missing required columns",
        )
        count = int(connection.execute("SELECT COUNT(*) FROM segment_offsets").fetchone()[0])
        require(count == expected_records, "segment offset index record count mismatch")
        signatures = list(
            connection.execute(
                "SELECT source_size, source_mtime_ns, source_sha256 FROM index_sources"
            )
        )
        require(
            all(int(size) > 0 and int(mtime_ns) > 0 and len(str(digest)) == 64 for size, mtime_ns, digest in signatures),
            "segment offset index source signatures are incomplete",
        )
    finally:
        connection.close()


def check_first_middle_last(
    index_path: Path,
    sources: dict[str, Path],
    records_by_corpus: dict[str, list[dict[str, object]]],
) -> None:
    for corpus_id in CORPORA:
        records = records_by_corpus[corpus_id]
        for record_index in (0, len(records) // 2, len(records) - 1):
            expected = records[record_index]
            actual = resolve_indexed_segment_record(
                corpus_id,
                str(expected["work_id"]),
                str(expected["segment_id"]),
                str(expected["variant_id"]),
                index_path=index_path,
                segment_files=sources,
            )
            require(actual == expected, f"{corpus_id} sample {record_index} did not round-trip")
            require(
                any(ord(character) > 127 for character in str(actual["text_raw"])),
                f"{corpus_id} sample {record_index} lost Unicode text",
            )

        first_variant = resolve_indexed_segment_record(
            corpus_id,
            "work-shared",
            "shared",
            index_path=index_path,
            segment_files=sources,
        )
        second_variant = resolve_indexed_segment_record(
            corpus_id,
            "work-shared",
            "shared",
            "v2",
            index_path=index_path,
            segment_files=sources,
        )
        require(first_variant["variant_id"] == "v1", "variant-free lookup must preserve first-record behavior")
        require(second_variant["variant_id"] == "v2", "explicit variant lookup returned the wrong record")


def check_bounded_source_reads(index_path: Path, sources: dict[str, Path]) -> None:
    source_path = sources["wittgenstein"]
    source_size = source_path.stat().st_size
    read_sizes: list[int] = []
    original_open = Path.open

    class TrackingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def seek(self, *args):
            return self.handle.seek(*args)

        def read(self, size: int = -1):
            require(size > 0, "runtime source lookup attempted an unbounded read")
            read_sizes.append(size)
            return self.handle.read(size)

    def tracked_open(path: Path, mode: str = "r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == source_path and mode == "rb":
            return TrackingReader(handle)
        return handle

    with patch.object(Path, "open", tracked_open):
        for _ in range(2):
            resolve_indexed_segment_record(
                "wittgenstein",
                "work-last",
                "last",
                "main",
                index_path=index_path,
                segment_files=sources,
            )
    require(len(read_sizes) == 2, "each source lookup should read exactly one indexed JSONL record")
    require(all(size < source_size for size in read_sizes), "source lookup read the entire JSONL fixture")


def check_missing_corrupt_and_stale(root: Path, index_path: Path, sources: dict[str, Path]) -> None:
    missing_index = root / "missing.sqlite"
    try:
        resolve_indexed_segment_record(
            "nietzsche",
            "work-middle",
            "middle",
            "main",
            index_path=missing_index,
            segment_files=sources,
        )
    except SegmentOffsetIndexError as exc:
        require(BUILD_COMMAND in str(exc), "missing index error must include the rebuild command")
    else:
        raise AssertionError("missing segment offset index should fail")

    corrupt_index = root / "corrupt.sqlite"
    corrupt_index.write_bytes(b"not a sqlite database")
    try:
        resolve_indexed_segment_record(
            "nietzsche",
            "work-middle",
            "middle",
            "main",
            index_path=corrupt_index,
            segment_files=sources,
        )
    except SegmentOffsetIndexError as exc:
        require(BUILD_COMMAND in str(exc), "corrupt index error must include the rebuild command")
    else:
        raise AssertionError("corrupt segment offset index should fail")

    try:
        resolve_indexed_segment_record(
            "nietzsche",
            "missing-work",
            "missing",
            index_path=index_path,
            segment_files=sources,
        )
    except SegmentOffsetIndexError as exc:
        raise AssertionError("missing target must not be reported as an index failure") from exc
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing target should raise FileNotFoundError")

    stale_source = sources["nietzsche"]
    stale_source.write_bytes(stale_source.read_bytes() + b"\n")
    try:
        resolve_indexed_segment_record(
            "nietzsche",
            "work-middle",
            "middle",
            "main",
            index_path=index_path,
            segment_files=sources,
        )
    except SegmentOffsetIndexError as exc:
        require("stale" in str(exc), "stale index error should identify staleness")
        require(BUILD_COMMAND in str(exc), "stale index error must include the rebuild command")
    else:
        raise AssertionError("stale segment offset index should fail")


def check_hash_validation(root: Path) -> None:
    sources, _ = fixture_sources(root / "hash-sources")
    index_path = root / "hash.sqlite"
    build_segment_offset_index(index_path, sources)
    source = sources["bible"]
    original_stat = source.stat()
    payload = source.read_bytes()
    mutated = payload.replace(b"second variant", b"second varianc", 1)
    require(len(mutated) == len(payload) and mutated != payload, "hash fixture mutation must preserve file size")
    source.write_bytes(mutated)
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    validate_segment_offset_index(index_path, sources, verify_hashes=False)
    try:
        validate_segment_offset_index(index_path, sources, verify_hashes=True)
    except SegmentOffsetIndexError as exc:
        require("hash is stale" in str(exc), "full hash validation should detect same-stat mutation")
    else:
        raise AssertionError("full hash validation should reject changed source bytes")


def check_atomic_replacement(root: Path) -> None:
    sources, _ = fixture_sources(root / "atomic-sources")
    index_path = root / "atomic.sqlite"
    build_segment_offset_index(index_path, sources)
    original_digest = sha256_file(index_path)
    invalid_source = root / "invalid_segments.jsonl"
    invalid_source.write_text("{invalid json}\n", encoding="utf-8")
    invalid_sources = dict(sources)
    invalid_sources["wittgenstein"] = invalid_source
    try:
        build_segment_offset_index(index_path, invalid_sources)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSONL should make offset index rebuild fail")
    require(sha256_file(index_path) == original_digest, "failed rebuild replaced the existing valid index")
    require(
        not list(index_path.parent.glob(f".{index_path.name}.*.tmp")),
        "failed rebuild left temporary SQLite files behind",
    )

    with patch.object(index_builder, "index_source", side_effect=KeyboardInterrupt):
        try:
            build_segment_offset_index(index_path, sources)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("interrupted rebuild should propagate KeyboardInterrupt")
    require(sha256_file(index_path) == original_digest, "interrupted rebuild replaced the existing valid index")
    require(
        not list(index_path.parent.glob(f".{index_path.name}.*.tmp")),
        "interrupted rebuild left temporary SQLite files behind",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        source_root = root / "sources"
        source_root.mkdir()
        sources, records_by_corpus = fixture_sources(source_root)
        index_path = root / "segment_offset_index.sqlite"
        counts = build_segment_offset_index(index_path, sources)
        expected_records = sum(len(records) for records in records_by_corpus.values())
        require(sum(counts.values()) == expected_records, "builder returned the wrong record count")
        check_schema(index_path, expected_records)
        check_first_middle_last(index_path, sources, records_by_corpus)
        check_bounded_source_reads(index_path, sources)
        validate_segment_offset_index(index_path, sources, verify_hashes=True)
        check_missing_corrupt_and_stale(root, index_path, sources)

        hash_root = root / "hash"
        hash_root.mkdir()
        (hash_root / "hash-sources").mkdir()
        check_hash_validation(hash_root)

        atomic_root = root / "atomic"
        atomic_root.mkdir()
        (atomic_root / "atomic-sources").mkdir()
        check_atomic_replacement(atomic_root)

    print("segment offset contracts ok (schema/round-trip/unicode/missing/corrupt/stale/hash/atomic/interrupted)")


if __name__ == "__main__":
    main()
