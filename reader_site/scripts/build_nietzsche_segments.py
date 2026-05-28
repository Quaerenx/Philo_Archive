from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from segment_utils import markdown_segments


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
METADATA = SITE / "data" / "nietzsche_metadata.json"
OUTPUT = SITE / "data" / "nietzsche_segments.jsonl"


def load_metadata() -> dict:
    if not METADATA.exists():
        raise SystemExit("missing data/nietzsche_metadata.json; run build_nietzsche_metadata.py first")
    return json.loads(METADATA.read_text(encoding="utf-8"))


def build_segments() -> list[dict]:
    metadata = load_metadata()
    records: list[dict] = []
    for work in sorted(metadata.get("works", {}).values(), key=lambda item: item.get("work_id", "")):
        source_path = work.get("source_path")
        if not source_path:
            continue
        path = (ROOT / source_path).resolve()
        if not path.exists():
            continue
        segments = markdown_segments(path.read_text(encoding="utf-8", errors="replace"))
        for segment in segments:
            segment.update(
                {
                    "schema_version": 1,
                    "corpus_id": "nietzsche",
                    "work_id": work["work_id"],
                    "variant_id": "",
                    "title": work.get("title") or work.get("work_id"),
                    "source_path": source_path,
                    "url": f"{work.get('work_url') or ('/work/nietzsche/' + work['work_id'])}#{segment['segment_id']}",
                }
            )
            records.append(segment)
    return records


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
            raise SystemExit("nietzsche segments are out of date")
        print("nietzsche segments are up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(records)} segments)")


if __name__ == "__main__":
    main()
