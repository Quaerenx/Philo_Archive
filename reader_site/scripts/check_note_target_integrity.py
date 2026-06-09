from __future__ import annotations

import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.notes import (  # noqa: E402
    DEFAULT_CORPUS_IDS,
    NOTES_DIR,
    SEGMENT_NOTE_TARGET_TYPES,
    normalize_note_record,
    note_target_url,
    read_jsonl,
    validate_note_target,
)


SUPPORTED_CORPORA = set(DEFAULT_CORPUS_IDS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def note_files() -> list[Path]:
    if not NOTES_DIR.exists():
        return []
    return sorted(path for path in NOTES_DIR.glob("*_notes.jsonl") if path.is_file())


def corpus_id_from_path(path: Path) -> str:
    return path.name[: -len("_notes.jsonl")]


def check_note(path: Path, note: dict, index: int) -> str:
    fallback_corpus_id = corpus_id_from_path(path)
    record = normalize_note_record(note, fallback_corpus_id)
    context = f"{path.relative_to(SITE).as_posix()}#{index}"
    corpus_id = str(record.get("corpus_id", ""))
    if corpus_id not in SUPPORTED_CORPORA:
        return "skipped"

    work_id = str(record.get("work_id", "")).strip()
    variant_id = str(record.get("variant_id", "")).strip()
    target_id = str(record.get("target_id", "")).strip()
    target_type = str(record.get("target_type", "")).strip()
    require(record.get("id"), f"{context}: missing note id")
    require(record.get("note"), f"{context}: missing note text")
    require(work_id, f"{context}: missing work_id")
    require(target_id, f"{context}: missing target_id")

    validate_note_target(corpus_id, work_id, variant_id, target_id, target_type)
    expected_url = note_target_url(corpus_id, work_id, variant_id, target_id)
    actual_url = str(record.get("url", "")).strip()
    require(actual_url == expected_url, f"{context}: note URL mismatch: expected {expected_url}, got {actual_url}")
    if target_type in SEGMENT_NOTE_TARGET_TYPES and target_id != "work":
        return "segment"
    return "non_segment"


def main() -> None:
    files = note_files()
    checked = 0
    segment_targets = 0
    non_segment_targets = 0
    skipped = 0
    for path in files:
        records = read_jsonl(path)
        for index, note in enumerate(records, start=1):
            result = check_note(path, note, index)
            if result == "skipped":
                skipped += 1
                continue
            checked += 1
            if result == "segment":
                segment_targets += 1
            else:
                non_segment_targets += 1

    print(
        "note target integrity ok "
        f"({checked} notes, {segment_targets} segment targets, {non_segment_targets} other targets, {skipped} skipped)"
    )


if __name__ == "__main__":
    main()
