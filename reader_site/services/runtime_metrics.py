from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
RUNTIME_DIR_ENV = "PHILO_RUNTIME_METRICS_DIR"
LOG_BYTES_ENV = "PHILO_RUNTIME_METRICS_LOG_BYTES"
SLOW_MS_ENV = "PHILO_RUNTIME_METRICS_SLOW_MS"
RECENT_SLOW_MAX_ENV = "PHILO_RUNTIME_METRICS_RECENT_SLOW_MAX"
DEFAULT_MAX_LOG_BYTES = 512 * 1024
DEFAULT_SLOW_REQUEST_MS = 1000.0
DEFAULT_RECENT_SLOW_MAX = 25
METRICS_LOG_NAME = "runtime_metrics.jsonl"

_LOCK = threading.RLock()
_RECENT_SLOW: deque[dict[str, Any]] = deque(maxlen=DEFAULT_RECENT_SLOW_MAX)
_COUNTERS: dict[str, Any] = {
    "search": {
        "requests": 0,
        "errors": 0,
        "slow": 0,
        "total_ms": 0.0,
        "max_ms": 0.0,
    },
    "gemma": {
        "requests": 0,
        "completed": 0,
        "busy": 0,
        "timeout": 0,
        "unavailable": 0,
        "errors": 0,
        "slow": 0,
        "total_ms": 0.0,
        "max_ms": 0.0,
    },
    "cache": {
        "translation_record_hit": 0,
        "gemma_response_cache_hit": 0,
        "miss": 0,
        "store_success": 0,
        "store_failure": 0,
    },
    "log_errors": 0,
    "last_event_at": "",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def runtime_metrics_dir() -> Path:
    configured = os.environ.get(RUNTIME_DIR_ENV, "").strip()
    return Path(configured).expanduser() if configured else SITE / "data" / "runtime.local"


def runtime_metrics_log_path() -> Path:
    return runtime_metrics_dir() / METRICS_LOG_NAME


def max_log_bytes() -> int:
    raw = os.environ.get(LOG_BYTES_ENV, "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_LOG_BYTES
    except ValueError:
        value = DEFAULT_MAX_LOG_BYTES
    return max(64 * 1024, min(value, 16 * 1024 * 1024))


def slow_request_ms() -> float:
    raw = os.environ.get(SLOW_MS_ENV, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_SLOW_REQUEST_MS
    except ValueError:
        value = DEFAULT_SLOW_REQUEST_MS
    return max(10.0, min(value, 120_000.0))


def recent_slow_max() -> int:
    raw = os.environ.get(RECENT_SLOW_MAX_ENV, "").strip()
    try:
        value = int(raw) if raw else DEFAULT_RECENT_SLOW_MAX
    except ValueError:
        value = DEFAULT_RECENT_SLOW_MAX
    return max(1, min(value, 100))


def stable_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


def _trim_recent_slow() -> None:
    target = recent_slow_max()
    while len(_RECENT_SLOW) > target:
        _RECENT_SLOW.popleft()


def _record_slow(event: dict[str, Any]) -> None:
    if float(event.get("duration_ms") or 0.0) < slow_request_ms():
        return
    _RECENT_SLOW.append(
        {
            "ts": event.get("ts", ""),
            "event": event.get("event", ""),
            "status": event.get("status", ""),
            "duration_ms": event.get("duration_ms", 0.0),
            "context": event.get("context", {}),
        }
    )
    _trim_recent_slow()


def _rotate_log_if_needed(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= max_log_bytes():
        return
    rotated = path.with_name(path.name + ".1")
    try:
        if rotated.exists():
            rotated.unlink()
        path.replace(rotated)
    except OSError:
        return


def _append_log(event: dict[str, Any]) -> None:
    path = runtime_metrics_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log_if_needed(path)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError:
        with _LOCK:
            _COUNTERS["log_errors"] = int(_COUNTERS.get("log_errors", 0)) + 1


def _counter_avg(counter: dict[str, Any]) -> float:
    requests = int(counter.get("requests") or 0)
    if requests <= 0:
        return 0.0
    return round(float(counter.get("total_ms") or 0.0) / requests, 3)


def _base_event(event_name: str, status: str, duration_ms: float, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": utc_now(),
        "event": event_name,
        "status": status,
        "duration_ms": round(float(duration_ms), 3),
        "context": context,
    }


def record_search_request(
    *,
    duration_ms: float,
    status: str,
    query: str,
    corpus_id: str,
    work_id: str,
    variant_id: str,
    limit: int,
    offset: int,
    engine: str = "",
    result_count: int = 0,
    error_type: str = "",
) -> None:
    try:
        context = {
            "query_hash": stable_hash(query),
            "query_chars": len(query or ""),
            "term_count": len(str(query or "").split()),
            "corpus_id": corpus_id,
            "work_id": work_id,
            "variant_id": variant_id,
            "limit": int(limit),
            "offset": int(offset),
            "engine": engine,
            "result_count": int(result_count),
        }
        if error_type:
            context["error_type"] = error_type
        event = _base_event("search_request", status, duration_ms, context)
        with _LOCK:
            search = _COUNTERS["search"]
            search["requests"] += 1
            search["total_ms"] += event["duration_ms"]
            search["max_ms"] = max(float(search["max_ms"]), event["duration_ms"])
            if status != "ok":
                search["errors"] += 1
            if event["duration_ms"] >= slow_request_ms():
                search["slow"] += 1
            _COUNTERS["last_event_at"] = event["ts"]
            _record_slow(event)
        _append_log(event)
    except Exception:
        return


def record_gemma_cache_event(
    *,
    source: str,
    hit: bool,
    cache_key: str,
    prompt_version: str,
    model_name: str,
    corpus_id: str,
    work_id: str,
    segment_id: str,
    sentence_id: str,
    store_success: bool | None = None,
) -> None:
    try:
        status = "hit" if hit else "miss"
        context = {
            "source": source,
            "cache_key_hash": stable_hash(cache_key),
            "prompt_version": prompt_version,
            "model_name": model_name,
            "corpus_id": corpus_id,
            "work_id": work_id,
            "segment_id": segment_id,
            "sentence_id": sentence_id,
        }
        if store_success is not None:
            context["store_success"] = bool(store_success)
        event = _base_event("gemma_cache", status, 0.0, context)
        with _LOCK:
            cache = _COUNTERS["cache"]
            if hit and source == "translation_record":
                cache["translation_record_hit"] += 1
            elif hit and source == "gemma_response_cache":
                cache["gemma_response_cache_hit"] += 1
            elif not hit:
                cache["miss"] += 1
            if store_success is True:
                cache["store_success"] += 1
            elif store_success is False:
                cache["store_failure"] += 1
            _COUNTERS["last_event_at"] = event["ts"]
        _append_log(event)
    except Exception:
        return


def record_gemma_request(
    *,
    duration_ms: float,
    status: str,
    request_id: str,
    model_name: str,
    prompt_sha256: str,
    input_sha256: str,
    prompt_chars: int,
    corpus_id: str,
    work_id: str,
    segment_id: str,
    sentence_id: str,
    error_type: str = "",
) -> None:
    try:
        normalized_status = status or "error"
        context = {
            "request_id": request_id,
            "model_name": model_name,
            "prompt_hash": stable_hash(prompt_sha256),
            "input_hash": stable_hash(input_sha256),
            "prompt_chars": int(prompt_chars),
            "corpus_id": corpus_id,
            "work_id": work_id,
            "segment_id": segment_id,
            "sentence_id": sentence_id,
        }
        if error_type:
            context["error_type"] = error_type
        event = _base_event("gemma_request", normalized_status, duration_ms, context)
        with _LOCK:
            gemma = _COUNTERS["gemma"]
            gemma["requests"] += 1
            gemma["total_ms"] += event["duration_ms"]
            gemma["max_ms"] = max(float(gemma["max_ms"]), event["duration_ms"])
            if normalized_status == "completed":
                gemma["completed"] += 1
            elif normalized_status == "busy":
                gemma["busy"] += 1
                gemma["errors"] += 1
            elif normalized_status == "timeout":
                gemma["timeout"] += 1
                gemma["errors"] += 1
            elif normalized_status == "unavailable":
                gemma["unavailable"] += 1
                gemma["errors"] += 1
            else:
                gemma["errors"] += 1
            if event["duration_ms"] >= slow_request_ms():
                gemma["slow"] += 1
            _COUNTERS["last_event_at"] = event["ts"]
            _record_slow(event)
        _append_log(event)
    except Exception:
        return


def runtime_metrics_snapshot() -> dict[str, Any]:
    try:
        with _LOCK:
            counters = json.loads(json.dumps(_COUNTERS))
            recent_slow = list(_RECENT_SLOW)
        counters["search"]["avg_ms"] = _counter_avg(counters["search"])
        counters["gemma"]["avg_ms"] = _counter_avg(counters["gemma"])
        path = runtime_metrics_log_path()
        return {
            "schema_version": 1,
            "counters": counters,
            "recent_slow_requests": recent_slow,
            "slow_threshold_ms": slow_request_ms(),
            "log": {
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "max_bytes": max_log_bytes(),
                "rotation": "single .1 file",
            },
        }
    except Exception as exc:
        return {
            "schema_version": 1,
            "error": type(exc).__name__,
        }


def reset_runtime_metrics_for_tests() -> None:
    with _LOCK:
        _RECENT_SLOW.clear()
        _COUNTERS["search"].update({"requests": 0, "errors": 0, "slow": 0, "total_ms": 0.0, "max_ms": 0.0})
        _COUNTERS["gemma"].update(
            {
                "requests": 0,
                "completed": 0,
                "busy": 0,
                "timeout": 0,
                "unavailable": 0,
                "errors": 0,
                "slow": 0,
                "total_ms": 0.0,
                "max_ms": 0.0,
            }
        )
        _COUNTERS["cache"].update(
            {
                "translation_record_hit": 0,
                "gemma_response_cache_hit": 0,
                "miss": 0,
                "store_success": 0,
                "store_failure": 0,
            }
        )
        _COUNTERS["log_errors"] = 0
        _COUNTERS["last_event_at"] = ""
