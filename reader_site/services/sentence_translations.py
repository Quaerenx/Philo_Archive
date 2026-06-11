from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.interpretation_prompts import load_prompt_template
from services.sentence_targets import sentence_target_bundle
from services.source_targets import sha256_text


SITE = Path(__file__).resolve().parents[1]
AI_DIR = SITE / "data" / "ai"
PROMPT_TEMPLATE_ID = "sentence_translation_study_v1"
MODEL_NAME = os.environ.get("PHILO_GEMMA_MODEL_NAME", "gemma-4-26B-A4B-it-Q4_K_M")
MODEL_RUNTIME = os.environ.get("PHILO_GEMMA_RUNTIME", "llama.cpp b9371-f12cc6d0f")
LLAMA_BASE_URL = os.environ.get("PHILO_GEMMA_BASE_URL", "http://127.0.0.1:8794")
MAX_SOURCE_CHARS = 6000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_id(value: str) -> str:
    value = str(value or "").strip()
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None, "invalid id")
    return value


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


def call_llama_server(prompt_bundle: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "You are a source-bounded translation tutor. Return only final JSON. Do not reveal hidden reasoning.",
            },
            {"role": "user", "content": prompt_bundle["prompt"]},
        ],
        "temperature": prompt_bundle["temperature"],
        "top_p": 0.95,
        "max_tokens": 900,
        "stream": False,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = Request(
        f"{LLAMA_BASE_URL.rstrip('/')}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ConnectionError("Gemma runtime is not running") from exc
    choices = payload.get("choices", [])
    require(isinstance(choices, list) and choices, "model response missing choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = str(message.get("content") or "").strip()
    require(content, "model response missing content")
    return normalized_model_output(content)


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
        "schema_version": 1,
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
        "translation": output["translation"],
        "literal_gloss": "",
        "commentary": output["commentary"],
        "key_terms": [],
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
    return {key: value for key, value in record.items() if key not in {"literal_gloss", "key_terms"}}


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
    if not regenerate:
        cached = find_cached_record(path, target, prompt_bundle)
        if cached:
            return {"ok": True, "cached": True, "record": public_translation_record(cached)}

    output = call_llama_server(prompt_bundle)
    record = build_record(target, prompt_bundle, output)
    append_record(path, record)
    return {"ok": True, "cached": False, "record": public_translation_record(record)}
