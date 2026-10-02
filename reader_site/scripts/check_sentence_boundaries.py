"""Source-light splitter regressions; synthetic cases are not model-quality scores."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from sentence_units import (  # noqa: E402
    normalized_inline_text,
    render_sentence_spans,
    sentence_units,
    split_sentence_texts,
)
from services import sentence_targets  # noqa: E402
from services.source_targets import sha256_text  # noqa: E402


R23_STRUCTURE_SOURCE = "First ( ɔ: a gloss). Next."


class SentenceBoundaryChecks(unittest.TestCase):
    def test_r23_bracket_pattern_stays_complete(self) -> None:
        self.assertEqual(split_sentence_texts(R23_STRUCTURE_SOURCE), ["First ( ɔ: a gloss).", "Next."])
        self.assertEqual(
            sentence_units("p-test", R23_STRUCTURE_SOURCE),
            [
                {
                    "sentence_id": "p-test.s001",
                    "sentence_index": 1,
                    "text_raw": "First ( ɔ: a gloss).",
                    "label": "문장 1",
                },
                {
                    "sentence_id": "p-test.s003",
                    "sentence_index": 2,
                    "text_raw": "Next.",
                    "label": "문장 2",
                },
            ],
        )

    def test_all_legacy_punctuation_inside_parentheses_is_protected(self) -> None:
        source = "Before (one. Two! Why? Note; word: detail) continues. After."
        self.assertEqual(
            split_sentence_texts(source),
            ["Before (one. Two! Why? Note; word: detail) continues.", "After."],
        )
        self.assertEqual(
            [unit["sentence_id"] for unit in sentence_units("p-test", source)],
            ["p-test.s001", "p-test.s007"],
        )

    def test_nested_bracket_types(self) -> None:
        cases = [
            (
                "Start (outer: [inner; detail] again) ends. Next.",
                ["Start (outer: [inner; detail] again) ends.", "Next."],
            ),
            (
                "Start (outer (inner: detail); again) ends. Next.",
                ["Start (outer (inner: detail); again) ends.", "Next."],
            ),
            (
                "Start {outer: [inner; detail]} ends. Next.",
                ["Start {outer: [inner; detail]} ends.", "Next."],
            ),
            (
                "문장（설명: 안쪽［하나; 둘］）이다. 다음.",
                ["문장（설명: 안쪽［하나; 둘］）이다.", "다음."],
            ),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(split_sentence_texts(source), expected)

    def test_external_colons_and_semicolons_keep_existing_units(self) -> None:
        source = "One: two; three. Four!"
        self.assertEqual(split_sentence_texts(source), ["One:", "two;", "three.", "Four!"])
        self.assertEqual(
            [unit["sentence_id"] for unit in sentence_units("p-test", source)],
            ["p-test.s001", "p-test.s002", "p-test.s003", "p-test.s004"],
        )

    def test_quote_closing_punctuation_respects_bracket_depth(self) -> None:
        self.assertEqual(
            split_sentence_texts('“First.” “Second!” End.'),
            ['“First.”', '“Second!”', "End."],
        )
        self.assertEqual(
            split_sentence_texts('Text (“First.” “Second!”) remains. Next.'),
            ['Text (“First.” “Second!”) remains.', "Next."],
        )

    def test_no_new_boundary_after_parenthesis_or_ascii_quote(self) -> None:
        # These were not legacy boundaries. Splitting them would require a
        # separate ID migration, rather than reusing an existing slot.
        self.assertEqual(
            split_sentence_texts("Text (ends.) Next. Last."),
            ["Text (ends.) Next.", "Last."],
        )
        self.assertEqual(
            split_sentence_texts('"First." Next. Last.'),
            ['"First." Next.', "Last."],
        )

    def test_unclosed_opening_bracket_keeps_remaining_source_intact(self) -> None:
        source = "Before. Open (explanation: unfinished. Next."
        self.assertEqual(
            split_sentence_texts(source),
            ["Before.", "Open (explanation: unfinished. Next."],
        )
        self.assertEqual(" ".join(split_sentence_texts(source)), source)

    def test_unmatched_closer_does_not_disable_later_boundaries(self) -> None:
        self.assertEqual(
            split_sentence_texts("First ) remains. Next: last."),
            ["First ) remains.", "Next:", "last."],
        )

    def test_mismatched_nesting_is_not_silently_repaired(self) -> None:
        source = "Start ([inner) detail: more]. Next."
        self.assertEqual(split_sentence_texts(source), [source])

    def test_repeated_sentences_have_stable_ids_and_contiguous_positions(self) -> None:
        source = "Repeat. Note (a: b). Repeat. Tail."
        units = sentence_units("p-test", source)
        self.assertEqual(
            [unit["sentence_id"] for unit in units],
            ["p-test.s001", "p-test.s002", "p-test.s004", "p-test.s005"],
        )
        self.assertEqual([unit["sentence_index"] for unit in units], [1, 2, 3, 4])
        self.assertEqual([unit["label"] for unit in units], ["문장 1", "문장 2", "문장 3", "문장 4"])
        marked = sentence_targets.marked_target_segment(source, "Repeat.", sentence_index=3)
        self.assertIn("Repeat. Note (a: b). <TARGET_SENTENCE>Repeat.</TARGET_SENTENCE> Tail.", marked)
        rendered = render_sentence_spans("p-test", source, sentence_position_offset=40)
        self.assertEqual(re.findall(r'data-sentence-position="(\d+)"', rendered), ["41", "42", "43", "44"])
        self.assertNotIn('id="p-test.s003"', rendered)

    def test_absorbed_id_fails_in_real_sentence_resolver(self) -> None:
        source = "Lead. Note (a: b). Tail."
        segment = {
            "corpus_id": "kierkegaard",
            "work_id": "synthetic",
            "variant_id": "text",
            "segment_id": "p-test",
            "label": "Synthetic fixture",
            "url": "/work/kierkegaard/synthetic#p-test",
            "text_raw": source,
            "source_text_sha256": sha256_text(source),
        }
        with (
            patch.object(sentence_targets, "resolve_segment_target", return_value=segment),
            patch.object(
                sentence_targets,
                "indexed_work_segment_locations",
                return_value=[{"segment_id": "p-test", "record_order": 0}],
            ),
        ):
            with self.assertRaises(FileNotFoundError):
                sentence_targets.resolve_sentence_target(
                    "kierkegaard", "synthetic", "p-test", "p-test.s003", "text"
                )
            target = sentence_targets.resolve_sentence_target(
                "kierkegaard", "synthetic", "p-test", "p-test.s004", "text"
            )
        self.assertEqual(target["sentence_text"], "Tail.")
        self.assertEqual(target["sentence_text_sha256"], sha256_text("Tail."))
        self.assertIn("<TARGET_SENTENCE>Tail.</TARGET_SENTENCE>", target["source_context"])

    def test_empty_and_whitespace_normalization_are_unchanged(self) -> None:
        for source in ("", " \t\r\n "):
            with self.subTest(source=source):
                self.assertEqual(split_sentence_texts(source), [])
                self.assertEqual(sentence_units("p-test", source), [])
                self.assertEqual(render_sentence_spans("p-test", source), "")
        source = "  One\n(a:\t b).\r\n Two.  "
        expected = ["One (a: b).", "Two."]
        self.assertEqual(split_sentence_texts(source), expected)
        self.assertEqual(" ".join(expected), normalized_inline_text(source))

    def test_rendered_hash_binds_normalized_source_before_html_escaping(self) -> None:
        source = "  한글 <표시>\n(a: b).\t Next.  "
        rendered = render_sentence_spans("p-test", source)
        self.assertEqual(
            re.findall(r'data-sentence-sha256="([a-f0-9]{64})"', rendered),
            [sha256_text("한글 <표시> (a: b)."), sha256_text("Next.")],
        )
        self.assertIn("&lt;표시&gt;", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
