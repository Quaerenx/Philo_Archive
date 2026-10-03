from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from path_config import ROOT  # noqa: E402
from services.rebuild_transaction import preflight_registered_sources, preserve_artifacts  # noqa: E402


@dataclass(frozen=True)
class Step:
    label: str
    script: str
    optional_args: tuple[str, ...] = ()
    requires_search_db: bool = False


BUILD_STEPS = [
    Step("Nietzsche metadata", "build_nietzsche_metadata.py"),
    Step("Bible metadata", "build_bible_metadata.py"),
    Step("Bible segments", "build_bible_segments.py"),
    Step("Kierkegaard metadata", "build_kierkegaard_metadata.py"),
    Step("Kierkegaard segments", "build_kierkegaard_segments.py"),
    Step("Wittgenstein metadata", "build_wittgenstein_metadata.py"),
    Step("Wittgenstein segments", "build_wittgenstein_segments.py"),
    Step("Nietzsche segments", "build_nietzsche_segments.py"),
    Step("Segment byte-offset index", "build_segment_offset_index.py"),
    Step("Versioned archive catalog", "build_archive_catalog.py"),
    Step("Portable search index", "build_search_index.py"),
    Step("SQLite search database", "build_search_db.py"),
]

CHECK_STEPS = [
    Step("Review regression checks", "check_review_regressions.py"),
    Step("Server boundary contracts", "check_server_boundary.py"),
    Step("Clean clone contracts", "check_clean_clone_contracts.py"),
    Step("CI contracts", "check_ci_contracts.py"),
    Step("Encoding contracts", "check_encoding_contracts.py"),
    Step("Path contracts", "check_path_contracts.py"),
    Step("Source publication contracts", "check_source_publication_contracts.py"),
    Step("Layout contracts", "check_layout_contracts.py"),
    Step("AI provenance contracts", "check_provenance_contracts.py"),
    Step("Prompt template contracts", "check_prompt_template_contracts.py", ("--with-source-targets",)),
    Step("Sentence translation contracts", "check_sentence_translation_contracts.py", ("--with-source-targets",)),
    Step("Translation quality regressions", "check_translation_quality_regressions.py"),
    Step("Corpus schema contracts", "check_corpus_schema.py"),
    Step("Segment offset contracts", "check_segment_offset_contracts.py"),
    Step("Large work chunk contracts", "check_work_chunk_contracts.py"),
    Step("Source target contracts", "check_source_target_contracts.py"),
    Step("Restore readiness contracts", "check_restore_readiness.py", requires_search_db=True),
    Step("Runtime API contracts", "check_api_contracts.py"),
    Step("Search contracts", "check_search_contracts.py", requires_search_db=True),
    Step("Search relevance contracts", "check_search_relevance.py", requires_search_db=True),
    Step("Search artifact integrity", "check_search_artifact_integrity.py", requires_search_db=True),
    Step("Notes contracts", "check_notes_contracts.py"),
    Step("Note target integrity", "check_note_target_integrity.py"),
    Step("AI record contracts", "check_ai_records_contracts.py"),
    Step("Translation human goldset", "check_translation_goldset.py"),
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
    preflight_registered_sources(SITE / "data", ROOT)
    with preserve_artifacts(SITE / "data"):
        rebuild(args)
    print("\nrebuild complete")


def rebuild(args: argparse.Namespace) -> None:
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
            if args.skip_search_db and step.requires_search_db:
                print(f"\n==> {step.label} skipped (search database rebuild disabled)")
                continue
            run_step(step)


if __name__ == "__main__":
    main()
