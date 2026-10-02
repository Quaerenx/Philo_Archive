"""Local, append-only AI translation evaluations; never human goldset results.

The scored candidate and an AI-selected revision have separate fields. Exact
UTF-8 hashes bind the evaluation to the supplied source, candidate, and notes.
Unknown candidate IDs remain null; a review ID identifies the review only.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from services.jsonl_storage import atomic_write_jsonl, locked_jsonl
from services.source_targets import sha256_text


SITE = Path(__file__).resolve().parents[1]
AI_DIR = Path(os.environ.get("PHILO_AI_DIR", str(SITE / "data" / "ai")))
DEFAULT_PATH = AI_DIR / "translation_ai_reviews.jsonl"
RECORD_TYPE = "ai_translation_review"
RUBRIC_ID = "translation_review_five_dimensions_v1"
RUBRIC_DIMENSIONS = (
    "omission_addition",
    "logic",
    "terminology",
    "korean_readability",
    "note_accuracy",
)
MAX_TEXT_CHARS = 12_000
RECORD_FIELDS = {
    "schema_version", "record_type", "id", "created_at", "evaluation_date",
    "case_id", "reviewer_label", "evaluator_type", "authored_by", "human_approval",
    "source", "scored_candidate", "rubric_id", "rubric_dimensions", "scores",
    "ai_verdict", "revised_translation", "revised_notes", "reason",
    "related_review_ids", "supersedes_review_id", "source_change_reason", "record_sha256",
}
SOURCE_FIELDS = {
    "corpus_id", "work_id", "variant_id", "segment_id", "sentence_id",
    "text", "text_sha256", "boundary_status",
}
CANDIDATE_FIELDS = {"candidate_id", "translation", "translation_sha256", "notes", "notes_sha256"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_text(value: Any, field: str, *, allow_empty: bool = False) -> None:
    require(isinstance(value, str), f"{field} must be a string")
    require(allow_empty or bool(value.strip()), f"{field} must not be empty")
    require(len(value) <= MAX_TEXT_CHARS, f"{field} exceeds {MAX_TEXT_CHARS} characters")


def require_fields(value: Any, fields: set[str], field: str) -> None:
    require(isinstance(value, dict), f"{field} must be an object")
    require(set(value) == fields, f"{field} has missing or unexpected fields")


def require_uuid(value: Any, field: str) -> None:
    require(isinstance(value, str), f"{field} must be a canonical UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a canonical UUID") from exc
    require(str(parsed) == value, f"{field} must be a canonical UUID")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def review_sha256(record: dict[str, Any]) -> str:
    """Integrity checksum, not proof of authorship or human approval."""
    return sha256_text(canonical_json({key: value for key, value in record.items() if key != "record_sha256"}))


def validate_notes(notes: Any, field: str) -> None:
    require(isinstance(notes, list), f"{field} must be a list")
    require(len(notes) <= 100, f"{field} has too many entries")
    for index, note in enumerate(notes):
        label = f"{field}[{index}]"
        require_fields(note, {"source_quote", "explanation"}, label)
        # A candidate may contain an incorrect quotation: preserve it as scored
        # evidence instead of silently fixing it or refusing its evaluation.
        require_text(note["source_quote"], f"{label}.source_quote", allow_empty=True)
        require_text(note["explanation"], f"{label}.explanation")


def validate_review(record: Any) -> None:
    """Validate one record. History/link checks additionally need load_reviews."""
    require_fields(record, RECORD_FIELDS, "review")
    require(type(record["schema_version"]) is int and record["schema_version"] == 1, "unsupported schema_version")
    require(record["record_type"] == RECORD_TYPE, "invalid record_type")
    require_uuid(record["id"], "id")
    require_text(record["created_at"], "created_at")
    try:
        created_at = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at must be an ISO timestamp with a timezone") from exc
    require(created_at.tzinfo is not None and created_at.utcoffset() is not None, "created_at requires a timezone")
    require_text(record["evaluation_date"], "evaluation_date")
    try:
        evaluated_on = date.fromisoformat(record["evaluation_date"])
    except ValueError as exc:
        raise ValueError("evaluation_date must be YYYY-MM-DD") from exc
    require(evaluated_on.isoformat() == record["evaluation_date"], "evaluation_date must be YYYY-MM-DD")
    for field in ("case_id", "reviewer_label", "authored_by", "reason"):
        require_text(record[field], field)
    require(record["evaluator_type"] == "ai", "evaluator_type must be ai")
    require(record["human_approval"] == "pending", "AI reviews must keep human_approval pending")

    source = record["source"]
    require_fields(source, SOURCE_FIELDS, "source")
    for field in ("corpus_id", "work_id", "text"):
        require_text(source[field], f"source.{field}")
    require(re.fullmatch(r"[A-Za-z0-9_-]+", source["corpus_id"]) is not None, "invalid source.corpus_id")
    require_text(source["variant_id"], "source.variant_id", allow_empty=True)
    for field in ("segment_id", "sentence_id"):
        if source[field] is not None:
            require_text(source[field], f"source.{field}")
    require(source["boundary_status"] in ("complete", "incomplete"), "invalid source.boundary_status")
    require(source["text_sha256"] == sha256_text(source["text"]), "source.text_sha256 mismatch")

    candidate = record["scored_candidate"]
    require_fields(candidate, CANDIDATE_FIELDS, "scored_candidate")
    if candidate["candidate_id"] is not None:
        require_uuid(candidate["candidate_id"], "scored_candidate.candidate_id")
    require_text(candidate["translation"], "scored_candidate.translation")
    require(candidate["translation_sha256"] == sha256_text(candidate["translation"]), "scored_candidate.translation_sha256 mismatch")
    validate_notes(candidate["notes"], "scored_candidate.notes")
    require(candidate["notes_sha256"] == sha256_text(canonical_json(candidate["notes"])), "scored_candidate.notes_sha256 mismatch")

    require(record["rubric_id"] == RUBRIC_ID, "invalid rubric_id")
    require(record["rubric_dimensions"] == list(RUBRIC_DIMENSIONS), "rubric_dimensions must preserve the five-dimension order")
    scores = record["scores"]
    require_fields(scores, set(RUBRIC_DIMENSIONS), "scores")
    for dimension in RUBRIC_DIMENSIONS:
        score = scores[dimension]
        if dimension == "note_accuracy" and not candidate["notes"]:
            require(score is None, "note_accuracy must be null when the scored candidate has no notes")
        else:
            require(type(score) is int and 1 <= score <= 5, f"scores.{dimension} must be an integer from 1 through 5")

    verdict = record["ai_verdict"]
    require(verdict in ("hold", "accept_candidate", "adopt_revision"), "invalid ai_verdict")
    if source["boundary_status"] == "incomplete":
        require(verdict == "hold", "an incomplete source boundary requires ai_verdict hold")
    revised_translation = record["revised_translation"]
    if revised_translation is not None:
        require_text(revised_translation, "revised_translation")
        require(revised_translation != candidate["translation"], "revised_translation must differ from the scored candidate")
    if verdict == "adopt_revision":
        require(revised_translation is not None, "adopt_revision requires revised_translation")
    elif verdict == "accept_candidate":
        require(revised_translation is None, "accept_candidate cannot adopt a revised_translation")
    validate_notes(record["revised_notes"], "revised_notes")

    related = record["related_review_ids"]
    require(isinstance(related, list), "related_review_ids must be a list")
    for linked_id in related:
        require_uuid(linked_id, "related_review_ids entry")
        require(linked_id != record["id"], "a review cannot link to itself")
    require(len(related) == len(set(related)), "duplicate related_review_ids")
    supersedes = record["supersedes_review_id"]
    if supersedes is not None:
        require_uuid(supersedes, "supersedes_review_id")
        require(supersedes != record["id"], "a review cannot supersede itself")
        require(supersedes not in related, "use either related or supersedes for the same review")
    if record["source_change_reason"] is not None:
        require_text(record["source_change_reason"], "source_change_reason")
    require(record["record_sha256"] == review_sha256(record), "record_sha256 mismatch")


def build_review(
    case_id: str,
    corpus_id: str,
    work_id: str,
    source_text: str,
    candidate_translation: str,
    scores: dict[str, int | None],
    ai_verdict: str,
    reason: str,
    *,
    candidate_id: str | None = None,
    candidate_notes: list[dict[str, str]] | None = None,
    revised_translation: str | None = None,
    revised_notes: list[dict[str, str]] | None = None,
    source_status: str = "complete",
    variant_id: str = "",
    segment_id: str | None = None,
    sentence_id: str | None = None,
    reviewer_label: str = "LSHD",
    authored_by: str = "ChatGPT",
    evaluation_date: str | None = None,
    related_review_ids: list[str] | None = None,
    supersedes_review_id: str | None = None,
    source_change_reason: str | None = None,
    review_id: str | None = None,
) -> dict[str, Any]:
    """Construct a review without inventing an unknown model candidate ID."""
    now = datetime.now(timezone.utc)
    notes = copy.deepcopy(candidate_notes if candidate_notes is not None else [])
    record = {
        "schema_version": 1,
        "record_type": RECORD_TYPE,
        "id": review_id if review_id is not None else str(uuid.uuid4()),
        "created_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "evaluation_date": evaluation_date if evaluation_date is not None else now.date().isoformat(),
        "case_id": case_id,
        "reviewer_label": reviewer_label,
        "evaluator_type": "ai",
        "authored_by": authored_by,
        "human_approval": "pending",
        "source": {
            "corpus_id": corpus_id, "work_id": work_id, "variant_id": variant_id,
            "segment_id": segment_id, "sentence_id": sentence_id,
            "text": source_text, "text_sha256": sha256_text(source_text), "boundary_status": source_status,
        },
        "scored_candidate": {
            "candidate_id": candidate_id,
            "translation": candidate_translation,
            "translation_sha256": sha256_text(candidate_translation),
            "notes": notes,
            "notes_sha256": sha256_text(canonical_json(notes)),
        },
        "rubric_id": RUBRIC_ID,
        "rubric_dimensions": list(RUBRIC_DIMENSIONS),
        "scores": copy.deepcopy(scores),
        "ai_verdict": ai_verdict,
        "revised_translation": revised_translation,
        "revised_notes": copy.deepcopy(revised_notes if revised_notes is not None else []),
        "reason": reason,
        "related_review_ids": list(related_review_ids if related_review_ids is not None else []),
        "supersedes_review_id": supersedes_review_id,
        "source_change_reason": source_change_reason,
    }
    record["record_sha256"] = review_sha256(record)
    validate_review(record)
    return record


def _candidate_binding(record: dict[str, Any]) -> str:
    return canonical_json({"case_id": record["case_id"], "source": record["source"], "candidate": record["scored_candidate"]})


def _content_identity(record: dict[str, Any]) -> str:
    return canonical_json({key: value for key, value in record.items() if key not in {"id", "created_at", "record_sha256"}})


def validate_history(records: list[dict[str, Any]]) -> None:
    seen: dict[str, dict[str, Any]] = {}
    candidate_bindings: dict[str, str] = {}
    content_identities: set[str] = set()
    for record in records:
        validate_review(record)
        record_id = record["id"]
        require(record_id not in seen, f"duplicate review id: {record_id}")
        identity = _content_identity(record)
        require(identity not in content_identities, "duplicate review content under a different id")
        binding = _candidate_binding(record)
        candidate_id = record["scored_candidate"]["candidate_id"]
        if candidate_id is not None:
            require(candidate_id not in candidate_bindings or candidate_bindings[candidate_id] == binding,
                    "candidate_id is already bound to a different source, translation, or notes")
            candidate_bindings[candidate_id] = binding

        changed_source = False
        for linked_id in record["related_review_ids"]:
            require(linked_id in seen, f"related review must already exist: {linked_id}")
            previous = seen[linked_id]
            require(previous["case_id"] == record["case_id"], "related review must refer to the same case_id")
            for field in ("corpus_id", "work_id", "variant_id"):
                require(previous["source"][field] == record["source"][field], f"related review source.{field} mismatch")
            changed_source = changed_source or previous["source"] != record["source"]
        if changed_source:
            require(record["source_change_reason"] is not None, "a related source change requires source_change_reason")
        else:
            require(record["source_change_reason"] is None, "source_change_reason requires a related review with a changed source")

        supersedes = record["supersedes_review_id"]
        if supersedes is not None:
            require(supersedes in seen, f"superseded review must already exist: {supersedes}")
            require(_candidate_binding(seen[supersedes]) == binding,
                    "supersedes requires the same source and scored candidate; use related_review_ids for a new source or candidate")
        seen[record_id] = record
        content_identities.add(identity)


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_reviews(path: Path | None = None) -> list[dict[str, Any]]:
    """Read without repairing, skipping, or rewriting invalid history."""
    path = Path(path) if path is not None else DEFAULT_PATH
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, object_pairs_hook=unique_json_object)
            validate_review(record)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        records.append(record)
    validate_history(records)
    return records


def append_review(record: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Append an immutable review; replaying the exact same ID/content is a no-op.

    The shared JSONL helper handles atomic replacement. A SQLite lock sidecar
    also serializes separate CLI processes on Windows and Unix, so simultaneous
    imports cannot overwrite each other's history. No human record is touched.
    """
    record = copy.deepcopy(record)
    validate_review(record)
    path = Path(path) if path is not None else DEFAULT_PATH
    require(path.suffix == ".jsonl", "AI review storage must be a .jsonl file")
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_jsonl(path):
        connection = sqlite3.connect(str(path) + ".lock.sqlite", timeout=30)
        try:
            connection.execute("BEGIN IMMEDIATE")
            records = load_reviews(path)
            for previous in records:
                if previous["id"] == record["id"]:
                    require(previous == record, "review id already exists with different content; history is immutable")
                    return {"record": previous, "created": False}
            validate_history([*records, record])
            atomic_write_jsonl(path, [*records, record])
            connection.commit()
        finally:
            connection.close()
    return {"record": record, "created": True}
