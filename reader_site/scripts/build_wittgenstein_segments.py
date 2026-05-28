from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from segment_utils import readable_markdown_chunks


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
METADATA = SITE / "data" / "wittgenstein_metadata.json"
OUTPUT = SITE / "data" / "wittgenstein_segments.jsonl"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_segments() -> list[dict]:
    if not METADATA.exists():
        raise SystemExit("missing data/wittgenstein_metadata.json; run build_wittgenstein_metadata.py first")
    metadata = read_json(METADATA)
    records: list[dict] = []
    for work in sorted(metadata.get("works", {}).values(), key=lambda item: item.get("work_id", "")):
        for variant in work.get("variants", []):
            source_path = variant.get("source_path")
            if not source_path or not source_path.endswith(".md"):
                continue
            path = (ROOT / source_path).resolve()
            if not path.exists():
                continue
            segments = readable_markdown_chunks(path.read_text(encoding="utf-8", errors="replace"))
            variant_id = variant.get("variant_id", "")
            for segment in segments:
                segment.update(
                    {
                        "schema_version": 1,
                        "corpus_id": "wittgenstein",
                        "work_id": work["work_id"],
                        "variant_id": variant_id,
                        "title": work.get("display_title") or work.get("title") or work["work_id"],
                        "source_path": source_path,
                        "url": f"{work.get('work_url') or ('/work/wittgenstein/' + work['work_id'])}?variant={variant_id}#{segment['segment_id']}",
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
            raise SystemExit("wittgenstein segments are out of date")
        print("wittgenstein segments are up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(records)} segments)")


if __name__ == "__main__":
    main()
