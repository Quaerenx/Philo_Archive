from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SITE))

from check_ai_records_contracts import validate_record  # noqa: E402
from services.human_reviews import HumanReviewError, import_human_reviews  # noqa: E402
from services.human_review_batches import import_review_batch, publish_review_cases  # noqa: E402
from services.sentence_translations import AI_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import translation reviews; writes require --apply.", allow_abbrev=False)
    parser.add_argument("--feedback", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--candidate-ai-dir", type=Path, help="Read-only candidate model records; defaults to sibling ai/ for legacy reviews or records/ for --review-store.")
    parser.add_argument("--goldset", type=Path, help="Legacy four-dimension goldset; cannot be combined with --review-store.")
    parser.add_argument("--review-store", type=Path, help="Private five-dimension evaluation ledger. Collection alone does not publish translations.")
    parser.add_argument("--publish-case", action="append", help="Explicitly adopted case ID from --review-store; repeat to select additional cases.")
    parser.add_argument("--approved-by", help="Person authorizing adoption, separate from the original evaluator.")
    parser.add_argument("--adopted-at", help="Actual adoption processing time with timezone; never substitutes for evaluation time.")
    parser.add_argument("--ai-dir", type=Path, help="Operational AI destination for legacy import or explicit adoption; defaults to PHILO_AI_DIR or data/ai.")
    parser.add_argument("--transaction-dir", type=Path, default=SITE / "data" / "runtime.local" / "human-review-imports", help="Private backup/journal directory. Within this project use data/runtime.local; an explicitly selected external directory must remain private.")
    parser.add_argument("--apply", action="store_true", help="Apply validated changes with backups; otherwise inspect without creating files.")
    args = parser.parse_args()
    try:
        destination = args.transaction_dir.resolve()
        require_private = destination.is_relative_to(SITE.parent)
        if require_private and not destination.is_relative_to(SITE / "data" / "runtime.local"):
            raise HumanReviewError("transaction_directory_must_be_private")
        validator = lambda record: validate_record(record, Path("candidate-record"), 0)
        if (args.approved_by is not None or args.adopted_at is not None) and not args.publish_case:
            raise HumanReviewError("explicit_adoption_cases_required")
        if args.publish_case and args.review_store is None:
            raise HumanReviewError("adoption_needs_review_store")
        if not args.publish_case and (args.feedback is None or args.candidates is None):
            raise HumanReviewError("feedback_and_candidates_required")
        if args.review_store is not None:
            if args.goldset is not None:
                raise HumanReviewError("review_store_cannot_change_legacy_goldset")
            if args.ai_dir is not None and not args.publish_case:
                raise HumanReviewError("review_store_cannot_change_operational_records")
            store = args.review_store.resolve()
            if store.is_relative_to(SITE.parent) and not store.is_relative_to(SITE / "data" / "runtime.local"):
                raise HumanReviewError("review_store_must_be_private")
            if args.publish_case:
                if args.feedback is not None or args.candidates is not None:
                    raise HumanReviewError("adoption_cannot_collect_feedback")
                if args.candidate_ai_dir is None:
                    raise HumanReviewError("adoption_needs_candidate_records")
                summary = publish_review_cases(
                    args.review_store, args.publish_case, args.candidate_ai_dir, args.ai_dir or AI_DIR,
                    args.transaction_dir, approved_by=args.approved_by, adopted_at=args.adopted_at,
                    apply=args.apply, record_validator=validator,
                )
            else:
                summary = import_review_batch(
                    args.feedback, args.candidates, args.candidate_ai_dir or args.candidates.parent / "records",
                    args.review_store, args.transaction_dir, apply=args.apply, record_validator=validator,
                )
        else:
            summary = import_human_reviews(
                args.feedback, args.candidates, args.candidate_ai_dir or args.candidates.parent / "ai",
                args.ai_dir or AI_DIR, args.goldset or SITE / "data" / "translation_quality_goldset.json", args.transaction_dir, apply=args.apply,
                record_validator=validator,
            )
    except HumanReviewError as error:
        print(f"human review import failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("human review import failed: storage_or_input_error", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("human review import interrupted; rerun the same command with --apply to check recovery", file=sys.stderr)
        return 130
    print("human review import: " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
