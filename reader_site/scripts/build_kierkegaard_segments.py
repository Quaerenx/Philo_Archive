from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from segment_utils import chunk_text, text_preview


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from path_config import ROOT  # noqa: E402
from corpora.kierkegaard_text import extract_texts, has_readable_text, reading_source_path  # noqa: E402
from services.jsonl_storage import atomic_write_jsonl  # noqa: E402

METADATA = SITE / "data" / "kierkegaard_metadata.json"
OUTPUT = SITE / "data" / "kierkegaard_segments.jsonl"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_segments() -> list[dict]:
    if not METADATA.exists():
        raise SystemExit("missing data/kierkegaard_metadata.json; run build_kierkegaard_metadata.py first")
    metadata = read_json(METADATA)
    records: list[dict] = []
    for work in sorted(metadata.get("works", {}).values(), key=lambda item: item.get("work_id", "")):
        for variant in work.get("variants", []):
            source_path = variant.get("source_path")
            if not source_path:
                raise ValueError(f"missing Kierkegaard source path: {work['work_id']}/{variant.get('variant_id', '')}")
            path = (ROOT / source_path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"missing Kierkegaard source: {work['work_id']}/{variant.get('variant_id', '')}")
            path = reading_source_path(path)
            source_path = path.relative_to(ROOT).as_posix()
            order = 0
            texts = extract_texts(path)
            if not texts:
                raise ValueError(f"empty Kierkegaard source: {work['work_id']}/{variant.get('variant_id', '')}")
            segment_type = "paragraph" if has_readable_text(texts) else "section"
            for text in texts:
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
                            "segment_type": segment_type,
                            "order": order,
                            "label": f"Paragraph {order}",
                            "title": work.get("display_title") or work.get("title") or work["work_id"],
                            "source_path": source_path,
                            "text_raw": chunk,
                            "text_preview": text_preview(chunk),
                            "url": f"{work.get('work_url') or ('/work/kierkegaard/' + work['work_id'])}?variant={variant.get('variant_id', '')}#{segment_id}",
                        }
                    )
    if not records:
        raise ValueError("Kierkegaard segment build produced no records")
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
    atomic_write_jsonl(OUTPUT, records)
    print(f"wrote {OUTPUT} ({len(records)} segments)")


if __name__ == "__main__":
    main()
