from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from services import sentence_translations as translations  # noqa: E402


class ReaderUsabilityContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "nietzsche_sentence_translations.jsonl"
        self.target = {"corpus_id": "nietzsche", "work_id": "ui-fixture", "variant_id": "", "segment_id": "p-0001",
            "sentence_id": "p-0001.s001", "sentence_text_sha256": translations.sha256_text("source sentence")}
        self.record = {**self.target, "id": "11111111-1111-4111-8111-111111111111", "record_type": "ai_sentence_translation",
            "translation": "UI 검증용 번역", "review_state": "generated", "generated_at": "2026-10-01T00:00:00Z",
            "quality_state": "needs_human_review", "translation_notes": []}
        self.write([self.record])

    def tearDown(self):
        self.directory.cleanup()

    def write(self, records):
        self.path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        translations._read_translation_snapshot.cache_clear()

    def lookup(self, **options):
        with patch.object(translations, "AI_DIR", self.root), patch.object(translations, "sentence_target_bundle", return_value=self.target), \
            patch.object(translations, "build_sentence_prompt_bundle", side_effect=AssertionError("cache browsing prepared a prompt")), \
            patch.object(translations, "run_translation_pipeline", side_effect=AssertionError("cache browsing generated a translation")):
            return translations.sentence_translation_from_payload({**self.target, "cache_only": True, **options})

    def test_cache_browsing_returns_flagged_model_without_generation(self):
        before = self.path.read_bytes()
        result = self.lookup()
        self.assertTrue(result["cached"])
        self.assertEqual(result["record"]["translation"], self.record["translation"])
        self.assertEqual(result["metrics"]["model_calls"], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cache_miss_requires_explicit_generation_without_prompt_or_write(self):
        self.write([])
        before = self.path.read_bytes()
        result = self.lookup()
        self.assertTrue(result["requires_generation"])
        self.assertIsNone(result["record"])
        self.assertEqual(result["metrics"]["model_calls"], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cache_lookup_rejects_stale_source_and_wrong_variant(self):
        for changed in ({"sentence_text_sha256": "a" * 64}, {"variant_id": "other"}, {"review_state": "rejected"}):
            with self.subTest(changed=changed):
                self.write([{**self.record, **changed}])
                self.assertTrue(self.lookup()["requires_generation"])

    def test_human_confirmation_survives_newer_model_generation_and_model_save(self):
        approved = {**self.record, "human_translation": "사람이 확정한 번역", "review_state": "reviewed",
            "human_translation_updated_at": "2026-10-02T00:00:00Z"}
        newer = {**self.record, "id": "22222222-2222-4222-8222-222222222222", "translation": "새 모델 번역",
            "generated_at": "2026-10-04T00:00:00Z", "review_state": "reviewed", "reviewed_at": "2026-10-04T00:00:00Z"}
        self.write([approved, newer])
        self.assertEqual(self.lookup()["record"]["human_translation"], approved["human_translation"])
        with patch.object(translations, "ai_record_paths_for_query", return_value=[self.path]):
            summary = translations.sentence_translations_summary_from_query({"corpus_id": ["nietzsche"]})
        self.assertTrue(summary["sentence_states"][0]["human_confirmed"])
        self.assertEqual(summary["sentence_states"][0]["record_id"], approved["id"])

    def test_cache_only_flags_are_strict(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.lookup(cache_only="true")
        with self.assertRaisesRegex(ValueError, "cannot regenerate"):
            self.lookup(regenerate=True)

    def test_summary_and_reader_choose_the_same_latest_human_approval_across_timezones(self):
        earlier = {**self.record, "human_translation": "이전 확정", "review_state": "reviewed",
            "human_translation_updated_at": "2026-10-02T14:00:00+09:00"}
        later = {**self.record, "id": "22222222-2222-4222-8222-222222222222", "human_translation": "나중 확정", "review_state": "reviewed",
            "human_translation_updated_at": "2026-10-02T10:00:00Z"}
        self.write([later, earlier])
        self.assertEqual(self.lookup()["record"]["id"], later["id"])
        with patch.object(translations, "ai_record_paths_for_query", return_value=[self.path]):
            summary = translations.sentence_translations_summary_from_query({})
        self.assertEqual(summary["sentence_states"][0]["record_id"], later["id"])

    def test_conflicting_human_edit_does_not_overwrite_or_remove_model(self):
        before = self.path.read_bytes()
        payload = {"corpus_id": "nietzsche", "review_state": "reviewed", "human_translation": "새 확정 번역", "expected_translation": "다른 기준 번역"}
        with patch.object(translations, "AI_DIR", self.root):
            with self.assertRaisesRegex(ValueError, "translation_changed_since_editing"):
                translations.update_sentence_translation_review(payload, self.record["id"])
            self.assertEqual(self.path.read_bytes(), before)
            payload["expected_translation"] = self.record["translation"]
            result = translations.update_sentence_translation_review(payload, self.record["id"])
        self.assertEqual(result["record"]["human_translation"], "새 확정 번역")
        self.assertEqual(result["record"]["translation"], self.record["translation"])

    def test_current_source_annotations_are_bounded_and_never_confirm_missing_hash(self):
        records = [dict(self.record), {**self.record, "sentence_text_sha256": "b" * 64}, {**self.record, "sentence_id": "missing", "sentence_text_sha256": None}]
        with patch.object(translations, "resolve_segment_target", return_value={"text_raw": "source sentence"}) as resolve, \
            patch.object(translations, "sentence_units", return_value=[{"sentence_id": self.target["sentence_id"], "text_raw": "source sentence"}]):
            translations.annotate_current_sources(records)
        self.assertEqual([record["source_current"] for record in records], [True, False, False])
        self.assertEqual(resolve.call_count, 1)

    def test_unavailable_source_remains_unverified(self):
        records = [dict(self.record)]
        with patch.object(translations, "resolve_segment_target", side_effect=ValueError("index unavailable")):
            translations.annotate_current_sources(records)
        self.assertIsNone(records[0]["source_current"])


if __name__ == "__main__":
    unittest.main()
