from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
CASES_PATH = SITE / "data" / "translation_regression_cases.json"
sys.path.insert(0, str(SITE))

from services.sentence_targets import sentence_target_bundle  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    CRITIC_CATEGORIES,
    build_critic_prompt_bundle,
    build_sentence_prompt_bundle,
    call_critic_server,
    merge_approved_policy_audit,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == 2, "translation regression schema_version must be 2")
    cases = payload.get("cases")
    require(isinstance(cases, list) and cases, "translation regression cases must be a non-empty list")
    return cases


def validate_case(case: dict[str, Any], *, with_model: bool) -> None:
    case_id = str(case.get("case_id", ""))
    require(case_id, "translation regression case_id is required")
    target = sentence_target_bundle(
        str(case["corpus_id"]),
        str(case["work_id"]),
        str(case["segment_id"]),
        str(case["sentence_id"]),
        str(case.get("variant_id", "")),
    )
    source_text = str(target["sentence_text"])
    feature_groups = case.get("source_features")
    require(isinstance(feature_groups, dict) and feature_groups, f"{case_id}: source_features are required")
    for feature, spans in feature_groups.items():
        require(isinstance(spans, list) and spans, f"{case_id}: {feature} spans are required")
        for span in spans:
            require(isinstance(span, str) and span in source_text, f"{case_id}: source feature missing: {span}")

    bad_translation = str(case.get("known_bad_translation", ""))
    bad_fragments = case.get("known_bad_fragments")
    require(bad_translation, f"{case_id}: known_bad_translation is required")
    require(isinstance(bad_fragments, list) and bad_fragments, f"{case_id}: known bad fragments are required")
    require(
        all(isinstance(fragment, str) and fragment and fragment in bad_translation for fragment in bad_fragments),
        f"{case_id}: known bad translation must contain every bad fragment",
    )
    expected_categories = set(case.get("expected_categories", []))
    require(expected_categories, f"{case_id}: expected critic categories are required")
    require(
        expected_categories <= set(CRITIC_CATEGORIES),
        f"{case_id}: expected critic category is unknown",
    )
    require(isinstance(case.get("require_major_issue"), bool), f"{case_id}: require_major_issue must be boolean")

    prompt_bundle = build_sentence_prompt_bundle(target)
    critic_bundle = build_critic_prompt_bundle(prompt_bundle, bad_translation)
    require(bad_translation in critic_bundle["prompt"], f"{case_id}: critic prompt missing known bad translation")
    require(source_text in critic_bundle["prompt"], f"{case_id}: critic prompt missing target sentence")
    if not with_model:
        return

    critic = merge_approved_policy_audit(
        prompt_bundle,
        bad_translation,
        call_critic_server(critic_bundle),
    )
    print(
        f"{case_id}: "
        + json.dumps(
            {
                "verdict": critic["verdict"],
                "issues": [
                    {"category": issue["category"], "severity": issue["severity"]}
                    for issue in critic["issues"]
                ],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    require(critic["verdict"] == "revise", f"{case_id}: critic failed to reject known bad translation")
    issues = list(critic["issues"])
    require(issues, f"{case_id}: critic rejected the draft without reporting an issue")
    if case["require_major_issue"]:
        require(any(issue["severity"] == "major" for issue in issues), f"{case_id}: critic did not report a major issue")
    require(
        any(issue["category"] in expected_categories for issue in issues),
        f"{case_id}: critic issue used an unexpected category",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate permanent sentence translation quality regressions.", allow_abbrev=False)
    parser.add_argument("--with-model", action="store_true", help="Also ask the local Gemma critic to reject each known-bad translation.")
    parser.add_argument("--case-id", help="Run one tracked regression case by exact id.")
    args = parser.parse_args()
    cases = load_cases()
    if args.case_id:
        cases = [case for case in cases if case["case_id"] == args.case_id]
        require(cases, f"unknown translation regression case: {args.case_id}")
    for case in cases:
        validate_case(case, with_model=args.with_model)
    suffix = " with local model" if args.with_model else ""
    print(f"translation quality regressions ok ({len(cases)} case(s){suffix})")


if __name__ == "__main__":
    main()
