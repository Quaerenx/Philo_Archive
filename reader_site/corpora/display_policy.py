from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import Any


CORPUS_DISPLAY_POLICIES = MappingProxyType(
    {
        "nietzsche": {
            "default_variant_prefixes": (),
            "categories": {
                "major_published_books": "주요 출간 저작",
                "untimely_meditations": "시대에 맞지 않는 고찰",
                "late_posthumous_books": "후기·사후 편집 저작",
                "lectures_essays_fragments": "강연·에세이·단편",
            },
            "variants": {},
        },
        "bible": {
            "default_variant_prefixes": ("oshb_morphhb", "sblgnt", "lxx_swete"),
            "categories": {
                "hebrew_bible": "히브리어 성경",
                "greek_nt": "그리스어 신약성경",
                "lxx_deuterocanon": "칠십인역(LXX)·제2경전",
            },
            "variants": {
                "oshb_morphhb": "OSHB 히브리어 본문",
                "sblgnt": "SBLGNT 그리스어 신약",
                "lxx_swete": "Swete 칠십인역(LXX)",
            },
        },
        "kierkegaard": {
            "default_variant_prefixes": ("text", "commentary", "textual_account"),
            "categories": {
                "sks": "『쇠렌 키르케고르 저작집』(SKS)",
            },
            "variants": {
                "text": "본문",
                "commentary": "주석",
                "textual_account": "텍스트 성립 자료",
            },
        },
        "wittgenstein": {
            "default_variant_prefixes": (
                "source_transcription_normalized.full",
                "source_transcription_normalized.index",
                "source_transcription_diplomatic.full",
                "source_transcription_diplomatic.index",
                "idp_transcription_linear",
                "idp_transcription_diplomatic",
                "source_metadata",
            ),
            "categories": {
                "source_items": "원전 자료",
                "idp_groups": "IDP 묶음",
            },
            "variants": {
                "source_transcription_normalized.full": "정규화 전사·전체",
                "source_transcription_normalized.index": "정규화 전사·색인",
                "source_transcription_diplomatic.full": "외교적 전사·전체",
                "source_transcription_diplomatic.index": "외교적 전사·색인",
                "idp_transcription_linear": "IDP 선형 전사",
                "idp_transcription_diplomatic": "IDP 외교적 전사",
                "source_metadata": "메타데이터",
            },
        },
    }
)


def policy_for(corpus_id: str) -> dict[str, Any]:
    return dict(CORPUS_DISPLAY_POLICIES.get(str(corpus_id), {}))


def preferred_variant_ids(corpus_id: str) -> tuple[str, ...]:
    policy = CORPUS_DISPLAY_POLICIES.get(str(corpus_id), {})
    return tuple(str(value) for value in policy.get("default_variant_prefixes", ()))


def category_display_label(corpus_id: str, category_id: str, fallback: str = "") -> str:
    policy = CORPUS_DISPLAY_POLICIES.get(str(corpus_id), {})
    categories = policy.get("categories", {})
    return str(categories.get(str(category_id)) or fallback or category_id)


def variant_display_label(corpus_id: str, variant: dict[str, Any] | str) -> str:
    variant_id = str(variant.get("variant_id", "")) if isinstance(variant, dict) else str(variant)
    fallback = str(variant.get("label", "")) if isinstance(variant, dict) else variant_id
    policy = CORPUS_DISPLAY_POLICIES.get(str(corpus_id), {})
    labels = policy.get("variants", {})
    if variant_id in labels:
        return str(labels[variant_id])
    prefix = variant_id.split(".", 1)[0]
    return str(labels.get(prefix) or fallback or variant_id)


def ordered_variants(corpus_id: str, variants: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    values = list(variants)
    preferred = preferred_variant_ids(corpus_id)

    def order_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        original_index, variant = item
        variant_id = str(variant.get("variant_id", ""))
        for rank, preferred_id in enumerate(preferred):
            if variant_id == preferred_id or variant_id.startswith(f"{preferred_id}."):
                return (rank, original_index)
        return (len(preferred), original_index)

    return [variant for _, variant in sorted(enumerate(values), key=order_key)]
