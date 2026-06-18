from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from corpora.catalogs import validate_work_target
from services.sentence_targets import resolve_sentence_target
from services.source_targets import resolve_segment_target
from services.sources import work_href


SITE = Path(__file__).resolve().parents[1]
NOTES_DIR = SITE / "data" / "notes"
DEFAULT_CORPUS_IDS = ("nietzsche", "bible", "kierkegaard", "wittgenstein")
VALID_REVIEW_STATES = {"raw", "reviewed"}
SEGMENT_NOTE_TARGET_TYPES = {"segment", "paragraph", "verse", "sentence"}


def safe_note_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "", value.strip())


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def query_corpus_id(query: dict[str, list[str]]) -> str:
    return safe_note_slug(first_query_value(query, "corpus_id") or first_query_value(query, "author"))


def normalize_tags(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_review_state(value: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in VALID_REVIEW_STATES else "raw"


def note_target_url(corpus_id: str, work_id: str, variant_id: str = "", target_id: str = "") -> str:
    href = work_href(corpus_id, work_id)
    if variant_id:
        href += "?variant=" + quote(variant_id, safe="")
    if target_id and target_id != "work":
        href += "#" + quote(target_id, safe="")
    return href


def validate_note_target(corpus_id: str, work_id: str, variant_id: str, target_id: str, target_type: str) -> None:
    validate_work_target(corpus_id, work_id)
    if not target_id or target_id == "work":
        return
    if target_type == "sentence":
        segment_id = target_id.split(".s", 1)[0]
        resolve_sentence_target(corpus_id, work_id, segment_id, target_id, variant_id)
        return
    if target_type in SEGMENT_NOTE_TARGET_TYPES:
        resolve_segment_target(corpus_id, work_id, target_id, variant_id)


def note_storage_path(corpus_id: str) -> Path:
    corpus_id = safe_note_slug(corpus_id)
    if not corpus_id:
        raise ValueError("missing corpus id")
    return NOTES_DIR / f"{corpus_id}_notes.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_note_record(note: dict, fallback_corpus_id: str) -> dict:
    record = dict(note)
    record["corpus_id"] = record.get("corpus_id") or record.get("author") or fallback_corpus_id
    record["target_type"] = record.get("target_type") or "segment"
    record["variant_id"] = record.get("variant_id") or ""
    record["tags"] = record.get("tags") if isinstance(record.get("tags"), list) else []
    record["review_state"] = normalize_review_state(record.get("review_state", "raw"))
    record["reviewed_at"] = record.get("reviewed_at") or ""
    return record


def note_matches_query(note: dict, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            str(note.get("target_label", "")),
            str(note.get("quote", "")),
            str(note.get("note", "")),
            " ".join(str(tag) for tag in note.get("tags", [])),
        ]
    ).lower()
    return query.lower() in haystack


def note_matches_tag(note: dict, tag: str) -> bool:
    if not tag:
        return True
    needle = tag.lower()
    return any(str(item).lower() == needle for item in note.get("tags", []))


def note_matches_review_state(note: dict, review_state: str) -> bool:
    if not review_state:
        return True
    return normalize_review_state(note.get("review_state", "")) == normalize_review_state(review_state)


def read_notes(
    corpus_id: str,
    work_id: str = "",
    target_id: str = "",
    tag: str = "",
    query: str = "",
    review_state: str = "",
) -> list[dict]:
    corpus_id = safe_note_slug(corpus_id)
    if not corpus_id:
        return []
    notes = [
        normalize_note_record(note, corpus_id)
        for note in read_jsonl(note_storage_path(corpus_id))
        if (note.get("corpus_id") or note.get("author")) == corpus_id
    ]
    if work_id:
        notes = [note for note in notes if note.get("work_id") == work_id]
    if target_id:
        notes = [note for note in notes if note.get("target_id") == target_id]
    if tag:
        notes = [note for note in notes if note_matches_tag(note, tag)]
    if query:
        notes = [note for note in notes if note_matches_query(note, query)]
    if review_state:
        notes = [note for note in notes if note_matches_review_state(note, review_state)]
    return notes


def available_note_corpus_ids() -> list[str]:
    corpus_ids = set(DEFAULT_CORPUS_IDS)
    if NOTES_DIR.exists():
        for path in NOTES_DIR.glob("*_notes.jsonl"):
            corpus_id = path.name[: -len("_notes.jsonl")]
            if safe_note_slug(corpus_id):
                corpus_ids.add(corpus_id)
    return sorted(corpus_ids)


def read_all_notes(
    corpus_ids: list[str] | None = None,
    work_id: str = "",
    target_id: str = "",
    tag: str = "",
    query: str = "",
    review_state: str = "",
) -> list[dict]:
    selected = [safe_note_slug(item) for item in (corpus_ids or available_note_corpus_ids())]
    notes: list[dict] = []
    for corpus_id in selected:
        if corpus_id:
            notes.extend(
                read_notes(
                    corpus_id,
                    work_id=work_id,
                    target_id=target_id,
                    tag=tag,
                    query=query,
                    review_state=review_state,
                )
            )
    return sorted(
        notes,
        key=lambda note: (str(note.get("updated_at") or note.get("created_at") or ""), str(note.get("id") or "")),
        reverse=True,
    )


def tag_counts_for_notes(notes: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for note in notes:
        for tag in note.get("tags", []):
            tag_value = str(tag).strip()
            if tag_value:
                counts[tag_value] = counts.get(tag_value, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


def reviewed_range_for_notes(notes: list[dict]) -> dict:
    dates = sorted(
        str(note.get("reviewed_at") or note.get("updated_at") or note.get("created_at") or "")
        for note in notes
        if str(note.get("reviewed_at") or note.get("updated_at") or note.get("created_at") or "")
    )
    return {"start": dates[0], "end": dates[-1]} if dates else {"start": "", "end": ""}


def study_group_summary(group: dict) -> str:
    notes = group.get("notes", [])
    note_count = len(notes)
    target_count = len({str(note.get("target_id", "")) for note in notes if str(note.get("target_id", ""))})
    tag_counts = tag_counts_for_notes(notes)
    top_tags = ", ".join(item["tag"] for item in tag_counts[:5])
    summary_parts = [f"{note_count} reviewed notes"]
    if target_count:
        summary_parts.append(f"{target_count} targets")
    if top_tags:
        summary_parts.append(f"tags: {top_tags}")
    return " / ".join(summary_parts)


def study_note_groups(notes: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for note in notes:
        corpus_id = str(note.get("corpus_id", ""))
        work_id = str(note.get("work_id", ""))
        key = (corpus_id, work_id)
        if key not in groups:
            groups[key] = {
                "corpus_id": corpus_id,
                "work_id": work_id,
                "title": " / ".join(item for item in [corpus_id, work_id] if item) or "Reviewed notes",
                "count": 0,
                "notes": [],
            }
        groups[key]["notes"].append(note)

    output = []
    for group in groups.values():
        group["notes"] = sorted(
            group["notes"],
            key=lambda note: (
                str(note.get("target_id") or ""),
                str(note.get("target_label") or ""),
                str(note.get("reviewed_at") or note.get("updated_at") or note.get("created_at") or ""),
            ),
        )
        group["count"] = len(group["notes"])
        group["target_count"] = len(
            {str(note.get("target_id", "")) for note in group["notes"] if str(note.get("target_id", ""))}
        )
        group["tag_counts"] = tag_counts_for_notes(group["notes"])
        group["reviewed_range"] = reviewed_range_for_notes(group["notes"])
        group["summary"] = study_group_summary(group)
        output.append(group)
    return sorted(output, key=lambda group: (group["corpus_id"], group["work_id"]))


def export_notes_jsonl(notes: list[dict]) -> str:
    return "".join(json.dumps(note, ensure_ascii=False, sort_keys=True) + "\n" for note in notes)


def export_notes_markdown(notes: list[dict]) -> str:
    lines = ["# Personal Archive Notes", "", f"{len(notes)} notes", ""]
    for note in notes:
        corpus_id = note.get("corpus_id", "")
        work_id = note.get("work_id", "")
        target_label = note.get("target_label") or note.get("target_id") or "Work"
        title = " / ".join(str(item) for item in [corpus_id, work_id, target_label] if item)
        lines.extend([f"## {title}", ""])
        if note.get("url"):
            lines.extend([f"- URL: {note['url']}"])
        if note.get("created_at"):
            lines.extend([f"- Created: {note['created_at']}"])
        if note.get("updated_at"):
            lines.extend([f"- Updated: {note['updated_at']}"])
        lines.extend([f"- Review: {normalize_review_state(note.get('review_state', 'raw'))}"])
        if note.get("reviewed_at"):
            lines.extend([f"- Reviewed: {note['reviewed_at']}"])
        tags = ", ".join(str(tag) for tag in note.get("tags", []))
        if tags:
            lines.extend([f"- Tags: {tags}"])
        if note.get("quote"):
            lines.extend(["", "> " + str(note["quote"]).replace("\n", "\n> ")])
        if note.get("note"):
            lines.extend(["", str(note["note"])])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_study_markdown(groups: list[dict]) -> str:
    total_notes = sum(int(group.get("count") or len(group.get("notes", []))) for group in groups)
    lines = ["# Study Notes", "", f"{total_notes} reviewed notes", ""]
    for group in groups:
        title = group.get("title") or "Reviewed notes"
        lines.extend([f"## {title}", ""])
        if group.get("summary"):
            lines.extend([str(group["summary"]), ""])
        reviewed_range = group.get("reviewed_range") or {}
        if reviewed_range.get("start") or reviewed_range.get("end"):
            lines.append(f"- Reviewed range: {reviewed_range.get('start', '')} - {reviewed_range.get('end', '')}")
        tag_counts = group.get("tag_counts") or []
        if tag_counts:
            tags = ", ".join(f"{item['tag']} ({item['count']})" for item in tag_counts)
            lines.append(f"- Tags: {tags}")
        if reviewed_range.get("start") or reviewed_range.get("end") or tag_counts:
            lines.append("")
        for note in group.get("notes", []):
            target_label = note.get("target_label") or note.get("target_id") or "Target"
            lines.extend([f"### {target_label}", ""])
            if note.get("url"):
                lines.append(f"- URL: {note['url']}")
            if note.get("reviewed_at"):
                lines.append(f"- Reviewed: {note['reviewed_at']}")
            tags = ", ".join(str(tag) for tag in note.get("tags", []))
            if tags:
                lines.append(f"- Tags: {tags}")
            if note.get("quote"):
                lines.extend(["", "> " + str(note["quote"]).replace("\n", "\n> ")])
            if note.get("note"):
                lines.extend(["", str(note["note"])])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def notes_payload_from_query(query: dict[str, list[str]]) -> dict:
    corpus_id = query_corpus_id(query)
    if not corpus_id:
        return {"notes": []}
    try:
        notes = read_notes(
            corpus_id,
            work_id=first_query_value(query, "work_id"),
            target_id=first_query_value(query, "target_id"),
            tag=first_query_value(query, "tag"),
            query=first_query_value(query, "q"),
            review_state=first_query_value(query, "review_state"),
        )
    except ValueError:
        notes = []
    return {"notes": notes}


def notes_for_export_query(query: dict[str, list[str]]) -> list[dict]:
    corpus_id = query_corpus_id(query)
    corpus_ids = [corpus_id] if corpus_id else None
    return read_all_notes(
        corpus_ids,
        work_id=first_query_value(query, "work_id"),
        target_id=first_query_value(query, "target_id"),
        tag=first_query_value(query, "tag"),
        query=first_query_value(query, "q"),
        review_state=first_query_value(query, "review_state"),
    )


def notes_export_from_query(query: dict[str, list[str]]) -> dict:
    notes = notes_for_export_query(query)
    export_format = first_query_value(query, "format", "json").lower()
    if export_format == "jsonl":
        return {
            "kind": "text",
            "body": export_notes_jsonl(notes),
            "content_type": "application/x-ndjson; charset=utf-8",
        }
    if export_format in {"md", "markdown"}:
        return {
            "kind": "text",
            "body": export_notes_markdown(notes),
            "content_type": "text/markdown; charset=utf-8",
        }
    return {"kind": "json", "payload": {"count": len(notes), "notes": notes}}


def study_groups_from_query(query: dict[str, list[str]]) -> list[dict]:
    corpus_id = query_corpus_id(query)
    corpus_ids = [corpus_id] if corpus_id else None
    notes = read_all_notes(
        corpus_ids,
        work_id=first_query_value(query, "work_id"),
        tag=first_query_value(query, "tag"),
        query=first_query_value(query, "q"),
        review_state="reviewed",
    )
    return study_note_groups(notes)


def study_payload_from_query(query: dict[str, list[str]]) -> dict:
    groups = study_groups_from_query(query)
    return {
        "count": sum(int(group.get("count") or 0) for group in groups),
        "group_count": len(groups),
        "groups": groups,
    }


def study_export_from_query(query: dict[str, list[str]]) -> dict:
    groups = study_groups_from_query(query)
    export_format = first_query_value(query, "format", "markdown").lower()
    if export_format == "json":
        return {"kind": "json", "payload": study_payload_from_query(query)}
    return {
        "kind": "text",
        "body": export_study_markdown(groups),
        "content_type": "text/markdown; charset=utf-8",
    }


def create_note_from_payload(payload: dict) -> dict:
    corpus_id = safe_note_slug(str(payload.get("corpus_id") or payload.get("author") or "").strip())
    work_id = str(payload.get("work_id", "")).strip()
    variant_id = str(payload.get("variant_id", "")).strip()
    note_text = str(payload.get("note", "")).strip()
    target_id = str(payload.get("target_id", "")).strip() or "work"
    target_type = str(payload.get("target_type", "")).strip() or "segment"
    target_label = str(payload.get("target_label", "")).strip() or target_id
    quote_text = str(payload.get("quote", "")).strip()
    tags = normalize_tags(payload.get("tags", []))
    if not corpus_id or not note_text:
        raise ValueError("missing required note fields")
    validate_note_target(corpus_id, work_id, variant_id, target_id, target_type)
    record = {
        "id": uuid4().hex,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "corpus_id": corpus_id,
        "work_id": work_id,
        "variant_id": variant_id[:120],
        "target_id": target_id[:120],
        "target_type": target_type[:80],
        "target_label": target_label[:240],
        "quote": quote_text[:2000],
        "note": note_text[:5000],
        "tags": [str(tag)[:80] for tag in tags[:12]],
        "review_state": "raw",
        "reviewed_at": "",
        "url": note_target_url(corpus_id, work_id, variant_id[:120], target_id[:120]),
    }
    if corpus_id == "nietzsche":
        record["author"] = "nietzsche"
    append_note(corpus_id, record)
    return record


def update_note_from_payload(note_id: str, payload: dict) -> dict:
    corpus_id = safe_note_slug(str(payload.get("corpus_id") or payload.get("author") or "").strip())
    note_text = str(payload.get("note", "")).strip()
    review_state = str(payload.get("review_state", "")).strip().lower()
    tags = normalize_tags(payload.get("tags", []))
    if not corpus_id or (not note_text and review_state not in VALID_REVIEW_STATES):
        raise ValueError("missing required note fields")
    updates = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if note_text:
        updates["note"] = note_text[:5000]
        updates["tags"] = [str(tag)[:80] for tag in tags[:12]]
    if review_state in VALID_REVIEW_STATES:
        updates["review_state"] = review_state
        updates["reviewed_at"] = datetime.now().isoformat(timespec="seconds") if review_state == "reviewed" else ""
    if "quote" in payload:
        updates["quote"] = str(payload.get("quote", "")).strip()[:2000]
    if "target_label" in payload:
        updates["target_label"] = str(payload.get("target_label", "")).strip()[:240]
    return update_note(corpus_id, note_id, updates)


def delete_note_from_query(note_id: str, query: dict[str, list[str]]) -> dict:
    corpus_id = query_corpus_id(query)
    if not corpus_id:
        raise ValueError("missing corpus id")
    return delete_note(corpus_id, note_id)


def append_note(corpus_id: str, record: dict) -> None:
    append_jsonl(note_storage_path(corpus_id), record)


def update_note(corpus_id: str, note_id: str, updates: dict) -> dict:
    corpus_id = safe_note_slug(corpus_id)
    if not corpus_id or not note_id:
        raise ValueError("missing note id")
    path = note_storage_path(corpus_id)
    records = read_jsonl(path)
    updated = None
    allowed_fields = {"note", "tags", "quote", "target_label", "review_state", "reviewed_at"}
    for index, record in enumerate(records):
        if record.get("id") != note_id:
            continue
        next_record = normalize_note_record(record, corpus_id)
        for field in allowed_fields:
            if field in updates:
                next_record[field] = updates[field]
        if "tags" in next_record and not isinstance(next_record["tags"], list):
            next_record["tags"] = []
        if "review_state" in next_record:
            next_record["review_state"] = normalize_review_state(next_record["review_state"])
        if "updated_at" in updates:
            next_record["updated_at"] = updates["updated_at"]
        records[index] = next_record
        updated = next_record
        break
    if updated is None:
        raise FileNotFoundError("note not found")
    write_jsonl(path, records)
    return updated


def delete_note(corpus_id: str, note_id: str) -> dict:
    corpus_id = safe_note_slug(corpus_id)
    if not corpus_id or not note_id:
        raise ValueError("missing note id")
    path = note_storage_path(corpus_id)
    records = read_jsonl(path)
    remaining = [record for record in records if record.get("id") != note_id]
    if len(remaining) == len(records):
        raise FileNotFoundError("note not found")
    write_jsonl(path, remaining)
    return {"id": note_id}
