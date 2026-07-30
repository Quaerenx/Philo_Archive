from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _lock_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def jsonl_snapshot_key(path: Path) -> tuple[str, int, int, int] | None:
    """Return a cache key that changes whenever a JSONL snapshot changes."""
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    changed_ns = getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000))
    return str(path.resolve()), metadata.st_mtime_ns, changed_ns, metadata.st_size


def _path_lock(path: Path) -> threading.RLock:
    key = _lock_key(path)
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextmanager
def locked_jsonl(path: Path) -> Iterator[None]:
    """Serialize a complete JSONL mutation within this reader process."""
    with _path_lock(path):
        yield


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_jsonl(path: Path, records: list[dict]) -> None:
    """Write a complete JSONL snapshot and atomically replace the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    with locked_jsonl(path):
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            _sync_directory(path.parent)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
