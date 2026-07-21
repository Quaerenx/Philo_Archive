from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable
from urllib.parse import quote


SCRIPT_SITE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT_SITE))

from path_config import REPO, ROOT, SITE, SOURCE_ROOT_NAMES  # noqa: E402


SCHEMA_VERSION = 1
HASH_CHUNK_BYTES = 1024 * 1024
REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
ROLES = {
    "corpus",
    "mutable",
    "derived",
    "tracked_metadata",
    "forensic_optional",
    "model_optional",
}

MUTABLE_NAMES = (
    "ai/bible_sentence_translations.jsonl",
    "ai/kierkegaard_sentence_translations.jsonl",
    "ai/nietzsche_sentence_translations.jsonl",
    "ai/wittgenstein_sentence_translations.jsonl",
    "notes/nietzsche_notes.jsonl",
)
REQUIRED_AI_NAMES = tuple(PurePosixPath(name).name for name in MUTABLE_NAMES if name.startswith("ai/"))
REQUIRED_NOTES_NAMES = tuple(PurePosixPath(name).name for name in MUTABLE_NAMES if name.startswith("notes/"))
DERIVED_NAMES = (
    "bible_segments.jsonl",
    "kierkegaard_segments.jsonl",
    "nietzsche_segments.jsonl",
    "wittgenstein_segments.jsonl",
    "search_index.jsonl",
    "search_index.sqlite",
)
TRACKED_METADATA_NAMES = (
    "ai_prompt_templates.json",
    "bible_metadata.json",
    "kierkegaard_metadata.json",
    "nietzsche_catalog.json",
    "nietzsche_concepts.json",
    "nietzsche_encoding_report.json",
    "nietzsche_metadata.json",
    "nietzsche_notes_schema.json",
    "search_eval_queries.json",
    "wittgenstein_metadata.json",
)
FORENSIC_OPTIONAL_NAMES = (
    "artifact_manifest.local.json",
    "runtime.local/gemma_response_cache.sqlite",
    "runtime.local/runtime_metrics.jsonl",
)
EXPECTED_ABSENT_NOTES = (
    "notes/bible_notes.jsonl",
    "notes/kierkegaard_notes.jsonl",
    "notes/wittgenstein_notes.jsonl",
)
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class SnapshotError(RuntimeError):
    pass


def logical_absolute(path: Path) -> Path:
    raw = os.fspath(path.expanduser())
    if os.name == "nt":
        if raw.startswith("\\\\?\\UNC\\"):
            raw = "\\\\" + raw[len("\\\\?\\UNC\\") :]
        elif raw.startswith("\\\\?\\"):
            raw = raw[len("\\\\?\\") :]
    return Path(os.path.abspath(raw))


def native_io_path(path: Path) -> str:
    raw = os.fspath(logical_absolute(path))
    if os.name != "nt":
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def fs_lstat(path: Path) -> os.stat_result:
    return os.lstat(native_io_path(path))


def fs_stat(path: Path) -> os.stat_result:
    return os.stat(native_io_path(path), follow_symlinks=False)


def fs_exists(path: Path) -> bool:
    try:
        fs_lstat(path)
        return True
    except FileNotFoundError:
        return False


def fs_is_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(fs_stat(path).st_mode)
    except FileNotFoundError:
        return False


def fs_is_dir(path: Path) -> bool:
    try:
        return stat.S_ISDIR(fs_stat(path).st_mode)
    except FileNotFoundError:
        return False


def is_relative_to(path: Path, root: Path) -> bool:
    path = logical_absolute(path)
    root = logical_absolute(root)
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_manifest_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise SnapshotError(f"unsafe manifest path: {value!r}")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise SnapshotError(f"absolute manifest path is forbidden: {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SnapshotError(f"unsafe manifest path: {value!r}")
    if value != unicodedata.normalize("NFC", value):
        raise SnapshotError(f"manifest path must use Unicode NFC: {value!r}")
    for part in parts:
        if ":" in part or part.endswith((".", " ")):
            raise SnapshotError(f"unsafe Windows manifest path: {value!r}")
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise SnapshotError(f"reserved Windows manifest path: {value!r}")
    return PurePosixPath(*parts).as_posix()


def validate_path_collisions(paths: Iterable[str]) -> None:
    seen: dict[str, str] = {}
    for path in paths:
        normalized = safe_manifest_path(path)
        key = unicodedata.normalize("NFC", normalized).casefold()
        previous = seen.get(key)
        if previous is not None and previous != normalized:
            raise SnapshotError(f"case/Unicode manifest path collision: {previous!r} and {normalized!r}")
        seen[key] = normalized


def repo_relative(path: Path, repo_root: Path) -> str:
    resolved = logical_absolute(path)
    repo = logical_absolute(repo_root)
    relative = os.path.relpath(resolved, repo)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep) or os.path.isabs(relative):
        raise SnapshotError(f"source is outside repo root: {path}")
    return safe_manifest_path(Path(relative).as_posix())


def lstat_is_reparse(path: Path) -> bool:
    info = fs_lstat(path)
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & REPARSE_ATTRIBUTE
    )


def ensure_component_safety(path: Path, stop: Path | None = None) -> None:
    current = logical_absolute(path)
    stop_absolute = logical_absolute(stop) if stop is not None else None
    while True:
        if fs_exists(current):
            if lstat_is_reparse(current):
                raise SnapshotError(f"symlink/reparse point is forbidden: {current}")
        if stop_absolute is not None and os.path.normcase(current) == os.path.normcase(stop_absolute):
            return
        if current.parent == current:
            return
        current = current.parent


def iter_regular_files(root: Path) -> Iterable[Path]:
    root = logical_absolute(root)
    if not fs_is_dir(root):
        raise SnapshotError(f"required directory is missing: {root}")
    ensure_component_safety(root)
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(native_io_path(directory)) as scanner:
            entries = sorted(scanner, key=lambda entry: entry.name)
        child_directories: list[Path] = []
        for entry in entries:
            path = directory / entry.name
            info = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & REPARSE_ATTRIBUTE):
                raise SnapshotError(f"symlink/reparse point is forbidden: {path}")
            if stat.S_ISDIR(info.st_mode):
                child_directories.append(path)
            elif stat.S_ISREG(info.st_mode):
                yield path
            else:
                raise SnapshotError(f"non-regular source entry is forbidden: {path}")
        stack.extend(reversed(child_directories))


def file_signature(path: Path) -> tuple[int, int, int, int]:
    info = fs_stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise SnapshotError(f"source is not a regular file: {path}")
    if bool(getattr(info, "st_file_attributes", 0) & REPARSE_ATTRIBUTE):
        raise SnapshotError(f"reparse-point file is forbidden: {path}")
    return (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)


def sha256_stream(path: Path) -> tuple[str, int]:
    path = logical_absolute(path)
    before = file_signature(path)
    digest = hashlib.sha256()
    length = 0
    with open(native_io_path(path), "rb") as handle:
        descriptor_info = os.fstat(handle.fileno())
        if not stat.S_ISREG(descriptor_info.st_mode):
            raise SnapshotError(f"source changed to a non-regular file: {path}")
        descriptor_signature = (
            descriptor_info.st_size,
            descriptor_info.st_mtime_ns,
            descriptor_info.st_dev,
            descriptor_info.st_ino,
        )
        if descriptor_signature != before:
            raise SnapshotError(f"source identity changed before hashing: {path}")
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
            length += len(chunk)
    after = file_signature(path)
    if before != after or length != after[0]:
        raise SnapshotError(f"source changed while hashing: {path}")
    return digest.hexdigest(), length


def jsonl_facts(path: Path) -> dict[str, Any]:
    path = logical_absolute(path)
    before = file_signature(path)
    records = valid = malformed = blank = 0
    schema_versions: Counter[str] = Counter()
    cache_identities: Counter[tuple[str, ...]] = Counter()
    with open(native_io_path(path), "rb") as handle:
        descriptor_info = os.fstat(handle.fileno())
        descriptor_signature = (
            descriptor_info.st_size,
            descriptor_info.st_mtime_ns,
            descriptor_info.st_dev,
            descriptor_info.st_ino,
        )
        if descriptor_signature != before:
            raise SnapshotError(f"JSONL identity changed before inspection: {path}")
        for raw_line in handle:
            if not raw_line.strip():
                blank += 1
                continue
            records += 1
            try:
                payload = json.loads(raw_line.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("JSONL record is not an object")
                valid += 1
                if "schema_version" in payload:
                    schema_versions[str(payload.get("schema_version"))] += 1
                if payload.get("record_type") == "ai_sentence_translation":
                    cache_identities[
                        (
                            str(payload.get("corpus_id", "")),
                            str(payload.get("work_id", "")),
                            str(payload.get("variant_id", "")),
                            str(payload.get("segment_id", "")),
                            str(payload.get("sentence_id", "")),
                            str(payload.get("sentence_text_sha256", "")),
                            str(payload.get("prompt_sha256", "")),
                        )
                    ] += 1
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                malformed += 1
    after = file_signature(path)
    if before != after:
        raise SnapshotError(f"JSONL changed while inspecting: {path}")
    return {
        "records": records,
        "valid_records": valid,
        "malformed_records": malformed,
        "blank_lines": blank,
        "schema_versions": dict(sorted(schema_versions.items())),
        "duplicate_cache_identity_rows": sum(count - 1 for count in cache_identities.values() if count > 1),
    }


def sqlite_sidecars(path: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    path = logical_absolute(path)
    for suffix in ("-wal", "-shm", "-journal"):
        candidate = Path(f"{path}{suffix}")
        if fs_exists(candidate):
            ensure_component_safety(candidate)
            found[suffix[1:]] = fs_stat(candidate).st_size
    return found


def sqlite_facts(path: Path) -> dict[str, Any]:
    path = logical_absolute(path)
    before = file_signature(path)
    sidecars_before = sqlite_sidecars(path)
    if sidecars_before:
        after = file_signature(path)
        sidecars_after = sqlite_sidecars(path)
        if before != after or sidecars_before != sidecars_after:
            raise SnapshotError(f"SQLite changed while inspecting: {path.name}")
        return {
            "quick_check": "not_run_sidecars_present",
            "table_counts": {},
            "sidecars": sidecars_after,
        }
    uri = "file:" + quote(native_io_path(path), safe=":") + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        checks = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
        table_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        virtual = {
            str(name)
            for name, sql in table_rows
            if isinstance(sql, str) and "VIRTUAL TABLE" in sql.upper()
        }
        shadow_suffixes = ("_data", "_idx", "_content", "_docsize", "_config")
        counts: dict[str, int] = {}
        for name, _sql in table_rows:
            name = str(name)
            if any(name == f"{base}{suffix}" for base in virtual for suffix in shadow_suffixes):
                continue
            quoted = name.replace('"', '""')
            counts[name] = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
    except sqlite3.DatabaseError as exc:
        raise SnapshotError(f"SQLite inspection failed for {path.name}: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()
    if checks != ["ok"]:
        raise SnapshotError(f"SQLite quick_check failed for {path.name}: {checks}")
    after = file_signature(path)
    sidecars_after = sqlite_sidecars(path)
    if before != after or sidecars_before != sidecars_after:
        raise SnapshotError(f"SQLite changed while inspecting: {path.name}")
    return {"quick_check": "ok", "table_counts": counts, "sidecars": sidecars_after}


def classify_facts(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".jsonl":
        return {"jsonl": jsonl_facts(path)}
    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return {"sqlite": sqlite_facts(path)}
    return {}


def add_file(
    selected: dict[str, tuple[Path, str]],
    repo_root: Path,
    path: Path,
    role: str,
    manifest_path: str | None = None,
) -> None:
    if role not in ROLES:
        raise SnapshotError(f"unknown role: {role}")
    path = logical_absolute(path)
    if not fs_is_file(path):
        raise SnapshotError(f"required file is missing: {path}")
    ensure_component_safety(path)
    key = safe_manifest_path(manifest_path) if manifest_path else repo_relative(path, repo_root)
    if key in selected:
        raise SnapshotError(f"duplicate manifest path: {key}")
    selected[key] = (path, role)


def select_sources(
    repo_root: Path,
    data_root: Path,
    corpus_root: Path,
    source_root_paths: list[str],
    ai_root: Path,
    notes_root: Path,
    model_path: Path | None,
    model_repo_path: str | None,
    include_forensic: bool,
) -> dict[str, tuple[Path, str]]:
    selected: dict[str, tuple[Path, str]] = {}
    for relative_name in source_root_paths:
        safe_name = safe_manifest_path(relative_name)
        source_root = logical_absolute(corpus_root / Path(*PurePosixPath(safe_name).parts))
        if not fs_is_dir(source_root):
            raise SnapshotError(f"required corpus root is missing: {safe_name}")
        for path in iter_regular_files(source_root):
            relative = safe_manifest_path(path.relative_to(source_root).as_posix())
            add_file(selected, repo_root, path, "corpus", manifest_path=f"{safe_name}/{relative}")

    data_relative = repo_relative(data_root, repo_root)
    for name in REQUIRED_AI_NAMES:
        add_file(selected, repo_root, ai_root / name, "mutable", manifest_path=f"{data_relative}/ai/{name}")
    for name in REQUIRED_NOTES_NAMES:
        add_file(selected, repo_root, notes_root / name, "mutable", manifest_path=f"{data_relative}/notes/{name}")
    for directory_name, directory in (("ai", ai_root), ("notes", notes_root)):
        directory = logical_absolute(directory)
        if fs_is_dir(directory):
            for candidate in iter_regular_files(directory):
                relative = safe_manifest_path(candidate.relative_to(directory).as_posix())
                if PurePosixPath(relative).name == ".gitkeep":
                    continue
                if relative.lower().endswith(("-wal", "-shm", "-journal")):
                    continue
                key = f"{data_relative}/{directory_name}/{relative}"
                if key not in selected:
                    add_file(selected, repo_root, candidate, "mutable", manifest_path=key)
    for name in DERIVED_NAMES:
        add_file(selected, repo_root, data_root / Path(*PurePosixPath(name).parts), "derived")
    for name in TRACKED_METADATA_NAMES:
        add_file(selected, repo_root, data_root / Path(*PurePosixPath(name).parts), "tracked_metadata")
    if include_forensic:
        for name in FORENSIC_OPTIONAL_NAMES:
            candidate = data_root / Path(*PurePosixPath(name).parts)
            if fs_exists(candidate):
                add_file(selected, repo_root, candidate, "forensic_optional")

    if model_path is not None:
        model_path = logical_absolute(model_path)
        if not fs_is_file(model_path):
            raise SnapshotError(f"optional model file is missing: {model_path}")
        ensure_component_safety(model_path)
        model_key = model_repo_path or f"{data_relative}/models/{model_path.name}"
        add_file(selected, repo_root, model_path, "model_optional", manifest_path=model_key)
    elif model_repo_path is not None:
        raise SnapshotError("--model-repo-path requires --model-path")
    return selected


def git_value(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_root.as_posix()}", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def consistency_record(mode: str, asserted: bool) -> dict[str, Any]:
    if mode == "reader_quiesced" and not asserted:
        raise SnapshotError("reader_quiesced mode requires --reader-quiesced assertion")
    if mode == "preflight" and asserted:
        raise SnapshotError("--reader-quiesced cannot be combined with preflight mode")
    if mode == "reader_quiesced":
        return {
            "mode": mode,
            "reader_quiesced_asserted": True,
            "point_in_time_consistent": False,
            "restore_eligible": False,
            "capture_candidate": True,
            "statement": (
                "Reader and writers were operator-asserted quiesced while this manifest was built; "
                "external-device verification and a fresh restore are still required."
            ),
        }
    return {
        "mode": mode,
        "reader_quiesced_asserted": False,
        "point_in_time_consistent": False,
        "restore_eligible": False,
        "capture_candidate": False,
        "statement": "Preflight is per-file stable only and is not a point-in-time backup.",
    }


def prepare_output_dir(output_dir: Path, repo_root: Path, source_roots: list[Path]) -> Path:
    output = logical_absolute(output_dir)
    repo = logical_absolute(repo_root)
    if is_relative_to(output, repo) or is_relative_to(repo, output):
        raise SnapshotError("output directory must be external to the repository")
    for source in source_roots:
        resolved_source = logical_absolute(source)
        if is_relative_to(output, resolved_source) or is_relative_to(resolved_source, output):
            raise SnapshotError("output directory overlaps a source root")
    if not fs_is_dir(output.parent):
        raise SnapshotError("output parent must already exist")
    ensure_component_safety(output.parent)
    if fs_exists(output):
        ensure_component_safety(output)
        if not fs_is_dir(output):
            raise SnapshotError("output directory must not exist or must be empty")
        with os.scandir(native_io_path(output)) as scanner:
            nonempty = next(scanner, None) is not None
        if nonempty:
            raise SnapshotError("output directory must not exist or must be empty")
    else:
        os.mkdir(native_io_path(output))
    return output


def atomic_write(path: Path, content: bytes) -> None:
    path = logical_absolute(path)
    temporary = path.with_name(f".{path.name}.tmp")
    with open(native_io_path(temporary), "xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(native_io_path(temporary), native_io_path(path))


def create_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = logical_absolute(args.repo_root)
    corpus_root = logical_absolute(args.corpus_root)
    data_root = logical_absolute(args.data_root or repo_root / "reader_site" / "data")
    ai_root = (
        args.ai_root
        or Path(os.environ.get("PHILO_AI_DIR", str(data_root / "ai")))
    )
    notes_root = (
        args.notes_root
        or Path(os.environ.get("PHILO_NOTES_DIR", str(data_root / "notes")))
    )
    ai_root = logical_absolute(ai_root)
    notes_root = logical_absolute(notes_root)
    for label, directory in (
        ("repo root", repo_root),
        ("corpus root", corpus_root),
        ("data root", data_root),
        ("AI root", ai_root),
        ("notes root", notes_root),
    ):
        if not fs_is_dir(directory):
            raise SnapshotError(f"{label} is missing or not a directory: {directory}")
    if not is_relative_to(data_root, repo_root):
        raise SnapshotError("data root must be within repo root")
    ensure_component_safety(repo_root)
    ensure_component_safety(corpus_root)
    ensure_component_safety(data_root, repo_root)
    ensure_component_safety(ai_root)
    ensure_component_safety(notes_root)
    source_names = args.source_root or list(SOURCE_ROOT_NAMES)
    if len(source_names) != len(SOURCE_ROOT_NAMES) or set(source_names) != set(SOURCE_ROOT_NAMES):
        raise SnapshotError("the exact centralized corpus root set is required")
    source_paths = [corpus_root / Path(*PurePosixPath(safe_manifest_path(name)).parts) for name in source_names]
    consistency = consistency_record(args.consistency, args.reader_quiesced)
    selected = select_sources(
        repo_root,
        data_root,
        corpus_root,
        source_names,
        ai_root,
        notes_root,
        args.model_path,
        args.model_repo_path,
        args.include_forensic,
    )
    validate_path_collisions(selected)

    git_commit = args.git_commit or git_value(repo_root, "rev-parse", "HEAD")
    git_branch = args.git_branch or git_value(repo_root, "branch", "--show-current")
    if not git_commit or not git_branch:
        raise SnapshotError("git commit and branch must be recorded")
    if args.model_path is not None:
        missing_provenance = [
            label
            for label, value in (
                ("--model-source-url", args.model_source_url),
                ("--model-revision", args.model_revision),
                ("--model-license", args.model_license),
            )
            if not value
        ]
        if missing_provenance:
            raise SnapshotError("model inclusion requires " + ", ".join(missing_provenance))

    records: list[dict[str, Any]] = []
    for key in sorted(selected):
        path, role = selected[key]
        digest, length = sha256_stream(path)
        record: dict[str, Any] = {
            "path": key,
            "role": role,
            "bytes": length,
            "sha256": digest,
            "restore_required": role != "forensic_optional",
            "git_tracked": role == "tracked_metadata",
        }
        record.update(classify_facts(path))
        jsonl_record = record.get("jsonl")
        if consistency["mode"] == "reader_quiesced" and jsonl_record and (
            jsonl_record["malformed_records"] or jsonl_record["blank_lines"]
        ):
            raise SnapshotError(f"strict JSONL validation failed: {key}")
        sqlite_record = record.get("sqlite")
        if consistency["mode"] == "reader_quiesced" and sqlite_record and sqlite_record["sidecars"]:
            raise SnapshotError(f"SQLite sidecars remain while reader is asserted quiesced: {key}")
        records.append(record)

    files_payload = b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )
    role_counts = dict(sorted(Counter(record["role"] for record in records).items()))
    role_bytes = {
        role: sum(record["bytes"] for record in records if record["role"] == role)
        for role in role_counts
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "philo-backup-snapshot",
        "manifest_state": "MANIFEST_COMPLETE",
        "backup_state": "MANIFEST_ONLY",
        "backup_complete": False,
        "path_semantics": "logical POSIX backup paths; absolute paths are forbidden",
        "git": {"commit": git_commit, "branch": git_branch},
        "consistency": consistency,
        "scope": {
            "corpus_roots": len(source_names),
            "corpus_root_names": sorted(source_names),
            "corpus_layout": "repo_collocated" if corpus_root == repo_root else "external_override",
            "ai_layout": "default_repo" if ai_root == data_root / "ai" else "runtime_override",
            "notes_layout": "default_repo" if notes_root == data_root / "notes" else "runtime_override",
            "required_mutable_files": len(MUTABLE_NAMES),
            "required_derived_files": len(DERIVED_NAMES),
            "required_tracked_metadata_files": len(TRACKED_METADATA_NAMES),
            "forensic_included": args.include_forensic,
            "optional_model_included": args.model_path is not None,
            "absent_expected_files": [
                f"{repo_relative(data_root, repo_root)}/{name}"
                for name in EXPECTED_ABSENT_NOTES
                if not fs_exists(notes_root / PurePosixPath(name).name)
            ],
        },
        "file_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "role_counts": role_counts,
        "role_bytes": role_bytes,
        "files_jsonl_sha256": hashlib.sha256(files_payload).hexdigest(),
    }
    if args.model_path is not None:
        manifest["model_provenance"] = {
            "source_url": args.model_source_url,
            "revision": args.model_revision,
            "license": args.model_license,
        }
    output = prepare_output_dir(
        args.output_dir,
        repo_root,
        [*source_paths, data_root, ai_root, notes_root],
    )
    atomic_write(output / "files.jsonl", files_payload)
    manifest_payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(output / "manifest.json", manifest_payload)
    return manifest


def load_snapshot(manifest_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_dir = logical_absolute(manifest_dir)
    ensure_component_safety(manifest_dir)
    manifest_path = manifest_dir / "manifest.json"
    files_path = manifest_dir / "files.jsonl"
    if not fs_is_file(manifest_path) or not fs_is_file(files_path):
        raise SnapshotError("manifest.json and files.jsonl are required")
    with open(native_io_path(manifest_path), "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("format") != "philo-backup-snapshot":
        raise SnapshotError("unsupported backup snapshot manifest")
    with open(native_io_path(files_path), "rb") as handle:
        raw_files = handle.read()
    if hashlib.sha256(raw_files).hexdigest() != manifest.get("files_jsonl_sha256"):
        raise SnapshotError("files.jsonl checksum does not match manifest.json")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(raw_files.splitlines(), 1):
        if not raw_line.strip():
            raise SnapshotError(f"blank files.jsonl line: {line_number}")
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotError(f"invalid files.jsonl line: {line_number}") from exc
        record["path"] = safe_manifest_path(str(record.get("path", "")))
        if record.get("role") not in ROLES:
            raise SnapshotError(f"invalid role for {record['path']}")
        records.append(record)
    paths = [record["path"] for record in records]
    validate_path_collisions(paths)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise SnapshotError("files.jsonl paths must be unique and deterministically sorted")
    expected_roles = dict(sorted(Counter(record["role"] for record in records).items()))
    if manifest.get("file_count") != len(records) or manifest.get("role_counts") != expected_roles:
        raise SnapshotError("manifest summary does not match files.jsonl")
    if manifest.get("total_bytes") != sum(int(record["bytes"]) for record in records):
        raise SnapshotError("manifest byte total does not match files.jsonl")
    return manifest, records


def payload_files(payload_root: Path) -> dict[str, Path]:
    payload_root = logical_absolute(payload_root)
    files: dict[str, Path] = {}
    for path in iter_regular_files(payload_root):
        key = safe_manifest_path(path.relative_to(payload_root).as_posix())
        files[key] = path
    validate_path_collisions(files)
    return files


def verify_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = logical_absolute(args.repo_root)
    manifest_dir = logical_absolute(args.manifest_dir)
    payload_root = logical_absolute(args.payload_root)
    for label, directory in (
        ("repo root", repo_root),
        ("manifest directory", manifest_dir),
        ("payload root", payload_root),
    ):
        if not fs_is_dir(directory):
            raise SnapshotError(f"{label} is missing or not a directory: {directory}")
    if is_relative_to(payload_root, repo_root) or is_relative_to(repo_root, payload_root):
        raise SnapshotError("payload root must be external to the repository")
    if is_relative_to(payload_root, manifest_dir) or is_relative_to(manifest_dir, payload_root):
        raise SnapshotError("payload root and manifest directory must not overlap")
    manifest, records = load_snapshot(manifest_dir)
    actual = payload_files(payload_root)
    expected_paths = {record["path"] for record in records}
    actual_paths = set(actual)
    errors: list[str] = []
    for path in sorted(expected_paths - actual_paths):
        errors.append(f"missing: {path}")
    for path in sorted(actual_paths - expected_paths):
        errors.append(f"extra: {path}")
    by_path = {record["path"]: record for record in records}
    for key in sorted(expected_paths & actual_paths):
        record = by_path[key]
        path = actual[key]
        digest, length = sha256_stream(path)
        if length != record["bytes"]:
            errors.append(f"size mismatch: {key}")
        if digest != record["sha256"]:
            errors.append(f"hash mismatch: {key}")
        if "jsonl" in record:
            facts = jsonl_facts(path)
            if facts != record["jsonl"]:
                errors.append(f"JSONL facts mismatch: {key}")
        if "sqlite" in record:
            try:
                facts = sqlite_facts(path)
            except SnapshotError as exc:
                errors.append(f"SQLite verification failed: {key}: {exc}")
            else:
                if facts["quick_check"] != record["sqlite"]["quick_check"]:
                    errors.append(f"SQLite quick_check mismatch: {key}")
                if facts["table_counts"] != record["sqlite"]["table_counts"]:
                    errors.append(f"SQLite counts mismatch: {key}")
                if facts["sidecars"]:
                    errors.append(f"unexpected SQLite sidecars: {key}")
    if errors:
        raise SnapshotError("backup verification failed:\n" + "\n".join(errors))
    return {
        "integrity_verified": True,
        "backup_complete": False,
        "file_count": len(records),
        "total_bytes": manifest["total_bytes"],
        "consistency_mode": manifest["consistency"]["mode"],
        "restore_eligible": bool(manifest["consistency"]["restore_eligible"]),
        "remaining_gates": ["distinct_external_device", "fresh_restore_verification"],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Create and verify a Philo backup snapshot manifest.",
        allow_abbrev=False,
    )
    commands = result.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "create",
        help="Inventory source files and write manifest files only.",
        allow_abbrev=False,
    )
    create.add_argument("--repo-root", type=Path, default=REPO)
    create.add_argument("--corpus-root", type=Path, default=ROOT)
    create.add_argument("--data-root", type=Path, default=None)
    create.add_argument("--ai-root", type=Path, default=None)
    create.add_argument("--notes-root", type=Path, default=None)
    create.add_argument("--source-root", action="append", default=None, help="Repo-relative corpus root; repeat four times.")
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--consistency", choices=("preflight", "reader_quiesced"), required=True)
    create.add_argument("--reader-quiesced", action="store_true")
    create.add_argument("--include-forensic", action="store_true")
    create.add_argument("--git-commit")
    create.add_argument("--git-branch")
    create.add_argument("--model-path", type=Path)
    create.add_argument("--model-repo-path")
    create.add_argument("--model-source-url")
    create.add_argument("--model-revision")
    create.add_argument("--model-license")

    verify = commands.add_parser(
        "verify",
        help="Verify an already-copied external payload against manifests.",
        allow_abbrev=False,
    )
    verify.add_argument("--repo-root", type=Path, default=REPO)
    verify.add_argument("--manifest-dir", type=Path, required=True)
    verify.add_argument("--payload-root", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        result = create_snapshot(args) if args.command == "create" else verify_snapshot(args)
    except (SnapshotError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"backup snapshot error: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
