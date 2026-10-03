from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


SITE = Path(__file__).resolve().parents[1]
CASES_PATH = SITE / "data" / "translation_regression_cases.json"
GOLDSET_PATH = SITE / "data" / "translation_quality_goldset.json"
REPORT_ROOT = SITE / "data" / "runtime.local"
sys.path.insert(0, str(SITE))

from services.sentence_targets import sentence_target_bundle  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    CRITIC_CATEGORIES,
    build_critic_prompt_bundle,
    build_sentence_prompt_bundle,
    call_critic_server,
    merge_approved_policy_audit,
)
from services.source_targets import sha256_text  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == 2, "translation regression schema_version must be 2")
    cases = payload.get("cases")
    require(isinstance(cases, list) and cases, "translation regression cases must be a non-empty list")
    superseded = payload.get("superseded_cases", [])
    require(isinstance(superseded, list), "superseded regression cases must be a list")
    active_ids = {case.get("case_id") for case in cases}
    retired_ids = set()
    for entry in superseded:
        require(isinstance(entry, dict) and isinstance(entry.get("case"), dict), "invalid superseded regression case")
        identifier = entry["case"].get("case_id")
        require(isinstance(identifier, str) and identifier and identifier not in active_ids and identifier not in retired_ids, "superseded regression case is still active or duplicated")
        require(bool(entry.get("reason")) and bool(entry.get("evidence_url")) and bool(entry.get("retired_date")), "superseded regression case needs evidence")
        retired_ids.add(identifier)
    return cases


def prepare_bad_case(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
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
    return prompt_bundle, critic_bundle


def validate_case(case: dict[str, Any], *, with_model: bool) -> None:
    prompt_bundle, critic_bundle = prepare_bad_case(case)
    if not with_model:
        return

    case_id = str(case["case_id"])
    critic = merge_approved_policy_audit(
        prompt_bundle,
        str(case["known_bad_translation"]),
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
        any(issue["category"] in set(case["expected_categories"]) for issue in issues),
        f"{case_id}: critic issue used an unexpected category",
    )


def load_reference_cases() -> list[dict[str, Any]]:
    from scripts.check_translation_goldset import validate

    validate(GOLDSET_PATH)
    payload = json.loads(GOLDSET_PATH.read_text(encoding="utf-8"))
    return [
        case for case in payload["cases"]
        if case["human_evaluation"]["status"] == "evaluated"
        and str(case.get("reference_translation", "")).strip()
    ]


def balanced_samples(bad_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples = [
        {"case_id": case["case_id"], "kind": "known_bad", "expected_verdict": "revise", "case": case}
        for case in bad_cases
    ]
    samples.extend(
        {
            "case_id": case["id"],
            "sample_label": case.get("sample_label", ""),
            "kind": "human_reference",
            "expected_verdict": "pass",
            "case": case,
        }
        for case in load_reference_cases()
    )
    return samples


def select_samples(samples: list[dict[str, Any]], selectors: list[str] | None) -> list[dict[str, Any]]:
    if not selectors:
        return samples
    selected_ids: set[str] = set()
    for selector in selectors:
        matches = [
            sample for sample in samples
            if sample["case_id"] == selector or sample.get("sample_label") == selector
        ]
        require(len(matches) == 1, f"unknown or ambiguous translation quality case: {selector}")
        selected_ids.add(matches[0]["case_id"])
    return [sample for sample in samples if sample["case_id"] in selected_ids]


def prepare_sample(sample: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    case = sample["case"]
    if sample["kind"] == "known_bad":
        prompt_bundle, critic_bundle = prepare_bad_case(case)
        return prompt_bundle, critic_bundle, str(case["known_bad_translation"])
    target = sentence_target_bundle(
        *(str(case.get(key, "")) for key in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id"))
    )
    require(
        target["sentence_text"] == case["source_text"]
        and target["sentence_text_sha256"] == sha256_text(case["source_text"]),
        f"{sample['case_id']}: human reference source differs from the canonical sentence",
    )
    translation = str(case["reference_translation"])
    prompt_bundle = build_sentence_prompt_bundle(target)
    critic_bundle = build_critic_prompt_bundle(prompt_bundle, translation)
    require(translation in critic_bundle["prompt"], f"{sample['case_id']}: reference missing from critic prompt")
    return prompt_bundle, critic_bundle, translation


def expectation_failures(sample: dict[str, Any], critic: dict[str, Any]) -> list[str]:
    failures = []
    if critic["verdict"] != sample["expected_verdict"]:
        failures.append(f"expected {sample['expected_verdict']}, received {critic['verdict']}")
    if sample["kind"] == "known_bad":
        case = sample["case"]
        issues = critic["issues"]
        if not any(issue["category"] in case["expected_categories"] for issue in issues):
            failures.append("expected issue category not detected")
        if case["require_major_issue"] and not any(issue["severity"] == "major" for issue in issues):
            failures.append("required major issue not detected")
    return failures


def evaluate_sample(sample: dict[str, Any], *, with_model: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "case_id": sample["case_id"],
        "sample_label": sample.get("sample_label", ""),
        "kind": sample["kind"],
        "expected_verdict": sample["expected_verdict"],
        "status": "validated",
        "raw_critic": None,
        "merged_critic": None,
        "deterministic_audit": None,
        "expectation_failures": {},
        "model_calls_attempted": 0,
        "model_elapsed_seconds": 0.0,
    }
    stage = "prepare"
    try:
        prompt_bundle, critic_bundle, translation = prepare_sample(sample)
        case = sample["case"]
        row.update({
            "target": {key: str(case.get(key, "")) for key in ("corpus_id", "work_id", "variant_id", "segment_id", "sentence_id")},
            "translation": translation,
            "sentence_text_sha256": prompt_bundle["target"]["sentence_text_sha256"],
            "translation_policy_sha256": prompt_bundle["translation_policy_sha256"],
            "critic_prompt_template_id": critic_bundle["prompt_template_id"],
            "critic_prompt_sha256": critic_bundle["prompt_sha256"],
            "pipeline_contract_sha256": prompt_bundle["pipeline_contract_sha256"],
        })
        if sample["kind"] == "human_reference":
            evaluation = case["human_evaluation"]
            row["reference_provenance"] = {
                "evaluator": evaluation["evaluator"],
                "evaluated_at": evaluation["evaluated_at"],
                "translation_sha256": sha256_text(translation),
                "candidate_scores_are_not_reference_scores": True,
            }
        stage = "deterministic_audit"
        row["deterministic_audit"] = merge_approved_policy_audit(
            prompt_bundle, translation, {"verdict": "pass", "issues": []}
        )
        row["expectation_failures"]["deterministic_audit"] = expectation_failures(sample, row["deterministic_audit"])
        if not with_model:
            if sample["kind"] == "human_reference" and row["expectation_failures"]["deterministic_audit"]:
                row["status"] = "failed"
            return row
        stage = "model"
        started = perf_counter()
        row["model_calls_attempted"] = 1
        try:
            row["raw_critic"] = call_critic_server(critic_bundle)
        finally:
            row["model_elapsed_seconds"] = round(perf_counter() - started, 6)
        row["expectation_failures"]["raw_critic"] = expectation_failures(sample, row["raw_critic"])
        stage = "policy_merge"
        row["merged_critic"] = merge_approved_policy_audit(prompt_bundle, translation, row["raw_critic"])
        row["expectation_failures"]["merged_critic"] = expectation_failures(sample, row["merged_critic"])
        row["status"] = "failed" if row["expectation_failures"]["merged_critic"] else "passed"
    except Exception as exc:
        row.update({"status": "error", "error_stage": stage, "error_type": type(exc).__name__, "error": str(exc)})
    return row


def sample_metrics(rows: list[dict[str, Any]], audit_key: str) -> dict[str, Any]:
    counts = {"true_positive": 0, "false_negative": 0, "true_negative": 0, "false_positive": 0, "unscored": 0}
    contracts_matched = 0
    for row in rows:
        critic = row.get(audit_key)
        if critic is None:
            counts["unscored"] += 1
            continue
        rejected = critic["verdict"] == "revise"
        if row["kind"] == "known_bad":
            counts["true_positive" if rejected else "false_negative"] += 1
        else:
            counts["false_positive" if rejected else "true_negative"] += 1
        contracts_matched += not row["expectation_failures"].get(audit_key, [])
    bad_count = counts["true_positive"] + counts["false_negative"]
    reference_count = counts["true_negative"] + counts["false_positive"]
    return {
        **counts,
        "sensitivity": counts["true_positive"] / bad_count if bad_count else None,
        "specificity": counts["true_negative"] / reference_count if reference_count else None,
        "known_bad_scored": bad_count,
        "human_reference_scored": reference_count,
        "category_and_severity_contracts_matched": contracts_matched,
    }


def report_summary(rows: list[dict[str, Any]], *, selected_count: int, with_model: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_type": "translation_critic_balanced_report",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "These purpose-selected, policy-aware samples are not an independent estimate of corpus-wide quality.",
        "positive_class": "known_bad translation; a revise verdict counts as defect detection",
        "human_quality_scores_updated": False,
        "with_model": with_model,
        "selected_count": selected_count,
        "completed_count": len(rows),
        "complete": len(rows) == selected_count,
        "errors": sum(row["status"] == "error" for row in rows),
        "failures": sum(row["status"] == "failed" for row in rows),
        "model_calls_attempted": sum(row["model_calls_attempted"] for row in rows),
        "model_elapsed_seconds": round(sum(row["model_elapsed_seconds"] for row in rows), 6),
        "metrics": {key: sample_metrics(rows, key) for key in ("raw_critic", "merged_critic", "deterministic_audit")},
        "samples": [{key: row[key] for key in ("case_id", "kind", "status")} for row in rows],
    }


def new_report_directory(value: Path) -> Path:
    directory = value.resolve()
    root = REPORT_ROOT.resolve()
    require(directory != root and directory.is_relative_to(root), "report directory must be a new directory under data/runtime.local")
    require(not directory.exists(), "report directory already exists; choose a fresh run directory")
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def write_summary(directory: Path, summary: dict[str, Any]) -> None:
    temporary = directory / "summary.json.tmp"
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / "summary.json")


def run_report_samples(samples: list[dict[str, Any]], *, with_model: bool, report_dir: Path | None) -> None:
    rows = []
    directory = new_report_directory(report_dir) if report_dir is not None else None
    if directory is not None:
        write_summary(directory, report_summary(rows, selected_count=len(samples), with_model=with_model))
    for sample in samples:
        row = evaluate_sample(sample, with_model=with_model)
        rows.append(row)
        if directory is not None:
            with (directory / "samples.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            write_summary(directory, report_summary(rows, selected_count=len(samples), with_model=with_model))
        print(f"{row['case_id']}: " + json.dumps({
            "kind": row["kind"], "status": row["status"],
            "raw": row["raw_critic"]["verdict"] if row["raw_critic"] else None,
            "merged": row["merged_critic"]["verdict"] if row["merged_critic"] else None,
            "error": row.get("error", ""),
        }, ensure_ascii=False), flush=True)
    summary = report_summary(rows, selected_count=len(samples), with_model=with_model)
    print("translation critic sample summary: " + json.dumps(summary, ensure_ascii=False), flush=True)
    require(not summary["errors"] and not summary["failures"], "translation critic sample checks failed; inspect the per-sample report")


def load_semantic_controls() -> list[dict[str, Any]]:
    controls = json.loads(CASES_PATH.read_text(encoding="utf-8")).get("semantic_controls", [])
    require(isinstance(controls, list) and 0 < len(controls) <= 64, "semantic controls are required")
    identifiers = set()
    for control in controls:
        require(isinstance(control, dict), "invalid semantic control")
        identifier = control.get("case_id")
        require(isinstance(identifier, str) and identifier and identifier not in identifiers, "duplicate semantic control")
        identifiers.add(identifier)
        require(type(control.get("expected_major_semantic_error")) is bool, "invalid semantic expectation")
        require(control.get("kind") in {"adopted-reference", "meaning-equivalent", "known-bad"}, "invalid semantic control kind")
        require(control["expected_major_semantic_error"] == (control["kind"] == "known-bad"), "semantic control label mismatch")
        require(type(control.get("expected_readability_issue", False)) is bool, "invalid readability expectation")
        require(isinstance(control.get("translation"), str) and bool(control["translation"].strip()), "semantic control needs translation")
    return controls


def prepare_semantic_control(control: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    target = sentence_target_bundle(*(str(control.get(key, "")) for key in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")))
    require(target["sentence_text_sha256"] == control.get("sentence_text_sha256"), "semantic control source changed")
    prompt = build_sentence_prompt_bundle(target)
    return prompt, build_critic_prompt_bundle(prompt, control["translation"])


def has_major_semantic_issue(critic: dict[str, Any]) -> bool:
    # Stylistic failures remain in the audit and can still require revision.
    return any(issue["severity"] == "major" and issue["category"] not in {"korean_readability", "register"} for issue in critic["issues"])


def semantic_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = dict.fromkeys(["true_positive", "false_negative", "true_negative", "false_positive", "unscored"], 0)
    for row in rows:
        audit = row.get(key)
        if audit is None:
            counts["unscored"] += 1
            continue
        found = has_major_semantic_issue(audit)
        if row["expected_major_semantic_error"]:
            counts["true_positive" if found else "false_negative"] += 1
        else:
            counts["false_positive" if found else "true_negative"] += 1
    return counts


def run_semantic_controls(controls: list[dict[str, Any]], *, with_model: bool, report_dir: Path | None) -> None:
    require(not with_model or report_dir is not None, "semantic model runs require a report directory")
    prepared = [(control, *prepare_semantic_control(control)) for control in controls]
    directory = new_report_directory(report_dir) if report_dir is not None else None
    rows = []
    for control, prompt, critic_bundle in prepared:
        row = {**control, "raw_critic": None, "merged_critic": None, "critic_prompt_sha256": critic_bundle["prompt_sha256"],
               "pipeline_contract_sha256": prompt["pipeline_contract_sha256"], "model_calls_attempted": 0, "status": "validated"}
        if with_model:
            row["model_calls_attempted"] = 1
            try:
                row["raw_critic"] = call_critic_server(critic_bundle)
                row["merged_critic"] = merge_approved_policy_audit(prompt, control["translation"], row["raw_critic"])
                meaning_matches = has_major_semantic_issue(row["raw_critic"]) == control["expected_major_semantic_error"]
                readability_matches = not control.get("expected_readability_issue") or any(issue["category"] == "korean_readability" for issue in row["raw_critic"]["issues"])
                row["status"] = "passed" if meaning_matches and readability_matches else "failed"
            except Exception as exc:
                row.update(status="error", error_type=type(exc).__name__, error=str(exc))
        rows.append(row)
        if directory is not None:
            with (directory / "samples.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(control["case_id"] + ": " + json.dumps({"status": row["status"], "raw_major_semantic_error": has_major_semantic_issue(row["raw_critic"]) if row["raw_critic"] else None}, ensure_ascii=False), flush=True)
    summary = {"record_type": "translation_critic_semantic_control_report", "selected_count": len(controls), "completed_count": len(rows),
        "scope": "Purpose-selected semantic controls; style issues remain actionable and no human scores are assigned.",
        "raw": semantic_metrics(rows, "raw_critic"), "merged": semantic_metrics(rows, "merged_critic"),
        "failures": sum(row["status"] == "failed" for row in rows), "errors": sum(row["status"] == "error" for row in rows),
        "readability_expected": sum(bool(row.get("expected_readability_issue")) for row in rows),
        "readability_detected": sum(bool(row.get("expected_readability_issue")) and row.get("raw_critic") is not None and any(issue["category"] == "korean_readability" for issue in row["raw_critic"]["issues"]) for row in rows),
        "model_calls_attempted": sum(row["model_calls_attempted"] for row in rows)}
    if directory is not None:
        write_summary(directory, summary)
    print("semantic controls: " + json.dumps(summary, ensure_ascii=False), flush=True)
    require(not summary["errors"] and not summary["failures"], "semantic critic controls failed; inspect the preserved audit")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate permanent sentence translation quality regressions.", allow_abbrev=False)
    parser.add_argument("--with-model", action="store_true", help="Also ask the local Gemma critic to reject each known-bad translation.")
    parser.add_argument("--case-id", action="append", help="Select an exact case id; repeat to select several. Balanced mode also accepts goldset sample labels such as K02.")
    parser.add_argument("--balanced", action="store_true", help="Also audit evaluated human reference translations from the read-only goldset.")
    parser.add_argument("--semantic-controls", action="store_true", help="Check source-bound meaning equivalents and contrast errors; readability issues are preserved separately.")
    parser.add_argument("--report-dir", type=Path, help="Write raw, merged, and deterministic audits to a fresh ignored data/runtime.local directory.")
    args = parser.parse_args()
    if args.semantic_controls:
        require(not args.balanced, "semantic controls and balanced samples are separate cohorts")
        controls = select_samples(load_semantic_controls(), args.case_id)
        run_semantic_controls(controls, with_model=args.with_model, report_dir=args.report_dir)
        return
    cases = load_cases()
    if args.balanced or args.report_dir is not None:
        require(not (args.balanced and args.with_model and args.report_dir is None), "balanced model runs require --report-dir to preserve every audit")
        samples = balanced_samples(cases) if args.balanced else [
            {"case_id": case["case_id"], "kind": "known_bad", "expected_verdict": "revise", "case": case}
            for case in cases
        ]
        run_report_samples(select_samples(samples, args.case_id), with_model=args.with_model, report_dir=args.report_dir)
        return
    if args.case_id:
        selected = select_samples([{"case_id": case["case_id"], "case": case} for case in cases], args.case_id)
        cases = [sample["case"] for sample in selected]
    for case in cases:
        validate_case(case, with_model=args.with_model)
    suffix = " with local model" if args.with_model else ""
    print(f"translation quality regressions ok ({len(cases)} case(s){suffix})")


if __name__ == "__main__":
    main()
