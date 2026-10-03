from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import struct
import tempfile
import threading
from collections import OrderedDict, namedtuple
from contextlib import contextmanager, nullcontext
from pathlib import Path
from time import monotonic
from typing import Callable, Iterator


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}
_LOCK_DEPTH = threading.local()
_APPEND_MAGIC = b"PHILOAPP1\n"
_APPEND_HEADER = struct.Struct(">BQqq16sQ32s")
_RECOVERY_TAIL_BYTES = 4096
CacheInfo = namedtuple("CacheInfo", "hits misses maxsize currsize")


class JsonlSnapshotCache:
    """Keep one current snapshot per file, bounded by entries and source bytes."""

    def __init__(self, maxsize: int = 16, max_bytes: int = 32 * 1024 * 1024) -> None:
        self.maxsize = maxsize
        self.max_bytes = max_bytes
        self._snapshots: OrderedDict[str, tuple[tuple, tuple[dict, ...]]] = OrderedDict()
        self._validated: OrderedDict[str, tuple] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: tuple, loader: Callable[[str], tuple[dict, ...]]) -> tuple[dict, ...]:
        with self._lock:
            for _attempt in range(3):
                current = self._snapshots.get(key[0])
                if current is not None and current[0] == key:
                    self._hits += 1
                    self._snapshots.move_to_end(key[0])
                    return current[1]
                self._misses += 1
                records = loader(key[0])
                after = jsonl_snapshot_key(Path(key[0]))
                if after == key:
                    self.remember(key, records)
                    return records
                if after is None:
                    return ()
                key = after
        raise ValueError("JSONL file changed repeatedly while loading; retry the request")

    def remember(self, key: tuple | None, records: tuple[dict, ...]) -> None:
        if key is None:
            return
        with self._lock:
            self._snapshots.pop(key[0], None)
            if key[3] <= self.max_bytes:
                self._snapshots[key[0]] = key, records
            while len(self._snapshots) > self.maxsize or sum(item[0][3] for item in self._snapshots.values()) > self.max_bytes:
                self._snapshots.popitem(last=False)
            self.remember_validation(key)

    def peek(self, key: tuple | None) -> tuple[dict, ...] | None:
        if key is None:
            return None
        with self._lock:
            current = self._snapshots.get(key[0])
            return current[1] if current is not None and current[0] == key else None

    def is_validated(self, key: tuple) -> bool:
        with self._lock:
            if self._validated.get(key[0]) == key:
                self._validated.move_to_end(key[0])
                return True
            return False

    def remember_validation(self, key: tuple) -> None:
        with self._lock:
            current = self._snapshots.get(key[0])
            if current is not None and current[0] != key:
                self._snapshots.pop(key[0])
            self._validated[key[0]] = key
            self._validated.move_to_end(key[0])
            while len(self._validated) > self.maxsize:
                self._validated.popitem(last=False)

    def invalidate(self, path: Path) -> None:
        with self._lock:
            self._snapshots.pop(str(path.resolve()), None)
            self._validated.pop(str(path.resolve()), None)

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()
            self._validated.clear()
            self._hits = self._misses = 0

    def info(self):
        with self._lock:
            return CacheInfo(self._hits, self._misses, self.maxsize, len(self._snapshots))


def _lock_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def jsonl_snapshot_key(path: Path) -> tuple[str, int, int, int, int] | None:
    """Return a cache key that changes whenever a JSONL snapshot changes."""
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    changed_ns = getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000))
    return str(path.resolve()), metadata.st_mtime_ns, changed_ns, metadata.st_size, metadata.st_ino


def _path_lock(path: Path) -> threading.RLock:
    key = _lock_key(path)
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


@contextmanager
def locked_jsonl(path: Path, *, read_only: bool = False) -> Iterator[None]:
    """Lock cooperating readers/writers and roll back interrupted appends."""
    with _path_lock(path):
        key = _lock_key(path)
        depths = getattr(_LOCK_DEPTH, "paths", None)
        if depths is None:
            depths = _LOCK_DEPTH.paths = {}
        if depths.get(key):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return
        lock_path = path.with_name(f".{path.name}.lock")
        if read_only:
            try:
                lock_handle = lock_path.open("rb")
            except FileNotFoundError:
                lock_handle = None
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            lock_handle = lock_path.open("a+b")
        with lock_handle if lock_handle is not None else nullcontext() as handle:
            if handle is not None and not read_only and handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            if handle is not None:
                _lock_file(handle)
            depths[key] = 1
            try:
                if read_only:
                    if _append_journal_path(path).exists():
                        raise ValueError("Pending JSONL append recovery; open the Reader to recover before backing up")
                else:
                    _recover_append(path)
                yield
            finally:
                depths.pop(key, None)
                if handle is not None:
                    _unlock_file(handle)


def _lock_file(handle) -> None:
    deadline = monotonic() + 30
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise
            if monotonic() >= deadline:
                raise ValueError("JSONL file is busy; retry the request") from exc
            threading.Event().wait(0.02)


def _unlock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_journal_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.append-journal")


def is_jsonl_auxiliary(path: Path) -> bool:
    return re.fullmatch(r"\..+\.jsonl\.(?:lock|append-journal|(?:append\.)?[A-Za-z0-9_-]+\.tmp)", path.name, re.IGNORECASE) is not None


def _recover_append(path: Path) -> None:
    """An intent journal remains until commit; recovery restores its old prefix."""
    journal_path = _append_journal_path(path)
    try:
        journal = journal_path.open("rb")
    except FileNotFoundError:
        return
    with journal:
        header = journal.read(len(_APPEND_MAGIC) + _APPEND_HEADER.size)
        if len(header) != len(_APPEND_MAGIC) + _APPEND_HEADER.size or not header.startswith(_APPEND_MAGIC):
            raise ValueError("Invalid JSONL append journal; preserve it and repair the storage")
        existed, size, accessed, modified, inode_bytes, added_size, tail_hash = _APPEND_HEADER.unpack(header[len(_APPEND_MAGIC):])
        if existed not in {0, 1} or os.fstat(journal.fileno()).st_size != len(header) + added_size:
            raise ValueError("Invalid JSONL append journal; preserve it and repair the storage")
        try:
            info = path.stat()
        except FileNotFoundError:
            if existed:
                raise ValueError("JSONL file disappeared during append recovery; preserve the journal")
            info = None
        if info is not None:
            inode = int.from_bytes(inode_bytes, "big")
            if (existed and info.st_ino != inode) or not size <= info.st_size <= size + added_size:
                raise ValueError("JSONL file changed outside the reader; preserve the append journal")
            with path.open("r+b") as handle:
                handle.seek(max(0, size - _RECOVERY_TAIL_BYTES))
                tail = handle.read(min(size, _RECOVERY_TAIL_BYTES))
                if hashlib.sha256(tail).digest() != tail_hash:
                    raise ValueError("JSONL prefix changed; preserve the append journal")
                remaining = info.st_size - size
                while remaining:
                    count = min(remaining, 1024 * 1024)
                    if handle.read(count) != journal.read(count):
                        raise ValueError("JSONL append differs from its journal; preserve both files")
                    remaining -= count
                handle.truncate(size)
                handle.flush()
                os.fsync(handle.fileno())
            if existed:
                os.utime(path, ns=(accessed, modified))
            else:
                path.unlink()
    journal_path.unlink()
    _sync_directory(path.parent)


def _publish_append_journal(path: Path, data: bytes, info, tail: bytes) -> None:
    header = _APPEND_MAGIC + _APPEND_HEADER.pack(
        int(info is not None), info.st_size if info else 0,
        info.st_atime_ns if info else 0, info.st_mtime_ns if info else 0,
        (info.st_ino if info else 0).to_bytes(16, "big"), len(data), hashlib.sha256(tail).digest(),
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.append.", suffix=".tmp", delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(header)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, _append_journal_path(path))
        temporary_path = None
        _sync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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


def atomic_append_jsonl(path: Path, record: dict, *, expected_signature: tuple | None) -> tuple[str, int, int, int, int]:
    """Append only new bytes, with rollback and locked snapshot reads.

    The caller must validate the existing snapshot before appending. The private
    intent journal permits rollback after an exception or process interruption.
    External readers/writers must use locked_jsonl or stop the reader first.
    """
    if not isinstance(record, dict):
        raise ValueError("JSONL records must be objects")
    data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with locked_jsonl(path):
        signature = jsonl_snapshot_key(path)
        if signature != expected_signature:
            raise ValueError("JSONL file changed after validation; retry the request")
        info = path.stat() if signature is not None else None
        tail = b""
        if info is not None:
            with path.open("rb") as handle:
                handle.seek(max(0, info.st_size - _RECOVERY_TAIL_BYTES))
                tail = handle.read(_RECOVERY_TAIL_BYTES)
            if tail and not tail.endswith(b"\n"):
                data = b"\n" + data
        if jsonl_snapshot_key(path) != signature:
            raise ValueError("JSONL file changed before append; retry the request")
        _publish_append_journal(path, data, info, tail)
        try:
            with path.open("ab") as handle:
                current = os.fstat(handle.fileno())
                if current.st_size != (info.st_size if info else 0) or (info is not None and current.st_ino != info.st_ino):
                    raise ValueError("JSONL file changed before append; preserve its journal")
                if handle.write(data) != len(data):
                    raise OSError("incomplete JSONL append")
                handle.flush()
                os.fsync(handle.fileno())
            new_signature = jsonl_snapshot_key(path)
            if new_signature is None:
                raise OSError("JSONL file disappeared before append commit")
            _append_journal_path(path).unlink()
            _sync_directory(path.parent)
            return new_signature
        except BaseException:
            _recover_append(path)
            raise
