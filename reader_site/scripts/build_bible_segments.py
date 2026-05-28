from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
METADATA = SITE / "data" / "bible_metadata.json"
OUTPUT = SITE / "data" / "bible_segments.jsonl"


def read_metadata() -> dict:
    if not METADATA.exists():
        raise SystemExit("missing data/bible_metadata.json; run build_bible_metadata.py first")
    return json.loads(METADATA.read_text(encoding="utf-8"))


def parse_reference(segment_id: str) -> tuple[str, int, str]:
    match = re.match(r"^([^.]+)\.(\d+)\.(.+)$", segment_id)
    if not match:
        return segment_id, 0, ""
    return match.group(1), int(match.group(2)), match.group(3)


def segment_label(work: dict, segment_id: str) -> str:
    _, chapter, verse = parse_reference(segment_id)
    title = work.get("book_name_en") or work.get("title") or work.get("book_id") or work.get("work_id")
    if chapter and verse:
        return f"{title} {chapter}:{verse}"
    return segment_id


def parse_segments(path: Path, work: dict) -> list[dict]:
    marker = re.compile(r"^\*\*([A-Za-z0-9]+(?:[A-Za-z0-9]+)?\.\d+\..+?)\*\*\s*(.*)$")
    segments = []
    current_id = ""
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order, current_id, current_lines
        if not current_id:
            return
        text = " ".join(line.strip() for line in current_lines if line.strip()).strip()
        book_id, chapter, verse = parse_reference(current_id)
        order += 1
        segments.append(
            {
                "schema_version": 1,
                "corpus_id": "bible",
                "work_id": work["work_id"],
                "variant_id": work.get("variant_id") or work.get("source_id"),
                "source_id": work.get("source_id", ""),
                "book_id": book_id,
                "segment_id": current_id,
                "segment_type": "verse",
                "chapter": chapter,
                "verse": verse,
                "order": order,
                "label": segment_label(work, current_id),
                "text_raw": text,
                "text_preview": text[:160],
            }
        )
        current_id = ""
        current_lines = []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            found = marker.match(line)
            if found:
                flush()
                current_id = found.group(1)
                trailing = found.group(2).strip()
                current_lines = [trailing] if trailing else []
                continue
            if current_id and line and not line.startswith("## "):
                current_lines.append(line)
        flush()
    return segments


def build_segments() -> list[dict]:
    metadata = read_metadata()
    works = sorted(
        metadata.get("works", {}).values(),
        key=lambda item: (item.get("category_id", ""), int(item.get("order") or 0), item.get("work_id", "")),
    )
    segments: list[dict] = []
    for work in works:
        source_path = work.get("source_path")
        if not source_path:
            continue
        path = (ROOT / source_path).resolve()
        if path.exists():
            segments.extend(parse_segments(path, work))
    return segments


def encode_jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = build_segments()
    encoded = encode_jsonl(records)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != encoded:
            raise SystemExit("bible segments are out of date")
        print("bible segments are up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(records)} segments)")


if __name__ == "__main__":
    main()
