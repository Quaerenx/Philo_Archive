from __future__ import annotations

import hashlib
from typing import Any

from services.segment_offsets import SEGMENT_FILES, resolve_indexed_segment_record



def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def resolve_segment_target(corpus_id: str, work_id: str, segment_id: str, variant_id: str = "") -> dict[str, Any]:
    record = resolve_indexed_segment_record(corpus_id, work_id, segment_id, variant_id)
    record_variant_id = str(record.get("variant_id", ""))
    text_raw = str(record.get("text_raw", ""))
    if not text_raw:
        raise ValueError("segment target has no text_raw")
    return {
        "corpus_id": corpus_id,
        "work_id": work_id,
        "variant_id": record_variant_id,
        "segment_id": segment_id,
        "segment_type": record.get("segment_type", ""),
        "label": record.get("label", segment_id),
        "title": record.get("title", work_id),
        "url": record.get("url", f"/work/{corpus_id}/{work_id}#{segment_id}"),
        "text_raw": text_raw,
        "text_preview": record.get("text_preview", text_raw[:220]),
        "source_text_sha256": sha256_text(text_raw),
    }


def source_target_bundle(corpus_id: str, work_id: str, segment_id: str, variant_id: str = "") -> dict[str, Any]:
    target = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
    source_text = str(target["text_raw"])
    return {
        "schema_version": 1,
        "record_type": "source_target_bundle",
        "corpus_id": target["corpus_id"],
        "work_id": target["work_id"],
        "variant_id": target["variant_id"],
        "target_id": target["segment_id"],
        "target_url": target["url"],
        "segment_type": target["segment_type"],
        "label": target["label"],
        "source_text": source_text,
        "source_text_preview": target["text_preview"],
        "source_text_chars": len(source_text),
        "source_text_sha256": target["source_text_sha256"],
    }


def source_target_payload_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    corpus_id = first_query_value(query, "corpus_id")
    work_id = first_query_value(query, "work_id")
    target_id = first_query_value(query, "target_id") or first_query_value(query, "segment_id")
    variant_id = first_query_value(query, "variant_id")
    if not corpus_id or not work_id or not target_id:
        raise ValueError("missing required source target fields")
    return {"target": source_target_bundle(corpus_id, work_id, target_id, variant_id)}
