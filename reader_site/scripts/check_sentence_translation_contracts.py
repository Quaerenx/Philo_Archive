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
from services.sentence_translations import (  # noqa: E402
    PROMPT_TEMPLATE_ID,
    build_record,
    build_sentence_prompt_bundle,
    normalized_model_output,
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
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "ai_sentence_translation.jsonl"
        path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        require(validate_file(path) == 1, "sentence translation record validator failed")


def check_restored_source_target() -> None:
    target = sentence_target_bundle("nietzsche", "GM", "p-0023", "p-0023.s001", "")
    require(target["sentence_id"] == "p-0023.s001", "restored sentence target id mismatch")
    check_prompt_and_record(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate on-demand sentence translation contracts.", allow_abbrev=False)
    parser.add_argument("--with-source-targets", action="store_true")
    args = parser.parse_args()

    check_sentence_units()
    check_prompt_and_record(synthetic_sentence_target())
    if args.with_source_targets:
        check_restored_source_target()
    print("sentence translation contracts ok")


if __name__ == "__main__":
    main()
