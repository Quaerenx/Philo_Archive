from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path
from typing import Any

from sentence_units import render_sentence_spans
from services.segment_offsets import (
    SEGMENT_FILES,
    SEGMENT_OFFSET_INDEX,
    indexed_work_segment_locations,
    read_indexed_segment_records,
)


VIRTUAL_WORK_MIN_SEGMENTS = 2000
VIRTUAL_WORK_MIN_TEXT_CHARS = 2 * 1024 * 1024
WORK_CHUNK_TARGET_SENTENCES = 360
WORK_CHUNK_MAX_SEGMENTS = 32
WORK_CHUNK_CACHE_SIZE = 16


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def _artifact_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _manifest_cache_key(corpus_id: str, work_id: str, variant_id: str) -> tuple[Any, ...]:
    source_path = SEGMENT_FILES.get(corpus_id)
    if source_path is None:
        raise ValueError(f"unknown corpus_id: {corpus_id}")
    return (
        corpus_id,
        work_id,
        variant_id,
        *_artifact_signature(SEGMENT_OFFSET_INDEX),
        *_artifact_signature(source_path),
    )


@lru_cache(maxsize=WORK_CHUNK_CACHE_SIZE)
def _cached_work_chunk_manifest(cache_key: tuple[Any, ...]) -> dict[str, Any]:
    corpus_id, work_id, variant_id = (str(cache_key[0]), str(cache_key[1]), str(cache_key[2]))
    locations = indexed_work_segment_locations(corpus_id, work_id, variant_id)
    chunks: list[dict[str, Any]] = []
    current_locations: list[dict[str, Any]] = []
    current_sentences = 0
    current_text_chars = 0
    total_sentences = 0
    total_text_chars = 0

    def flush_chunk() -> None:
        nonlocal current_locations, current_sentences, current_text_chars
        if not current_locations:
            return
        chunk_index = len(chunks)
        first_location = current_locations[0]
        last_location = current_locations[-1]
        chunks.append(
            {
                "index": chunk_index,
                "first_segment_id": str(first_location["segment_id"]),
                "last_segment_id": str(last_location["segment_id"]),
                "segment_count": len(current_locations),
                "sentence_start": int(first_location["sentence_start"]),
                "sentence_count": current_sentences,
                "text_chars": current_text_chars,
                "locations": tuple(current_locations),
            }
        )
        current_locations = []
        current_sentences = 0
        current_text_chars = 0

    for work_segment_index, original_location in enumerate(locations):
        location = dict(original_location)
        sentence_count = max(1, int(location["sentence_count"]))
        text_chars = max(0, int(location["text_chars"]))
        if current_locations and (
            len(current_locations) >= WORK_CHUNK_MAX_SEGMENTS
            or current_sentences + sentence_count > WORK_CHUNK_TARGET_SENTENCES
        ):
            flush_chunk()
        location["work_segment_index"] = work_segment_index
        location["sentence_start"] = total_sentences + 1
        current_locations.append(location)
        current_sentences += sentence_count
        current_text_chars += text_chars
        total_sentences += sentence_count
        total_text_chars += text_chars
    flush_chunk()

    segment_to_chunk: dict[str, int] = {}
    for chunk in chunks:
        for location in chunk["locations"]:
            segment_to_chunk[str(location["segment_id"])] = int(chunk["index"])

    return {
        "corpus_id": corpus_id,
        "work_id": work_id,
        "variant_id": variant_id,
        "segment_count": len(locations),
        "sentence_count": total_sentences,
        "text_chars": total_text_chars,
        "chunks": tuple(chunks),
        "segment_to_chunk": segment_to_chunk,
        "virtualized": (
            len(locations) >= VIRTUAL_WORK_MIN_SEGMENTS
            and total_text_chars >= VIRTUAL_WORK_MIN_TEXT_CHARS
        ),
    }


def work_chunk_manifest(corpus_id: str, work_id: str, variant_id: str = "") -> dict[str, Any]:
    return _cached_work_chunk_manifest(_manifest_cache_key(corpus_id, work_id, variant_id))


def anchor_segment_id(anchor: str) -> str:
    value = str(anchor or "").strip().lstrip("#")
    if ".s" in value:
        prefix, suffix = value.rsplit(".s", 1)
        if prefix and suffix.isdigit():
            return prefix
    return value


def chunk_index_for_anchor(manifest: dict[str, Any], anchor: str) -> int:
    segment_id = anchor_segment_id(anchor)
    try:
        return int(manifest["segment_to_chunk"][segment_id])
    except (KeyError, TypeError, ValueError) as exc:
        raise FileNotFoundError(f"work anchor not found: {anchor}") from exc


def localized_segment_label(record: dict[str, Any], fallback_index: int) -> str:
    segment_type = str(record.get("segment_type", ""))
    label = str(record.get("label") or "")
    order = int(record.get("order") or fallback_index)
    if segment_type == "paragraph":
        return f"문단 {order}"
    return label or str(record.get("segment_id") or "")


def render_chunk_records(chunk: dict[str, Any]) -> str:
    locations = list(chunk["locations"])
    if not locations:
        return ""
    corpus_id = str(locations[0]["corpus_id"])
    records = read_indexed_segment_records(corpus_id, locations)
    output: list[str] = []

    for location, record in zip(locations, records, strict=True):
        segment_id = str(record.get("segment_id") or "")
        segment_type = str(record.get("segment_type") or "paragraph")
        label = localized_segment_label(record, int(location["work_segment_index"]) + 1)
        escaped_id = html.escape(segment_id, quote=True)
        escaped_label = html.escape(label, quote=True)
        text_raw = str(record.get("text_raw") or "")

        if segment_type in {"section", "chapter"}:
            output.append(
                f'<h2 id="{escaped_id}" data-label="{escaped_label}" data-target-type="{html.escape(segment_type, quote=True)}">'
                f'<a class="segment-anchor" href="#{escaped_id}" aria-label="구역 링크">#</a>'
                f"{html.escape(label)}</h2>"
            )
            continue
        if segment_type == "quote":
            output.append(
                f'<blockquote id="{escaped_id}" data-label="{escaped_label}" data-target-type="quote">'
                f"{html.escape(text_raw)}</blockquote>"
            )
            continue

        sentence_offset = int(location["sentence_start"]) - 1
        sentence_html = render_sentence_spans(
            segment_id,
            text_raw,
            sentence_position_offset=sentence_offset,
        )
        if segment_type == "verse":
            output.append(
                f'<p id="{escaped_id}" class="verse" data-label="{escaped_label}" data-target-type="verse">'
                f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{escaped_label}">&#182;</a>'
                f'<span class="verse-label">{escaped_id}</span>'
                f'<span class="verse-text">{sentence_html}</span></p>'
            )
            continue
        output.append(
            f'<p id="{escaped_id}" data-label="{escaped_label}" data-target-type="paragraph">'
            f'<a class="segment-anchor" href="#{escaped_id}" aria-label="{escaped_label}">&#182;</a>'
            f"{sentence_html}</p>"
        )
    return "\n".join(output)


def estimated_chunk_height(chunk: dict[str, Any]) -> int:
    text_height = int(int(chunk["text_chars"]) / 58 * 24)
    segment_spacing = int(chunk["segment_count"]) * 16
    return max(480, min(26000, text_height + segment_spacing))


def public_chunk_descriptor(chunk: dict[str, Any]) -> dict[str, int | str]:
    return {
        "index": int(chunk["index"]),
        "first_segment_id": str(chunk["first_segment_id"]),
        "last_segment_id": str(chunk["last_segment_id"]),
        "segment_count": int(chunk["segment_count"]),
        "sentence_start": int(chunk["sentence_start"]),
        "sentence_count": int(chunk["sentence_count"]),
        "text_chars": int(chunk["text_chars"]),
        "estimated_height": estimated_chunk_height(chunk),
    }


def chunk_shell_markup(chunk: dict[str, Any], total_chunks: int, *, loaded: bool) -> str:
    descriptor = public_chunk_descriptor(chunk)
    index = int(descriptor["index"])
    common = (
        f'id="work-chunk-{index}" class="reader-chunk'
        f'{" is-loaded" if loaded else " reader-chunk-placeholder"}" '
        f'data-chunk-index="{index}" data-chunk-state="{"loaded" if loaded else "placeholder"}" '
        f'data-first-segment-id="{html.escape(str(descriptor["first_segment_id"]), quote=True)}" '
        f'data-last-segment-id="{html.escape(str(descriptor["last_segment_id"]), quote=True)}" '
        f'data-sentence-start="{descriptor["sentence_start"]}" '
        f'data-sentence-count="{descriptor["sentence_count"]}"'
    )
    if loaded:
        return f"<section {common}>{render_chunk_records(chunk)}</section>"
    label = f"문서 청크 {index + 1} / {total_chunks}"
    return (
        f'<section {common} aria-hidden="true" aria-busy="false" '
        f'style="min-height:{descriptor["estimated_height"]}px">'
        f'<span class="visually-hidden">{html.escape(label)} — 스크롤하면 불러옵니다.</span></section>'
    )


def virtual_work_document(
    corpus_id: str,
    work_id: str,
    variant_id: str = "",
    *,
    initial_anchor: str = "",
) -> dict[str, Any] | None:
    try:
        manifest = work_chunk_manifest(corpus_id, work_id, variant_id)
    except FileNotFoundError:
        return None
    if not manifest["virtualized"]:
        return None

    initial_chunk_index = chunk_index_for_anchor(manifest, initial_anchor) if initial_anchor else 0
    chunks = list(manifest["chunks"])
    content = "\n".join(
        chunk_shell_markup(chunk, len(chunks), loaded=int(chunk["index"]) == initial_chunk_index)
        for chunk in chunks
    )
    return {
        "html": content,
        "toc": [],
        "paragraph_count": int(manifest["segment_count"]),
        "heading_count": 0,
        "virtual_document": {
            "enabled": True,
            "endpoint": "/api/work-chunks",
            "initial_chunk": initial_chunk_index,
            "chunk_count": len(chunks),
            "total_segments": int(manifest["segment_count"]),
            "total_sentences": int(manifest["sentence_count"]),
            "chunks": [public_chunk_descriptor(chunk) for chunk in chunks],
        },
    }


def work_chunk_payload_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    corpus_id = first_query_value(query, "corpus_id")
    work_id = first_query_value(query, "work_id")
    variant_id = first_query_value(query, "variant_id")
    anchor = first_query_value(query, "anchor")
    if not corpus_id or not work_id:
        raise ValueError("missing required work chunk fields")

    manifest = work_chunk_manifest(corpus_id, work_id, variant_id)
    if not manifest["virtualized"]:
        raise ValueError("work does not require chunk loading")
    chunks = list(manifest["chunks"])
    if anchor:
        chunk_index = chunk_index_for_anchor(manifest, anchor)
    else:
        raw_chunk = first_query_value(query, "chunk", "0")
        try:
            chunk_index = int(raw_chunk)
        except ValueError as exc:
            raise ValueError("invalid work chunk index") from exc
    if chunk_index < 0 or chunk_index >= len(chunks):
        raise FileNotFoundError(f"work chunk not found: {chunk_index}")
    chunk = chunks[chunk_index]
    return {
        "schema_version": 1,
        "corpus_id": corpus_id,
        "work_id": work_id,
        "variant_id": variant_id,
        "chunk_count": len(chunks),
        "total_segments": int(manifest["segment_count"]),
        "total_sentences": int(manifest["sentence_count"]),
        "chunk": {
            **public_chunk_descriptor(chunk),
            "html": render_chunk_records(chunk),
        },
    }
