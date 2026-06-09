from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"

SEGMENT_FILES = {
    "nietzsche": DATA / "nietzsche_segments.jsonl",
    "bible": DATA / "bible_segments.jsonl",
    "kierkegaard": DATA / "kierkegaard_segments.jsonl",
    "wittgenstein": DATA / "wittgenstein_segments.jsonl",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def segment_records(corpus_id: str) -> list[dict[str, Any]]:
    path = SEGMENT_FILES.get(corpus_id)
    if path is None:
        raise ValueError(f"unknown corpus_id: {corpus_id}")
    if not path.exists():
        raise FileNotFoundError(f"missing segment file for {corpus_id}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
    return records


def resolve_segment_target(corpus_id: str, work_id: str, segment_id: str, variant_id: str = "") -> dict[str, Any]:
    for record in segment_records(corpus_id):
        if record.get("work_id") != work_id:
            continue
        if record.get("segment_id") != segment_id:
            continue
        record_variant_id = str(record.get("variant_id", ""))
        if variant_id and record_variant_id != variant_id:
            continue
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
            "url": record.get("url", f"/work/{corpus_id}/{work_id}#{segment_id}"),
            "text_raw": text_raw,
            "text_preview": record.get("text_preview", text_raw[:220]),
            "source_text_sha256": sha256_text(text_raw),
        }
    raise FileNotFoundError(f"segment target not found: {corpus_id}/{work_id}/{variant_id}/{segment_id}")


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
