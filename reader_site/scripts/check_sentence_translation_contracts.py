from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from sentence_units import render_sentence_spans, sentence_units  # noqa: E402
from services.segment_offsets import SEGMENT_FILES  # noqa: E402
from services import sentence_targets as sentence_target_service  # noqa: E402
from services.sentence_targets import (  # noqa: E402
    MAX_CONTEXT_CHARS,
    marked_target_segment,
    sentence_target_bundle,
    structural_source_context,
)
from services import sentence_translations as sentence_translation_service  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    CRITIC_RESPONSE_SCHEMA,
    PROMPT_TEMPLATE_ID,
    TRANSLATION_RESPONSE_SCHEMA,
    TranslationModelResponseError,
    append_record,
    build_record,
    build_critic_prompt_bundle,
    build_sentence_prompt_bundle,
    delete_sentence_translation,
    delete_sentence_translation_from_query,
    export_sentence_translations_markdown,
    find_cached_record,
    iter_cached_records,
    normalized_model_output,
    normalized_critic_output,
    public_record_id,
    public_translation_record,
    sentence_translations_for_export,
    sentence_translations_summary_from_query,
    run_translation_pipeline,
    update_sentence_translation_review,
)
from services.source_targets import sha256_text  # noqa: E402
from services.translation_profiles import translation_policy_bundle  # noqa: E402
from scripts.check_ai_records_contracts import validate_file  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_ai_dir_override_contract() -> None:
    source = Path(sentence_translation_service.__file__).read_text(encoding="utf-8")
    require("PHILO_AI_DIR" in source, "sentence translation storage should support an isolated AI data directory")
    require('os.environ.get("PHILO_AI_DIR"' in source, "sentence translation storage should use PHILO_AI_DIR")


def check_indexed_source_lookup_contract() -> None:
    translation_source = Path(sentence_translation_service.__file__).read_text(encoding="utf-8")
    source_target_source = (SITE / "services" / "source_targets.py").read_text(encoding="utf-8")
    require(
        "resolve_indexed_segment_record" in source_target_source,
        "sentence source targets should use the byte-offset index",
    )
    require(
        "def segment_records(" not in source_target_source,
        "sentence source targets must not retain the full JSONL parser",
    )
    target_position = translation_source.index("target = sentence_target_bundle(")
    cache_position = translation_source.index("cached = find_cached_record(")
    require(
        target_position < cache_position,
        "translation cache lookup contract changed unexpectedly",
    )


def check_concurrent_cache_writes() -> None:
    record_count = 32
    with tempfile.TemporaryDirectory(prefix="philo_translation_atomic_") as temp_dir:
        original_ai_dir = sentence_translation_service.AI_DIR
        sentence_translation_service.AI_DIR = Path(temp_dir)
        try:
            path = sentence_translation_service.ai_record_path("nietzsche")

            def append_index(index: int) -> None:
                append_record(
                    path,
                    {
                        "schema_version": 2,
                        "record_type": "ai_sentence_translation",
                        "id": f"concurrent-translation-{index:02d}",
                        "corpus_id": "nietzsche",
                        "work_id": "demo",
                        "review_state": "generated",
                        "translation": f"translation {index}",
                    },
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(append_index, range(record_count)))

            records = iter_cached_records(path)
            require(len(records) == record_count, "concurrent sentence translation writes lost records")
            require(
                len({record["id"] for record in records}) == record_count,
                "concurrent translation writes duplicated records",
            )

            def review_index(index: int) -> None:
                update_sentence_translation_review(
                    {"corpus_id": "nietzsche", "review_state": "reviewed"},
                    f"concurrent-translation-{index:02d}",
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(review_index, range(record_count)))
            records = iter_cached_records(path)
            require(
                all(record["review_state"] == "reviewed" for record in records),
                "concurrent sentence translation reviews lost changes",
            )

            def delete_index(index: int) -> None:
                delete_sentence_translation("nietzsche", f"concurrent-translation-{index:02d}")

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(delete_index, range(0, record_count, 2)))
            records = iter_cached_records(path)
            require(len(records) == record_count // 2, "concurrent sentence translation deletes lost changes")
            require(
                all(int(record["id"].rsplit("-", 1)[1]) % 2 == 1 for record in records),
                "concurrent sentence translation deletes removed the wrong records",
            )
            require(
                not list(path.parent.glob(f".{path.name}.*.tmp")),
                "atomic sentence translation writes left temporary files behind",
            )
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir


def check_snapshot_read_cache() -> None:
    with tempfile.TemporaryDirectory(prefix="philo_translation_cache_") as temp_dir:
        path = Path(temp_dir) / "sentence_translations.jsonl"
        first_record = {
            "id": "cache-record-1",
            "record_type": "ai_sentence_translation",
            "translation": "first snapshot",
        }
        sentence_translation_service.write_records(path, [first_record])
        first_read = iter_cached_records(path)
        first_read[0]["translation"] = "caller mutation"
        cache_before = sentence_translation_service._read_translation_snapshot.cache_info()
        second_read = iter_cached_records(path)
        cache_after = sentence_translation_service._read_translation_snapshot.cache_info()
        require(second_read[0]["translation"] == "first snapshot", "translation cache leaked caller mutation")
        require(cache_after.hits > cache_before.hits, "unchanged translation snapshot should hit the read cache")
        require(cache_after.maxsize == 16, "translation read cache should remain bounded")

        second_record = dict(first_record)
        second_record["id"] = "cache-record-2"
        second_record["translation"] = "externally replaced snapshot with a different size"
        path.write_text(json.dumps(second_record, ensure_ascii=False) + "\n", encoding="utf-8")
        external_read = iter_cached_records(path)
        require(external_read[0]["id"] == "cache-record-2", "translation cache missed an external file change")


def check_sentence_boundary_context_contract() -> None:
    target_text = "Zielsatz bleibt vollständig."
    target_segment = {
        "corpus_id": "synthetic",
        "work_id": "demo",
        "variant_id": "",
        "segment_id": "p-0002",
        "text_raw": target_text,
        "source_text_sha256": sha256_text(target_text),
    }
    previous_text = " ".join(
        [
            "P1 " + "eins " * 25 + ".",
            "P2 " + "zwei " * 25 + ".",
            "P3 " + "drei " * 25 + ".",
        ]
    )
    next_text = " ".join(
        [
            "N1 " + "vier " * 25 + ".",
            "N2 " + "fünf " * 25 + ".",
            "N3 " + "sechs " * 25 + ".",
        ]
    )
    locations = [
        {"segment_id": "p-0001", "record_order": 1, "text_chars": len(previous_text)},
        {"segment_id": "p-0002", "record_order": 2, "text_chars": len(target_text)},
        {"segment_id": "p-0003", "record_order": 3, "text_chars": len(next_text)},
    ]
    neighbor_records = [
        {"segment_id": "p-0001", "text_raw": previous_text},
        {"segment_id": "p-0003", "text_raw": next_text},
    ]
    with (
        patch.object(sentence_target_service, "indexed_work_segment_locations", return_value=locations),
        patch.object(sentence_target_service, "read_indexed_segment_records", return_value=neighbor_records),
    ):
        context = structural_source_context(target_segment, target_text, max_chars=500)

    source_context = context["source_context"]
    previous_units = [str(unit["text_raw"]) for unit in sentence_units("previous", previous_text)]
    next_units = [str(unit["text_raw"]) for unit in sentence_units("next", next_text)]
    require(len(source_context) <= 500, "sentence-aware structural context exceeds its limit")
    require(source_context.count("<TARGET_SENTENCE>") == 1, "sentence-aware context lost the target marker")
    require(previous_units[-1] in source_context, "previous context should include its nearest complete sentence")
    require(next_units[0] in source_context, "next context should include its nearest complete sentence")
    require("… " + previous_units[-1] in source_context, "truncated previous context must expose an omission marker")
    require(next_units[0] + " …" in source_context, "truncated next context must expose an omission marker")
    require(
        {item["position"] for item in context["context_segments"]} == {"previous", "target", "next"},
        "sentence-aware context audit should record both partial neighbors",
    )


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


def passing_pipeline_output(translation: str, commentary: str = "", cautions: list[str] | None = None) -> dict:
    return {
        "translation": translation,
        "commentary": commentary,
        "cautions": list(cautions or []),
        "quality_state": "critic_pass",
        "revision_count": 0,
        "critic": {"initial": {"verdict": "pass", "issues": []}, "final": None},
        "critic_prompt_sha256": {"initial": "a" * 64, "final": ""},
        "revision_prompt_sha256": "",
    }


def check_sentence_units() -> None:
    units = sentence_units("p-0001", "One. Two.")
    require([unit["sentence_id"] for unit in units] == ["p-0001.s001", "p-0001.s002"], "sentence IDs are unstable")
    html = render_sentence_spans("p-0001", "One. Two.")
    require('id="p-0001.s001"' in html, "rendered sentence span missing id")
    require('data-target-type="sentence"' in html, "rendered sentence span missing target type")
    repeated = marked_target_segment("One. One. Three.", "One.", sentence_index=2)
    require("One. <TARGET_SENTENCE>One.</TARGET_SENTENCE> Three." in repeated, "target marker selected the wrong repeated sentence")
    oversized = "Alpha " + "eins " * 20 + ". Target bleibt vollstaendig. Omega " + "drei " * 20 + "."
    bounded = marked_target_segment(oversized, "Target bleibt vollstaendig.", max_chars=140, sentence_index=2)
    require(len(bounded) <= 140, "oversized target segment context exceeds its limit")
    require("… <TARGET_SENTENCE>Target bleibt vollstaendig.</TARGET_SENTENCE> …" in bounded, "oversized target segment should keep a whole selected sentence")
    require("eins" not in bounded and "drei" not in bounded, "oversized target segment must not include neighboring sentence fragments")


def check_prompt_and_record(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    prompt = prompt_bundle["prompt"]
    require(prompt_bundle["prompt_template_id"] == PROMPT_TEMPLATE_ID, "unexpected sentence prompt template id")
    require(prompt_bundle["prompt_sha256"] == sha256_text(prompt), "prompt_sha256 mismatch")
    require(target["sentence_text"] in prompt, "prompt missing selected sentence")
    for phrase in [
        "Translate only the text inside <TARGET_SENTENCE>",
        "Keep translation and interpretation strictly separate",
        "Preserve logical relations",
        "quoted source data",
        "historical spelling",
        "unsupported specialized term",
        "Do not praise, defend, or justify",
        "silently verify",
        "Return exactly one JSON object",
    ]:
        require(phrase in prompt, f"sentence prompt missing {phrase!r}")
    for audit_value in [
        target["corpus_id"],
        target["segment_id"],
        target["sentence_id"],
        target["target_url"],
        target["source_text_sha256"],
        target["sentence_text_sha256"],
    ]:
        require(audit_value not in prompt, f"prompt should keep audit value outside model input: {audit_value!r}")
    marked_sentence = f"<TARGET_SENTENCE>{target['sentence_text']}</TARGET_SENTENCE>"
    require(prompt.count(marked_sentence) == 1, "prompt should mark the selected sentence exactly once")
    require(prompt_bundle["temperature"] <= 0.1, "translation temperature should remain deterministic")
    require(prompt_bundle["response_schema"] == TRANSLATION_RESPONSE_SCHEMA, "translation response schema drifted")

    output = passing_pipeline_output(
        "삶은 힘에의 의지이다.",
        "선택 문장에 한정한 해설.",
        ["Generated translation"],
    )
    record = build_record(target, prompt_bundle, output)
    require(record["schema_version"] == 5, "new sentence translation records should use schema v5")
    require("interpretation" not in record, "sentence translation must not duplicate commentary as interpretation")
    require(record["quality_state"] == "critic_pass", "record missing automatic quality state")
    require(record["generation_parameters"] == prompt_bundle["generation_parameters"], "record missing generation parameters")
    require(record["response_schema_name"] == "sentence_translation_response", "record missing response schema name")
    require(len(record["translation_policy_sha256"]) == 64, "record missing translation policy fingerprint")
    require(len(record["request_contract_sha256"]) == 64, "record missing full request contract fingerprint")
    require(len(record["pipeline_contract_sha256"]) == 64, "record missing quality pipeline fingerprint")
    require(len(record["source_context_sha256"]) == 64, "record missing structural context fingerprint")
    citation = record["citations"][0]
    require(citation["source_text_sha256"] == target["source_text_sha256"], "citation source hash is incorrect")
    require(citation["sentence_text_sha256"] == target["sentence_text_sha256"], "citation sentence hash is incorrect")
    require(citation["source_context_sha256"] == record["source_context_sha256"], "citation context hash is incorrect")
    public_record = public_translation_record(record)
    require("literal_gloss" not in public_record, "public sentence translation record should hide literal_gloss")
    require("key_terms" not in public_record, "public sentence translation record should hide key_terms")
    markdown = export_sentence_translations_markdown([public_record])
    require("번역 목록" in markdown, "sentence translation markdown export heading missing")
    require("번역" in markdown and "해설" in markdown, "sentence translation markdown export should use reader-language section labels")
    require("Reviewed Gemma" not in markdown, "sentence translation markdown export should hide runtime-oriented title")
    require("Review:" not in markdown, "sentence translation markdown export should hide review-state metadata")
    require("Reviewed:" not in markdown, "sentence translation markdown export should hide reviewed timestamps")
    for noisy_text in ["Sentence Translations", " translations", "Translation", "Commentary", "Original", "Source:"]:
        require(noisy_text not in markdown, f"sentence translation markdown export should avoid English label {noisy_text!r}")
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
        passing_pipeline_output("older translation", "older commentary"),
    )
    rejected = build_record(
        target,
        prompt_bundle,
        passing_pipeline_output("rejected translation", "rejected commentary"),
    )
    rejected["review_state"] = "rejected"
    newest = build_record(
        target,
        prompt_bundle,
        passing_pipeline_output("newest translation", "newest commentary"),
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
        stale_contract = dict(newest)
        stale_contract["request_contract_sha256"] = "0" * 64
        path.write_text(json.dumps(stale_contract, ensure_ascii=False) + "\n", encoding="utf-8")
        require(find_cached_record(path, target, prompt_bundle) is None, "cache should reject a stale model request contract")
        stale_pipeline = dict(newest)
        stale_pipeline["pipeline_contract_sha256"] = "0" * 64
        path.write_text(json.dumps(stale_pipeline, ensure_ascii=False) + "\n", encoding="utf-8")
        require(find_cached_record(path, target, prompt_bundle) is None, "cache should reject a stale quality pipeline contract")

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
            metadata_record = dict(stored)
            metadata_record["id"] = "wittgenstein-metadata-demo-translation"
            metadata_record["corpus_id"] = "wittgenstein"
            metadata_record["work_id"] = "10.7.10"
            metadata_record["variant_id"] = "source_metadata"
            metadata_record["target_url"] = "/work/wittgenstein/10.7.10?variant=source_metadata#p-0001.s001"
            metadata_record["translation"] = "metadata generated translation"
            metadata_record["commentary"] = "metadata generated commentary"
            metadata_record["review_state"] = "generated"
            metadata_path = sentence_translation_service.ai_record_path("wittgenstein")
            metadata_path.write_text(json.dumps(metadata_record, ensure_ascii=False) + "\n", encoding="utf-8")
            all_records = sentence_translations_for_export({"review_state": ["all"]})
            require(
                {record["corpus_id"] for record in all_records} == {"nietzsche", "bible", "wittgenstein"},
                "sentence translation export without corpus_id should include all corpora",
            )
            require(all_records[-1]["variant_id"] == "source_metadata", "metadata translations should not lead review lists")
            require(all_records[0]["variant_id"] != "source_metadata", "primary text translations should lead review lists")
            filtered_records = sentence_translations_for_export({"review_state": ["all"], "q": ["newest"]})
            require(len(filtered_records) == 1, "sentence translation export q filter count failed")
            require(filtered_records[0]["translation"] == "newest translation", "sentence translation export q filter mismatch")
            empty_filtered_records = sentence_translations_for_export({"review_state": ["all"], "q": ["not-present"]})
            require(empty_filtered_records == [], "sentence translation export q filter should allow empty results")
            all_summary = sentence_translations_summary_from_query({"review_state": ["all"]})
            require(all_summary["count"] == 3, "sentence translation summary without corpus_id should count all corpora")
            require(all_summary["review_state_counts"]["generated"] == 2, "all-corpus summary generated count failed")
            require(all_summary["review_state_counts"]["reviewed"] == 1, "all-corpus summary reviewed count failed")
            deleted = delete_sentence_translation_from_query(
                public_legacy["id"],
                {"corpus_id": [target["corpus_id"]]},
            )
            require(deleted["id"] == public_legacy["id"], "legacy public id should support permanent deletion")
            require(iter_cached_records(path) == [], "permanent deletion should remove the stored translation")
            try:
                delete_sentence_translation(target["corpus_id"], public_legacy["id"])
            except FileNotFoundError:
                pass
            else:
                require(False, "deleting a missing sentence translation should fail")
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir


def check_restored_source_target() -> None:
    target = sentence_target_bundle("nietzsche", "GM", "p-0023", "p-0023.s001", "")
    require(target["sentence_id"] == "p-0023.s001", "restored sentence target id mismatch")
    require(len(target["source_context"]) <= MAX_CONTEXT_CHARS, "restored structural context exceeds limit")
    require(target["source_context"].count("<TARGET_SENTENCE>") == 1, "restored structural context missing target marker")
    require(len(target["context_segments"]) >= 2, "restored structural context should include an adjacent paragraph")
    require(any(item["position"] == "target" for item in target["context_segments"]), "context audit missing target paragraph")
    check_prompt_and_record(target)
    check_cache_and_review_compatibility(target)


def check_translation_cache_paths_use_bounded_source_reads() -> None:
    source_path = SEGMENT_FILES["nietzsche"]
    source_size = source_path.stat().st_size
    read_sizes: list[int] = []
    model_calls = 0
    original_open = Path.open

    class TrackingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def seek(self, *args):
            return self.handle.seek(*args)

        def read(self, size: int = -1):
            require(size > 0, "translation source lookup attempted an unbounded JSONL read")
            read_sizes.append(size)
            return self.handle.read(size)

    def tracked_open(path: Path, mode: str = "r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == source_path and mode == "rb":
            return TrackingReader(handle)
        return handle

    def fake_pipeline(_prompt_bundle: dict) -> dict:
        nonlocal model_calls
        model_calls += 1
        return passing_pipeline_output("bounded lookup test translation", "bounded lookup test commentary")

    payload = {
        "corpus_id": "nietzsche",
        "work_id": "GM",
        "variant_id": "",
        "segment_id": "p-0023",
        "sentence_id": "p-0023.s001",
    }
    with tempfile.TemporaryDirectory(prefix="philo_translation_offset_") as temp_dir:
        original_ai_dir = sentence_translation_service.AI_DIR
        sentence_translation_service.AI_DIR = Path(temp_dir)
        try:
            with (
                patch.object(Path, "open", tracked_open),
                patch.object(sentence_translation_service, "run_translation_pipeline", fake_pipeline),
            ):
                generated = sentence_translation_service.sentence_translation_from_payload(payload)
                cached = sentence_translation_service.sentence_translation_from_payload(payload)
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir

    require(generated["cached"] is False, "first isolated translation request should be a cache miss")
    require(cached["cached"] is True, "second isolated translation request should be a cache hit")
    require(model_calls == 1, "cache hit should not call the model")
    require(len(read_sizes) >= 2, "cache miss and cache hit should resolve indexed source records")
    require(len(read_sizes) < 64, "structural context lookup read an unreasonable number of source records")
    require(all(size < source_size for size in read_sizes), "translation request read the entire segment JSONL")


def check_strict_model_output_contract() -> None:
    invalid_outputs = [
        "not json",
        json.dumps({"translation": "번역", "commentary": ""}),
        json.dumps({"translation": "번역", "commentary": "", "cautions": [], "extra": "no"}),
        json.dumps({"translation": "", "commentary": "", "cautions": []}),
        json.dumps({"translation": "번역", "commentary": "", "cautions": "none"}),
        json.dumps({"translation": "번역", "commentary": [], "cautions": []}),
    ]
    for content in invalid_outputs:
        try:
            normalized_model_output(content)
        except TranslationModelResponseError:
            pass
        else:
            require(False, f"invalid model output should be rejected: {content}")


def critic_issue(severity: str = "major") -> dict[str, str]:
    return {
        "source_span": "Vaterschaft dieses Buches",
        "translation_span": "이 책의 저작권",
        "category": "semantic_substitution",
        "severity": severity,
        "explanation": "부성의 비유가 근거 없는 법률 개념으로 치환되었다.",
    }


def check_strict_critic_output_contract() -> None:
    valid = normalized_critic_output(
        json.dumps({"verdict": "revise", "issues": [critic_issue()]}, ensure_ascii=False)
    )
    require(valid["issues"][0]["severity"] == "major", "valid critic issue was not preserved")
    invalid_outputs = [
        "not json",
        json.dumps({"verdict": "pass", "issues": [critic_issue()]}),
        json.dumps({"verdict": "revise", "issues": []}),
        json.dumps({"verdict": "fail", "issues": []}),
        json.dumps({"verdict": "revise", "issues": [{**critic_issue(), "category": "style"}]}),
        json.dumps({"verdict": "revise", "issues": [{**critic_issue(), "extra": "no"}]}),
    ]
    for content in invalid_outputs:
        try:
            normalized_critic_output(content)
        except TranslationModelResponseError:
            pass
        else:
            require(False, f"invalid critic output should be rejected: {content}")


def check_critic_prompt_boundary(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    critic_bundle = build_critic_prompt_bundle(prompt_bundle, "이 책의 저작권을 얻은 사람")
    require(critic_bundle["response_schema"] == CRITIC_RESPONSE_SCHEMA, "critic response schema drifted")
    require(critic_bundle["generation_parameters"]["temperature"] == 0.0, "critic temperature must be zero")
    require("이 책의 저작권을 얻은 사람" in critic_bundle["prompt"], "critic prompt missing draft translation")
    require("translator's commentary is intentionally absent" in critic_bundle["prompt"], "critic prompt must declare commentary absent")


def check_quality_pipeline_contract(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    draft = {"translation": "초벌 번역", "commentary": "초벌 해설", "cautions": []}

    with (
        patch.object(sentence_translation_service, "call_llama_server", return_value=draft),
        patch.object(sentence_translation_service, "call_critic_server", return_value={"verdict": "pass", "issues": []}),
        patch.object(sentence_translation_service, "call_revision_server") as revision_call,
    ):
        passed = run_translation_pipeline(prompt_bundle)
    require(passed["quality_state"] == "critic_pass", "passing draft quality state is incorrect")
    require(passed["revision_count"] == 0, "passing draft should not be revised")
    require(not revision_call.called, "passing draft should not call revision")

    with (
        patch.object(sentence_translation_service, "call_llama_server", return_value=draft),
        patch.object(
            sentence_translation_service,
            "call_critic_server",
            side_effect=[{"verdict": "revise", "issues": [critic_issue()]}, {"verdict": "pass", "issues": []}],
        ),
        patch.object(
            sentence_translation_service,
            "call_revision_server",
            return_value={"translation": "이 책을 낳은 사상가", "commentary": "부성 비유를 보존했다.", "cautions": []},
        ) as revision_call,
    ):
        revised = run_translation_pipeline(prompt_bundle)
    require(revised["quality_state"] == "critic_pass_after_revision", "revised draft quality state is incorrect")
    require(revised["revision_count"] == 1, "major issue should trigger one revision")
    require(revision_call.call_count == 1, "major issue should trigger exactly one revision")

    with (
        patch.object(sentence_translation_service, "call_llama_server", return_value=draft),
        patch.object(
            sentence_translation_service,
            "call_critic_server",
            return_value={"verdict": "revise", "issues": [critic_issue("minor")]},
        ),
        patch.object(sentence_translation_service, "call_revision_server") as revision_call,
    ):
        minor = run_translation_pipeline(prompt_bundle)
    require(minor["quality_state"] == "needs_human_review", "minor-only issues should require human review")
    require(minor["revision_count"] == 0, "minor-only issues should not trigger revision")
    require(not revision_call.called, "minor-only issues must not call revision")

    with (
        patch.object(sentence_translation_service, "call_llama_server", return_value=draft),
        patch.object(
            sentence_translation_service,
            "call_critic_server",
            side_effect=TranslationModelResponseError("critic failed"),
        ),
    ):
        errored = run_translation_pipeline(prompt_bundle)
    require(errored["quality_state"] == "critic_error", "critic failure quality state is incorrect")
    require(any("인간 검토" in caution for caution in errored["cautions"]), "critic failure should add a caution")


def check_llama_json_schema_contract(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            output = {"translation": "삶은 의지다.", "commentary": "", "cautions": []}
            payload = {"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]}
            return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch.object(sentence_translation_service, "urlopen", fake_urlopen):
        output = sentence_translation_service.call_llama_server(prompt_bundle)
    require(output["translation"] == "삶은 의지다.", "schema-constrained response was not normalized")
    body = captured["body"]
    require(body["response_format"]["type"] == "json_schema", "llama request must use JSON Schema response format")
    require(body["response_format"]["json_schema"] == TRANSLATION_RESPONSE_SCHEMA, "llama response schema drifted")
    require(body["temperature"] <= 0.1, "llama request temperature is too high")
    require(body["seed"] == 0, "llama request should record a deterministic seed")


def check_human_approved_translation_profile_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="philo_translation_profile_") as temp_dir:
        path = Path(temp_dir) / "translation_profiles.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profiles": [
                        {
                            "profile_id": "nietzsche-demo-v1",
                            "corpus_id": "nietzsche",
                            "work_id": "demo",
                            "variant_id": "",
                            "approval_state": "approved",
                            "terminology": [{"source": "Macht", "target": "힘", "note": "연구자 승인"}],
                            "style_notes": ["반복을 보존한다."],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        policy = translation_policy_bundle("nietzsche", "demo", path=path)
        require(policy["profile_id"] == "nietzsche-demo-v1", "approved translation profile was not selected")
        require(policy["terminology"][0]["target"] == "힘", "approved terminology was not preserved")

        rejected_payload = json.loads(path.read_text(encoding="utf-8"))
        rejected_payload["profiles"][0]["approval_state"] = "generated"
        path.write_text(json.dumps(rejected_payload, ensure_ascii=False), encoding="utf-8")
        try:
            translation_policy_bundle("nietzsche", "demo", path=path)
        except ValueError:
            pass
        else:
            require(False, "non-approved translation profile should be rejected")


def check_runtime_error_copy(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    original_urlopen = sentence_translation_service.urlopen

    def failing_urlopen(*_args, **_kwargs):
        raise OSError("connection refused")

    sentence_translation_service.urlopen = failing_urlopen
    try:
        try:
            sentence_translation_service.call_llama_server(prompt_bundle)
        except ConnectionError as exc:
            message = str(exc)
            require("번역 준비가 필요합니다." in message, "runtime connection failure should use reader-language copy")
            require("Gemma runtime is not running" not in message, "runtime connection failure should not expose English backend copy")
        else:
            require(False, "runtime connection failure should raise ConnectionError")
    finally:
        sentence_translation_service.urlopen = original_urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate on-demand sentence translation contracts.", allow_abbrev=False)
    parser.add_argument("--with-source-targets", action="store_true")
    args = parser.parse_args()

    check_ai_dir_override_contract()
    check_indexed_source_lookup_contract()
    check_concurrent_cache_writes()
    check_snapshot_read_cache()
    check_sentence_units()
    check_sentence_boundary_context_contract()
    check_strict_model_output_contract()
    check_strict_critic_output_contract()
    check_human_approved_translation_profile_contract()
    synthetic_target = synthetic_sentence_target()
    check_prompt_and_record(synthetic_target)
    check_critic_prompt_boundary(synthetic_target)
    check_quality_pipeline_contract(synthetic_target)
    check_llama_json_schema_contract(synthetic_target)
    check_cache_and_review_compatibility(synthetic_target)
    check_runtime_error_copy(synthetic_target)
    if args.with_source_targets:
        check_restored_source_target()
        check_translation_cache_paths_use_bounded_source_reads()
    print("sentence translation contracts ok")


if __name__ == "__main__":
    main()
