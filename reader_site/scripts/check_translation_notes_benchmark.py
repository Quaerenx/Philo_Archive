"""Frozen 50-sentence benchmark; human scores are never inferred or modified."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from urllib.parse import urlsplit

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from services import sentence_translations as translations
from services.sentence_targets import sentence_target_bundle
from services.source_targets import sha256_text
from scripts.check_ai_records_contracts import validate_record

PLAN = SITE / "data/translation_notes_benchmark.json"


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--plan", type=Path, default=PLAN, help="Frozen benchmark plan; use a new plan when a source boundary changes.")
    parser.add_argument("--with-sources", action="store_true")
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    cases = plan["cases"]
    assert len(cases) == 50
    assert Counter(case["corpus_id"] for case in cases) == {"bible":13,"kierkegaard":13,"nietzsche":12,"wittgenstein":12}
    assert Counter(case["split"] for case in cases) == {"calibration":20,"held_out":30}
    assert set(plan["rubric"]["dimensions"]) == {"omission_addition","logic","terminology","korean_readability","note_accuracy"}
    identities = set()
    for case in cases:
        key = tuple(case[field] for field in ["corpus_id","work_id","variant_id","sentence_id"])
        assert key not in identities
        identities.add(key)
        assert case["source_text_sha256"] == sha256_text(case["source_text"])
        evaluation = case["human_evaluation"]
        assert evaluation["status"] in {"pending", "evaluated"}
        if evaluation["status"] == "pending":
            assert not evaluation["scores"]
        else:
            assert set(evaluation["scores"]) == set(plan["rubric"]["dimensions"])
            assert evaluation["evaluator"] and evaluation.get("evaluated_at")
            assert all(isinstance(score,int) and not isinstance(score,bool) and 1 <= score <= 5 for score in evaluation["scores"].values())
        if args.with_sources or args.with_model:
            target = sentence_target_bundle(*(case[field] for field in ["corpus_id","work_id","segment_id","sentence_id","variant_id"]))
            assert target["sentence_text_sha256"] == case["source_text_sha256"], case["id"]
    if not args.with_model:
        print("translation notes benchmark ok: 50 frozen sentences, five dimensions, human evaluation pending")
        return

    selected = cases[:args.limit] if args.limit > 0 else cases
    endpoint = urlsplit(translations.LLAMA_BASE_URL)
    assert endpoint.scheme in {"http","https"} and endpoint.hostname in {"127.0.0.1","localhost","::1"}, "benchmark model endpoint must be loopback"
    protected = [SITE/"data/translation_quality_goldset.json", SITE/"data/translation_profiles.json", *sorted((SITE/"data/ai").glob("*.jsonl")), *sorted((SITE/"data/notes").glob("*.jsonl"))]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    output = SITE / "data/runtime.local" / datetime.now().strftime("notes-benchmark-%Y%m%d-%H%M%S")
    output.mkdir()
    results = []
    try:
        with patch.object(translations,"AI_DIR",output/"records"):
            for case in selected:
                started = perf_counter()
                response = translations.sentence_translation_from_payload({**case,"regenerate":True})
                record = response["record"]
                # Public fields may omit a failed note; validate the untouched saved record.
                raw = translations.iter_cached_records(translations.ai_record_path(case["corpus_id"]))[-1]
                validate_record(raw, Path("isolated-live-record"), 1)
                assert response["metrics"]["model_calls"] <= 4
                assert record["commentary_status"] in {"current","none"}
                result = {"case_id":case["id"],"split":case["split"],"seconds":perf_counter()-started,"quality_state":record["quality_state"],"revision_count":record["revision_count"],"commentary_status":record["commentary_status"],"metrics":response["metrics"],"record":record,"human_scores":{}}
                results.append(result)
                (output/"candidates.json").write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
                print(json.dumps({key:result[key] for key in ["case_id","seconds","quality_state","revision_count","commentary_status"]},ensure_ascii=True),flush=True)
    finally:
        unchanged = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path,digest in before.items())
        tokens = [call["prompt_tokens"] for result in results for call in result["metrics"]["model_usage"] if call["prompt_tokens"] is not None]
        summary = {"recorded_at":datetime.now(timezone.utc).isoformat(),"benchmark_sha256":hashlib.sha256(plan_bytes).hexdigest(),"selected":len(selected),"completed":len(results),"quality_states":dict(Counter(result["quality_state"] for result in results)),"notes_present":sum(result["commentary_status"]=="current" for result in results),"mean_seconds":statistics.mean(result["seconds"] for result in results) if results else None,"prompt_token_max":max(tokens) if tokens else None,"model_calls":sum(result["metrics"]["model_calls"] for result in results),"personal_and_reference_unchanged":unchanged,"human_evaluation":"pending; automatic states are not accuracy scores"}
        (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        assert unchanged,"personal records changed during benchmark; inspect external activity, do not restore automatically"
        print(json.dumps({"output":str(output),**summary},ensure_ascii=True),flush=True)


if __name__ == "__main__":
    main()
