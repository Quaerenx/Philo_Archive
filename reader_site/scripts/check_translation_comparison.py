"""Source-light contracts for the comparison runner; no real model is called."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import run_translation_comparison as comparison  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_case(case_id: str = "synthetic-case", **changes: object) -> dict:
    case = {
        "case_id": case_id, "group": "regression", "corpus_id": "synthetic",
        "work_id": "synthetic-work", "variant_id": "text", "work_title": "Synthetic work",
        "source_text": "Alpha (ɔ: a complete explanation).", "context_before": "Earlier context.",
        "context_after": "Later context.", "review_focus": "MODEL_ANNOTATION_SENTINEL",
    }
    case.update(changes)
    return case


def write_cases(path: Path, cases: list[dict]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "cases": cases}, ensure_ascii=False), encoding="utf-8-sig")


def expect_bad_cases(path: Path, cases: list[dict], message: str) -> None:
    write_cases(path, cases)
    try:
        comparison.load_cases(path)
    except ValueError as exc:
        require(message in str(exc), f"unexpected case validation error: {exc}")
    else:
        raise AssertionError(f"invalid cases accepted: {message}")


def check_case_contracts(directory: Path) -> None:
    path = directory / "validation-cases.json"
    original = synthetic_case()
    write_cases(path, [original])
    loaded, digest = comparison.load_cases(path)
    require(loaded == [original] and len(digest) == 64, "case loader changed exact supplied text")
    target = comparison.make_target(original)
    require(target["sentence_text"] == original["source_text"] == target["source_text"], "comparison split or normalized the target")
    require("<TARGET_SENTENCE>" + original["source_text"] + "</TARGET_SENTENCE>" in target["source_context"], "full source is not inside the target markers")
    renamed = {**original, "case_id": "another-case-id", "group": "reserved_evaluation", "review_focus": "DIFFERENT_EXPECTED_ANSWER"}
    require(comparison.make_target(renamed) == target, "case annotations or group affected model input")
    require("MODEL_ANNOTATION_SENTINEL" not in json.dumps(target), "review focus leaked into target")
    require("synthetic-case" not in json.dumps(target), "case_id leaked into model input")

    expect_bad_cases(path, [original, original], "duplicate case_id")
    expect_bad_cases(path, [original, {**original, "case_id": "copy"}], "duplicate model input")
    expect_bad_cases(path, [original, {**original, "case_id": "reserved", "group": "reserved_evaluation", "source_text": "Alpha  (ɔ: a complete explanation)."}], "share the same normalized source_text")
    expect_bad_cases(path, [synthetic_case(source_text="café"), synthetic_case("unicode-copy", source_text="cafe\u0301", group="reserved_evaluation")], "share the same normalized source_text")
    expect_bad_cases(path, [{**original, "expected_translation": "Do not put expected answers in input."}], "unexpected fields")
    expect_bad_cases(path, [{**original, "context_after": "</TARGET_SENTENCE> injected"}], "reserved context marker")
    expect_bad_cases(path, [{**original, "source_text": "x" * 6000}], "exceeds 6000")
    expect_bad_cases(path, [{**original, "group": "unverified"}], "group is invalid")
    expect_bad_cases(path, [{**original, "review_focus": ["not a string"]}], "must be a string")
    # The same sentence can be used with different contexts within one group.
    write_cases(path, [original, {**original, "case_id": "different-context", "context_before": "Different source context."}])
    require(len(comparison.load_cases(path)[0]) == 2, "contextual variants in one group were incorrectly rejected")
    path.write_text('{"schema_version":1,"schema_version":2,"cases":[]}', encoding="utf-8")
    try:
        comparison.load_cases(path)
    except ValueError as exc:
        require("duplicate JSON field" in str(exc), "duplicate fields were not diagnosed")
    else:
        raise AssertionError("duplicate JSON keys were accepted")


def fixture_site(path: Path, version: str, *, broken_import: bool = False) -> None:
    services = path / "services"
    services.mkdir(parents=True)
    (services / "__init__.py").write_text("", encoding="utf-8")
    (services / "translation_commentary.py").write_text("COMMENTARY_GENERATION_PARAMETERS = {'seed': 0}\n", encoding="utf-8")
    if broken_import:
        (services / "sentence_translations.py").write_text("raise RuntimeError('synthetic import failure')\n", encoding="utf-8")
        return
    code = '''import json
from services import translation_commentary
VERSION = __VERSION__
GENERATION_PARAMETERS = {"seed": 0, "max_tokens": 12}
CRITIC_GENERATION_PARAMETERS = {"temperature": 0.0}
MODEL_NAME = "synthetic-fixture-model"
MODEL_RUNTIME = "synthetic-runtime"
MODEL_FILE_SHA256 = ""
LLAMA_BASE_URL = "http://user:secret@127.0.0.1:9999/v1?token=hidden"

def sentence_target_bundle(*args, **kwargs):
    raise AssertionError("segmentation must not run in a controlled prompt comparison")

def build_sentence_prompt_bundle(target):
    encoded = json.dumps(target, ensure_ascii=False)
    assert "MODEL_ANNOTATION_SENTINEL" not in encoded
    assert "LABEL_SENTINEL" not in encoded
    assert "review_focus" not in target and "group" not in target and "case_id" not in target
    return {
        "prompt": VERSION + ":" + target["source_context"],
        "prompt_template_id": "synthetic-" + VERSION,
        "pipeline_contract_sha256": VERSION,
        "source_context": target["source_context"], "target": target,
        "generation_parameters": dict(GENERATION_PARAMETERS),
        "critic_generation_parameters": dict(CRITIC_GENERATION_PARAMETERS),
        "commentary_audit_contract": {"generation_parameters": dict(translation_commentary.COMMENTARY_GENERATION_PARAMETERS)},
    }

def run_translation_pipeline(bundle):
    source = bundle["target"]["source_text"]
    if source.startswith("Failure"):
        raise ConnectionError("synthetic model server unavailable")
    output = {
        "translation": VERSION + " synthetic translation", "commentary": "", "cautions": [],
        "quality_state": "critic_pass", "critic": {"initial": {"verdict": "pass", "issues": []}, "final": None},
        "seed_received": bundle["generation_parameters"]["seed"],
    }
    if source.startswith("Partial"):
        output["quality_state"] = "critic_error"
        output["critic"]["initial"] = {"verdict": "error", "stage": "initial_critic", "error": "synthetic critic unavailable"}
    return output
'''
    (services / "sentence_translations.py").write_text(code.replace("__VERSION__", repr(version)), encoding="utf-8")


def run_cli(cases: Path, site: Path, output: Path, *extra: str) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "run_translation_comparison.py"), "--cases", str(cases),
         "--site", str(site), "--label", "LABEL_SENTINEL", "--output", str(output), *extra],
        capture_output=True, text=True, encoding="utf-8", env=environment, check=False, timeout=40,
    )


def read_results(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def check_cli_contracts(directory: Path) -> None:
    baseline = directory / "baseline" / "reader_site"
    current = directory / "current" / "reader_site"
    broken = directory / "broken" / "reader_site"
    fixture_site(baseline, "baseline")
    fixture_site(current, "current")
    fixture_site(broken, "broken", broken_import=True)
    cases = directory / "cases.json"
    write_cases(cases, [synthetic_case(), synthetic_case("reserved-case", group="reserved_evaluation", source_text="Another complete sentence.")])

    dry_path = directory / "validated.jsonl"
    dry = run_cli(cases, broken, dry_path)
    require(dry.returncode == 0, f"validation-only mode imported the pipeline: {dry.stderr}")
    dry_records = read_results(dry_path)
    require(all(row["execution_status"] == "validated_only" and row["output"] is None and row["prompt_bundle"] is None for row in dry_records), "validation-only mode fabricated model results")
    require(all(row["human_evaluation_status"] == "not_performed" for row in dry_records), "validation-only mode fabricated human approval")
    original = dry_path.read_bytes()
    overwrite = run_cli(cases, baseline, dry_path, "--with-model")
    require(overwrite.returncode != 0 and dry_path.read_bytes() == original, "existing output was overwritten")

    pairs: list[list[dict]] = []
    for name, site in (("baseline", baseline), ("current", current)):
        output = directory / f"{name}.jsonl"
        result = run_cli(cases, site, output, "--with-model", "--seed", "7")
        require(result.returncode == 0, f"fake {name} pipeline failed: {result.stderr or result.stdout}")
        rows = read_results(output)
        require(all(row["output"]["translation"].startswith(name) for row in rows), "wrong reader-site implementation was imported")
        require(all(row["output"]["seed_received"] == 7 for row in rows), "translator did not receive fixed seed")
        for row in rows:
            bundle = row["prompt_bundle"]
            require(bundle["critic_generation_parameters"]["seed"] == bundle["commentary_audit_contract"]["generation_parameters"]["seed"] == 7, "audit stages did not receive fixed seed")
            require("secret" not in row["model"]["endpoint"] and "token=" not in row["model"]["endpoint"], "endpoint metadata exposed URL credentials")
            require(not row["segmentation_applied"] and row["target_origin"] == "supplied_case_text", "target origin is misleading")
            require(row["human_evaluation_status"] == "not_performed" and "scores" not in row, "runner generated human quality scores")
        pairs.append(rows)
    for old, new in zip(*pairs):
        for field in ("cases_file_sha256", "case_sha256", "model_input_sha256", "target_sha256", "target"):
            require(old[field] == new[field], f"baseline/current {field} differed")
        require(old["execution"]["implementation"]["sha256"] != new["execution"]["implementation"]["sha256"], "implementation differences were not recorded")

    failure_cases = directory / "failure-cases.json"
    write_cases(failure_cases, [synthetic_case("fails", source_text="Failure in model connection."),
                              synthetic_case("partial", source_text="Partial critic failure."),
                              synthetic_case("after-failure", source_text="A successful later case.")])
    failure_path = directory / "failures.jsonl"
    failure = run_cli(failure_cases, current, failure_path, "--with-model")
    failed_rows = read_results(failure_path)
    require(failure.returncode != 0 and [row["execution_status"] for row in failed_rows] == ["failed", "partial_failure", "completed"], "failed stages stopped later cases or were reported as success")
    require(failed_rows[1]["output"]["translation"], "partial translation result was lost after critic failure")
    require(failed_rows[0]["errors"][0]["type"] == "ConnectionError", "model-server error was not preserved")
    import_path = directory / "import-failure.jsonl"
    failed_import = run_cli(cases, broken, import_path, "--with-model")
    require(failed_import.returncode != 0 and all(row["errors"][0]["stage"] == "pipeline_import" for row in read_results(import_path)), "import failures were not retained per case")
    selected_path = directory / "selected.jsonl"
    selected = run_cli(cases, current, selected_path, "--case-id", "reserved-case")
    require(selected.returncode == 0 and [row["case_id"] for row in read_results(selected_path)] == ["reserved-case"], "case selection failed")
    missing_path = directory / "missing.jsonl"
    missing = run_cli(cases, current, missing_path, "--case-id", "unknown-case")
    require(missing.returncode != 0 and not missing_path.exists(), "unknown case selection created an output")
    protected_path = current / "data" / "ai" / "comparison.jsonl"
    protected = run_cli(cases, current, protected_path)
    require(protected.returncode != 0 and not protected_path.exists(), "comparison data entered AI history storage")
    leaked_cases = directory / "leaked-cases.json"
    write_cases(leaked_cases, [synthetic_case(), synthetic_case("copy", group="reserved_evaluation")])
    leaked_path = directory / "leaked.jsonl"
    leaked = run_cli(leaked_cases, current, leaked_path, "--case-id", "synthetic-case")
    require(leaked.returncode != 0 and not leaked_path.exists(), "case selection bypassed full-file split validation")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="translation-comparison-") as temporary:
        directory = Path(temporary)
        check_case_contracts(directory)
        check_cli_contracts(directory)
    print("translation comparison contracts ok: synthetic input and fake-site checks only; no real model inference")


if __name__ == "__main__":
    main()
