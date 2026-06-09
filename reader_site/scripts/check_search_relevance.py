from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"
DEFAULT_QUERY_FILE = DATA / "search_eval_queries.json"
sys.path.insert(0, str(SITE))

from services.search import search_records  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_cases(path: Path) -> list[dict[str, Any]]:
    require(path.exists(), f"missing search evaluation query file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, list), "search evaluation query file must contain a JSON array")
    return payload


def find_rank(items: list[dict[str, Any]], **expected: str) -> int | None:
    for index, item in enumerate(items, start=1):
        if all(str(item.get(key, "")) == value for key, value in expected.items()):
            return index
    return None


def combined_result_text(item: dict[str, Any]) -> str:
    values = [
        item.get("label", ""),
        item.get("title", ""),
        item.get("snippet", ""),
        item.get("text", ""),
    ]
    return " ".join(str(value) for value in values if value).lower()


def check_case(case: dict[str, Any]) -> None:
    case_id = str(case.get("id") or case.get("query") or "<unnamed>")
    query = str(case.get("query", ""))
    require(query, f"{case_id}: query is required")

    payload = search_records(
        query,
        corpus_id=str(case.get("corpus_id", "")),
        work_id=str(case.get("work_id", "")),
        variant_id=str(case.get("variant_id", "")),
        limit=int(case.get("limit", 10)),
    )
    if case.get("expected_engine"):
        require(
            payload.get("engine") == case["expected_engine"],
            f"{case_id}: expected engine {case['expected_engine']}, got {payload.get('engine')}",
        )

    work_results = payload.get("work_results", [])
    if case.get("expected_work_id"):
        rank = find_rank(work_results, work_id=str(case["expected_work_id"]))
        max_rank = int(case.get("expected_work_rank_max", 3))
        require(rank is not None and rank <= max_rank, f"{case_id}: expected work {case['expected_work_id']} in top {max_rank}")

    results = payload.get("results", [])
    if case.get("expected_segment_id") or case.get("expected_segment_work_id"):
        expected: dict[str, str] = {}
        if case.get("expected_segment_id"):
            expected["segment_id"] = str(case["expected_segment_id"])
        if case.get("expected_segment_work_id"):
            expected["work_id"] = str(case["expected_segment_work_id"])
        rank = find_rank(results, **expected)
        max_rank = int(case.get("expected_segment_rank_max", 3))
        require(rank is not None and rank <= max_rank, f"{case_id}: expected segment {expected} in top {max_rank}")

    if case.get("expected_top_corpus_id"):
        require(results, f"{case_id}: expected segment results")
        require(
            results[0].get("corpus_id") == case["expected_top_corpus_id"],
            f"{case_id}: expected top corpus {case['expected_top_corpus_id']}, got {results[0].get('corpus_id')}",
        )

    if case.get("expected_snippet_contains"):
        require(results, f"{case_id}: expected segment results")
        needle = str(case["expected_snippet_contains"]).lower()
        require(needle in combined_result_text(results[0]), f"{case_id}: top result does not expose {needle!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check representative search relevance queries.", allow_abbrev=False)
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    args = parser.parse_args()

    cases = load_cases(args.query_file)
    for case in cases:
        check_case(case)
    print(f"search relevance ok ({len(cases)} cases)")


if __name__ == "__main__":
    main()
