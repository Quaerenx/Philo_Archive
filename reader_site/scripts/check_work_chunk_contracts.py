from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.segment_offsets import SEGMENT_FILES  # noqa: E402
from services.work_chunks import (  # noqa: E402
    VIRTUAL_WORK_MIN_SEGMENTS,
    anchor_segment_id,
    chunk_index_for_anchor,
    virtual_work_document,
    work_chunk_manifest,
    work_chunk_payload_from_query,
)
from services.work_pages import build_work_page_html  # noqa: E402


CORPUS_ID = "wittgenstein"
WORK_ID = "Group_BigTypescriptCorpus"
VARIANT_ID = "idp_transcription_linear"
FIRST_ANCHOR = "p-0001.s001"
MIDDLE_ANCHOR = "p-3301.s001"
LAST_ANCHOR = "p-6600.s009"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def query(**values: str) -> dict[str, list[str]]:
    return {key: [value] for key, value in values.items()}


def payload_for(**values: str) -> dict:
    defaults = {
        "corpus_id": CORPUS_ID,
        "work_id": WORK_ID,
        "variant_id": VARIANT_ID,
    }
    defaults.update(values)
    return work_chunk_payload_from_query(query(**defaults))


def sentence_ids(markup: str) -> list[str]:
    return re.findall(r'id="([^"]+\.s\d+)"', markup)


def check_manifest_and_boundaries() -> None:
    manifest = work_chunk_manifest(CORPUS_ID, WORK_ID, VARIANT_ID)
    require(manifest["virtualized"] is True, "largest Wittgenstein work should be virtualized")
    require(manifest["segment_count"] >= VIRTUAL_WORK_MIN_SEGMENTS, "large work segment count is too small")
    require(manifest["sentence_count"] == 108_891, "large work sentence count changed unexpectedly")
    require(len(manifest["chunks"]) > 1, "large work should contain multiple chunks")
    require(anchor_segment_id(MIDDLE_ANCHOR) == "p-3301", "sentence anchor should resolve to its segment")

    expected_chunks = {
        FIRST_ANCHOR: 0,
        MIDDLE_ANCHOR: 158,
        LAST_ANCHOR: len(manifest["chunks"]) - 1,
    }
    for anchor, expected_chunk in expected_chunks.items():
        chunk_index = chunk_index_for_anchor(manifest, anchor)
        require(chunk_index == expected_chunk, f"{anchor} resolved to chunk {chunk_index}, not {expected_chunk}")
        payload = payload_for(anchor=anchor)
        ids = sentence_ids(payload["chunk"]["html"])
        require(anchor in ids, f"chunk payload did not preserve deep-link sentence ID {anchor}")
        require(payload["chunk"]["index"] == expected_chunk, f"{anchor} payload chunk mismatch")

    first_payload = payload_for(chunk="0")
    second_payload = payload_for(chunk="1")
    first_positions = [int(value) for value in re.findall(r'data-sentence-position="(\d+)"', first_payload["chunk"]["html"])]
    second_positions = [int(value) for value in re.findall(r'data-sentence-position="(\d+)"', second_payload["chunk"]["html"])]
    require(first_positions[0] == 1, "first sentence position should remain one-based")
    require(first_positions[-1] + 1 == second_positions[0], "sentence positions should be contiguous across chunks")


def check_initial_and_print_views() -> None:
    document = virtual_work_document(CORPUS_ID, WORK_ID, VARIANT_ID)
    require(document is not None, "large work should produce a virtual document")
    require(document["virtual_document"]["enabled"] is True, "virtual document metadata missing")
    require(document["html"].count('class="reader-chunk') == document["virtual_document"]["chunk_count"], "chunk shells mismatch")

    page = build_work_page_html(CORPUS_ID, WORK_ID, VARIANT_ID)
    page_bytes = len(page.encode("utf-8"))
    require(page_bytes < 2 * 1024 * 1024, f"initial large-work HTML exceeds 2 MiB: {page_bytes}")
    require("virtual-work" in page, "large work page missing virtual-work marker")
    require(FIRST_ANCHOR in page, "initial chunk should contain the first sentence")
    require(MIDDLE_ANCHOR not in page, "initial page should not eagerly render a middle chunk")
    require("전체 인쇄 보기" in page, "virtual page should expose the complete print view")

    print_page = build_work_page_html(CORPUS_ID, WORK_ID, VARIANT_ID, view="print")
    require("virtual-work" not in print_page and "print-work" in print_page, "print view should render the complete work")
    require(FIRST_ANCHOR in print_page and LAST_ANCHOR in print_page, "print view should contain first and last sentences")

    normal_page = build_work_page_html("nietzsche", "GM")
    require("virtual-work" not in normal_page, "normal-sized work should keep eager rendering")
    require("reader-chunk-placeholder" not in normal_page, "normal-sized work should not receive chunk shells")


def check_unicode_and_bounded_source_reads() -> None:
    source_path = SEGMENT_FILES[CORPUS_ID]
    source_size = source_path.stat().st_size
    read_sizes: list[int] = []
    original_open = Path.open

    class TrackingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def seek(self, *args):
            return self.handle.seek(*args)

        def read(self, size: int = -1):
            require(size > 0, "work chunk lookup attempted an unbounded JSONL read")
            read_sizes.append(size)
            return self.handle.read(size)

    def tracked_open(path: Path, mode: str = "r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == source_path and mode == "rb":
            return TrackingReader(handle)
        return handle

    with patch.object(Path, "open", tracked_open):
        payload = payload_for(anchor=MIDDLE_ANCHOR)
    require(read_sizes, "work chunk lookup did not read indexed source records")
    require(all(size < source_size for size in read_sizes), "work chunk lookup read the entire JSONL artifact")

    rendered = payload["chunk"]["html"]
    non_ascii_text = re.sub(r"<[^>]+>", " ", html.unescape(rendered))
    require(any(ord(character) > 127 for character in non_ascii_text), "chunk rendering lost Unicode source text")


def check_errors() -> None:
    for bad_query, expected_exception in (
        ({"corpus_id": [CORPUS_ID]}, ValueError),
        (query(corpus_id=CORPUS_ID, work_id=WORK_ID, variant_id=VARIANT_ID, chunk="-1"), FileNotFoundError),
        (query(corpus_id=CORPUS_ID, work_id=WORK_ID, variant_id=VARIANT_ID, anchor="missing"), FileNotFoundError),
    ):
        try:
            work_chunk_payload_from_query(bad_query)
        except expected_exception:
            pass
        else:
            raise AssertionError(f"invalid work chunk query should raise {expected_exception.__name__}")


def main() -> None:
    check_manifest_and_boundaries()
    check_initial_and_print_views()
    check_unicode_and_bounded_source_reads()
    check_errors()
    print("work chunk contracts ok")


if __name__ == "__main__":
    main()
