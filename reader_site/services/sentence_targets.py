from __future__ import annotations

from typing import Any

from sentence_units import normalized_inline_text, sentence_units
from services.segment_offsets import indexed_work_segment_locations, read_indexed_segment_records
from services.source_targets import resolve_segment_target, sha256_text


MAX_CONTEXT_CHARS = 6000
TARGET_SENTENCE_OPEN = "<TARGET_SENTENCE>"
TARGET_SENTENCE_CLOSE = "</TARGET_SENTENCE>"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def context_segment(position: str, text: str) -> str:
    return f'<CONTEXT_SEGMENT position="{position}">\n{text}\n</CONTEXT_SEGMENT>'


def marked_target_segment(
    source_text: str,
    sentence_text: str,
    max_chars: int = MAX_CONTEXT_CHARS,
    sentence_index: int = 1,
) -> str:
    paragraph = normalized_inline_text(source_text)
    target_sentence = normalized_inline_text(sentence_text)
    units = sentence_units("context", paragraph)
    require(0 < sentence_index <= len(units), "selected sentence index is outside its source paragraph")
    require(units[sentence_index - 1]["text_raw"] == target_sentence, "selected sentence does not match its source index")
    search_start = 0
    index = -1
    for unit in units[:sentence_index]:
        index = paragraph.find(str(unit["text_raw"]), search_start)
        require(index >= 0, "selected sentence is not present in its source paragraph")
        search_start = index + len(str(unit["text_raw"]))
    require(index >= 0, "selected sentence is not present in its source paragraph")

    prefix = '<CONTEXT_SEGMENT position="target">\n'
    suffix = "\n</CONTEXT_SEGMENT>"
    fixed_chars = len(prefix) + len(TARGET_SENTENCE_OPEN) + len(TARGET_SENTENCE_CLOSE) + len(suffix)
    text_budget = max_chars - fixed_chars
    require(len(target_sentence) <= text_budget, "selected sentence exceeds the translation context limit")

    if len(paragraph) <= text_budget:
        marked = (
            paragraph[:index]
            + TARGET_SENTENCE_OPEN
            + target_sentence
            + TARGET_SENTENCE_CLOSE
            + paragraph[index + len(target_sentence) :]
        )
        return prefix + marked + suffix

    target_index = sentence_index - 1
    selected_start = target_index
    selected_end = target_index

    def render_window(start: int, end: int) -> str:
        parts: list[str] = []
        if start > 0:
            parts.append("…")
        for unit_index in range(start, end + 1):
            unit_text = str(units[unit_index]["text_raw"])
            if unit_index == target_index:
                parts.append(TARGET_SENTENCE_OPEN + unit_text + TARGET_SENTENCE_CLOSE)
            else:
                parts.append(unit_text)
        if end < len(units) - 1:
            parts.append("…")
        return prefix + " ".join(parts) + suffix

    current = render_window(selected_start, selected_end)
    require(len(current) <= max_chars, "selected sentence exceeds the translation context limit")
    while True:
        expanded = False
        if selected_start > 0:
            candidate = render_window(selected_start - 1, selected_end)
            if len(candidate) <= max_chars:
                selected_start -= 1
                current = candidate
                expanded = True
        if selected_end < len(units) - 1:
            candidate = render_window(selected_start, selected_end + 1)
            if len(candidate) <= max_chars:
                selected_end += 1
                current = candidate
                expanded = True
        if not expanded:
            break
    return current


def structural_source_context(
    segment: dict[str, Any],
    sentence_text: str,
    max_chars: int = MAX_CONTEXT_CHARS,
    sentence_index: int = 1,
) -> dict[str, Any]:
    current_block = marked_target_segment(
        str(segment["text_raw"]),
        sentence_text,
        max_chars,
        sentence_index,
    )
    if len(current_block) >= max_chars:
        return {
            "source_context": current_block[:max_chars],
            "context_segments": [
                {
                    "segment_id": segment["segment_id"],
                    "position": "target",
                    "source_text_sha256": segment["source_text_sha256"],
                }
            ],
        }

    locations = indexed_work_segment_locations(
        str(segment["corpus_id"]),
        str(segment["work_id"]),
        str(segment.get("variant_id", "")),
    )
    current_index = next(
        (index for index, location in enumerate(locations) if location["segment_id"] == segment["segment_id"]),
        -1,
    )
    require(current_index >= 0, "selected segment is missing from its work context")

    remaining = max_chars - len(current_block)
    selected: dict[int, dict[str, Any]] = {}
    partial_candidates: dict[str, tuple[int, dict[str, Any]]] = {}
    blocked_sides: set[str] = set()
    distance = 1
    while remaining > 0 and len(blocked_sides) < 2:
        found_candidate = False
        for side, candidate_index in (("previous", current_index - distance), ("next", current_index + distance)):
            if side in blocked_sides:
                continue
            if candidate_index < 0 or candidate_index >= len(locations):
                blocked_sides.add(side)
                continue
            found_candidate = True
            location = locations[candidate_index]
            wrapper_chars = len(context_segment(side, "")) + 2
            estimated_chars = int(location["text_chars"]) + wrapper_chars
            if estimated_chars > remaining:
                partial_candidates[side] = (candidate_index, location)
                blocked_sides.add(side)
                continue
            selected[candidate_index] = location
            remaining -= estimated_chars
        if not found_candidate:
            break
        distance += 1

    read_locations = {index: location for index, location in selected.items()}
    read_locations.update({index: location for index, location in partial_candidates.values()})
    neighbor_records = read_indexed_segment_records(
        str(segment["corpus_id"]),
        [read_locations[index] for index in sorted(read_locations)],
    ) if read_locations else []
    neighbor_by_segment = {str(record["segment_id"]): record for record in neighbor_records}

    blocks: list[tuple[int, str]] = [(current_index, current_block)]
    context_segments = [
        {
            "segment_id": segment["segment_id"],
            "position": "target",
            "source_text_sha256": segment["source_text_sha256"],
        }
    ]
    for index in sorted(selected):
        location = selected[index]
        record = neighbor_by_segment[str(location["segment_id"])]
        position = "previous" if index < current_index else "next"
        text = normalized_inline_text(str(record.get("text_raw", "")))
        if not text:
            continue
        blocks.append((index, context_segment(position, text)))
        context_segments.append(
            {
                "segment_id": str(record["segment_id"]),
                "position": position,
                "source_text_sha256": sha256_text(str(record["text_raw"])),
            }
        )

    partial_units: dict[str, list[str]] = {}
    partial_counts: dict[str, int] = {}
    for side, (index, location) in partial_candidates.items():
        record = neighbor_by_segment[str(location["segment_id"])]
        partial_units[side] = [str(unit["text_raw"]) for unit in sentence_units("context", str(record.get("text_raw", "")))]
        partial_counts[side] = 0

    def partial_block(side: str, count: int) -> str:
        units = partial_units[side]
        if side == "previous":
            chosen = units[-count:]
            text = ("… " if count < len(units) else "") + " ".join(chosen)
        else:
            chosen = units[:count]
            text = " ".join(chosen) + (" …" if count < len(units) else "")
        return context_segment(side, text)

    while partial_candidates:
        expanded = False
        for side in ("previous", "next"):
            candidate = partial_candidates.get(side)
            if candidate is None:
                continue
            index, _ = candidate
            next_count = partial_counts[side] + 1
            if next_count > len(partial_units[side]):
                continue
            candidate_blocks = [(block_index, block) for block_index, block in blocks if block_index != index]
            candidate_blocks.append((index, partial_block(side, next_count)))
            candidate_context = "\n\n".join(block for _, block in sorted(candidate_blocks))
            if len(candidate_context) <= max_chars:
                blocks = candidate_blocks
                partial_counts[side] = next_count
                expanded = True
        if not expanded:
            break

    for side, (index, location) in partial_candidates.items():
        if partial_counts[side] == 0:
            record = neighbor_by_segment[str(location["segment_id"])]
            text = normalized_inline_text(str(record.get("text_raw", "")))
            base_context = "\n\n".join(block for _, block in sorted(blocks))
            wrapper_budget = max_chars - len(base_context) - 2 - len(context_segment(side, "")) - 1
            if wrapper_budget > 0 and text:
                excerpt = ("…" + text[-wrapper_budget:]) if side == "previous" else (text[:wrapper_budget] + "…")
                candidate_blocks = [*blocks, (index, context_segment(side, excerpt))]
                candidate_context = "\n\n".join(block for _, block in sorted(candidate_blocks))
                if len(candidate_context) <= max_chars:
                    blocks = candidate_blocks
                    partial_counts[side] = -1
        if partial_counts[side] != 0:
            record = neighbor_by_segment[str(location["segment_id"])]
            context_segments.append(
                {
                    "segment_id": str(record["segment_id"]),
                    "position": side,
                    "source_text_sha256": sha256_text(str(record["text_raw"])),
                }
            )

    source_context = "\n\n".join(block for _, block in sorted(blocks))
    require(len(source_context) <= max_chars, "structural source context exceeds its character limit")
    require(source_context.count(TARGET_SENTENCE_OPEN) == 1, "translation context must contain one target marker")
    return {
        "source_context": source_context,
        "context_segments": sorted(
            context_segments,
            key=lambda item: next(
                location["record_order"]
                for location in locations
                if location["segment_id"] == item["segment_id"]
            ),
        ),
    }


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
        context = structural_source_context(segment, sentence_text, sentence_index=int(unit["sentence_index"]))
        source_context = str(context["source_context"])
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
            "work_title": segment.get("title", work_id),
            "source_text": source_text,
            "sentence_text": sentence_text,
            "source_context": source_context,
            "source_context_chars": len(source_context),
            "source_context_sha256": sha256_text(source_context),
            "context_segments": context["context_segments"],
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
        "schema_version": 2,
        "record_type": "sentence_target_bundle",
        **target,
    }
