from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Step:
    label: str
    script: str
    optional_args: tuple[str, ...] = ()


BUILD_STEPS = [
    Step("Nietzsche metadata", "build_nietzsche_metadata.py"),
    Step("Bible metadata", "build_bible_metadata.py"),
    Step("Bible segments", "build_bible_segments.py"),
    Step("Kierkegaard metadata", "build_kierkegaard_metadata.py"),
    Step("Kierkegaard segments", "build_kierkegaard_segments.py"),
    Step("Wittgenstein metadata", "build_wittgenstein_metadata.py"),
    Step("Wittgenstein segments", "build_wittgenstein_segments.py"),
    Step("Nietzsche segments", "build_nietzsche_segments.py"),
    Step("Portable search index", "build_search_index.py"),
    Step("SQLite search database", "build_search_db.py"),
]

CHECK_STEPS = [
    Step("Server boundary contracts", "check_server_boundary.py"),
    Step("Layout contracts", "check_layout_contracts.py"),
    Step("AI provenance contracts", "check_provenance_contracts.py"),
    Step("Corpus schema contracts", "check_corpus_schema.py"),
    Step("Runtime API contracts", "check_api_contracts.py"),
    Step("Search contracts", "check_search_contracts.py"),
    Step("Search relevance contracts", "check_search_relevance.py"),
    Step("Notes contracts", "check_notes_contracts.py"),
    Step("AI record contracts", "check_ai_records_contracts.py"),
    Step("Static route contracts", "check_static_routes.py"),
]


def run_step(step: Step, extra_args: list[str] | None = None) -> None:
    args = [sys.executable, str(SITE / "scripts" / step.script), *step.optional_args]
    if extra_args:
        args.extend(extra_args)
    print(f"\n==> {step.label}")
    subprocess.run(args, cwd=SITE, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate local reader-site artifacts and optionally verify them.")
    parser.add_argument("--skip-search-db", action="store_true", help="Skip the SQLite FTS search database rebuild.")
    parser.add_argument("--skip-manifest", action="store_true", help="Skip artifact manifest generation.")
    parser.add_argument("--manifest-checksums", action="store_true", help="Include SHA-256 checksums in the manifest.")
    parser.add_argument("--no-checks", action="store_true", help="Do not run contract checks after rebuilding.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for step in BUILD_STEPS:
        if args.skip_search_db and step.script == "build_search_db.py":
            print(f"\n==> {step.label} skipped")
            continue
        run_step(step)

    if not args.skip_manifest:
        manifest_args = ["--checksums"] if args.manifest_checksums else []
        run_step(Step("Artifact manifest", "build_artifact_manifest.py"), manifest_args)

    if not args.no_checks:
        for step in CHECK_STEPS:
            run_step(step)

    print("\nrebuild complete")


if __name__ == "__main__":
    main()
