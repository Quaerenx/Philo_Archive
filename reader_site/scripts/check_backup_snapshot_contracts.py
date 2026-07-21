from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath


SITE = Path(__file__).resolve().parents[1]
SCRIPTS = SITE / "scripts"
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SCRIPTS))

import build_backup_snapshot as snapshot  # noqa: E402


SCRIPT = SCRIPTS / "build_backup_snapshot.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_tool(arguments: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(f"command failed: {result.stderr or result.stdout}")
    if not expect_success and result.returncode == 0:
        raise AssertionError("command unexpectedly succeeded")
    return result


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def build_sqlite(path: Path, rows: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany("INSERT INTO records(value) VALUES (?)", [(value,) for value in rows])
        connection.commit()
    finally:
        connection.close()


def build_repo(repo: Path) -> None:
    for index, root_name in enumerate(snapshot.SOURCE_ROOT_NAMES):
        write(repo / root_name / "source" / f"item-{index}.txt", f"corpus-{index}\n")

    data = repo / "reader_site" / "data"
    for index, name in enumerate(snapshot.MUTABLE_NAMES):
        content = '{"id": 1}\n'
        if index == 0:
            content += "not-json\n\n"
        write(data / Path(*PurePosixPath(name).parts), content)
    for name in snapshot.DERIVED_NAMES:
        path = data / Path(*PurePosixPath(name).parts)
        if path.suffix == ".sqlite":
            build_sqlite(path, ("alpha", "beta"))
        else:
            write(path, '{"segment_id": "s1"}\n')
    for name in snapshot.TRACKED_METADATA_NAMES:
        write(data / Path(*PurePosixPath(name).parts), '{"schema_version": 1}\n')
    for name in snapshot.FORENSIC_OPTIONAL_NAMES:
        path = data / Path(*PurePosixPath(name).parts)
        if path.suffix == ".sqlite":
            build_sqlite(path, ("cached",))
        elif path.suffix == ".jsonl":
            write(path, '{"event": "synthetic"}\n')
        else:
            write(path, '{"forensic": true}\n')


def create_args(repo: Path, output: Path, model: Path, consistency: str) -> list[str]:
    result = [
        "create",
        "--repo-root",
        str(repo),
        "--corpus-root",
        str(repo),
        "--ai-root",
        str(repo / "reader_site" / "data" / "ai"),
        "--notes-root",
        str(repo / "reader_site" / "data" / "notes"),
        "--output-dir",
        str(output),
        "--consistency",
        consistency,
        "--include-forensic",
        "--git-commit",
        "a" * 40,
        "--git-branch",
        "synthetic-backup",
        "--model-path",
        str(model),
        "--model-repo-path",
        "reader_site/data/models/synthetic.gguf",
        "--model-source-url",
        "https://example.invalid/model",
        "--model-revision",
        "synthetic-revision",
        "--model-license",
        "synthetic-license",
    ]
    if consistency == "reader_quiesced":
        result.append("--reader-quiesced")
    return result


def records_from(snapshot_dir: Path) -> list[dict]:
    return [json.loads(line) for line in snapshot_dir.joinpath("files.jsonl").read_text(encoding="utf-8").splitlines()]


def copy_payload(snapshot_dir: Path, repo: Path, model: Path, destination: Path) -> None:
    for record in records_from(snapshot_dir):
        relative = Path(*PurePosixPath(record["path"]).parts)
        source = model if record["role"] == "model_optional" else repo / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def verify_args(repo: Path, manifest: Path, payload: Path) -> list[str]:
    return [
        "verify",
        "--repo-root",
        str(repo),
        "--manifest-dir",
        str(manifest),
        "--payload-root",
        str(payload),
    ]


def source_fingerprints(repo: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(candidate for candidate in repo.rglob("*") if candidate.is_file()):
        relative = path.relative_to(repo).as_posix()
        values[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def check_manifest_contract(snapshot_dir: Path, expected_consistency: str) -> None:
    manifest = json.loads(snapshot_dir.joinpath("manifest.json").read_text(encoding="utf-8"))
    records = records_from(snapshot_dir)
    paths = [record["path"] for record in records]
    require(paths == sorted(paths), "manifest records are not deterministic")
    require(len(paths) == len(set(paths)), "manifest has duplicate paths")
    require(set(record["role"] for record in records) == snapshot.ROLES, "not all roles were represented")
    for path in paths:
        require("\\" not in path, f"non-POSIX path: {path}")
        require(not PurePosixPath(path).is_absolute(), f"absolute POSIX path: {path}")
        require(not PureWindowsPath(path).is_absolute(), f"absolute Windows path: {path}")
        require(".." not in PurePosixPath(path).parts, f"traversal path: {path}")
    require(manifest["consistency"]["mode"] == expected_consistency, "wrong consistency mode")
    require(manifest["consistency"]["restore_eligible"] is False, "manifest-only output claimed restore eligibility")
    require(manifest["backup_state"] == "MANIFEST_ONLY", "wrong backup state")
    require(manifest["backup_complete"] is False, "manifest creation claimed backup completion")
    require(manifest["scope"]["corpus_roots"] == len(snapshot.SOURCE_ROOT_NAMES), "wrong corpus scope")
    require(manifest["scope"]["required_mutable_files"] == 5, "wrong mutable scope")
    require(manifest["scope"]["required_derived_files"] == 6, "wrong derived scope")
    require(manifest["scope"]["required_tracked_metadata_files"] == 10, "wrong metadata scope")
    require(manifest["git"] == {"branch": "synthetic-backup", "commit": "a" * 40}, "wrong git binding")
    malformed = [record for record in records if record.get("jsonl", {}).get("malformed_records") == 1]
    if expected_consistency == "preflight":
        require(len(malformed) == 1, "preflight did not record malformed JSONL facts")
    else:
        require(not malformed, "restore-eligible manifest contains malformed JSONL")
    search = next(record for record in records if record["path"].endswith("search_index.sqlite"))
    require(search["sqlite"]["quick_check"] == "ok", "SQLite quick_check missing")
    require(search["sqlite"]["table_counts"] == {"records": 2}, "SQLite row counts are wrong")
    serialized = snapshot_dir.joinpath("manifest.json").read_text(encoding="utf-8")
    require("temp" not in manifest.get("path_semantics", "").lower(), "unexpected path disclosure")
    require(str(snapshot_dir) not in serialized, "manifest leaked an absolute output path")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="philo-backup-contract-") as temporary:
        base = Path(temporary)
        repo = base / "synthetic_repo"
        repo.mkdir()
        build_repo(repo)
        model = base / "synthetic-model.gguf"
        model.write_bytes(b"synthetic model bytes\n")
        before = source_fingerprints(repo)

        missing_assertion = run_tool(
            [item for item in create_args(repo, base / "missing-assertion", model, "reader_quiesced") if item != "--reader-quiesced"],
            expect_success=False,
        )
        require("requires --reader-quiesced" in missing_assertion.stderr, "quiescence assertion was not enforced")

        preflight = base / "manifest-preflight"
        run_tool(create_args(repo, preflight, model, "preflight"))
        check_manifest_contract(preflight, "preflight")
        require(source_fingerprints(repo) == before, "preflight create modified the source repository")

        strict_malformed = run_tool(
            create_args(repo, base / "strict-malformed", model, "reader_quiesced"),
            expect_success=False,
        )
        require("strict JSONL validation failed" in strict_malformed.stderr, "strict malformed JSONL was accepted")
        write(repo / "reader_site" / "data" / "ai" / "bible_sentence_translations.jsonl", '{"id": 1}\n')
        before = source_fingerprints(repo)

        first = base / "manifest-one"
        second = base / "manifest-two"
        run_tool(create_args(repo, first, model, "reader_quiesced"))
        run_tool(create_args(repo, second, model, "reader_quiesced"))
        check_manifest_contract(first, "reader_quiesced")
        require(first.joinpath("files.jsonl").read_bytes() == second.joinpath("files.jsonl").read_bytes(), "files manifest is nondeterministic")
        require(first.joinpath("manifest.json").read_bytes() == second.joinpath("manifest.json").read_bytes(), "summary manifest is nondeterministic")
        require(source_fingerprints(repo) == before, "create modified the source repository")

        payload = base / "payload-ok"
        copy_payload(first, repo, model, payload)
        verified = run_tool(verify_args(repo, first, payload))
        verification = json.loads(verified.stdout)
        require(verification["integrity_verified"] is True, "happy-path integrity verification failed")
        require(verification["backup_complete"] is False, "payload integrity check claimed backup completion")

        tampered = base / "payload-tampered"
        shutil.copytree(payload, tampered)
        target = next(path for path in tampered.rglob("*.jsonl"))
        target.write_bytes(target.read_bytes() + b"{}\n")
        failure = run_tool(verify_args(repo, first, tampered), expect_success=False)
        require("mismatch" in failure.stderr, "tampering was not detected")

        missing = base / "payload-missing"
        shutil.copytree(payload, missing)
        next(path for path in missing.rglob("*.txt")).unlink()
        failure = run_tool(verify_args(repo, first, missing), expect_success=False)
        require("missing:" in failure.stderr, "missing file was not detected")

        extra = base / "payload-extra"
        shutil.copytree(payload, extra)
        write(extra / "unexpected.bin", b"extra")
        failure = run_tool(verify_args(repo, first, extra), expect_success=False)
        require("extra:" in failure.stderr, "extra file was not detected")

        nonempty = base / "nonempty-output"
        write(nonempty / "marker", "do not overwrite")
        failure = run_tool(create_args(repo, nonempty, model, "preflight"), expect_success=False)
        require("must not exist or must be empty" in failure.stderr, "nonempty output was accepted")

        overlap = repo / "reader_site" / "data" / "backup-manifest"
        failure = run_tool(create_args(repo, overlap, model, "preflight"), expect_success=False)
        require("external to the repository" in failure.stderr, "repository-overlapping output was accepted")

        traversal_args = create_args(repo, base / "traversal-output", model, "preflight")
        traversal_args[traversal_args.index("reader_site/data/models/synthetic.gguf")] = "../outside.gguf"
        failure = run_tool(traversal_args, expect_success=False)
        require("unsafe manifest path" in failure.stderr, "manifest traversal was accepted")

        sqlite_path = repo / "reader_site" / "data" / "search_index.sqlite"
        wal_path = Path(f"{sqlite_path}-wal")
        wal_path.write_bytes(b"synthetic live WAL marker")
        wal_preflight = base / "wal-preflight"
        run_tool(create_args(repo, wal_preflight, model, "preflight"))
        wal_record = next(
            record for record in records_from(wal_preflight) if record["path"].endswith("search_index.sqlite")
        )
        require(wal_record["sqlite"]["sidecars"].get("wal") == wal_path.stat().st_size, "WAL was not recorded")
        failure = run_tool(
            create_args(repo, base / "wal-quiesced", model, "reader_quiesced"),
            expect_success=False,
        )
        require("SQLite sidecars remain" in failure.stderr, "quiesced capture accepted a live WAL")
        wal_path.unlink()

        bad_manifest = base / "bad-manifest"
        shutil.copytree(first, bad_manifest)
        bad_records = records_from(bad_manifest)
        bad_records[0]["path"] = "../escape"
        files_payload = b"".join(
            (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            for record in bad_records
        )
        bad_manifest.joinpath("files.jsonl").write_bytes(files_payload)
        summary = json.loads(bad_manifest.joinpath("manifest.json").read_text(encoding="utf-8"))
        summary["files_jsonl_sha256"] = hashlib.sha256(files_payload).hexdigest()
        bad_manifest.joinpath("manifest.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        failure = run_tool(verify_args(repo, bad_manifest, payload), expect_success=False)
        require("unsafe manifest path" in failure.stderr, "unsafe path in manifest was accepted")

        symlink_tested = False
        link = repo / snapshot.SOURCE_ROOT_NAMES[0] / "unsafe-link"
        try:
            link.symlink_to(model)
        except OSError:
            pass
        else:
            symlink_tested = True
            failure = run_tool(create_args(repo, base / "symlink-output", model, "preflight"), expect_success=False)
            require("symlink/reparse" in failure.stderr, "source symlink was accepted")

        print(
            "backup snapshot contracts ok "
            f"(create/verify/determinism/tamper/missing/extra/malformed/path/quiescence; symlink_tested={symlink_tested})"
        )


if __name__ == "__main__":
    main()
