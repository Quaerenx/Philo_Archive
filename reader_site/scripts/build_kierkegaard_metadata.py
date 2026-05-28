from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
KIERKEGAARD_TEXTS = (
    ROOT
    / "키르케고르_원서수집"
    / "kierkegaard"
    / "kierkegaard"
    / "data"
    / "kierkegaard"
    / "raw"
    / "texts"
)
OUTPUT = SITE / "data" / "kierkegaard_metadata.json"

VARIANTS = [
    ("text", "Text"),
    ("commentary", "Commentary"),
    ("textual_account", "Textual Account"),
]


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_value(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return ""


def relative_source_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def source_href(path: Path) -> str:
    return "/source?path=" + quote(relative_source_path(path), safe="")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def title_from_document(document: dict, fallback: str) -> str:
    return (
        first_value(document.get("work_title_tesim"))
        or document.get("sort_title_ssi")
        or first_value(document.get("volume_title_tesim"))
        or document.get("id")
        or fallback
    )


def extract_count(document: dict) -> int:
    count = 0
    for key in ("prose_extract_tesim", "verse_extract_tesim", "performance_extract_tesim", "text_tesim"):
        value = document.get(key)
        if isinstance(value, list):
            count += sum(1 for item in value if str(item).strip())
        elif value and str(value).strip():
            count += 1
    return count


def load_existing_generated_at() -> str:
    if not OUTPUT.exists():
        return datetime.now().isoformat(timespec="seconds")
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8")).get("generated_at") or datetime.now().isoformat(timespec="seconds")
    except json.JSONDecodeError:
        return datetime.now().isoformat(timespec="seconds")


def build_metadata() -> dict:
    works = {}
    for work_dir in sorted([path for path in KIERKEGAARD_TEXTS.iterdir() if path.is_dir()], key=lambda item: item.name.lower()):
        variants = []
        title = ""
        copyright_note = ""
        volume = ""
        for variant_id, label in VARIANTS:
            variant_dir = work_dir / variant_id
            json_files = sorted(variant_dir.glob("*.json"))
            if not json_files:
                continue
            path = json_files[0]
            payload = read_json(path)
            document = payload.get("response", {}).get("document", {})
            title = title or title_from_document(document, work_dir.name)
            copyright_note = copyright_note or document.get("copyright_ssi", "")
            volume = volume or first_value(document.get("volume_title_tesim"))
            variants.append(
                {
                    "variant_id": variant_id,
                    "label": label,
                    "document_id": document.get("id") or path.stem,
                    "source_path": relative_source_path(path),
                    "source_url": source_href(path),
                    "source_xml": document.get("url_ssi", ""),
                    "sha256": sha256_file(path),
                    "extract_count": extract_count(document),
                }
            )
        if not variants:
            continue
        work_id = work_dir.name
        works[work_id] = {
            "corpus_id": "kierkegaard",
            "work_id": work_id,
            "title": title,
            "display_title": title,
            "author": "Søren Kierkegaard",
            "category_id": "sks",
            "category_title": "Søren Kierkegaards Skrifter",
            "language": "da",
            "work_url": f"/work/kierkegaard/{work_id}",
            "segment_scheme": "sks_extract",
            "variant_ids": [variant["variant_id"] for variant in variants],
            "variants": variants,
            "license": copyright_note,
            "volume": volume,
        }
    return {
        "schema_version": 1,
        "corpus_id": "kierkegaard",
        "generated_at": load_existing_generated_at(),
        "source_root": relative_source_path(KIERKEGAARD_TEXTS),
        "works": dict(sorted(works.items(), key=lambda item: item[0].lower())),
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
            raise SystemExit("kierkegaard metadata is out of date")
        print("kierkegaard metadata is up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(payload['works'])} works)")


if __name__ == "__main__":
    main()
