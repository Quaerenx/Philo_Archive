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
    seen_ids: set[str] = set()
    for index, case in enumerate(payload, start=1):
        require(isinstance(case, dict), f"search evaluation case {index} must be an object")
        case_id = str(case.get("id", "")).strip()
        require(case_id, f"search evaluation case {index} requires id")
        require(case_id not in seen_ids, f"duplicate search evaluation id: {case_id}")
        seen_ids.add(case_id)
        require(str(case.get("query", "")).strip(), f"{case_id}: query is required")
        for rank_key in ("expected_work_rank_max", "expected_segment_rank_max"):
            if rank_key in case:
                require(int(case[rank_key]) > 0, f"{case_id}: {rank_key} must be positive")
        if "limit" in case:
            require(int(case["limit"]) > 0, f"{case_id}: limit must be positive")
        require(
            any(
                case.get(key)
                for key in (
                    "expected_work_id",
                    "expected_segment_id",
                    "expected_segment_work_id",
                    "expected_top_corpus_id",
                    "expected_snippet_contains",
                )
            ),
            f"{case_id}: at least one result expectation is required",
        )
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


def first_text_rank(items: list[dict[str, Any]], needle: str) -> int | None:
    for index, item in enumerate(items, start=1):
        if needle in combined_result_text(item):
            return index
    return None


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id") or case.get("query") or "<unnamed>")
    query = str(case.get("query", ""))
    payload = search_records(
        query,
        corpus_id=str(case.get("corpus_id", "")),
        work_id=str(case.get("work_id", "")),
        variant_id=str(case.get("variant_id", "")),
        limit=int(case.get("limit", 10)),
    )
    errors: list[str] = []
    if case.get("expected_engine"):
        if payload.get("engine") != case["expected_engine"]:
            errors.append(f"expected engine {case['expected_engine']}, got {payload.get('engine')}")

    work_results = payload.get("work_results", [])
    target_kind = ""
    target_rank: int | None = None
    if case.get("expected_work_id"):
        target_kind = "work"
        target_rank = find_rank(work_results, work_id=str(case["expected_work_id"]))
        max_rank = int(case.get("expected_work_rank_max", 3))
        if target_rank is None or target_rank > max_rank:
            errors.append(f"expected work {case['expected_work_id']} in top {max_rank}, got rank {target_rank}")

    results = payload.get("results", [])
    if case.get("expected_segment_id") or case.get("expected_segment_work_id"):
        if not target_kind:
            target_kind = "segment"
        expected: dict[str, str] = {}
        if case.get("expected_segment_id"):
            expected["segment_id"] = str(case["expected_segment_id"])
        if case.get("expected_segment_work_id"):
            expected["work_id"] = str(case["expected_segment_work_id"])
        if case.get("expected_segment_variant_id"):
            expected["variant_id"] = str(case["expected_segment_variant_id"])
        rank = find_rank(results, **expected)
        if target_kind == "segment":
            target_rank = rank
        max_rank = int(case.get("expected_segment_rank_max", 3))
        if rank is None or rank > max_rank:
            errors.append(f"expected segment {expected} in top {max_rank}, got rank {rank}")

    if case.get("expected_top_corpus_id"):
        expected_corpus = str(case["expected_top_corpus_id"])
        corpus_rank = find_rank(results, corpus_id=expected_corpus)
        if not target_kind:
            target_kind = "corpus"
            target_rank = corpus_rank
        if not results:
            errors.append("expected segment results")
        elif results[0].get("corpus_id") != expected_corpus:
            errors.append(f"expected top corpus {expected_corpus}, got {results[0].get('corpus_id')}")

    if case.get("expected_snippet_contains"):
        needle = str(case["expected_snippet_contains"]).lower()
        text_rank = first_text_rank(results, needle)
        if not target_kind:
            target_kind = "text"
            target_rank = text_rank
        if not results:
            errors.append("expected segment results")
        elif text_rank != 1:
            errors.append(f"top result does not expose {needle!r}")

    return {
        "id": case_id,
        "query": query,
        "passed": not errors,
        "target_kind": target_kind,
        "rank": target_rank,
        "engine": payload.get("engine", ""),
        "errors": errors,
    }


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_case(case) for case in cases]
    judged = [result for result in results if result["target_kind"]]
    reciprocal_rank_total = sum(1 / result["rank"] for result in judged if result["rank"])

    def recall_at(limit: int) -> float:
        if not judged:
            return 0.0
        return sum(1 for result in judged if result["rank"] and result["rank"] <= limit) / len(judged)

    return {
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["passed"]),
        "failed_count": sum(1 for result in results if not result["passed"]),
        "judged_count": len(judged),
        "mrr": round(reciprocal_rank_total / len(judged), 6) if judged else 0.0,
        "recall_at_1": round(recall_at(1), 6),
        "recall_at_3": round(recall_at(3), 6),
        "recall_at_10": round(recall_at(10), 6),
        "cases": results,
    }


def print_text_report(report: dict[str, Any]) -> None:
    status = "ok" if report["failed_count"] == 0 else "failed"
    print(
        "search relevance "
        f"{status} ({report['passed_count']}/{report['case_count']} cases; "
        f"MRR={report['mrr']:.4f}; "
        f"R@1={report['recall_at_1']:.4f}; "
        f"R@3={report['recall_at_3']:.4f}; "
        f"R@10={report['recall_at_10']:.4f})"
    )
    for result in report["cases"]:
        if result["passed"]:
            continue
        print(f"- {result['id']}: {'; '.join(result['errors'])}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Check representative search relevance queries.", allow_abbrev=False)
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    cases = load_cases(args.query_file)
    report = evaluate_cases(cases)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    if report["failed_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
