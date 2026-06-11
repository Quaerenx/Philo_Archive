from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
sys.path.insert(0, str(SITE))

MAX_TRACKED_FILE_BYTES = 20 * 1024 * 1024

from path_config import SOURCE_ROOT_NAMES  # noqa: E402

SOURCE_DIRS = list(SOURCE_ROOT_NAMES)

GENERATED_ARTIFACT_PATTERNS = [
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
]

LOCAL_STATE_PATTERNS = [
    "reader_site/data/notes/*.jsonl",
    "reader_site/data/ai/*.jsonl",
    "reader_site/data/ai/*.sqlite",
    "reader_site/data/ai/*.sqlite-*",
    "reader_site/local_paths.json",
    ".env",
    ".env.*",
]

REQUIRED_DOC_SNIPPETS = {
    "README.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "python .\\scripts\\rebuild_all.py",
        "python .\\scripts\\build_release_stage_manifest.py --check",
        "python .\\scripts\\check_clean_clone_contracts.py",
        "python .\\scripts\\check_ci_contracts.py",
        "python .\\scripts\\check_encoding_contracts.py",
        "python .\\scripts\\check_path_contracts.py",
        "python .\\scripts\\check_source_publication_contracts.py",
        "python .\\scripts\\check_restore_readiness.py",
        "python .\\scripts\\check_source_target_contracts.py",
        "python .\\scripts\\check_search_artifact_integrity.py",
        "Large generated files are ignored by Git",
    ],
    "reader_site/README.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "python .\\scripts\\rebuild_all.py",
        "python .\\scripts\\build_release_stage_manifest.py --check",
        "python .\\scripts\\check_clean_clone_contracts.py",
        "python .\\scripts\\check_ci_contracts.py",
        "python .\\scripts\\check_encoding_contracts.py",
        "python .\\scripts\\check_path_contracts.py",
        "python .\\scripts\\check_source_publication_contracts.py",
        "python .\\scripts\\check_restore_readiness.py",
        "python .\\scripts\\check_source_target_contracts.py",
        "python .\\scripts\\check_search_artifact_integrity.py",
        "Layout vocabulary is centralized",
    ],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=check,
        capture_output=True,
    )


def tracked_paths() -> list[str]:
    result = run_git("ls-files", "-z")
    raw_paths = result.stdout.split(b"\0")
    return [path.decode("utf-8", errors="surrogateescape").replace("\\", "/") for path in raw_paths if path]


def is_forbidden_tracked_path(path: str) -> bool:
    if any(path == source or path.startswith(f"{source}/") for source in SOURCE_DIRS):
        return True
    if any(fnmatch.fnmatch(path, pattern) for pattern in GENERATED_ARTIFACT_PATTERNS):
        return True
    if any(fnmatch.fnmatch(path, pattern) for pattern in LOCAL_STATE_PATTERNS):
        return path not in {"reader_site/data/notes/.gitkeep", "reader_site/data/ai/.gitkeep"}
    return False


def assert_git_available() -> None:
    require((REPO / ".git").exists(), "release contracts require a Git checkout")
    run_git("rev-parse", "--show-toplevel")


def assert_gitignore_policy() -> None:
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    for source in SOURCE_DIRS:
        require(f"{source}/" in gitignore, f".gitignore missing source corpus rule for {source}")
    for pattern in [*GENERATED_ARTIFACT_PATTERNS, *LOCAL_STATE_PATTERNS]:
        require(pattern in gitignore, f".gitignore missing rule for {pattern}")


def assert_ignored_existing_artifacts() -> None:
    existing_candidates = [REPO / source for source in SOURCE_DIRS]
    existing_candidates.extend(
        [
            SITE / "data" / "search_index.jsonl",
            SITE / "data" / "search_index.sqlite",
            SITE / "data" / "artifact_manifest.local.json",
            SITE / "data" / "release_stage_manifest.local.json",
            SITE / "data" / "visual_qa.local",
            SITE / "data" / "runtime.local",
            SITE / "data" / "ai" / "nietzsche_interpretations.jsonl",
            SITE / "data" / "ai" / "ai_interpretation_index.sqlite",
            SITE / "data" / "bible_segments.jsonl",
            SITE / "data" / "nietzsche_segments.jsonl",
            SITE / "data" / "kierkegaard_segments.jsonl",
            SITE / "data" / "wittgenstein_segments.jsonl",
        ]
    )
    for candidate in existing_candidates:
        if not candidate.exists():
            continue
        relative = repo_relative(candidate)
        result = run_git("check-ignore", "--quiet", "--", relative, check=False)
        require(result.returncode == 0, f"{relative} exists but is not ignored by Git")


def assert_no_forbidden_tracked_files(paths: list[str]) -> None:
    forbidden = sorted(path for path in paths if is_forbidden_tracked_path(path))
    require(not forbidden, "forbidden tracked release files: " + ", ".join(forbidden))


def assert_no_large_tracked_files(paths: list[str]) -> None:
    large_files: list[str] = []
    for path in paths:
        absolute = REPO / path
        if not absolute.is_file():
            continue
        if absolute.stat().st_size > MAX_TRACKED_FILE_BYTES:
            large_files.append(f"{path} ({absolute.stat().st_size} bytes)")
    require(not large_files, "large tracked files found: " + ", ".join(sorted(large_files)))


def assert_required_docs() -> None:
    for relative_path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = (REPO / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            require(snippet in text, f"{relative_path} missing release handoff snippet {snippet!r}")


def main() -> None:
    assert_git_available()
    paths = tracked_paths()
    assert_gitignore_policy()
    assert_ignored_existing_artifacts()
    assert_no_forbidden_tracked_files(paths)
    assert_no_large_tracked_files(paths)
    assert_required_docs()
    print("release contracts ok")


if __name__ == "__main__":
    main()
