from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


SITE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT", Path(__file__).resolve().parents[2])).resolve()
WITTGENSTEIN_OUTPUT = ROOT / "비트겐슈타인_원서수집" / "wittgenstein" / "wittgenstein" / "output"
MANIFEST = WITTGENSTEIN_OUTPUT / "_manifest.json"
OUTPUT = SITE / "data" / "wittgenstein_metadata.json"

KIND_LABELS = {
    "source_transcription_normalized": "Source normalized",
    "source_transcription_diplomatic": "Source diplomatic",
    "idp_transcription_linear": "IDP linear",
    "idp_transcription_diplomatic": "IDP diplomatic",
    "source_metadata": "Metadata",
}
KIND_ORDER = {
    "source_transcription_normalized": 10,
    "source_transcription_diplomatic": 20,
    "idp_transcription_linear": 30,
    "idp_transcription_diplomatic": 40,
    "source_metadata": 50,
}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def safe_work_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return cleaned or "work"


def load_existing_generated_at() -> str:
    if not OUTPUT.exists():
        return datetime.now().isoformat(timespec="seconds")
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8")).get("generated_at") or datetime.now().isoformat(timespec="seconds")
    except json.JSONDecodeError:
        return datetime.now().isoformat(timespec="seconds")


def allocate_work_ids(siglums: list[str]) -> dict[str, str]:
    allocated = {}
    used = {}
    for siglum in sorted(siglums, key=str.lower):
        base = safe_work_id(siglum)
        work_id = base
        if work_id in used and used[work_id] != siglum:
            short = hashlib.sha1(siglum.encode("utf-8")).hexdigest()[:8]
            work_id = f"{base}_{short}"
        used[work_id] = siglum
        allocated[siglum] = work_id
    return allocated


def build_metadata() -> dict:
    manifest = read_json(MANIFEST)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in manifest.get("records", []):
        output_name = record.get("output_md") or record.get("output_html")
        if not output_name:
            continue
        path = WITTGENSTEIN_OUTPUT / output_name
        if not path.exists():
            continue
        grouped[record.get("siglum") or path.stem].append(record)

    work_ids = allocate_work_ids(list(grouped))
    works = {}
    for siglum, records in grouped.items():
        work_id = work_ids[siglum]
        variants = []
        used_variant_ids: set[str] = set()
        for record in sorted(records, key=lambda item: (KIND_ORDER.get(item.get("kind", ""), 999), item.get("variant", ""))):
            output_name = record.get("output_md") or record.get("output_html")
            path = WITTGENSTEIN_OUTPUT / output_name
            kind = record.get("kind", "")
            variant_name = record.get("variant", "")
            variant_id = kind
            if variant_name and not kind.endswith(variant_name):
                variant_id = f"{kind}.{safe_work_id(variant_name)}"
            if variant_id in used_variant_ids:
                suffix = safe_work_id(Path(output_name).stem)
                candidate = f"{variant_id}.{suffix}"
                if candidate in used_variant_ids:
                    short = hashlib.sha1(str(output_name).encode("utf-8")).hexdigest()[:8]
                    candidate = f"{variant_id}.{short}"
                variant_id = candidate
            used_variant_ids.add(variant_id)
            label = KIND_LABELS.get(kind, kind)
            if variant_name and variant_name.lower() not in label.lower():
                label = f"{label} ({variant_name})"
            variants.append(
                {
                    "variant_id": variant_id,
                    "label": label,
                    "variant": variant_name,
                    "source_path": relative_source_path(path),
                    "source_url": source_href(path),
                    "external_source_url": record.get("source_url", ""),
                    "sha256": record.get("export_md_sha256") or sha256_file(path),
                    "license": record.get("license", ""),
                    "rights_note": record.get("rights_note", ""),
                }
            )
        category_id = "idp_groups" if siglum.startswith("Group_") else "source_items"
        category_title = "IDP Groups" if category_id == "idp_groups" else "Source Items"
        works[work_id] = {
            "corpus_id": "wittgenstein",
            "work_id": work_id,
            "title": siglum,
            "display_title": siglum.replace("_", " "),
            "author": "Ludwig Wittgenstein",
            "category_id": category_id,
            "category_title": category_title,
            "language": "de/en",
            "work_url": f"/work/wittgenstein/{work_id}",
            "segment_scheme": "transcription_block",
            "variant_ids": [variant["variant_id"] for variant in variants],
            "concept_ids": [],
            "variants": variants,
            "license": variants[0].get("license", "") if variants else "",
            "rights_note": variants[0].get("rights_note", "") if variants else "",
            "siglum": siglum,
        }
    return {
        "schema_version": 1,
        "corpus_id": "wittgenstein",
        "generated_at": load_existing_generated_at(),
        "source_root": relative_source_path(WITTGENSTEIN_OUTPUT),
        "works": dict(sorted(works.items(), key=lambda item: (item[1]["category_id"], item[1]["title"].lower()))),
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
            raise SystemExit("wittgenstein metadata is out of date")
        print("wittgenstein metadata is up to date")
        return
    OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(payload['works'])} works)")


if __name__ == "__main__":
    main()
