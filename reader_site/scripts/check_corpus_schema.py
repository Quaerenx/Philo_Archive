from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"


@dataclass(frozen=True)
class CorpusFiles:
    corpus_id: str
    metadata: Path
    segments: Path


CORPORA = [
    CorpusFiles("nietzsche", DATA / "nietzsche_metadata.json", DATA / "nietzsche_segments.jsonl"),
    CorpusFiles("bible", DATA / "bible_metadata.json", DATA / "bible_segments.jsonl"),
    CorpusFiles("kierkegaard", DATA / "kierkegaard_metadata.json", DATA / "kierkegaard_segments.jsonl"),
    CorpusFiles("wittgenstein", DATA / "wittgenstein_metadata.json", DATA / "wittgenstein_segments.jsonl"),
]

METADATA_TOP_LEVEL_KEYS = {"schema_version", "corpus_id", "generated_at", "works"}
WORK_KEYS = {"corpus_id", "work_id", "title", "work_url", "language", "segment_scheme", "variant_ids", "concept_ids"}
SEGMENT_KEYS = {
    "schema_version",
    "corpus_id",
    "work_id",
    "variant_id",
    "segment_id",
    "segment_type",
    "order",
    "label",
    "text_raw",
    "text_preview",
    "url",
}


class SchemaCheck:
    def __init__(self, max_errors: int) -> None:
        self.errors: list[str] = []
        self.max_errors = max_errors

    def require(self, condition: bool, message: str) -> None:
        if condition:
            return
        self.errors.append(message)
        if len(self.errors) >= self.max_errors:
            raise AssertionError(self.report())

    def report(self) -> str:
        return "\n".join(self.errors)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AssertionError(f"{path.name} must be a JSON object")
    return payload


def normalize_works(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(work_id): work for work_id, work in value.items() if isinstance(work, dict)}


def variant_ids_for(work: dict[str, Any]) -> set[str]:
    ids = work.get("variant_ids", [])
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids}


def validate_metadata(check: SchemaCheck, corpus: CorpusFiles) -> dict[str, dict[str, Any]]:
    check.require(corpus.metadata.exists(), f"{corpus.corpus_id}: missing metadata file")
    metadata = load_metadata(corpus.metadata)
    missing_top_keys = sorted(METADATA_TOP_LEVEL_KEYS - set(metadata))
    check.require(not missing_top_keys, f"{corpus.corpus_id}: metadata missing {missing_top_keys}")
    check.require(metadata.get("schema_version") == 1, f"{corpus.corpus_id}: metadata.schema_version must be 1")
    check.require(metadata.get("corpus_id") == corpus.corpus_id, f"{corpus.corpus_id}: metadata.corpus_id mismatch")

    works = normalize_works(metadata.get("works"))
    check.require(bool(works), f"{corpus.corpus_id}: metadata.works must be a non-empty object")
    for key, work in works.items():
        context = f"{corpus.corpus_id}.{key}"
        required_keys = set(WORK_KEYS)
        if not is_non_empty_string(work.get("title")):
            required_keys.discard("title")
            check.require(is_non_empty_string(work.get("display_title")), f"{context}: title or display_title required")
        missing_work_keys = sorted(required_keys - set(work))
        check.require(not missing_work_keys, f"{context}: work missing {missing_work_keys}")
        check.require(work.get("corpus_id") == corpus.corpus_id, f"{context}: work.corpus_id mismatch")
        check.require(work.get("work_id") == key, f"{context}: work_id must match works key")
        check.require(str(work.get("work_url", "")).startswith(f"/work/{corpus.corpus_id}/"), f"{context}: invalid work_url")
        check.require(isinstance(work.get("variant_ids"), list), f"{context}: variant_ids must be list")
        check.require(isinstance(work.get("concept_ids"), list), f"{context}: concept_ids must be list")
        check.require(is_non_empty_string(work.get("segment_scheme")), f"{context}: segment_scheme required")
        variants = work.get("variants", [])
        if variants:
            check.require(isinstance(variants, list), f"{context}: variants must be list")
            ids = variant_ids_for(work)
            for index, variant in enumerate(variants):
                variant_context = f"{context}.variants[{index}]"
                check.require(isinstance(variant, dict), f"{variant_context}: variant must be object")
                variant_id = str(variant.get("variant_id", ""))
                check.require(is_non_empty_string(variant_id), f"{variant_context}: variant_id required")
                check.require(variant_id in ids, f"{variant_context}: variant_id missing from variant_ids")
                check.require(
                    is_non_empty_string(variant.get("source_path")) or is_non_empty_string(variant.get("external_source_url")),
                    f"{variant_context}: source_path or external_source_url required",
                )
        else:
            check.require(is_non_empty_string(work.get("source_path")), f"{context}: source_path required without variants")
            check.require(is_non_empty_string(work.get("source_url")), f"{context}: source_url required without variants")
    return works


def validate_segments(check: SchemaCheck, corpus: CorpusFiles, works: dict[str, dict[str, Any]]) -> int:
    check.require(corpus.segments.exists(), f"{corpus.corpus_id}: missing segment file")
    seen: set[tuple[str, str, str]] = set()
    count = 0
    with corpus.segments.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                check.require(False, f"{corpus.corpus_id}:{line_number}: invalid JSONL record: {exc}")
                continue
            if not isinstance(record, dict):
                check.require(False, f"{corpus.corpus_id}:{line_number}: segment must be object")
                continue
            count += 1
            context = f"{corpus.corpus_id}:{line_number}"
            missing_segment_keys = sorted(SEGMENT_KEYS - set(record))
            check.require(not missing_segment_keys, f"{context}: segment missing {missing_segment_keys}")
            check.require(record.get("schema_version") == 1, f"{context}: schema_version must be 1")
            check.require(record.get("corpus_id") == corpus.corpus_id, f"{context}: corpus_id mismatch")
            work_id = str(record.get("work_id", ""))
            check.require(work_id in works, f"{context}: unknown work_id {work_id!r}")
            variant_id = str(record.get("variant_id", ""))
            if work_id in works:
                ids = variant_ids_for(works[work_id])
                check.require(not variant_id or variant_id in ids, f"{context}: unknown variant_id {variant_id!r}")
            key = (work_id, variant_id, str(record.get("segment_id", "")))
            check.require(key not in seen, f"{context}: duplicate segment key {key}")
            seen.add(key)
            check.require(isinstance(record.get("order"), int) and record["order"] >= 1, f"{context}: order must be positive int")
            for field in ("segment_id", "segment_type", "label", "text_raw", "text_preview"):
                check.require(is_non_empty_string(record.get(field)), f"{context}: {field} required")
            url = str(record.get("url", ""))
            check.require(url.startswith(f"/work/{corpus.corpus_id}/"), f"{context}: url must start with /work/{corpus.corpus_id}/")
            check.require("#" in url, f"{context}: url must include segment anchor")
    check.require(count > 0, f"{corpus.corpus_id}: segment file must contain records")
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate common corpus metadata and segment schema.")
    parser.add_argument("--max-errors", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check = SchemaCheck(max(1, args.max_errors))
    summaries = []
    try:
        for corpus in CORPORA:
            works = validate_metadata(check, corpus)
            segment_count = validate_segments(check, corpus, works)
            summaries.append(f"{corpus.corpus_id}: {len(works)} works, {segment_count} segments")
    except AssertionError as exc:
        raise SystemExit(str(exc)) from exc
    if check.errors:
        raise SystemExit(check.report())
    print("corpus schema ok")
    for summary in summaries:
        print(f"- {summary}")


if __name__ == "__main__":
    main()
