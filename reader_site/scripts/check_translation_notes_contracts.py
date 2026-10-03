from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlencode
from unittest.mock import patch

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from services import sentence_translations as translations
from services.translation_notes import grounded_notes, translation_hash
from services.translation_metrics import capture_model_usage, begin_model_call, finish_model_call, usage_summary
from scripts.check_sentence_translation_contracts import synthetic_sentence_target, passing_pipeline_output, critic_issue
from scripts.check_ai_records_contracts import validate_record
from services.translation_source_checks import source_meaning_issues, source_evidence_text, source_note_issues


def benchmark_sentence_target(case):
    """Use committed excerpts here; source-aware regression checks validate restored corpora."""
    source = case["source_text"]
    fingerprint = translations.sha256_text(source)
    if fingerprint != case["source_text_sha256"]:
        raise AssertionError("benchmark source changed")
    target_url = f"/work/{quote(case['corpus_id'], safe='')}/{quote(case['work_id'], safe='')}"
    if case["variant_id"]:
        target_url += "?" + urlencode({"variant": case["variant_id"]})
    target_url += "#" + quote(case["sentence_id"], safe="")
    return {
        **synthetic_sentence_target(),
        **{key: case[key] for key in ["corpus_id", "work_id", "variant_id", "segment_id", "sentence_id"]},
        "target_id": case["sentence_id"], "target_url": target_url,
        "label": case["sentence_id"], "work_title": case["work_id"],
        "source_text": source, "sentence_text": source,
        "source_text_preview": source[:220], "source_text_chars": len(source), "sentence_text_chars": len(source),
        "source_text_sha256": fingerprint, "sentence_text_sha256": fingerprint,
    }


class TranslationNotesContracts(unittest.TestCase):
    def record(self):
        target = synthetic_sentence_target()
        output = passing_pipeline_output("삶은 힘에의 의지다.")
        output["translation_notes"] = [{"source_span": "Wille zur Macht", "note": "힘에의 의지는 원문의 명사구에 대응한다."}]
        return translations.build_record(target, translations.build_sentence_prompt_bundle(target), output)

    def test_current_notes_and_exact_source_binding(self):
        record = self.record()
        validate_record(record, Path("fixture"), 1)
        public = translations.public_translation_record(record)
        self.assertEqual(public["commentary_status"], "current")
        self.assertTrue(public["commentary"])
        self.assertEqual(record["commentary_translation_sha256"], translation_hash(record["translation"]))

    def test_human_edit_invalidates_api_and_exports_without_erasing_history(self):
        record = self.record()
        original_commentary = record["commentary"]
        with tempfile.TemporaryDirectory() as directory, patch.object(translations, "AI_DIR", Path(directory)):
            path = translations.ai_record_path("nietzsche")
            translations.append_record(path, record)
            changed = translations.update_sentence_translation_review({"corpus_id":"nietzsche", "review_state":"reviewed", "human_translation":"삶은 다른 확정문이다."}, record["id"])["record"]
            self.assertEqual(changed["commentary_status"], "translation_changed")
            self.assertEqual(changed["commentary"], "")
            raw = translations.iter_cached_records(path)[0]
            self.assertEqual(raw["translation"], record["translation"])
            self.assertEqual(raw["commentary"], original_commentary)
            self.assertNotIn(original_commentary, translations.export_sentence_translations_markdown([raw]))
            self.assertEqual(raw["review_state"], "reviewed")

    def test_identical_human_confirmation_keeps_bound_notes(self):
        record = self.record()
        record["human_translation"] = "  삶은  힘에의 의지다. "
        self.assertEqual(translations.public_translation_record(record)["commentary_status"], "current")

    def test_legacy_and_interpretation_fallback_are_not_published(self):
        for human in ["", "사람이 수정한 문장"]:
            record = {"translation":"옛 번역", "human_translation":human, "commentary":"옛 해설", "interpretation":"옛 해설"}
            public = translations.public_translation_record(record)
            self.assertEqual(public["commentary"], "")
            self.assertNotIn("interpretation", public)
            self.assertNotIn("옛 해설", translations.export_sentence_translations_markdown([record]))

    def test_source_and_internal_language_fail_closed(self):
        for notes in [[{"source_span":"absent", "note":"원문에 없는 표현이다."}], [{"source_span":"Wille", "note":"승인된 번역 지침에 따라 옮겼다."}], [{"source_span":"Wille", "note":"지침에 명시된 표현을 적용했다."}], [{"source_span":"Wille", "note":"Translation policy를 적용했다."}], [{"source_span":"Wille", "note":12}]]:
            self.assertEqual(grounded_notes(notes, "Wille zur Macht"), [])

    def test_final_revision_gets_its_own_notes_with_four_calls(self):
        bundle = translations.build_sentence_prompt_bundle(synthetic_sentence_target())
        initial = {"verdict":"revise", "issues":[critic_issue()], "translation_notes":[{"source_span":"Leben", "note":"버려질 초벌 노트다."}]}
        final = {"verdict":"pass", "issues":[], "translation_notes":[{"source_span":"Wille zur Macht", "note":"최종 번역의 힘에의 의지가 원문 명사구를 옮긴다."}]}
        with patch.object(translations, "call_llama_server", return_value={"translation":"초벌", "commentary":"버려질 설명", "cautions":[]}) as translator, patch.object(translations, "call_critic_server", side_effect=[initial,final]) as critic, patch.object(translations, "call_revision_server", return_value={"translation":"삶은 힘에의 의지다.", "commentary":"수정 중 설명", "cautions":[]}) as revision:
            output = translations.run_translation_pipeline(bundle)
        self.assertEqual(translator.call_count+critic.call_count+revision.call_count, 4)
        self.assertEqual(output["translation_notes"], final["translation_notes"])
        self.assertNotIn("버려질", output["commentary"])
        self.assertEqual(output["commentary_translation_sha256"], translation_hash(output["translation"]))

    def test_unresolved_issues_never_publish_notes(self):
        output = translations.pipeline_output({"translation":"초벌", "commentary":"오래된 설명", "cautions":[]}, quality_state="needs_human_review", revision_count=0, initial_critic={"verdict":"revise","issues":[critic_issue("minor")],"translation_notes":[{"source_span":"Leben","note":"표시되면 안 되는 설명"}]}, final_critic=None, initial_critic_prompt_sha256="a"*64)
        self.assertEqual(output["commentary"], "")
        self.assertEqual(output["translation_notes"], [])

    def test_missing_new_critic_notes_is_a_contract_error(self):
        with self.assertRaises(translations.TranslationModelResponseError):
            translations.normalized_critic_output(json.dumps({"verdict":"pass","issues":[]}), require_notes=True)

    def test_schema_rejects_broken_hash_and_ungrounded_notes(self):
        record = self.record()
        record["translation"] = "다른 번역"
        with self.assertRaises(AssertionError):
            validate_record(record, Path("fixture"), 1)
        record = self.record()
        record["note_source_text"] = "Changed source with Wille zur Macht."
        self.assertEqual(translations.public_translation_record(record)["commentary_status"],"source_changed")
        self.assertEqual(translations.public_translation_record(record)["commentary"],"")
        record = self.record()
        record["translation_notes"][0]["source_span"] = "not in source"
        with self.assertRaises(AssertionError):
            validate_record(record, Path("fixture"), 1)

    def test_semantic_omission_survives_approved_wording(self):
        bundle = translations.build_sentence_prompt_bundle(synthetic_sentence_target())
        bundle["approved_sentence_rules"] = [{"allowed_translation_fragments":["삶은 의지다."]}]
        issue = {"source_span":"Macht","translation_span":"삶은 의지다.","category":"omission","severity":"major","explanation":"원문의 의미 요소가 누락되었다."}
        audit = translations.merge_approved_policy_audit(bundle,"삶은 의지다.",{"verdict":"revise","issues":[issue]})
        self.assertEqual(audit["issues"],[issue])

    def test_usage_is_numeric_isolated_and_missing_is_unknown(self):
        def sample(index):
            with capture_model_usage() as calls:
                event = begin_model_call("sentence_translation_response",900)
                finish_model_call(event,{"usage":{"prompt_tokens":3000+index,"completion_tokens":100},"content":"must not be retained"},8192)
                return usage_summary(calls,True)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(sample,range(4)))
        for index,result in enumerate(results):
            self.assertEqual(result["model_calls"],1)
            self.assertEqual(result["model_usage"][0]["available_context"],5192-index)
            self.assertNotIn("content",json.dumps(result))
        event = begin_model_call("sentence_translation_response",900)
        finish_model_call(event,{},None)
        self.assertIsNone(event["prompt_tokens"])
        self.assertIsNone(event["available_context"])

    def test_primary_meaning_checks_reject_known_errors_and_accept_faithful_variants(self):
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
        samples = [
            ("fb", "sks-0027.s001", "이 돈에 대해서는 나에게 아무런 윤리적 의무가 없으나, 아들에 대해서는 아버지가 가장 높고 거룩하다.",
             ["왜냐하면 나는 돈에 대한 윤리적 의무가 없지만 아버지는 아들에게 가장 높고 신성한 의무를 진다.",
              "아버지는 아들에 대해 지극히 신성한 책무를 진다.", "아들에 대한 가장 신성한 의무를 지는 사람은 아버지이다."]),
            ("FW", "p-0186.s001", "우리 면전의 땀 흘리는 수고 속에서",
             ["우리 얼굴에 땀을 흘리며", "우리의 낯에 흐르는 땀으로", "우리 이마에 땀을 흘리며"]),
            ("fb", "sks-0014.s001", "하나님과 함께 걷는 자는 모든 이보다 더 위대해졌다.",
             ["그러나 하나님과 겨룬 사람은 모든 이보다 더 위대해졌다.", "하지만 하나님과 싸웠던 자는 모두보다 위대해졌다.",
              "이와 달리 하나님과의 싸움에 임한 사람은 더 위대해졌다."]),
        ]
        for work, sentence, bad, alternatives in samples:
            case = next(case for case in plan["cases"] if case["work_id"] == work and case["sentence_id"] == sentence)
            target = {**case, "sentence_text_sha256": case["source_text_sha256"]}
            with self.subTest(sentence=sentence):
                self.assertTrue(any(issue["severity"] == "major" for issue in source_meaning_issues(target, bad)))
                for good in alternatives:
                    self.assertEqual(source_meaning_issues(target, good), [])
                self.assertEqual(source_meaning_issues({**target, "sentence_text_sha256": "0" * 64}, bad), [])
                self.assertEqual(source_meaning_issues({**target, "work_id": "another-work"}, bad), [])
                self.assertIn("primary text and dictionary evidence", source_evidence_text(target))
                bundle = {"source_context": "<TARGET_SENTENCE>" + case["source_text"] + "</TARGET_SENTENCE>", "target": target}
                audit = translations.merge_approved_policy_audit(bundle, bad, {"verdict": "pass", "issues": []})
                self.assertEqual(audit["verdict"], "revise")
                self.assertTrue(any(issue["severity"] == "major" for issue in audit["issues"]))

    def test_new_optional_source_check_conditions_reject_invalid_configuration(self):
        from services import translation_source_checks as source_rules
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checks.json"
            rule = {"corpus_id": "demo", "work_id": "demo", "variant_id": "", "sentence_id": "s1", "sentence_text_sha256": "a" * 64,
                    "meaning_checks": [{"source_span": "word", "korean_patterns": ["("], "explanation": "설명"}]}
            for conditions in [{"korean_patterns": ["("]}, {"korean_patterns": "word"},
                               {"forbidden_korean_patterns": ["("]}, {"forbidden_korean_patterns": "word"},
                               {"forbidden_korean_fragments": [False]}, {"severity": "fatal", "korean_alternatives": ["단어"]}, {}]:
                rule["meaning_checks"] = [{"source_span": "word", "explanation": "설명", **conditions}]
                path.write_text(json.dumps({"schema_version": 1, "rules": [rule]}), encoding="utf-8")
                with self.subTest(conditions=conditions), patch.object(source_rules, "CHECKS_FILE", path), self.assertRaises(ValueError):
                    source_rules.source_meaning_issues(rule, "단어")

    def test_k03_riding_check_is_exact_source_scoped(self):
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
        case = next(case for case in plan["cases"] if case["work_id"] == "fb" and case["sentence_id"] == "sks-0006.s009")
        target = {**case, "sentence_text_sha256":case["source_text_sha256"]}
        self.assertEqual(source_meaning_issues(target,"그의 열망은 갔던 여정에 동행하는 것이었다.")[0]["category"],"omission")
        for fragment in ["말을 타고 갔던", "말을 탄", "말에 올라 갔던", "승마"]:
            self.assertEqual(source_meaning_issues(target,fragment),[])
        self.assertIn("Attraa is a Danish noun",source_evidence_text(target))
        self.assertEqual(source_meaning_issues({**target,"sentence_text_sha256":"0"*64},"갔다"),[])
        self.assertEqual(source_meaning_issues({**target,"work_id":"other"},"갔다"),[])
        raw = {**target, "id":"k03-check", "translation":"그의 열망은 갔던 여정에 동행하는 것이었다.",
               "note_source_text":case["source_text"], "translation_notes":[{"source_span":"Attraa", "note":"열망은 원문의 명사에 대응한다."}],
               "commentary_translation_sha256":translation_hash("그의 열망은 갔던 여정에 동행하는 것이었다.")}
        public = translations.public_translation_record(raw)
        self.assertEqual(public["commentary_status"],"translation_review_required")
        self.assertEqual(public["commentary"],"")
        self.assertEqual(public["current_translation_issues"][0]["source_span"],"reed")
        self.assertIn("현재 번역 의미 검토 필요", translations.export_sentence_translations_markdown([raw]))

    def test_recorded_false_notes_fail_audit_api_and_export_without_banning_negation(self):
        fixtures = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["note_cases"]
        self.assertEqual(len(fixtures), 10)
        for case in fixtures:
            with self.subTest(case=case["case_id"]):
                target = {**case, "sentence_text": case["source_text"]}
                bad = case["known_bad_notes"]
                good = case["corrected_notes"]
                self.assertEqual(grounded_notes(bad, case["source_text"]), bad)
                self.assertEqual(grounded_notes(good, case["source_text"]), good)
                plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
                source_case = next(item for item in plan["cases"] if all(item[field] == case[field] for field in ["corpus_id", "work_id", "variant_id", "sentence_id"]))
                self.assertEqual(source_case["source_text"], case["source_text"])
                self.assertEqual(source_case["source_text_sha256"], case["sentence_text_sha256"])
                self.assertTrue(source_note_issues(target, bad))
                self.assertEqual(source_note_issues(target, good), [])
                self.assertEqual(source_note_issues({**target, "sentence_text_sha256": "0" * 64}, bad), [])
                self.assertEqual(source_note_issues({**target, "variant_id": "other"}, bad), [])
                corrected_quote = [{**bad[0], "note": "다음 설명은 오류이며 채택하지 않는다: " + bad[0]["note"]}]
                self.assertEqual(source_note_issues(target, corrected_quote), [])
                bundle = {"target": target, "source_context": f'<TARGET_SENTENCE>{case["source_text"]}</TARGET_SENTENCE>'}
                audit = translations.merge_approved_policy_audit(bundle, case["reference_translation"], {"verdict": "pass", "issues": [], "translation_notes": bad})
                self.assertEqual(audit["verdict"], "revise")
                self.assertTrue(any(issue["severity"] == "major" for issue in audit["issues"]))
                raw = {**target, "id": case["case_id"], "translation": case["reference_translation"], "translation_notes": bad,
                       "note_source_text": case["source_text"], "commentary_translation_sha256": translation_hash(case["reference_translation"])}
                public = translations.public_translation_record(raw)
                self.assertEqual(public["commentary_status"], "notes_review_required")
                self.assertEqual(public["translation_notes"], [])
                self.assertEqual(public["commentary"], "")
                self.assertTrue(public["current_note_issues"])
                for export_input in [raw, public]:
                    exported = translations.export_sentence_translations_markdown([export_input])
                    self.assertIn("현재 번역 노트 검토 필요", exported)
                    self.assertNotIn(bad[0]["note"], exported)
                changed_public = translations.public_translation_record({**public, "human_translation": "다른 확정 번역"})
                self.assertEqual(changed_public["commentary_status"], "translation_changed")
                self.assertEqual(changed_public["current_note_issues"], [])
                raw["human_translation_notes"] = {"source_text": case["source_text"], "sentence_text_sha256": case["sentence_text_sha256"],
                    "translation_sha256": translation_hash(case["reference_translation"]), "notes": good}
                self.assertEqual(translations.public_translation_record(raw)["commentary_status"], "current")
                self.assertEqual(raw["translation_notes"], bad)
                raw.pop("human_translation_notes")
                raw["translation_notes"] = good
                self.assertEqual(translations.public_translation_record(raw)["commentary_status"], "current")

    def test_remaining_source_checks_accept_references_and_hold_recorded_failures(self):
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
        regression = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))
        targets = {(case["corpus_id"], case["work_id"], case["variant_id"], case["sentence_id"]): case for case in plan["cases"]}
        cases = [case for case in regression["cases"] if case["case_id"].startswith(tuple(f"r{number:02d}-" for number in [3,6,7,13,14,15,17,21,24,34,38,44]))]
        self.assertEqual(len(cases), 12)
        for case in cases:
            original = targets[tuple(case[key] for key in ["corpus_id", "work_id", "variant_id", "sentence_id"])]
            target = {**case, "sentence_text_sha256": original["source_text_sha256"]}
            with self.subTest(case=case["case_id"]):
                issues = source_meaning_issues(target, case["known_bad_translation"])
                self.assertTrue(issues)
                if case["require_major_issue"]:
                    self.assertTrue(any(issue["severity"] == "major" for issue in issues))
                for good in case["accepted_translations"]:
                    self.assertEqual(source_meaning_issues(target, good), [])
                self.assertEqual(source_meaning_issues({**target, "sentence_text_sha256": "0" * 64}, case["known_bad_translation"]), [])
        for case in regression["note_cases"]:
            self.assertEqual(source_meaning_issues(case, case["reference_translation"]), [])

    def test_source_evidence_reaches_translator_critic_and_revision_requests(self):
        from services.translation_source_checks import source_checks
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
        checked = 0
        for case in plan["cases"]:
            target = {**case, "sentence_text_sha256": case["source_text_sha256"]}
            rules = source_checks(target)
            if not rules:
                continue
            target = benchmark_sentence_target(case)
            bundle = translations.build_sentence_prompt_bundle(target)
            critic = translations.build_critic_prompt_bundle(bundle, "검토할 번역")
            revision = translations.build_revision_prompt_bundle(bundle, "검토할 번역", [critic_issue()])
            for rule in rules:
                for fact in rule["lexical_evidence"]:
                    for stage in [bundle, critic, revision]:
                        self.assertIn(fact, stage["prompt"])
            checked += 1
        self.assertEqual(checked, 19)

    def test_semantic_controls_bind_to_source_and_preserve_real_audit_issues(self):
        from scripts import check_translation_quality_regressions as quality
        controls = quality.load_semantic_controls()
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual(len(controls), 9)
        self.assertEqual(sum(control["expected_major_semantic_error"] for control in controls), 3)
        for control in controls:
            case = next(case for case in plan["cases"] if all(case[key] == control[key]
                for key in ["corpus_id", "work_id", "variant_id", "segment_id", "sentence_id"]))
            with patch.object(quality, "sentence_target_bundle", return_value=benchmark_sentence_target(case)):
                bundle, critic = quality.prepare_semantic_control(control)
                self.assertIn(control["translation"], critic["prompt"])
                with self.assertRaisesRegex(AssertionError, "source changed"):
                    quality.prepare_semantic_control({**control, "sentence_text_sha256": "0" * 64})
            # Correct meanings do not grant an unconditional pass or hide a
            # critic's future legitimate semantic/readability objection.
            issue = {"source_span": "", "translation_span": control["translation"], "category": "syntax_or_scope",
                     "severity": "major", "explanation": "향후 별도의 의미 문제가 확인된 경우의 검사이다."}
            merged = translations.merge_approved_policy_audit(bundle, control["translation"], {"verdict": "revise", "issues": [issue]})
            self.assertIn(issue, merged["issues"])
            self.assertEqual(merged["verdict"], "revise")
            self.assertTrue(quality.has_major_semantic_issue(merged))
            issue = {**issue, "category": "korean_readability"}
            merged = translations.merge_approved_policy_audit(bundle, control["translation"], {"verdict": "revise", "issues": [issue]})
            self.assertIn(issue, merged["issues"])
            self.assertEqual(merged["verdict"], "revise")
        old = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["note_cases"]
        r44 = next(case for case in old if case["case_id"] == "note-r44")
        self.assertEqual(len(r44["known_bad_notes"]), 3)
        for note in r44["known_bad_notes"]:
            self.assertTrue(source_note_issues(r44, [note]))
        self.assertEqual(source_note_issues(r44, r44["corrected_notes"]), [])

    def test_followup_meaning_errors_hold_audit_api_and_export(self):
        cases = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["cases"]
        cases = [case for case in cases if case["case_id"].startswith("followup-")]
        self.assertEqual(len(cases), 3)
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["case_id"]):
                source = next(item for item in plan if all(item[key] == case[key] for key in ["corpus_id", "work_id", "variant_id", "sentence_id"]))
                target = {**case, "sentence_text_sha256": source["source_text_sha256"]}
                issues = source_meaning_issues(target, case["known_bad_translation"])
                self.assertTrue(any(issue["category"] in case["expected_categories"] and issue["severity"] == "major" for issue in issues))
                for good in case["accepted_translations"]:
                    self.assertEqual(source_meaning_issues(target, good), [])
                for field in ["corpus_id", "work_id", "variant_id", "sentence_id", "sentence_text_sha256"]:
                    self.assertEqual(source_meaning_issues({**target, field: "changed"}, case["known_bad_translation"]), [])
                bundle = {"target": target, "source_context": f'<TARGET_SENTENCE>{source["source_text"]}</TARGET_SENTENCE>'}
                audit = translations.merge_approved_policy_audit(bundle, case["known_bad_translation"], {"verdict": "pass", "issues": []})
                self.assertEqual(audit["verdict"], "revise")
                raw = {**target, "id": case["case_id"], "translation": case["known_bad_translation"],
                       "note_source_text": source["source_text"], "translation_notes": [],
                       "commentary_translation_sha256": translation_hash(case["known_bad_translation"])}
                for notes in [[], [{"source_span": next(iter(case["source_features"].values()))[0], "note": "이 구절의 의미 관계를 보존해야 한다."}]]:
                    raw["translation_notes"] = notes
                    public = translations.public_translation_record(raw)
                    self.assertEqual(public["commentary_status"], "translation_review_required" if notes else "none")
                    self.assertEqual(public["translation_notes"], [])
                    self.assertTrue(public["current_translation_issues"])
                    for exported_record in [raw, public]:
                        self.assertIn("현재 번역 의미 검토 필요", translations.export_sentence_translations_markdown([exported_record]))

    def test_r02_corrupted_assertion_variants_preserve_corrective_quotes(self):
        case = next(case for case in json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["note_cases"] if case["case_id"] == "note-r02")
        bad = case["known_bad_notes"][-1]
        self.assertTrue(source_note_issues(case, [bad]))
        variation = {**bad, "note": bad["note"].replace("가장 높고도 거룩한", "최고로 신성한").replace("명시적 관계를 설정함.", "명확히 연결됨.")}
        self.assertTrue(source_note_issues(case, [variation]))
        for corrected in ["다음 설명은 오류이며 채택하지 않는다: " + bad["note"], bad["note"] + " 이 설명에는 오타가 있어 의무로 고쳐야 한다.",
                          "번역문에서 '의ub의'가 아니라 '의무'로 표기해야 한다."]:
            self.assertEqual(source_note_issues(case, [{**bad, "note": corrected}]), [])
        bundle = {"target": case, "source_context": f'<TARGET_SENTENCE>{case["source_text"]}</TARGET_SENTENCE>'}
        audit = translations.merge_approved_policy_audit(bundle, case["reference_translation"], {"verdict": "pass", "issues": [], "translation_notes": [variation]})
        self.assertEqual(audit["verdict"], "revise")
        raw = {**case, "id": case["case_id"], "translation": case["reference_translation"], "translation_notes": [variation],
               "note_source_text": case["source_text"], "commentary_translation_sha256": translation_hash(case["reference_translation"])}
        public = translations.public_translation_record(raw)
        self.assertEqual(public["commentary_status"], "notes_review_required")
        self.assertEqual(public["translation_notes"], [])
        self.assertIn("현재 번역 노트 검토 필요", translations.export_sentence_translations_markdown([raw]))
        self.assertNotIn(variation["note"], translations.export_sentence_translations_markdown([raw]))
        for field in ["corpus_id", "work_id", "variant_id", "sentence_id", "sentence_text_sha256"]:
            self.assertEqual(source_note_issues({**case, field: "changed"}, [variation]), [])

    def test_logical_relations_survive_raw_pass_without_rejecting_faithful_word_order(self):
        fixtures = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["cases"]
        fixtures = [case for case in fixtures if case["case_id"] in {"relations-r07", "relations-r14", "relations-r17"}]
        self.assertEqual(len(fixtures), 3)
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))["cases"]
        for case in fixtures:
            with self.subTest(case=case["case_id"]):
                source = next(item for item in plan if all(item[key] == case[key] for key in ["corpus_id", "work_id", "variant_id", "sentence_id"]))
                target = {**case, "sentence_text_sha256": source["source_text_sha256"]}
                self.assertTrue(any(issue["severity"] == "major" and issue["category"] == "syntax_or_scope" for issue in source_meaning_issues(target, case["known_bad_translation"])))
                for good in case["accepted_translations"]:
                    self.assertEqual(source_meaning_issues(target, good), [])
                bundle = {"target": target, "source_context": f'<TARGET_SENTENCE>{source["source_text"]}</TARGET_SENTENCE>'}
                audit = translations.merge_approved_policy_audit(bundle, case["known_bad_translation"], {"verdict": "pass", "issues": [], "translation_notes": []})
                self.assertEqual(audit["verdict"], "revise")
                for field in ["corpus_id", "work_id", "variant_id", "sentence_id", "sentence_text_sha256"]:
                    self.assertEqual(source_meaning_issues({**target, field: "changed"}, case["known_bad_translation"]), [])
                raw = {**target, "id": case["case_id"], "translation": case["known_bad_translation"], "note_source_text": source["source_text"],
                       "translation_notes": [{"source_span": next(iter(case["source_features"].values()))[0], "note": "이 구절의 논리 관계를 보존해야 한다."}],
                       "commentary_translation_sha256": translation_hash(case["known_bad_translation"])}
                public = translations.public_translation_record(raw)
                self.assertEqual(public["commentary_status"], "translation_review_required")
                self.assertEqual(public["translation_notes"], [])
                self.assertTrue(public["current_translation_issues"])
                for exported in [raw, public]:
                    self.assertIn("현재 번역 의미 검토 필요", translations.export_sentence_translations_markdown([exported]))
        r17 = next(case for case in fixtures if case["case_id"] == "relations-r17")
        source = next(item for item in plan if item["corpus_id"] == r17["corpus_id"] and item["work_id"] == r17["work_id"] and item["sentence_id"] == r17["sentence_id"])
        target = {**r17, "sentence_text_sha256": source["source_text_sha256"]}
        # A negation in a different clause cannot restore the reminder's polarity.
        wrong = r17["known_bad_translation"].replace("기만한다는", "기만하지 않는다는")
        self.assertTrue(any(issue["source_span"] == "men aldrig minder dem om denne Salighed" and issue["category"] == "syntax_or_scope" for issue in source_meaning_issues(target, wrong)))
        # Korean coordination also separates predicates without punctuation.
        wrong = r17["accepted_translations"][0].replace("이 복됨을 결코 일깨워 주지 않으며", "이 복됨을 일깨워 주며 그들을 속이지 않으며")
        self.assertTrue(any(issue["source_span"] == "men aldrig minder dem om denne Salighed" and issue["category"] == "syntax_or_scope" for issue in source_meaning_issues(target, wrong)))

    def test_observed_r07_revision_rejects_heightened_moses_idiom(self):
        fixtures = json.loads((SITE / "data/translation_regression_cases.json").read_text(encoding="utf-8"))["cases"]
        case = next(case for case in fixtures if case["case_id"] == "relations-r07-heightened-moses")
        plan = json.loads((SITE / "data/translation_notes_benchmark.json").read_text(encoding="utf-8"))["cases"]
        source = next(item for item in plan if item["corpus_id"] == case["corpus_id"] and item["work_id"] == case["work_id"] and item["sentence_id"] == case["sentence_id"])
        target = {**case, "sentence_text_sha256": source["source_text_sha256"]}
        self.assertTrue(any(issue["category"] == "semantic_substitution" and issue["severity"] == "major" for issue in source_meaning_issues(target, case["known_bad_translation"])))
        for good in case["accepted_translations"]:
            self.assertEqual(source_meaning_issues(target, good), [])

    def test_note_pattern_configuration_is_validated_and_matches_whole_assertions(self):
        from services import translation_source_checks as source_rules
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checks.json"
            rule = {"corpus_id": "demo", "work_id": "demo", "variant_id": "", "sentence_id": "s1", "sentence_text_sha256": "a" * 64}
            for conditions in [{"forbidden_note_patterns": ["("]}, {"forbidden_note_patterns": "word"},
                               {"forbidden_note_patterns": [False]}, {"forbidden_note_assertions": None}, {},
                               {"forbidden_note_assertions": ["설명"], "forbidden_note_patterns": ["("]}]:
                rule["note_checks"] = [{"source_span": "word", "explanation": "설명", **conditions}]
                path.write_text(json.dumps({"schema_version": 1, "rules": [rule]}), encoding="utf-8")
                with self.subTest(conditions=conditions), patch.object(source_rules, "CHECKS_FILE", path), self.assertRaises(ValueError):
                    source_rules.source_note_issues(rule, [{"source_span": "word", "note": "설명"}])
            rule["note_checks"] = [{"source_span": "word", "explanation": "설명", "forbidden_note_patterns": ["잘못된 (?:설명|노트)입니다\\."]}]
            path.write_text(json.dumps({"schema_version": 1, "rules": [rule]}), encoding="utf-8")
            with patch.object(source_rules, "CHECKS_FILE", path):
                self.assertTrue(source_rules.source_note_issues(rule, [{"source_span": "word", "note": "잘못된 설명입니다."}]))
                self.assertEqual(source_rules.source_note_issues(rule, [{"source_span": "word", "note": "오류 인용: 잘못된 설명입니다."}]), [])


if __name__ == "__main__":
    unittest.main()
