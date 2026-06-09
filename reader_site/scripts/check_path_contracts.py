from __future__ import annotations

import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
SCRIPTS = SITE / "scripts"
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SCRIPTS))

import build_bible_metadata  # noqa: E402
import build_kierkegaard_metadata  # noqa: E402
import build_release_stage_manifest  # noqa: E402
import build_wittgenstein_metadata  # noqa: E402
import check_clean_clone_contracts  # noqa: E402
import check_encoding_contracts  # noqa: E402
import check_release_contracts  # noqa: E402
import check_source_publication_contracts  # noqa: E402
from corpora import catalogs  # noqa: E402
from path_config import PRIMARY_OUTPUTS, SOURCE_ROOT_NAMES  # noqa: E402
from runtime_status import CORPORA, ROOT  # noqa: E402
from services import sources  # noqa: E402


EXPECTED_SOURCE_ROOTS = set(SOURCE_ROOT_NAMES)
CENTRAL_PATH_CONFIG = SITE / "path_config.py"
PATH_CONTRACT = Path(__file__).resolve()
FORBIDDEN_DIRECT_ENV_SNIPPETS = (
    'os.environ.get("PHILOSOPHY_CRAWL_ROOT"',
    "os.environ.get('PHILOSOPHY_CRAWL_ROOT'",
    'os.getenv("PHILOSOPHY_CRAWL_ROOT"',
    "os.getenv('PHILOSOPHY_CRAWL_ROOT'",
    'Path(os.environ.get("PHILOSOPHY_CRAWL_ROOT"',
    "Path(os.environ.get('PHILOSOPHY_CRAWL_ROOT'",
)

EXPECTED_PRIMARY_OUTPUTS = {
    "nietzsche": catalogs.NIETZSCHE_OUTPUT,
    "bible": build_bible_metadata.BIBLE_OUTPUT,
    "kierkegaard": build_kierkegaard_metadata.KIERKEGAARD_TEXTS,
    "wittgenstein": build_wittgenstein_metadata.WITTGENSTEIN_OUTPUT,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def resolved(path: Path) -> Path:
    return path.resolve()


def require_name_set(label: str, values: list[str] | tuple[str, ...] | set[str]) -> None:
    actual = set(values)
    missing = sorted(EXPECTED_SOURCE_ROOTS - actual)
    unexpected = sorted(actual - EXPECTED_SOURCE_ROOTS)
    require(not missing, f"{label} missing source roots: {', '.join(missing)}")
    require(not unexpected, f"{label} has unexpected source roots: {', '.join(unexpected)}")


def check_source_root_vocabularies() -> None:
    require_name_set("services.sources.CORPUS_ROOTS", [path.name for path in sources.CORPUS_ROOTS])
    require_name_set("runtime_status.CORPORA", [Path(config["source_root"]).name for config in CORPORA])
    require_name_set("check_clean_clone_contracts.SOURCE_ROOTS", check_clean_clone_contracts.SOURCE_ROOTS)
    require_name_set("check_release_contracts.SOURCE_DIRS", check_release_contracts.SOURCE_DIRS)
    require_name_set("build_release_stage_manifest.SOURCE_DIRS", build_release_stage_manifest.SOURCE_DIRS)
    require_name_set(
        "check_source_publication_contracts.SOURCE_DIRS",
        check_source_publication_contracts.SOURCE_DIRS,
    )
    require_name_set("check_encoding_contracts.KOREAN_SOURCE_ROOTS", check_encoding_contracts.KOREAN_SOURCE_ROOTS)


def check_runtime_roots() -> None:
    for config in CORPORA:
        corpus_id = config["corpus_id"]
        source_root = Path(config["source_root"])
        require(resolved(source_root.parent) == resolved(ROOT), f"{corpus_id}: source root is not under ROOT")
        require(source_root.name in EXPECTED_SOURCE_ROOTS, f"{corpus_id}: unexpected source root {source_root.name}")


def check_primary_outputs() -> None:
    runtime_by_id = {config["corpus_id"]: Path(config["primary_output"]) for config in CORPORA}
    for corpus_id, builder_path in EXPECTED_PRIMARY_OUTPUTS.items():
        runtime_path = runtime_by_id.get(corpus_id)
        require(runtime_path is not None, f"{corpus_id}: missing runtime primary output")
        require(
            resolved(PRIMARY_OUTPUTS[corpus_id]) == resolved(builder_path),
            f"{corpus_id}: centralized primary output differs from builder path",
        )
        require(
            resolved(runtime_path) == resolved(builder_path),
            f"{corpus_id}: runtime primary output differs from builder path",
        )


def python_files() -> list[Path]:
    return sorted(
        path
        for path in SITE.rglob("*.py")
        if "__pycache__" not in path.parts and ".pytest_tmp" not in path.parts
    )


def check_no_direct_path_redefinitions() -> None:
    direct_root_failures: list[str] = []
    direct_env_failures: list[str] = []
    for path in python_files():
        if path.resolve() in {CENTRAL_PATH_CONFIG.resolve(), PATH_CONTRACT}:
            continue
        relative = path.relative_to(SITE).as_posix()
        source = path.read_text(encoding="utf-8")
        for root_name in SOURCE_ROOT_NAMES:
            if f'"{root_name}"' in source or f"'{root_name}'" in source:
                direct_root_failures.append(f"{relative}: {root_name}")
        for snippet in FORBIDDEN_DIRECT_ENV_SNIPPETS:
            if snippet in source:
                direct_env_failures.append(f"{relative}: {snippet}")
    require(
        not direct_root_failures,
        "source root names must be imported from path_config.py: " + ", ".join(direct_root_failures),
    )
    require(
        not direct_env_failures,
        "PHILOSOPHY_CRAWL_ROOT must be read through path_config.py: " + ", ".join(direct_env_failures),
    )


def main() -> None:
    check_source_root_vocabularies()
    check_runtime_roots()
    check_primary_outputs()
    check_no_direct_path_redefinitions()
    print("path contracts ok")


if __name__ == "__main__":
    main()
