from __future__ import annotations


def translation_unavailable_reason(corpus_id: str, variant_id: str) -> str:
    if corpus_id == "wittgenstein" and variant_id.endswith(".index"):
        return "이 판본은 원문 탐색용 색인입니다. 본문 판본에서 번역할 문장을 선택해 주세요."
    return ""
