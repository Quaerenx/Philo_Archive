from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
DEFAULT_PATH = SITE / "data" / "translation_quality_goldset.json"
REQUIRED_CORPORA = {"bible", "kierkegaard", "nietzsche", "wittgenstein"}
REQUIRED_DIMENSIONS = {"fidelity", "completeness", "terminology", "korean_readability"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_text(value: Any, label: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be a non-empty string")


def require_iso_timestamp(value: Any, label: str) -> None:
    require_text(value, label)
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise AssertionError(f"{label} must be an ISO-8601 timestamp") from error


def validate(path: Path, require_complete: bool = False) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == 1, "unsupported goldset schema_version")
    rubric = payload.get("rubric")
    require(isinstance(rubric, dict), "rubric must be an object")
    dimensions = rubric.get("dimensions")
    require(isinstance(dimensions, dict), "rubric.dimensions must be an object")
    require(set(dimensions) == REQUIRED_DIMENSIONS, "rubric dimensions are incomplete")
    score_scale = rubric.get("scale")
    require(score_scale == {"min": 1, "max": 5}, "rubric score scale must be 1 through 5")
    passing_score = rubric.get("passing_score_per_dimension")
    require(isinstance(passing_score, int) and 1 <= passing_score <= 5, "invalid passing score")

    cases = payload.get("cases")
    require(isinstance(cases, list) and bool(cases), "cases must be a non-empty list")
    seen_ids: set[str] = set()
    covered_corpora: set[str] = set()
    evaluated: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        label = f"case {index}"
        require(isinstance(case, dict), f"{label} must be an object")
        for field in ("id", "corpus_id", "work_id", "segment_id", "sentence_id", "source_text", "candidate_translation"):
            require_text(case.get(field), f"{label}.{field}")
        require(case["id"] not in seen_ids, f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        covered_corpora.add(case["corpus_id"])
        evaluation = case.get("human_evaluation")
        require(isinstance(evaluation, dict), f"{label}.human_evaluation must be an object")
        status = evaluation.get("status")
        require(status in {"pending", "evaluated"}, f"{label} has an invalid evaluation status")
        if status == "pending":
            require(not str(case.get("reference_translation") or "").strip(), f"{label} pending reference must be empty")
            require(not evaluation.get("scores"), f"{label} pending scores must be empty")
            pending.append(case)
            continue
        require_text(case.get("reference_translation"), f"{label}.reference_translation")
        require_text(evaluation.get("evaluator"), f"{label}.human_evaluation.evaluator")
        require_iso_timestamp(evaluation.get("evaluated_at"), f"{label}.human_evaluation.evaluated_at")
        scores = evaluation.get("scores")
        require(isinstance(scores, dict) and set(scores) == REQUIRED_DIMENSIONS, f"{label} scores are incomplete")
        for dimension, score in scores.items():
            require(isinstance(score, int) and 1 <= score <= 5, f"{label}.{dimension} score must be 1 through 5")
        require(isinstance(evaluation.get("notes"), str), f"{label}.human_evaluation.notes must be a string")
        evaluated.append(case)

    require(covered_corpora == REQUIRED_CORPORA, "goldset must cover every supported corpus")
    if require_complete:
        require(not pending, f"{len(pending)} goldset cases still need human evaluation")

    dimension_means = {
        dimension: round(sum(case["human_evaluation"]["scores"][dimension] for case in evaluated) / len(evaluated), 2)
        for dimension in sorted(REQUIRED_DIMENSIONS)
    } if evaluated else {}
    passing_cases = sum(
        all(score >= passing_score for score in case["human_evaluation"]["scores"].values())
        for case in evaluated
    )
    return {
        "total": len(cases),
        "evaluated": len(evaluated),
        "pending": len(pending),
        "passing": passing_cases,
        "dimension_means": dimension_means,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and summarize the human translation goldset.")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    summary = validate(args.path, require_complete=args.require_complete)
    print(
        "translation goldset ok: "
        f"{summary['evaluated']}/{summary['total']} evaluated, "
        f"{summary['pending']} pending, {summary['passing']} passing"
    )
    if summary["dimension_means"]:
        print("dimension means: " + json.dumps(summary["dimension_means"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
