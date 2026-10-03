"""Primary-text and dictionary meaning checks scoped to one exact sentence."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.source_targets import sha256_text

CHECKS_FILE = Path(__file__).resolve().parents[1] / "data/translation_source_checks.json"


def source_checks(target: dict[str, Any]) -> list[dict[str, Any]]:
    payload = json.loads(CHECKS_FILE.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported source checks schema")
    fields = ("corpus_id", "work_id", "variant_id", "sentence_id", "sentence_text_sha256")
    rules = [rule for rule in payload["rules"] if all(str(rule.get(field, "")) == str(target.get(field, "")) for field in fields)]
    for rule in rules:
        for check in rule.get("meaning_checks", []):
            for field in ("korean_alternatives", "korean_patterns", "forbidden_korean_fragments", "forbidden_korean_patterns"):
                values = check.get(field, [])
                if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                    raise ValueError(f"invalid source meaning check {field}")
            for pattern in check.get("korean_patterns", []) + check.get("forbidden_korean_patterns", []):
                try:
                    re.compile(pattern)
                except re.error:
                    raise ValueError("invalid source meaning check pattern") from None
            if not any(check.get(field) for field in ("korean_alternatives", "korean_patterns", "forbidden_korean_fragments", "forbidden_korean_patterns")):
                raise ValueError("source meaning check requires a condition")
            if check.get("severity", "major") not in {"major", "minor"}:
                raise ValueError("invalid source meaning check severity")
        for check in rule.get("note_checks", []):
            for field in ("forbidden_note_assertions", "forbidden_note_patterns"):
                values = check.get(field, [])
                if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                    raise ValueError(f"invalid source note check {field}")
            for pattern in check.get("forbidden_note_patterns", []):
                try:
                    re.compile(pattern)
                except re.error:
                    raise ValueError("invalid source note check pattern") from None
            if not any(check.get(field) for field in ("forbidden_note_assertions", "forbidden_note_patterns")):
                raise ValueError("source note check requires a condition")
    return rules


def source_evidence_text(target: dict[str, Any]) -> str:
    rules = source_checks(target)
    if not rules:
        return ""
    evidence = "primary text and dictionary evidence" if any(rule.get("primary_text_evidence") for rule in rules) else "dictionary evidence"
    return f"\n\nSource lexical evidence for this exact sentence ({evidence}, not a claim of human translation approval):\n" + "\n".join(f"- {fact}" for rule in rules for fact in rule["lexical_evidence"])


def source_checks_hash(target: dict[str, Any]) -> str:
    return sha256_text(json.dumps(source_checks(target), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def source_meaning_issues(target: dict[str, Any], translation: str) -> list[dict[str, str]]:
    issues = []
    for rule in source_checks(target):
        for check in rule.get("meaning_checks", []):
            alternatives = check.get("korean_alternatives", [])
            patterns = check.get("korean_patterns", [])
            matched = any(fragment in translation for fragment in alternatives) or any(re.search(pattern, translation) for pattern in patterns)
            forbidden = next((fragment for fragment in check.get("forbidden_korean_fragments", []) if fragment in translation), "")
            if not forbidden:
                for pattern in check.get("forbidden_korean_patterns", []):
                    match = re.search(pattern, translation)
                    if match:
                        forbidden = match.group(0)
                        break
            if forbidden or ((alternatives or patterns) and not matched):
                issues.append({"source_span": check["source_span"], "translation_span": forbidden,
                               "category": check.get("category", "omission"), "severity": check.get("severity", "major"),
                               "explanation": check["explanation"]})
    return issues


def source_note_issues(target: dict[str, Any], notes: list[dict[str, str]]) -> list[dict[str, str]]:
    """Match complete false assertions, including scoped paraphrase patterns."""
    issues = []
    for rule in source_checks(target):
        for check in rule.get("note_checks", []):
            assertions = {re.sub(r"\s+", " ", assertion).strip() for assertion in check.get("forbidden_note_assertions", [])}
            for note in notes:
                assertion = re.sub(r"\s+", " ", note["note"]).strip()
                if assertion in assertions or any(re.fullmatch(pattern, assertion) for pattern in check.get("forbidden_note_patterns", [])):
                    issues.append({"source_span": check["source_span"], "translation_span": "",
                                   "category": "syntax_or_scope", "severity": "major",
                                   "explanation": check["explanation"]})
    return issues
