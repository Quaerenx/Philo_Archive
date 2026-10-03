from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from typing import Callable, Iterator


class TranslationCancelled(RuntimeError):
    pass


class TranslationBusy(RuntimeError):
    pass


@dataclass
class TranslationJob:
    request_id: str
    disconnected: Callable[[], bool]
    cancelled: bool = False
    committed: bool = False
    executing: bool = False
    abort_transport: Callable[[], None] | None = None

    def check(self) -> None:
        if self.cancelled or self.disconnected():
            raise TranslationCancelled("번역 요청을 취소했습니다.")


_guard = threading.Condition(threading.RLock())
_active: TranslationJob | None = None
REPLACEMENT_WAIT_SECONDS = 210
_running: dict[str, TranslationJob] = {}
_finished: OrderedDict[str, str] = OrderedDict()
_current: ContextVar[TranslationJob | None] = ContextVar("translation_job", default=None)


def request_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid translation request_id") from exc


def remember(identifier: str, state: str) -> None:
    _finished[identifier] = state
    _finished.move_to_end(identifier)
    while len(_finished) > 256:
        _finished.popitem(last=False)


def cancel_translation(value: str) -> dict:
    identifier = request_id(value)
    with _guard:
        job = _running.get(identifier)
        if (job and job.committed) or _finished.get(identifier) == "completed":
            return {"ok": True, "cancelled": False, "state": "completed", "execution_released": not bool(job and job.executing)}
        if job:
            job.cancelled = True
            if job.abort_transport:
                job.abort_transport()
        # Retain early cancellations when the cancel POST arrives before generation.
        remember(identifier, "cancelled")
        _guard.notify_all()
        releasing = bool(job and job.executing)
        return {"ok": True, "cancelled": True, "state": "cancelling" if releasing else "cancelled", "execution_released": not releasing}


@contextmanager
def translation_job(value: str = "", disconnected: Callable[[], bool] = lambda: False) -> Iterator[None]:
    global _active
    identifier = request_id(value) if value else str(uuid.uuid4())
    with _guard:
        if _finished.get(identifier) == "cancelled":
            raise TranslationCancelled("번역 요청을 취소했습니다.")
        if identifier in _finished:
            raise ValueError("translation request_id has already completed")
        if identifier in _running or _current.get() is not None:
            raise TranslationBusy("다른 번역을 처리 중입니다. 완료한 뒤 다시 시도하세요.")
        if _active and not (_active.cancelled or _active.committed or _active.disconnected()):
            raise TranslationBusy("다른 번역을 처리 중입니다. 완료한 뒤 다시 시도하세요.")
        if any(not job.executing and not job.cancelled for job in _running.values()):
            raise TranslationBusy("다음 번역이 대기 중입니다. 완료한 뒤 다시 시도하세요.")
        job = TranslationJob(identifier, disconnected)
        _running[identifier] = job
        deadline = monotonic() + REPLACEMENT_WAIT_SECONDS
        try:
            # One replacement can wait for a cancelled model call to release its slot.
            while _active is not None:
                job.check()
                if monotonic() >= deadline:
                    raise TranslationBusy("이전 번역의 종료가 지연되고 있습니다. 잠시 후 다시 시도하세요.")
                _guard.wait(timeout=0.1)
            job.check()
            _active = job
            job.executing = True
        except BaseException:
            _running.pop(identifier, None)
            remember(identifier, "cancelled")
            _guard.notify_all()
            raise
    token = _current.set(job)
    try:
        job.check()
        yield
    finally:
        _current.reset(token)
        with _guard:
            _running.pop(identifier, None)
            remember(identifier, "completed" if job.committed else "cancelled")
            job.executing = False
            _active = None
            _guard.notify_all()


def translation_checkpoint() -> None:
    job = _current.get()
    if job:
        job.check()


@contextmanager
def translation_transport(abort: Callable[[], None]) -> Iterator[None]:
    """Interrupt model I/O for explicit cancellation and a disconnected reader."""
    job = _current.get()
    if job is None:
        yield
        return
    stopped = threading.Event()
    with _guard:
        job.check()
        job.abort_transport = abort

    def watch_connection() -> None:
        while not stopped.wait(0.1):
            if job.cancelled or job.disconnected():
                with _guard:
                    job.cancelled = True
                    if job.abort_transport is abort:
                        abort()
                return

    watcher = threading.Thread(target=watch_connection, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        stopped.set()
        watcher.join(timeout=1)
        with _guard:
            if job.abort_transport is abort:
                job.abort_transport = None


def commit_translation(write: Callable[[], None]) -> None:
    # A cancel acknowledgement cannot race a write that has already committed.
    with _guard:
        job = _current.get()
        if job:
            job.check()
        write()
        if job:
            job.committed = True
