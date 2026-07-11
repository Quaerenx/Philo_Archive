from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SITE = Path(__file__).resolve().parents[1]
CACHE_SCHEMA_VERSION = 1
CACHE_DB_ENV = "PHILO_GEMMA_CACHE_DB"
CACHE_DIR_ENV = "PHILO_GEMMA_CACHE_DIR"
CACHE_DB_NAME = "gemma_response_cache.sqlite"
_SCHEMA_LOCK = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def cache_db_path() -> Path:
    configured_db = os.environ.get(CACHE_DB_ENV, "").strip()
    if configured_db:
        return Path(configured_db).expanduser()
    configured_dir = os.environ.get(CACHE_DIR_ENV, "").strip()
    cache_dir = Path(configured_dir).expanduser() if configured_dir else SITE / "data" / "runtime.local"
    return cache_dir / CACHE_DB_NAME


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def build_cache_key(
    *,
    namespace: str,
    prompt_version: str,
    model_name: str,
    input_sha256: str,
    options: dict[str, Any],
) -> str:
    return stable_hash(
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "namespace": namespace,
            "prompt_version": prompt_version,
            "model_name": model_name,
            "input_sha256": input_sha256,
            "options": options,
        }
    )


def connect_cache() -> sqlite3.Connection:
    path = cache_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    except sqlite3.DatabaseError:
        conn.close()
        raise


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gemma_response_cache (
            cache_key TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            namespace TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            model_name TEXT NOT NULL,
            input_sha256 TEXT NOT NULL,
            options_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_gemma_response_cache_lookup
        ON gemma_response_cache(namespace, prompt_version, model_name, input_sha256)
        """
    )
    conn.commit()


def quarantine_cache_file(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        shutil.move(str(path), str(target))
    except OSError:
        try:
            path.unlink()
        except OSError:
            return
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass


def with_cache_connection() -> sqlite3.Connection | None:
    path = cache_db_path()
    with _SCHEMA_LOCK:
        try:
            conn = connect_cache()
            ensure_schema(conn)
            return conn
        except sqlite3.DatabaseError:
            try:
                conn.close()  # type: ignore[possibly-undefined]
            except Exception:
                pass
            quarantine_cache_file(path)
            try:
                conn = connect_cache()
                ensure_schema(conn)
                return conn
            except sqlite3.DatabaseError:
                return None


def cached_response(cache_key: str) -> dict[str, Any] | None:
    conn = with_cache_connection()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT response_json FROM gemma_response_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        try:
            response = json.loads(str(row["response_json"]))
        except json.JSONDecodeError:
            conn.execute("DELETE FROM gemma_response_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
            return None
        if not isinstance(response, dict):
            conn.execute("DELETE FROM gemma_response_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
            return None
        conn.execute(
            """
            UPDATE gemma_response_cache
            SET hit_count = hit_count + 1, updated_at = ?
            WHERE cache_key = ?
            """,
            (utc_now(), cache_key),
        )
        conn.commit()
        return response
    except sqlite3.DatabaseError:
        quarantine_cache_file(cache_db_path())
        return None
    finally:
        conn.close()


def store_response(
    *,
    cache_key: str,
    namespace: str,
    prompt_version: str,
    model_name: str,
    input_sha256: str,
    options: dict[str, Any],
    response: dict[str, Any],
) -> bool:
    conn = with_cache_connection()
    if conn is None:
        return False
    now = utc_now()
    try:
        conn.execute(
            """
            INSERT INTO gemma_response_cache (
                cache_key, schema_version, namespace, prompt_version, model_name,
                input_sha256, options_json, response_json, created_at, updated_at, hit_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(cache_key) DO UPDATE SET
                response_json = excluded.response_json,
                updated_at = excluded.updated_at
            """,
            (
                cache_key,
                CACHE_SCHEMA_VERSION,
                namespace,
                prompt_version,
                model_name,
                input_sha256,
                stable_json(options),
                stable_json(response),
                now,
                now,
            ),
        )
        conn.commit()
        return True
    except (TypeError, sqlite3.DatabaseError):
        return False
    finally:
        conn.close()
