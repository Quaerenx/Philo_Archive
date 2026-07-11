from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.gemma_response_cache import CACHE_SCHEMA_VERSION as GEMMA_CACHE_SCHEMA_VERSION
from services.gemma_response_cache import build_cache_key, cached_response, store_response
from services.gemma_runtime import (
    GemmaRuntimeTimeout,
    GemmaRuntimeUnavailable,
    gemma_request_metadata,
    new_gemma_request_id,
    run_gemma_operation,
)
from services.interpretation_prompts import load_prompt_template
from services.runtime_metrics import elapsed_ms, record_gemma_cache_event, record_gemma_request
from services.sentence_targets import sentence_target_bundle
from services.source_targets import sha256_text


SITE = Path(__file__).resolve().parents[1]
AI_DIR = Path(os.environ.get("PHILO_AI_DIR", str(SITE / "data" / "ai")))
PROMPT_TEMPLATE_ID = "sentence_translation_study_v1"
MODEL_NAME = os.environ.get("PHILO_GEMMA_MODEL_NAME", "gemma-4-26B-A4B-it-Q4_K_M")
MODEL_RUNTIME = os.environ.get("PHILO_GEMMA_RUNTIME", "llama.cpp b9371-f12cc6d0f")
LLAMA_BASE_URL = os.environ.get("PHILO_GEMMA_BASE_URL", "http://127.0.0.1:8794")
MAX_SOURCE_CHARS = 6000
TRANSLATION_FILE_SUFFIX = "_sentence_translations.jsonl"
LLAMA_SYSTEM_PROMPT = "You are a source-bounded translation tutor. Return only final JSON. Do not reveal hidden reasoning."
LLAMA_TOP_P = 0.95
LLAMA_MAX_TOKENS = 900
GEMMA_CACHE_NAMESPACE = "sentence_translation"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_id(value: str) -> str:
    value = str(value or "").strip()
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None, "invalid id")
    return value


def valid_record_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+", candidate) is None:
        return ""
    return candidate


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_corpus_id(value: str) -> str:
    value = str(value or "").strip()
    require(re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None, "invalid corpus_id")
    return value


def infer_source_language(corpus_id: str, work_id: str) -> str:
    if corpus_id == "nietzsche":
        return "de"
    if corpus_id == "kierkegaard":
        return "da"
    if corpus_id == "wittgenstein":
        return "de"
    if corpus_id == "bible":
        if work_id.startswith("oshb."):
            return "hbo"
        return "grc"
    return "und"


def bounded_source_context(source_text: str, sentence_text: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    if len(source_text) <= max_chars:
        return source_text
    index = source_text.find(sentence_text)
    if index == -1:
        return source_text[:max_chars].rstrip() + " [...]"
    before_budget = max(0, (max_chars - len(sentence_text)) // 2)
    start = max(0, index - before_budget)
    end = min(len(source_text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    context = source_text[start:end].strip()
    if start > 0:
        context = "[...] " + context
    if end < len(source_text):
        context = context + " [...]"
    return context


def ai_record_path(corpus_id: str) -> Path:
    return AI_DIR / f"{safe_corpus_id(corpus_id)}_sentence_translations.jsonl"


def query_corpus_id(query: dict[str, list[str]]) -> str:
    value = str((query.get("corpus_id") or [""])[0]).strip()
    return safe_corpus_id(value) if value else ""


def ai_record_paths_for_query(corpus_id: str) -> list[Path]:
    if corpus_id:
        return [ai_record_path(corpus_id)]
    if not AI_DIR.exists():
        return []
    paths: list[Path] = []
    for path in AI_DIR.glob(f"*{TRANSLATION_FILE_SUFFIX}"):
        stem = path.name[: -len(TRANSLATION_FILE_SUFFIX)]
        if re.fullmatch(r"[A-Za-z0-9_-]+", stem):
            paths.append(path)
    return sorted(paths)


def render_sentence_prompt(template_record: dict[str, Any], target: dict[str, Any]) -> str:
    source_text = str(target.get("source_text", ""))
    sentence_text = str(target.get("sentence_text", ""))
    require(source_text.strip(), "source target missing source_text")
    require(sentence_text.strip(), "source target missing sentence_text")
    require(target.get("source_text_sha256") == sha256_text(source_text), "source_text_sha256 mismatch")
    require(target.get("sentence_text_sha256") == sha256_text(sentence_text), "sentence_text_sha256 mismatch")
    source_context = bounded_source_context(source_text, sentence_text)
    values = {
        "prompt_template_id": template_record["prompt_template_id"],
        "corpus_id": target.get("corpus_id", ""),
        "work_id": target.get("work_id", ""),
        "variant_id": target.get("variant_id", ""),
        "segment_id": target.get("segment_id", ""),
        "sentence_id": target.get("sentence_id", ""),
        "target_url": target.get("target_url", ""),
        "label": target.get("label", ""),
        "source_text_sha256": target.get("source_text_sha256", ""),
        "sentence_text_sha256": target.get("sentence_text_sha256", ""),
        "source_text_chars": target.get("source_text_chars", len(source_text)),
        "sentence_text_chars": target.get("sentence_text_chars", len(sentence_text)),
        "source_text": source_context,
        "sentence_text": sentence_text,
    }
    missing = [key for key, value in values.items() if value is None or (value == "" and key != "variant_id")]
    require(not missing, "sentence target missing prompt values: " + ", ".join(sorted(missing)))
    return str(template_record["template"]).format(**values)


def build_sentence_prompt_bundle(target: dict[str, Any]) -> dict[str, Any]:
    template_record = load_prompt_template(PROMPT_TEMPLATE_ID)
    prompt = render_sentence_prompt(template_record, target)
    return {
        "schema_version": 1,
        "record_type": "sentence_translation_prompt_bundle",
        "prompt_template_id": PROMPT_TEMPLATE_ID,
        "prompt_sha256": sha256_text(prompt),
        "temperature": template_record["default_temperature"],
        "target_url": target["target_url"],
        "target": {
            "corpus_id": target["corpus_id"],
            "work_id": target["work_id"],
            "variant_id": target.get("variant_id", ""),
            "segment_id": target["segment_id"],
            "sentence_id": target["sentence_id"],
            "target_url": target["target_url"],
            "label": target["label"],
            "source_text_sha256": target["source_text_sha256"],
            "sentence_text_sha256": target["sentence_text_sha256"],
            "source_text_chars": target["source_text_chars"],
            "sentence_text_chars": target["sentence_text_chars"],
        },
        "prompt": prompt,
    }


def extract_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    require(isinstance(parsed, dict), "model response JSON must be an object")
    return parsed


def normalized_model_output(content: str) -> dict[str, Any]:
    try:
        parsed = extract_json_object(content)
    except (json.JSONDecodeError, ValueError):
        return {
            "translation": "",
            "commentary": content.strip(),
            "cautions": ["Model response was not valid JSON; saved as commentary."],
        }
    return {
        "translation": str(parsed.get("translation", "")).strip(),
        "commentary": str(parsed.get("commentary", "")).strip(),
        "cautions": parsed.get("cautions") if isinstance(parsed.get("cautions"), list) else [],
    }


def llama_request_options(prompt_bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": prompt_bundle["temperature"],
        "top_p": LLAMA_TOP_P,
        "max_tokens": LLAMA_MAX_TOKENS,
        "response_format": "json_object",
        "system_prompt_sha256": sha256_text(LLAMA_SYSTEM_PROMPT),
        "model_runtime": MODEL_RUNTIME,
        "prompt_bundle_schema_version": prompt_bundle.get("schema_version", 1),
    }


def llama_request_body(prompt_bundle: dict[str, Any]) -> dict[str, Any]:
    options = llama_request_options(prompt_bundle)
    return {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": LLAMA_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt_bundle["prompt"]},
        ],
        "temperature": options["temperature"],
        "top_p": options["top_p"],
        "max_tokens": options["max_tokens"],
        "stream": False,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }


def sentence_gemma_cache_identity(prompt_bundle: dict[str, Any]) -> dict[str, Any]:
    options = llama_request_options(prompt_bundle)
    prompt_version = str(prompt_bundle.get("prompt_template_id") or PROMPT_TEMPLATE_ID)
    input_sha256 = str(prompt_bundle["prompt_sha256"])
    cache_key = build_cache_key(
        namespace=GEMMA_CACHE_NAMESPACE,
        prompt_version=prompt_version,
        model_name=MODEL_NAME,
        input_sha256=input_sha256,
        options=options,
    )
    return {
        "schema_version": GEMMA_CACHE_SCHEMA_VERSION,
        "namespace": GEMMA_CACHE_NAMESPACE,
        "prompt_version": prompt_version,
        "model_name": MODEL_NAME,
        "input_sha256": input_sha256,
        "options": options,
        "cache_key": cache_key,
    }


def cache_metadata(
    identity: dict[str, Any],
    hit: bool,
    source: str,
    request_id: str = "",
    request_status: str = "",
) -> dict[str, Any]:
    metadata = {
        "cache": {
            "hit": hit,
            "source": source,
            "cache_key": identity["cache_key"],
            "schema_version": identity["schema_version"],
            "prompt_version": identity["prompt_version"],
            "model_name": identity["model_name"],
        }
    }
    if request_id:
        metadata["gemma_request"] = gemma_request_metadata(
            request_id,
            status=request_status or "completed",
        )
    return metadata


def sentence_translation_response(
    *,
    record: dict[str, Any],
    cached: bool,
    identity: dict[str, Any],
    cache_source: str,
    request_id: str = "",
    request_status: str = "",
) -> dict[str, Any]:
    return {
        "ok": True,
        "cached": cached,
        "record": public_translation_record(record),
        "metadata": cache_metadata(
            identity,
            hit=cached,
            source=cache_source,
            request_id=request_id,
            request_status=request_status,
        ),
    }


def call_llama_server(prompt_bundle: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    request_id = request_id or new_gemma_request_id()
    body = llama_request_body(prompt_bundle)

    def fetch_model_response(timeout_seconds: float) -> dict[str, Any]:
        request = Request(
            f"{LLAMA_BASE_URL.rstrip('/')}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise GemmaRuntimeTimeout(
                "번역 요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.",
                request_id=request_id,
            ) from exc
        except HTTPError as exc:
            raise GemmaRuntimeUnavailable(
                "번역 서비스가 응답하지 못했습니다. 잠시 후 다시 시도해주세요.",
                request_id=request_id,
            ) from exc
        except (URLError, OSError) as exc:
            raise GemmaRuntimeUnavailable("번역 준비가 필요합니다.", request_id=request_id) from exc
        except json.JSONDecodeError as exc:
            raise GemmaRuntimeUnavailable(
                "번역 응답을 해석하지 못했습니다. 잠시 후 다시 시도해주세요.",
                request_id=request_id,
            ) from exc

        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise GemmaRuntimeUnavailable(
                "번역 응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해주세요.",
                request_id=request_id,
            )
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise GemmaRuntimeUnavailable(
                "번역 응답 내용이 비어 있습니다. 잠시 후 다시 시도해주세요.",
                request_id=request_id,
            )
        return normalized_model_output(content)

    return run_gemma_operation(fetch_model_response, request_id=request_id)


def iter_cached_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def write_records(path: Path, records: list[dict[str, Any]]) -> None:
    AI_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def public_record_id(record: dict[str, Any]) -> str:
    stored_id = valid_record_id(record.get("id"))
    if stored_id:
        return stored_id
    identity = {
        "record_type": record.get("record_type", ""),
        "created_at": record.get("created_at", ""),
        "generated_at": record.get("generated_at", ""),
        "corpus_id": record.get("corpus_id", ""),
        "work_id": record.get("work_id", ""),
        "variant_id": record.get("variant_id", ""),
        "segment_id": record.get("segment_id", ""),
        "sentence_id": record.get("sentence_id", record.get("target_id", "")),
        "source_text_sha256": record.get("source_text_sha256", ""),
        "sentence_text_sha256": record.get("sentence_text_sha256", ""),
        "prompt_sha256": record.get("prompt_sha256", ""),
    }
    return "legacy-" + sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True))[:32]


def find_cached_record(path: Path, target: dict[str, Any], prompt_bundle: dict[str, Any]) -> dict[str, Any] | None:
    for record in reversed(iter_cached_records(path)):
        if record.get("record_type") != "ai_sentence_translation":
            continue
        if record.get("corpus_id") != target["corpus_id"] or record.get("work_id") != target["work_id"]:
            continue
        if record.get("variant_id", "") != target.get("variant_id", ""):
            continue
        if record.get("segment_id") != target["segment_id"] or record.get("sentence_id") != target["sentence_id"]:
            continue
        if record.get("sentence_text_sha256") != target["sentence_text_sha256"]:
            continue
        if record.get("prompt_sha256") != prompt_bundle["prompt_sha256"]:
            continue
        if record.get("review_state") == "rejected":
            continue
        return record
    return None


def append_record(path: Path, record: dict[str, Any]) -> None:
    AI_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_record(target: dict[str, Any], prompt_bundle: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    interpretation = output["commentary"] or output["translation"] or "Generated sentence translation."
    return {
        "schema_version": 2,
        "record_type": "ai_sentence_translation",
        "id": str(uuid.uuid4()),
        "created_at": now,
        "generated_at": now,
        "corpus_id": target["corpus_id"],
        "work_id": target["work_id"],
        "variant_id": target.get("variant_id", ""),
        "target_id": target["sentence_id"],
        "segment_id": target["segment_id"],
        "sentence_id": target["sentence_id"],
        "target_url": target["target_url"],
        "source_text_sha256": target["source_text_sha256"],
        "sentence_text_sha256": target["sentence_text_sha256"],
        "source_text_excerpt": target["sentence_text"][:320],
        "source_language": infer_source_language(target["corpus_id"], target["work_id"]),
        "model_provider": "local_llama_cpp",
        "model_name": MODEL_NAME,
        "model_version": MODEL_NAME,
        "model_runtime": MODEL_RUNTIME,
        "prompt_template_id": prompt_bundle["prompt_template_id"],
        "prompt_sha256": prompt_bundle["prompt_sha256"],
        "temperature": prompt_bundle["temperature"],
        "gemma_response_cache_schema_version": GEMMA_CACHE_SCHEMA_VERSION,
        "gemma_response_cache_key": sentence_gemma_cache_identity(prompt_bundle)["cache_key"],
        "translation": output["translation"],
        "commentary": output["commentary"],
        "cautions": [str(item) for item in output["cautions"]],
        "interpretation": interpretation,
        "citations": [
            {
                "target_url": target["target_url"],
                "label": target["label"],
                "source_text_sha256": target["sentence_text_sha256"],
            }
        ],
        "review_state": "generated",
}


def public_translation_record(record: dict[str, Any]) -> dict[str, Any]:
    public_record = {key: value for key, value in record.items() if key not in {"literal_gloss", "key_terms"}}
    public_record["id"] = public_record_id(record)
    return public_record


def update_sentence_translation_review(payload: dict[str, Any], record_id: str) -> dict[str, Any]:
    corpus_id = safe_corpus_id(str(payload.get("corpus_id", "")))
    review_state = str(payload.get("review_state", "")).strip().lower()
    require(review_state in {"reviewed", "rejected", "generated"}, "invalid review_state")
    record_id = clean_id(record_id)
    path = ai_record_path(corpus_id)
    records = iter_cached_records(path)
    now = utc_now()
    updated: dict[str, Any] | None = None
    for index, record in enumerate(records):
        if public_record_id(record) != record_id:
            continue
        next_record = dict(record)
        if not valid_record_id(next_record.get("id")):
            next_record["id"] = record_id
        next_record["review_state"] = review_state
        next_record["reviewed_at"] = now if review_state == "reviewed" else ""
        next_record["updated_at"] = now
        records[index] = next_record
        updated = next_record
        break
    if updated is None:
        raise FileNotFoundError("sentence translation record not found")
    write_records(path, records)
    return {"ok": True, "record": public_translation_record(updated)}


def translation_record_matches_text_query(record: dict[str, Any], text_query: str) -> bool:
    needle = clean_text(text_query).lower()
    if not needle:
        return True
    haystack = " ".join(
        clean_text(record.get(field))
        for field in (
            "corpus_id",
            "work_id",
            "variant_id",
            "segment_id",
            "sentence_id",
            "source_text_excerpt",
            "translation",
            "commentary",
        )
    ).lower()
    return needle in haystack


def translation_record_sort_key(record: dict[str, Any]) -> tuple[int, str, str, str, str, str, str]:
    variant_id = str(record.get("variant_id") or "").lower()
    target_url = str(record.get("target_url") or "").lower()
    auxiliary_rank = 1 if "metadata" in variant_id or "variant=source_metadata" in target_url else 0
    return (
        auxiliary_rank,
        str(record.get("corpus_id") or ""),
        str(record.get("work_id") or ""),
        str(record.get("segment_id") or ""),
        str(record.get("sentence_id") or ""),
        str(record.get("variant_id") or ""),
        str(record.get("generated_at") or ""),
    )


def sentence_translations_for_export(query: dict[str, list[str]]) -> list[dict[str, Any]]:
    corpus_id = query_corpus_id(query)
    work_id = str((query.get("work_id") or [""])[0]).strip()
    text_query = str((query.get("q") or [""])[0]).strip()
    review_state = str((query.get("review_state") or ["reviewed"])[0]).strip().lower() or "reviewed"
    require(review_state in {"generated", "reviewed", "rejected", "all"}, "invalid review_state")
    records = [
        public_translation_record(record)
        for path in ai_record_paths_for_query(corpus_id)
        for record in iter_cached_records(path)
        if record.get("record_type") == "ai_sentence_translation"
    ]
    if work_id:
        records = [record for record in records if record.get("work_id") == work_id]
    if text_query:
        records = [record for record in records if translation_record_matches_text_query(record, text_query)]
    if review_state != "all":
        records = [record for record in records if record.get("review_state") == review_state]
    return sorted(records, key=translation_record_sort_key)


def sentence_translations_summary_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    corpus_id = query_corpus_id(query)
    work_id = str((query.get("work_id") or [""])[0]).strip()
    records = [
        public_translation_record(record)
        for path in ai_record_paths_for_query(corpus_id)
        for record in iter_cached_records(path)
        if record.get("record_type") == "ai_sentence_translation"
    ]
    if work_id:
        records = [record for record in records if record.get("work_id") == work_id]
    review_counts = {"generated": 0, "reviewed": 0, "rejected": 0}
    latest_generated_at = ""
    latest_reviewed_at = ""
    sentence_states: dict[str, dict[str, Any]] = {}
    for record in records:
        review_state = str(record.get("review_state") or "generated").strip().lower()
        if review_state not in review_counts:
            review_state = "generated"
        review_counts[review_state] += 1
        generated_at = str(record.get("generated_at") or record.get("created_at") or "")
        reviewed_at = str(record.get("reviewed_at") or "")
        updated_at = str(record.get("updated_at") or reviewed_at or generated_at)
        if generated_at > latest_generated_at:
            latest_generated_at = generated_at
        if reviewed_at > latest_reviewed_at:
            latest_reviewed_at = reviewed_at
        sentence_id = str(record.get("sentence_id") or record.get("target_id") or "").strip()
        if sentence_id:
            current = sentence_states.get(sentence_id)
            if current is None or updated_at >= current.get("updated_at", ""):
                sentence_states[sentence_id] = {
                    "sentence_id": sentence_id,
                    "segment_id": str(record.get("segment_id") or ""),
                    "review_state": review_state,
                    "record_id": public_record_id(record),
                    "updated_at": updated_at,
                    "generated_at": generated_at,
                    "reviewed_at": reviewed_at,
                }
    return {
        "ok": True,
        "corpus_id": corpus_id,
        "work_id": work_id,
        "count": len(records),
        "review_state_counts": review_counts,
        "sentence_state_count": len(sentence_states),
        "sentence_states": sorted(sentence_states.values(), key=lambda item: item["sentence_id"]),
        "latest_generated_at": latest_generated_at,
        "latest_reviewed_at": latest_reviewed_at,
    }


def export_sentence_translations_markdown(records: list[dict[str, Any]]) -> str:
    lines = ["# 번역 목록", "", f"번역 {len(records)}개", ""]
    for record in records:
        label = " / ".join(
            item
            for item in [
                str(record.get("corpus_id") or ""),
                str(record.get("work_id") or ""),
                str(record.get("sentence_id") or ""),
            ]
            if item
        )
        lines.extend([f"## {label or '문장 번역'}", ""])
        if record.get("translation"):
            lines.extend(["번역", "", str(record["translation"]), ""])
        if record.get("commentary"):
            lines.extend(["해설", "", str(record["commentary"]), ""])
        if record.get("source_text_excerpt"):
            lines.extend(["원문", "", "> " + str(record["source_text_excerpt"]).replace("\n", "\n> "), ""])
        if record.get("target_url"):
            lines.append(f"출처: {record['target_url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def sentence_translations_export_from_query(query: dict[str, list[str]]) -> dict[str, Any]:
    records = sentence_translations_for_export(query)
    export_format = str((query.get("format") or ["markdown"])[0]).strip().lower()
    if export_format == "json":
        return {"kind": "json", "payload": {"count": len(records), "records": records}}
    return {
        "kind": "text",
        "body": export_sentence_translations_markdown(records),
        "content_type": "text/markdown; charset=utf-8",
    }


def sentence_translation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    corpus_id = safe_corpus_id(str(payload.get("corpus_id", "")))
    work_id = clean_id(str(payload.get("work_id", "")))
    segment_id = clean_id(str(payload.get("segment_id", "")))
    sentence_id = clean_id(str(payload.get("sentence_id", "")))
    variant_id = str(payload.get("variant_id", "") or "")
    regenerate = bool(payload.get("regenerate", False))

    target = sentence_target_bundle(corpus_id, work_id, segment_id, sentence_id, variant_id)
    prompt_bundle = build_sentence_prompt_bundle(target)
    path = ai_record_path(corpus_id)
    cache_identity = sentence_gemma_cache_identity(prompt_bundle)
    if not regenerate:
        cached = find_cached_record(path, target, prompt_bundle)
        if cached:
            record_gemma_cache_event(
                source="translation_record",
                hit=True,
                cache_key=cache_identity["cache_key"],
                prompt_version=cache_identity["prompt_version"],
                model_name=cache_identity["model_name"],
                corpus_id=corpus_id,
                work_id=work_id,
                segment_id=segment_id,
                sentence_id=sentence_id,
            )
            return sentence_translation_response(
                record=cached,
                cached=True,
                identity=cache_identity,
                cache_source="translation_record",
            )
        output = cached_response(cache_identity["cache_key"])
        if output:
            record_gemma_cache_event(
                source="gemma_response_cache",
                hit=True,
                cache_key=cache_identity["cache_key"],
                prompt_version=cache_identity["prompt_version"],
                model_name=cache_identity["model_name"],
                corpus_id=corpus_id,
                work_id=work_id,
                segment_id=segment_id,
                sentence_id=sentence_id,
            )
            record = build_record(target, prompt_bundle, output)
            append_record(path, record)
            return sentence_translation_response(
                record=record,
                cached=True,
                identity=cache_identity,
                cache_source="gemma_response_cache",
            )

    record_gemma_cache_event(
        source="regenerate" if regenerate else "gemma_runtime",
        hit=False,
        cache_key=cache_identity["cache_key"],
        prompt_version=cache_identity["prompt_version"],
        model_name=cache_identity["model_name"],
        corpus_id=corpus_id,
        work_id=work_id,
        segment_id=segment_id,
        sentence_id=sentence_id,
    )
    runtime_request_id = new_gemma_request_id()
    runtime_started_at = time.perf_counter()
    try:
        output = call_llama_server(prompt_bundle, request_id=runtime_request_id)
    except ConnectionError as exc:
        record_gemma_request(
            duration_ms=elapsed_ms(runtime_started_at),
            status=str(getattr(exc, "error_code", "error")),
            request_id=runtime_request_id,
            model_name=MODEL_NAME,
            prompt_sha256=str(prompt_bundle.get("prompt_sha256", "")),
            input_sha256=cache_identity["input_sha256"],
            prompt_chars=len(str(prompt_bundle.get("prompt", ""))),
            corpus_id=corpus_id,
            work_id=work_id,
            segment_id=segment_id,
            sentence_id=sentence_id,
            error_type=type(exc).__name__,
        )
        raise
    else:
        record_gemma_request(
            duration_ms=elapsed_ms(runtime_started_at),
            status="completed",
            request_id=runtime_request_id,
            model_name=MODEL_NAME,
            prompt_sha256=str(prompt_bundle.get("prompt_sha256", "")),
            input_sha256=cache_identity["input_sha256"],
            prompt_chars=len(str(prompt_bundle.get("prompt", ""))),
            corpus_id=corpus_id,
            work_id=work_id,
            segment_id=segment_id,
            sentence_id=sentence_id,
        )
    store_response(
        cache_key=cache_identity["cache_key"],
        namespace=cache_identity["namespace"],
        prompt_version=cache_identity["prompt_version"],
        model_name=cache_identity["model_name"],
        input_sha256=cache_identity["input_sha256"],
        options=cache_identity["options"],
        response=output,
    )
    record = build_record(target, prompt_bundle, output)
    append_record(path, record)
    return sentence_translation_response(
        record=record,
        cached=False,
        identity=cache_identity,
        cache_source="gemma_runtime",
        request_id=runtime_request_id,
        request_status="completed",
    )
