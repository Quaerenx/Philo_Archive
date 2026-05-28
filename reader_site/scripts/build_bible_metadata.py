from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
BIBLE_OUTPUT = ROOT / "성경_원서수집" / "bible" / "bible" / "output"
OUTPUT = SITE / "data" / "bible_metadata.json"

SOURCE_SPECS = [
    {
        "source_id": "oshb_morphhb",
        "work_prefix": "oshb",
        "source_label": "OSHB MorphHB",
        "category_id": "hebrew_bible",
        "category_title": "Hebrew Bible",
        "language": "hbo",
        "folder": BIBLE_OUTPUT / "markdown" / "core_original" / "hebrew_bible_oshb",
    },
    {
        "source_id": "sblgnt",
        "work_prefix": "sblgnt",
        "source_label": "SBLGNT",
        "category_id": "greek_nt",
        "category_title": "Greek New Testament",
        "language": "grc",
        "folder": BIBLE_OUTPUT / "markdown" / "core_original" / "greek_nt_sblgnt",
    },
    {
        "source_id": "lxx_swete",
        "work_prefix": "lxx",
        "source_label": "LXX Swete",
        "category_id": "lxx_deuterocanon",
        "category_title": "LXX / Deuterocanon",
        "language": "grc",
        "folder": BIBLE_OUTPUT / "markdown" / "lxx_and_deuterocanon" / "lxx_swete",
    },
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_source_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def source_href(path: Path) -> str:
    return "/source?path=" + quote(relative_source_path(path), safe="")


def clean_markdown_title(value: str) -> str:
    value = re.sub(r"^#+\s*", "", value.strip())
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value.replace("_", "").strip()


def markdown_title(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("# "):
                return clean_markdown_title(line)
    return path.stem


def header_fields(path: Path) -> dict[str, str]:
    fields = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                if fields:
                    break
                continue
            match = re.match(r"^-\s+([^:]+):\s+`?(.+?)`?\s*$", stripped)
            if match:
                fields[match.group(1).strip().lower().replace(" ", "_")] = match.group(2).strip()
    return fields


def first_verse_id(path: Path) -> str:
    pattern = re.compile(r"^\*\*([A-Za-z0-9]+(?:[A-Za-z0-9]+)?\.\d+\.\d+[A-Za-z]?)\*\*")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = pattern.match(line.strip())
            if match:
                return match.group(1)
    return ""


def file_order(path: Path) -> int:
    match = re.match(r"^(\d+)_", path.name)
    return int(match.group(1)) if match else 9999


def load_existing_generated_at() -> str:
    if not OUTPUT.exists():
        return datetime.now().isoformat(timespec="seconds")
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8")).get("generated_at") or datetime.now().isoformat(timespec="seconds")
    except json.JSONDecodeError:
        return datetime.now().isoformat(timespec="seconds")


def build_metadata() -> dict:
    canonical_rows = read_csv_rows(BIBLE_OUTPUT / "mapping" / "canonical_books.csv")
    canonical = {row.get("book_id", ""): row for row in canonical_rows}
    inventory_rows = read_csv_rows(BIBLE_OUTPUT / "mapping" / "source_inventory.csv")
    inventory = {(row.get("source_id", ""), row.get("book_id", "")): row for row in inventory_rows}
    works = {}

    for spec in SOURCE_SPECS:
        folder = spec["folder"]
        for path in sorted(folder.glob("*.md"), key=lambda item: (file_order(item), item.name.lower())):
            verse_id = first_verse_id(path)
            if not verse_id:
                continue
            book_id = verse_id.split(".", 1)[0]
            work_id = f"{spec['work_prefix']}.{book_id}"
            title = markdown_title(path)
            fields = header_fields(path)
            canon = canonical.get(book_id, {})
            stats = inventory.get((spec["source_id"], book_id), {})
            display_title = title
            if canon.get("book_name_ko") and canon.get("book_name_ko") not in title:
                display_title = f"{title} / {canon['book_name_ko']}"
            works[work_id] = {
                "corpus_id": "bible",
                "work_id": work_id,
                "title": canon.get("book_name_en") or stats.get("book_name_detected") or title,
                "display_title": display_title,
                "book_id": book_id,
                "book_name_en": canon.get("book_name_en") or stats.get("book_name_detected") or title,
                "book_name_ko": canon.get("book_name_ko", ""),
                "canon": canon.get("canon", ""),
                "order": int(canon.get("order") or file_order(path)),
                "category_id": spec["category_id"],
                "category_title": spec["category_title"],
                "language": fields.get("language") or spec["language"],
                "source_id": spec["source_id"],
                "source_label": spec["source_label"],
                "variant_id": spec["source_id"],
                "source_path": relative_source_path(path),
                "work_url": f"/work/bible/{work_id}",
                "source_url": source_href(path),
                "segment_scheme": "chapter_verse",
                "variant_ids": [spec["source_id"]],
                "license": fields.get("license", ""),
                "corpus_layer": fields.get("corpus_layer", ""),
                "tradition_scope": fields.get("tradition_scope", ""),
                "chapter_count": int(stats.get("chapter_count") or 0),
                "verse_count": int(stats.get("verse_count") or 0),
                "first_ref": stats.get("first_ref", verse_id),
                "last_ref": stats.get("last_ref", ""),
                "sha256": sha256_file(path),
                "concept_ids": [],
            }

    return {
        "schema_version": 1,
        "corpus_id": "bible",
        "generated_at": load_existing_generated_at(),
        "source_root": relative_source_path(BIBLE_OUTPUT),
        "works": dict(sorted(works.items(), key=lambda item: (item[1]["category_id"], item[1]["order"], item[0]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_metadata()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != encoded:
            raise SystemExit("bible metadata is out of date")
        print("bible metadata is up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(payload['works'])} works)")


if __name__ == "__main__":
    main()
