from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SITE))

from check_ai_records_contracts import validate_record  # noqa: E402
from services import human_reviews as reviews  # noqa: E402
from services import human_review_batches as batches  # noqa: E402
from services.translation_notes import translation_hash, visible_notes  # noqa: E402
from services.sentence_translations import public_translation_record, export_sentence_translations_markdown  # noqa: E402


class HumanReviewImportContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="philo_human_review_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "run" / "ai"
        self.output = self.root / "operational" / "ai"
        self.source.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.feedback_path = self.root / "feedback.json"
        self.candidates_path = self.root / "candidates.json"
        self.gold_path = self.root / "goldset.json"
        self.transaction = self.root / "private" / "imports"
        self.record_id = str(uuid.uuid4())
        stamp = "2026-09-30T12:00:00+09:00"
        source = "Example source sentence."
        self.target = {
            "corpus_id": "nietzsche", "work_id": "demo", "variant_id": "", "segment_id": "p-0001",
            "sentence_id": "p-0001.s001", "sentence_text": source,
            "source_text_sha256": reviews.digest(source.encode()), "sentence_text_sha256": reviews.digest(source.encode()),
        }
        self.model = {
            "schema_version": 1, "record_type": "ai_sentence_translation", "id": self.record_id,
            "created_at": stamp, "generated_at": stamp, **{key: self.target[key] for key in reviews.TARGET_FIELDS},
            "target_id": self.target["sentence_id"], "target_url": "/work/nietzsche/demo#p-0001.s001",
            "source_text_sha256": self.target["source_text_sha256"], "sentence_text_sha256": self.target["sentence_text_sha256"],
            "source_text_excerpt": source, "source_language": "en", "model_provider": "synthetic", "model_name": "synthetic",
            "model_version": "synthetic", "model_runtime": "synthetic", "prompt_template_id": "sentence_translation_study_v5",
            "prompt_sha256": "a" * 64, "temperature": 0, "translation": "모델 후보.", "commentary": "",
            "literal_gloss": "", "key_terms": [], "cautions": [], "review_state": "generated", "citations": [{
                "target_url": "/work/nietzsche/demo#p-0001.s001", "label": "Synthetic sentence", "source_text_sha256": self.target["source_text_sha256"],
            }],
        }
        self.source_file = self.source / "nietzsche_sentence_translations.jsonl"
        self.source_file.write_bytes((json.dumps(self.model, ensure_ascii=False) + "\n").encode())
        self.output_file = self.output / self.source_file.name
        self.personal = b'{ "id": "unrelated-personal-record", "translation": "KEEP EXACT", "nested": {"x": 1} }\r\n\r\n'
        self.output_file.write_bytes(self.personal)
        self.notes = self.root / "operational" / "notes.jsonl"
        self.notes.write_bytes(b'{"id":"unrelated-note","note":"KEEP NOTE"}\n')
        self.candidate = {
            "id": "review-demo", "sample_label": "DEMO", "candidate_record_id": self.record_id,
            **{key: self.target[key] for key in reviews.TARGET_FIELDS},
            "source_text": source, "candidate_translation": self.model["translation"],
        }
        self.feedback = {
            "schema_version": 1, "evaluator": "synthetic-evaluator-private", "evaluated_at": stamp,
            "score_order": list(reviews.DIMENSIONS), "cases": [{
                "id": "review-demo", "sample_label": "DEMO", "candidate_record_id": self.record_id,
                "scores": dict.fromkeys(reviews.DIMENSIONS, 3), "reference_translation": "사람 확정문.",
                "notes": "synthetic-private-evaluation-notes",
            }],
        }
        cases = [{
            "id": "review-demo" if corpus == "nietzsche" else f"other-{corpus}", "corpus_id": corpus,
            "work_id": "demo", "variant_id": "", "segment_id": "p-0001", "sentence_id": "p-0001.s001",
            "source_text": source, "candidate_translation": "이전 후보.", "reference_translation": "",
            "candidate_record_id": str(uuid.uuid4()), "human_evaluation": {"status": "pending", "scores": {}},
        } for corpus in sorted(reviews.CORPORA)]
        self.gold = {
            "schema_version": 1, "rubric": {"dimensions": dict.fromkeys(reviews.DIMENSIONS, "synthetic"), "scale": {"min": 1, "max": 5}, "passing_score_per_dimension": 4},
            "cases": cases,
        }
        self.save_inputs()

    def save_inputs(self):
        self.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        self.candidates_path.write_bytes(reviews.json_bytes([self.candidate]))
        self.gold_path.write_bytes(reviews.json_bytes(self.gold))

    def snapshot(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}

    def run_import(self, apply=False):
        return reviews.import_human_reviews(
            self.feedback_path, self.candidates_path, self.source, self.output, self.gold_path, self.transaction,
            apply=apply, target_resolver=lambda *args: deepcopy(self.target),
            record_validator=lambda record: validate_record(record, Path("synthetic"), 0),
        )

    def test_dry_run_creates_nothing_and_rejects_model_generation(self):
        before = self.snapshot()
        with patch("services.sentence_translations.call_llama_server", side_effect=AssertionError("model must not be called")):
            result = self.run_import()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["changed_files"], 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.transaction.exists())

    def test_apply_preserves_originals_private_lines_and_repeated_apply_is_no_op(self):
        source_before = self.source_file.read_bytes()
        note_before = self.notes.read_bytes()
        result = self.run_import(apply=True)
        self.assertEqual(result["new_operational_records"], 1)
        self.assertEqual(result["passing_model_candidates"], 0)
        self.assertTrue(self.output_file.read_bytes().startswith(self.personal))
        record = reviews.read_records(self.output_file.read_bytes())[-1]
        self.assertEqual(reviews.immutable_model(record), reviews.immutable_model(self.model))
        self.assertEqual(record["human_translation"], self.feedback["cases"][0]["reference_translation"])
        self.assertEqual(self.source_file.read_bytes(), source_before)
        self.assertEqual(self.notes.read_bytes(), note_before)
        self.assertEqual(len(list(self.transaction.glob("backup-*"))), 1)
        before = self.snapshot()
        self.assertEqual(self.run_import()["status"], "no_op")
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")
        self.assertEqual(self.snapshot(), before)

    def test_re_evaluation_preserves_record_and_goldset_history(self):
        original_feedback = deepcopy(self.feedback)
        self.run_import(apply=True)
        prior = reviews.read_records(self.output_file.read_bytes())[-1]
        previous_gold = json.loads(self.gold_path.read_bytes())
        self.feedback["evaluated_at"] = "2026-10-01T12:00:00+09:00"
        self.feedback["cases"][0]["scores"]["fidelity"] = 4
        self.feedback["cases"][0]["reference_translation"] = "새 사람 확정문."
        self.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        self.run_import(apply=True)
        record = reviews.read_records(self.output_file.read_bytes())[-1]
        self.assertEqual(record["human_evaluation_history"][0]["human_evaluation"], prior["human_evaluation"])
        self.assertEqual(reviews.immutable_model(record), reviews.immutable_model(self.model))
        self.assertTrue(self.output_file.read_bytes().startswith(self.personal))
        gold = json.loads(self.gold_path.read_bytes())
        case = next(case for case in gold["cases"] if case["id"] == "review-demo")
        self.assertEqual(len(case["evaluation_history"]), 2)
        self.assertEqual(case["evaluation_history"][-1]["human_evaluation"], prior["human_evaluation"])
        self.assertEqual([case for case in gold["cases"] if case["id"] != "review-demo"], [case for case in previous_gold["cases"] if case["id"] != "review-demo"])
        self.feedback_path.write_bytes(reviews.json_bytes(original_feedback))
        before = self.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "stale_human_review"):
            self.run_import(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_scores_uuid_selection_and_publication_are_read_only(self):
        original_feedback, original_candidate, original_gold = deepcopy(self.feedback), deepcopy(self.candidate), deepcopy(self.gold)
        changes = [
            lambda: self.feedback["cases"][0]["scores"].update(fidelity=True),
            lambda: self.feedback["cases"][0]["scores"].update(fidelity=0),
            lambda: self.feedback["cases"][0]["scores"].update(fidelity=6),
            lambda: self.feedback["cases"][0]["scores"].update(fidelity=4.0),
            lambda: self.feedback["cases"][0].update(candidate_record_id="invalid"),
            lambda: self.feedback["cases"][0].update(candidate_record_id=str(uuid.uuid4())),
            lambda: self.candidate.update(source_text="Different source."),
            lambda: self.gold.update(model_name="forbidden-runtime-metadata"),
            lambda: self.gold.update(description="x" * 65536),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.feedback, self.candidate, self.gold = deepcopy(original_feedback), deepcopy(original_candidate), deepcopy(original_gold)
                change()
                self.save_inputs()
                before = self.snapshot()
                with self.assertRaises(reviews.HumanReviewError):
                    self.run_import()
                self.assertEqual(self.snapshot(), before)

    def test_source_hash_and_operational_model_conflicts_are_rejected(self):
        for kind in ("source_hash", "model"):
            with self.subTest(kind=kind):
                bad = deepcopy(self.model)
                bad["source_text_sha256" if kind == "source_hash" else "translation"] = "b" * 64 if kind == "source_hash" else "changed model"
                path = self.source_file if kind == "source_hash" else self.output_file
                path.write_bytes((json.dumps(bad) + "\n").encode())
                before = self.snapshot()
                with self.assertRaises(reviews.HumanReviewError):
                    self.run_import()
                self.assertEqual(self.snapshot(), before)
                self.source_file.write_bytes((json.dumps(self.model) + "\n").encode())

    def failing_writer(self, target):
        original = reviews.atomic_bytes
        failures = []
        def write(path, value):
            if target(path) and not failures:
                failures.append(True)
                raise OSError("synthetic write failure")
            original(path, value)
        return write

    def test_failed_target_replace_rolls_back_exact_bytes_and_can_retry(self):
        original = {path: path.read_bytes() for path in (self.output_file, self.gold_path, self.source_file, self.notes)}
        with patch.object(reviews, "atomic_bytes", side_effect=self.failing_writer(lambda path: path == self.gold_path)):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_rolled_back"):
                self.run_import(apply=True)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        self.assertFalse((self.transaction / "pending").exists())
        self.assertEqual(self.run_import(apply=True)["status"], "applied")

    def test_failed_backup_prepare_leaves_targets_untouched_and_can_retry(self):
        before = self.output_file.read_bytes(), self.gold_path.read_bytes()
        with patch.object(reviews, "atomic_bytes", side_effect=self.failing_writer(lambda path: path.name.endswith(".after"))):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_rolled_back"):
                self.run_import(apply=True)
        self.assertEqual((self.output_file.read_bytes(), self.gold_path.read_bytes()), before)
        self.assertFalse((self.transaction / "pending").exists())
        self.assertEqual(self.run_import(apply=True)["status"], "applied")

    def leave_interrupted_import(self):
        original_recover = reviews.recover_pending
        def recover(pending, *args, **kwargs):
            if pending.exists():
                raise OSError("simulate killed process during rollback")
            return original_recover(pending, *args, **kwargs)
        with patch.object(reviews, "atomic_bytes", side_effect=self.failing_writer(lambda path: path == self.gold_path)), patch.object(reviews, "recover_pending", side_effect=recover):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_recovery_required"):
                self.run_import(apply=True)
        self.assertTrue((self.transaction / "pending" / "manifest.json").is_file())

    def test_interrupted_import_requires_apply_then_recovers_and_resumes(self):
        self.leave_interrupted_import()
        before = self.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "requires_apply"):
            self.run_import()
        self.assertEqual(self.snapshot(), before)
        result = self.run_import(apply=True)
        self.assertTrue(result["recovered_previous_attempt"])
        self.assertEqual(result["status"], "applied")
        self.assertTrue(self.output_file.read_bytes().startswith(self.personal))
        self.assertEqual(len(reviews.read_records(self.output_file.read_bytes())), 2)

    def test_interrupted_import_never_overwrites_external_changes_or_different_feedback(self):
        self.leave_interrupted_import()
        self.feedback["cases"][0]["scores"]["fidelity"] = 4
        self.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        before = self.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "needs_original_input"):
            self.run_import(apply=True)
        self.assertEqual(self.snapshot(), before)
        self.feedback["cases"][0]["scores"]["fidelity"] = 3
        self.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        with self.output_file.open("ab") as handle:
            handle.write(b'{"id":"new-external-private-record"}\n')
        before = self.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "changed_externally"):
            self.run_import(apply=True)
        self.assertEqual(self.snapshot(), before)

    def test_missing_preparation_manifest_is_safely_archived_before_retry(self):
        (self.transaction / "pending").mkdir(parents=True)
        result = self.run_import(apply=True)
        self.assertTrue(result["recovered_previous_attempt"])
        self.assertEqual(result["status"], "applied")

    def test_cli_errors_do_not_print_private_input(self):
        self.feedback["cases"][0]["scores"]["fidelity"] = True
        self.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        before = self.snapshot()
        result = subprocess.run([
            sys.executable, "-B", "-X", "utf8", str(SITE / "scripts" / "apply_translation_human_review.py"),
            "--feedback", str(self.feedback_path), "--candidates", str(self.candidates_path),
            "--candidate-ai-dir", str(self.source), "--goldset", str(self.gold_path), "--ai-dir", str(self.output),
            "--transaction-dir", str(self.transaction),
        ], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "human review import failed: invalid_scores")
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.snapshot(), before)

    def test_cli_rejects_backup_directory_in_public_project_tree(self):
        rejected = SITE / "data" / "human-review-backups-public-contract"
        existed = rejected.exists()
        before = self.snapshot()
        result = subprocess.run([
            sys.executable, "-B", "-X", "utf8", str(SITE / "scripts" / "apply_translation_human_review.py"),
            "--feedback", str(self.feedback_path), "--candidates", str(self.candidates_path),
            "--transaction-dir", str(rejected), "--apply",
        ], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "human review import failed: transaction_directory_must_be_private")
        self.assertEqual(result.stdout, "")
        self.assertEqual(rejected.exists(), existed)
        self.assertEqual(self.snapshot(), before)


class FiveDimensionReviewContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = HumanReviewImportContracts("test_dry_run_creates_nothing_and_rejects_model_generation")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.root / "private" / "five-dimension.json"
        self.case = {
            "id": "review-demo", "candidate_record_id": self.fixture.record_id,
            "sentence_text_sha256": self.fixture.target["sentence_text_sha256"],
            "candidate_translation_sha256": reviews.digest(self.fixture.model["translation"].encode("utf-8")),
            "decision": "confirmed", "evaluator": "Original AI evaluator", "evaluator_kind": "ai",
            "evaluated_date": "2026-10-02", "evaluated_at": None,
            "scores": {**dict.fromkeys(batches.DIMENSIONS[:-1], 4), "note_accuracy": None},
            "reference_translation": "새 확정문.", "note_action": "not_applicable", "translation_notes": [],
            "notes": "Submitted rationale; not an independent human score.",
        }
        self.feedback = {"schema_version": 2, "score_order": list(batches.DIMENSIONS), "cases": [self.case]}
        self.save()

    def save(self):
        self.fixture.feedback_path.write_bytes(reviews.json_bytes(self.feedback))
        self.fixture.candidates_path.write_bytes(reviews.json_bytes([{"case_id": "review-demo", "record": self.fixture.model}]))
        self.fixture.source_file.write_bytes((json.dumps(self.fixture.model, ensure_ascii=False) + "\n").encode("utf-8"))

    def run_import(self, apply=False):
        return batches.import_review_batch(
            self.fixture.feedback_path, self.fixture.candidates_path, self.fixture.source, self.store,
            self.fixture.transaction, apply=apply, target_resolver=lambda *args: deepcopy(self.fixture.target),
            record_validator=lambda record: validate_record(record, Path("synthetic"), 0),
        )

    def with_candidate_notes(self):
        note = {"source_span": "Example source", "note": "원문의 표현을 그대로 설명한다."}
        self.fixture.model.update(
            translation_notes=[note], note_source_text=self.fixture.target["sentence_text"],
            commentary_translation_sha256=translation_hash(self.fixture.model["translation"]),
        )
        self.case["scores"]["note_accuracy"] = 4
        self.case["note_action"] = "keep"
        self.save()
        return note

    def run_publication(self, apply=False, case_ids=None):
        return batches.publish_review_cases(
            self.store, [self.case["id"]] if case_ids is None else case_ids,
            self.fixture.source, self.fixture.output, self.fixture.transaction / "adoption",
            approved_by="Actual adopter", adopted_at="2026-10-04T12:00:00+09:00", apply=apply,
            target_resolver=lambda *args: deepcopy(self.fixture.target),
            record_validator=lambda record: validate_record(record, Path("synthetic"), 0),
        )

    def test_explicit_adoption_preserves_model_and_date_only_scores_and_publishes_bound_notes(self):
        self.with_candidate_notes()
        self.case.update(note_action="replace", translation_notes=[
            {"source_span": span, "note": note} for span, note in [
                ("Example", "주어를 설명하는 서술보어이다."),
                ("source", "괄호 부연을 한 번으로 옮긴다."),
                ("sentence.", "다루다의 뜻을 보존한다."),
            ]
        ])
        self.save()
        self.run_import(apply=True)
        preserved = {p: p.read_bytes() for p in (self.store, self.fixture.source_file, self.fixture.gold_path, self.fixture.notes)}
        before = self.fixture.snapshot()
        with patch("services.sentence_translations.call_llama_server", side_effect=AssertionError("no generation")):
            self.assertEqual(self.run_publication()["status"], "ready")
            self.assertEqual(self.fixture.snapshot(), before)
            self.assertEqual(self.run_publication(apply=True)["operational_records_changed"], 1)
        self.assertEqual({p: p.read_bytes() for p in preserved}, preserved)
        raw = self.fixture.output_file.read_bytes()
        self.assertTrue(raw.startswith(self.fixture.personal))
        record = reviews.read_records(raw)[-1]
        self.assertEqual(reviews.immutable_model(record), reviews.immutable_model(self.fixture.model))
        self.assertEqual(record["human_evaluation_v2"], self.case)
        self.assertIsNone(record["human_evaluation_v2"]["evaluated_at"])
        self.assertEqual(record["reviewed_by"], "Actual adopter")
        self.assertEqual(record["reviewed_at"], "2026-10-04T12:00:00+09:00")
        self.assertEqual(visible_notes(record)[2], self.case["translation_notes"])
        public = public_translation_record(record)
        self.assertEqual(public["translation_notes"], self.case["translation_notes"])
        self.assertNotIn("human_evaluation_v2", public)
        self.assertNotIn("human_translation_notes", public)
        projected_again = public_translation_record(public)
        self.assertEqual(projected_again["translation_notes"], public["translation_notes"])
        markdown = export_sentence_translations_markdown([public])
        for note in self.case["translation_notes"]:
            self.assertIn(note["note"], markdown)
        self.assertEqual(self.run_publication(apply=True)["status"], "no_op")
        self.assertEqual(self.fixture.output_file.read_bytes(), raw)

    def test_later_public_note_guard_does_not_erase_original_note_score(self):
        from services import translation_source_checks as source_rules
        original_note = self.with_candidate_notes()
        self.case.update(note_action="replace", translation_notes=[
            {"source_span": "Example source", "note": "수정된 원문 설명을 확정 번역에 연결한다."}
        ])
        self.save()
        rules_path = self.fixture.root / "checks.json"
        rule = {**{key: self.fixture.target[key] for key in ("corpus_id", "work_id", "variant_id", "sentence_id", "sentence_text_sha256")},
                "lexical_evidence": [], "note_checks": [{"source_span": "Example source", "forbidden_note_assertions": [original_note["note"]],
                                                         "explanation": "이 원본 노트는 이후 검사에서 공개를 보류한다."}]}
        rules_path.write_bytes(reviews.json_bytes({"schema_version": 1, "rules": [rule]}))
        model_before = deepcopy(self.fixture.model)
        with patch.object(source_rules, "CHECKS_FILE", rules_path):
            self.assertEqual(visible_notes(self.fixture.model)[0], "notes_review_required")
            self.assertEqual(visible_notes(self.fixture.model)[2], [])
            self.assertEqual(self.run_import(apply=True)["changed_cases"], 1)
            entry = json.loads(self.store.read_bytes())["cases"][0]
            self.assertEqual(entry["review"]["scores"]["note_accuracy"], 4)
            self.assertEqual(entry["resolved_translation_notes"], self.case["translation_notes"])
            self.assertEqual(self.run_publication(apply=True)["operational_records_changed"], 1)
            adopted = reviews.read_records(self.fixture.output_file.read_bytes())[-1]
            public = public_translation_record(adopted)
            self.assertEqual(public["commentary_status"], "current")
            self.assertEqual(public["translation_notes"], self.case["translation_notes"])
            self.assertEqual(adopted["translation_notes"], [original_note])
            self.assertEqual(visible_notes(self.fixture.model)[0], "notes_review_required")
        self.assertEqual(self.fixture.model, model_before)
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")

    def test_original_note_binding_is_required_without_an_optional_record_validator(self):
        self.with_candidate_notes()
        for binding in [{"note_source_text": "Wrong original source"}, {"commentary_translation_sha256": "0" * 64}]:
            with self.subTest(binding=binding):
                saved_model = deepcopy(self.fixture.model)
                self.fixture.model.update(binding)
                self.save()
                before = self.fixture.snapshot()
                with self.assertRaisesRegex(reviews.HumanReviewError, "candidate_note_binding_mismatch"):
                    batches.import_review_batch(self.fixture.feedback_path, self.fixture.candidates_path, self.fixture.source, self.store,
                                                self.fixture.transaction, target_resolver=lambda *args: deepcopy(self.fixture.target))
                self.assertEqual(self.fixture.snapshot(), before)
                self.fixture.model = saved_model
        self.save()

    def test_adoption_needs_explicit_case_and_rejects_held_without_creating_files(self):
        self.case.update(decision="held", reference_translation="", provisional_translation="보류 수정안.")
        self.save()
        self.run_import(apply=True)
        before = self.fixture.snapshot()
        for ids, code in [([], "explicit_adoption_cases_required"), ([self.case["id"]] * 2, "duplicate_adoption_case"), (["absent"], "selected_case_not_found"), ([self.case["id"]], "held_review_cannot_be_adopted")]:
            with self.subTest(ids=ids):
                with self.assertRaisesRegex(reviews.HumanReviewError, code):
                    self.run_publication(apply=True, case_ids=ids)
                self.assertEqual(self.fixture.snapshot(), before)

    def test_adoption_rejects_live_source_model_and_output_conflicts_read_only(self):
        self.run_import(apply=True)
        original_source = self.fixture.source_file.read_bytes()
        original_output = self.fixture.output_file.read_bytes()
        for conflict in ("source", "model", "output"):
            with self.subTest(conflict=conflict):
                target = deepcopy(self.fixture.target)
                model = deepcopy(self.fixture.model)
                if conflict == "source":
                    self.fixture.target["sentence_text_sha256"] = "b" * 64
                elif conflict == "model":
                    model["commentary"] = "changed model"
                    self.fixture.source_file.write_bytes((json.dumps(model) + "\n").encode())
                else:
                    model["translation"] = "다른 원본 모델."
                    self.fixture.output_file.write_bytes(original_output + (json.dumps(model) + "\n").encode())
                before = self.fixture.snapshot()
                with self.assertRaises(reviews.HumanReviewError):
                    self.run_publication(apply=True)
                self.assertEqual(self.fixture.snapshot(), before)
                self.fixture.target = target
                self.fixture.source_file.write_bytes(original_source)
                self.fixture.output_file.write_bytes(original_output)

    def test_replayed_adoption_never_overwrites_manual_edits_and_hides_stale_notes(self):
        self.with_candidate_notes()
        self.run_import(apply=True)
        self.run_publication(apply=True)
        records = reviews.read_records(self.fixture.output_file.read_bytes())
        record = records[-1]
        record.update(human_translation="Reader에서 나중에 수정한 번역.", human_translation_updated_at="2026-10-05T12:00:00+09:00")
        self.fixture.output_file.write_bytes(reviews.changed_record_bytes(self.fixture.output_file.read_bytes(), records))
        validate_record(record, Path("synthetic"), 0)
        self.assertEqual(visible_notes(record), ("translation_changed", "", []))
        self.assertEqual(public_translation_record(record)["translation_notes"], [])
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "operational_review_changed_externally"):
            self.run_publication(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)
        record["sentence_text_sha256"] = "b" * 64
        record["human_translation"] = self.case["reference_translation"]
        self.assertEqual(visible_notes(record), ("source_changed", "", []))

    def test_adoption_revision_preserves_history_and_invalid_bindings_fail_validation(self):
        self.with_candidate_notes()
        self.run_import(apply=True)
        self.run_publication(apply=True)
        old = reviews.read_records(self.fixture.output_file.read_bytes())[-1]
        self.case.update(evaluated_date="2026-10-03", reference_translation="새로 확정한 번역.")
        self.save()
        self.run_import(apply=True)
        self.run_publication(apply=True)
        record = reviews.read_records(self.fixture.output_file.read_bytes())[-1]
        self.assertEqual(record["human_evaluation_history"][0]["human_evaluation_v2"], old["human_evaluation_v2"])
        self.assertNotIn("human_evaluation_v2", public_translation_record(record)["human_evaluation_history"][0])
        for field in ("translation_sha256", "sentence_text_sha256", "source_text"):
            broken = deepcopy(record)
            broken["human_translation_notes"][field] = "bad binding"
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_record(broken, Path("synthetic"), 0)

    def test_failed_adoption_rolls_back_exact_bytes_and_retry_is_idempotent(self):
        self.run_import(apply=True)
        original = reviews.atomic_bytes
        before = self.fixture.output_file.read_bytes()
        failures = []
        def fail(path, value):
            if path == self.fixture.output_file and not failures:
                failures.append(True)
                raise OSError("synthetic adoption failure")
            original(path, value)
        with patch.object(reviews, "atomic_bytes", side_effect=fail):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_rolled_back"):
                self.run_publication(apply=True)
        self.assertEqual(self.fixture.output_file.read_bytes(), before)
        self.assertEqual(self.run_publication(apply=True)["status"], "applied")
        self.assertEqual(self.run_publication(apply=True)["status"], "no_op")

    def test_dry_run_creates_nothing_and_calls_no_model(self):
        before = self.fixture.snapshot()
        with patch("services.sentence_translations.call_llama_server", side_effect=AssertionError("no generation")):
            result = self.run_import()
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(result["notes_not_applicable"], 1)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_apply_keeps_legacy_goldset_original_model_private_records_and_provenance(self):
        preserved = {p: p.read_bytes() for p in (self.fixture.gold_path, self.fixture.output_file, self.fixture.source_file, self.fixture.notes)}
        result = self.run_import(apply=True)
        self.assertEqual(result["operational_records_changed"], 0)
        entry = json.loads(self.store.read_bytes())["cases"][0]
        self.assertEqual(entry["review"]["evaluator"], self.case["evaluator"])
        self.assertEqual(entry["review"]["evaluator_kind"], "ai")
        self.assertIsNone(entry["review"]["evaluated_at"])
        self.assertIsNone(entry["review"]["scores"]["note_accuracy"])
        self.assertEqual({p: p.read_bytes() for p in preserved}, preserved)
        before = self.fixture.snapshot()
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")
        self.assertEqual(self.fixture.snapshot(), before)

    def test_held_draft_keeps_scores_and_proposed_notes_without_a_published_binding(self):
        self.with_candidate_notes()
        self.case.update(decision="held", reference_translation="", provisional_translation="잠정 수정안(")
        self.save()
        result = self.run_import(apply=True)
        entry = json.loads(self.store.read_bytes())["cases"][0]
        self.assertEqual(result["held"], 1)
        self.assertEqual(entry["review"]["provisional_translation"], "잠정 수정안(")
        self.assertEqual(entry["review"]["reference_translation"], "")
        self.assertIsNone(entry["note_binding"])
        self.case["reference_translation"] = "must not be adopted"
        self.save()
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "held_review_has_reference"):
            self.run_import(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_notes_bind_to_review_translation_and_original_source_without_changing_model(self):
        original_note = self.with_candidate_notes()
        self.case.update(note_action="replace", translation_notes=[{"source_span": "Example source sentence.", "note": "수정 번역에 연결된 원문 설명이다."}])
        self.save()
        original_model = self.fixture.source_file.read_bytes()
        self.run_import(apply=True)
        entry = json.loads(self.store.read_bytes())["cases"][0]
        self.assertEqual(entry["resolved_translation_notes"], self.case["translation_notes"])
        self.assertEqual(entry["note_binding"], {"sentence_text_sha256": self.case["sentence_text_sha256"], "translation_sha256": translation_hash(self.case["reference_translation"])})
        self.assertEqual(self.fixture.source_file.read_bytes(), original_model)
        self.assertEqual(self.fixture.model["translation_notes"], [original_note])

    def test_adopt_new_notes_without_model_notes_preserves_not_applicable_score(self):
        self.case.update(note_action="replace", translation_notes=[
            {"source_span": "Example source", "note": "확정 번역에 새로 연결한 원문 설명이다."}
        ])
        self.save()
        originals = {p: p.read_bytes() for p in (self.fixture.source_file, self.fixture.gold_path, self.fixture.notes)}
        before = self.fixture.snapshot()
        with patch("services.sentence_translations.call_llama_server", side_effect=AssertionError("no generation")):
            self.assertEqual(self.run_import()["status"], "ready")
            self.assertEqual(self.fixture.snapshot(), before)
            self.run_import(apply=True)
            entry = json.loads(self.store.read_bytes())["cases"][0]
            self.assertIsNone(entry["review"]["scores"]["note_accuracy"])
            self.assertEqual(entry["resolved_translation_notes"], self.case["translation_notes"])
            self.assertIsNotNone(entry["note_binding"])
            self.assertEqual(self.run_publication()["status"], "ready")
            self.assertEqual(self.run_publication(apply=True)["operational_records_changed"], 1)
        record = reviews.read_records(self.fixture.output_file.read_bytes())[-1]
        validate_record(record, Path("synthetic"), 0)
        self.assertIsNone(record["human_evaluation_v2"]["scores"]["note_accuracy"])
        self.assertEqual(reviews.immutable_model(record), reviews.immutable_model(self.fixture.model))
        public = public_translation_record(record)
        self.assertEqual(public["commentary_status"], "current")
        self.assertEqual(public["translation_notes"], self.case["translation_notes"])
        self.assertIn(self.case["translation_notes"][0]["note"], export_sentence_translations_markdown([public]))
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")
        self.assertEqual(self.run_publication(apply=True)["status"], "no_op")
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)

    def test_adopting_new_notes_cannot_create_a_model_note_score(self):
        self.case.update(note_action="replace", translation_notes=[
            {"source_span": "Example source", "note": "새로 채택한 설명이다."}
        ])
        self.case["scores"]["note_accuracy"] = 5
        self.save()
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "candidate_note_applicability_mismatch"):
            self.run_import(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_bad_scores_null_boolean_missing_and_applicability_are_rejected_read_only(self):
        original = deepcopy(self.case)
        changes = [
            lambda: self.case["scores"].update(logic=True),
            lambda: self.case["scores"].update(logic=0),
            lambda: self.case["scores"].update(logic=6),
            lambda: self.case["scores"].update(logic=4.0),
            lambda: self.case["scores"].update(logic=None),
            lambda: self.case["scores"].pop("logic"),
            lambda: self.case["scores"].update(note_accuracy=5),
            lambda: self.case.update(note_action="keep"),
            lambda: self.case.update(evaluated_date="2026-02-30"),
            lambda: self.case.update(evaluated_at="2026-10-03T12:00:00+09:00"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.case.clear()
                self.case.update(deepcopy(original))
                change()
                self.save()
                before = self.fixture.snapshot()
                with self.assertRaises(reviews.HumanReviewError):
                    self.run_import(apply=True)
                self.assertEqual(self.fixture.snapshot(), before)
        self.case.clear()
        self.case.update(deepcopy(original))
        self.with_candidate_notes()
        self.case.update(note_action="not_applicable")
        self.case["scores"]["note_accuracy"] = None
        self.save()
        with self.assertRaisesRegex(reviews.HumanReviewError, "candidate_note_applicability_mismatch"):
            self.run_import()

    def test_uuid_translation_and_live_source_hash_mismatches_are_rejected(self):
        original = deepcopy(self.case)
        for field, value in [("candidate_record_id", str(uuid.uuid4())), ("sentence_text_sha256", "b" * 64), ("candidate_translation_sha256", "b" * 64)]:
            with self.subTest(field=field):
                self.case.update(deepcopy(original))
                self.case[field] = value
                self.save()
                before = self.fixture.snapshot()
                with self.assertRaises(reviews.HumanReviewError):
                    self.run_import(apply=True)
                self.assertEqual(self.fixture.snapshot(), before)

    def test_unquoted_leaked_and_oversized_notes_are_rejected(self):
        self.with_candidate_notes()
        self.case["note_action"] = "replace"
        for notes in [
            [{"source_span": "not in the source", "note": "원문에 없는 인용이다."}],
            [{"source_span": "Example", "note": "프롬프트 지침에 따라 설명했다."}],
            [{"source_span": "Example", "note": "가" * 1501}],
            [{"source_span": "Example", "note": "설명이다."}] * 4,
        ]:
            with self.subTest(notes=notes[0]["source_span"]):
                self.case["translation_notes"] = notes
                self.save()
                before = self.fixture.snapshot()
                with self.assertRaisesRegex(reviews.HumanReviewError, "invalid_review_translation_notes"):
                    self.run_import(apply=True)
                self.assertEqual(self.fixture.snapshot(), before)

    def test_re_evaluation_history_and_older_or_ambiguous_date_only_review(self):
        self.run_import(apply=True)
        previous = json.loads(self.store.read_bytes())["cases"][0]
        self.case["reference_translation"] = "두 번째 확정문."
        self.save()
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "same_day_revision_needs_timestamp"):
            self.run_import(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)
        self.case["evaluated_date"] = "2026-10-03"
        self.save()
        self.run_import(apply=True)
        entry = json.loads(self.store.read_bytes())["cases"][0]
        self.assertEqual(entry["evaluation_history"], [previous])
        self.case["evaluated_date"] = "2026-10-01"
        self.save()
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "stale_human_review"):
            self.run_import(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_failed_ledger_replace_rolls_back_then_retry_is_idempotent(self):
        original = reviews.atomic_bytes
        failures = []
        def fail(path, value):
            if path == self.store and not failures:
                failures.append(True)
                raise OSError("synthetic ledger disk failure")
            original(path, value)
        originals = {p: p.read_bytes() for p in (self.fixture.gold_path, self.fixture.output_file, self.fixture.source_file)}
        with patch.object(reviews, "atomic_bytes", side_effect=fail):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_rolled_back"):
                self.run_import(apply=True)
        self.assertFalse(self.store.exists())
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        self.assertEqual(self.run_import(apply=True)["status"], "applied")
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")

    def test_duplicate_uuid_corrupted_store_and_input_alias_are_rejected(self):
        duplicate = deepcopy(self.case)
        duplicate["id"] = "another-case"
        self.feedback["cases"].append(duplicate)
        self.save()
        with self.assertRaisesRegex(reviews.HumanReviewError, "duplicate_candidate_uuid"):
            self.run_import()
        self.feedback["cases"].pop()
        self.save()
        self.run_import(apply=True)
        store = json.loads(self.store.read_bytes())
        store["cases"][0]["review"]["candidate_translation_sha256"] = "b" * 64
        self.store.write_bytes(reviews.json_bytes(store))
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "invalid_review_store"):
            self.run_import(apply=True)
        self.assertEqual(self.fixture.snapshot(), before)
        self.store = self.fixture.candidates_path
        with self.assertRaisesRegex(reviews.HumanReviewError, "input_target_alias"):
            self.run_import()

    def test_cli_rejects_public_ledger_and_preserves_private_error_output(self):
        before = self.fixture.snapshot()
        args = [sys.executable, "-B", "-X", "utf8", str(SITE / "scripts" / "apply_translation_human_review.py"),
                "--feedback", str(self.fixture.feedback_path), "--candidates", str(self.fixture.candidates_path),
                "--candidate-ai-dir", str(self.fixture.source), "--transaction-dir", str(self.fixture.transaction)]
        result = subprocess.run(args + ["--review-store", str(SITE / "data/public-review-contract.json"), "--apply"], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "human review import failed: review_store_must_be_private")
        for flag, value, error in [
            ("--goldset", self.fixture.gold_path, "review_store_cannot_change_legacy_goldset"),
            ("--ai-dir", self.fixture.output, "review_store_cannot_change_operational_records"),
        ]:
            result = subprocess.run(args + ["--review-store", str(self.store), flag, str(value)], capture_output=True, text=True, encoding="utf-8", check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.strip(), "human review import failed: " + error)
            self.assertEqual(self.fixture.snapshot(), before)
        self.case["scores"]["logic"] = True
        self.save()
        result = subprocess.run(args + ["--review-store", str(self.store)], capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "human review import failed: invalid_batch_scores")
        self.assertEqual(result.stdout, "")
        self.assertEqual(set(self.fixture.snapshot()), set(before))

    def test_exact_timestamps_order_revisions_and_date_only_input_never_invents_time(self):
        self.case["evaluated_at"] = "2026-10-02T12:00:00+09:00"
        self.save()
        self.run_import(apply=True)
        self.case.update(evaluated_at="2026-10-02T04:00:00+00:00", reference_translation="시각이 확인된 새 확정문.")
        self.save()
        self.run_import(apply=True)
        entry = json.loads(self.store.read_bytes())["cases"][0]
        self.assertEqual(len(entry["evaluation_history"]), 1)
        self.case.update(evaluated_at="2026-10-02T11:00:00+09:00", reference_translation="더 오래된 확정문.")
        self.save()
        with self.assertRaisesRegex(reviews.HumanReviewError, "stale_human_review"):
            self.run_import(apply=True)

    def test_existing_four_dimension_record_evaluation_is_preserved(self):
        evaluation = {"status": "evaluated", "evaluator": "legacy reviewer", "evaluated_at": "2026-09-30T12:00:00+09:00", "scores": dict.fromkeys(reviews.DIMENSIONS, 3), "notes": "legacy rationale"}
        self.fixture.model = reviews.reviewed_record(self.fixture.model, evaluation, "기존 4영역 확정문.")
        self.save()
        original = self.fixture.source_file.read_bytes()
        self.run_import(apply=True)
        self.assertEqual(self.fixture.source_file.read_bytes(), original)
        self.assertEqual(reviews.read_records(original)[0]["human_evaluation"], evaluation)
        self.assertEqual(json.loads(self.store.read_bytes())["cases"][0]["review"]["scores"], self.case["scores"])

    def test_interrupted_batch_requires_original_input_then_recovers(self):
        original_write = reviews.atomic_bytes
        original_recover = reviews.recover_pending
        def write(path, value):
            if path == self.store:
                raise OSError("simulate killed ledger writer")
            original_write(path, value)
        def recover(pending, *args, **kwargs):
            if pending.exists():
                raise OSError("simulate interrupted recovery")
            return original_recover(pending, *args, **kwargs)
        with patch.object(reviews, "atomic_bytes", side_effect=write), patch.object(reviews, "recover_pending", side_effect=recover):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_recovery_required"):
                self.run_import(apply=True)
        before = self.fixture.snapshot()
        with self.assertRaisesRegex(reviews.HumanReviewError, "requires_apply"):
            self.run_import()
        self.assertEqual(self.fixture.snapshot(), before)
        self.case["notes"] = "Different input must not recover another transaction."
        self.save()
        with self.assertRaisesRegex(reviews.HumanReviewError, "needs_original_input"):
            self.run_import(apply=True)
        self.case["notes"] = "Submitted rationale; not an independent human score."
        self.save()
        result = self.run_import(apply=True)
        self.assertTrue(result["recovered_previous_attempt"])
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.run_import(apply=True)["status"], "no_op")


if __name__ == "__main__":
    unittest.main(verbosity=1)
