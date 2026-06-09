from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent

SOURCE_ROOTS = [
    "니체_원서수집",
    "비트겐슈타인_원서수집",
    "성경_원서수집",
    "키르케고르_원서수집",
]

FORBIDDEN_CLEAN_CLONE_PATTERNS = [
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
    "reader_site/local_paths.json",
    ".env",
    ".env.*",
]

ALLOWED_LOCAL_STATE_KEEPERS = {
    "reader_site/data/notes/.gitkeep",
    "reader_site/data/ai/.gitkeep",
}

REQUIRED_FILES = [
    ".gitattributes",
    ".gitignore",
    "README.md",
    "reader_site/README.md",
    "reader_site/server.py",
    "reader_site/scripts/rebuild_all.py",
    "reader_site/scripts/check_clean_clone_contracts.py",
    "reader_site/scripts/check_encoding_contracts.py",
    "reader_site/scripts/check_release_contracts.py",
    "reader_site/docs/clean_clone_reproducibility.md",
    "reader_site/docs/encoding_policy.md",
    "reader_site/docs/release_handoff.md",
]

REQUIRED_DOC_SNIPPETS = {
    "README.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "python .\\scripts\\rebuild_all.py",
        "python .\\scripts\\check_clean_clone_contracts.py",
    ],
    "reader_site/README.md": [
        "docs/clean_clone_reproducibility.md",
        "python .\\scripts\\check_clean_clone_contracts.py",
    ],
    "reader_site/docs/release_handoff.md": [
        "python .\\scripts\\check_clean_clone_contracts.py",
        "docs/clean_clone_reproducibility.md",
    ],
    "reader_site/docs/clean_clone_reproducibility.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "--clone-smoke",
        "Source-Light Checks",
        "Full Restore",
    ],
}

SOURCE_LIGHT_COMMANDS = [
    [sys.executable, "-m", "compileall", "-q", "server.py", "runtime_status.py", "corpora", "rendering", "services", "scripts"],
    [sys.executable, "scripts/check_encoding_contracts.py"],
    [sys.executable, "scripts/check_release_contracts.py"],
    [sys.executable, "scripts/check_layout_contracts.py"],
    [sys.executable, "scripts/check_server_boundary.py"],
    [sys.executable, "scripts/check_provenance_contracts.py"],
    [sys.executable, "scripts/check_ai_records_contracts.py"],
    [sys.executable, "scripts/build_release_stage_manifest.py", "--check"],
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True)


def run_capture(command: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=cwd, check=check, capture_output=True)


def tracked_paths(repo: Path = REPO) -> list[str]:
    result = run_capture(["git", "ls-files", "-z"], cwd=repo)
    return [
        path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for path in result.stdout.split(b"\0")
        if path
    ]


def current_branch(repo: Path = REPO) -> str:
    result = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return result.stdout.decode("utf-8").strip()


def is_worktree_clean(repo: Path = REPO) -> bool:
    result = run_capture(["git", "status", "--porcelain=v1", "-uall"], cwd=repo)
    return not result.stdout.strip()


def is_forbidden_path(path: str) -> bool:
    if any(path == source or path.startswith(f"{source}/") for source in SOURCE_ROOTS):
        return True
    if any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_CLEAN_CLONE_PATTERNS):
        return path not in ALLOWED_LOCAL_STATE_KEEPERS
    return False


def check_required_files(repo: Path = REPO) -> None:
    for relative_path in REQUIRED_FILES:
        require((repo / relative_path).exists(), f"clean clone missing required file: {relative_path}")


def check_no_forbidden_tracked_files(repo: Path = REPO) -> None:
    forbidden = sorted(path for path in tracked_paths(repo) if is_forbidden_path(path))
    require(not forbidden, "clean clone would track forbidden files: " + ", ".join(forbidden))


def check_docs(repo: Path = REPO) -> None:
    for relative_path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = (repo / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            require(snippet in text, f"{relative_path} missing clean clone snippet {snippet!r}")


def check_clean_clone_contracts(repo: Path = REPO) -> None:
    require((repo / ".git").exists(), "clean clone contracts require a Git checkout")
    check_required_files(repo)
    check_no_forbidden_tracked_files(repo)
    check_docs(repo)


def run_source_light_checks(site: Path, empty_corpus_root: Path | None = None) -> None:
    env = os.environ.copy()
    pycache_root = Path(tempfile.gettempdir()) / "philo_archive_clean_clone_pycache"
    pycache_root.mkdir(parents=True, exist_ok=True)
    env["PYTHONPYCACHEPREFIX"] = str(pycache_root)
    if empty_corpus_root is not None:
        empty_corpus_root.mkdir(parents=True, exist_ok=True)
        env["PHILOSOPHY_CRAWL_ROOT"] = str(empty_corpus_root)
    for command in SOURCE_LIGHT_COMMANDS:
        run(command, cwd=site, env=env)


def clone_smoke(parent: Path, keep_clone: bool) -> None:
    require(is_worktree_clean(REPO), "commit or stash local changes before --clone-smoke")
    branch = current_branch(REPO)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / "philo_archive_clean_clone_smoke"
    empty_root = parent / "philo_archive_empty_corpus_root"
    if target.exists():
        shutil.rmtree(target)
    if empty_root.exists():
        shutil.rmtree(empty_root)

    try:
        run(["git", "clone", "--local", str(REPO), str(target)], cwd=parent)
        run(["git", "checkout", branch], cwd=target)
        for source in SOURCE_ROOTS:
            require(not (target / source).exists(), f"clean clone unexpectedly contains source corpus: {source}")
        check_clean_clone_contracts(target)
        run_source_light_checks(target / "reader_site", empty_root)
    finally:
        if not keep_clone:
            if target.exists():
                shutil.rmtree(target)
            if empty_root.exists():
                shutil.rmtree(empty_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate source-light clean clone reproducibility contracts.", allow_abbrev=False)
    parser.add_argument("--run-source-light-checks", action="store_true", help="Run checks that should pass without source corpora.")
    parser.add_argument("--clone-smoke", action="store_true", help="Create a real local clean clone and run source-light checks there.")
    parser.add_argument("--clone-parent", type=Path, default=REPO.parent, help="Parent folder for --clone-smoke temporary directories.")
    parser.add_argument("--keep-clone", action="store_true", help="Keep the temporary clone and empty corpus root after --clone-smoke.")
    args = parser.parse_args()

    check_clean_clone_contracts(REPO)
    if args.run_source_light_checks:
        run_source_light_checks(SITE)
    if args.clone_smoke:
        clone_smoke(args.clone_parent, args.keep_clone)
    print("clean clone contracts ok")


if __name__ == "__main__":
    main()
