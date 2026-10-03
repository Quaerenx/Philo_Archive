from __future__ import annotations

import re


def strip_links(value: str, *, inert_only: bool = False) -> str:
    target = r"javascript:;" if inert_only else r"[^)]*"
    label = r"((?:[^\[\]\n]|\[[^\[\]\n]*\])+)"
    value = re.sub(r"\[\[" + label + r"\]\]\(" + target + r"\)", r"\1", value)
    return re.sub(r"\[" + label + r"\]\(" + target + r"\)", r"\1", value)
