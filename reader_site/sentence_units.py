from __future__ import annotations

import hashlib
import html
import re


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:\u00bb\u201d\u2019\u3002\uff01\uff1f\u05c3])\s+")
BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}", "（": "）", "［": "］", "｛": "｝"}
BRACKET_CLOSERS = frozenset(BRACKET_PAIRS.values())


def normalized_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sentence_parts(value: str) -> list[tuple[int, str]]:
    """Merge boundaries inside brackets while preserving legacy start slots.

    Only boundaries recognized by the original splitter can end a unit. In
    particular, this does not add a boundary after ``end.) Next.`` or an ASCII
    closing quote. Adding boundaries would require a separate ID migration.

    A merged unit keeps its first legacy slot; absorbed fragment IDs are not
    reassigned or aliased. Exact sentence-ID lookup therefore fails closed for
    those IDs instead of silently selecting a later sentence. An unmatched
    opening bracket conservatively keeps the rest of the paragraph together;
    no missing source punctuation is supplied or repaired.
    """
    text = normalized_inline_text(value)
    if not text:
        return []

    parts: list[tuple[int, str]] = []
    expected_closers: list[str] = []
    part_start = scan_start = 0
    first_legacy_slot = 1
    for legacy_slot, boundary in enumerate(SENTENCE_BOUNDARY.finditer(text), start=1):
        for character in text[scan_start:boundary.start()]:
            if character in BRACKET_PAIRS:
                expected_closers.append(BRACKET_PAIRS[character])
            elif character in BRACKET_CLOSERS and expected_closers:
                if character == expected_closers[-1]:
                    expected_closers.pop()
        scan_start = boundary.end()
        if expected_closers:
            continue
        parts.append((first_legacy_slot, text[part_start:boundary.start()]))
        part_start = boundary.end()
        first_legacy_slot = legacy_slot + 1
    parts.append((first_legacy_slot, text[part_start:]))
    return parts


def split_sentence_texts(value: str) -> list[str]:
    return [sentence_text for _, sentence_text in _sentence_parts(value)]


def sentence_units(segment_id: str, text: str) -> list[dict[str, str | int]]:
    """Keep stable legacy start-slot IDs and contiguous display/position indices.

    After fragment merging, IDs can have gaps (s001, s003), while
    ``sentence_index`` and labels remain consecutive (1, 2). Consumers must use
    ``sentence_index`` for positions and treat ``sentence_id`` as an opaque ID.
    """
    units = []
    for index, (legacy_slot, sentence_text) in enumerate(_sentence_parts(text), start=1):
        units.append(
            {
                "sentence_id": f"{segment_id}.s{legacy_slot:03d}",
                "sentence_index": index,
                "text_raw": sentence_text,
                "label": f"문장 {index}",
            }
        )
    return units


def render_sentence_spans(segment_id: str, text: str, *, sentence_position_offset: int = -1) -> str:
    spans = []
    for unit in sentence_units(segment_id, text):
        sentence_id = str(unit["sentence_id"])
        label = str(unit["label"])
        sentence_text = str(unit["text_raw"])
        sentence_sha256 = hashlib.sha256(sentence_text.encode("utf-8")).hexdigest()
        sentence_position = sentence_position_offset + int(unit["sentence_index"])
        position_attribute = (
            f' data-sentence-position="{sentence_position}"'
            if sentence_position_offset >= 0
            else ""
        )
        spans.append(
            f'<span id="{html.escape(sentence_id, quote=True)}" '
            f'class="reader-sentence" data-target-type="sentence" '
            f'data-segment-id="{html.escape(segment_id, quote=True)}" '
            f'data-sentence-id="{html.escape(sentence_id, quote=True)}" '
            f'data-sentence-sha256="{sentence_sha256}" '
            f'data-label="{html.escape(label, quote=True)}"{position_attribute}>'
            f"{html.escape(sentence_text)}</span>"
        )
    return " ".join(spans)
