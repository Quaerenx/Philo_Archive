from __future__ import annotations

import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.source_targets import (  # noqa: E402
    SEGMENT_TARGET_CACHE_MAX_ENTRIES,
    SEGMENT_TARGET_CACHE_TTL_SECONDS,
    resolve_segment_target,
)


CASES = [
    ("nietzsche", "GM", "p-0023", ""),
    ("bible", "sblgnt.John", "John.3.16", ""),
    ("bible", "oshb.Gen", "Gen.1.1", ""),
    ("kierkegaard", "ba", "sks-0001", "text"),
    ("wittgenstein", "Ms-101", "p-0001", "source_transcription_normalized.full"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(SEGMENT_TARGET_CACHE_MAX_ENTRIES == 256, "source target cache size should be explicit")
    require(SEGMENT_TARGET_CACHE_TTL_SECONDS == 300, "source target cache TTL should be explicit")
    for corpus_id, work_id, segment_id, variant_id in CASES:
        target = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
        repeated = resolve_segment_target(corpus_id, work_id, segment_id, variant_id)
        context = f"{corpus_id}/{work_id}/{variant_id}/{segment_id}"
        require(target["corpus_id"] == corpus_id, f"{context}: corpus_id mismatch")
        require(target["work_id"] == work_id, f"{context}: work_id mismatch")
        require(target["segment_id"] == segment_id, f"{context}: segment_id mismatch")
        require(repeated == target, f"{context}: cached repeated lookup mismatch")
        require(len(target["source_text_sha256"]) == 64, f"{context}: invalid source_text_sha256")
        require(target["url"].startswith(f"/work/{corpus_id}/"), f"{context}: invalid URL")
        require(target["text_raw"].strip(), f"{context}: empty source text")

    try:
        resolve_segment_target("nietzsche", "GM", "missing", "")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing segment target should raise FileNotFoundError")

    print(f"source target contracts ok ({len(CASES)} cases)")


if __name__ == "__main__":
    main()
