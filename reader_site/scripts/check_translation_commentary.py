"""Offline contracts for note auditing; these do not evaluate model judgments.

Synthetic model replies test isolation, bounded calls, error handling and record
integrity. Detecting real grammatical or approval-scope mistakes still requires
separate model evaluation against independently reviewed examples.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services import sentence_translations as translations  # noqa: E402
from services import translation_ai_reviews as reviews  # noqa: E402
from services import translation_commentary as commentary  # noqa: E402
from services.source_targets import sha256_text  # noqa: E402
from scripts.check_ai_records_contracts import (  # noqa: E402
    SENTENCE_TRANSLATION_V3_FIELDS,
    SENTENCE_TRANSLATION_V4_FIELDS,
    SENTENCE_TRANSLATION_V5_FIELDS,
    SENTENCE_TRANSLATION_V6_FIELDS,
    validate_file,
    validate_record,
)
from scripts.check_sentence_translation_contracts import synthetic_sentence_target  # noqa: E402


PASS = {"verdict": "pass", "issues": []}
FINAL_TRANSLATION = "삶은 힘에의 의지이다."
FINAL_COMMENTARY = "‘Macht’를 ‘힘’으로 옮겼다."


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_rejected(action, message: str) -> None:
    try:
        action()
    except (AssertionError, ValueError):
        return
    raise AssertionError(message)


def notes_issue(**overrides: str) -> dict[str, str]:
    # This deliberately supplied verdict exercises contracts, not linguistic quality.
    issue = {
        "source_span": "Macht",
        "commentary_span": "‘Macht’를 ‘힘’으로 옮겼다.",
        "category": "translation_match",
        "severity": "minor",
        "explanation": "합성 감사 이슈: 해당 주장은 검토가 필요하다.",
    }
    return {**issue, **overrides}


def fidelity_issue(severity: str = "major") -> dict[str, str]:
    return {
        "source_span": "Macht", "translation_span": "초벌", "category": "semantic_substitution",
        "severity": severity, "explanation": "합성 본문 감사 이슈.",
    }


def run_fixture(
    prompt_bundle: dict, *, note_text: str = FINAL_COMMENTARY, notes_response: object = PASS,
    initial_critic: dict | Exception = PASS,
) -> tuple[dict, int]:
    draft = {"translation": FINAL_TRANSLATION, "commentary": note_text, "cautions": []}
    critic_options = {"side_effect": initial_critic} if isinstance(initial_critic, Exception) else {"return_value": copy.deepcopy(initial_critic)}
    response_text = notes_response if isinstance(notes_response, str) else json.dumps(notes_response, ensure_ascii=False)
    with (
        patch.object(translations, "call_llama_server", return_value=draft),
        patch.object(translations, "call_critic_server", **critic_options),
        patch.object(translations, "call_revision_server", side_effect=AssertionError("unexpected revision")),
        patch.object(translations, "call_llama_json", return_value=response_text) as notes_call,
    ):
        result = translations.run_translation_pipeline(prompt_bundle)
    return result, notes_call.call_count


def validate_output(target: dict, prompt_bundle: dict, output: dict) -> dict:
    record = translations.build_record(target, prompt_bundle, output)
    validate_record(record, Path("synthetic-commentary.jsonl"), 1)
    require(record["review_state"] == "generated", "an automatic note audit must not claim human review")
    return record


def check_parser_claim_anchors(prompt_bundle: dict) -> None:
    context = prompt_bundle["source_context"]
    parse = lambda value: commentary.normalized_commentary_output(
        json.dumps(value, ensure_ascii=False), source_context=context, commentary=FINAL_COMMENTARY,
    )
    require(parse(PASS) == PASS, "valid empty-issue audit was rejected")
    issue = notes_issue()
    require(parse({"verdict": "revise", "issues": [issue]})["issues"] == [issue], "valid issue anchors were rejected")
    for invalid in (
        [], {"verdict": "pass", "issues": [], "extra": "ignored"},
        {"verdict": "pass", "issues": [issue]}, {"verdict": "revise", "issues": []},
        {"verdict": "reviewed", "issues": []},
        {"verdict": "revise", "issues": [notes_issue(category="coverage")]},
        {"verdict": "revise", "issues": [notes_issue(commentary_span="a claim absent from the notes")]},
        {"verdict": "revise", "issues": [notes_issue(source_span="a quotation absent from the source")]},
        {"verdict": "revise", "issues": [notes_issue(explanation=" ")]},
        {"verdict": "revise", "issues": [issue] * 9},
    ):
        expect_rejected(lambda invalid=invalid: parse(invalid), "invalid notes audit was accepted")

    # An unsupported quotation is retained in the note under review. The auditor
    # may use an empty source anchor when that is the very error being reported.
    bad_quote_note = "‘NOT_IN_SOURCE’라는 원문을 옮겼다."
    result = commentary.normalized_commentary_output(
        json.dumps({"verdict": "revise", "issues": [notes_issue(
            source_span="", commentary_span="‘NOT_IN_SOURCE’", category="source_support",
        )]}, ensure_ascii=False), source_context=context, commentary=bad_quote_note,
    )
    require(result["verdict"] == "revise", "an inaccurate source quotation must remain auditable")


def check_bounded_final_audit(target: dict, prompt_bundle: dict) -> None:
    empty, calls = run_fixture(prompt_bundle, note_text="")
    require(calls == 0 and empty["commentary_audit"]["status"] == "skipped_empty", "empty notes must make no audit request")
    validate_output(target, prompt_bundle, empty)
    passed, calls = run_fixture(prompt_bundle)
    require(calls == 1 and passed["commentary_audit"]["status"] == "pass", "nonempty final notes must be audited once")
    validate_output(target, prompt_bundle, passed)

    initial_note = "초벌 노트 DRAFT_NOTE_ONLY"
    final_note = "최종 노트 FINAL_NOTE_ONLY"
    replies = [
        {"translation": "초벌 번역", "commentary": initial_note, "cautions": []},
        {"verdict": "revise", "issues": [fidelity_issue()]},
        {"translation": FINAL_TRANSLATION, "commentary": final_note, "cautions": []},
        PASS, PASS,
    ]
    calls_seen: list[tuple[str, str]] = []

    def reply(prompt, _parameters, _schema, system_prompt):
        calls_seen.append((system_prompt, prompt))
        return json.dumps(replies.pop(0), ensure_ascii=False)

    with patch.object(translations, "call_llama_json", side_effect=reply):
        revised = translations.run_translation_pipeline(prompt_bundle)
    require(not replies and len(calls_seen) == 5, "revision path must make exactly four fidelity calls and one notes call")
    require([system for system, _ in calls_seen] == [
        translations.TRANSLATOR_SYSTEM_PROMPT, translations.CRITIC_SYSTEM_PROMPT,
        translations.REVISION_SYSTEM_PROMPT, translations.CRITIC_SYSTEM_PROMPT,
        commentary.COMMENTARY_SYSTEM_PROMPT,
    ], "notes auditing changed the independent fidelity stage order")
    for system, prompt in calls_seen[:-1]:
        if system in {translations.CRITIC_SYSTEM_PROMPT, translations.REVISION_SYSTEM_PROMPT}:
            require("NOTE_ONLY" not in prompt, "translator commentary leaked into fidelity review or revision")
    require(final_note in calls_seen[-1][1] and initial_note not in calls_seen[-1][1], "notes auditor received a stale draft note")
    require(FINAL_TRANSLATION in calls_seen[-1][1], "notes auditor did not receive the final model translation")
    require(revised["quality_state"] == "critic_pass_after_revision", "successful revision/notes audit lost its state")
    require(revised["commentary_audit"]["commentary_sha256"] == sha256_text(final_note), "notes audit fingerprint is stale")
    validate_output(target, prompt_bundle, revised)


def check_combined_states_and_failures(target: dict, prompt_bundle: dict, directory: Path) -> None:
    note_failure = {"verdict": "revise", "issues": [notes_issue()]}
    for response, expected_audit in (
        (note_failure, "needs_review"), ("invalid JSON", "error"),
        ({"verdict": "pass", "issues": [notes_issue()]}, "error"),
        ({"verdict": ["pass"], "issues": []}, "error"),
    ):
        result, calls = run_fixture(prompt_bundle, notes_response=response)
        require(calls == 1, "a notes failure must not retry or revise the translation")
        require(result["translation_quality_state"] == "critic_pass", "notes failure overwrote the fidelity audit result")
        require(result["quality_state"] == "needs_human_review", "notes failure must not leave combined automatic approval")
        require(result["commentary_audit"]["status"] == expected_audit, "notes failure lost its cause")
        record = validate_output(target, prompt_bundle, result)
        cache_path = directory / "notes-failure.jsonl"
        cache_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        require(translations.find_cached_record(cache_path, target, prompt_bundle) is None, "failed notes were reused as a passing generation")

    # Exercise actual timeout conversion in call_llama_json rather than mocking
    # it as an already-normalized ConnectionError.
    draft = {"translation": FINAL_TRANSLATION, "commentary": FINAL_COMMENTARY, "cautions": []}
    with (
        patch.object(translations, "call_llama_server", return_value=draft),
        patch.object(translations, "call_critic_server", return_value=PASS),
        patch.object(translations, "urlopen", side_effect=TimeoutError("synthetic notes timeout")) as request,
    ):
        timeout = translations.run_translation_pipeline(prompt_bundle)
    require(request.call_count == 1, "notes timeout must not trigger another model request")
    require(timeout["quality_state"] == "needs_human_review" and timeout["commentary_audit"]["status"] == "error", "timeout was not retained as an incomplete notes audit")
    timeout_record = validate_output(target, prompt_bundle, timeout)
    cache_path.write_text(json.dumps(timeout_record, ensure_ascii=False) + "\n", encoding="utf-8")
    require(translations.find_cached_record(cache_path, target, prompt_bundle) is None, "timed-out notes entered the passing cache")

    # A correct limited note can coexist with a failed translation; do not use
    # notes coverage as a verdict about the whole translation.
    minor, calls = run_fixture(prompt_bundle, initial_critic={"verdict": "revise", "issues": [fidelity_issue("minor")]})
    require(calls == 1 and minor["commentary_audit"]["status"] == "pass", "notes pass should remain separately recorded")
    require(minor["quality_state"] == minor["translation_quality_state"] == "needs_human_review", "notes pass promoted a fidelity failure")
    validate_output(target, prompt_bundle, minor)
    for note_text in (FINAL_COMMENTARY, ""):
        failed, calls = run_fixture(prompt_bundle, note_text=note_text, initial_critic=translations.TranslationModelResponseError("synthetic critic failure"))
        require(calls == 0, "failed fidelity audit should stop before nonempty notes auditing")
        require(failed["quality_state"] == "critic_error", "skipped notes erased a fidelity error")
        require(failed["commentary_audit"]["status"] == ("not_run" if note_text else "skipped_empty"), "unaudited notes were incorrectly marked as passing")
        validate_output(target, prompt_bundle, failed)


def check_approval_scope_handoff(target: dict) -> None:
    policy = {
        "profile_id": "synthetic-scoped-approval", "approval_state": "approved", "terminology": [],
        "style_notes": [], "sentence_rules": [{
            "sentence_id": target["sentence_id"], "allowed_translation_fragments": ["힘에의 의지"],
            "forbidden_translation_fragments": [],
        }],
    }
    policy["policy_sha256"] = sha256_text(json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    with patch.object(translations, "translation_policy_bundle", return_value=policy):
        bundle = translations.build_sentence_prompt_bundle(target)
    note = "‘힘에의 의지’는 이 문장에 등록된 승인 조각이다."
    audit_bundle = commentary.build_commentary_prompt_bundle(bundle, FINAL_TRANSLATION, note)
    require(bundle["translation_policy_text"] in audit_bundle["prompt"], "notes auditor lost the exact applicable approval policy")
    require("‘힘에의 의지’" in audit_bundle["prompt"], "the registered fragment was omitted from the notes audit")
    allowed, calls = run_fixture(bundle, note_text=note)
    require(calls == 1 and allowed["quality_state"] == "critic_pass", "a supplied pass on a scoped approval claim was blocked by a blanket approval-word rule")
    validate_output(target, bundle, allowed)
    broad_claim = "이 번역문 전체는 사람이 승인했다."
    supplied_issue = notes_issue(source_span="", commentary_span=broad_claim, category="approval_claim")
    flagged, _ = run_fixture(bundle, note_text=broad_claim, notes_response={"verdict": "revise", "issues": [supplied_issue]})
    require(flagged["quality_state"] == "needs_human_review", "a supplied scope-error issue was discarded")
    validate_output(target, bundle, flagged)


def check_record_binding_and_contract_cache(target: dict, prompt_bundle: dict, directory: Path) -> dict:
    result, _ = run_fixture(prompt_bundle)
    record = validate_output(target, prompt_bundle, result)
    path = directory / "bound-record.jsonl"
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    require(translations.find_cached_record(path, target, prompt_bundle) is not None, "an intact passing notes audit was not cacheable")
    for field in ("translation", "commentary", "source_context_sha256", "translation_policy_sha256"):
        invalid = copy.deepcopy(record)
        invalid[field] = "f" * 64 if field.endswith("sha256") else invalid[field] + " 변경"
        expect_rejected(lambda invalid=invalid: validate_record(invalid, path, 1), f"notes audit accepted changed {field}")
        path.write_text(json.dumps(invalid, ensure_ascii=False) + "\n", encoding="utf-8")
        require(translations.find_cached_record(path, target, prompt_bundle) is None, f"runtime cache reused an audit after {field} changed")
    for malformed in ({}, {"status": []}, None):
        invalid = copy.deepcopy(record)
        invalid["commentary_audit"] = malformed
        path.write_text(json.dumps(invalid, ensure_ascii=False) + "\n", encoding="utf-8")
        require(translations.find_cached_record(path, target, prompt_bundle) is None, "malformed persisted notes audit was reused or crashed the cache")
    invalid = copy.deepcopy(record)
    invalid["commentary_audit"]["status"] = []
    invalid["review_state"] = "reviewed"
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in [record, invalid]), encoding="utf-8")
    cached = translations.find_cached_record(path, target, prompt_bundle)
    require(cached is not None and cached["review_state"] == "generated", "cache must skip a damaged newer audit even when its human review flag is set")
    for field, value in (("translation_quality_state", "critic_pass_after_revision"), ("quality_pipeline_version", 2), ("prompt_template_id", "sentence_translation_study_v4")):
        invalid = copy.deepcopy(record)
        invalid[field] = value
        expect_rejected(lambda invalid=invalid: validate_record(invalid, path, 1), f"v6 accepted inconsistent {field}")
    for field in SENTENCE_TRANSLATION_V6_FIELDS:
        invalid = copy.deepcopy(record)
        invalid.pop(field)
        expect_rejected(lambda invalid=invalid: validate_record(invalid, path, 1), f"v6 accepted missing {field}")

    flagged, _ = run_fixture(prompt_bundle, notes_response={"verdict": "revise", "issues": [notes_issue()]})
    invalid = translations.build_record(target, prompt_bundle, flagged)
    invalid["quality_state"] = "critic_pass"
    expect_rejected(lambda: validate_record(invalid, path, 1), "notes failure was allowed to claim a combined pass")
    altered_contract = copy.deepcopy(prompt_bundle["commentary_audit_contract"])
    altered_contract["system_prompt_sha256"] = "0" * 64
    with patch.object(translations, "commentary_audit_contract", return_value=altered_contract):
        next_bundle = translations.build_sentence_prompt_bundle(target)
    require(next_bundle["request_contract_sha256"] == prompt_bundle["request_contract_sha256"], "notes-only change altered the translator request contract")
    require(next_bundle["pipeline_contract_sha256"] != prompt_bundle["pipeline_contract_sha256"], "notes system prompt did not invalidate the pipeline contract")
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    require(translations.find_cached_record(path, target, next_bundle) is None, "cache ignored a changed notes audit contract")

    human = copy.deepcopy(record)
    human.update(human_translation="사람이 별도로 수정한 번역.", human_translation_updated_at=record["generated_at"],
                 human_translation_base_sha256=sha256_text(record["translation"]), review_state="reviewed")
    validate_record(human, path, 1)
    require(human["commentary_audit"]["translation_sha256"] != sha256_text(human["human_translation"]), "old automatic audit was silently rebound to the human revision")
    return record


def check_legacy_record_compatibility(record: dict, directory: Path) -> None:
    for schema_version in range(1, 6):
        legacy = copy.deepcopy(record)
        legacy["schema_version"] = schema_version
        for field in SENTENCE_TRANSLATION_V6_FIELDS:
            legacy.pop(field)
        legacy.update(quality_pipeline_version=2, prompt_template_id="sentence_translation_study_v4",
                      critic_prompt_template_id="sentence_translation_critic_v2",
                      revision_prompt_template_id="sentence_translation_revision_v2")
        for introduced, fields in ((5, SENTENCE_TRANSLATION_V5_FIELDS), (4, SENTENCE_TRANSLATION_V4_FIELDS), (3, SENTENCE_TRANSLATION_V3_FIELDS)):
            if schema_version < introduced:
                for field in fields:
                    legacy.pop(field, None)
        if schema_version < 5:
            legacy["citations"][0]["source_text_sha256"] = legacy["sentence_text_sha256"]
        if schema_version == 1:
            legacy.update(literal_gloss="", key_terms=[])
        path = directory / f"legacy-v{schema_version}.jsonl"
        path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")
        require(validate_file(path) == 1, f"legacy schema v{schema_version} was rejected")
        if schema_version == 5:
            minor_only = copy.deepcopy(legacy)
            minor_only.update(quality_state="needs_human_review", critic={"initial": {"verdict": "revise", "issues": [fidelity_issue("minor")]}, "final": None})
            validate_record(minor_only, path, 1)
            legacy.update(quality_pipeline_version=1, prompt_template_id="sentence_translation_study_v3",
                          critic_prompt_template_id="sentence_translation_critic_v1", revision_prompt_template_id="sentence_translation_revision_v1")
            validate_record(legacy, path, 1)
            legacy["quality_pipeline_version"] = 3
            expect_rejected(lambda: validate_record(legacy, path, 1), "schema v5 must not silently claim the new pipeline")


def check_ai_review_history_routing(record: dict, directory: Path) -> None:
    review = reviews.build_review(
        "synthetic-history-routing", "synthetic", "work", "A synthetic sentence.", "합성 문장이다.",
        dict(zip(reviews.RUBRIC_DIMENSIONS, (5, 5, 5, 5, None))), "accept_candidate", "합성 이력 위임 검사.",
    )
    path = directory / "ai-review-history.jsonl"
    write = lambda records: path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")
    write([review])
    require(validate_file(path) == 1, "generic checker did not accept a valid dedicated AI review history")
    orphan = copy.deepcopy(review)
    orphan["related_review_ids"] = [str(uuid.uuid4())]
    orphan["record_sha256"] = reviews.review_sha256(orphan)
    reviews.validate_review(orphan)  # Individually valid; only history knows the link is absent.
    write([orphan])
    expect_rejected(lambda: validate_file(path), "generic checker skipped review history link validation")
    write([review, review])
    expect_rejected(lambda: validate_file(path), "generic checker accepted duplicate review history IDs")
    write([record, review])
    expect_rejected(lambda: validate_file(path), "AI reviews were mixed into generated sentence records")


def main() -> None:
    target = synthetic_sentence_target()
    prompt_bundle = translations.build_sentence_prompt_bundle(target)
    with tempfile.TemporaryDirectory(prefix="philo_commentary_contracts_") as temp_dir:
        directory = Path(temp_dir)
        with patch.object(translations, "urlopen", side_effect=AssertionError("offline checks must not contact a model")):
            check_parser_claim_anchors(prompt_bundle)
            check_bounded_final_audit(target, prompt_bundle)
            check_combined_states_and_failures(target, prompt_bundle, directory)
            check_approval_scope_handoff(target)
            record = check_record_binding_and_contract_cache(target, prompt_bundle, directory)
            check_legacy_record_compatibility(record, directory)
            check_ai_review_history_routing(record, directory)
    print("translation commentary contracts ok (offline: anchors/call-bounds/isolation/failure-states/hash-binding/legacy/history-routing; model judgments not evaluated)")


if __name__ == "__main__":
    main()
