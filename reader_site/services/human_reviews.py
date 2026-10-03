from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from services import sentence_translations as translations
from services.jsonl_storage import _sync_directory, locked_jsonl
from services.sentence_targets import sentence_target_bundle


CORPORA = {"bible", "kierkegaard", "nietzsche", "wittgenstein"}
DIMENSIONS = ("fidelity", "completeness", "terminology", "korean_readability")
TARGET_FIELDS = ("corpus_id", "work_id", "variant_id", "segment_id", "sentence_id")
REVIEW_FIELDS = {
    "review_state", "reviewed_at", "updated_at", "reviewed_by", "human_translation",
    "human_translation_updated_at", "human_translation_base_sha256", "human_evaluation",
    "human_evaluation_history", "human_evaluation_v2", "human_translation_notes",
}
GOLD_REVIEW_FIELDS = ("candidate_record_id", "candidate_translation", "reference_translation", "human_evaluation")
FORBIDDEN_GOLD_KEYS = {
    "body", "content", "full_text", "html", "text_raw", "model", "model_id", "model_name",
    "path", "runtime", "runtime_id", "source_path", "source_root",
}
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_AI_BYTES = 256 * 1024 * 1024


class HumanReviewError(ValueError):
    """A content-free error code suitable for CLI output."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise HumanReviewError(code)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_bytes(path: Path, limit: int, *, missing: bool = False) -> bytes | None:
    require(not path.is_symlink(), "symlink_input_or_target")
    try:
        require(path.stat().st_size <= limit, "file_size_limit")
        with path.open("rb") as handle:
            value = handle.read(limit + 1)
        require(len(value) <= limit, "file_size_limit")
        return value
    except FileNotFoundError:
        if missing:
            return None
        raise HumanReviewError("required_file_missing") from None


def parse_json(value: bytes) -> Any:
    def object_pairs(pairs):
        result = {}
        for key, child in pairs:
            require(key not in result, "duplicate_json_field")
            result[key] = child
        return result
    try:
        return json.loads(value, object_pairs_hook=object_pairs)
    except (ValueError, UnicodeError):
        raise HumanReviewError("invalid_json") from None


def text(value: Any, code: str, limit: int = 4000) -> None:
    require(isinstance(value, str) and bool(value.strip()) and "\0" not in value and len(value) <= limit, code)


def timestamp(value: Any) -> None:
    text(value, "invalid_evaluation_timestamp", 100)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HumanReviewError("invalid_evaluation_timestamp") from None
    require(stamp.tzinfo is not None, "evaluation_timestamp_needs_timezone")


def scores(value: Any) -> None:
    require(isinstance(value, dict) and set(value) == set(DIMENSIONS), "invalid_scores")
    require(all(type(score) is int and 1 <= score <= 5 for score in value.values()), "invalid_scores")


def record_uuid(value: Any) -> None:
    require(isinstance(value, str), "invalid_candidate_uuid")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise HumanReviewError("invalid_candidate_uuid") from None
    require(str(parsed) == value and parsed.version == 4, "invalid_candidate_uuid")


def unique_by_id(items: Any, code: str) -> dict[str, dict]:
    require(isinstance(items, list) and bool(items), code)
    result = {}
    for item in items:
        require(isinstance(item, dict), code)
        text(item.get("id"), code, 200)
        require(item["id"] not in result, code)
        result[item["id"]] = item
    return result


def feedback_cases(feedback: Any) -> dict[str, dict]:
    require(isinstance(feedback, dict) and type(feedback.get("schema_version")) is int and feedback["schema_version"] == 1, "invalid_feedback_schema")
    require(set(feedback) <= {"schema_version", "evaluator", "evaluated_at", "score_order", "cases"}, "unknown_feedback_field")
    text(feedback.get("evaluator"), "invalid_evaluator", 200)
    timestamp(feedback.get("evaluated_at"))
    require(feedback.get("score_order", list(DIMENSIONS)) == list(DIMENSIONS), "invalid_score_order")
    cases = unique_by_id(feedback.get("cases"), "invalid_feedback_cases")
    require(len(cases) <= 64, "too_many_feedback_cases")
    for case in cases.values():
        require(set(case) <= {"id", "sample_label", "candidate_record_id", "scores", "reference_translation", "notes"}, "unknown_feedback_case_field")
        record_uuid(case.get("candidate_record_id"))
        scores(case.get("scores"))
        text(case.get("reference_translation"), "invalid_reference_translation")
        require(isinstance(case.get("notes"), str) and "\0" not in case["notes"] and len(case["notes"]) <= 12000, "invalid_evaluation_notes")
    return cases


def validate_goldset(gold: Any) -> None:
    require(isinstance(gold, dict) and gold.get("schema_version") == 1, "invalid_goldset_schema")
    rubric = gold.get("rubric", {})
    require(isinstance(rubric, dict) and isinstance(rubric.get("dimensions"), dict), "invalid_goldset_rubric")
    require(set(rubric["dimensions"]) == set(DIMENSIONS) and rubric.get("scale") == {"min": 1, "max": 5}, "invalid_goldset_rubric")
    require(type(rubric.get("passing_score_per_dimension")) is int and 1 <= rubric["passing_score_per_dimension"] <= 5, "invalid_goldset_rubric")
    cases = unique_by_id(gold.get("cases"), "invalid_goldset_cases")
    require(len(cases) <= 64 and {case.get("corpus_id") for case in cases.values()} == CORPORA, "invalid_goldset_coverage")
    require(sum(len(case.get("source_text", "")) for case in cases.values() if isinstance(case.get("source_text"), str)) <= 20000, "goldset_source_size_limit")
    for case in cases.values():
        for field in ("work_id", "segment_id", "sentence_id"):
            text(case.get(field), "invalid_goldset_target", 300)
        text(case.get("source_text"), "goldset_source_size_limit", 1000)
        text(case.get("candidate_translation"), "goldset_translation_size_limit")
        reference = case.get("reference_translation", "")
        require(isinstance(reference, str) and len(reference) <= 4000, "goldset_translation_size_limit")
        evaluation = case.get("human_evaluation")
        require(isinstance(evaluation, dict) and evaluation.get("status") in {"pending", "evaluated"}, "invalid_goldset_evaluation")
        if evaluation["status"] == "pending":
            require(not reference.strip() and not evaluation.get("scores"), "invalid_pending_evaluation")
        else:
            text(reference, "invalid_reference_translation")
            text(evaluation.get("evaluator"), "invalid_evaluator", 200)
            timestamp(evaluation.get("evaluated_at"))
            scores(evaluation.get("scores"))
            require(isinstance(evaluation.get("notes"), str), "invalid_evaluation_notes")

    def walk(value: Any, pointer: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower()
                require(normalized not in FORBIDDEN_GOLD_KEYS and "prompt" not in normalized and "runtime" not in normalized, "forbidden_goldset_metadata")
                child_pointer = f"{pointer}.{key}" if pointer else key
                require(key != "source_text" or re.fullmatch(r"cases\[\d+\]\.source_text", child_pointer) is not None, "unbounded_goldset_source")
                walk(child, child_pointer)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{pointer}[{index}]")
    walk(gold)
    require(len(json_bytes(gold)) <= 64 * 1024, "goldset_file_size_limit")


def read_records(value: bytes | None) -> list[dict]:
    records = []
    for line in (value or b"").splitlines():
        if not line.strip():
            continue
        record = parse_json(line)
        require(isinstance(record, dict), "invalid_ai_record")
        records.append(record)
    identifiers = [record.get("id") for record in records]
    require(all(isinstance(identifier, str) and identifier for identifier in identifiers), "invalid_ai_record_id")
    require(len(set(identifiers)) == len(identifiers), "duplicate_ai_record_id")
    return records


def immutable_model(record: dict) -> dict:
    return {key: value for key, value in record.items() if key not in REVIEW_FIELDS}


def reject_stale_review(evaluation: dict, existing: dict) -> None:
    incoming = datetime.fromisoformat(evaluation["evaluated_at"].replace("Z", "+00:00"))
    previous = existing.get("human_evaluation", {})
    values = [previous.get("evaluated_at")] if isinstance(previous, dict) else []
    values.extend(existing.get(field) for field in ("human_translation_updated_at", "reviewed_at"))
    for value in values:
        if value:
            timestamp(value)
            require(incoming >= datetime.fromisoformat(value.replace("Z", "+00:00")), "stale_human_review")


def changed_record_bytes(before: bytes | None, records: list[dict]) -> bytes:
    """Preserve untouched lines byte-for-byte, including a new record's old prefix."""
    remaining = {record["id"]: record for record in records}
    lines = []
    for line in (before or b"").splitlines(keepends=True):
        if not line.strip():
            lines.append(line)
            continue
        original = parse_json(line)
        updated = remaining.pop(original["id"])
        if original == updated:
            lines.append(line)
        else:
            ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b""
            lines.append(json.dumps(updated, ensure_ascii=False, sort_keys=True).encode("utf-8") + ending)
    value = b"".join(lines)
    if remaining and value and not value.endswith(b"\n"):
        value += b"\n"
    value += b"".join((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for record in remaining.values())
    require(len(value) <= MAX_AI_BYTES, "file_size_limit")
    return value


def reviewed_record(record: dict, evaluation: dict, reference: str) -> dict:
    desired = {
        "review_state": "reviewed", "reviewed_by": evaluation["evaluator"],
        "human_translation": reference, "human_translation_base_sha256": digest(record["translation"].encode("utf-8")),
        "human_evaluation": evaluation,
    }
    if all(record.get(key) == value for key, value in desired.items()):
        return deepcopy(record)
    reject_stale_review(evaluation, record)
    updated = deepcopy(record)
    if record.get("human_evaluation") is not None or record.get("human_translation") or record.get("review_state") == "reviewed":
        history = deepcopy(record.get("human_evaluation_history", []))
        require(isinstance(history, list), "invalid_record_review_history")
        history.append({key: deepcopy(record[key]) for key in REVIEW_FIELDS - {"human_evaluation_history"} if key in record})
        updated["human_evaluation_history"] = history
    updated.update(deepcopy(desired))
    for field in ("reviewed_at", "updated_at", "human_translation_updated_at"):
        updated[field] = evaluation["evaluated_at"]
    return updated


def build_plan(
    feedback: dict, candidates: dict[str, dict], source_paths: dict[str, Path], output_paths: dict[str, Path],
    goldset_path: Path, *, target_resolver: Callable, record_validator: Callable | None,
) -> tuple[list[dict], dict]:
    reviews = feedback_cases(feedback)
    gold_before = read_bytes(goldset_path, 64 * 1024)
    gold = parse_json(gold_before)
    validate_goldset(gold)
    gold_cases = unique_by_id(gold["cases"], "invalid_goldset_cases")
    originals = {corpus: read_records(read_bytes(path, MAX_AI_BYTES)) for corpus, path in source_paths.items()}
    before = {corpus: read_bytes(path, MAX_AI_BYTES, missing=True) for corpus, path in output_paths.items()}
    outputs = {corpus: read_records(value) for corpus, value in before.items()}
    gold_changed = False
    new_records = 0
    for identifier, review in reviews.items():
        require(identifier in candidates and identifier in gold_cases, "selected_case_not_found")
        candidate = candidates[identifier]
        require(candidate.get("candidate_record_id") == review["candidate_record_id"], "candidate_selection_mismatch")
        corpus = candidate.get("corpus_id")
        require(corpus in CORPORA, "invalid_candidate_corpus")
        for field in TARGET_FIELDS:
            require(isinstance(candidate.get(field), str), "invalid_candidate_target")
        text(candidate.get("candidate_translation"), "invalid_candidate_translation")
        text(candidate.get("source_text"), "invalid_candidate_source", 1000)
        gold_case = gold_cases[identifier]
        require(all(str(candidate.get(field) or "") == str(gold_case.get(field) or "") for field in TARGET_FIELDS), "goldset_target_mismatch")
        require(candidate["source_text"] == gold_case["source_text"], "goldset_source_mismatch")
        if "sample_label" in review:
            require(review["sample_label"] == candidate.get("sample_label"), "sample_label_mismatch")
        try:
            target = target_resolver(*(candidate[field] for field in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")))
        except (ValueError, OSError, KeyError):
            raise HumanReviewError("source_target_unavailable") from None
        require(all(str(candidate[field]) == str(target.get(field) or "") for field in TARGET_FIELDS), "resolved_target_mismatch")
        require(candidate["source_text"] == target.get("sentence_text"), "resolved_sentence_mismatch")
        require(target.get("sentence_text_sha256") == digest(candidate["source_text"].encode("utf-8")), "resolved_sentence_hash_mismatch")
        matches = [record for record in originals[corpus] if record.get("id") == review["candidate_record_id"]]
        require(len(matches) == 1, "candidate_model_record_not_found")
        model = matches[0]
        require(model.get("record_type") == "ai_sentence_translation" and model.get("translation") == candidate["candidate_translation"], "candidate_model_mismatch")
        require(all(str(model.get(field) or "") == str(target.get(field) or "") for field in (*TARGET_FIELDS, "source_text_sha256", "sentence_text_sha256")), "candidate_source_hash_mismatch")
        if record_validator:
            try:
                record_validator(model)
            except (AssertionError, ValueError, TypeError, KeyError):
                raise HumanReviewError("candidate_record_contract_failed") from None
        evaluation = {"status": "evaluated", "evaluator": feedback["evaluator"], "evaluated_at": feedback["evaluated_at"], "scores": deepcopy(review["scores"]), "notes": review["notes"]}
        current = next((record for record in outputs[corpus] if record.get("id") == model["id"]), None)
        require(current is None or immutable_model(current) == immutable_model(model), "operational_model_conflict")
        approved = reviewed_record(current if current is not None else model, evaluation, review["reference_translation"])
        require(immutable_model(approved) == immutable_model(model), "model_preservation_failed")
        if record_validator:
            try:
                record_validator(approved)
            except (AssertionError, ValueError, TypeError, KeyError):
                raise HumanReviewError("approved_record_contract_failed") from None
        if current is None:
            outputs[corpus].append(approved)
            new_records += 1
        elif current != approved:
            outputs[corpus][outputs[corpus].index(current)] = approved
        desired_gold = {
            "candidate_record_id": model["id"], "candidate_translation": model["translation"],
            "reference_translation": review["reference_translation"], "human_evaluation": evaluation,
        }
        if any(gold_case.get(key) != value for key, value in desired_gold.items()):
            reject_stale_review(evaluation, gold_case)
            history = deepcopy(gold_case.get("evaluation_history", []))
            require(isinstance(history, list), "invalid_goldset_review_history")
            history.append({key: deepcopy(gold_case[key]) for key in GOLD_REVIEW_FIELDS if key in gold_case})
            gold_case.update(deepcopy(desired_gold), evaluation_history=history)
            gold_changed = True
    validate_goldset(gold)
    mutations = []
    for corpus, path in output_paths.items():
        old_records = read_records(before[corpus])
        if outputs[corpus] != old_records:
            after = changed_record_bytes(before[corpus], outputs[corpus])
            mutations.append({"path": path, "before": before[corpus], "after": after})
    if gold_changed:
        mutations.append({"path": goldset_path, "before": gold_before, "after": json_bytes(gold)})
    summary = {
        "cases": len(reviews), "changed_files": len(mutations), "new_operational_records": new_records,
        "passing_model_candidates": sum(all(score >= gold["rubric"]["passing_score_per_dimension"] for score in review["scores"].values()) for review in reviews.values()),
    }
    return mutations, summary


def atomic_bytes(path: Path, value: bytes | None) -> None:
    if value is None:
        path.unlink(missing_ok=True)
        _sync_directory(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            _sync_directory(path.parent)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if path.suffix == ".jsonl":
        translations._TRANSLATION_SNAPSHOTS.invalidate(path)


def current_digest(path: Path) -> str | None:
    value = read_bytes(path, MAX_AI_BYTES, missing=True)
    return digest(value) if value is not None else None


def archive_pending(pending: Path) -> None:
    pending.rename(pending.with_name(f"backup-{uuid.uuid4()}"))
    _sync_directory(pending.parent)


def recover_pending(pending: Path, input_hash: str, allowed_targets: set[Path], *, apply: bool) -> bool:
    require(not pending.is_symlink(), "symlink_import_journal")
    if not pending.exists():
        return False
    raw = read_bytes(pending / "manifest.json", MAX_INPUT_BYTES, missing=True)
    if raw is None:
        require(apply, "pending_import_requires_apply_to_recover")
        # Target publication starts only after the prepared manifest is durable.
        archive_pending(pending)
        return True
    manifest = parse_json(raw)
    require(isinstance(manifest, dict) and manifest.get("schema_version") == 1, "invalid_import_journal")
    if manifest.get("state") in {"committed", "rolled_back"}:
        if apply:
            archive_pending(pending)
        return False
    require(manifest.get("state") in {"preparing", "prepared"} and manifest.get("input_hash") == input_hash, "pending_import_needs_original_input")
    require(apply, "pending_import_requires_apply_to_recover")
    entries = manifest.get("entries")
    require(isinstance(entries, list) and 0 < len(entries) <= 5, "invalid_import_journal")
    restored = []
    seen = set()
    for index, entry in enumerate(entries):
        require(isinstance(entry, dict) and isinstance(entry.get("path"), str), "invalid_import_journal")
        path = Path(entry["path"])
        require(path in allowed_targets and path not in seen, "invalid_import_journal_target")
        seen.add(path)
        if manifest["state"] == "preparing":
            require(current_digest(path) == entry.get("before_sha256"), "import_target_changed_externally")
            continue
        before = read_bytes(pending / f"{index}.before", MAX_AI_BYTES) if entry.get("before_sha256") is not None else None
        after = read_bytes(pending / f"{index}.after", MAX_AI_BYTES)
        require((digest(before) if before is not None else None) == entry.get("before_sha256") and digest(after) == entry.get("after_sha256"), "import_backup_checksum_mismatch")
        require(current_digest(path) in {entry.get("before_sha256"), entry.get("after_sha256")}, "import_target_changed_externally")
        if current_digest(path) != entry.get("before_sha256"):
            restored.append((path, before))
    for path, before in restored:
        atomic_bytes(path, before)
    manifest["state"] = "rolled_back"
    atomic_bytes(pending / "manifest.json", json_bytes(manifest))
    archive_pending(pending)
    return True


def apply_plan(mutations: list[dict], pending: Path, input_hash: str) -> None:
    pending.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "input_hash": input_hash, "state": "preparing", "entries": [
        {"path": str(mutation["path"]), "before_sha256": digest(mutation["before"]) if mutation["before"] is not None else None, "after_sha256": digest(mutation["after"])}
        for mutation in mutations
    ]}
    try:
        atomic_bytes(pending / "manifest.json", json_bytes(manifest))
        for index, mutation in enumerate(mutations):
            if mutation["before"] is not None:
                atomic_bytes(pending / f"{index}.before", mutation["before"])
            atomic_bytes(pending / f"{index}.after", mutation["after"])
        manifest["state"] = "prepared"
        atomic_bytes(pending / "manifest.json", json_bytes(manifest))
        for mutation, entry in zip(mutations, manifest["entries"]):
            require(current_digest(mutation["path"]) == entry["before_sha256"], "import_target_changed_externally")
            atomic_bytes(mutation["path"], mutation["after"])
        manifest["state"] = "committed"
        atomic_bytes(pending / "manifest.json", json_bytes(manifest))
    except BaseException:
        error_code = "import_failed_rolled_back"
        try:
            saved = read_bytes(pending / "manifest.json", MAX_INPUT_BYTES, missing=True)
            saved_manifest = parse_json(saved) if saved is not None else None
            durable_commit = isinstance(saved_manifest, dict) and saved_manifest.get("state") == "committed"
            restored = recover_pending(pending, input_hash, {mutation["path"] for mutation in mutations}, apply=True)
            if not restored:
                require(durable_commit, "import_recovery_outcome_unverified")
                require(all(current_digest(mutation["path"]) == digest(mutation["after"]) for mutation in mutations), "import_target_changed_externally")
                error_code = "import_failed_committed"
        except BaseException:
            raise HumanReviewError("import_failed_recovery_required") from None
        raise HumanReviewError(error_code) from None
    archive_pending(pending)


def import_human_reviews(
    feedback_path: Path, candidates_path: Path, candidate_ai_dir: Path, operational_ai_dir: Path,
    goldset_path: Path, transaction_dir: Path, *, apply: bool = False,
    target_resolver: Callable = sentence_target_bundle, record_validator: Callable | None = None,
) -> dict:
    paths = [feedback_path, candidates_path, candidate_ai_dir, operational_ai_dir, goldset_path, transaction_dir]
    require(not any(path.is_symlink() for path in paths), "symlink_input_or_target")
    feedback_path, candidates_path, candidate_ai_dir, operational_ai_dir, goldset_path, transaction_dir = [path.resolve() for path in paths]
    feedback_raw = read_bytes(feedback_path, MAX_INPUT_BYTES)
    candidates_raw = read_bytes(candidates_path, MAX_INPUT_BYTES)
    feedback = parse_json(feedback_raw)
    reviews = feedback_cases(feedback)
    candidates = unique_by_id(parse_json(candidates_raw), "invalid_candidates")
    require(set(reviews) <= set(candidates), "selected_case_not_found")
    corpora = {candidates[identifier].get("corpus_id") for identifier in reviews}
    require(corpora <= CORPORA, "invalid_candidate_corpus")
    source_paths = {corpus: candidate_ai_dir / f"{corpus}_sentence_translations.jsonl" for corpus in sorted(corpora)}
    output_paths = {corpus: operational_ai_dir / f"{corpus}_sentence_translations.jsonl" for corpus in sorted(corpora)}
    allowed_targets = {goldset_path, *output_paths.values()}
    require(not allowed_targets.intersection({feedback_path, candidates_path, *source_paths.values()}), "input_target_alias")
    input_hash = digest(json_bytes({"feedback_sha256": digest(feedback_raw), "candidates_sha256": digest(candidates_raw), "source_paths": [str(path) for path in source_paths.values()], "targets": sorted(str(path) for path in allowed_targets)}))
    with ExitStack() as stack:
        stack.enter_context(locked_jsonl(transaction_dir / "import.jsonl", read_only=not apply))
        for path in sorted({goldset_path, *source_paths.values(), *output_paths.values()}, key=str):
            stack.enter_context(locked_jsonl(path, read_only=not apply or path in source_paths.values()))
        require(read_bytes(feedback_path, MAX_INPUT_BYTES) == feedback_raw and read_bytes(candidates_path, MAX_INPUT_BYTES) == candidates_raw, "input_changed_during_import")
        resumed = recover_pending(transaction_dir / "pending", input_hash, allowed_targets, apply=apply)
        mutations, summary = build_plan(feedback, candidates, source_paths, output_paths, goldset_path, target_resolver=target_resolver, record_validator=record_validator)
        summary.update(mode="apply" if apply else "dry_run", status="no_op" if not mutations else "applied" if apply else "ready", recovered_previous_attempt=resumed)
        if apply and mutations:
            apply_plan(mutations, transaction_dir / "pending", input_hash)
        return summary
