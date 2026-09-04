from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from services.source_targets import sha256_text


SITE = Path(__file__).resolve().parents[1]
TRANSLATION_PROFILE_FILE = SITE / "data" / "translation_profiles.json"
POLICY_ISSUE_CATEGORIES = {
    "omission",
    "unsupported_addition",
    "semantic_substitution",
    "syntax_or_scope",
    "negation_or_modality",
    "ambiguity_resolution",
    "referent",
    "metaphor_or_rhetoric",
    "terminology",
    "register",
    "korean_readability",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_translation_profiles(path: Path = TRANSLATION_PROFILE_FILE) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "translation profile payload must be an object")
    require(payload.get("schema_version") == 1, "translation profile schema_version must be 1")
    profiles = payload.get("profiles")
    require(isinstance(profiles, list), "translation profile payload must include profiles")

    validated: list[dict[str, Any]] = []
    seen_profile_ids: set[str] = set()
    seen_scopes: set[tuple[str, str, str]] = set()
    for index, profile in enumerate(profiles):
        require(isinstance(profile, dict), f"translation profile {index} must be an object")
        for field in ("profile_id", "corpus_id", "work_id", "approval_state"):
            require(clean_text(profile.get(field)), f"translation profile {index} missing {field}")
        require(profile["approval_state"] == "approved", f"translation profile {index} must be human-approved")
        require(isinstance(profile.get("variant_id", ""), str), f"translation profile {index} has invalid variant_id")
        profile_id = clean_text(profile["profile_id"])
        scope = (
            clean_text(profile["corpus_id"]),
            clean_text(profile["work_id"]),
            clean_text(profile.get("variant_id", "")),
        )
        require(profile_id not in seen_profile_ids, f"duplicate translation profile_id: {profile_id}")
        require(scope not in seen_scopes, f"duplicate approved translation profile scope: {'/'.join(scope)}")
        seen_profile_ids.add(profile_id)
        seen_scopes.add(scope)
        if "approved_by" in profile:
            require(clean_text(profile.get("approved_by")), f"translation profile {index} has invalid approved_by")
        if "approved_at" in profile:
            require(clean_text(profile.get("approved_at")), f"translation profile {index} has invalid approved_at")
            try:
                datetime.fromisoformat(str(profile["approved_at"]).replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(f"translation profile {index} has invalid approved_at") from error
        if "source_case_ids" in profile:
            source_case_ids = profile["source_case_ids"]
            require(isinstance(source_case_ids, list) and source_case_ids, f"translation profile {index} has invalid source_case_ids")
            require(
                all(isinstance(case_id, str) and clean_text(case_id) for case_id in source_case_ids),
                f"translation profile {index} has invalid source_case_ids",
            )
            require(len(source_case_ids) == len(set(source_case_ids)), f"translation profile {index} has duplicate source_case_ids")
        terminology = profile.get("terminology", [])
        style_notes = profile.get("style_notes", [])
        sentence_rules = profile.get("sentence_rules", [])
        require(isinstance(terminology, list), f"translation profile {index} terminology must be a list")
        require(isinstance(style_notes, list), f"translation profile {index} style_notes must be a list")
        require(isinstance(sentence_rules, list), f"translation profile {index} sentence_rules must be a list")
        require(all(isinstance(note, str) and clean_text(note) for note in style_notes), f"translation profile {index} has invalid style_notes")
        for term_index, term in enumerate(terminology):
            require(isinstance(term, dict), f"translation profile {index} term {term_index} must be an object")
            require(clean_text(term.get("source")), f"translation profile {index} term {term_index} missing source")
            require(clean_text(term.get("target")), f"translation profile {index} term {term_index} missing target")
            require(isinstance(term.get("note", ""), str), f"translation profile {index} term {term_index} has invalid note")
        seen_sentence_ids: set[str] = set()
        for rule_index, rule in enumerate(sentence_rules):
            require(isinstance(rule, dict), f"translation profile {index} sentence rule {rule_index} must be an object")
            sentence_id = clean_text(rule.get("sentence_id"))
            require(sentence_id, f"translation profile {index} sentence rule {rule_index} missing sentence_id")
            require(sentence_id not in seen_sentence_ids, f"translation profile {index} has duplicate sentence rule {sentence_id}")
            seen_sentence_ids.add(sentence_id)
            forbidden = rule.get("forbidden_translation_fragments")
            allowed = rule.get("allowed_translation_fragments", [])
            require(
                isinstance(forbidden, list) and forbidden,
                f"translation profile {index} sentence rule {rule_index} needs forbidden_translation_fragments",
            )
            require(
                isinstance(allowed, list) and all(isinstance(item, str) and clean_text(item) for item in allowed),
                f"translation profile {index} sentence rule {rule_index} has invalid allowed_translation_fragments",
            )
            for fragment_index, fragment in enumerate(forbidden):
                fragment_label = f"translation profile {index} sentence rule {rule_index} fragment {fragment_index}"
                require(isinstance(fragment, dict), f"{fragment_label} must be an object")
                for field in ("text", "category", "severity", "explanation"):
                    require(clean_text(fragment.get(field)), f"{fragment_label} missing {field}")
                require(fragment["category"] in POLICY_ISSUE_CATEGORIES, f"{fragment_label} has invalid category")
                require(fragment["severity"] in {"minor", "major"}, f"{fragment_label} has invalid severity")
        validated.append(profile)
    return validated


def translation_policy_bundle(
    corpus_id: str,
    work_id: str,
    variant_id: str = "",
    sentence_id: str = "",
    path: Path = TRANSLATION_PROFILE_FILE,
) -> dict[str, Any]:
    candidates = [
        profile
        for profile in read_translation_profiles(path)
        if profile["corpus_id"] == corpus_id
        and profile["work_id"] == work_id
        and profile.get("variant_id", "") in {"", variant_id}
    ]
    candidates.sort(key=lambda profile: profile.get("variant_id", "") == variant_id, reverse=True)
    profile = candidates[0] if candidates else None
    snapshot = {
        "profile_id": str(profile.get("profile_id", "")) if profile else "",
        "approval_state": "approved" if profile else "none",
        "terminology": list(profile.get("terminology", [])) if profile else [],
        "style_notes": list(profile.get("style_notes", [])) if profile else [],
        "sentence_rules": [
            rule
            for rule in profile.get("sentence_rules", [])
            if clean_text(rule.get("sentence_id")) == clean_text(sentence_id)
        ] if profile and sentence_id else [],
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**snapshot, "policy_sha256": sha256_text(canonical)}


def render_translation_policy(policy: dict[str, Any]) -> str:
    lines: list[str] = []
    terminology = policy.get("terminology", [])
    style_notes = policy.get("style_notes", [])
    sentence_rules = policy.get("sentence_rules", [])
    if terminology:
        lines.append("Human-approved terminology:")
        for term in terminology:
            note = clean_text(term.get("note"))
            suffix = f" ({note})" if note else ""
            lines.append(f"- {clean_text(term['source'])} -> {clean_text(term['target'])}{suffix}")
    if style_notes:
        lines.append("Human-approved style notes:")
        lines.extend(f"- {clean_text(note)}" for note in style_notes)
    if sentence_rules:
        lines.append("Human-approved rules for this exact sentence:")
        for rule in sentence_rules:
            allowed = rule.get("allowed_translation_fragments", [])
            if allowed:
                lines.append(
                    "- These exact Korean fragments are human-approved and must not be flagged merely for their form: "
                    + ", ".join(f"‘{clean_text(fragment)}’" for fragment in allowed)
                )
            for fragment in rule.get("forbidden_translation_fragments", []):
                lines.append(
                    f"- Do not use Korean fragment ‘{clean_text(fragment['text'])}’: "
                    f"{clean_text(fragment['explanation'])}"
                )
    if not lines:
        return "No human-approved work-specific terminology or style rule is registered. Do not invent one."
    return "\n".join(lines)
