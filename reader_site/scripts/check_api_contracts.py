from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora.archive import build_archive  # noqa: E402
from corpora.catalogs import bible_segments_payload_from_query  # noqa: E402
from runtime_status import build_artifact_manifest, build_runtime_health  # noqa: E402
from services.source_targets import sha256_text, source_target_payload_from_query  # noqa: E402


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
                require_keys(link, {"label", "href", "source_href", "path", "meta"}, link_context)


def check_health(payload: dict[str, Any]) -> None:
    require_keys(
        payload,
        {"status", "generated_at", "site_root", "corpus_root", "corpora", "search", "issues", "next_recommended_upgrades"},
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
    for index, artifact in enumerate(payload["artifacts"]):
        check_file_record(artifact, f"artifacts.artifacts[{index}]")
    check_file_record(payload["search"], "artifacts.search")


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
        require_keys(
            target,
            {
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
            },
            "source target",
        )
        require(target["schema_version"] == 1, "source target schema_version must be 1")
        require(target["record_type"] == "source_target_bundle", "source target record_type mismatch")
        require(target["corpus_id"] == query["corpus_id"][0], "source target corpus_id mismatch")
        require(target["work_id"] == query["work_id"][0], "source target work_id mismatch")
        require(target["target_id"] == query["target_id"][0], "source target target_id mismatch")
        if "expected_segment_type" in query:
            require(target["segment_type"] == query["expected_segment_type"][0], "source target segment_type mismatch")
        require(target["target_url"].startswith(f"/work/{target['corpus_id']}/"), "source target URL invalid")
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


def main() -> None:
    check_archive(build_archive())
    check_health(build_runtime_health())
    check_artifacts(build_artifact_manifest())
    check_bible_segments_payload()
    check_source_target_payload()
    print("api contracts ok")


if __name__ == "__main__":
    main()
