from __future__ import annotations

import html
import re
from typing import Any


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:\u00bb\u201d\u2019\u3002\uff01\uff1f\u05c3])\s+")


def normalized_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def joins_abbreviation(previous: str, following: str) -> bool:
    # Historical Danish "that is": the colon belongs to the abbreviation.
    if re.search(r"(?:^|[\s(])ɔ\s*:$", previous):
        return True
    if re.search(r"\b(?:Dr|Prof|Mr|Mrs|Ms|Hr|Fr|Skt|St|Chr|Nr|Bd|Vol)\.$", previous, re.IGNORECASE):
        return bool(re.match(r"[\w]", following))
    if re.search(r"\b(?:d\.\s*h|z\.\s*B|u\.\s*a|f\.\s*eks|bl\.\s*a)\.$", previous, re.IGNORECASE):
        return True
    if re.search(r"\b(?:d|z|u|f|bl)\.$", previous, re.IGNORECASE):
        pair = re.search(r"\b(\w+)\.$", previous)
        expected = {"d": "h", "z": "b", "u": "a", "f": "eks", "bl": "a"}
        if pair and re.match(rf"{expected[pair.group(1).lower()]}\.(?:\s|$)", following, re.IGNORECASE):
            return True
    return bool(re.search(r"\b[A-ZÄÖÜÆØÅ]\.$", previous) and re.match(r"[A-ZÄÖÜÆØÅ](?:[a-zäöüæøåA-ZÄÖÜÆØÅ]|\.)", following))


def sentence_groups(value: str) -> list[tuple[int, int, str]]:
    text = normalized_inline_text(value)
    if not text:
        return []
    parts = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    groups: list[tuple[int, int, str]] = []
    for index, part in enumerate(parts, start=1):
        if groups and joins_abbreviation(groups[-1][2], part):
            start, _, previous = groups[-1]
            groups[-1] = (start, index, previous + " " + part)
        else:
            groups.append((index, index, part))
    return groups


def split_sentence_texts(value: str) -> list[str]:
    return [text for _, _, text in sentence_groups(value)]


def sentence_units(segment_id: str, text: str) -> list[dict[str, Any]]:
    units = []
    for index, (legacy_start, legacy_end, sentence_text) in enumerate(sentence_groups(text), start=1):
        units.append(
            {
                # Keep every unaffected ID stable when adjacent abbreviation fragments merge.
                "sentence_id": f"{segment_id}.s{legacy_start:03d}",
                "sentence_index": index,
                "text_raw": sentence_text,
                "label": f"문장 {index}",
                "legacy_sentence_ids": [f"{segment_id}.s{old:03d}" for old in range(legacy_start + 1, legacy_end + 1)],
            }
        )
    return units


def render_sentence_spans(segment_id: str, text: str, *, sentence_position_offset: int = -1, translatable: bool = True) -> str:
    spans = []
    for unit in sentence_units(segment_id, text):
        sentence_id = str(unit["sentence_id"])
        label = str(unit["label"])
        sentence_text = str(unit["text_raw"])
        aliases = "".join(
            f'<span id="{html.escape(alias, quote=True)}" data-sentence-alias="{html.escape(sentence_id, quote=True)}" aria-hidden="true"></span>'
            for alias in unit["legacy_sentence_ids"]
        )
        if not translatable:
            spans.append(f'<span id="{html.escape(sentence_id, quote=True)}" class="reader-reference">{aliases}{html.escape(sentence_text)}</span>')
            continue
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
            f'data-label="{html.escape(label, quote=True)}"{position_attribute}>'
            f"{aliases}{html.escape(sentence_text)}</span>"
        )
    return " ".join(spans)
