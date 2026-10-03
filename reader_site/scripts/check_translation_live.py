"""Opt-in HTTP checks against the real local model, with isolated AI records.

No model responses are mocked. The urlopen observer records actual call timing;
the production Handler, source resolver, pipeline and storage perform the work.
Human scores remain empty. Run explicitly; this is not a source-light CI check.
Queue checks briefly hold Python exception cleanup after the real socket abort
to observe a waiting replacement; this does not verify GPU-side cancellation.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sys
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

import server  # noqa: E402
from services import sentence_translations as translations, translation_jobs as jobs  # noqa: E402
from services.sentence_targets import sentence_target_bundle  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def personal_fingerprints():
    return {
        str(path.relative_to(SITE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (SITE / "data" / "ai", SITE / "data" / "notes")
        for path in sorted(directory.glob("*.jsonl"))
    }


def load_targets(plan):
    require(plan.get("schema_version") == 1, "unsupported sample plan")
    counts = Counter(case["corpus_id"] for case in plan["cases"])
    require(counts == {name: 4 for name in ("bible", "kierkegaard", "nietzsche", "wittgenstein")}, "need four new cases per corpus")
    targets = {}
    identities = set()
    for case in plan["cases"]:
        require(case["id"] not in targets, "duplicate sample id")
        target = sentence_target_bundle(*(case[key] for key in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")))
        require(target["sentence_id"] == case["sentence_id"], f"{case['id']}: stale sentence id")
        identity = tuple(target[key] for key in ("corpus_id", "work_id", "variant_id", "sentence_id"))
        require(identity not in identities, "duplicate sample target")
        identities.add(identity)
        targets[case["id"]] = target
    return targets


@contextmanager
def local_server():
    class QuietHandler(server.Handler):
        def log_message(self, *args):
            pass

    httpd = server.LoopbackThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield httpd.server_port
    finally:
        with jobs._guard:
            outstanding = list(jobs._running)
        for identifier in outstanding:
            jobs.cancel_translation(identifier)
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)


class LiveRun:
    def __init__(self, port, output):
        self.port = port
        self.output = output
        self.calls = []
        self.results = {}
        self.threads = []
        self.checks = []
        self.started = time.monotonic()
        self.original_urlopen = translations.urlopen
        self.cancel_release_gates = {}

    @contextmanager
    def observe_urlopen(self, request, **kwargs):
        # Observe the real HTTP request; return the original, unmodified response.
        current = jobs._current.get()
        event = {"request_id": current.request_id if current else "", "started_seconds": self.elapsed()}
        self.calls.append(event)
        try:
            with self.original_urlopen(request, **kwargs) as response:
                event["http_status"] = response.status
                event["headers_received_seconds"] = self.elapsed()
                yield response
        except Exception as error:
            event["error_type"] = type(error).__name__
            event["transport_ended_seconds"] = self.elapsed()
            gate = self.cancel_release_gates.get(event["request_id"])
            if gate is not None:
                # Hold only Python cleanup after the real socket has closed,
                # making the waiting replacement observable. Responses and
                # model execution remain unmodified.
                event["cleanup_barrier"] = True
                require(gate.wait(timeout=20), "cancel cleanup barrier was not released")
            raise
        finally:
            event["finished_seconds"] = self.elapsed()

    def elapsed(self):
        return round(time.monotonic() - self.started, 3)

    def post(self, route, payload):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=800)
        try:
            connection.request("POST", route, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
            response = connection.getresponse()
            return {"status": response.status, "body": json.loads(response.read()), "finished_seconds": self.elapsed()}
        finally:
            connection.close()

    def payload(self, case, regenerate=True):
        return {**{key: case[key] for key in ("corpus_id", "work_id", "variant_id", "segment_id", "sentence_id")}, "regenerate": regenerate, "request_id": str(uuid.uuid4())}

    def start(self, payload):
        def run():
            try:
                self.results[payload["request_id"]] = self.post("/api/sentence-translation", payload)
            except Exception as error:
                self.results[payload["request_id"]] = {"error": repr(error)}
        worker = threading.Thread(target=run)
        self.threads.append(worker)
        worker.start()

    def wait(self, predicate, message, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError(message)

    def finish(self, payload):
        identifier = payload["request_id"]
        self.wait(lambda: identifier in self.results, "translation did not finish", timeout=790)
        result = self.results[identifier]
        require("error" not in result, result)
        return result

    def cancel(self, payload):
        result = self.post("/api/sentence-translation/cancel", {"request_id": payload["request_id"]})
        require(result["status"] == 200, result)
        return result

    def records(self):
        return [record for path in sorted(translations.AI_DIR.glob("*_sentence_translations.jsonl")) for record in translations.iter_cached_records(path)]

    def checked(self, name, **evidence):
        self.checks.append({"name": name, "passed": True, **evidence})
        write_json(self.output / "checks.json", self.checks)
        print(f"PASS {name}", flush=True)

    def cancellation(self, first_case, next_case, cancel_waiter):
        before_ids = {record["id"] for record in self.records()}
        first, second = self.payload(first_case), self.payload(next_case)
        release = threading.Event()
        self.cancel_release_gates[first["request_id"]] = release
        try:
            self.start(first)
            self.wait(lambda: any(call["request_id"] == first["request_id"] for call in self.calls), "model call never started")
            call = next(call for call in self.calls if call["request_id"] == first["request_id"])

            def transport_registered():
                with jobs._guard:
                    job = jobs._running.get(first["request_id"])
                    return bool(job and job.abort_transport)

            self.wait(transport_registered, "model transport was not registered")
            time.sleep(0.1)
            require("headers_received_seconds" not in call, "model already finished before cancellation")
            ack = self.cancel(first)
            require(ack["body"].get("state") == "cancelling" and not ack["body"].get("execution_released"), ack)
            self.wait(lambda: "transport_ended_seconds" in call, "cancel did not interrupt the real HTTP transport")
            self.start(second)

            def queued():
                with jobs._guard:
                    job = jobs._running.get(second["request_id"])
                    return bool(job and not job.executing)

            self.wait(queued, "replacement never entered the waiting state")
            require(not any(item["request_id"] == second["request_id"] for item in self.calls), "queued request called the model")
            queued_ack = self.cancel(second) if cancel_waiter else None
        finally:
            release.set()
        first_result, second_result = self.finish(first), self.finish(second)
        require(first_result["status"] == 409, first_result)
        require(second_result["status"] == (409 if cancel_waiter else 200), second_result)
        calls = [item for item in self.calls if item["request_id"] == first["request_id"]]
        require(len(calls) == 1 and (calls[0].get("http_status") == 200 or calls[0].get("error_type")), "cancelled request must attempt one real model HTTP call and skip all later stages")
        require(calls[0]["finished_seconds"] > ack["finished_seconds"], "did not observe an in-flight cancellation")
        after = self.records()
        added = [record for record in after if record["id"] not in before_ids]
        if cancel_waiter:
            require(queued_ack["body"].get("state") == "cancelled" and queued_ack["body"].get("execution_released"), queued_ack)
            require(not added, "a cancelled request wrote a record")
            require(not any(item["request_id"] == second["request_id"] for item in self.calls), "cancelled waiter called the model")
        else:
            require(len(added) == 1 and added[0]["id"] == second_result["body"]["record"]["id"], "only replacement may write")
        self.checked("cancel_waiting_replacement" if cancel_waiter else "cancel_active_then_generate_replacement", acknowledgement=ack, queued_acknowledgement=queued_ack, active_status=first_result["status"], replacement_status=second_result["status"], added_records=len(added), transport_release_delay_seconds=round(calls[0]["transport_ended_seconds"] - ack["finished_seconds"], 3), cleanup_barrier=True, gpu_cancellation_verified=False)
        return second, second_result


def candidate(case, target, record):
    require(record["sentence_text_sha256"] == target["sentence_text_sha256"], "candidate/source hash mismatch")
    require(record["review_state"] == "generated" and not record.get("human_translation"), "model candidate must remain unreviewed")
    return {
        **case,
        "id": f"expansion-20260909-{case['id'].lower()}",
        "sample_label": case["id"],
        "source_text": target["sentence_text"],
        "candidate_translation": record["translation"],
        "candidate_record_id": record["id"],
        "reference_translation": "",
        "human_evaluation": {"status": "pending", "evaluator": "", "evaluated_at": "", "scores": {}, "notes": ""},
        "candidate_provenance": {key: record[key] for key in ("model_name", "model_runtime", "generated_at", "quality_pipeline_version", "prompt_sha256", "pipeline_contract_sha256", "sentence_text_sha256", "source_context_sha256", "quality_state", "revision_count")},
    }


def write_review(output, candidates, targets):
    for corpus in ("bible", "kierkegaard", "nietzsche", "wittgenstein"):
        selected = [case for case in candidates if case["corpus_id"] == corpus]
        lines = [f"# 번역 사람 평가: {corpus}", "", "점수 순서: 충실성 / 완전성 / 용어 정확성 / 한국어 가독성 (각 1~5점). 각 차원 4점 이상이 합격입니다.", "", "각 항목에 점수 네 개, 확정 번역, 판정 근거를 작성해 주세요. 문맥이 부족하면 점수 없이 보류할 수 있습니다. 자동 비평 결과와 모델 해설은 이 평가 문서에 표시하지 않았습니다.", ""]
        for case in selected:
            target = targets[case["sample_label"]]
            link = "http://127.0.0.1:8793/" + target["target_url"].lstrip("/")
            lines += [f"## {case['sample_label']} · {case['work_id']}", "", f"판본: `{case['variant_id'] or 'default'}` · 문장: `{case['sentence_id']}` · [원문 열기]({link})", "", "**평가할 원문**", "", case["source_text"], "", "**모델 후보 번역**", "", case["candidate_translation"], "", "**평가 답변**", "", f"- {case['sample_label']} 점수: / / /", "- 확정 번역:", "- 판정 근거 또는 보류 사유:", "", "<details>", "<summary>모델에 제공한 주변 문맥 (TARGET_SENTENCE가 평가 대상)</summary>", "", "```text", target["source_context"], "```", "", "</details>", ""]
        (output / f"review-{corpus}.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=SITE / "data" / "translation_quality_sample_plan.json")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory under data/runtime.local; existing directories are rejected.")
    parser.add_argument("--validate-plan-only", action="store_true")
    parser.add_argument("--generation-only", action="store_true", help="Generate fresh candidates without rerunning cancellation scenarios.")
    parser.add_argument("--case-id", action="append", help="Select sample IDs from the validated plan; cancellation checks require at least two.")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    targets = load_targets(plan)
    if args.validate_plan_only:
        print(f"sample plan ok: {len(targets)} distinct canonical source sentences")
        return
    if args.case_id:
        selected_ids = set(args.case_id)
        require(selected_ids <= set(targets), "unknown selected sample ID")
        plan = {**plan, "cases": [case for case in plan["cases"] if case["id"] in selected_ids]}
        require(args.generation_only or len(plan["cases"]) >= 2, "select at least two sample IDs for cancellation checks")
    output = args.output_dir.resolve()
    require(output.is_relative_to((SITE / "data" / "runtime.local").resolve()), "output must be inside data/runtime.local")
    output.mkdir(parents=True, exist_ok=False)
    personal_before = personal_fingerprints()
    goldset_path = SITE / "data" / "translation_quality_goldset.json"
    goldset_before = hashlib.sha256(goldset_path.read_bytes()).hexdigest()
    write_json(output / "personal-before.json", personal_before)
    write_json(output / "plan.json", plan)
    write_json(output / "targets.json", targets)
    write_json(output / "prompt-templates.json", json.loads((SITE / "data" / "ai_prompt_templates.json").read_text(encoding="utf-8")))
    with urlopen(translations.LLAMA_BASE_URL.rstrip("/") + "/v1/models", timeout=5) as response:
        observed_models = json.load(response)
    report = {"started_at": timestamp(), "model_endpoint": translations.LLAMA_BASE_URL, "observed_models": observed_models, "status": "running", "generation_only": args.generation_only, "human_evaluated_new_cases": 0}
    write_json(output / "report.json", report)
    cases, candidates = plan["cases"], []
    run = None
    try:
        with patch.object(translations, "AI_DIR", output / "ai"), local_server() as port:
            run = LiveRun(port, output)
            with patch.object(translations, "urlopen", run.observe_urlopen):
                if not args.generation_only:
                    early = run.payload(cases[0])
                    ack = run.cancel(early)
                    early_result = run.post("/api/sentence-translation", early)
                    require(early_result["status"] == 409 and not run.calls and not run.records(), early_result)
                    run.checked("cancel_before_generation", acknowledgement=ack, generation_status=early_result["status"], model_calls=0, records=0)
                    cancellation_case = cases[min(5, len(cases) - 1)]
                    completed, result = run.cancellation(cancellation_case, cases[0], cancel_waiter=False)
                    record = result["body"]["record"]
                    candidates.append(candidate(cases[0], targets[cases[0]["id"]], record))
                    write_json(output / "candidates.json", candidates)
                    completed_ack = run.cancel(completed)
                    require(completed_ack["body"].get("state") == "completed" and completed_ack["body"].get("cancelled") is False, completed_ack)
                    run.checked("cancel_after_commit", acknowledgement=completed_ack)
                    run.cancellation(cancellation_case, cases[1], cancel_waiter=True)
                for case in cases if args.generation_only else cases[1:]:
                    started = run.elapsed()
                    result = run.post("/api/sentence-translation", run.payload(case))
                    require(result["status"] == 200 and result["body"].get("cached") is False, {"sample": case["id"], "result": result})
                    record = result["body"]["record"]
                    candidates.append(candidate(case, targets[case["id"]], record))
                    write_json(output / "candidates.json", candidates)
                    write_review(output, candidates, targets)
                    run.checked(f"generate_{case['id']}", quality_state=record["quality_state"], revision_count=record["revision_count"], elapsed_seconds=round(run.elapsed() - started, 3), record_id=record["id"])
                # Cache only records that the existing production policy permits.
                cache_case = next((case for case in candidates if case["candidate_provenance"]["quality_state"] in {"critic_pass", "critic_pass_after_revision"}), None)
                require(len(run.records()) == len(cases), "isolated storage must contain exactly the successful candidates")
                if cache_case is not None:
                    before_calls = len(run.calls)
                    cached = run.post("/api/sentence-translation", run.payload(cache_case, regenerate=False))
                    require(cached["status"] == 200 and cached["body"].get("cached") is True, cached)
                    require(cached["body"]["record"]["id"] == cache_case["candidate_record_id"] and len(run.calls) == before_calls, "cache invoked model or returned a different record")
                    run.checked("cache_without_model", record_id=cache_case["candidate_record_id"], new_model_calls=0, stored_records=len(cases))
                    report["cache_check"] = "passed"
                else:
                    report["cache_check"] = "skipped_no_automatically_eligible_candidate"
                report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        if run:
            # local_server has cancelled outstanding work and joined HTTP handlers.
            for worker in run.threads:
                worker.join(timeout=1)
            report.update({"checks": run.checks, "model_calls": run.calls, "elapsed_seconds": run.elapsed()})
        report.update({"finished_at": timestamp(), "generated_candidates": len(candidates), "automated_quality_states": dict(Counter(case["candidate_provenance"]["quality_state"] for case in candidates)), "personal_files_unchanged": personal_before == personal_fingerprints(), "goldset_unchanged": goldset_before == hashlib.sha256(goldset_path.read_bytes()).hexdigest()})
        write_json(output / "report.json", report)
        write_review(output, candidates, targets)
    require(report["personal_files_unchanged"], "production personal files changed during validation; inspect before attributing the writer")
    require(report["goldset_unchanged"], "human goldset changed during validation")
    print(json.dumps({key: report[key] for key in ("status", "generated_candidates", "automated_quality_states", "personal_files_unchanged", "elapsed_seconds")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
