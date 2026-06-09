from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora.catalogs import NIETZSCHE_CATALOG, NIETZSCHE_METADATA, NIETZSCHE_OUTPUT, read_json  # noqa: E402
from rendering.documents import render_reading_document, title_from_markdown  # noqa: E402
from services.sources import relative_source_path, source_href, work_href  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_title(title: str, korean_title: str) -> str:
    return f"{title} / {korean_title}" if korean_title else title


def split_catalog_meta(meta: str) -> tuple[str, str]:
    for separator in ("·", "쨌"):
        if separator in meta:
            date_label, korean_title = meta.split(separator, 1)
            return date_label.strip(), korean_title.strip()
    return meta.strip(), ""


def load_concepts_by_work() -> dict[str, list[str]]:
    concepts_path = SITE / "data" / "nietzsche_concepts.json"
    concepts_payload = read_json(concepts_path) if concepts_path.exists() else {"concepts": []}
    concepts_by_work: dict[str, list[str]] = {}
    for concept in concepts_payload.get("concepts", []):
        concept_id = str(concept.get("id", "")).strip()
        if not concept_id:
            continue
        for work_id in concept.get("works", []):
            concepts_by_work.setdefault(str(work_id), []).append(concept_id)
    return concepts_by_work


def build_payload() -> dict:
    catalog = read_json(NIETZSCHE_CATALOG)
    concepts_by_work = load_concepts_by_work()

    works = {}
    for section in catalog.get("sections", []):
        for item in section.get("works", []):
            path = NIETZSCHE_OUTPUT / "works" / item["file"]
            if not path.exists():
                continue
            work_id = path.stem
            text = path.read_text(encoding="utf-8", errors="replace")
            document = render_reading_document(text)
            date_label, korean_title = split_catalog_meta(str(item.get("meta", "")))
            title = str(item.get("label") or title_from_markdown(path))
            works[work_id] = {
                "author": "Friedrich Nietzsche",
                "author_id": "nietzsche",
                "corpus_id": "nietzsche",
                "work_id": work_id,
                "title": title,
                "display_title": display_title(title, korean_title),
                "korean_title": korean_title,
                "date_label": date_label,
                "category_id": section.get("id", ""),
                "category_title": section.get("title", ""),
                "source_file": item["file"],
                "source_path": relative_source_path(path),
                "work_url": work_href("nietzsche", work_id),
                "source_url": source_href(path),
                "language": "de",
                "edition_note": "eKGWB markdown export, locally collected",
                "license": "",
                "segment_scheme": "section_paragraph",
                "variant_ids": [],
                "heading_count": int(document["heading_count"]),
                "paragraph_count": int(document["paragraph_count"]),
                "char_count": len(text),
                "sha256": sha256_file(path),
                "concept_ids": concepts_by_work.get(work_id, []),
            }

    return {
        "schema_version": 1,
        "corpus_id": "nietzsche",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "Nietzsche works only; Nachlass and Briefe remain source-level collections.",
        "works": works,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Nietzsche work metadata for the reader site.")
    parser.add_argument("--check", action="store_true", help="Fail if the metadata file is stale.")
    parser.add_argument("--output", type=Path, default=NIETZSCHE_METADATA)
    args = parser.parse_args()

    payload = build_payload()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current:
            try:
                payload["generated_at"] = json.loads(current).get("generated_at", payload["generated_at"])
            except json.JSONDecodeError:
                pass
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if current == rendered:
            print(f"metadata up to date: {args.output}")
            return 0
        print(f"metadata stale: {args.output}", file=sys.stderr)
        return 1

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {args.output} ({len(payload['works'])} works)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
