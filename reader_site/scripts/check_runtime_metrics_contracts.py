from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.runtime_metrics import (  # noqa: E402
    LOG_BYTES_ENV,
    RUNTIME_DIR_ENV,
    record_gemma_cache_event,
    record_gemma_request,
    record_search_request,
    reset_runtime_metrics_for_tests,
    runtime_metrics_log_path,
    runtime_metrics_snapshot,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    original_dir = os.environ.get(RUNTIME_DIR_ENV)
    original_log_bytes = os.environ.get(LOG_BYTES_ENV)
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ[RUNTIME_DIR_ENV] = temp_dir
        os.environ[LOG_BYTES_ENV] = "65536"
        reset_runtime_metrics_for_tests()
        record_search_request(
            duration_ms=1234.5,
            status="ok",
            query="sensitive search phrase",
            corpus_id="nietzsche",
            work_id="GM",
            variant_id="",
            limit=5,
            offset=0,
            engine="sqlite-fts5",
            result_count=5,
        )
        record_gemma_cache_event(
            source="gemma_response_cache",
            hit=True,
            cache_key="cache-key-secret",
            prompt_version="sentence_translation_study_v1",
            model_name="gemma",
            corpus_id="nietzsche",
            work_id="GM",
            segment_id="p-0001",
            sentence_id="p-0001.s001",
        )
        record_gemma_cache_event(
            source="gemma_runtime",
            hit=False,
            cache_key="cache-key-secret",
            prompt_version="sentence_translation_study_v1",
            model_name="gemma",
            corpus_id="nietzsche",
            work_id="GM",
            segment_id="p-0001",
            sentence_id="p-0001.s001",
        )
        record_gemma_request(
            duration_ms=1500.0,
            status="timeout",
            request_id="gemma-test",
            model_name="gemma",
            prompt_sha256="a" * 64,
            input_sha256="b" * 64,
            prompt_chars=1200,
            corpus_id="nietzsche",
            work_id="GM",
            segment_id="p-0001",
            sentence_id="p-0001.s001",
            error_type="GemmaRuntimeTimeout",
        )
        snapshot = runtime_metrics_snapshot()
        counters = snapshot["counters"]
        require(counters["search"]["requests"] == 1, "search metrics counter failed")
        require(counters["gemma"]["timeout"] == 1, "Gemma timeout counter failed")
        require(counters["cache"]["gemma_response_cache_hit"] == 1, "Gemma cache hit counter failed")
        require(counters["cache"]["miss"] == 1, "Gemma cache miss counter failed")
        require(snapshot["recent_slow_requests"], "slow request ring buffer should include slow events")
        log_path = runtime_metrics_log_path()
        require(log_path.exists(), "runtime metrics log file missing")
        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        require(len(lines) == 4, "runtime metrics log should contain four JSONL records")
        search_context = lines[0]["context"]
        require("query_hash" in search_context and "query" not in search_context, "search metrics should not log raw query")
        require("sensitive search phrase" not in log_path.read_text(encoding="utf-8"), "metrics log leaked raw query")
    if original_dir is None:
        os.environ.pop(RUNTIME_DIR_ENV, None)
    else:
        os.environ[RUNTIME_DIR_ENV] = original_dir
    if original_log_bytes is None:
        os.environ.pop(LOG_BYTES_ENV, None)
    else:
        os.environ[LOG_BYTES_ENV] = original_log_bytes
    reset_runtime_metrics_for_tests()
    print("runtime metrics contracts ok")


if __name__ == "__main__":
    main()
