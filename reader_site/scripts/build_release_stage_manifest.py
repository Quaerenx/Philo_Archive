from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
OUTPUT = SITE / "data" / "release_stage_manifest.local.json"
sys.path.insert(0, str(SITE))

from path_config import SOURCE_ROOT_NAMES  # noqa: E402

MAX_STAGE_FILE_BYTES = 20 * 1024 * 1024

SOURCE_DIRS = list(SOURCE_ROOT_NAMES)

FORBIDDEN_PATTERNS = [
    "reader_site/data/*_segments.jsonl",
    "reader_site/data/search_index.jsonl",
    "reader_site/data/search_index.sqlite",
    "reader_site/data/search_index.sqlite-*",
    "reader_site/data/artifact_manifest.local.json",
    "reader_site/data/release_stage_manifest.local.json",
    "reader_site/data/visual_qa.local/",
    "reader_site/data/visual_qa.local/*",
    "reader_site/data/runtime.local/",
    "reader_site/data/runtime.local/*",
    "reader_site/data/notes/*.jsonl",
    "reader_site/data/ai/*.jsonl",
    "reader_site/data/ai/*.sqlite",
    "reader_site/data/ai/*.sqlite-*",
    "reader_site/local_paths.json",
    ".env",
    ".env.*",
]

ALLOWED_EXACT_PATHS = {
    ".gitattributes",
    ".gitignore",
    ".github/workflows/reader-site-source-light.yml",
    "README.md",
    "reader_site/README.md",
    "reader_site/data/ai/.gitkeep",
    "reader_site/data/notes/.gitkeep",
    "reader_site/run_reader_with_gemma.ps1",
    "reader_site/sentence_units.py",
}

ALLOWED_PREFIXES = [
    "reader_site/assets/",
    "reader_site/corpora/",
    "reader_site/docs/",
    "reader_site/rendering/",
    "reader_site/scripts/",
    "reader_site/services/",
    "reader_site/templates/",
]

ALLOWED_TOP_LEVEL_FILES = {
    "reader_site/app.js",
    "reader_site/index.html",
    "reader_site/notes.html",
    "reader_site/path_config.py",
    "reader_site/runtime_status.py",
    "reader_site/search.html",
    "reader_site/server.py",
    "reader_site/study.html",
    "reader_site/styles.css",
}

ALLOWED_DATA_PATTERNS = [
    "reader_site/data/*_metadata.json",
    "reader_site/data/nietzsche_catalog.json",
    "reader_site/data/nietzsche_concepts.json",
    "reader_site/data/nietzsche_encoding_report.json",
    "reader_site/data/nietzsche_notes_schema.json",
    "reader_site/data/search_eval_queries.json",
    "reader_site/data/ai_prompt_templates.json",
]


def run_git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def changed_records() -> list[dict[str, Any]]:
    raw = run_git("status", "--porcelain=v1", "-z", "-uall").stdout
    parts = [part for part in raw.split(b"\0") if part]
    records: list[dict[str, Any]] = []
    index = 0
    while index < len(parts):
        entry = parts[index].decode("utf-8", errors="surrogateescape")
        status = entry[:2]
        path = normalize_path(entry[3:])
        previous_path = ""
        if "R" in status or "C" in status:
            index += 1
            if index < len(parts):
                previous_path = path
                path = normalize_path(parts[index].decode("utf-8", errors="surrogateescape"))
        records.append({"status": status, "path": path, "previous_path": previous_path})
        index += 1
    return records


def is_source_corpus_path(path: str) -> bool:
    return any(path == source or path.startswith(f"{source}/") for source in SOURCE_DIRS)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def allowed_category(path: str) -> str:
    if path in ALLOWED_EXACT_PATHS:
        return "repo_config"
    if path in ALLOWED_TOP_LEVEL_FILES:
        return "reader_entrypoint"
    if matches_any(path, ALLOWED_DATA_PATTERNS):
        return "small_metadata"
    for prefix in ALLOWED_PREFIXES:
        if path.startswith(prefix):
            if prefix == "reader_site/assets/":
                return "ui_asset"
            if prefix == "reader_site/docs/":
                return "documentation"
            if prefix == "reader_site/scripts/":
                return "script"
            if prefix in {"reader_site/corpora/", "reader_site/rendering/", "reader_site/services/"}:
                return "application_code"
            if prefix == "reader_site/templates/":
                return "template"
    return ""


def classify_record(record: dict[str, Any]) -> dict[str, Any]:
    path = record["path"]
    absolute = REPO / path
    status = record["status"]
    category = allowed_category(path)
    exists = absolute.exists()
    size = absolute.stat().st_size if absolute.is_file() else 0

    reasons: list[str] = []
    decision = "stage"
    if is_source_corpus_path(path):
        decision = "block"
        reasons.append("source corpus path")
    if matches_any(path, FORBIDDEN_PATTERNS):
        decision = "block"
        reasons.append("generated or local-only artifact")
    if exists and absolute.is_file() and size > MAX_STAGE_FILE_BYTES:
        decision = "block"
        reasons.append(f"file exceeds {MAX_STAGE_FILE_BYTES} bytes")
    if not category and decision != "block":
        decision = "review"
        reasons.append("path is outside known release categories")
    if status.strip() == "D" and decision == "stage":
        reasons.append("deletion of tracked release file")
    if not reasons and decision == "stage":
        reasons.append(f"known {category} release path")

    return {
        **record,
        "decision": decision,
        "category": category or "unknown",
        "exists": exists,
        "bytes": size,
        "reasons": reasons,
    }


def build_manifest() -> dict[str, Any]:
    records = [classify_record(record) for record in changed_records()]
    counts: dict[str, int] = {"stage": 0, "review": 0, "block": 0}
    for record in records:
        counts[record["decision"]] = counts.get(record["decision"], 0) + 1
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "repo_root": str(REPO),
        "stage_policy": {
            "max_stage_file_bytes": MAX_STAGE_FILE_BYTES,
            "source_dirs_excluded": SOURCE_DIRS,
            "forbidden_patterns": FORBIDDEN_PATTERNS,
        },
        "counts": counts,
        "records": records,
    }


def print_summary(manifest: dict[str, Any]) -> None:
    print("release stage manifest")
    print(json.dumps(manifest["counts"], ensure_ascii=False, sort_keys=True))
    for decision in ("block", "review", "stage"):
        records = [record for record in manifest["records"] if record["decision"] == decision]
        if not records:
            continue
        print(f"\n[{decision}]")
        for record in records:
            reason = "; ".join(record["reasons"])
            print(f"{record['status']} {record['path']} - {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a staging review manifest for a GitHub release push.")
    parser.add_argument("--write", action="store_true", help=f"Write {OUTPUT.relative_to(SITE).as_posix()}.")
    parser.add_argument("--check", action="store_true", help="Fail if blocked files are present.")
    args = parser.parse_args()

    manifest = build_manifest()
    print_summary(manifest)
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nwrote {OUTPUT}")
    if args.check and manifest["counts"].get("block", 0):
        raise SystemExit("release stage manifest has blocked files")


if __name__ == "__main__":
    main()
