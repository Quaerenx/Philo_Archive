from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
SCRIPTS = SITE / "scripts"
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SCRIPTS))

from path_config import SOURCE_ROOT_NAMES  # noqa: E402
import rebuild_all  # noqa: E402

SOURCE_ROOTS = list(SOURCE_ROOT_NAMES)

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
    ".github/workflows/reader-site-source-light.yml",
    "README.md",
    "reader_site/README.md",
    "reader_site/path_config.py",
    "reader_site/server.py",
    "reader_site/scripts/rebuild_all.py",
    "reader_site/scripts/check_clean_clone_contracts.py",
    "reader_site/scripts/check_ci_contracts.py",
    "reader_site/scripts/check_encoding_contracts.py",
    "reader_site/scripts/check_release_contracts.py",
    "reader_site/scripts/check_path_contracts.py",
    "reader_site/scripts/check_source_publication_contracts.py",
    "reader_site/scripts/check_prompt_template_contracts.py",
    "reader_site/scripts/check_source_target_contracts.py",
    "reader_site/scripts/check_restore_readiness.py",
    "reader_site/scripts/check_search_artifact_integrity.py",
    "reader_site/scripts/check_note_target_integrity.py",
    "reader_site/data/ai_prompt_templates.json",
    "reader_site/services/interpretation_prompts.py",
    "reader_site/services/source_targets.py",
    "reader_site/docs/clean_clone_reproducibility.md",
    "reader_site/docs/encoding_policy.md",
    "reader_site/docs/release_handoff.md",
    "reader_site/docs/source_publication_policy.md",
]

REQUIRED_DOC_SNIPPETS = {
    "README.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "python .\\scripts\\rebuild_all.py",
        "python .\\scripts\\check_clean_clone_contracts.py",
        "--run-source-light-checks",
        "python .\\scripts\\check_ci_contracts.py",
        "python .\\scripts\\check_source_publication_contracts.py",
        ".github/workflows/reader-site-source-light.yml",
    ],
    "reader_site/README.md": [
        "docs/clean_clone_reproducibility.md",
        "python .\\scripts\\check_clean_clone_contracts.py",
        "--run-source-light-checks",
        "python .\\scripts\\check_ci_contracts.py",
        "python .\\scripts\\check_source_publication_contracts.py",
        ".github/workflows/reader-site-source-light.yml",
    ],
    "reader_site/docs/release_handoff.md": [
        "python .\\scripts\\check_clean_clone_contracts.py",
        "python .\\scripts\\check_ci_contracts.py",
        "python .\\scripts\\check_source_publication_contracts.py",
        "docs/clean_clone_reproducibility.md",
        "docs/source_publication_policy.md",
        ".github/workflows/reader-site-source-light.yml",
    ],
    "reader_site/docs/clean_clone_reproducibility.md": [
        "PHILOSOPHY_CRAWL_ROOT",
        "--clone-smoke",
        ".github/workflows/reader-site-source-light.yml",
        "Source-Light Checks",
        "Full Restore",
    ],
}

SOURCE_LIGHT_COMMAND_DOCS = {
    "reader_site/docs/clean_clone_reproducibility.md": "The exact source-light command set is:",
}

REBUILD_SEQUENCE_DOCS = {
    "README.md": "The explicit rebuild sequence is:",
    "reader_site/README.md": "The explicit command sequence is:",
}

SOURCE_ROOT_DOC_REFERENCES = {
    "README.md": lambda root: f"{root}/",
    "reader_site/docs/clean_clone_reproducibility.md": lambda root: f"`{root}`",
    "reader_site/docs/release_handoff.md": lambda root: f"`{root}/`",
}

FORBIDDEN_SOURCE_LIGHT_SCRIPTS = {
    step.script for step in rebuild_all.BUILD_STEPS
} | {
    "build_search_db.py",
    "check_api_contracts.py",
    "check_corpus_schema.py",
    "check_notes_contracts.py",
    "check_note_target_integrity.py",
    "check_restore_readiness.py",
    "check_search_artifact_integrity.py",
    "check_search_contracts.py",
    "check_search_relevance.py",
    "check_source_target_contracts.py",
    "check_static_routes.py",
    "check_visual_smoke.py",
}

SOURCE_LIGHT_COMMANDS = [
    [sys.executable, "-m", "compileall", "-q", "server.py", "runtime_status.py", "corpora", "rendering", "services", "scripts"],
    [sys.executable, "scripts/check_ci_contracts.py"],
    [sys.executable, "scripts/check_encoding_contracts.py"],
    [sys.executable, "scripts/check_path_contracts.py"],
    [sys.executable, "scripts/check_source_publication_contracts.py"],
    [sys.executable, "scripts/check_release_contracts.py"],
    [sys.executable, "scripts/check_layout_contracts.py"],
    [sys.executable, "scripts/check_server_boundary.py"],
    [sys.executable, "scripts/check_provenance_contracts.py"],
    [sys.executable, "scripts/check_prompt_template_contracts.py"],
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
    tracked = set(tracked_paths(repo))
    for relative_path in REQUIRED_FILES:
        require((repo / relative_path).exists(), f"clean clone missing required file: {relative_path}")
        require(relative_path in tracked, f"clean clone required file is not tracked: {relative_path}")


def check_no_forbidden_tracked_files(repo: Path = REPO) -> None:
    forbidden = sorted(path for path in tracked_paths(repo) if is_forbidden_path(path))
    require(not forbidden, "clean clone would track forbidden files: " + ", ".join(forbidden))


def check_docs(repo: Path = REPO) -> None:
    for relative_path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = (repo / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            require(snippet in text, f"{relative_path} missing clean clone snippet {snippet!r}")


def expected_rebuild_commands() -> list[str]:
    return [
        f"python .\\scripts\\{step.script}"
        for step in rebuild_all.BUILD_STEPS
    ] + ["python .\\scripts\\build_artifact_manifest.py"]


def extract_powershell_block_after(text: str, marker: str, relative_path: str) -> str:
    marker_index = text.find(marker)
    require(marker_index >= 0, f"{relative_path} missing rebuild sequence marker {marker!r}")
    block_start = text.find("```powershell", marker_index)
    require(block_start >= 0, f"{relative_path} missing rebuild sequence powershell block")
    block_start = text.find("\n", block_start)
    require(block_start >= 0, f"{relative_path} has malformed rebuild sequence block")
    block_end = text.find("```", block_start + 1)
    require(block_end >= 0, f"{relative_path} has unterminated rebuild sequence block")
    return text[block_start + 1 : block_end]


def check_rebuild_sequence_docs(repo: Path = REPO) -> None:
    expected = expected_rebuild_commands()
    for relative_path, marker in REBUILD_SEQUENCE_DOCS.items():
        text = (repo / relative_path).read_text(encoding="utf-8")
        block = extract_powershell_block_after(text, marker, relative_path)
        actual = [
            line.strip()
            for line in block.splitlines()
            if line.strip().startswith("python .\\scripts\\")
        ]
        require(
            actual == expected,
            f"{relative_path} rebuild sequence differs from scripts/rebuild_all.py",
        )


def source_light_command_doc_lines() -> list[str]:
    lines: list[str] = []
    for command in SOURCE_LIGHT_COMMANDS:
        display_parts = ["python"]
        for part in command[1:]:
            if part.startswith("scripts/"):
                display_parts.append(".\\" + part.replace("/", "\\"))
            elif part in {"server.py", "runtime_status.py", "corpora", "rendering", "services", "scripts"}:
                display_parts.append(".\\" + part)
            else:
                display_parts.append(part.replace("/", "\\"))
        lines.append(" ".join(display_parts))
    return lines


def check_source_light_command_docs(repo: Path = REPO) -> None:
    expected = source_light_command_doc_lines()
    for relative_path, marker in SOURCE_LIGHT_COMMAND_DOCS.items():
        text = (repo / relative_path).read_text(encoding="utf-8")
        block = extract_powershell_block_after(text, marker, relative_path)
        actual = [
            line.strip()
            for line in block.splitlines()
            if line.strip().startswith("python")
        ]
        require(
            actual == expected,
            f"{relative_path} source-light command set differs from check_clean_clone_contracts.py",
        )


def check_source_root_docs(repo: Path = REPO) -> None:
    for relative_path, formatter in SOURCE_ROOT_DOC_REFERENCES.items():
        text = (repo / relative_path).read_text(encoding="utf-8")
        for root in SOURCE_ROOTS:
            expected = formatter(root)
            require(expected in text, f"{relative_path} missing source root reference {expected!r}")


def check_source_light_commands() -> None:
    failures: list[str] = []
    for command in SOURCE_LIGHT_COMMANDS:
        if len(command) < 2:
            continue
        script = Path(command[1]).name
        if script in FORBIDDEN_SOURCE_LIGHT_SCRIPTS:
            failures.append(" ".join(command))
    require(
        not failures,
        "source-light clean clone commands must not require local source artifacts: " + "; ".join(failures),
    )


def check_clean_clone_contracts(repo: Path = REPO) -> None:
    require((repo / ".git").exists(), "clean clone contracts require a Git checkout")
    check_required_files(repo)
    check_no_forbidden_tracked_files(repo)
    check_docs(repo)
    check_source_root_docs(repo)
    check_rebuild_sequence_docs(repo)
    check_source_light_command_docs(repo)
    check_source_light_commands()


def run_source_light_checks(site: Path, empty_corpus_root: Path | None = None) -> None:
    env = os.environ.copy()
    pycache_root = Path(tempfile.gettempdir()) / "philo_archive_clean_clone_pycache"
    pycache_root.mkdir(parents=True, exist_ok=True)
    env["PYTHONPYCACHEPREFIX"] = str(pycache_root)
    cleanup_root: Path | None = None
    if empty_corpus_root is None:
        cleanup_root = Path(tempfile.mkdtemp(prefix="philo_archive_empty_corpus_root_"))
        empty_corpus_root = cleanup_root
    empty_corpus_root.mkdir(parents=True, exist_ok=True)
    env["PHILOSOPHY_CRAWL_ROOT"] = str(empty_corpus_root)
    try:
        for command in SOURCE_LIGHT_COMMANDS:
            run(command, cwd=site, env=env)
    finally:
        if cleanup_root is not None:
            remove_tree(cleanup_root)


def remove_tree(path: Path) -> None:
    def clear_readonly(func, target, exc_info) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=clear_readonly)


def clone_smoke(parent: Path, keep_clone: bool) -> None:
    require(is_worktree_clean(REPO), "commit or stash local changes before --clone-smoke")
    branch = current_branch(REPO)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / "philo_archive_clean_clone_smoke"
    empty_root = parent / "philo_archive_empty_corpus_root"
    remove_tree(target)
    remove_tree(empty_root)

    try:
        run(["git", "clone", "--local", str(REPO), str(target)], cwd=parent)
        run(["git", "checkout", branch], cwd=target)
        for source in SOURCE_ROOTS:
            require(not (target / source).exists(), f"clean clone unexpectedly contains source corpus: {source}")
        check_clean_clone_contracts(target)
        run_source_light_checks(target / "reader_site", empty_root)
    finally:
        if not keep_clone:
            remove_tree(target)
            remove_tree(empty_root)


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
