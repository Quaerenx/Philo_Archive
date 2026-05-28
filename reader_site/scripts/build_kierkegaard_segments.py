from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from segment_utils import chunk_text, text_preview


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
METADATA = SITE / "data" / "kierkegaard_metadata.json"
OUTPUT = SITE / "data" / "kierkegaard_segments.jsonl"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_texts(path: Path) -> list[str]:
    payload = read_json(path)
    document = payload.get("response", {}).get("document", {})
    for key in ("prose_extract_tesim", "verse_extract_tesim", "performance_extract_tesim", "text_tesim"):
        value = document.get(key)
        if isinstance(value, list):
            texts = [str(item).strip() for item in value if str(item).strip()]
        elif value and str(value).strip():
            texts = [str(value).strip()]
        else:
            texts = []
        if texts:
            return texts
    return []


def build_segments() -> list[dict]:
    if not METADATA.exists():
        raise SystemExit("missing data/kierkegaard_metadata.json; run build_kierkegaard_metadata.py first")
    metadata = read_json(METADATA)
    records: list[dict] = []
    for work in sorted(metadata.get("works", {}).values(), key=lambda item: item.get("work_id", "")):
        for variant in work.get("variants", []):
            source_path = variant.get("source_path")
            if not source_path:
                continue
            path = (ROOT / source_path).resolve()
            if not path.exists():
                continue
            order = 0
            for text in extract_texts(path):
                for chunk in chunk_text(text):
                    order += 1
                    segment_id = f"sks-{order:04d}"
                    records.append(
                        {
                            "schema_version": 1,
                            "corpus_id": "kierkegaard",
                            "work_id": work["work_id"],
                            "variant_id": variant.get("variant_id", ""),
                            "segment_id": segment_id,
                            "segment_type": "paragraph",
                            "order": order,
                            "label": f"Paragraph {order}",
                            "title": work.get("display_title") or work.get("title") or work["work_id"],
                            "source_path": source_path,
                            "text_raw": chunk,
                            "text_preview": text_preview(chunk),
                            "url": f"{work.get('work_url') or ('/work/kierkegaard/' + work['work_id'])}?variant={variant.get('variant_id', '')}#{segment_id}",
                        }
                    )
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
            raise SystemExit("kierkegaard segments are out of date")
        print("kierkegaard segments are up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(records)} segments)")


if __name__ == "__main__":
    main()
