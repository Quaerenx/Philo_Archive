from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

from services.source_targets import sha256_text, source_target_bundle


SITE = Path(__file__).resolve().parents[1]
PROMPT_TEMPLATE_FILE = SITE / "data" / "ai_prompt_templates.json"
DEFAULT_PROMPT_TEMPLATE_ID = "segment_interpretation_v1"
PROMPT_BUNDLE_SCHEMA_VERSION = 1

FORBIDDEN_LOCAL_KEYS = {
    "absolute_path",
    "filesystem_path",
    "local_path",
    "path",
    "source_path",
    "source_root",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prompt_template_payload(path: Path = PROMPT_TEMPLATE_FILE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "prompt template payload must be an object")
    require(payload.get("schema_version") == 1, "prompt template schema_version must be 1")
    templates = payload.get("templates")
    require(isinstance(templates, list) and templates, "prompt template payload must include templates")
    return payload


def placeholder_names(template_text: str) -> set[str]:
    names: set[str] = set()
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(template_text):
        if not field_name:
            continue
        require("." not in field_name and "[" not in field_name, f"unsupported placeholder syntax: {field_name}")
        names.add(field_name)
    return names


def iter_prompt_templates(path: Path = PROMPT_TEMPLATE_FILE) -> list[dict[str, Any]]:
    payload = prompt_template_payload(path)
    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload["templates"]):
        require(isinstance(record, dict), f"template {index} must be an object")
        require(record.get("record_type") == "ai_prompt_template", f"template {index} has invalid record_type")
        template_id = record.get("prompt_template_id")
        require(isinstance(template_id, str) and template_id.strip(), f"template {index} missing prompt_template_id")
        template_text = record.get("template")
        require(isinstance(template_text, str) and template_text.strip(), f"template {template_id} missing template text")
        required = record.get("required_placeholders")
        require(isinstance(required, list) and required, f"template {template_id} missing required_placeholders")
        require(all(isinstance(item, str) and item for item in required), f"template {template_id} has invalid placeholders")
        actual = placeholder_names(template_text)
        expected = set(required)
        require(actual == expected, f"template {template_id} placeholder mismatch")
        temperature = record.get("default_temperature")
        require(isinstance(temperature, int | float), f"template {template_id} missing numeric default_temperature")
        records.append(record)
    return records


def prompt_template_ids(path: Path = PROMPT_TEMPLATE_FILE) -> set[str]:
    return {str(record["prompt_template_id"]) for record in iter_prompt_templates(path)}


def load_prompt_template(template_id: str = DEFAULT_PROMPT_TEMPLATE_ID, path: Path = PROMPT_TEMPLATE_FILE) -> dict[str, Any]:
    for record in iter_prompt_templates(path):
        if record["prompt_template_id"] == template_id:
            return record
    raise KeyError(f"unknown prompt_template_id: {template_id}")


def public_source_target_fields(source_bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": source_bundle.get("schema_version"),
        "record_type": source_bundle.get("record_type"),
        "corpus_id": source_bundle.get("corpus_id"),
        "work_id": source_bundle.get("work_id"),
        "variant_id": source_bundle.get("variant_id", ""),
        "target_id": source_bundle.get("target_id"),
        "target_url": source_bundle.get("target_url"),
        "segment_type": source_bundle.get("segment_type"),
        "label": source_bundle.get("label"),
        "source_text_preview": source_bundle.get("source_text_preview"),
        "source_text_chars": source_bundle.get("source_text_chars"),
        "source_text_sha256": source_bundle.get("source_text_sha256"),
    }


def render_prompt(template_record: dict[str, Any], source_bundle: dict[str, Any]) -> str:
    source_text = str(source_bundle.get("source_text", ""))
    require(source_text.strip(), "source bundle must include source_text")
    values = {
        "prompt_template_id": template_record["prompt_template_id"],
        "corpus_id": source_bundle.get("corpus_id", ""),
        "work_id": source_bundle.get("work_id", ""),
        "variant_id": source_bundle.get("variant_id", ""),
        "target_id": source_bundle.get("target_id", ""),
        "target_url": source_bundle.get("target_url", ""),
        "label": source_bundle.get("label", ""),
        "source_text_sha256": source_bundle.get("source_text_sha256", ""),
        "source_text_chars": source_bundle.get("source_text_chars", len(source_text)),
        "source_text": source_text,
    }
    missing = [key for key, value in values.items() if value is None or (value == "" and key != "variant_id")]
    require(not missing, "source bundle missing prompt values: " + ", ".join(sorted(missing)))
    require(values["source_text_sha256"] == sha256_text(source_text), "source_text_sha256 does not match source_text")
    return str(template_record["template"]).format(**values)


def build_interpretation_prompt_bundle_from_source(
    source_bundle: dict[str, Any],
    prompt_template_id: str = DEFAULT_PROMPT_TEMPLATE_ID,
) -> dict[str, Any]:
    template_record = load_prompt_template(prompt_template_id)
    prompt = render_prompt(template_record, source_bundle)
    source_fields = public_source_target_fields(source_bundle)
    bundle = {
        "schema_version": PROMPT_BUNDLE_SCHEMA_VERSION,
        "record_type": "interpretation_prompt_bundle",
        "prompt_template_id": template_record["prompt_template_id"],
        "prompt_sha256": sha256_text(prompt),
        "temperature": template_record["default_temperature"],
        "target_url": source_fields["target_url"],
        "target": source_fields,
        "source_text_sha256": source_fields["source_text_sha256"],
        "source_text_chars": source_fields["source_text_chars"],
        "prompt": prompt,
    }
    forbidden = sorted(key for key in bundle if key in FORBIDDEN_LOCAL_KEYS)
    require(not forbidden, "prompt bundle contains local path fields: " + ", ".join(forbidden))
    return bundle


def build_interpretation_prompt_bundle(
    corpus_id: str,
    work_id: str,
    target_id: str,
    variant_id: str = "",
    prompt_template_id: str = DEFAULT_PROMPT_TEMPLATE_ID,
) -> dict[str, Any]:
    source_bundle = source_target_bundle(corpus_id, work_id, target_id, variant_id)
    return build_interpretation_prompt_bundle_from_source(source_bundle, prompt_template_id)
