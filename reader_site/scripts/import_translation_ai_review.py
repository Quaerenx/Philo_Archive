from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.translation_ai_reviews import (  # noqa: E402
    DEFAULT_PATH,
    append_review,
    unique_json_object,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append one complete AI translation review JSON object to local-only history. Never updates human approvals.",
        allow_abbrev=False,
    )
    parser.add_argument("input", type=Path, help="UTF-8 JSON review created with build_review; no automatic text/hash repair.")
    parser.add_argument("--store", type=Path, default=DEFAULT_PATH, help="Local AI review JSONL path.")
    args = parser.parse_args()
    try:
        record = json.loads(args.input.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_json_object)
        result = append_review(record, args.store)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"AI review import failed: {exc}\n")
    outcome = "appended" if result["created"] else "already present (unchanged)"
    print(f"AI review {outcome}: {result['record']['id']}; human_approval=pending")


if __name__ == "__main__":
    main()
