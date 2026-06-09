from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from runtime_status import SEARCH_INDEX, build_runtime_health  # noqa: E402


EXPECTED_CORPORA = {"nietzsche", "bible", "kierkegaard", "wittgenstein"}


def fail(message: str) -> None:
    raise AssertionError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def positive_file(record: dict[str, Any], label: str) -> None:
    require(record.get("exists") is True, f"{label} is missing")
    require(int(record.get("bytes") or 0) > 0, f"{label} is empty")


def check_corpus(corpus: dict[str, Any]) -> None:
    corpus_id = str(corpus.get("corpus_id", ""))
    require(corpus_id in EXPECTED_CORPORA, f"unexpected corpus in readiness payload: {corpus_id}")
    require(corpus.get("source_root_exists") is True, f"{corpus_id}: source root is missing")
    require(corpus.get("primary_output_exists") is True, f"{corpus_id}: primary output folder is missing")
    require(not corpus.get("metadata_error"), f"{corpus_id}: metadata parse error: {corpus.get('metadata_error')}")
    require(int(corpus.get("work_count") or 0) > 0, f"{corpus_id}: no works in metadata")
    positive_file(corpus.get("metadata") or {}, f"{corpus_id}: metadata")
    positive_file(corpus.get("segments") or {}, f"{corpus_id}: segment artifact")


def check_search(payload: dict[str, Any], allow_degraded_search: bool) -> None:
    search = payload.get("search") or {}
    positive_file(search, "search sqlite database")
    require(int(search.get("records") or 0) > 0, "search sqlite database has no records")

    by_corpus = search.get("by_corpus") or {}
    missing = sorted(EXPECTED_CORPORA - set(by_corpus))
    require(not missing, "search sqlite database missing corpus records: " + ", ".join(missing))
    for corpus_id in sorted(EXPECTED_CORPORA):
        require(int(by_corpus.get(corpus_id) or 0) > 0, f"search sqlite database has no {corpus_id} records")

    require(SEARCH_INDEX.exists(), "portable search index is missing")
    require(SEARCH_INDEX.stat().st_size > 0, "portable search index is empty")

    if not allow_degraded_search:
        require(search.get("fts5") is True, "search sqlite database is missing FTS5")


def check_restore_readiness(allow_degraded_search: bool = False) -> dict[str, Any]:
    payload = build_runtime_health()
    corpora = payload.get("corpora") or []
    seen = {str(corpus.get("corpus_id", "")) for corpus in corpora}
    missing = sorted(EXPECTED_CORPORA - seen)
    require(not missing, "readiness payload missing corpora: " + ", ".join(missing))
    for corpus in corpora:
        check_corpus(corpus)
    check_search(payload, allow_degraded_search)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify that a restored local clone has source corpora and generated reader artifacts.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--allow-degraded-search",
        action="store_true",
        help="Allow a search database without FTS5. Source and artifact checks still remain strict.",
    )
    args = parser.parse_args()

    payload = check_restore_readiness(allow_degraded_search=args.allow_degraded_search)
    search = payload["search"]
    print(
        "restore readiness ok "
        f"({len(payload['corpora'])} corpora, {search.get('records', 0)} search records, fts5={search.get('fts5')})"
    )


if __name__ == "__main__":
    main()
