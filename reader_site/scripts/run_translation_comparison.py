"""Run the same supplied targets against separate reader-site checkouts.

Case annotations never enter model input. Segmentation is deliberately bypassed:
the supplied full source_text is the exact target in both baseline and current.
Results are local experiment records, never AI-review or human-goldset records.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit


SITE = Path(__file__).resolve().parents[1]
REQUIRED_CASE_FIELDS = {"case_id", "group", "corpus_id", "work_id", "variant_id", "work_title", "source_text"}
OPTIONAL_CASE_FIELDS = {"context_before", "context_after", "review_focus"}
MODEL_INPUT_FIELDS = ("corpus_id", "work_id", "variant_id", "work_title", "source_text", "context_before", "context_after")
MAX_CONTEXT_CHARS = 6000
RESERVED_MARKER = re.compile(r"</?(?:TARGET_SENTENCE|CONTEXT_SEGMENT)\b", re.IGNORECASE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field: {key}")
        result[key] = value
    return result


def model_input(case: dict[str, Any]) -> dict[str, str]:
    return {field: case.get(field, "") for field in MODEL_INPUT_FIELDS}


def make_target(case: dict[str, Any]) -> dict[str, Any]:
    supplied = model_input(case)
    identity = sha256_text(canonical_json(supplied))
    segment_id = "comparison-" + identity[:24]
    sentence_id = segment_id + ".s001"
    source = supplied["source_text"]
    blocks: list[str] = []
    context_segments: list[dict[str, str]] = []
    for position, text in (("previous", supplied["context_before"]), ("target", source), ("next", supplied["context_after"])):
        if not text:
            continue
        content = "<TARGET_SENTENCE>" + text + "</TARGET_SENTENCE>" if position == "target" else text
        blocks.append(f'<CONTEXT_SEGMENT position="{position}">\n{content}\n</CONTEXT_SEGMENT>')
        context_segments.append({
            "segment_id": segment_id if position == "target" else segment_id + "." + position,
            "position": position, "source_text_sha256": sha256_text(text),
        })
    context = "\n\n".join(blocks)
    require(len(context) <= MAX_CONTEXT_CHARS, f"{case['case_id']}: supplied context exceeds {MAX_CONTEXT_CHARS} characters; shorten it explicitly")
    require(context.count("<TARGET_SENTENCE>") == context.count("</TARGET_SENTENCE>") == 1, "exactly one target marker pair is required")
    return {
        "corpus_id": supplied["corpus_id"], "work_id": supplied["work_id"], "variant_id": supplied["variant_id"],
        "work_title": supplied["work_title"], "segment_id": segment_id, "sentence_id": sentence_id,
        "label": "Comparison target",
        "target_url": f"/work/{quote(supplied['corpus_id'], safe='')}/{quote(supplied['work_id'], safe='')}#{sentence_id}",
        "source_text": source, "sentence_text": source,
        "source_text_sha256": sha256_text(source), "sentence_text_sha256": sha256_text(source),
        "source_text_chars": len(source), "sentence_text_chars": len(source),
        "source_context": context, "source_context_sha256": sha256_text(context),
        "context_segments": context_segments,
    }


def load_cases(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_json_object)
    require(isinstance(payload, dict) and set(payload) == {"schema_version", "cases"}, "case file requires exactly schema_version and cases")
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1, "case schema_version must be 1")
    cases = payload["cases"]
    require(isinstance(cases, list) and bool(cases), "cases must be a non-empty list")
    seen_ids: set[str] = set()
    source_groups: dict[str, str] = {}
    seen_inputs: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        require(isinstance(case, dict), f"{label} must be an object")
        require(REQUIRED_CASE_FIELDS <= set(case) <= REQUIRED_CASE_FIELDS | OPTIONAL_CASE_FIELDS, f"{label} has missing or unexpected fields")
        for field, value in case.items():
            require(isinstance(value, str), f"{label}.{field} must be a string")
            if field in REQUIRED_CASE_FIELDS - {"variant_id"}:
                require(bool(value.strip()), f"{label}.{field} must not be empty")
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", case["case_id"]) is not None, f"{label}.case_id is invalid")
        require(case["case_id"] not in seen_ids, f"duplicate case_id: {case['case_id']}")
        seen_ids.add(case["case_id"])
        require(case["group"] in ("regression", "reserved_evaluation"), f"{label}.group is invalid")
        for field in ("source_text", "context_before", "context_after"):
            require(not RESERVED_MARKER.search(case.get(field, "")), f"{label}.{field} contains a reserved context marker")
        normalized_source = " ".join(unicodedata.normalize("NFC", case["source_text"]).split())
        previous_group = source_groups.get(normalized_source)
        require(previous_group is None or previous_group == case["group"], "regression and reserved_evaluation share the same normalized source_text")
        source_groups[normalized_source] = case["group"]
        supplied = canonical_json(model_input(case))
        require(supplied not in seen_inputs, f"duplicate model input under another case_id: {case['case_id']}")
        seen_inputs.add(supplied)
        make_target(case)
    return cases, hashlib.sha256(raw).hexdigest()


def git_metadata(site: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "-C", str(site), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        if commit.returncode:
            return {"commit": None, "worktree_dirty": None, "status": "not_a_git_checkout"}
        status = subprocess.run(["git", "-C", str(site), "status", "--porcelain", "--untracked-files=normal"], capture_output=True, text=True, timeout=10, check=False)
        return {"commit": commit.stdout.strip(), "worktree_dirty": bool(status.stdout) if status.returncode == 0 else None,
                "status": "identified" if status.returncode == 0 else "commit_only"}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "worktree_dirty": None, "status": "git_unavailable"}


def implementation_metadata(site: Path) -> dict[str, Any]:
    paths = sorted((site / "services").rglob("*.py"))
    paths += [site / "sentence_units.py", site / "data" / "ai_prompt_templates.json", site / "data" / "translation_profiles.json"]
    files = [{"path": path.relative_to(site).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in paths if path.is_file()]
    return {"sha256": sha256_text(canonical_json(files)), "files": files}


def import_pipeline(site: Path, seed: int) -> tuple[ModuleType, list[str]]:
    # Each CLI invocation uses one checkout. Refuse a cached module from another
    # site instead of accidentally comparing the current implementation twice.
    previous = sys.modules.get("services.sentence_translations")
    if previous is not None:
        require(Path(previous.__file__).resolve() == (site / "services" / "sentence_translations.py").resolve(), "a different reader site is already imported; run each label in a separate process")
    sys.path.insert(0, str(site))
    pipeline = importlib.import_module("services.sentence_translations")
    require(Path(pipeline.__file__).resolve() == (site / "services" / "sentence_translations.py").resolve(), "translation module did not come from --site")
    require(callable(getattr(pipeline, "build_sentence_prompt_bundle", None)) and callable(getattr(pipeline, "run_translation_pipeline", None)), "site lacks the required comparison pipeline API")
    overrides: list[str] = []
    for owner in (pipeline, sys.modules.get("services.translation_commentary")):
        if owner is None:
            continue
        for name in ("GENERATION_PARAMETERS", "CRITIC_GENERATION_PARAMETERS", "COMMENTARY_GENERATION_PARAMETERS"):
            parameters = getattr(owner, name, None)
            if isinstance(parameters, dict):
                setattr(owner, name, {**parameters, "seed": seed})
                overrides.append(owner.__name__ + "." + name)
    return pipeline, overrides


def model_metadata(pipeline: ModuleType) -> dict[str, Any]:
    endpoint = str(getattr(pipeline, "LLAMA_BASE_URL", ""))
    parsed = urlsplit(endpoint)
    # Retain the configured endpoint without embedding URL credentials or queries.
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = hostname + (f":{parsed.port}" if parsed.port is not None else "")
    return {
        "provider": "local_llama_cpp", "name": getattr(pipeline, "MODEL_NAME", None),
        "runtime": getattr(pipeline, "MODEL_RUNTIME", None), "file_sha256": getattr(pipeline, "MODEL_FILE_SHA256", None) or None,
        "endpoint": urlunsplit((parsed.scheme, netloc, parsed.path, "", "")),
        "identity_status": "configured_not_runtime_attested",
    }


def pipeline_errors(output: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    critics = output.get("critic", {})
    if isinstance(critics, dict):
        for stage, result in critics.items():
            if isinstance(result, dict) and result.get("verdict") == "error":
                errors.append({"stage": str(result.get("stage") or stage), "type": "PipelineStageError", "message": str(result.get("error") or "critic failed")})
    audit = output.get("commentary_audit")
    if isinstance(audit, dict) and audit.get("status") in ("error", "not_run"):
        errors.append({"stage": "commentary_audit", "type": "PipelineStageError", "message": str(audit.get("error") or "commentary audit did not complete")})
    if output.get("quality_state") == "critic_error" and not errors:
        errors.append({"stage": "critic", "type": "PipelineStageError", "message": "quality_state=critic_error"})
    return errors


def validate_output_path(path: Path, site: Path) -> None:
    require(path.suffix == ".jsonl", "comparison output must be a .jsonl file")
    require(path.name != "translation_ai_reviews.jsonl" and not path.name.endswith("_sentence_translations.jsonl"), "comparison output must be separate from AI history")
    protected = [root / "data" / name for root in (SITE, site) for name in ("ai", "notes")]
    protected.extend(Path(value) for name in ("PHILO_AI_DIR", "PHILO_NOTES_DIR") if (value := os.environ.get(name)))
    require(not any(path.resolve().is_relative_to(root.resolve()) for root in protected), "comparison output cannot be written into AI or personal-note storage")


def run(args: argparse.Namespace) -> int:
    site = args.site.resolve()
    require((site / "services" / "sentence_translations.py").is_file(), "--site must contain services/sentence_translations.py")
    require(bool(args.label.strip()), "--label must not be empty")
    require(0 <= args.seed <= 2_147_483_647, "--seed must be between 0 and 2147483647")
    cases, cases_sha256 = load_cases(args.cases)
    if args.case_id:
        require(len(args.case_id) == len(set(args.case_id)), "duplicate --case-id selection")
        missing = set(args.case_id) - {case["case_id"] for case in cases}
        require(not missing, "unknown case_id: " + ", ".join(sorted(missing)))
        cases = [case for case in cases if case["case_id"] in args.case_id]
    validate_output_path(args.output, site)
    require(not args.output.exists(), "output already exists; choose a new file to preserve earlier results")
    execution = {
        "run_id": str(uuid.uuid4()), "label": args.label, "git": git_metadata(site),
        "implementation": implementation_metadata(site), "python_version": sys.version.split()[0],
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "seed": args.seed, "with_model": args.with_model,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    interrupted = False
    pipeline: ModuleType | None = None
    import_error: Exception | None = None
    overrides: list[str] = []
    # Exclusive create happens before loading or calling the model.
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        if args.with_model:
            try:
                pipeline, overrides = import_pipeline(site, args.seed)
            except Exception as exc:
                import_error = exc
        for case in cases:
            target = make_target(case)
            record = {
                "schema_version": 1, "record_type": "translation_comparison_result", "execution": execution,
                "case_id": case["case_id"], "group": case["group"], "review_focus": case.get("review_focus", ""),
                "cases_file_sha256": cases_sha256, "case_sha256": sha256_text(canonical_json(case)),
                "model_input_sha256": sha256_text(canonical_json(model_input(case))),
                "target_origin": "supplied_case_text", "segmentation_applied": False,
                "target": target, "target_sha256": sha256_text(canonical_json(target)),
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "execution_status": "validated_only", "model": None, "seed_overrides": overrides,
                "prompt_bundle": None, "output": None, "errors": [],
                "human_evaluation_status": "not_performed",
                "measurement_note": "No model inference was requested. Translation quality has not been measured.",
            }
            if args.with_model:
                stage = "pipeline_import"
                try:
                    if import_error is not None:
                        raise import_error
                    assert pipeline is not None
                    record["model"] = model_metadata(pipeline)
                    stage = "prompt_build"
                    bundle = pipeline.build_sentence_prompt_bundle(copy.deepcopy(target))
                    require(isinstance(bundle, dict), "pipeline prompt bundle must be an object")
                    canonical_json(bundle)
                    require(bundle.get("source_context") == target["source_context"], "pipeline changed the supplied source context")
                    require(bundle.get("generation_parameters", {}).get("seed") == args.seed, "pipeline did not apply the requested translation seed")
                    record["prompt_bundle"] = bundle
                    stage = "model_pipeline"
                    output = pipeline.run_translation_pipeline(bundle)
                    require(isinstance(output, dict) and isinstance(output.get("translation"), str) and bool(output["translation"].strip()), "pipeline returned no translation")
                    canonical_json(output)
                    record["output"] = output
                    record["errors"] = pipeline_errors(output)
                    record["execution_status"] = "partial_failure" if record["errors"] else "completed"
                    record["measurement_note"] = "Generated output and automatic audits are retained for review. No human quality scores were assigned."
                except KeyboardInterrupt:
                    record["execution_status"] = "interrupted"
                    record["errors"] = [{"stage": stage, "type": "KeyboardInterrupt", "message": "Run interrupted; earlier case results are retained."}]
                    record["measurement_note"] = "Execution did not complete. Translation quality cannot be scored from this run."
                    interrupted = True
                except Exception as exc:
                    record["execution_status"] = "failed"
                    record["errors"] = [{"stage": stage, "type": type(exc).__name__, "message": str(exc)[:4000]}]
                    record["measurement_note"] = "Execution failed; check the configured model server and recorded error. Translation quality cannot be scored from this run."
                failed = failed or record["execution_status"] != "completed"
            record["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            handle.write(canonical_json(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            print(f"{case['case_id']}: {record['execution_status']}", flush=True)
            if interrupted:
                break
    if not args.with_model:
        print("Inputs validated. No model inference or quality scoring was performed.")
    elif failed:
        print("Some model stages failed or were interrupted. Partial results were retained; no human quality scores were assigned.")
    else:
        print("Model outputs retained for review. No human quality scores were assigned.")
    return 130 if interrupted else 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--cases", type=Path, required=True, help="Local UTF-8 JSON case file; schema_version=1.")
    parser.add_argument("--site", type=Path, default=SITE, help="Baseline or current reader_site checkout.")
    parser.add_argument("--label", required=True, help="Output label only; never included in model input.")
    parser.add_argument("--output", type=Path, required=True, help="New isolated JSONL file, preferably under data/runtime.local/comparisons.")
    parser.add_argument("--case-id", action="append", help="Select an exact case ID; repeat for more than one.")
    parser.add_argument("--seed", type=int, default=0, help="Fixed seed applied to each available generation stage.")
    parser.add_argument("--with-model", action="store_true", help="Explicitly run the configured model; otherwise validate inputs only.")
    args = parser.parse_args()
    try:
        status = run(args)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Translation comparison failed: {exc}\n")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
