from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
AI_DIR = SITE / "data" / "ai"
sys.path.insert(0, str(SITE))

from services.interpretation_prompts import prompt_template_ids  # noqa: E402

HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REVIEW_STATES = {"generated", "reviewed", "rejected"}
ALLOWED_RECORD_TYPES = {"ai_interpretation", "ai_sentence_translation"}
KNOWN_PROMPT_TEMPLATE_IDS = prompt_template_ids()
REQUIRED_FIELDS = [
    "schema_version",
    "record_type",
    "id",
    "created_at",
    "generated_at",
    "corpus_id",
    "work_id",
    "variant_id",
    "target_id",
    "target_url",
    "source_text_sha256",
    "source_text_excerpt",
    "source_language",
    "model_provider",
    "model_name",
    "model_version",
    "prompt_template_id",
    "prompt_sha256",
    "temperature",
    "interpretation",
    "citations",
    "review_state",
]
SENTENCE_TRANSLATION_FIELDS = [
    "segment_id",
    "sentence_id",
    "sentence_text_sha256",
    "model_runtime",
    "translation",
    "commentary",
    "cautions",
]
LEGACY_SENTENCE_TRANSLATION_FIELDS = [
    "literal_gloss",
    "key_terms",
]
REQUIRED_TEXT_FIELDS = [
    "id",
    "created_at",
    "generated_at",
    "corpus_id",
    "work_id",
    "target_id",
    "target_url",
    "source_text_sha256",
    "source_text_excerpt",
    "source_language",
    "model_provider",
    "model_name",
    "model_version",
    "prompt_template_id",
    "prompt_sha256",
    "interpretation",
    "review_state",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def context(path: Path, line_number: int, message: str) -> str:
    return f"{path}:{line_number}: {message}"


def require_iso_timestamp(value: str, path: Path, line_number: int, field: str) -> None:
    candidate = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AssertionError(context(path, line_number, f"{field} is not an ISO timestamp")) from exc


def validate_citation(citation: Any, path: Path, line_number: int, index: int, parent_hash: str) -> None:
    require(isinstance(citation, dict), context(path, line_number, f"citations[{index}] must be an object"))
    for field in ("target_url", "label", "source_text_sha256"):
        require(isinstance(citation.get(field), str) and citation[field].strip(), context(path, line_number, f"citations[{index}].{field} is required"))
    require(
        HEX_SHA256.fullmatch(citation["source_text_sha256"]) is not None,
        context(path, line_number, f"citations[{index}].source_text_sha256 must be a SHA-256 hex digest"),
    )
    require(
        citation["source_text_sha256"] == parent_hash,
        context(path, line_number, f"citations[{index}].source_text_sha256 must match expected source hash"),
    )
    require(citation["target_url"].startswith("/work/"), context(path, line_number, f"citations[{index}].target_url must point at a work route"))


def validate_record(record: Any, path: Path, line_number: int) -> None:
    require(isinstance(record, dict), context(path, line_number, "record must be a JSON object"))
    for field in REQUIRED_FIELDS:
        require(field in record, context(path, line_number, f"missing required field {field}"))
    for field in REQUIRED_TEXT_FIELDS:
        require(isinstance(record[field], str) and record[field].strip(), context(path, line_number, f"{field} must be a non-empty string"))

    require(record["schema_version"] in {1, 2}, context(path, line_number, "schema_version must be 1 or 2"))
    require(record["record_type"] in ALLOWED_RECORD_TYPES, context(path, line_number, "record_type is invalid"))
    require(record["review_state"] in ALLOWED_REVIEW_STATES, context(path, line_number, "review_state is invalid"))
    require(isinstance(record.get("variant_id"), str), context(path, line_number, "variant_id must be a string"))
    require(isinstance(record["temperature"], int | float), context(path, line_number, "temperature must be numeric"))
    require(record["target_url"].startswith("/work/"), context(path, line_number, "target_url must point at a work route"))
    require(
        f"/{record['corpus_id']}/{record['work_id']}" in record["target_url"],
        context(path, line_number, "target_url must include corpus_id and work_id"),
    )
    require(HEX_SHA256.fullmatch(record["source_text_sha256"]) is not None, context(path, line_number, "source_text_sha256 must be a SHA-256 hex digest"))
    require(HEX_SHA256.fullmatch(record["prompt_sha256"]) is not None, context(path, line_number, "prompt_sha256 must be a SHA-256 hex digest"))
    require(record["prompt_template_id"] in KNOWN_PROMPT_TEMPLATE_IDS, context(path, line_number, "prompt_template_id must reference a tracked prompt template"))
    require_iso_timestamp(record["created_at"], path, line_number, "created_at")
    require_iso_timestamp(record["generated_at"], path, line_number, "generated_at")

    citation_hash = record["source_text_sha256"]
    if record["record_type"] == "ai_sentence_translation":
        for field in SENTENCE_TRANSLATION_FIELDS:
            require(field in record, context(path, line_number, f"missing required sentence translation field {field}"))
        if record["schema_version"] == 1:
            for field in LEGACY_SENTENCE_TRANSLATION_FIELDS:
                require(field in record, context(path, line_number, f"missing required legacy sentence translation field {field}"))
        for field in ("segment_id", "sentence_id", "sentence_text_sha256", "model_runtime"):
            require(isinstance(record[field], str) and record[field].strip(), context(path, line_number, f"{field} must be a non-empty string"))
        for field in ("translation", "commentary"):
            require(isinstance(record[field], str), context(path, line_number, f"{field} must be a string"))
        if record["schema_version"] == 1:
            require(isinstance(record["literal_gloss"], str), context(path, line_number, "literal_gloss must be a string"))
        require(HEX_SHA256.fullmatch(record["sentence_text_sha256"]) is not None, context(path, line_number, "sentence_text_sha256 must be a SHA-256 hex digest"))
        require(record["target_id"] == record["sentence_id"], context(path, line_number, "target_id must match sentence_id"))
        require(record["sentence_id"].startswith(f"{record['segment_id']}.s"), context(path, line_number, "sentence_id must belong to segment_id"))
        if record["schema_version"] == 1:
            require(isinstance(record["key_terms"], list), context(path, line_number, "key_terms must be a list"))
        require(isinstance(record["cautions"], list), context(path, line_number, "cautions must be a list"))
        citation_hash = record["sentence_text_sha256"]

    citations = record["citations"]
    require(isinstance(citations, list), context(path, line_number, "citations must be a list"))
    require(citations, context(path, line_number, "citations must include at least one source citation"))
    for index, citation in enumerate(citations):
        validate_citation(citation, path, line_number, index, citation_hash)


def iter_record_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    require(path.exists(), f"missing AI records path: {path}")
    return sorted(candidate for candidate in path.glob("*.jsonl") if candidate.is_file())


def validate_file(path: Path) -> int:
    count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(context(path, line_number, "invalid JSONL record")) from exc
        validate_record(record, path, line_number)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local AI interpretation JSONL records.", allow_abbrev=False)
    parser.add_argument("--path", type=Path, default=AI_DIR, help="AI JSONL file or directory. Defaults to data/ai.")
    args = parser.parse_args()

    files = iter_record_files(args.path)
    total = sum(validate_file(path) for path in files)
    print(f"ai records contracts ok ({len(files)} files, {total} records)")


if __name__ == "__main__":
    main()
