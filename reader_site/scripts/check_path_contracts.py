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
from runtime_status import CORPORA, ROOT  # noqa: E402
from services import sources  # noqa: E402


EXPECTED_SOURCE_ROOTS = {
    "니체_원서수집",
    "비트겐슈타인_원서수집",
    "성경_원서수집",
    "키르케고르_원서수집",
}

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
            resolved(runtime_path) == resolved(builder_path),
            f"{corpus_id}: runtime primary output differs from builder path",
        )


def main() -> None:
    check_source_root_vocabularies()
    check_runtime_roots()
    check_primary_outputs()
    print("path contracts ok")


if __name__ == "__main__":
    main()
