from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from rendering.work_markup import concept_markup, render_work_page_html  # noqa: E402
from services.translation_profiles import read_translation_profiles  # noqa: E402


class ReaderPresentationContracts(unittest.TestCase):
    def test_approved_terms_remain_scoped_to_work_and_variant(self):
        profiles = read_translation_profiles()
        template = '<script type="application/json">{{RESEARCH_JSON}}</script>'
        for profile in profiles:
            with self.subTest(profile=profile["profile_id"]):
                context = {key: profile.get(key, "") for key in ("corpus_id", "work_id", "variant_id")}
                model = {"research": dict(context)}
                html = render_work_page_html(template, model)
                terms = json.loads(html.split(">", 1)[1].rsplit("<", 1)[0])["reading_terms"]
                self.assertEqual(
                    [(term["source"], term["target"]) for term in terms],
                    [(term["source"], term["target"]) for term in profile.get("terminology", [])],
                )
                self.assertTrue(all(term["kind"] == "approved" for term in terms))
                self.assertNotIn("reading_terms", model["research"])
                if context["variant_id"] and not any(
                    candidate["corpus_id"] == context["corpus_id"]
                    and candidate["work_id"] == context["work_id"]
                    and not candidate.get("variant_id") for candidate in profiles
                ):
                    wrong_variant = render_work_page_html(template, {"research": {**context, "variant_id": "not-a-registered-variant"}})
                    self.assertEqual(json.loads(wrong_variant.split(">", 1)[1].rsplit("<", 1)[0])["reading_terms"], [])
                unrelated = render_work_page_html(template, {"research": {**context, "work_id": "not-a-registered-work"}})
                self.assertEqual(json.loads(unrelated.split(">", 1)[1].rsplit("<", 1)[0])["reading_terms"], [])

    def test_script_json_preserves_special_characters_without_markup_injection(self):
        dangerous = '<script> & </script> " 😀'
        policy = {"terminology": [{"source": dangerous, "target": dangerous, "note": dangerous}]}
        with patch("rendering.work_markup.translation_policy_bundle", return_value=policy):
            html = render_work_page_html('{{RESEARCH_JSON}}', {"research": {"title": dangerous}})
        self.assertNotIn("<", html)
        self.assertNotIn(">", html)
        self.assertNotIn("&", html)
        payload = json.loads(html)
        self.assertEqual(payload["title"], dangerous)
        self.assertEqual(payload["reading_terms"][0]["source"], dangerous)
        self.assertEqual(payload["reading_terms"][0]["note"], dangerous)

    def test_registered_concept_attributes_are_escaped_and_labelled_separately(self):
        html = concept_markup([{"label_ko": '개념 "이름"', "search_query": '<x>"',
            "description_ko": '<script>alert("x")</script>'}], "nietzsche")
        self.assertIn('data-term-source="&lt;x&gt;&quot;"', html)
        self.assertIn('data-term-note="&lt;script&gt;', html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("승인", html)


if __name__ == "__main__":
    unittest.main()
