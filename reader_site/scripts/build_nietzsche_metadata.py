from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

import server  # noqa: E402


def build_payload() -> dict:
    catalog = server.read_json(server.NIETZSCHE_CATALOG)
    concepts_by_work: dict[str, list[str]] = {}
    for concept in server.load_nietzsche_concepts().get("concepts", []):
        for work_id in concept.get("works", []):
            concepts_by_work.setdefault(work_id, []).append(concept["id"])

    works = {}
    for section in catalog.get("sections", []):
        for item in section.get("works", []):
            path = server.NIETZSCHE_OUTPUT / "works" / item["file"]
            if not path.exists():
                continue
            work_id = path.stem
            text = path.read_text(encoding="utf-8", errors="replace")
            document = server.render_reading_document(text)
            meta = item.get("meta", "")
            date_label = meta.split("·", 1)[0].strip() if "·" in meta else meta.strip()
            korean_title = meta.split("·", 1)[1].strip() if "·" in meta else ""
            works[work_id] = {
                "author": "Friedrich Nietzsche",
                "author_id": "nietzsche",
                "work_id": work_id,
                "title": item.get("label", server.title_from_markdown(path)),
                "korean_title": korean_title,
                "date_label": date_label,
                "category_id": section.get("id", ""),
                "category_title": section.get("title", ""),
                "source_file": item["file"],
                "source_path": server.relative_source_path(path),
                "work_url": server.work_href("nietzsche", work_id),
                "source_url": server.source_href(path),
                "language": "de",
                "edition_note": "eKGWB markdown export, locally collected",
                "heading_count": int(document["heading_count"]),
                "paragraph_count": int(document["paragraph_count"]),
                "char_count": len(text),
                "sha256": server.sha256_file(path),
                "concept_ids": concepts_by_work.get(work_id, []),
            }

    return {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "Nietzsche works only; Nachlass and Briefe remain source-level collections.",
        "works": works,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Nietzsche work metadata for the reader site.")
    parser.add_argument("--check", action="store_true", help="Fail if the metadata file is stale.")
    parser.add_argument("--output", type=Path, default=server.NIETZSCHE_METADATA)
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
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} ({len(payload['works'])} works)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
