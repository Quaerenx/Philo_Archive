from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from segment_utils import text_preview


SITE = Path(__file__).resolve().parents[1]
OUTPUT = SITE / "data" / "search_index.jsonl"

SEGMENT_FILES = [
    SITE / "data" / "nietzsche_segments.jsonl",
    SITE / "data" / "bible_segments.jsonl",
    SITE / "data" / "kierkegaard_segments.jsonl",
    SITE / "data" / "wittgenstein_segments.jsonl",
]
METADATA_FILES = {
    "bible": SITE / "data" / "bible_metadata.json",
    "nietzsche": SITE / "data" / "nietzsche_metadata.json",
    "kierkegaard": SITE / "data" / "kierkegaard_metadata.json",
    "wittgenstein": SITE / "data" / "wittgenstein_metadata.json",
}


def read_json(path: Path) -> dict:
    if not path.exists():
        return {"works": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_metadata() -> dict[str, dict]:
    return {corpus_id: read_json(path).get("works", {}) for corpus_id, path in METADATA_FILES.items()}


def build_index() -> list[dict]:
    metadata = load_metadata()
    records = []
    for path in SEGMENT_FILES:
        for segment in read_jsonl(path):
            corpus_id = segment.get("corpus_id", "")
            work_id = segment.get("work_id", "")
            work = metadata.get(corpus_id, {}).get(work_id, {})
            text_raw = normalize_text(str(segment.get("text_raw") or ""))
            if not text_raw:
                continue
            title = segment.get("title") or work.get("display_title") or work.get("title") or work_id
            url = segment.get("url")
            if not url:
                base_url = work.get("work_url") or f"/work/{corpus_id}/{work_id}"
                variant = segment.get("variant_id", "")
                query = f"?variant={variant}" if variant else ""
                url = f"{base_url}{query}#{segment.get('segment_id', '')}"
            records.append(
                {
                    "schema_version": 1,
                    "corpus_id": corpus_id,
                    "work_id": work_id,
                    "variant_id": segment.get("variant_id", ""),
                    "segment_id": segment.get("segment_id", ""),
                    "segment_type": segment.get("segment_type", ""),
                    "label": segment.get("label", ""),
                    "title": title,
                    "url": url,
                    "text": text_raw,
                    "text_preview": segment.get("text_preview") or text_preview(text_raw),
                }
            )
    return records


def encode_jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    records = build_index()
    encoded = encode_jsonl(records)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != encoded:
            raise SystemExit("search index is out of date")
        print("search index is up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(records)} records)")


if __name__ == "__main__":
    main()
