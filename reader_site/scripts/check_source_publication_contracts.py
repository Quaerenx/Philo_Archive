from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
POLICY = SITE / "docs" / "source_publication_policy.md"
GITIGNORE = REPO / ".gitignore"

SOURCE_DIRS = [
    "니체_원서수집",
    "비트겐슈타인_원서수집",
    "성경_원서수집",
    "키르케고르_원서수집",
]

FORBIDDEN_TRACKED_PATTERNS = [
    "reader_site/data/*_segments.jsonl",
    "reader_site/data/search_index.jsonl",
    "reader_site/data/search_index.sqlite",
    "reader_site/data/search_index.sqlite-*",
    "reader_site/data/artifact_manifest.local.json",
    "reader_site/data/release_stage_manifest.local.json",
    "reader_site/data/visual_qa.local/*",
    "reader_site/data/notes/*.jsonl",
    "reader_site/data/ai/*.jsonl",
    "reader_site/data/ai/*.sqlite",
    "reader_site/data/ai/*.sqlite-*",
]

REQUIRED_POLICY_SECTIONS = [
    "## Publication Boundary",
    "## Metadata Rule",
    "## Local Restore Rule",
    "## Verification",
]

REQUIRED_POLICY_PHRASES = [
    "not a public mirror",
    "Git must not contain",
    "local source-corpus folders",
    "generated segment JSONL files",
    "personal notes",
    "generated AI interpretations",
    "PHILOSOPHY_CRAWL_ROOT",
]

REQUIRED_GITIGNORE_RULES = [
    f"{source}/" for source in SOURCE_DIRS
] + [
    "reader_site/data/*_segments.jsonl",
    "reader_site/data/search_index.jsonl",
    "reader_site/data/search_index.sqlite",
    "reader_site/data/search_index.sqlite-*",
    "reader_site/data/notes/*.jsonl",
    "reader_site/data/ai/*.jsonl",
]

FORBIDDEN_TEXT_KEYS = {
    "body",
    "content",
    "full_text",
    "html",
    "source_text",
    "text_raw",
}

ABSOLUTE_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True)


def tracked_paths() -> list[str]:
    raw = run_git("ls-files", "-z").stdout
    return [
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in raw.split(b"\0")
        if item
    ]


def check_policy() -> None:
    require(POLICY.exists(), "missing docs/source_publication_policy.md")
    text = POLICY.read_text(encoding="utf-8")
    for section in REQUIRED_POLICY_SECTIONS:
        require(section in text, f"source publication policy missing section {section}")
    for phrase in REQUIRED_POLICY_PHRASES:
        require(phrase in text, f"source publication policy missing phrase {phrase!r}")


def check_gitignore() -> None:
    text = GITIGNORE.read_text(encoding="utf-8")
    for rule in REQUIRED_GITIGNORE_RULES:
        require(rule in text, f".gitignore missing source publication rule {rule}")


def is_forbidden_tracked_path(path: str) -> bool:
    if any(path == source or path.startswith(f"{source}/") for source in SOURCE_DIRS):
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_TRACKED_PATTERNS)


def check_tracked_paths() -> None:
    forbidden = sorted(path for path in tracked_paths() if is_forbidden_tracked_path(path))
    require(not forbidden, "source publication forbidden tracked paths: " + ", ".join(forbidden))


def walk_json(value: Any, path: str = "") -> list[tuple[str, Any]]:
    records: list[tuple[str, Any]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            records.extend(walk_json(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(walk_json(child, f"{path}[{index}]"))
    return records


def check_metadata_json() -> None:
    metadata_files = sorted((SITE / "data").glob("*_metadata.json"))
    require(metadata_files, "missing tracked metadata JSON files")
    for path in metadata_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for pointer, value in walk_json(payload):
            key = pointer.rsplit(".", maxsplit=1)[-1]
            if "[" in key:
                key = key.split("[", maxsplit=1)[0]
            require(key not in FORBIDDEN_TEXT_KEYS, f"{path.relative_to(REPO)} contains forbidden source-text key {pointer}")
            if key in {"source_path", "source_root"} and isinstance(value, str):
                require(not ABSOLUTE_WINDOWS_PATH.match(value), f"{path.relative_to(REPO)} contains absolute local path at {pointer}")


def check_docs_reference_policy() -> None:
    required_docs = [
        REPO / "README.md",
        SITE / "README.md",
        SITE / "docs" / "release_handoff.md",
        SITE / "docs" / "clean_clone_reproducibility.md",
    ]
    for path in required_docs:
        text = path.read_text(encoding="utf-8")
        require("source" in text.lower(), f"{path.relative_to(REPO)} should describe source boundary")


def main() -> None:
    require((REPO / ".git").exists(), "source publication contracts require a Git checkout")
    check_policy()
    check_gitignore()
    check_tracked_paths()
    check_metadata_json()
    check_docs_reference_policy()
    print("source publication contracts ok")


if __name__ == "__main__":
    main()
