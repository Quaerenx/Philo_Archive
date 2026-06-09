from __future__ import annotations

import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

import services.notes as notes_service  # noqa: E402
from services.notes import (  # noqa: E402
    append_note,
    create_note_from_payload,
    delete_note,
    export_notes_jsonl,
    export_notes_markdown,
    export_study_markdown,
    delete_note_from_query,
    note_storage_path,
    notes_export_from_query,
    notes_payload_from_query,
    read_all_notes,
    read_notes,
    study_export_from_query,
    study_note_groups,
    study_payload_from_query,
    update_note,
    update_note_from_payload,
)


CORPUS_ID = "contract_notes"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def cleanup() -> None:
    path = note_storage_path(CORPUS_ID)
    if path.exists():
        path.unlink()


def run_contracts() -> None:
    cleanup()
    try:
        append_note(
            CORPUS_ID,
            {
                "id": "note-1",
                "created_at": "2026-06-04T12:00:00",
                "corpus_id": CORPUS_ID,
                "work_id": "M",
                "variant_id": "",
                "target_id": "sec-1",
                "target_type": "section",
                "target_label": "Section 1",
                "quote": "quote text",
                "note": "first note about dawn",
                "tags": ["dawn", "test"],
                "url": "/work/nietzsche/M#sec-1",
            },
        )
        append_note(
            CORPUS_ID,
            {
                "id": "note-2",
                "created_at": "2026-06-04T12:00:01",
                "corpus_id": CORPUS_ID,
                "work_id": "GM",
                "variant_id": "",
                "target_id": "p-0001",
                "target_type": "paragraph",
                "target_label": "Paragraph 1",
                "quote": "",
                "note": "second note about genealogy",
                "tags": ["genealogy"],
                "url": "/work/nietzsche/GM#p-0001",
            },
        )

        require(len(read_notes(CORPUS_ID)) == 2, "read all notes failed")
        require(len(read_notes(CORPUS_ID, review_state="raw")) == 2, "default raw review filter failed")
        require(len(read_notes(CORPUS_ID, work_id="M")) == 1, "work filter failed")
        require(len(read_notes(CORPUS_ID, tag="dawn")) == 1, "tag filter failed")
        require(len(read_notes(CORPUS_ID, query="genealogy")) == 1, "query filter failed")
        require(len(read_all_notes([CORPUS_ID], tag="dawn")) == 1, "read all notes tag filter failed")
        require(len(read_all_notes([CORPUS_ID], work_id="GM")) == 1, "read all notes work filter failed")
        require(len(read_all_notes([CORPUS_ID], target_id="sec-1")) == 1, "read all notes target filter failed")
        require("note-1" in export_notes_jsonl(read_all_notes([CORPUS_ID])), "jsonl export failed")
        require("# Personal Archive Notes" in export_notes_markdown(read_all_notes([CORPUS_ID])), "markdown export failed")

        created = create_note_from_payload(
            {
                "corpus_id": "wittgenstein",
                "work_id": "Ms-101",
                "variant_id": "source_transcription_normalized.full",
                "target_id": "p-0001",
                "target_type": "paragraph",
                "target_label": "Paragraph 1",
                "quote": "sample quote",
                "note": "variant target note",
                "tags": ["variant"],
            },
        )
        require(created["corpus_id"] == "wittgenstein", "create note corpus failed")
        require(created["work_id"] == "Ms-101", "create note work failed")
        require(created["target_id"] == "p-0001", "create note target failed")
        require(
            created["url"] == "/work/wittgenstein/Ms-101?variant=source_transcription_normalized.full#p-0001",
            "create note variant target URL failed",
        )
        require(
            len(read_notes("wittgenstein", work_id="Ms-101", target_id="p-0001")) == 1,
            "created note target filter failed",
        )
        try:
            create_note_from_payload(
                {
                    "corpus_id": "wittgenstein",
                    "work_id": "Ms-101",
                    "variant_id": "source_transcription_normalized.full",
                    "target_id": "missing-segment",
                    "target_type": "paragraph",
                    "target_label": "Missing segment",
                    "note": "bad target note",
                },
            )
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("invalid segment note target should fail")

        updated = update_note(
            CORPUS_ID,
            "note-1",
            {
                "note": "updated note",
                "tags": ["edited"],
                "updated_at": "2026-06-04T12:01:00",
            },
        )
        require(updated["note"] == "updated note", "update note text failed")
        require(updated["tags"] == ["edited"], "update tags failed")
        require(len(read_notes(CORPUS_ID, tag="edited")) == 1, "updated tag filter failed")

        reviewed = update_note(
            CORPUS_ID,
            "note-1",
            {
                "review_state": "reviewed",
                "reviewed_at": "2026-06-04T12:02:00",
                "updated_at": "2026-06-04T12:02:00",
            },
        )
        require(reviewed["review_state"] == "reviewed", "review state update failed")
        require(len(read_notes(CORPUS_ID, review_state="reviewed")) == 1, "reviewed filter failed")
        require("- Review: reviewed" in export_notes_markdown(read_all_notes([CORPUS_ID])), "markdown review export failed")
        groups = study_note_groups(read_all_notes([CORPUS_ID], review_state="reviewed"))
        require(len(groups) == 1, "study group count failed")
        require(groups[0]["work_id"] == "M", "study group work id failed")
        require(groups[0]["summary"].startswith("1 reviewed notes"), "study group summary failed")
        require(groups[0]["target_count"] == 1, "study group target count failed")
        require(groups[0]["tag_counts"][0]["tag"] == "edited", "study group tag counts failed")
        require(groups[0]["reviewed_range"]["start"] == "2026-06-04T12:02:00", "study group reviewed range failed")
        study_markdown = export_study_markdown(groups)
        require("# Study Notes" in study_markdown, "study markdown export failed")
        require("tags: edited" in study_markdown, "study markdown summary failed")
        require("- Tags: edited (1)" in study_markdown, "study markdown tag counts failed")
        notes_payload = notes_payload_from_query({"corpus_id": [CORPUS_ID], "tag": ["edited"]})
        require(len(notes_payload["notes"]) == 1, "notes payload query helper failed")
        json_export = notes_export_from_query({"corpus_id": [CORPUS_ID], "format": ["json"]})
        require(json_export["kind"] == "json" and json_export["payload"]["count"] == 2, "notes JSON export helper failed")
        markdown_export = notes_export_from_query({"corpus_id": [CORPUS_ID], "format": ["markdown"]})
        require(markdown_export["kind"] == "text" and "# Personal Archive Notes" in markdown_export["body"], "notes markdown export helper failed")
        study_payload = study_payload_from_query({"corpus_id": [CORPUS_ID]})
        require(study_payload["group_count"] == 1 and study_payload["count"] == 1, "study payload helper failed")
        study_export = study_export_from_query({"corpus_id": [CORPUS_ID], "format": ["markdown"]})
        require(study_export["kind"] == "text" and "# Study Notes" in study_export["body"], "study export helper failed")
        helper_updated = update_note_from_payload(
            "note-2",
            {
                "corpus_id": CORPUS_ID,
                "note": "helper updated note",
                "tags": "helper,api",
            },
        )
        require(helper_updated["note"] == "helper updated note", "update payload helper failed")
        require(helper_updated["tags"] == ["helper", "api"], "update payload helper tags failed")
        helper_deleted = delete_note_from_query("note-2", {"corpus_id": [CORPUS_ID]})
        require(helper_deleted["id"] == "note-2", "delete query helper failed")

        deleted = delete_note(CORPUS_ID, "note-1")
        require(deleted["id"] == "note-1", "delete response failed")
        require(len(read_notes(CORPUS_ID)) == 0, "delete did not remove notes")
        print("notes contracts ok")
    finally:
        cleanup()


def main() -> None:
    original_notes_dir = notes_service.NOTES_DIR
    with tempfile.TemporaryDirectory(prefix="philo_notes_contract_") as temp_dir:
        notes_service.NOTES_DIR = Path(temp_dir)
        try:
            run_contracts()
        finally:
            notes_service.NOTES_DIR = original_notes_dir


if __name__ == "__main__":
    main()
