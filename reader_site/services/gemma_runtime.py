from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar


REQUEST_TIMEOUT_SECONDS_ENV = "PHILO_GEMMA_TIMEOUT_SECONDS"
QUEUE_TIMEOUT_SECONDS_ENV = "PHILO_GEMMA_QUEUE_TIMEOUT_SECONDS"
MAX_CONCURRENCY_ENV = "PHILO_GEMMA_MAX_CONCURRENCY"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 180.0
DEFAULT_QUEUE_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_CONCURRENCY = 1

_T = TypeVar("_T")
_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def request_timeout_seconds() -> float:
    return _bounded_float(REQUEST_TIMEOUT_SECONDS_ENV, DEFAULT_REQUEST_TIMEOUT_SECONDS, 1.0, 900.0)


def queue_timeout_seconds() -> float:
    return _bounded_float(QUEUE_TIMEOUT_SECONDS_ENV, DEFAULT_QUEUE_TIMEOUT_SECONDS, 0.05, 120.0)


def _configured_max_concurrency() -> int:
    return _bounded_int(MAX_CONCURRENCY_ENV, DEFAULT_MAX_CONCURRENCY, 1, 8)


def _initial_state(max_concurrency: int) -> dict[str, Any]:
    return {
        "max_concurrency": max_concurrency,
        "active": 0,
        "started_count": 0,
        "completed_count": 0,
        "busy_count": 0,
        "timeout_count": 0,
        "failure_count": 0,
        "last_request_id": "",
        "last_status": "idle",
        "last_started_at": "",
        "last_finished_at": "",
        "last_error": "",
        "last_error_at": "",
    }


_MAX_CONCURRENCY = _configured_max_concurrency()
_GATE = threading.BoundedSemaphore(_MAX_CONCURRENCY)
_STATE = _initial_state(_MAX_CONCURRENCY)


class GemmaRuntimeError(ConnectionError):
    error_code = "unavailable"
    status_code = 503

    def __init__(self, message: str, *, request_id: str) -> None:
        super().__init__(message)
        self.request_id = request_id

    def response_metadata(self) -> dict[str, Any]:
        return {
            "gemma_request": gemma_request_metadata(
                self.request_id,
                status=self.error_code,
            )
        }


class GemmaRuntimeBusy(GemmaRuntimeError):
    error_code = "busy"
    status_code = 429


class GemmaRuntimeTimeout(GemmaRuntimeError):
    error_code = "timeout"
    status_code = 504


class GemmaRuntimeUnavailable(GemmaRuntimeError):
    error_code = "unavailable"
    status_code = 503


def new_gemma_request_id() -> str:
    return "gemma-" + uuid.uuid4().hex


def gemma_request_metadata(request_id: str, *, status: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "status": status,
        "timeout_seconds": request_timeout_seconds(),
        "queue_timeout_seconds": queue_timeout_seconds(),
        "max_concurrency": _MAX_CONCURRENCY,
    }


def _mark_busy(request_id: str) -> None:
    with _LOCK:
        _STATE["busy_count"] += 1
        _STATE["last_request_id"] = request_id
        _STATE["last_status"] = "busy"
        _STATE["last_error"] = "queue timeout"
        _STATE["last_error_at"] = _utc_now()
        _STATE["last_finished_at"] = _STATE["last_error_at"]


def _mark_started(request_id: str) -> None:
    with _LOCK:
        _STATE["active"] += 1
        _STATE["started_count"] += 1
        _STATE["last_request_id"] = request_id
        _STATE["last_status"] = "running"
        _STATE["last_started_at"] = _utc_now()
        _STATE["last_error"] = ""


def _mark_finished(request_id: str, status: str, error: str = "") -> None:
    with _LOCK:
        _STATE["active"] = max(0, _STATE["active"] - 1)
        _STATE["last_request_id"] = request_id
        _STATE["last_status"] = status
        _STATE["last_finished_at"] = _utc_now()
        if status == "completed":
            _STATE["completed_count"] += 1
            _STATE["last_error"] = ""
            return
        if status == "timeout":
            _STATE["timeout_count"] += 1
        else:
            _STATE["failure_count"] += 1
        _STATE["last_error"] = error
        _STATE["last_error_at"] = _STATE["last_finished_at"]


def run_gemma_operation(operation: Callable[[float], _T], *, request_id: str | None = None) -> _T:
    request_id = request_id or new_gemma_request_id()
    if not _GATE.acquire(timeout=queue_timeout_seconds()):
        _mark_busy(request_id)
        raise GemmaRuntimeBusy("번역 요청이 많습니다. 잠시 후 다시 시도해주세요.", request_id=request_id)

    finished = False
    _mark_started(request_id)
    try:
        result = operation(request_timeout_seconds())
    except GemmaRuntimeError as exc:
        _mark_finished(request_id, exc.error_code, str(exc))
        finished = True
        raise
    except (TypeError, ValueError) as exc:
        runtime_error = GemmaRuntimeUnavailable(
            "번역 응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해주세요.",
            request_id=request_id,
        )
        _mark_finished(request_id, runtime_error.error_code, str(runtime_error))
        finished = True
        raise runtime_error from exc
    else:
        _mark_finished(request_id, "completed")
        finished = True
        return result
    finally:
        if not finished:
            _mark_finished(request_id, "failed", "unexpected Gemma runtime failure")
        _GATE.release()


def gemma_runtime_status() -> dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)
    state["request_timeout_seconds"] = request_timeout_seconds()
    state["queue_timeout_seconds"] = queue_timeout_seconds()
    return state


def reset_gemma_runtime_for_tests(max_concurrency: int | None = None) -> None:
    global _GATE, _MAX_CONCURRENCY, _STATE

    next_max_concurrency = max_concurrency if max_concurrency is not None else _configured_max_concurrency()
    if next_max_concurrency < 1:
        next_max_concurrency = 1
    if next_max_concurrency > 8:
        next_max_concurrency = 8
    with _LOCK:
        _MAX_CONCURRENCY = next_max_concurrency
        _GATE = threading.BoundedSemaphore(_MAX_CONCURRENCY)
        _STATE = _initial_state(_MAX_CONCURRENCY)
