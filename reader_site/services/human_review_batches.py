"""Five-dimension reviews with separate, explicit per-case operational adoption."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from services import human_reviews as legacy
from services.jsonl_storage import locked_jsonl
from services.sentence_targets import sentence_target_bundle
from services.translation_notes import grounded_notes, translation_hash


DIMENSIONS = ("omission_addition", "logic", "terminology", "korean_readability", "note_accuracy")
CASE_FIELDS = {
    "id", "candidate_record_id", "sentence_text_sha256", "candidate_translation_sha256",
    "decision", "evaluator", "evaluator_kind", "evaluated_date", "evaluated_at", "scores",
    "reference_translation", "provisional_translation", "note_action", "translation_notes", "notes",
}


def validate_review(review: Any) -> None:
    legacy.require(isinstance(review, dict) and set(review) <= CASE_FIELDS, "invalid_batch_review")
    legacy.text(review.get("id"), "invalid_batch_review", 200)
    legacy.record_uuid(review.get("candidate_record_id"))
    for field in ("sentence_text_sha256", "candidate_translation_sha256"):
        value = review.get(field)
        legacy.require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), "invalid_review_hash")
    legacy.require(review.get("decision") in {"confirmed", "held"}, "invalid_review_decision")
    legacy.text(review.get("evaluator"), "invalid_evaluator", 200)
    legacy.require(review.get("evaluator_kind") in {"unspecified", "ai", "ai_assisted"}, "invalid_evaluator_kind")
    day = review.get("evaluated_date")
    legacy.require(isinstance(day, str), "invalid_evaluation_date")
    try:
        legacy.require(date.fromisoformat(day).isoformat() == day, "invalid_evaluation_date")
    except ValueError:
        raise legacy.HumanReviewError("invalid_evaluation_date") from None
    if review.get("evaluated_at") is not None:
        legacy.timestamp(review["evaluated_at"])
        legacy.require(datetime.fromisoformat(review["evaluated_at"].replace("Z", "+00:00")).date().isoformat() == day, "evaluation_date_mismatch")
    scores = review.get("scores")
    legacy.require(isinstance(scores, dict) and set(scores) == set(DIMENSIONS), "invalid_batch_scores")
    legacy.require(all(type(scores[key]) is int and 1 <= scores[key] <= 5 for key in DIMENSIONS[:-1]), "invalid_batch_scores")
    note_score = scores["note_accuracy"]
    legacy.require(note_score is None or type(note_score) is int and 1 <= note_score <= 5, "invalid_batch_scores")
    legacy.require(review.get("note_action") in {"not_applicable", "keep", "replace"}, "invalid_note_action")
    # The score assesses model notes; replacement notes may be newly authored.
    legacy.require(review["note_action"] == "replace" or (note_score is None) == (review["note_action"] == "not_applicable"), "note_score_applicability_mismatch")
    notes = review.get("translation_notes")
    legacy.require(isinstance(notes, list), "invalid_review_translation_notes")
    legacy.require(bool(notes) if review["note_action"] == "replace" else not notes, "invalid_review_translation_notes")
    reference = review.get("reference_translation")
    if review["decision"] == "confirmed":
        legacy.text(reference, "invalid_reference_translation")
        legacy.require(not review.get("provisional_translation"), "confirmed_review_has_provisional_text")
    else:
        legacy.require(reference == "", "held_review_has_reference")
        legacy.text(review.get("provisional_translation"), "invalid_provisional_translation")
    legacy.text(review.get("notes"), "invalid_evaluation_notes", 12000)


def feedback_cases(feedback: Any) -> dict[str, dict]:
    legacy.require(isinstance(feedback, dict) and type(feedback.get("schema_version")) is int and feedback["schema_version"] == 2, "invalid_batch_feedback_schema")
    legacy.require(set(feedback) == {"schema_version", "score_order", "cases"}, "unknown_batch_feedback_field")
    legacy.require(feedback["score_order"] == list(DIMENSIONS), "invalid_score_order")
    reviews = legacy.unique_by_id(feedback["cases"], "invalid_feedback_cases")
    legacy.require(len(reviews) <= 64, "too_many_feedback_cases")
    for review in reviews.values():
        validate_review(review)
    legacy.require(len({review["candidate_record_id"] for review in reviews.values()}) == len(reviews), "duplicate_candidate_uuid")
    return reviews


def validate_store(store: Any) -> dict[str, dict]:
    legacy.require(isinstance(store, dict) and set(store) == {"schema_version", "score_order", "cases"}, "invalid_review_store")
    legacy.require(type(store["schema_version"]) is int and store["schema_version"] == 2 and store["score_order"] == list(DIMENSIONS), "invalid_review_store")
    if store["cases"] == []:
        return {}
    cases = legacy.unique_by_id(store["cases"], "invalid_review_store")
    legacy.require(len(cases) <= 64, "too_many_feedback_cases")
    for entry in cases.values():
        legacy.require(set(entry) == {"id", "target", "source_text", "candidate_translation", "model_sha256", "review", "resolved_translation_notes", "note_binding", "evaluation_history"}, "invalid_review_store")
        validate_review(entry["review"])
        legacy.require(entry["id"] == entry["review"]["id"], "invalid_review_store")
        legacy.text(entry["source_text"], "invalid_review_store", 1000)
        legacy.text(entry["candidate_translation"], "invalid_review_store")
        legacy.require(legacy.digest(entry["source_text"].encode("utf-8")) == entry["review"]["sentence_text_sha256"], "invalid_review_store")
        legacy.require(legacy.digest(entry["candidate_translation"].encode("utf-8")) == entry["review"]["candidate_translation_sha256"], "invalid_review_store")
        target = entry["target"]
        legacy.require(isinstance(target, dict) and set(target) == set(legacy.TARGET_FIELDS), "invalid_review_store")
        legacy.require(target["corpus_id"] in legacy.CORPORA and all(isinstance(v, str) for v in target.values()), "invalid_review_store")
        legacy.require(isinstance(entry["model_sha256"], str) and len(entry["model_sha256"]) == 64 and all(c in "0123456789abcdef" for c in entry["model_sha256"]), "invalid_review_store")
        history = entry["evaluation_history"]
        legacy.require(isinstance(history, list), "invalid_review_history")
        for prior in history:
            legacy.require(isinstance(prior, dict) and prior.get("evaluation_history") == [], "invalid_review_history")
            legacy.require(prior.get("id") == entry["id"] and prior.get("target") == target and prior.get("source_text") == entry["source_text"], "invalid_review_history")
            validate_store({"schema_version": 2, "score_order": list(DIMENSIONS), "cases": [prior]})
        notes = entry["resolved_translation_notes"]
        legacy.require(isinstance(notes, list) and grounded_notes(notes, entry["source_text"]) == notes, "invalid_review_translation_notes")
        legacy.require(bool(notes) == (entry["review"]["note_action"] != "not_applicable"), "invalid_review_translation_notes")
        if entry["review"]["note_action"] == "replace":
            legacy.require(notes == entry["review"]["translation_notes"], "invalid_review_translation_notes")
        expected = None
        if notes and entry["review"]["decision"] == "confirmed":
            expected = {"sentence_text_sha256": entry["review"]["sentence_text_sha256"], "translation_sha256": translation_hash(entry["review"]["reference_translation"])}
        legacy.require(entry["note_binding"] == expected, "invalid_review_note_binding")
    return cases


def reject_stale_review(incoming: dict, previous: dict) -> None:
    if incoming.get("evaluated_at") and previous.get("evaluated_at"):
        old = datetime.fromisoformat(previous["evaluated_at"].replace("Z", "+00:00"))
        new = datetime.fromisoformat(incoming["evaluated_at"].replace("Z", "+00:00"))
        legacy.require(new > old, "stale_human_review")
    else:
        legacy.require(incoming["evaluated_date"] >= previous["evaluated_date"], "stale_human_review")
        legacy.require(incoming["evaluated_date"] != previous["evaluated_date"], "same_day_revision_needs_timestamp")


def candidate_cases(value: Any) -> dict[str, dict]:
    legacy.require(isinstance(value, list) and 0 < len(value) <= 64, "invalid_candidates")
    result = {}
    for row in value:
        legacy.require(isinstance(row, dict) and isinstance(row.get("record"), dict), "invalid_candidates")
        identifier = row.get("case_id")
        legacy.text(identifier, "invalid_candidates", 200)
        legacy.require(identifier not in result, "invalid_candidates")
        result[identifier] = row["record"]
    return result


def build_plan(reviews: dict[str, dict], candidates: dict[str, dict], source_paths: dict[str, Path], store_path: Path, *, target_resolver: Callable, record_validator: Callable | None) -> tuple[list[dict], dict]:
    before = legacy.read_bytes(store_path, legacy.MAX_INPUT_BYTES, missing=True)
    store = legacy.parse_json(before) if before is not None else {"schema_version": 2, "score_order": list(DIMENSIONS), "cases": []}
    stored = validate_store(store)
    originals = {corpus: legacy.read_records(legacy.read_bytes(path, legacy.MAX_AI_BYTES)) for corpus, path in source_paths.items()}
    changed_cases = 0
    for identifier, review in reviews.items():
        candidate = candidates[identifier]
        legacy.require(candidate.get("id") == review["candidate_record_id"], "candidate_selection_mismatch")
        corpus = candidate.get("corpus_id")
        legacy.require(corpus in legacy.CORPORA, "invalid_candidate_corpus")
        legacy.require(all(isinstance(candidate.get(field), str) for field in legacy.TARGET_FIELDS), "invalid_candidate_target")
        try:
            target = target_resolver(*(candidate[field] for field in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")))
        except (ValueError, OSError, KeyError):
            raise legacy.HumanReviewError("source_target_unavailable") from None
        legacy.require(all(candidate[field] == str(target.get(field) or "") for field in legacy.TARGET_FIELDS), "resolved_target_mismatch")
        sentence = target.get("sentence_text")
        legacy.text(sentence, "invalid_candidate_source", 1000)
        legacy.require(target.get("sentence_text_sha256") == review["sentence_text_sha256"] == legacy.digest(sentence.encode("utf-8")), "resolved_sentence_hash_mismatch")
        matches = [model for model in originals[corpus] if model.get("id") == review["candidate_record_id"]]
        legacy.require(len(matches) == 1, "candidate_model_record_not_found")
        model = matches[0]
        legacy.require(model.get("record_type") == "ai_sentence_translation" and model.get("translation") == candidate.get("translation"), "candidate_model_mismatch")
        legacy.text(model.get("translation"), "invalid_candidate_translation")
        legacy.require(legacy.digest(model["translation"].encode("utf-8")) == review["candidate_translation_sha256"], "candidate_translation_hash_mismatch")
        legacy.require(all(str(model.get(field) or "") == str(target.get(field) or "") for field in (*legacy.TARGET_FIELDS, "source_text_sha256", "sentence_text_sha256")), "candidate_source_hash_mismatch")
        if record_validator:
            try:
                record_validator(model)
            except (AssertionError, ValueError, TypeError, KeyError):
                raise legacy.HumanReviewError("candidate_record_contract_failed") from None
        # Scores refer to the frozen submitted model notes. A later public
        # safety check may hide them without changing what the evaluator saw.
        raw_notes = model.get("translation_notes", [])
        candidate_notes = grounded_notes(raw_notes, sentence)
        legacy.require(candidate_notes == raw_notes, "invalid_candidate_translation_notes")
        if candidate_notes:
            legacy.require(model.get("note_source_text") == sentence and
                           model.get("commentary_translation_sha256") == translation_hash(model["translation"]),
                           "candidate_note_binding_mismatch")
        legacy.require(bool(candidate_notes) == (review["scores"]["note_accuracy"] is not None), "candidate_note_applicability_mismatch")
        notes = []
        if review["note_action"] == "keep":
            notes = candidate_notes
        elif review["note_action"] == "replace":
            notes = grounded_notes(review["translation_notes"], sentence)
            legacy.require(bool(notes) and notes == review["translation_notes"], "invalid_review_translation_notes")
        entry = {
            "id": identifier, "target": {field: candidate[field] for field in legacy.TARGET_FIELDS},
            "source_text": sentence, "candidate_translation": model["translation"],
            "model_sha256": legacy.digest(legacy.json_bytes(legacy.immutable_model(model))),
            "review": deepcopy(review), "resolved_translation_notes": deepcopy(notes), "note_binding": None,
            "evaluation_history": [],
        }
        if notes and review["decision"] == "confirmed":
            entry["note_binding"] = {"sentence_text_sha256": review["sentence_text_sha256"], "translation_sha256": translation_hash(review["reference_translation"])}
        previous = stored.get(identifier)
        if previous is not None:
            legacy.require(previous["target"] == entry["target"] and previous["source_text"] == sentence, "review_store_target_conflict")
            if previous["review"]["candidate_record_id"] == review["candidate_record_id"]:
                legacy.require(previous["model_sha256"] == entry["model_sha256"], "candidate_model_mismatch")
            entry["evaluation_history"] = deepcopy(previous["evaluation_history"])
            if previous == entry:
                continue
            reject_stale_review(review, previous["review"])
            snapshot = deepcopy(previous)
            snapshot["evaluation_history"] = []
            entry["evaluation_history"].append(snapshot)
            store["cases"][store["cases"].index(previous)] = entry
        else:
            store["cases"].append(entry)
        changed_cases += 1
    validate_store(store)
    after = legacy.json_bytes(store)
    legacy.require(len(after) <= legacy.MAX_INPUT_BYTES, "file_size_limit")
    mutations = [{"path": store_path, "before": before, "after": after}] if changed_cases else []
    summary = {
        "cases": len(reviews), "changed_cases": changed_cases, "changed_files": len(mutations),
        "confirmed": sum(r["decision"] == "confirmed" for r in reviews.values()),
        "held": sum(r["decision"] == "held" for r in reviews.values()),
        "notes_not_applicable": sum(r["scores"]["note_accuracy"] is None for r in reviews.values()),
        "ai_evaluations": sum(r["evaluator_kind"] == "ai" for r in reviews.values()),
        "ai_assisted_evaluations": sum(r["evaluator_kind"] == "ai_assisted" for r in reviews.values()),
        "operational_records_changed": 0,
    }
    return mutations, summary


def import_review_batch(feedback_path: Path, candidates_path: Path, candidate_ai_dir: Path, store_path: Path, transaction_dir: Path, *, apply: bool = False, target_resolver: Callable = sentence_target_bundle, record_validator: Callable | None = None) -> dict:
    paths = [feedback_path, candidates_path, candidate_ai_dir, store_path, transaction_dir]
    legacy.require(not any(path.is_symlink() for path in paths), "symlink_input_or_target")
    feedback_path, candidates_path, candidate_ai_dir, store_path, transaction_dir = [path.resolve() for path in paths]
    feedback_raw = legacy.read_bytes(feedback_path, legacy.MAX_INPUT_BYTES)
    candidates_raw = legacy.read_bytes(candidates_path, legacy.MAX_INPUT_BYTES)
    reviews = feedback_cases(legacy.parse_json(feedback_raw))
    candidates = candidate_cases(legacy.parse_json(candidates_raw))
    legacy.require(set(reviews) <= set(candidates), "selected_case_not_found")
    corpora = {candidates[identifier].get("corpus_id") for identifier in reviews}
    legacy.require(corpora <= legacy.CORPORA, "invalid_candidate_corpus")
    source_paths = {corpus: candidate_ai_dir / f"{corpus}_sentence_translations.jsonl" for corpus in sorted(corpora)}
    inputs = {feedback_path, candidates_path, *source_paths.values()}
    legacy.require(store_path not in inputs and not any(path.is_relative_to(transaction_dir) for path in {*inputs, store_path}), "input_target_alias")
    input_hash = legacy.digest(legacy.json_bytes({"feedback_sha256": legacy.digest(feedback_raw), "candidates_sha256": legacy.digest(candidates_raw), "source_paths": [str(p) for p in source_paths.values()], "targets": [str(store_path)]}))
    if apply and not (transaction_dir / "pending").exists():
        # Reject bad input before creating write-lock files. Rebuild under locks
        # below so concurrent edits cannot publish a stale preflight plan.
        mutations, summary = build_plan(reviews, candidates, source_paths, store_path, target_resolver=target_resolver, record_validator=record_validator)
        if not mutations:
            return {**summary, "mode": "apply", "status": "no_op", "recovered_previous_attempt": False}
    with ExitStack() as stack:
        stack.enter_context(locked_jsonl(transaction_dir / "import.jsonl", read_only=not apply))
        for path in sorted({store_path, *source_paths.values()}, key=str):
            stack.enter_context(locked_jsonl(path, read_only=not apply or path != store_path))
        legacy.require(legacy.read_bytes(feedback_path, legacy.MAX_INPUT_BYTES) == feedback_raw and legacy.read_bytes(candidates_path, legacy.MAX_INPUT_BYTES) == candidates_raw, "input_changed_during_import")
        resumed = legacy.recover_pending(transaction_dir / "pending", input_hash, {store_path}, apply=apply)
        mutations, summary = build_plan(reviews, candidates, source_paths, store_path, target_resolver=target_resolver, record_validator=record_validator)
        summary.update(mode="apply" if apply else "dry_run", status="no_op" if not mutations else "applied" if apply else "ready", recovered_previous_attempt=resumed)
        if apply and mutations:
            legacy.apply_plan(mutations, transaction_dir / "pending", input_hash)
        return summary


def adopted_record(record: dict, entry: dict, approved_by: str, adopted_at: str) -> dict:
    review = entry["review"]
    desired = {
        "review_state": "reviewed", "reviewed_by": approved_by,
        "human_translation": review["reference_translation"],
        "human_translation_base_sha256": legacy.digest(record["translation"].encode("utf-8")),
        "human_evaluation_v2": deepcopy(review),
        "human_translation_notes": {
            "source_text": entry["source_text"], "sentence_text_sha256": review["sentence_text_sha256"],
            "translation_sha256": translation_hash(review["reference_translation"]),
            "notes": deepcopy(entry["resolved_translation_notes"]),
        },
    }
    if record.get("human_evaluation_v2") == review:
        legacy.require(all(record.get(key) == value for key, value in desired.items()), "operational_review_changed_externally")
        return deepcopy(record)
    previous = record.get("human_evaluation_v2")
    if previous is not None:
        validate_review(previous)
        reject_stale_review(review, previous)
    stamp = datetime.fromisoformat(adopted_at.replace("Z", "+00:00"))
    for field in ("reviewed_at", "human_translation_updated_at"):
        if record.get(field):
            legacy.timestamp(record[field])
            legacy.require(stamp >= datetime.fromisoformat(record[field].replace("Z", "+00:00")), "stale_adoption_timestamp")
    updated = deepcopy(record)
    if record.get("human_translation") or record.get("human_evaluation") or previous is not None:
        history = deepcopy(record.get("human_evaluation_history", []))
        legacy.require(isinstance(history, list), "invalid_record_review_history")
        history.append({key: deepcopy(record[key]) for key in legacy.REVIEW_FIELDS - {"human_evaluation_history"} if key in record})
        updated["human_evaluation_history"] = history
    updated.update(desired)
    # Processing time is distinct from the evaluator's date-only submission.
    for field in ("reviewed_at", "updated_at", "human_translation_updated_at"):
        updated[field] = adopted_at
    return updated


def build_adoption_plan(entries: dict[str, dict], source_paths: dict[str, Path], output_paths: dict[str, Path], *, approved_by: str, adopted_at: str, target_resolver: Callable, record_validator: Callable | None) -> tuple[list[dict], dict]:
    models = {corpus: legacy.read_records(legacy.read_bytes(path, legacy.MAX_AI_BYTES)) for corpus, path in source_paths.items()}
    before = {corpus: legacy.read_bytes(path, legacy.MAX_AI_BYTES, missing=True) for corpus, path in output_paths.items()}
    outputs = {corpus: legacy.read_records(value) for corpus, value in before.items()}
    changed = 0
    for entry in entries.values():
        review, target = entry["review"], entry["target"]
        legacy.require(review["decision"] == "confirmed", "held_review_cannot_be_adopted")
        try:
            live = target_resolver(*(target[field] for field in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")))
        except (ValueError, OSError, KeyError):
            raise legacy.HumanReviewError("source_target_unavailable") from None
        legacy.require(all(target[field] == str(live.get(field) or "") for field in legacy.TARGET_FIELDS), "resolved_target_mismatch")
        legacy.require(live.get("sentence_text") == entry["source_text"] and live.get("sentence_text_sha256") == review["sentence_text_sha256"], "resolved_sentence_hash_mismatch")
        corpus = target["corpus_id"]
        matches = [record for record in models[corpus] if record.get("id") == review["candidate_record_id"]]
        legacy.require(len(matches) == 1, "candidate_model_record_not_found")
        model = matches[0]
        legacy.require(legacy.digest(legacy.json_bytes(legacy.immutable_model(model))) == entry["model_sha256"], "candidate_model_mismatch")
        legacy.require(all(str(model.get(field) or "") == str(live.get(field) or "") for field in (*legacy.TARGET_FIELDS, "source_text_sha256", "sentence_text_sha256")), "candidate_source_hash_mismatch")
        current = next((record for record in outputs[corpus] if record.get("id") == model["id"]), None)
        legacy.require(current is None or legacy.immutable_model(current) == legacy.immutable_model(model), "operational_model_conflict")
        approved = adopted_record(current or model, entry, approved_by, adopted_at)
        legacy.require(legacy.immutable_model(approved) == legacy.immutable_model(model), "model_preservation_failed")
        if record_validator:
            try:
                record_validator(approved)
            except (AssertionError, ValueError, TypeError, KeyError):
                raise legacy.HumanReviewError("approved_record_contract_failed") from None
        if approved == current:
            continue
        if current is None:
            outputs[corpus].append(approved)
        else:
            outputs[corpus][outputs[corpus].index(current)] = approved
        changed += 1
    mutations = []
    for corpus, path in output_paths.items():
        after = legacy.changed_record_bytes(before[corpus], outputs[corpus])
        if after != before[corpus]:
            mutations.append({"path": path, "before": before[corpus], "after": after})
    return mutations, {"cases": len(entries), "operational_records_changed": changed, "changed_files": len(mutations)}


def publish_review_cases(store_path: Path, case_ids: list[str], candidate_ai_dir: Path, operational_ai_dir: Path, transaction_dir: Path, *, approved_by: str, adopted_at: str, apply: bool = False, target_resolver: Callable = sentence_target_bundle, record_validator: Callable | None = None) -> dict:
    """Publish only explicitly adopted cases; never infer adoption from a score."""
    legacy.require(isinstance(case_ids, list) and 0 < len(case_ids) <= 64 and all(isinstance(key, str) and key for key in case_ids), "explicit_adoption_cases_required")
    legacy.require(len(set(case_ids)) == len(case_ids), "duplicate_adoption_case")
    legacy.text(approved_by, "invalid_adopter", 200)
    legacy.timestamp(adopted_at)
    paths = [store_path, candidate_ai_dir, operational_ai_dir, transaction_dir]
    legacy.require(not any(path.is_symlink() for path in paths), "symlink_input_or_target")
    store_path, candidate_ai_dir, operational_ai_dir, transaction_dir = [path.resolve() for path in paths]
    raw = legacy.read_bytes(store_path, legacy.MAX_INPUT_BYTES)
    stored = validate_store(legacy.parse_json(raw))
    legacy.require(set(case_ids) <= set(stored), "selected_case_not_found")
    entries = {key: stored[key] for key in case_ids}
    corpora = {entry["target"]["corpus_id"] for entry in entries.values()}
    source_paths = {corpus: candidate_ai_dir / f"{corpus}_sentence_translations.jsonl" for corpus in sorted(corpora)}
    output_paths = {corpus: operational_ai_dir / f"{corpus}_sentence_translations.jsonl" for corpus in sorted(corpora)}
    inputs, targets = {store_path, *source_paths.values()}, set(output_paths.values())
    legacy.require(not inputs.intersection(targets) and not any(path.is_relative_to(transaction_dir) for path in inputs | targets), "input_target_alias")
    input_hash = legacy.digest(legacy.json_bytes({"store_sha256": legacy.digest(raw), "cases": case_ids, "approved_by": approved_by, "adopted_at": adopted_at, "source_paths": [str(p) for p in source_paths.values()], "targets": [str(p) for p in output_paths.values()]}))
    options = dict(approved_by=approved_by, adopted_at=adopted_at, target_resolver=target_resolver, record_validator=record_validator)
    if apply and not (transaction_dir / "pending").exists():
        mutations, summary = build_adoption_plan(entries, source_paths, output_paths, **options)
        if not mutations:
            return {**summary, "mode": "apply", "status": "no_op", "recovered_previous_attempt": False}
    with ExitStack() as stack:
        stack.enter_context(locked_jsonl(transaction_dir / "import.jsonl", read_only=not apply))
        for path in sorted(inputs | targets, key=str):
            stack.enter_context(locked_jsonl(path, read_only=not apply or path not in targets))
        legacy.require(legacy.read_bytes(store_path, legacy.MAX_INPUT_BYTES) == raw, "input_changed_during_import")
        resumed = legacy.recover_pending(transaction_dir / "pending", input_hash, targets, apply=apply)
        mutations, summary = build_adoption_plan(entries, source_paths, output_paths, **options)
        summary.update(mode="apply" if apply else "dry_run", status="no_op" if not mutations else "applied" if apply else "ready", recovered_previous_attempt=resumed)
        if apply and mutations:
            legacy.apply_plan(mutations, transaction_dir / "pending", input_hash)
        return summary
