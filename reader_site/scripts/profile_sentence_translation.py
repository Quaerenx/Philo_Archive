"""Opt-in stage/token profiling through an isolated Reader and real local Gemma.

Model bytes, production return values and generation parameters remain unchanged.
The report contains only timing/count metadata; private candidates stay in the
new runtime.local output directory. Pipeline and model-stage times overlap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


SITE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SITE))

from check_translation_live import LiveRun, candidate, load_targets, local_server, timestamp, write_json  # noqa: E402
import server  # noqa: E402
from services import sentence_translations as translations  # noqa: E402
from services import translation_jobs as jobs  # noqa: E402


BASE_STAGES = (
    "source_target", "approved_lookup", "prompt_build", "auto_cache_lookup", "model_slot_wait",
    "pipeline", "record_build", "record_store",
)
MODEL_STAGES = ("translator", "initial_critic", "revision", "final_critic")
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")
TIMING_KEYS = (
    "cache_n", "prompt_n", "prompt_ms", "prompt_per_token_ms", "prompt_per_second",
    "predicted_n", "predicted_ms", "predicted_per_token_ms", "predicted_per_second",
)
FINISH_REASONS = {"stop", "length", "tool_calls", "function_call", "content_filter"}
QUALITY_STATES = {"critic_pass", "critic_pass_after_revision", "needs_human_review", "critic_error"}


class ProfileError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ProfileError(code)


def response_metadata(raw):
    """Return an explicit allowlist; never retain model text or unknown fields."""
    result = dict.fromkeys(("usage", "timings", "finish_reason", "content_chars", "reasoning_content_chars", "reasoning_chars"))
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return result
    if not isinstance(payload, dict):
        return result
    usage = payload.get("usage")
    if isinstance(usage, dict):
        selected = {key: usage[key] for key in USAGE_KEYS if type(usage.get(key)) is int and usage[key] >= 0}
        if selected:
            result["usage"] = selected
    timings = payload.get("timings")
    if isinstance(timings, dict):
        def numeric(value):
            if type(value) not in {int, float} or value < 0:
                return False
            try:
                return math.isfinite(value)
            except OverflowError:
                return False
        selected = {key: timings[key] for key in TIMING_KEYS if numeric(timings.get(key))}
        if selected:
            result["timings"] = selected
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        if isinstance(choice.get("finish_reason"), str) and choice["finish_reason"] in FINISH_REASONS:
            result["finish_reason"] = choice["finish_reason"]
        message = choice.get("message")
        if isinstance(message, dict):
            for key in ("content", "reasoning_content", "reasoning"):
                if isinstance(message.get(key), str):
                    result[f"{key}_chars"] = len(message[key])
    return result


class ResponseObserver:
    def __init__(self, response, event):
        self.response = response
        self.event = event
        self.parts = []
        self.bytes_seen = 0
        self.capture_available = True

    def __getattr__(self, name):
        return getattr(self.response, name)

    def read(self, *args, **kwargs):
        started = time.perf_counter()
        value = self.response.read(*args, **kwargs)
        self.event["response_read_seconds"] = self.event.get("response_read_seconds", 0) + time.perf_counter() - started
        if self.capture_available and isinstance(value, bytes):
            self.bytes_seen += len(value)
            if self.bytes_seen <= 8 * 1024 * 1024:
                self.parts.append(value)
            else:
                self.capture_available = False
                self.parts.clear()
        return value

    def finish(self):
        started = time.perf_counter()
        if self.capture_available and self.parts:
            self.event["response_metadata"] = response_metadata(b"".join(self.parts))
        else:
            self.event["response_metadata"] = response_metadata(b"")
        self.parts.clear()
        self.event["metadata_parse_seconds"] = time.perf_counter() - started


class Measurements:
    def __init__(self):
        self.rows = []
        self.requests = {}
        self.local = threading.local()
        self.original_urlopen = translations.urlopen

    def timed(self, function, stage):
        def call(*args, **kwargs):
            row = getattr(self.local, "row", None)
            if row is None:
                return function(*args, **kwargs)
            selected = stage(row) if callable(stage) else stage
            previous_stage = getattr(self.local, "model_stage", None)
            if selected in MODEL_STAGES:
                self.local.model_stage = selected
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - started
                entry = row["stages"].setdefault(selected, {"calls": 0, "seconds": 0.0})
                entry["calls"] += 1
                entry["seconds"] += elapsed
                self.local.model_stage = previous_stage
        return call

    def handler(self, function):
        def call(payload, *args, **kwargs):
            row = self.requests.get(payload.get("request_id"))
            if row is None:
                return function(payload, *args, **kwargs)
            self.local.row = row
            started = time.perf_counter()
            try:
                return function(payload, *args, **kwargs)
            finally:
                row["service_wall_seconds"] = time.perf_counter() - started
                self.local.row = None
        return call

    def critic_stage(self, row):
        count = row.get("critic_calls", 0)
        row["critic_calls"] = count + 1
        return "initial_critic" if count == 0 else "final_critic"

    def job(self, original):
        @contextmanager
        def enter(*args, **kwargs):
            row = getattr(self.local, "row", None)
            started = time.perf_counter()
            with original(*args, **kwargs) as value:
                if row is not None:
                    row["stages"]["model_slot_wait"] = {"calls": 1, "seconds": time.perf_counter() - started}
                yield value
        return enter

    @contextmanager
    def observe_urlopen(self, request, **kwargs):
        row = getattr(self.local, "row", None)
        if row is None:
            with self.original_urlopen(request, **kwargs) as response:
                yield response
            return
        current = jobs._current.get()
        require(current is not None and self.requests.get(current.request_id) is row, "model_request_attribution_failed")
        event = {"stage": getattr(self.local, "model_stage", None) or "unclassified"}
        row["model_calls"].append(event)
        started = time.perf_counter()
        observed = None
        try:
            with self.original_urlopen(request, **kwargs) as response:
                event["headers_seconds"] = time.perf_counter() - started
                event["http_status"] = response.status
                observed = ResponseObserver(response, event)
                yield observed
        finally:
            event["transport_wall_seconds"] = time.perf_counter() - started
            if observed is not None:
                observed.finish()

    @contextmanager
    def instrument(self):
        names = {
            "sentence_target_bundle": "source_target", "find_reviewed_record": "approved_lookup",
            "build_sentence_prompt_bundle": "prompt_build", "find_cached_record": "auto_cache_lookup",
            "run_translation_pipeline": "pipeline", "build_record": "record_build", "append_record": "record_store",
            "call_llama_server": "translator", "call_revision_server": "revision", "call_critic_server": self.critic_stage,
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(server, "sentence_translation_from_payload", self.handler(server.sentence_translation_from_payload)))
            for name, stage in names.items():
                stack.enter_context(patch.object(translations, name, self.timed(getattr(translations, name), stage)))
            stack.enter_context(patch.object(translations, "translation_job", self.job(translations.translation_job)))
            stack.enter_context(patch.object(translations, "urlopen", self.observe_urlopen))
            yield

    def post(self, run, case, repetition, *, cache_probe=False):
        payload = run.payload(case, regenerate=not cache_probe)
        row = {"sample_label": case["id"], "repetition": repetition, "mode": "cache_probe" if cache_probe else "generation", "stages": {}, "model_calls": []}
        self.requests[payload["request_id"]] = row
        self.rows.append(row)
        started = time.perf_counter()
        try:
            result = run.post("/api/sentence-translation", payload)
            row["http_status"] = result["status"]
            require(result["status"] == 200 and isinstance(result.get("body"), dict), "reader_translation_request_failed")
            require(result["body"].get("cached") is cache_probe, "unexpected_translation_cache_state")
            record = result["body"].get("record")
            require(isinstance(record, dict), "missing_translation_record")
            if record.get("quality_state") in QUALITY_STATES:
                row["quality_state"] = record["quality_state"]
            if type(record.get("revision_count")) is int:
                row["revision_count"] = record["revision_count"]
            if cache_probe:
                require(not row["model_calls"], "cache_probe_called_model")
            return record
        finally:
            row["client_wall_seconds"] = time.perf_counter() - started
            self.requests.pop(payload["request_id"], None)

    def report_rows(self):
        result = []
        for row in self.rows:
            item = {key: value for key, value in row.items() if key != "critic_calls"}
            item["stages"] = {
                stage: {"status": "called", **row["stages"][stage]} if stage in row["stages"] else {"status": "not_called"}
                for stage in (*BASE_STAGES, *MODEL_STAGES)
            }
            base = sum(row["stages"].get(stage, {}).get("seconds", 0) for stage in BASE_STAGES)
            pipeline = row["stages"].get("pipeline", {}).get("seconds", 0)
            model_stages = sum(row["stages"].get(stage, {}).get("seconds", 0) for stage in MODEL_STAGES)
            item["base_stage_seconds"] = base
            item["pipeline_model_stage_seconds"] = model_stages
            item["pipeline_other_seconds"] = max(0, pipeline - model_stages)
            if "service_wall_seconds" in row:
                item["service_other_seconds"] = max(0, row["service_wall_seconds"] - base)
                item["http_other_seconds"] = max(0, row["client_wall_seconds"] - row["service_wall_seconds"])
            result.append(item)
        return result


def fingerprints(operational_ai):
    directories = {SITE / "data" / "ai", SITE / "data" / "notes", operational_ai}
    files = {SITE / "data" / "translation_quality_goldset.json"}
    files.update(path for directory in directories for path in directory.glob("*.jsonl") if path.is_file())
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}


def run_profile(args):
    require(1 <= args.repetitions <= 20, "invalid_repetition_count")
    output = args.output_dir.resolve()
    require(not args.output_dir.is_symlink() and output.is_relative_to((SITE / "data" / "runtime.local").resolve()), "output_must_be_private_runtime_directory")
    require(not output.exists(), "output_directory_already_exists")
    model_url = urlsplit(translations.LLAMA_BASE_URL)
    require(model_url.scheme in {"http", "https"} and model_url.hostname in {"127.0.0.1", "localhost", "::1"}, "model_endpoint_must_be_loopback")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    targets = load_targets(plan)
    selected = set(args.case_id or targets)
    require(bool(selected) and selected <= set(targets), "unknown_selected_sample")
    cases = [case for case in plan["cases"] if case["id"] in selected]
    if args.validate_plan_only:
        return {"status": "plan_valid", "selected_cases": len(cases), "repetitions": args.repetitions, "generation_requests": len(cases) * args.repetitions}
    operational_ai = translations.AI_DIR
    before = fingerprints(operational_ai)
    goldset = SITE / "data" / "translation_quality_goldset.json"
    gold_cases_before = len(json.loads(goldset.read_text(encoding="utf-8"))["cases"])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "personal-before.json", before)
    write_json(output / "plan.json", {**plan, "cases": cases})
    measurements = Measurements()
    candidates = []
    report = {
        "schema_version": 1, "started_at": timestamp(), "status": "running", "repetitions": args.repetitions,
        "selected_cases": len(cases), "pipeline_version": translations.QUALITY_PIPELINE_VERSION,
        "timing_semantics": {
            "source_preflight": "load_targets validates all plan targets before timing, warming source metadata/index caches; request source_target is warm-path timing.",
            "base_stages": "Non-overlapping service stages; pipeline includes all nested model stages.",
            "model_stages": "Nested inclusive times; do not add them again to base_stage_seconds.",
            "transport": "Nested within model stage; includes server response wait and client JSON read scope.",
            "missing_metadata": "Absent keys are unavailable, never assumed zero; no token estimation.",
            "observer_overhead": "metadata_parse_seconds is profiler JSON parsing already included in measured wall/stage time.",
            "cache_probe": "Separate HTTP request only for automatically cache-eligible candidates; it must make zero model calls.",
        },
    }
    started = time.perf_counter()
    def save_progress():
        report.update(
            elapsed_seconds=time.perf_counter() - started, requests=measurements.report_rows(),
            generated_candidates=len(candidates), model_calls=sum(len(row["model_calls"]) for row in measurements.rows),
        )
        write_json(output / "profile.json", report)
    save_progress()
    try:
        with patch.object(translations, "AI_DIR", output / "ai"), local_server() as port:
            run = LiveRun(port, output)
            with measurements.instrument():
                for repetition in range(1, args.repetitions + 1):
                    for case in cases:
                        record = measurements.post(run, case, repetition)
                        item = candidate(case, targets[case["id"]], record)
                        item["profile_repetition"] = repetition
                        candidates.append(item)
                        write_json(output / "candidates.json", candidates)
                        save_progress()
                        if record.get("quality_state") in {"critic_pass", "critic_pass_after_revision"}:
                            cached = measurements.post(run, case, repetition, cache_probe=True)
                            require(cached.get("id") == record.get("id"), "cache_probe_returned_other_record")
                            save_progress()
                require(len(run.records()) == len(cases) * args.repetitions, "isolated_record_count_mismatch")
        report["status"] = "passed"
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        after = fingerprints(operational_ai)
        report.update(
            finished_at=timestamp(), elapsed_seconds=time.perf_counter() - started, requests=measurements.report_rows(),
            generated_candidates=len(candidates), model_calls=sum(len(row["model_calls"]) for row in measurements.rows),
            personal_and_goldset_unchanged=before == after,
            goldset_cases_before=gold_cases_before, goldset_cases_after=len(json.loads(goldset.read_text(encoding="utf-8"))["cases"]),
        )
        if not report["personal_and_goldset_unchanged"]:
            report["status"] = "failed"
            report["error_code"] = "operational_files_changed_during_profile"
        write_json(output / "personal-after.json", after)
        write_json(output / "profile.json", report)
    require(report["personal_and_goldset_unchanged"], "operational_files_changed_during_profile")
    return {key: report[key] for key in ("status", "selected_cases", "repetitions", "generated_candidates", "model_calls", "elapsed_seconds", "personal_and_goldset_unchanged")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan", type=Path, default=SITE / "data" / "translation_quality_sample_plan.json")
    parser.add_argument("--case-id", action="append", help="Select sample IDs; keep original sample plan order each repetition.")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory under data/runtime.local; existing directories are rejected.")
    parser.add_argument("--validate-plan-only", action="store_true", help="Resolve source targets and validate the plan without creating files or calling the model.")
    args = parser.parse_args()
    try:
        summary = run_profile(args)
    except ProfileError as error:
        print(f"translation profile failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("translation profile interrupted", file=sys.stderr)
        return 130
    except Exception:
        print("translation profile failed: runtime_or_input_error", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
