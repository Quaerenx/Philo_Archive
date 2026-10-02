from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services import translation_ai_reviews as reviews  # noqa: E402
from services.source_targets import sha256_text  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_review(**overrides: object) -> dict:
    values = {
        "case_id": "synthetic-review-01",
        "corpus_id": "synthetic",
        "work_id": "synthetic-work",
        "source_text": "Sætning (ɔ: en forklaring).",
        "candidate_translation": "문장(즉, 설명).",
        "candidate_notes": [{"source_quote": "Sætning", "explanation": "합성 검사용 명사."}],
        "scores": dict(zip(reviews.RUBRIC_DIMENSIONS, (5, 3, 3, 4, 3))),
        "ai_verdict": "adopt_revision",
        "revised_translation": "문장이다(즉, 설명이다).",
        "reason": "Synthetic evaluation: an AI-selected revision is separate from the scored candidate.",
        "evaluation_date": "2026-10-02",
    }
    values.update(overrides)
    return reviews.build_review(**values)


def reseal(record: dict) -> dict:
    record["record_sha256"] = reviews.review_sha256(record)
    return record


def expect_invalid(record: dict, message_part: str) -> None:
    try:
        reviews.validate_review(record)
    except ValueError as exc:
        require(message_part in str(exc), f"unexpected validation error: {exc}")
    else:
        raise AssertionError(f"invalid review accepted; expected {message_part}")


def expect_append_rejected(record: dict, path: Path, message_part: str) -> None:
    original = path.read_bytes() if path.exists() else None
    try:
        reviews.append_review(record, path)
    except ValueError as exc:
        require(message_part in str(exc), f"unexpected append error: {exc}")
    else:
        raise AssertionError(f"invalid append accepted; expected {message_part}")
    current = path.read_bytes() if path.exists() else None
    require(current == original, "a rejected import changed existing history")


def check_record_contracts() -> None:
    record = synthetic_review()
    require(record["evaluator_type"] == "ai" and record["human_approval"] == "pending", "AI/human provenance missing")
    require(record["reviewer_label"] == "LSHD" and record["authored_by"] == "ChatGPT", "reviewer and author must remain distinct")
    require(record["scored_candidate"]["candidate_id"] is None, "an unknown model candidate ID was fabricated")
    require(record["scored_candidate"]["translation"] == "문장(즉, 설명).", "candidate text was overwritten by the revision")
    require(record["scores"]["logic"] == 3, "candidate score was replaced with a revision score")

    for field, invalid_value, message in (
        ("human_approval", "approved", "human_approval pending"),
        ("evaluator_type", "human", "evaluator_type must be ai"),
        ("schema_version", True, "schema_version"),
        ("rubric_id", "human_goldset_v1", "rubric_id"),
        ("rubric_dimensions", list(reversed(reviews.RUBRIC_DIMENSIONS)), "five-dimension order"),
        ("created_at", "2026-10-02T09:00:00", "timezone"),
        ("evaluation_date", "20261002", "YYYY-MM-DD"),
        ("ai_verdict", "human_confirmed", "ai_verdict"),
    ):
        invalid = copy.deepcopy(record)
        invalid[field] = invalid_value
        expect_invalid(reseal(invalid), message)
    invalid = copy.deepcopy(record)
    invalid["human_evaluation"] = {"status": "evaluated"}
    expect_invalid(reseal(invalid), "unexpected fields")
    for invalid_score in (0, 6, -1, 3.5, 4.0, True, False, None, "5"):
        invalid = copy.deepcopy(record)
        invalid["scores"]["logic"] = invalid_score
        expect_invalid(reseal(invalid), "scores.logic")
    for dimension in ("omission_addition", "terminology", "korean_readability", "note_accuracy"):
        invalid = copy.deepcopy(record)
        invalid["scores"][dimension] = None
        expect_invalid(reseal(invalid), f"scores.{dimension}")
    invalid = copy.deepcopy(record)
    invalid["scores"]["fidelity"] = invalid["scores"].pop("logic")
    expect_invalid(reseal(invalid), "scores has missing or unexpected fields")

    no_notes = synthetic_review(candidate_notes=[], scores=dict(zip(reviews.RUBRIC_DIMENSIONS, (5, 4, 4, 4, None))))
    reviews.validate_review(no_notes)
    no_notes["scores"]["note_accuracy"] = 5
    expect_invalid(reseal(no_notes), "note_accuracy must be null")
    for container, hash_field, message in (
        ("source", "text_sha256", "source.text_sha256 mismatch"),
        ("scored_candidate", "translation_sha256", "translation_sha256 mismatch"),
        ("scored_candidate", "notes_sha256", "notes_sha256 mismatch"),
    ):
        invalid = copy.deepcopy(record)
        invalid[container][hash_field] = "0" * 64
        expect_invalid(reseal(invalid), message)
    invalid = copy.deepcopy(record)
    invalid["scores"]["logic"] = 5
    expect_invalid(invalid, "record_sha256 mismatch")
    invalid = copy.deepcopy(record)
    invalid["scored_candidate"]["candidate_id"] = "unknown-new-candidate"
    expect_invalid(reseal(invalid), "canonical UUID")
    invalid = copy.deepcopy(record)
    invalid["source"]["boundary_status"] = "incomplete"
    expect_invalid(reseal(invalid), "requires ai_verdict hold")
    invalid = copy.deepcopy(record)
    invalid["revised_translation"] = None
    expect_invalid(reseal(invalid), "requires revised_translation")
    invalid = copy.deepcopy(record)
    invalid["ai_verdict"] = "accept_candidate"
    expect_invalid(reseal(invalid), "cannot adopt a revised_translation")
    invalid = copy.deepcopy(record)
    invalid["related_review_ids"] = [record["id"]]
    expect_invalid(reseal(invalid), "cannot link to itself")
    linked_id = str(uuid.uuid4())
    invalid = copy.deepcopy(record)
    invalid["related_review_ids"] = [linked_id, linked_id]
    expect_invalid(reseal(invalid), "duplicate related_review_ids")


def check_history_contracts(directory: Path) -> None:
    path = directory / "history.jsonl"
    old = synthetic_review(
        source_text="Sætning (ɔ:", candidate_translation="문장(ɔ:",
        candidate_id=str(uuid.uuid4()), source_status="incomplete", ai_verdict="hold", revised_translation=None,
        scores=dict(zip(reviews.RUBRIC_DIMENSIONS, (4, 2, 2, 3, 1))),
        reason="Synthetic incomplete-boundary review; retain as history.",
    )
    result = reviews.append_review(old, path)
    require(result["created"], "first review was not appended")
    original = path.read_bytes()
    replay = reviews.append_review(old, path)
    require(not replay["created"] and path.read_bytes() == original, "exact replay was not idempotent")
    changed = copy.deepcopy(old)
    changed["reason"] = "Attempt to overwrite the prior review."
    expect_append_rejected(reseal(changed), path, "history is immutable")
    duplicate = copy.deepcopy(old)
    duplicate["id"] = str(uuid.uuid4())
    expect_append_rejected(reseal(duplicate), path, "duplicate review content")

    for changed_field in ("source", "translation", "notes"):
        changed = copy.deepcopy(old)
        changed["id"] = str(uuid.uuid4())
        changed["reason"] = f"Reused candidate ID after changing {changed_field}."
        if changed_field == "source":
            changed["source"]["text"] += " new source"
            changed["source"]["text_sha256"] = sha256_text(changed["source"]["text"])
        elif changed_field == "translation":
            changed["scored_candidate"]["translation"] += " 새 후보"
            changed["scored_candidate"]["translation_sha256"] = sha256_text(changed["scored_candidate"]["translation"])
        else:
            changed["scored_candidate"]["notes"][0]["explanation"] += " Changed notes."
            changed["scored_candidate"]["notes_sha256"] = sha256_text(reviews.canonical_json(changed["scored_candidate"]["notes"]))
        expect_append_rejected(reseal(changed), path, "candidate_id is already bound")

    new = synthetic_review(related_review_ids=[old["id"]], source_change_reason="Synthetic parenthetical source boundary restored.")
    missing_reason = copy.deepcopy(new)
    missing_reason["source_change_reason"] = None
    expect_append_rejected(reseal(missing_reason), path, "requires source_change_reason")
    missing_link = copy.deepcopy(new)
    missing_link["related_review_ids"] = [str(uuid.uuid4())]
    expect_append_rejected(reseal(missing_link), path, "must already exist")
    wrong_case = copy.deepcopy(new)
    wrong_case["case_id"] = "another-case"
    expect_append_rejected(reseal(wrong_case), path, "same case_id")
    wrong_work = copy.deepcopy(new)
    wrong_work["source"]["work_id"] = "another-work"
    expect_append_rejected(reseal(wrong_work), path, "work_id mismatch")
    improper_supersedes = copy.deepcopy(new)
    improper_supersedes["related_review_ids"] = []
    improper_supersedes["source_change_reason"] = None
    improper_supersedes["supersedes_review_id"] = old["id"]
    expect_append_rejected(reseal(improper_supersedes), path, "same source and scored candidate")

    reviews.append_review(new, path)
    require(path.read_bytes().startswith(original), "appending a restored source changed the old record")
    history = reviews.load_reviews(path)
    require(len(history) == 2 and history[0] == old and history[1] == new, "old and new review identity or scores were conflated")
    require(history[1]["scored_candidate"]["candidate_id"] is None, "old candidate ID leaked into the new candidate")
    reevaluation = copy.deepcopy(new)
    reevaluation.update({"id": str(uuid.uuid4()), "related_review_ids": [], "source_change_reason": None,
                         "supersedes_review_id": new["id"], "reason": "A later AI evaluation of exactly the same candidate."})
    reevaluation["scores"]["logic"] = 4
    reviews.append_review(reseal(reevaluation), path)
    require(reviews.load_reviews(path)[1]["scores"]["logic"] == 3, "superseding a review mutated its earlier scores")

    unrelated_change_reason = synthetic_review(case_id="synthetic-other", source_change_reason="No linked source change exists.")
    expect_append_rejected(unrelated_change_reason, path, "requires a related review")
    invalid_path = directory / "invalid.jsonl"
    invalid_path.write_text('{"incomplete":', encoding="utf-8")
    expect_append_rejected(synthetic_review(), invalid_path, "invalid.jsonl:1")
    tampered = copy.deepcopy(new)
    tampered["reason"] = "An unsealed edit of prior history."
    invalid_path.write_text(json.dumps(tampered, ensure_ascii=False) + "\n", encoding="utf-8")
    expect_append_rejected(synthetic_review(), invalid_path, "record_sha256 mismatch")
    invalid_path.write_text('{"schema_version": 1, "schema_version": 2}\n', encoding="utf-8")
    expect_append_rejected(synthetic_review(), invalid_path, "duplicate JSON field")
    invalid_path.write_text(json.dumps(old) + "\n" + json.dumps(old) + "\n", encoding="utf-8")
    expect_append_rejected(synthetic_review(), invalid_path, "duplicate review id")


def check_cli_and_concurrent_imports(directory: Path) -> None:
    script = SITE / "scripts" / "import_translation_ai_review.py"
    path = directory / "concurrent.jsonl"
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    inputs: list[Path] = []
    processes: list[subprocess.Popen] = []
    for index in range(4):
        source_path = directory / f"input-{index}.json"
        source_path.write_text(json.dumps(synthetic_review(case_id=f"synthetic-concurrent-{index}"), ensure_ascii=False), encoding="utf-8-sig")
        inputs.append(source_path)
        processes.append(subprocess.Popen(
            [sys.executable, "-B", str(script), str(source_path), "--store", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=environment,
        ))
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=40)
            require(process.returncode == 0, f"concurrent import failed: {stderr or stdout}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
    require(len(reviews.load_reviews(path)) == 4, "concurrent CLI imports lost or duplicated reviews")
    previous = path.read_bytes()
    replay = subprocess.run(
        [sys.executable, "-B", str(script), str(inputs[0]), "--store", str(path)],
        capture_output=True, text=True, encoding="utf-8", env=environment, timeout=40, check=False,
    )
    require(replay.returncode == 0 and "already present" in replay.stdout, f"CLI replay failed: {replay.stderr}")
    require(path.read_bytes() == previous, "CLI replay changed stored history")
    bad_input = directory / "input-invalid.json"
    bad = synthetic_review()
    bad["human_approval"] = "approved"
    bad_input.write_text(json.dumps(reseal(bad)), encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-B", str(script), str(bad_input), "--store", str(path)],
        capture_output=True, text=True, encoding="utf-8", env=environment, timeout=40, check=False,
    )
    require(failed.returncode != 0 and "human_approval pending" in failed.stderr, "CLI accepted an AI record as human-approved")
    require(path.read_bytes() == previous, "failed CLI import changed stored history")


def check_contracts() -> None:
    check_record_contracts()
    with tempfile.TemporaryDirectory(prefix="translation-ai-reviews-") as temporary:
        directory = Path(temporary)
        check_history_contracts(directory)
        check_cli_and_concurrent_imports(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check AI translation review storage with synthetic cases, then validate local review history.", allow_abbrev=False)
    parser.add_argument("--path", type=Path, default=reviews.DEFAULT_PATH, help="AI review JSONL path; missing default history is allowed.")
    parser.add_argument("--require-records", action="store_true", help="Fail unless at least one valid local review exists.")
    args = parser.parse_args()
    check_contracts()
    records = reviews.load_reviews(args.path)
    require(not args.require_records or bool(records), "no AI review records found")
    print(f"translation AI reviews ok: synthetic contracts passed; {len(records)} local reviews, all human_approval=pending")


if __name__ == "__main__":
    main()
