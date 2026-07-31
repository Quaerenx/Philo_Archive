from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.segment_offsets import (  # noqa: E402
    SEGMENT_FILES,
    SEGMENT_OFFSET_INDEX,
    validate_segment_offset_index,
)
from services.source_targets import resolve_segment_target, sha256_text  # noqa: E402


CASES = [
    ("nietzsche", "GM", "p-0023", ""),
    ("bible", "sblgnt.John", "John.3.16", ""),
    ("bible", "oshb.Gen", "Gen.1.1", ""),
    ("kierkegaard", "ba", "sks-0001", "text"),
    ("wittgenstein", "Ms-101", "p-0001", "source_transcription_normalized.full"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sample_keys(corpus_id: str) -> list[tuple[str, str, str]]:
    connection = sqlite3.connect(SEGMENT_OFFSET_INDEX)
    try:
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM segment_offsets WHERE corpus_id = ?",
                (corpus_id,),
            ).fetchone()[0]
        )
        require(count > 0, f"{corpus_id}: segment offset index has no records")
        keys = []
        for record_order in (0, count // 2, count - 1):
            row = connection.execute(
                """
                SELECT work_id, variant_id, segment_id
                FROM segment_offsets
                WHERE corpus_id = ? AND record_order = ?
                """,
                (corpus_id, record_order),
            ).fetchone()
            require(row is not None, f"{corpus_id}: missing sample record_order {record_order}")
            keys.append((str(row[0]), str(row[1]), str(row[2])))
        return keys
    finally:
        connection.close()


def legacy_records_for_keys(
    corpus_id: str,
    keys: list[tuple[str, str, str]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    wanted = set(keys)
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    with SEGMENT_FILES[corpus_id].open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            key = (
                str(record.get("work_id", "")),
                str(record.get("variant_id", "")),
                str(record.get("segment_id", "")),
            )
            if key in wanted:
                found[key] = record
                if len(found) == len(wanted):
                    break
    require(set(found) == wanted, f"{corpus_id}: legacy scan did not find all index samples")
    return found


def check_index_samples() -> int:
    checked = 0
    unicode_found = False
    for corpus_id in SEGMENT_FILES:
        keys = sample_keys(corpus_id)
        legacy = legacy_records_for_keys(corpus_id, keys)
        for work_id, variant_id, segment_id in keys:
            expected = legacy[(work_id, variant_id, segment_id)]
            target = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
            text_raw = str(expected.get("text_raw", ""))
            context = f"{corpus_id}/{work_id}/{variant_id}/{segment_id}"
            require(target["text_raw"] == text_raw, f"{context}: indexed text differs from legacy scan")
            require(target["label"] == expected.get("label", segment_id), f"{context}: indexed label mismatch")
            require(target["url"] == expected.get("url"), f"{context}: indexed URL mismatch")
            require(target["source_text_sha256"] == sha256_text(text_raw), f"{context}: indexed hash mismatch")
            unicode_found = unicode_found or any(ord(character) > 127 for character in text_raw)
            checked += 1
    require(unicode_found, "real segment index samples did not exercise Unicode text")
    return checked


def main() -> None:
    validate_segment_offset_index(verify_hashes=False)
    for corpus_id, work_id, segment_id, variant_id in CASES:
        target = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
        context = f"{corpus_id}/{work_id}/{variant_id}/{segment_id}"
        require(target["corpus_id"] == corpus_id, f"{context}: corpus_id mismatch")
        require(target["work_id"] == work_id, f"{context}: work_id mismatch")
        require(target["segment_id"] == segment_id, f"{context}: segment_id mismatch")
        require(len(target["source_text_sha256"]) == 64, f"{context}: invalid source_text_sha256")
        require(target["url"].startswith(f"/work/{corpus_id}/"), f"{context}: invalid URL")
        require(target["text_raw"].strip(), f"{context}: empty source text")

    try:
        resolve_segment_target("nietzsche", "GM", "missing", "")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing segment target should raise FileNotFoundError")

    sample_count = check_index_samples()
    print(f"source target contracts ok ({len(CASES)} fixed cases, {sample_count} first/middle/last comparisons)")


if __name__ == "__main__":
    main()
