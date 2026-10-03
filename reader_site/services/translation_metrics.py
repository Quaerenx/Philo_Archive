"""Bounded numeric model usage; never retains prompts or generated text."""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from urllib.request import urlopen


_calls: ContextVar[list[dict] | None] = ContextVar("translation_model_usage", default=None)
_limits: dict[str, tuple[float, int | None]] = {}


@contextmanager
def capture_model_usage():
    calls: list[dict] = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def begin_model_call(schema_name: str, max_tokens: int | None) -> dict:
    event = {"stage": schema_name, "max_tokens": max_tokens, "prompt_tokens": None,
             "completion_tokens": None, "available_context": None, "context_limit": None,
             "completed": False}
    calls = _calls.get()
    if calls is not None:
        calls.append(event)
    return event


def runtime_context_limit(base_url: str) -> int | None:
    cached = _limits.get(base_url)
    if cached and monotonic() - cached[0] < 60:
        return cached[1]
    limit = None
    try:
        with urlopen(base_url.rstrip("/") + "/props", timeout=2) as response:
            value = json.load(response).get("default_generation_settings", {}).get("n_ctx")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            limit = value
    except (OSError, ValueError, AttributeError):
        pass
    _limits[base_url] = (monotonic(), limit)
    return limit


def finish_model_call(event: dict, payload: dict, context_limit: int | None) -> None:
    usage = payload.get("usage", {})
    for key in ("prompt_tokens", "completion_tokens"):
        value = usage.get(key) if isinstance(usage, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            event[key] = value
    event["context_limit"] = context_limit
    if context_limit is not None and event["prompt_tokens"] is not None:
        event["available_context"] = max(0, context_limit - event["prompt_tokens"])
    event["completed"] = True


def usage_summary(calls: list[dict], context_truncated: bool = False) -> dict:
    return {"model_calls": len(calls), "model_usage": list(calls), "context_truncated": context_truncated}
