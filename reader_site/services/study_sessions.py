from __future__ import annotations

from typing import Any

from services.notes import first_query_value, read_all_notes, safe_note_slug
from services.sentence_translations import sentence_translations_for_export


def markdown_quote(value: Any) -> str:
    return str(value or "").replace("\n", "\n> ")


def session_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    return first_query_value(query, key, default).strip()


def reviewed_note_state(query: dict[str, list[str]]) -> str:
    value = session_query_value(query, "notes_review_state", "reviewed").lower()
    if value == "all":
        return ""
    if value not in {"raw", "reviewed"}:
        raise ValueError("invalid notes_review_state")
    return value


def translation_review_state(query: dict[str, list[str]]) -> str:
    value = session_query_value(query, "translation_review_state", "reviewed").lower()
    if value not in {"generated", "reviewed", "rejected", "all"}:
        raise ValueError("invalid translation_review_state")
    return value


def study_session_payload_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    corpus_id = safe_note_slug(session_query_value(query, "corpus_id") or session_query_value(query, "author"))
    if not corpus_id:
        raise ValueError("missing corpus_id")
    work_id = session_query_value(query, "work_id")
    note_state = reviewed_note_state(query)
    translation_state = translation_review_state(query)
    notes = read_all_notes([corpus_id], work_id=work_id, review_state=note_state)
    translations = sentence_translations_for_export(
        {"corpus_id": [corpus_id], "work_id": [work_id], "review_state": [translation_state]}
    )
    return {
        "ok": True,
        "corpus_id": corpus_id,
        "work_id": work_id,
        "notes_review_state": note_state or "all",
        "translation_review_state": translation_state,
        "note_count": len(notes),
        "translation_count": len(translations),
        "notes": notes,
        "translations": translations,
    }


def export_study_session_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 학습 기록",
        "",
        f"노트 {payload.get('note_count', 0)}개 / 번역 {payload.get('translation_count', 0)}개",
        "",
        "## 노트",
        "",
    ]
    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    if not notes:
        lines.extend(["일치하는 노트가 없습니다.", ""])
    for note in notes:
        target_label = note.get("target_label") or note.get("target_id") or "대상"
        lines.extend([f"### {target_label}", ""])
        if note.get("note"):
            lines.extend([str(note["note"]), ""])
        if note.get("quote"):
            lines.extend(["> " + markdown_quote(note["quote"]), ""])
        note_meta = []
        if note.get("url"):
            note_meta.append(f"출처: {note['url']}")
        tags = ", ".join(str(tag) for tag in note.get("tags", []))
        if tags:
            note_meta.append(f"태그: {tags}")
        if note_meta:
            lines.extend(note_meta)
        lines.append("")

    lines.extend(["## 번역과 해설", ""])
    translations = payload.get("translations") if isinstance(payload.get("translations"), list) else []
    if not translations:
        lines.extend(["일치하는 번역이 없습니다.", ""])
    for record in translations:
        title = " / ".join(
            item
            for item in [
                str(record.get("work_id") or ""),
                str(record.get("sentence_id") or record.get("target_id") or ""),
            ]
            if item
        )
        lines.extend([f"### {title or '문장 번역'}", ""])
        if record.get("translation"):
            lines.extend(["번역", "", str(record["translation"]), ""])
        if record.get("commentary"):
            lines.extend(["해설", "", str(record["commentary"]), ""])
        if record.get("source_text_excerpt"):
            lines.extend(["원문", "", "> " + markdown_quote(record["source_text_excerpt"]), ""])
        if record.get("target_url"):
            lines.append(f"출처: {record['target_url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def study_session_export_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    payload = study_session_payload_from_query(query)
    export_format = session_query_value(query, "format", "markdown").lower()
    if export_format == "json":
        return {"kind": "json", "payload": payload}
    return {
        "kind": "text",
        "body": export_study_session_markdown(payload),
        "content_type": "text/markdown; charset=utf-8",
    }
