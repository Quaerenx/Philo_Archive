from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora import archive as archive_service  # noqa: E402
from corpora.archive import archive_title_search, build_archive, build_archive_summary  # noqa: E402
from corpora.catalogs import bible_segments_payload_from_query  # noqa: E402
import runtime_status  # noqa: E402
from runtime_status import (  # noqa: E402
    TTLCache,
    build_artifact_manifest,
    build_public_artifact_manifest,
    build_public_gemma_health,
    build_public_runtime_health,
    build_runtime_health,
    read_gemma_launcher_state,
)
from scripts import build_archive_catalog as archive_catalog_script  # noqa: E402
from services.sentence_translations import (  # noqa: E402
    sentence_translations_export_from_query,
    sentence_translations_summary_from_query,
)
from services.source_targets import sha256_text, source_target_payload_from_query  # noqa: E402
from services.study_sessions import study_session_export_from_query  # noqa: E402


SOURCE_TARGET_BUNDLE_KEYS = {
    "schema_version",
    "record_type",
    "corpus_id",
    "work_id",
    "variant_id",
    "target_id",
    "target_url",
    "segment_type",
    "label",
    "source_text",
    "source_text_preview",
    "source_text_chars",
    "source_text_sha256",
}

FORBIDDEN_SOURCE_TARGET_KEYS = {
    "path",
    "source_path",
    "source_root",
    "local_path",
    "metadata_path",
}

FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS = {
    "base_url",
    "bytes",
    "corpus_root",
    "error",
    "metadata_error",
    "models",
    "modified_at",
    "notes",
    "path",
    "primary_output",
    "regeneration_commands",
    "sha256",
    "site_root",
    "source_root",
    "uses_env_corpus_root",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_keys(record: dict[str, Any], keys: set[str], context: str) -> None:
    missing = sorted(keys - set(record))
    require(not missing, f"{context} missing keys: {', '.join(missing)}")


def check_file_record(record: dict[str, Any], context: str) -> None:
    require_keys(record, {"name", "kind", "role", "path", "exists"}, context)
    require(isinstance(record["exists"], bool), f"{context}.exists must be bool")
    if record["exists"]:
        require_keys(record, {"bytes", "modified_at"}, context)
        require(isinstance(record["bytes"], int), f"{context}.bytes must be int")


def check_archive(payload: dict[str, Any]) -> None:
    require_keys(payload, {"generated_at", "corpora"}, "archive")
    require(isinstance(payload["corpora"], list), "archive.corpora must be list")
    require(payload["corpora"], "archive.corpora must not be empty")
    for index, corpus in enumerate(payload["corpora"]):
        context = f"archive.corpora[{index}]"
        require_keys(corpus, {"id", "title", "subtitle", "counts", "links", "sections"}, context)
        require_keys(corpus["counts"], {"files", "links", "bytes"}, f"{context}.counts")
        require(isinstance(corpus["sections"], list), f"{context}.sections must be list")
        for section_index, section in enumerate(corpus["sections"]):
            section_context = f"{context}.sections[{section_index}]"
            require_keys(section, {"title", "count", "links"}, section_context)
            require(isinstance(section["links"], list), f"{section_context}.links must be list")
            for link_index, link in enumerate(section["links"]):
                link_context = f"{section_context}.links[{link_index}]"
                require_keys(link, {"label", "display_title", "href", "source_href", "path", "meta"}, link_context)


def check_archive_title_search() -> None:
    morning = archive_title_search("아침")
    require(morning["count"] == 1, "archive title search should resolve the Korean Morning alias")
    require(morning["results"][0]["href"] == "/work/nietzsche/M", "Morning title search resolved the wrong work")
    require(
        morning["results"][0]["display_title"] == "Morgenröthe / 아침놀",
        "archive title search must return a stable display title",
    )

    genesis = archive_title_search("Genesis")
    require(genesis["count"] == 2, "duplicate Genesis editions should remain separate title results")
    require(
        {result["section_title"] for result in genesis["results"]} == {"Hebrew Bible", "LXX / Deuterocanon"},
        "duplicate Genesis results must identify their source sections",
    )
    for result in genesis["results"]:
        require(
            not ({"path", "source_href"} & set(result)),
            "archive title search should not expose full archive source fields",
        )

    require(len(archive_title_search("a", limit=3)["results"]) <= 3, "archive title search ignored its limit")
    try:
        archive_title_search("a", limit=0)
    except ValueError:
        pass
    else:
        raise AssertionError("archive title search should reject an out-of-range limit")


def check_archive_summary(payload: dict[str, Any]) -> None:
    require_keys(payload, {"schema_version", "generated_at", "corpora"}, "archive summary")
    require(payload["schema_version"] == 1, "archive summary schema_version must be 1")
    require(len(payload["corpora"]) == 4, "archive summary must list four corpora")
    for index, corpus in enumerate(payload["corpora"]):
        require(
            set(corpus) == {"id", "title", "subtitle"},
            f"archive summary corpus {index} must remain lightweight",
        )


def check_health(payload: dict[str, Any]) -> None:
    require_keys(
        payload,
        {"status", "generated_at", "site_root", "corpus_root", "corpora", "search", "gemma", "issues", "next_recommended_upgrades"},
        "health",
    )
    require(payload["status"] in {"ok", "warning"}, "health.status must be ok or warning")
    require(isinstance(payload["issues"], list), "health.issues must be list")
    require(isinstance(payload["next_recommended_upgrades"], list), "health.next_recommended_upgrades must be list")
    for index, corpus in enumerate(payload["corpora"]):
        context = f"health.corpora[{index}]"
        require_keys(
            corpus,
            {
                "corpus_id",
                "title",
                "source_root",
                "source_root_exists",
                "primary_output",
                "primary_output_exists",
                "metadata",
                "segments",
                "notes",
                "work_count",
                "variant_count",
                "metadata_error",
            },
            context,
        )
        check_file_record(corpus["metadata"], f"{context}.metadata")
        check_file_record(corpus["segments"], f"{context}.segments")
        check_file_record(corpus["notes"], f"{context}.notes")
    check_file_record(payload["search"], "health.search")
    require_keys(payload["search"], {"records", "fts5"}, "health.search")
    require_keys(payload["gemma"], {"base_url", "reachable", "model_count", "models", "state"}, "health.gemma")
    require(isinstance(payload["gemma"]["reachable"], bool), "health.gemma.reachable must be bool")
    require(isinstance(payload["gemma"]["model_count"], int), "health.gemma.model_count must be int")
    require(isinstance(payload["gemma"]["models"], list), "health.gemma.models must be list")
    require(
        payload["gemma"]["state"] in {"starting", "ready", "failed", "unavailable"},
        "health.gemma.state must be a public runtime state",
    )


def check_artifacts(payload: dict[str, Any]) -> None:
    require_keys(
        payload,
        {
            "schema_version",
            "generated_at",
            "site_root",
            "corpus_root",
            "uses_env_corpus_root",
            "corpora",
            "artifacts",
            "search",
            "regeneration_commands",
        },
        "artifacts",
    )
    require(payload["schema_version"] == 1, "artifacts.schema_version must be 1")
    require(isinstance(payload["artifacts"], list), "artifacts.artifacts must be list")
    require(isinstance(payload["regeneration_commands"], list), "artifacts.regeneration_commands must be list")
    require(
        any("rebuild_all.py" in command for command in payload["regeneration_commands"]),
        "artifacts.regeneration_commands must include rebuild_all.py",
    )
    require(
        any("build_segment_offset_index.py" in command for command in payload["regeneration_commands"]),
        "artifacts.regeneration_commands must include build_segment_offset_index.py",
    )
    require(
        any("build_archive_catalog.py" in command for command in payload["regeneration_commands"]),
        "artifacts.regeneration_commands must include build_archive_catalog.py",
    )
    require(
        any(artifact.get("name") == "segment_offset_index.sqlite" for artifact in payload["artifacts"]),
        "artifacts.artifacts must include segment_offset_index.sqlite",
    )
    require(
        any(artifact.get("name") == "archive_catalog.local.json" for artifact in payload["artifacts"]),
        "artifacts.artifacts must include archive_catalog.local.json",
    )
    for index, artifact in enumerate(payload["artifacts"]):
        check_file_record(artifact, f"artifacts.artifacts[{index}]")
    check_file_record(payload["search"], "artifacts.search")


def nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(nested_keys(child))
    return keys


def check_public_health(payload: dict[str, Any]) -> None:
    require_keys(payload, {"status", "generated_at", "corpora", "search", "gemma", "issues"}, "public health")
    require(payload["status"] in {"ok", "warning"}, "public health.status must be ok or warning")
    require_keys(payload["search"], {"ready", "fts5"}, "public health.search")
    require_keys(payload["gemma"], {"reachable", "model_count", "state"}, "public health.gemma")
    require(
        payload["gemma"]["state"] in {"starting", "ready", "failed", "unavailable"},
        "public health.gemma.state must be a public runtime state",
    )
    for index, corpus in enumerate(payload["corpora"]):
        require_keys(
            corpus,
            {"corpus_id", "title", "source_ready", "metadata_ready", "segments_ready"},
            f"public health.corpora[{index}]",
        )
    exposed = sorted(FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS & nested_keys(payload))
    require(not exposed, "public health exposes private keys: " + ", ".join(exposed))


def check_public_gemma_health(payload: dict[str, Any]) -> None:
    require_keys(payload, {"status", "generated_at", "gemma"}, "public Gemma health")
    require(payload["status"] in {"ok", "warning"}, "public Gemma health status invalid")
    require_keys(payload["gemma"], {"reachable", "model_count", "state"}, "public Gemma health.gemma")
    require(
        payload["gemma"]["state"] in {"starting", "ready", "failed", "unavailable"},
        "public Gemma health state invalid",
    )
    exposed = sorted(FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS & nested_keys(payload))
    require(not exposed, "public Gemma health exposes private keys: " + ", ".join(exposed))


def check_ttl_cache_contracts() -> None:
    original_monotonic = runtime_status.monotonic
    clock = [100.0]
    runtime_status.monotonic = lambda: clock[0]
    try:
        cache = TTLCache()
        calls = []

        def build_state() -> dict[str, Any]:
            calls.append(clock[0])
            return {"reachable": len(calls) > 1, "nested": {"safe": True}}

        ttl_for_state = lambda value: 3.0 if value["reachable"] else 0.5
        first = cache.get(build_state, ttl_for_state)
        first["nested"]["safe"] = False
        require(cache.get(build_state, ttl_for_state)["nested"]["safe"], "TTL cache leaked caller mutation")
        require(len(calls) == 1, "TTL cache rebuilt inside failure TTL")
        clock[0] += 0.51
        require(cache.get(build_state, ttl_for_state)["reachable"], "TTL cache did not expose changed state after TTL")
        require(len(calls) == 2, "TTL cache did not rebuild after TTL")
        clock[0] += 2.99
        cache.get(build_state, ttl_for_state)
        require(len(calls) == 2, "successful TTL expired too early")
        clock[0] += 0.02
        cache.get(build_state, ttl_for_state)
        require(len(calls) == 3, "successful TTL did not expire")
    finally:
        runtime_status.monotonic = original_monotonic

    cache = TTLCache()
    build_count = 0
    build_lock = threading.Lock()

    def slow_builder() -> dict[str, int]:
        nonlocal build_count
        with build_lock:
            build_count += 1
        time.sleep(0.03)
        return {"build": build_count}

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: cache.get(slow_builder, lambda _value: 1.0), range(8)))
    require(build_count == 1, "concurrent TTL cache requests duplicated the build")
    require({result["build"] for result in results} == {1}, "concurrent TTL cache observed partial values")


def check_archive_cache_contracts() -> None:
    with tempfile.TemporaryDirectory(prefix="philo_archive_cache_contract_") as temporary_directory:
        input_path = Path(temporary_directory) / "metadata.json"
        catalog_path = Path(temporary_directory) / "archive_catalog.local.json"
        input_path.write_text('{"version":1}', encoding="utf-8")

        original_metadata_files = archive_service.ARCHIVE_METADATA_FILES
        original_input_trees = archive_service.ARCHIVE_INPUT_TREES
        original_catalog_path = archive_service.ARCHIVE_CATALOG
        try:
            catalog_path.write_text('{"old":true}', encoding="utf-8")
            original_json_dump = archive_catalog_script.json.dump

            def fail_json_dump(*_args, **_kwargs) -> None:
                raise RuntimeError("simulated interrupted catalog write")

            archive_catalog_script.json.dump = fail_json_dump
            try:
                archive_catalog_script.atomic_write_json(catalog_path, {"new": True})
            except RuntimeError:
                pass
            else:
                raise AssertionError("interrupted archive catalog write should fail")
            finally:
                archive_catalog_script.json.dump = original_json_dump
            require(
                json.loads(catalog_path.read_text(encoding="utf-8")) == {"old": True},
                "interrupted archive catalog write damaged the previous catalog",
            )
            require(
                not list(catalog_path.parent.glob(f".{catalog_path.name}.*.tmp")),
                "interrupted archive catalog write left a temporary file",
            )

            archive_service.ARCHIVE_METADATA_FILES = (input_path,)
            archive_service.ARCHIVE_INPUT_TREES = ()
            archive_service.ARCHIVE_CATALOG = catalog_path
            first_snapshot = archive_service.archive_input_snapshot()
            input_path.write_text('{"version":200}', encoding="utf-8")
            os.utime(input_path, None)
            second_snapshot = archive_service.archive_input_snapshot()
            require(first_snapshot.signature != second_snapshot.signature, "archive input mutation was not detected")

            cached_archive = {"generated_at": "contract", "corpora": []}
            catalog_path.write_text(
                json.dumps(
                    {
                        "schema_version": archive_service.ARCHIVE_SCHEMA_VERSION,
                        "input_signature": second_snapshot.signature,
                        "archive": cached_archive,
                    }
                ),
                encoding="utf-8",
            )
            require(
                archive_service.load_archive_catalog(second_snapshot) == cached_archive,
                "matching archive catalog was not reused",
            )
            input_path.write_text('{"version":3000}', encoding="utf-8")
            os.utime(input_path, None)
            stale_snapshot = archive_service.archive_input_snapshot()
            require(
                archive_service.load_archive_catalog(stale_snapshot) is None,
                "stale archive catalog was accepted",
            )
            catalog_path.write_text("{broken", encoding="utf-8")
            require(
                archive_service.load_archive_catalog(stale_snapshot) is None,
                "corrupt archive catalog was accepted",
            )
        finally:
            archive_service.ARCHIVE_METADATA_FILES = original_metadata_files
            archive_service.ARCHIVE_INPUT_TREES = original_input_trees
            archive_service.ARCHIVE_CATALOG = original_catalog_path

    original_snapshot_builder = archive_service.archive_input_snapshot
    original_catalog_loader = archive_service.load_archive_catalog
    original_catalog_builder = archive_service.build_archive_catalog
    original_cache = archive_service.ARCHIVE_CACHE
    original_cache_state = archive_service._ARCHIVE_CACHE_STATE
    build_count = 0
    build_lock = threading.Lock()
    signature = (("contract.json", "file", 1, 1, 1, 1),)
    snapshot = archive_service.ArchiveInputSnapshot(signature, {})

    def slow_catalog_builder(_snapshot=None) -> dict[str, Any]:
        nonlocal build_count
        with build_lock:
            build_count += 1
        time.sleep(0.03)
        return {
            "schema_version": archive_service.ARCHIVE_SCHEMA_VERSION,
            "input_signature": signature,
            "archive": {"generated_at": "contract", "corpora": []},
        }

    try:
        archive_service.ARCHIVE_CACHE = None
        archive_service._ARCHIVE_CACHE_STATE = None
        archive_service.archive_input_snapshot = lambda: snapshot
        archive_service.load_archive_catalog = lambda _snapshot: None
        archive_service.build_archive_catalog = slow_catalog_builder
        with ThreadPoolExecutor(max_workers=8) as executor:
            payloads = list(executor.map(lambda _: archive_service.build_archive(), range(8)))
        require(build_count == 1, "concurrent archive requests duplicated catalog construction")
        require(all(payload is payloads[0] for payload in payloads), "archive cache did not publish one immutable snapshot")
    finally:
        archive_service.archive_input_snapshot = original_snapshot_builder
        archive_service.load_archive_catalog = original_catalog_loader
        archive_service.build_archive_catalog = original_catalog_builder
        archive_service.ARCHIVE_CACHE = original_cache
        archive_service._ARCHIVE_CACHE_STATE = original_cache_state


def check_public_artifacts(payload: dict[str, Any]) -> None:
    require_keys(payload, {"schema_version", "generated_at", "corpora", "artifacts", "search"}, "public artifacts")
    require(payload["schema_version"] == 1, "public artifacts.schema_version must be 1")
    require(isinstance(payload["artifacts"], list), "public artifacts.artifacts must be list")
    for index, artifact in enumerate(payload["artifacts"]):
        require_keys(artifact, {"name", "kind", "role", "ready"}, f"public artifacts.artifacts[{index}]")
    exposed = sorted(FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS & nested_keys(payload))
    require(not exposed, "public artifacts expose private keys: " + ", ".join(exposed))


def check_gemma_launcher_states() -> None:
    base_url = "http://127.0.0.1:9999"
    now = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "gemma-state.json"

        def write_state(state: str, updated_at: datetime, marker_base_url: str = base_url) -> None:
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": state,
                        "base_url": marker_base_url,
                        "updated_at": updated_at.isoformat(),
                    }
                ),
                encoding="utf-8",
            )

        write_state("starting", now)
        require(
            read_gemma_launcher_state(path, base_url, now) == {"state": "starting"},
            "fresh Gemma launcher state should remain starting",
        )
        write_state("starting", now - timedelta(minutes=4))
        require(
            read_gemma_launcher_state(path, base_url, now) == {"state": "unavailable"},
            "stale Gemma launcher state should become unavailable",
        )
        write_state("failed", now)
        require(
            read_gemma_launcher_state(path, base_url, now) == {"state": "failed"},
            "failed Gemma launcher state should remain failed",
        )
        write_state("ready", now, "http://127.0.0.1:8794")
        require(
            read_gemma_launcher_state(path, base_url, now) == {},
            "Gemma launcher state for another base URL should be ignored",
        )


def check_bible_segments_payload() -> None:
    empty = bible_segments_payload_from_query({})
    require(empty == {"segments": []}, "empty bible segments query should return empty segments")

    genesis = bible_segments_payload_from_query({"work_id": ["oshb.Gen"]})
    require(genesis.get("segments"), "Genesis bible segments payload returned no segments")
    first = genesis["segments"][0]
    require_keys(first, {"corpus_id", "work_id", "segment_id", "label", "url"}, "bible segment")
    require(first["work_id"] == "oshb.Gen", "bible segment work_id mismatch")

    try:
        bible_segments_payload_from_query({"work_id": ["missing.Work"]})
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing bible work should raise FileNotFoundError")


def check_source_target_payload() -> None:
    cases = [
        {"corpus_id": ["nietzsche"], "work_id": ["AC"], "target_id": ["sec-1"], "expected_segment_type": ["section"]},
        {"corpus_id": ["nietzsche"], "work_id": ["GM"], "target_id": ["p-0023"]},
        {"corpus_id": ["bible"], "work_id": ["sblgnt.John"], "target_id": ["John.3.16"]},
        {
            "corpus_id": ["kierkegaard"],
            "work_id": ["ba"],
            "target_id": ["sks-0001"],
            "variant_id": ["text"],
        },
        {
            "corpus_id": ["wittgenstein"],
            "work_id": ["Ms-101"],
            "target_id": ["p-0001"],
            "variant_id": ["source_transcription_normalized.full"],
        },
    ]
    for query in cases:
        payload = source_target_payload_from_query(query)
        require_keys(payload, {"target"}, "source target payload")
        target = payload["target"]
        require(set(target) == SOURCE_TARGET_BUNDLE_KEYS, "source target bundle schema drift")
        unexpected_path_keys = sorted(FORBIDDEN_SOURCE_TARGET_KEYS & set(target))
        require(not unexpected_path_keys, "source target bundle exposes local path keys: " + ", ".join(unexpected_path_keys))
        require(target["schema_version"] == 1, "source target schema_version must be 1")
        require(target["record_type"] == "source_target_bundle", "source target record_type mismatch")
        require(target["corpus_id"] == query["corpus_id"][0], "source target corpus_id mismatch")
        require(target["work_id"] == query["work_id"][0], "source target work_id mismatch")
        require(target["target_id"] == query["target_id"][0], "source target target_id mismatch")
        if "expected_segment_type" in query:
            require(target["segment_type"] == query["expected_segment_type"][0], "source target segment_type mismatch")
        require(target["target_url"].startswith(f"/work/{target['corpus_id']}/"), "source target URL invalid")
        require("://" not in target["target_url"], "source target URL must be site-relative")
        require(target["source_text"].strip(), "source target source_text is empty")
        require(target["source_text_chars"] == len(target["source_text"]), "source target chars mismatch")
        require(
            target["source_text_sha256"] == sha256_text(target["source_text"]),
            "source target checksum mismatch",
        )

    try:
        source_target_payload_from_query({"corpus_id": ["nietzsche"], "work_id": ["GM"]})
    except ValueError:
        pass
    else:
        raise AssertionError("missing target_id should raise ValueError")

    try:
        source_target_payload_from_query({"corpus_id": ["nietzsche"], "work_id": ["GM"], "target_id": ["missing"]})
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing source target should raise FileNotFoundError")


def check_sentence_translation_export() -> None:
    markdown = sentence_translations_export_from_query(
        {"corpus_id": ["nietzsche"], "work_id": ["GM"], "format": ["markdown"]}
    )
    require(markdown["kind"] == "text", "sentence translations markdown export should be text")
    require("번역 목록" in markdown["body"], "sentence translations markdown export heading missing")
    require("번역 " in markdown["body"], "sentence translations markdown export count summary missing")
    require("Reviewed Gemma" not in markdown["body"], "sentence translations export should hide runtime-oriented title")
    require("Review:" not in markdown["body"], "sentence translations export should hide review-state metadata")
    require("Reviewed:" not in markdown["body"], "sentence translations export should hide reviewed timestamps")
    for noisy_text in ["Sentence Translations", " translations", "Translation", "Commentary", "Original", "Source:"]:
        require(noisy_text not in markdown["body"], f"sentence translations export should avoid English label {noisy_text!r}")
    payload = sentence_translations_export_from_query(
        {"corpus_id": ["nietzsche"], "work_id": ["GM"], "format": ["json"], "review_state": ["all"]}
    )
    require(payload["kind"] == "json", "sentence translations json export should be json")
    require_keys(payload["payload"], {"count", "records"}, "sentence translations export")
    summary = sentence_translations_summary_from_query({"corpus_id": ["nietzsche"], "work_id": ["GM"]})
    require_keys(
        summary,
        {
            "ok",
            "count",
            "review_state_counts",
            "sentence_state_count",
            "sentence_states",
            "latest_generated_at",
            "latest_reviewed_at",
        },
        "sentence translations summary",
    )
    require_keys(summary["review_state_counts"], {"generated", "reviewed", "rejected"}, "sentence translations review counts")
    require(isinstance(summary["sentence_states"], list), "sentence translations summary states should be a list")


def check_study_session_export() -> None:
    markdown = study_session_export_from_query(
        {"corpus_id": ["nietzsche"], "work_id": ["GM"], "format": ["markdown"]}
    )
    require(markdown["kind"] == "text", "study session markdown export should be text")
    require("학습 기록" in markdown["body"], "study session export heading missing")
    require("노트 " in markdown["body"] and " / 번역 " in markdown["body"], "study session export count summary should be reader-language")
    require("번역과 해설" in markdown["body"], "study session export translation section missing")
    for noisy_text in ["Study Bundle", " notes / ", "Translations And Commentary", "No matching notes.", "No matching translations."]:
        require(noisy_text not in markdown["body"], f"study session export should avoid English fallback text {noisy_text!r}")
    require("Review:" not in markdown["body"], "study session export should hide review-state metadata")
    require("AI output below" not in markdown["body"], "study session export should avoid log-like AI disclaimers")
    payload = study_session_export_from_query(
        {"corpus_id": ["nietzsche"], "work_id": ["GM"], "format": ["json"]}
    )
    require(payload["kind"] == "json", "study session json export should be json")
    require_keys(payload["payload"], {"note_count", "translation_count", "notes", "translations"}, "study session export")


def main() -> None:
    check_archive(build_archive())
    check_archive_summary(build_archive_summary())
    check_archive_title_search()
    check_archive_cache_contracts()
    check_health(build_runtime_health())
    check_artifacts(build_artifact_manifest())
    check_public_health(build_public_runtime_health())
    check_public_gemma_health(build_public_gemma_health())
    check_public_artifacts(build_public_artifact_manifest())
    check_ttl_cache_contracts()
    check_gemma_launcher_states()
    check_bible_segments_payload()
    check_source_target_payload()
    check_sentence_translation_export()
    check_study_session_export()
    print("api contracts ok")


if __name__ == "__main__":
    main()
