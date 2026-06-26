from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from sentence_units import render_sentence_spans, sentence_units  # noqa: E402
from services.sentence_targets import sentence_target_bundle  # noqa: E402
from services import sentence_translations as sentence_translation_service  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    PROMPT_TEMPLATE_ID,
    build_record,
    build_sentence_prompt_bundle,
    export_sentence_translations_markdown,
    find_cached_record,
    normalized_model_output,
    public_record_id,
    public_translation_record,
    sentence_translations_for_export,
    sentence_translations_summary_from_query,
    update_sentence_translation_review,
)
from services.source_targets import sha256_text  # noqa: E402
from scripts.check_ai_records_contracts import validate_file  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_sentence_target() -> dict:
    source_text = "Das Leben ist Wille zur Macht. Dies ist ein zweiter Satz."
    sentence_text = "Das Leben ist Wille zur Macht."
    return {
        "schema_version": 1,
        "record_type": "sentence_target_bundle",
        "corpus_id": "nietzsche",
        "work_id": "demo",
        "variant_id": "",
        "segment_id": "p-0001",
        "sentence_id": "p-0001.s001",
        "target_id": "p-0001.s001",
        "target_url": "/work/nietzsche/demo#p-0001.s001",
        "segment_type": "paragraph",
        "label": "Paragraph 1 / Sentence 1",
        "source_text": source_text,
        "sentence_text": sentence_text,
        "source_text_preview": source_text,
        "source_text_chars": len(source_text),
        "sentence_text_chars": len(sentence_text),
        "source_text_sha256": sha256_text(source_text),
        "sentence_text_sha256": sha256_text(sentence_text),
    }


def check_sentence_units() -> None:
    units = sentence_units("p-0001", "One. Two.")
    require([unit["sentence_id"] for unit in units] == ["p-0001.s001", "p-0001.s002"], "sentence IDs are unstable")
    html = render_sentence_spans("p-0001", "One. Two.")
    require('id="p-0001.s001"' in html, "rendered sentence span missing id")
    require('data-target-type="sentence"' in html, "rendered sentence span missing target type")


def check_prompt_and_record(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    prompt = prompt_bundle["prompt"]
    require(prompt_bundle["prompt_template_id"] == PROMPT_TEMPLATE_ID, "unexpected sentence prompt template id")
    require(prompt_bundle["prompt_sha256"] == sha256_text(prompt), "prompt_sha256 mismatch")
    require(target["sentence_text"] in prompt, "prompt missing selected sentence")
    for phrase in ["Generated interpretation", "Original source", "sentence_text_sha256", "Return only a valid JSON object"]:
        require(phrase in prompt, f"sentence prompt missing {phrase!r}")

    output = normalized_model_output(
        json.dumps(
            {
                "translation": "삶은 힘에의 의지이다.",
                "commentary": "선택 문장에 한정한 해설.",
                "cautions": ["Generated translation"],
            },
            ensure_ascii=False,
        )
    )
    record = build_record(target, prompt_bundle, output)
    require(record["schema_version"] == 2, "new sentence translation records should use schema v2")
    public_record = public_translation_record(record)
    require("literal_gloss" not in public_record, "public sentence translation record should hide literal_gloss")
    require("key_terms" not in public_record, "public sentence translation record should hide key_terms")
    markdown = export_sentence_translations_markdown([public_record])
    require("Sentence Translations" in markdown, "sentence translation markdown export heading missing")
    require("Reviewed Gemma" not in markdown, "sentence translation markdown export should hide runtime-oriented title")
    require("Review:" not in markdown, "sentence translation markdown export should hide review-state metadata")
    require("Reviewed:" not in markdown, "sentence translation markdown export should hide reviewed timestamps")
    require(target["sentence_id"] in markdown, "sentence translation markdown export missing sentence id")
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "ai_sentence_translation.jsonl"
        path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        require(validate_file(path) == 1, "sentence translation record validator failed")


def check_cache_and_review_compatibility(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    older = build_record(
        target,
        prompt_bundle,
        {
            "translation": "older translation",
            "commentary": "older commentary",
            "cautions": [],
        },
    )
    rejected = build_record(
        target,
        prompt_bundle,
        {
            "translation": "rejected translation",
            "commentary": "rejected commentary",
            "cautions": [],
        },
    )
    rejected["review_state"] = "rejected"
    newest = build_record(
        target,
        prompt_bundle,
        {
            "translation": "newest translation",
            "commentary": "newest commentary",
            "cautions": [],
        },
    )
    legacy = dict(newest)
    legacy.pop("id", None)
    public_legacy = public_translation_record(legacy)
    require(public_legacy["id"].startswith("legacy-"), "legacy sentence translations need a stable public id")
    require(public_record_id(legacy) == public_legacy["id"], "legacy public id should be stable")

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "sentence_translations.jsonl"
        path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in [older, newest, rejected]) + "\n",
            encoding="utf-8",
        )
        cached = find_cached_record(path, target, prompt_bundle)
        require(cached and cached["translation"] == "newest translation", "cache should return newest non-rejected record")

    with tempfile.TemporaryDirectory() as temp_dir:
        original_ai_dir = sentence_translation_service.AI_DIR
        sentence_translation_service.AI_DIR = Path(temp_dir)
        try:
            path = sentence_translation_service.ai_record_path(target["corpus_id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")
            summary = sentence_translations_summary_from_query(
                {"corpus_id": [target["corpus_id"]], "work_id": [target["work_id"]]}
            )
            require(summary["count"] == 1, "sentence translation summary count failed")
            require(summary["review_state_counts"]["generated"] == 1, "sentence translation summary generated count failed")
            require(summary["sentence_state_count"] == 1, "sentence translation summary sentence state count failed")
            require(summary["sentence_states"][0]["sentence_id"] == target["sentence_id"], "sentence translation summary state sentence id failed")
            require(summary["sentence_states"][0]["review_state"] == "generated", "sentence translation summary state review failed")
            updated = update_sentence_translation_review(
                {"corpus_id": target["corpus_id"], "review_state": "reviewed"},
                public_legacy["id"],
            )
            require(updated["record"]["review_state"] == "reviewed", "legacy public id should support review updates")
            summary = sentence_translations_summary_from_query(
                {"corpus_id": [target["corpus_id"]], "work_id": [target["work_id"]]}
            )
            require(summary["review_state_counts"]["reviewed"] == 1, "sentence translation summary reviewed count failed")
            require(summary["sentence_states"][0]["review_state"] == "reviewed", "sentence translation summary reviewed state failed")
            stored = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            require(stored["id"] == public_legacy["id"], "reviewing a legacy record should persist the stable id")
            bible_record = dict(stored)
            bible_record["id"] = "bible-demo-translation"
            bible_record["corpus_id"] = "bible"
            bible_record["work_id"] = "demo2"
            bible_record["translation"] = "bible generated translation"
            bible_record["commentary"] = "bible generated commentary"
            bible_record["review_state"] = "generated"
            bible_path = sentence_translation_service.ai_record_path("bible")
            bible_path.write_text(json.dumps(bible_record, ensure_ascii=False) + "\n", encoding="utf-8")
            all_records = sentence_translations_for_export({"review_state": ["all"]})
            require(
                {record["corpus_id"] for record in all_records} == {"nietzsche", "bible"},
                "sentence translation export without corpus_id should include all corpora",
            )
            filtered_records = sentence_translations_for_export({"review_state": ["all"], "q": ["newest"]})
            require(len(filtered_records) == 1, "sentence translation export q filter count failed")
            require(filtered_records[0]["translation"] == "newest translation", "sentence translation export q filter mismatch")
            empty_filtered_records = sentence_translations_for_export({"review_state": ["all"], "q": ["not-present"]})
            require(empty_filtered_records == [], "sentence translation export q filter should allow empty results")
            all_summary = sentence_translations_summary_from_query({"review_state": ["all"]})
            require(all_summary["count"] == 2, "sentence translation summary without corpus_id should count all corpora")
            require(all_summary["review_state_counts"]["generated"] == 1, "all-corpus summary generated count failed")
            require(all_summary["review_state_counts"]["reviewed"] == 1, "all-corpus summary reviewed count failed")
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir


def check_restored_source_target() -> None:
    target = sentence_target_bundle("nietzsche", "GM", "p-0023", "p-0023.s001", "")
    require(target["sentence_id"] == "p-0023.s001", "restored sentence target id mismatch")
    check_prompt_and_record(target)
    check_cache_and_review_compatibility(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate on-demand sentence translation contracts.", allow_abbrev=False)
    parser.add_argument("--with-source-targets", action="store_true")
    args = parser.parse_args()

    check_sentence_units()
    synthetic_target = synthetic_sentence_target()
    check_prompt_and_record(synthetic_target)
    check_cache_and_review_compatibility(synthetic_target)
    if args.with_source_targets:
        check_restored_source_target()
    print("sentence translation contracts ok")


if __name__ == "__main__":
    main()
