from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.source_targets import sha256_text


SITE = Path(__file__).resolve().parents[1]
TRANSLATION_PROFILE_FILE = SITE / "data" / "translation_profiles.json"


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
    for index, profile in enumerate(profiles):
        require(isinstance(profile, dict), f"translation profile {index} must be an object")
        for field in ("profile_id", "corpus_id", "work_id", "approval_state"):
            require(clean_text(profile.get(field)), f"translation profile {index} missing {field}")
        require(profile["approval_state"] == "approved", f"translation profile {index} must be human-approved")
        require(isinstance(profile.get("variant_id", ""), str), f"translation profile {index} has invalid variant_id")
        terminology = profile.get("terminology", [])
        style_notes = profile.get("style_notes", [])
        require(isinstance(terminology, list), f"translation profile {index} terminology must be a list")
        require(isinstance(style_notes, list), f"translation profile {index} style_notes must be a list")
        require(all(isinstance(note, str) and clean_text(note) for note in style_notes), f"translation profile {index} has invalid style_notes")
        for term_index, term in enumerate(terminology):
            require(isinstance(term, dict), f"translation profile {index} term {term_index} must be an object")
            require(clean_text(term.get("source")), f"translation profile {index} term {term_index} missing source")
            require(clean_text(term.get("target")), f"translation profile {index} term {term_index} missing target")
            require(isinstance(term.get("note", ""), str), f"translation profile {index} term {term_index} has invalid note")
        validated.append(profile)
    return validated


def translation_policy_bundle(
    corpus_id: str,
    work_id: str,
    variant_id: str = "",
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
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**snapshot, "policy_sha256": sha256_text(canonical)}


def render_translation_policy(policy: dict[str, Any]) -> str:
    lines: list[str] = []
    terminology = policy.get("terminology", [])
    style_notes = policy.get("style_notes", [])
    if terminology:
        lines.append("Human-approved terminology:")
        for term in terminology:
            note = clean_text(term.get("note"))
            suffix = f" ({note})" if note else ""
            lines.append(f"- {clean_text(term['source'])} -> {clean_text(term['target'])}{suffix}")
    if style_notes:
        lines.append("Human-approved style notes:")
        lines.extend(f"- {clean_text(note)}" for note in style_notes)
    if not lines:
        return "No human-approved work-specific terminology or style rule is registered. Do not invent one."
    return "\n".join(lines)
