from __future__ import annotations

from typing import Any

from sentence_units import sentence_units
from services.source_targets import resolve_segment_target, sha256_text


def resolve_sentence_target(
    corpus_id: str,
    work_id: str,
    segment_id: str,
    sentence_id: str,
    variant_id: str = "",
) -> dict[str, Any]:
    if not sentence_id.startswith(f"{segment_id}.s"):
        raise ValueError("sentence_id must belong to segment_id")

    segment = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
    source_text = str(segment["text_raw"])
    for unit in sentence_units(segment_id, source_text):
        if unit["sentence_id"] != sentence_id:
            continue
        sentence_text = str(unit["text_raw"])
        target_url = str(segment["url"]).split("#", 1)[0] + f"#{sentence_id}"
        return {
            "corpus_id": corpus_id,
            "work_id": work_id,
            "variant_id": segment.get("variant_id", ""),
            "segment_id": segment_id,
            "sentence_id": sentence_id,
            "target_id": sentence_id,
            "target_url": target_url,
            "segment_type": segment.get("segment_type", ""),
            "label": f"{segment.get('label', segment_id)} / {unit['label']}",
            "source_text": source_text,
            "sentence_text": sentence_text,
            "source_text_preview": segment.get("text_preview", source_text[:220]),
            "source_text_chars": len(source_text),
            "sentence_text_chars": len(sentence_text),
            "source_text_sha256": sha256_text(source_text),
            "sentence_text_sha256": sha256_text(sentence_text),
        }

    raise FileNotFoundError(f"sentence target not found: {corpus_id}/{work_id}/{variant_id}/{sentence_id}")


def sentence_target_bundle(
    corpus_id: str,
    work_id: str,
    segment_id: str,
    sentence_id: str,
    variant_id: str = "",
) -> dict[str, Any]:
    target = resolve_sentence_target(corpus_id, work_id, segment_id, sentence_id, variant_id)
    return {
        "schema_version": 1,
        "record_type": "sentence_target_bundle",
        **target,
    }
