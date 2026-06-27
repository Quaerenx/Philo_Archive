from __future__ import annotations

import html
import re


SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:\u00bb\u201d\u2019\u3002\uff01\uff1f\u05c3])\s+")


def normalized_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_sentence_texts(value: str) -> list[str]:
    text = normalized_inline_text(value)
    if not text:
        return []
    parts = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    return parts or [text]


def sentence_units(segment_id: str, text: str) -> list[dict[str, str | int]]:
    units = []
    for index, sentence_text in enumerate(split_sentence_texts(text), start=1):
        units.append(
            {
                "sentence_id": f"{segment_id}.s{index:03d}",
                "sentence_index": index,
                "text_raw": sentence_text,
                "label": f"문장 {index}",
            }
        )
    return units


def render_sentence_spans(segment_id: str, text: str) -> str:
    spans = []
    for unit in sentence_units(segment_id, text):
        sentence_id = str(unit["sentence_id"])
        label = str(unit["label"])
        sentence_text = str(unit["text_raw"])
        spans.append(
            f'<span id="{html.escape(sentence_id, quote=True)}" '
            f'class="reader-sentence" data-target-type="sentence" '
            f'data-segment-id="{html.escape(segment_id, quote=True)}" '
            f'data-sentence-id="{html.escape(sentence_id, quote=True)}" '
            f'data-label="{html.escape(label, quote=True)}">'
            f"{html.escape(sentence_text)}</span>"
        )
    return " ".join(spans)
