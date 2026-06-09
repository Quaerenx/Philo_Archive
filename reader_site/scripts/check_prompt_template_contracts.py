from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.interpretation_prompts import (  # noqa: E402
    DEFAULT_PROMPT_TEMPLATE_ID,
    build_interpretation_prompt_bundle_from_source,
    iter_prompt_templates,
)
from services.source_targets import sha256_text, source_target_bundle  # noqa: E402


CASES = [
    ("nietzsche", "GM", "p-0023", ""),
    ("bible", "sblgnt.John", "John.3.16", ""),
    ("bible", "oshb.Gen", "Gen.1.1", ""),
    ("kierkegaard", "ba", "sks-0001", "text"),
    ("wittgenstein", "Ms-101", "p-0001", "source_transcription_normalized.full"),
]

FORBIDDEN_LOCAL_KEY_NEEDLES = [
    "absolute_path",
    "filesystem_path",
    "local_path",
    "source_path",
    "source_root",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_source_bundle() -> dict[str, Any]:
    source_text = "Synthetic source text for source-light prompt validation.\nSecond line."
    return {
        "schema_version": 1,
        "record_type": "source_target_bundle",
        "corpus_id": "synthetic",
        "work_id": "demo",
        "variant_id": "",
        "target_id": "p-0001",
        "target_url": "/work/synthetic/demo#p-0001",
        "segment_type": "paragraph",
        "label": "Synthetic / Paragraph 1",
        "source_text": source_text,
        "source_text_preview": source_text,
        "source_text_chars": len(source_text),
        "source_text_sha256": sha256_text(source_text),
    }


def check_bundle(bundle: dict[str, Any], source_text: str) -> None:
    prompt = bundle.get("prompt")
    require(isinstance(prompt, str) and prompt.strip(), "prompt bundle missing prompt")
    require(bundle.get("record_type") == "interpretation_prompt_bundle", "invalid prompt bundle record_type")
    require(bundle.get("prompt_template_id") == DEFAULT_PROMPT_TEMPLATE_ID, "unexpected prompt_template_id")
    require(bundle.get("prompt_sha256") == sha256_text(prompt), "prompt_sha256 mismatch")
    require(bundle.get("source_text_sha256") == sha256_text(source_text), "source_text_sha256 mismatch")
    require(source_text in prompt, "prompt does not include exact source text")
    for phrase in [
        "Generated interpretation",
        "Original source",
        "source_text_sha256",
        "target_url",
    ]:
        require(phrase in prompt, f"prompt missing required phrase {phrase!r}")
    serialized = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
    for needle in FORBIDDEN_LOCAL_KEY_NEEDLES:
        require(needle not in serialized, f"prompt bundle contains local key {needle}")


def check_template_records() -> None:
    templates = iter_prompt_templates()
    ids = [record["prompt_template_id"] for record in templates]
    require(DEFAULT_PROMPT_TEMPLATE_ID in ids, f"missing default prompt template {DEFAULT_PROMPT_TEMPLATE_ID}")
    require(len(ids) == len(set(ids)), "duplicate prompt_template_id values")
    for record in templates:
        text = record["template"]
        for phrase in [
            "Do not replace",
            "Do not use filesystem paths",
            "Original source",
            "Generated interpretation",
            "source_text_sha256",
        ]:
            require(phrase in text, f"{record['prompt_template_id']} missing prompt safety phrase {phrase!r}")


def check_source_light_render() -> None:
    source_bundle = synthetic_source_bundle()
    first = build_interpretation_prompt_bundle_from_source(source_bundle)
    second = build_interpretation_prompt_bundle_from_source(source_bundle)
    require(first == second, "prompt bundle render is not deterministic")
    check_bundle(first, source_bundle["source_text"])


def check_restored_source_targets() -> None:
    for corpus_id, work_id, target_id, variant_id in CASES:
        source_bundle = source_target_bundle(corpus_id, work_id, target_id, variant_id)
        bundle = build_interpretation_prompt_bundle_from_source(source_bundle)
        check_bundle(bundle, source_bundle["source_text"])
        require(bundle["target_url"].startswith(f"/work/{corpus_id}/"), f"{corpus_id}: invalid target URL")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate deterministic AI prompt template contracts.", allow_abbrev=False)
    parser.add_argument(
        "--with-source-targets",
        action="store_true",
        help="Also render prompts from restored generated segment artifacts.",
    )
    args = parser.parse_args()

    check_template_records()
    check_source_light_render()
    if args.with_source_targets:
        check_restored_source_targets()
    print("prompt template contracts ok")


if __name__ == "__main__":
    main()
