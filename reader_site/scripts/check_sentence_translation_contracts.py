from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from sentence_units import render_sentence_spans, sentence_units  # noqa: E402
from services.sentence_targets import sentence_target_bundle  # noqa: E402
from services import sentence_translations as sentence_translation_service  # noqa: E402
from services.gemma_response_cache import (  # noqa: E402
    CACHE_DB_ENV,
    CACHE_SCHEMA_VERSION as GEMMA_CACHE_SCHEMA_VERSION,
    build_cache_key,
    cache_db_path,
)
from services import gemma_runtime as gemma_runtime_service  # noqa: E402
from services.gemma_runtime import GemmaRuntimeBusy, GemmaRuntimeTimeout  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    PROMPT_TEMPLATE_ID,
    build_record,
    build_sentence_prompt_bundle,
    export_sentence_translations_markdown,
    find_cached_record,
    normalized_model_output,
    public_record_id,
    public_translation_record,
    sentence_gemma_cache_identity,
    sentence_translation_from_payload,
    sentence_translations_for_export,
    sentence_translations_summary_from_query,
    update_sentence_translation_review,
)
from services.source_targets import sha256_text  # noqa: E402
from scripts.check_ai_records_contracts import validate_file  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_ai_dir_override_contract() -> None:
    source = Path(sentence_translation_service.__file__).read_text(encoding="utf-8")
    require("PHILO_AI_DIR" in source, "sentence translation storage should support an isolated AI data directory")
    require('os.environ.get("PHILO_AI_DIR"' in source, "sentence translation storage should use PHILO_AI_DIR")


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
    require(record["gemma_response_cache_schema_version"] == GEMMA_CACHE_SCHEMA_VERSION, "record cache schema missing")
    require(len(record["gemma_response_cache_key"]) == 64, "record cache key must be a SHA-256 hex digest")
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
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir


def check_gemma_response_cache_contract(target: dict) -> None:
    prompt_bundle = build_sentence_prompt_bundle(target)
    identity = sentence_gemma_cache_identity(prompt_bundle)
    same_key = build_cache_key(
        namespace=identity["namespace"],
        prompt_version=identity["prompt_version"],
        model_name=identity["model_name"],
        input_sha256=identity["input_sha256"],
        options=dict(reversed(list(identity["options"].items()))),
    )
    require(identity["cache_key"] == same_key, "Gemma response cache key should be stable across option order")
    require(identity["schema_version"] == GEMMA_CACHE_SCHEMA_VERSION, "Gemma response cache schema version mismatch")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        original_ai_dir = sentence_translation_service.AI_DIR
        original_target_builder = sentence_translation_service.sentence_target_bundle
        original_llama = sentence_translation_service.call_llama_server
        original_cache_db = os.environ.get(CACHE_DB_ENV)
        call_count = {"count": 0}

        def fake_sentence_target_bundle(*_args):
            return dict(target)

        def fake_llama(_prompt_bundle: dict, request_id: str | None = None) -> dict:
            call_count["count"] += 1
            require(bool(request_id), "runtime cache miss should assign a Gemma request id")
            return {
                "translation": f"cached translation {call_count['count']}",
                "commentary": "cached commentary",
                "cautions": [],
            }

        sentence_translation_service.AI_DIR = temp_root / "ai"
        sentence_translation_service.sentence_target_bundle = fake_sentence_target_bundle
        sentence_translation_service.call_llama_server = fake_llama
        os.environ[CACHE_DB_ENV] = str(temp_root / "runtime.local" / "gemma_response_cache.sqlite")
        try:
            payload = {
                "corpus_id": target["corpus_id"],
                "work_id": target["work_id"],
                "variant_id": target.get("variant_id", ""),
                "segment_id": target["segment_id"],
                "sentence_id": target["sentence_id"],
            }
            first = sentence_translation_from_payload(payload)
            require(first["cached"] is False, "first sentence translation should be a cache miss")
            require(first["metadata"]["cache"]["hit"] is False, "first response cache metadata should mark miss")
            require(first["metadata"]["cache"]["source"] == "gemma_runtime", "first response should come from runtime")
            require(first["metadata"]["gemma_request"]["request_id"].startswith("gemma-"), "runtime miss should return request id metadata")
            require(first["metadata"]["gemma_request"]["status"] == "completed", "runtime miss should mark request completed")
            require(call_count["count"] == 1, "first request should call Gemma once")

            ai_path = sentence_translation_service.ai_record_path(target["corpus_id"])
            ai_path.unlink()
            second = sentence_translation_from_payload(payload)
            require(second["cached"] is True, "second request should be served from Gemma response cache")
            require(second["metadata"]["cache"]["hit"] is True, "second response cache metadata should mark hit")
            require(
                second["metadata"]["cache"]["source"] == "gemma_response_cache",
                "second response should come from Gemma response cache",
            )
            require(call_count["count"] == 1, "Gemma response cache hit should not call Gemma again")
            require(second["record"]["translation"] == "cached translation 1", "cached response payload mismatch")

            ai_path.unlink()
            cache_path = cache_db_path()
            cache_path.write_bytes(b"not a sqlite database")
            third = sentence_translation_from_payload(payload)
            require(third["cached"] is False, "corrupt cache should fall back to runtime miss")
            require(call_count["count"] == 2, "corrupt cache should not prevent runtime regeneration")
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir
            sentence_translation_service.sentence_target_bundle = original_target_builder
            sentence_translation_service.call_llama_server = original_llama
            if original_cache_db is None:
                os.environ.pop(CACHE_DB_ENV, None)
            else:
                os.environ[CACHE_DB_ENV] = original_cache_db


def check_gemma_runtime_limits_contract() -> None:
    original_queue_timeout = os.environ.get(gemma_runtime_service.QUEUE_TIMEOUT_SECONDS_ENV)
    original_request_timeout = os.environ.get(gemma_runtime_service.REQUEST_TIMEOUT_SECONDS_ENV)
    started = threading.Event()
    release = threading.Event()
    results: list[str] = []
    errors: list[Exception] = []

    def long_operation(_timeout_seconds: float) -> str:
        started.set()
        release.wait(2.0)
        return "held"

    def run_holder() -> None:
        try:
            results.append(gemma_runtime_service.run_gemma_operation(long_operation, request_id="gemma-test-holder"))
        except Exception as exc:
            errors.append(exc)

    os.environ[gemma_runtime_service.QUEUE_TIMEOUT_SECONDS_ENV] = "0.05"
    os.environ[gemma_runtime_service.REQUEST_TIMEOUT_SECONDS_ENV] = "1"
    gemma_runtime_service.reset_gemma_runtime_for_tests(max_concurrency=1)
    thread = threading.Thread(target=run_holder)
    thread.start()
    try:
        require(started.wait(1.0), "Gemma runtime limit test holder did not start")
        try:
            gemma_runtime_service.run_gemma_operation(lambda _timeout_seconds: "late", request_id="gemma-test-busy")
        except GemmaRuntimeBusy as exc:
            metadata = exc.response_metadata()["gemma_request"]
            require(exc.status_code == 429, "busy Gemma request should map to HTTP 429")
            require(metadata["request_id"] == "gemma-test-busy", "busy response should preserve request id")
            require(metadata["status"] == "busy", "busy response should expose request status")
        else:
            require(False, "concurrent Gemma request should fail fast when the runtime queue is full")

        release.set()
        thread.join(2.0)
        require(not thread.is_alive(), "Gemma runtime limit test holder did not finish")
        require(not errors, f"Gemma runtime holder failed: {errors!r}")
        require(results == ["held"], "Gemma runtime holder result mismatch")
        status = gemma_runtime_service.gemma_runtime_status()
        require(status["busy_count"] == 1, "Gemma runtime status should count busy requests")
        require(status["completed_count"] == 1, "Gemma runtime status should count completed requests")
    finally:
        release.set()
        thread.join(2.0)
        if original_queue_timeout is None:
            os.environ.pop(gemma_runtime_service.QUEUE_TIMEOUT_SECONDS_ENV, None)
        else:
            os.environ[gemma_runtime_service.QUEUE_TIMEOUT_SECONDS_ENV] = original_queue_timeout
        if original_request_timeout is None:
            os.environ.pop(gemma_runtime_service.REQUEST_TIMEOUT_SECONDS_ENV, None)
        else:
            os.environ[gemma_runtime_service.REQUEST_TIMEOUT_SECONDS_ENV] = original_request_timeout
        gemma_runtime_service.reset_gemma_runtime_for_tests()


def check_restored_source_target() -> None:
    target = sentence_target_bundle("nietzsche", "GM", "p-0023", "p-0023.s001", "")
    require(target["sentence_id"] == "p-0023.s001", "restored sentence target id mismatch")
    check_prompt_and_record(target)
    check_cache_and_review_compatibility(target)
    check_gemma_response_cache_contract(target)


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
            require("connection refused" not in message, "runtime connection failure should not expose socket details")
            metadata = exc.response_metadata()["gemma_request"] if hasattr(exc, "response_metadata") else {}
            require(metadata.get("request_id", "").startswith("gemma-"), "runtime failure should include request id metadata")
            require(metadata.get("status") == "unavailable", "runtime failure should expose unavailable status")
        else:
            require(False, "runtime connection failure should raise ConnectionError")

        def timeout_urlopen(*_args, **_kwargs):
            raise TimeoutError("timed out")

        sentence_translation_service.urlopen = timeout_urlopen
        try:
            sentence_translation_service.call_llama_server(prompt_bundle)
        except GemmaRuntimeTimeout as exc:
            metadata = exc.response_metadata()["gemma_request"]
            require(exc.status_code == 504, "Gemma timeout should map to HTTP 504")
            require(metadata["status"] == "timeout", "Gemma timeout should expose timeout status")
            require("시간이 초과" in str(exc), "Gemma timeout should use clear reader-language copy")
        else:
            require(False, "Gemma timeout should raise GemmaRuntimeTimeout")
    finally:
        sentence_translation_service.urlopen = original_urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate on-demand sentence translation contracts.", allow_abbrev=False)
    parser.add_argument("--with-source-targets", action="store_true")
    args = parser.parse_args()

    check_ai_dir_override_contract()
    check_sentence_units()
    synthetic_target = synthetic_sentence_target()
    check_prompt_and_record(synthetic_target)
    check_cache_and_review_compatibility(synthetic_target)
    check_gemma_response_cache_contract(synthetic_target)
    check_gemma_runtime_limits_contract()
    check_runtime_error_copy(synthetic_target)
    if args.with_source_targets:
        check_restored_source_target()
    print("sentence translation contracts ok")


if __name__ == "__main__":
    main()
