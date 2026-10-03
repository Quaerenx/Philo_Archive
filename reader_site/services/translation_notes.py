"""Source-grounded notes bound to the exact translation they explain."""
from __future__ import annotations

import re
from typing import Any

from services.source_targets import sha256_text
from services.translation_source_checks import source_note_issues


INTERNAL_NOTE_LANGUAGE = re.compile(
    r"prompt|pipeline|system\s+rules?|approved\s+(?:policy|terminology)|translation\s+(?:policy|instructions)"
    r"|프롬프트|파이프라인|시스템\s*(?:규칙|지침)|승인된?\s*(?:번역\s*)?(?:정책|지침|용어)|지침에\s*(?:따라|명시)|정책에\s*(?:따라|명시)",
    re.IGNORECASE,
)


def translation_hash(text: Any) -> str:
    return sha256_text(re.sub(r"\s+", " ", str(text or "")).strip())


def grounded_notes(notes: Any, source: str) -> list[dict[str, str]]:
    """Fail closed for an unquoted source span or leaked implementation language."""
    if not isinstance(notes, list) or len(notes) > 3:
        return []
    result = []
    source = re.sub(r"\s+", " ", source).strip()
    for item in notes:
        if not isinstance(item, dict) or set(item) != {"source_span", "note"}:
            return []
        if not all(isinstance(value, str) for value in item.values()):
            return []
        span = re.sub(r"\s+", " ", item["source_span"]).strip()
        note = item["note"].strip()
        if not span or len(span) > 500 or span not in source or not note or len(note) > 1500:
            return []
        if not re.search(r"[가-힣]", note) or INTERNAL_NOTE_LANGUAGE.search(note):
            return []
        result.append({"source_span": span, "note": note})
    return result


def visible_notes(record: dict[str, Any]) -> tuple[str, str, list[dict[str, str]]]:
    current = record.get("human_translation") or record.get("translation") or ""
    if "human_translation_notes" in record:
        binding = record["human_translation_notes"]
        if not isinstance(binding, dict) or not isinstance(binding.get("source_text"), str):
            return "source_changed", "", []
        if binding.get("translation_sha256") != translation_hash(current):
            return "translation_changed", "", []
        if binding.get("sentence_text_sha256") != record.get("sentence_text_sha256") or sha256_text(binding["source_text"]) != record.get("sentence_text_sha256"):
            return "source_changed", "", []
        notes = grounded_notes(binding.get("notes"), binding["source_text"])
        if not notes or notes != binding.get("notes"):
            return "none", "", []
        if source_note_issues(record, notes):
            return "notes_review_required", "", []
        return "current", "\n".join(item["note"] for item in notes), notes
    bound = record.get("commentary_translation_sha256")
    if not bound:
        if record.get("commentary") and record.get("human_translation") and translation_hash(current) != translation_hash(record.get("translation")):
            return "translation_changed", "", []
        return "legacy_unverified" if record.get("commentary") else "none", "", []
    if bound != translation_hash(current):
        return "translation_changed", "", []
    if sha256_text(str(record.get("note_source_text") or "")) != record.get("sentence_text_sha256"):
        return "source_changed", "", []
    notes = grounded_notes(record.get("translation_notes", []), str(record.get("note_source_text") or ""))
    # Newly generated notes retain the exact selected sentence for validation.
    if not notes:
        return "none", "", []
    if source_note_issues(record, notes):
        return "notes_review_required", "", []
    return "current", "\n".join(item["note"] for item in notes), notes
