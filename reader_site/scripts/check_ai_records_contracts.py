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
from services.source_targets import sha256_text  # noqa: E402

HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REVIEW_STATES = {"generated", "reviewed", "rejected"}
ALLOWED_RECORD_TYPES = {"ai_interpretation", "ai_sentence_translation"}
ALLOWED_CRITIC_CATEGORIES = {
    "omission",
    "unsupported_addition",
    "semantic_substitution",
    "syntax_or_scope",
    "negation_or_modality",
    "ambiguity_resolution",
    "referent",
    "metaphor_or_rhetoric",
    "terminology",
    "register",
    "korean_readability",
}
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
SENTENCE_TRANSLATION_V3_FIELDS = [
    "source_context_sha256",
    "source_context_chars",
    "context_segments",
    "model_file_sha256",
    "generation_parameters",
    "response_schema_name",
    "translation_profile_id",
    "translation_policy_sha256",
]
SENTENCE_TRANSLATION_V4_FIELDS = ["request_contract_sha256"]
SENTENCE_TRANSLATION_V5_FIELDS = [
    "pipeline_contract_sha256",
    "quality_pipeline_version",
    "critic_prompt_template_id",
    "critic_prompt_template_sha256",
    "critic_generation_parameters",
    "critic_response_schema_name",
    "revision_prompt_template_id",
    "revision_prompt_template_sha256",
    "max_revision_count",
    "quality_state",
    "revision_count",
    "critic",
    "critic_prompt_sha256",
    "revision_prompt_sha256",
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


def validate_critic_result(value: Any, path: Path, line_number: int, field: str) -> None:
    require(isinstance(value, dict), context(path, line_number, f"{field} must be an object"))
    verdict = value.get("verdict")
    if verdict == "error":
        require(set(value) == {"verdict", "issues", "stage", "error"}, context(path, line_number, f"{field} error audit fields are invalid"))
        require(value["issues"] == [], context(path, line_number, f"{field} error audit must not claim issues"))
        require(value["stage"] in {"initial_critic", "revision", "final_critic"}, context(path, line_number, f"{field} error stage is invalid"))
        require(isinstance(value["error"], str) and value["error"].strip(), context(path, line_number, f"{field} error message is required"))
        return

    require(set(value) == {"verdict", "issues"}, context(path, line_number, f"{field} fields are invalid"))
    require(verdict in {"pass", "revise"}, context(path, line_number, f"{field} verdict is invalid"))
    issues = value["issues"]
    require(isinstance(issues, list), context(path, line_number, f"{field}.issues must be a list"))
    require((verdict == "pass" and not issues) or (verdict == "revise" and bool(issues)), context(path, line_number, f"{field} verdict and issues disagree"))
    issue_fields = {"source_span", "translation_span", "category", "severity", "explanation"}
    for issue_index, issue in enumerate(issues):
        issue_field = f"{field}.issues[{issue_index}]"
        require(isinstance(issue, dict) and set(issue) == issue_fields, context(path, line_number, f"{issue_field} fields are invalid"))
        require(issue["category"] in ALLOWED_CRITIC_CATEGORIES, context(path, line_number, f"{issue_field}.category is invalid"))
        require(issue["severity"] in {"minor", "major"}, context(path, line_number, f"{issue_field}.severity is invalid"))
        for text_field in issue_fields:
            require(isinstance(issue[text_field], str), context(path, line_number, f"{issue_field}.{text_field} must be a string"))
        require(issue["explanation"].strip(), context(path, line_number, f"{issue_field}.explanation is required"))


def validate_record(record: Any, path: Path, line_number: int) -> None:
    require(isinstance(record, dict), context(path, line_number, "record must be a JSON object"))
    for field in REQUIRED_FIELDS:
        require(field in record, context(path, line_number, f"missing required field {field}"))
    for field in REQUIRED_TEXT_FIELDS:
        require(isinstance(record[field], str) and record[field].strip(), context(path, line_number, f"{field} must be a non-empty string"))

    require(record["schema_version"] in {1, 2, 3, 4, 5}, context(path, line_number, "schema_version must be between 1 and 5"))
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

    human_fields = {
        "human_translation",
        "human_translation_updated_at",
        "human_translation_base_sha256",
    }
    present_human_fields = human_fields.intersection(record)
    if present_human_fields:
        require(present_human_fields == human_fields, context(path, line_number, "human translation audit fields must be complete"))
        require(
            isinstance(record["human_translation"], str) and record["human_translation"].strip(),
            context(path, line_number, "human_translation must be a non-empty string"),
        )
        require(record["review_state"] == "reviewed", context(path, line_number, "human translation must be reviewed"))
        require_iso_timestamp(record["human_translation_updated_at"], path, line_number, "human_translation_updated_at")
        require(
            HEX_SHA256.fullmatch(record["human_translation_base_sha256"]) is not None,
            context(path, line_number, "human_translation_base_sha256 must be a SHA-256 hex digest"),
        )

    if record["record_type"] == "ai_interpretation":
        require(isinstance(record.get("interpretation"), str) and record["interpretation"].strip(), context(path, line_number, "ai_interpretation record requires interpretation"))

    citation_hash = record["source_text_sha256"]
    if record["record_type"] == "ai_sentence_translation":
        for field in SENTENCE_TRANSLATION_FIELDS:
            require(field in record, context(path, line_number, f"missing required sentence translation field {field}"))
        if record["schema_version"] == 1:
            for field in LEGACY_SENTENCE_TRANSLATION_FIELDS:
                require(field in record, context(path, line_number, f"missing required legacy sentence translation field {field}"))
        if record["schema_version"] >= 3:
            for field in SENTENCE_TRANSLATION_V3_FIELDS:
                require(field in record, context(path, line_number, f"missing required sentence translation v3 field {field}"))
        if record["schema_version"] >= 4:
            for field in SENTENCE_TRANSLATION_V4_FIELDS:
                require(field in record, context(path, line_number, f"missing required sentence translation v4 field {field}"))
        if record["schema_version"] >= 5:
            for field in SENTENCE_TRANSLATION_V5_FIELDS:
                require(field in record, context(path, line_number, f"missing required sentence translation v5 field {field}"))
        for field in ("segment_id", "sentence_id", "sentence_text_sha256", "model_runtime"):
            require(isinstance(record[field], str) and record[field].strip(), context(path, line_number, f"{field} must be a non-empty string"))
        for field in ("translation", "commentary"):
            require(isinstance(record[field], str), context(path, line_number, f"{field} must be a string"))
        if present_human_fields:
            require(
                record["human_translation_base_sha256"] == sha256_text(record["translation"]),
                context(path, line_number, "human translation base hash must match the preserved model translation"),
            )
        if record["schema_version"] == 1:
            require(isinstance(record["literal_gloss"], str), context(path, line_number, "literal_gloss must be a string"))
        require(HEX_SHA256.fullmatch(record["sentence_text_sha256"]) is not None, context(path, line_number, "sentence_text_sha256 must be a SHA-256 hex digest"))
        require(record["target_id"] == record["sentence_id"], context(path, line_number, "target_id must match sentence_id"))
        require(record["sentence_id"].startswith(f"{record['segment_id']}.s"), context(path, line_number, "sentence_id must belong to segment_id"))
        if record["schema_version"] == 1:
            require(isinstance(record["key_terms"], list), context(path, line_number, "key_terms must be a list"))
        require(isinstance(record["cautions"], list), context(path, line_number, "cautions must be a list"))
        require(all(isinstance(item, str) and item.strip() for item in record["cautions"]), context(path, line_number, "cautions must contain non-empty strings"))
        if record["schema_version"] >= 3:
            require(HEX_SHA256.fullmatch(record["source_context_sha256"]) is not None, context(path, line_number, "source_context_sha256 must be a SHA-256 hex digest"))
            require(HEX_SHA256.fullmatch(record["translation_policy_sha256"]) is not None, context(path, line_number, "translation_policy_sha256 must be a SHA-256 hex digest"))
            require(isinstance(record["source_context_chars"], int) and 0 < record["source_context_chars"] <= 6000, context(path, line_number, "source_context_chars must be between 1 and 6000"))
            require(isinstance(record["context_segments"], list) and record["context_segments"], context(path, line_number, "context_segments must be a non-empty list"))
            for context_index, context_segment in enumerate(record["context_segments"]):
                require(isinstance(context_segment, dict), context(path, line_number, f"context_segments[{context_index}] must be an object"))
                require(isinstance(context_segment.get("segment_id"), str) and context_segment["segment_id"], context(path, line_number, f"context_segments[{context_index}].segment_id is required"))
                require(context_segment.get("position") in {"previous", "target", "next"}, context(path, line_number, f"context_segments[{context_index}].position is invalid"))
                require(HEX_SHA256.fullmatch(str(context_segment.get("source_text_sha256", ""))) is not None, context(path, line_number, f"context_segments[{context_index}].source_text_sha256 is invalid"))
            require(isinstance(record["model_file_sha256"], str), context(path, line_number, "model_file_sha256 must be a string"))
            require(not record["model_file_sha256"] or HEX_SHA256.fullmatch(record["model_file_sha256"]) is not None, context(path, line_number, "model_file_sha256 must be empty or a SHA-256 hex digest"))
            parameters = record["generation_parameters"]
            require(isinstance(parameters, dict), context(path, line_number, "generation_parameters must be an object"))
            require(parameters.get("temperature") == record["temperature"], context(path, line_number, "generation temperature mismatch"))
            require(isinstance(parameters.get("top_p"), int | float), context(path, line_number, "generation top_p must be numeric"))
            require(isinstance(parameters.get("max_tokens"), int) and parameters["max_tokens"] > 0, context(path, line_number, "generation max_tokens must be positive"))
            require(isinstance(parameters.get("seed"), int), context(path, line_number, "generation seed must be an integer"))
            require(record["response_schema_name"] == "sentence_translation_response", context(path, line_number, "response_schema_name is invalid"))
            require(isinstance(record["translation_profile_id"], str), context(path, line_number, "translation_profile_id must be a string"))
        if record["schema_version"] >= 4:
            require(HEX_SHA256.fullmatch(record["request_contract_sha256"]) is not None, context(path, line_number, "request_contract_sha256 must be a SHA-256 hex digest"))
        if record["schema_version"] >= 5:
            require("interpretation" not in record, context(path, line_number, "sentence translation v5 must not duplicate commentary as interpretation"))
            for field in ("pipeline_contract_sha256", "critic_prompt_template_sha256", "revision_prompt_template_sha256"):
                require(HEX_SHA256.fullmatch(str(record[field])) is not None, context(path, line_number, f"{field} must be a SHA-256 hex digest"))
            require(record["quality_pipeline_version"] in {1, 2}, context(path, line_number, "quality_pipeline_version must be 1 or 2"))
            if record["quality_pipeline_version"] == 2:
                require(record["prompt_template_id"] == "sentence_translation_study_v4", context(path, line_number, "pipeline v2 translator prompt is invalid"))
                require(record["critic_prompt_template_id"] == "sentence_translation_critic_v2", context(path, line_number, "pipeline v2 critic prompt is invalid"))
                require(record["revision_prompt_template_id"] == "sentence_translation_revision_v2", context(path, line_number, "pipeline v2 revision prompt is invalid"))
            require(record["critic_prompt_template_id"] in KNOWN_PROMPT_TEMPLATE_IDS, context(path, line_number, "critic prompt template is unknown"))
            require(record["revision_prompt_template_id"] in KNOWN_PROMPT_TEMPLATE_IDS, context(path, line_number, "revision prompt template is unknown"))
            require(record["critic_response_schema_name"] == "sentence_translation_critic_response", context(path, line_number, "critic_response_schema_name is invalid"))
            require(record["quality_state"] in {"critic_pass", "critic_pass_after_revision", "needs_human_review", "critic_error"}, context(path, line_number, "quality_state is invalid"))
            require(record["max_revision_count"] == 1, context(path, line_number, "max_revision_count must be 1"))
            require(record["revision_count"] in {0, 1}, context(path, line_number, "revision_count must be 0 or 1"))
            critic_parameters = record["critic_generation_parameters"]
            require(isinstance(critic_parameters, dict), context(path, line_number, "critic_generation_parameters must be an object"))
            require(critic_parameters.get("temperature") == 0.0, context(path, line_number, "critic temperature must be 0.0"))
            require(isinstance(critic_parameters.get("max_tokens"), int) and critic_parameters["max_tokens"] > 0, context(path, line_number, "critic max_tokens must be positive"))
            critic = record["critic"]
            require(isinstance(critic, dict) and set(critic) == {"initial", "final"}, context(path, line_number, "critic audit must contain initial and final"))
            validate_critic_result(critic["initial"], path, line_number, "critic.initial")
            if critic["final"] is not None:
                validate_critic_result(critic["final"], path, line_number, "critic.final")
            critic_hashes = record["critic_prompt_sha256"]
            require(isinstance(critic_hashes, dict) and set(critic_hashes) == {"initial", "final"}, context(path, line_number, "critic_prompt_sha256 must contain initial and final"))
            require(HEX_SHA256.fullmatch(str(critic_hashes["initial"])) is not None, context(path, line_number, "initial critic prompt hash is invalid"))
            require(not critic_hashes["final"] or HEX_SHA256.fullmatch(str(critic_hashes["final"])) is not None, context(path, line_number, "final critic prompt hash is invalid"))
            require(not record["revision_prompt_sha256"] or HEX_SHA256.fullmatch(str(record["revision_prompt_sha256"])) is not None, context(path, line_number, "revision prompt hash is invalid"))

            initial_verdict = critic["initial"]["verdict"]
            final_verdict = critic["final"]["verdict"] if critic["final"] is not None else None
            if initial_verdict == "pass":
                require(record["quality_state"] == "critic_pass", context(path, line_number, "initial critic pass must map to critic_pass"))
                require(record["revision_count"] == 0 and critic["final"] is None, context(path, line_number, "passing draft must not have a revision or final critic"))
                require(not record["revision_prompt_sha256"] and not critic_hashes["final"], context(path, line_number, "passing draft must not have revision-stage hashes"))
            elif initial_verdict == "error":
                require(record["quality_state"] == "critic_error", context(path, line_number, "initial critic error must map to critic_error"))
                require(record["revision_count"] == 0 and critic["final"] is None, context(path, line_number, "initial critic error must stop the pipeline"))
            else:
                initial_has_major = any(issue["severity"] == "major" for issue in critic["initial"]["issues"])
                if not initial_has_major:
                    require(record["quality_state"] == "needs_human_review", context(path, line_number, "minor-only critic issues must require human review"))
                    require(record["revision_count"] == 0 and critic["final"] is None, context(path, line_number, "minor-only issues must not trigger a revision"))
                elif final_verdict is None:
                    require(False, context(path, line_number, "major critic issues require a revision-stage audit"))
                elif final_verdict == "error":
                    require(record["quality_state"] == "critic_error", context(path, line_number, "revision-stage error must map to critic_error"))
                    expected_revision_count = 0 if critic["final"]["stage"] == "revision" else 1
                    require(record["revision_count"] == expected_revision_count, context(path, line_number, "critic error revision count is inconsistent"))
                else:
                    require(record["revision_count"] == 1, context(path, line_number, "completed revision must have revision_count 1"))
                    expected_quality = "critic_pass_after_revision" if final_verdict == "pass" else "needs_human_review"
                    require(record["quality_state"] == expected_quality, context(path, line_number, "final critic verdict and quality_state disagree"))
                require(bool(record["revision_prompt_sha256"]), context(path, line_number, "major issue path must record the revision prompt hash"))
        citation_hash = record["source_text_sha256"] if record["schema_version"] >= 5 else record["sentence_text_sha256"]

    citations = record["citations"]
    require(isinstance(citations, list), context(path, line_number, "citations must be a list"))
    require(citations, context(path, line_number, "citations must include at least one source citation"))
    for index, citation in enumerate(citations):
        validate_citation(citation, path, line_number, index, citation_hash)
        if record["record_type"] == "ai_sentence_translation" and record["schema_version"] >= 5:
            require(citation.get("sentence_text_sha256") == record["sentence_text_sha256"], context(path, line_number, f"citations[{index}].sentence_text_sha256 mismatch"))
            require(citation.get("source_context_sha256") == record["source_context_sha256"], context(path, line_number, f"citations[{index}].source_context_sha256 mismatch"))


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
