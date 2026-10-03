from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SITE))

from services import human_reviews as reviews  # noqa: E402
from services import jsonl_storage as storage  # noqa: E402


INPUT_HASH = "d" * 64
CRASH_EXIT = 81


def mutation_fixture(root: Path) -> list[dict]:
    return [
        {"path": root / "first.jsonl", "before": b'{"state":"before-first"}\r\n', "after": b'{"state":"after-first"}\n'},
        {"path": root / "second.json", "before": b'{"state":"before-second"}\n', "after": b'{"state":"after-second"}\n'},
        {"path": root / "new.jsonl", "before": None, "after": b'{"state":"after-new"}\n'},
    ]


def pending_path(root: Path) -> Path:
    return root / "transaction" / "pending"


def transaction_locks(root: Path, mutations: list[dict]) -> ExitStack:
    stack = ExitStack()
    try:
        stack.enter_context(storage.locked_jsonl(root / "transaction" / "import.jsonl"))
        for mutation in mutations:
            stack.enter_context(storage.locked_jsonl(mutation["path"]))
        return stack
    except BaseException:
        stack.close()
        raise


def child(mode: str, root: Path) -> None:
    root = root.resolve()
    relative = root.relative_to(Path(tempfile.gettempdir()).resolve())
    if not relative.parts or not relative.parts[0].startswith("philo_storage_fault_"):
        raise ValueError("storage fault children require their synthetic temporary workspace")
    if mode in {"hold-lock", "waiting-writer"}:
        path = root / "contended.jsonl"
        if mode == "waiting-writer":
            (root / "writer.started").write_bytes(b"ready")
        with storage.locked_jsonl(path):
            if mode == "hold-lock":
                (root / "holder.ready").write_bytes(b"ready")
                while True:
                    time.sleep(0.1)
            storage.atomic_append_jsonl(path, {"id": "writer"}, expected_signature=storage.jsonl_snapshot_key(path))
            (root / "writer.done").write_bytes(b"done")
        return
    if mode == "append-recovery-truncated":
        path = root / "append.jsonl"
        original = storage.os.fsync

        def stop_after_recovery_sync(descriptor):
            original(descriptor)
            if os.fstat(descriptor).st_ino == path.stat().st_ino:
                os._exit(CRASH_EXIT)

        with patch.object(storage.os, "fsync", side_effect=stop_after_recovery_sync):
            with storage.locked_jsonl(path):
                pass
        raise AssertionError("recovery did not reach the crash boundary")
    mutations = mutation_fixture(root)
    original = reviews.atomic_bytes

    def interrupted_write(path, value):
        if mode == "rollback-first" and path == mutations[2]["path"] and value == mutations[2]["after"]:
            raise OSError(errno.ENOSPC, "synthetic storage exhaustion")
        original(path, value)
        if mode == "rollback-first" and path == mutations[0]["path"] and value == mutations[0]["before"]:
            os._exit(CRASH_EXIT)
        if mode == "import-first" and path == mutations[0]["path"] and value == mutations[0]["after"]:
            os._exit(CRASH_EXIT)
        if mode == "import-second" and path == mutations[1]["path"] and value == mutations[1]["after"]:
            os._exit(CRASH_EXIT)
        if mode == "import-committed" and path.name == "manifest.json" and json.loads(value)["state"] == "committed":
            os._exit(CRASH_EXIT)

    with transaction_locks(root, mutations), patch.object(reviews, "atomic_bytes", side_effect=interrupted_write):
        reviews.apply_plan(mutations, pending_path(root), INPUT_HASH)
    raise AssertionError("import did not reach the crash boundary")


class StorageFaultContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="philo_storage_fault_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def prepare_import(self, root: Path) -> list[dict]:
        root.mkdir(parents=True, exist_ok=True)
        mutations = mutation_fixture(root)
        for mutation in mutations:
            if mutation["before"] is not None:
                mutation["path"].write_bytes(mutation["before"])
        return mutations

    def start_child(self, mode: str, root: Path):
        process = subprocess.Popen(
            [sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()), "--child", mode, str(root)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        def stop():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

        self.addCleanup(stop)
        return process

    def crash_child(self, mode: str, root: Path):
        process = self.start_child(mode, root)
        stdout, stderr = process.communicate(timeout=12)
        self.assertTrue(process.returncode == CRASH_EXIT, "synthetic child did not stop at the requested boundary")
        self.assertTrue(not stdout and not stderr, "crash child unexpectedly emitted diagnostic content")

    def wait_for(self, marker: Path, process):
        deadline = time.monotonic() + 8
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(marker.exists(), "synthetic child did not reach its barrier")

    def recover_import(self, root: Path, mutations: list[dict]):
        with transaction_locks(root, mutations):
            return reviews.recover_pending(pending_path(root), INPUT_HASH, {item["path"] for item in mutations}, apply=True)

    def assert_state(self, mutations: list[dict], field: str):
        for item in mutations:
            actual = item["path"].read_bytes() if item["path"].exists() else None
            self.assertTrue(actual == item[field], "transaction target bytes or original absence were not preserved")

    def fingerprint(self, root: Path):
        return {str(path.relative_to(root)): (reviews.digest(path.read_bytes()), path.stat().st_mtime_ns)
                for path in root.rglob("*") if path.is_file()}

    def test_actual_import_crashes_and_interrupted_rollback_recover_exact_targets(self):
        for mode in ("import-first", "import-second", "rollback-first"):
            with self.subTest(boundary=mode):
                root = self.root / mode
                mutations = self.prepare_import(root)
                self.crash_child(mode, root)
                self.assertTrue(pending_path(root).exists(), "interrupted transaction lost its recovery journal")
                self.assertTrue(self.recover_import(root, mutations), "prepared transaction was not rolled back")
                self.assert_state(mutations, "before")
                self.assertFalse(pending_path(root).exists())
                self.assertEqual(len(list((root / "transaction").glob("backup-*"))), 1)
                with transaction_locks(root, mutations):
                    reviews.apply_plan(mutations, pending_path(root), INPUT_HASH)
                self.assert_state(mutations, "after")

    def test_durable_committed_process_crash_preserves_committed_targets(self):
        mutations = self.prepare_import(self.root)
        self.crash_child("import-committed", self.root)
        self.assertFalse(self.recover_import(self.root, mutations), "committed transaction must not report a rollback")
        self.assert_state(mutations, "after")
        self.assertFalse(pending_path(self.root).exists())
        self.assertEqual(len(list((self.root / "transaction").glob("backup-*"))), 1)

    def test_commit_marker_failures_report_the_on_disk_outcome(self):
        for published in (False, True):
            with self.subTest(published=published):
                root = self.root / str(published)
                mutations = self.prepare_import(root)
                original = reviews.atomic_bytes

                def interrupt_commit(path, value):
                    committing = path.name == "manifest.json" and json.loads(value)["state"] == "committed"
                    if committing and not published:
                        raise OSError(errno.ENOSPC, "synthetic commit marker exhaustion")
                    original(path, value)
                    if committing:
                        raise KeyboardInterrupt()

                expected = "import_failed_committed" if published else "import_failed_rolled_back"
                with transaction_locks(root, mutations), patch.object(reviews, "atomic_bytes", side_effect=interrupt_commit):
                    with self.assertRaisesRegex(reviews.HumanReviewError, expected):
                        reviews.apply_plan(mutations, pending_path(root), INPUT_HASH)
                self.assert_state(mutations, "after" if published else "before")
                self.assertFalse(pending_path(root).exists())
                self.assertEqual(len(list((root / "transaction").glob("backup-*"))), 1)

    def test_actual_commit_marker_fsync_and_replace_failures_restore_all_targets(self):
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                root = self.root / operation
                mutations = self.prepare_import(root)
                original_sync, original_replace = reviews.os.fsync, reviews.os.replace
                injected = False

                def is_committed_temporary(path):
                    return path.parent == pending_path(root) and path.name.startswith(".manifest.json.") and json.loads(path.read_bytes())["state"] == "committed"

                def failing_sync(descriptor):
                    nonlocal injected
                    for candidate in pending_path(root).glob(".manifest.json.*.tmp"):
                        if candidate.stat().st_ino == os.fstat(descriptor).st_ino and is_committed_temporary(candidate):
                            injected = True
                            raise OSError(errno.ENOSPC, "synthetic commit journal sync exhaustion")
                    return original_sync(descriptor)

                def failing_replace(source, target):
                    nonlocal injected
                    if Path(target) == pending_path(root) / "manifest.json" and is_committed_temporary(Path(source)):
                        injected = True
                        raise OSError(errno.ENOSPC, "synthetic commit journal publication exhaustion")
                    return original_replace(source, target)

                replacement = failing_sync if operation == "fsync" else failing_replace
                with transaction_locks(root, mutations), patch.object(reviews.os, operation, replacement):
                    with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_rolled_back"):
                        reviews.apply_plan(mutations, pending_path(root), INPUT_HASH)
                self.assertTrue(injected, "commit fault was not exercised at the real storage primitive")
                self.assert_state(mutations, "before")
                self.assertFalse(pending_path(root).exists())
                self.assertEqual(len(list((root / "transaction").glob("backup-*"))), 1)

    def test_full_import_retry_after_late_committed_error_is_no_op(self):
        from check_human_review_import_contracts import HumanReviewImportContracts

        fixture = HumanReviewImportContracts("test_apply_preserves_originals_private_lines_and_repeated_apply_is_no_op")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = reviews.atomic_bytes

        def interrupt_after_commit(path, value):
            original(path, value)
            if path.name == "manifest.json" and json.loads(value)["state"] == "committed":
                raise KeyboardInterrupt()

        with patch.object(reviews, "atomic_bytes", side_effect=interrupt_after_commit):
            with self.assertRaisesRegex(reviews.HumanReviewError, "import_failed_committed"):
                fixture.run_import(apply=True)
        before = fixture.snapshot()
        self.assertEqual(fixture.run_import(apply=True)["status"], "no_op")
        self.assertTrue(fixture.snapshot() == before, "retry after a committed interruption altered the fixture")

    def test_recovery_prevalidates_all_targets_and_backup_checksums(self):
        for changed in ("later-target", "before-backup", "after-backup"):
            with self.subTest(changed=changed):
                root = self.root / changed
                mutations = self.prepare_import(root)
                self.crash_child("import-second", root)
                path = mutations[1]["path"] if changed == "later-target" else pending_path(root) / ("1.before" if changed == "before-backup" else "1.after")
                path.write_bytes(b'{"state":"synthetic-external-change"}\n')
                before = self.fingerprint(root)
                code = "import_target_changed_externally" if changed == "later-target" else "import_backup_checksum_mismatch"
                with self.assertRaisesRegex(reviews.HumanReviewError, code):
                    self.recover_import(root, mutations)
                self.assertTrue(self.fingerprint(root) == before, "failed validation modified a target or recovery evidence")

    def prepare_append(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        path = root / "append.jsonl"
        before = b'{"id":"before"}\n'
        data = b'{"id":"uncommitted"}\n'
        path.write_bytes(before)
        storage._publish_append_journal(path, data, path.stat(), before)
        with path.open("ab") as stream:
            stream.write(data[:9])
            stream.flush()
            os.fsync(stream.fileno())
        return path, before

    def test_recovery_process_crash_after_truncate_replays_and_backup_stays_read_only(self):
        path, before = self.prepare_append(self.root)
        original = self.fingerprint(self.root)
        with self.assertRaisesRegex(ValueError, "Pending JSONL append recovery"):
            with storage.locked_jsonl(path, read_only=True):
                pass
        self.assertTrue(self.fingerprint(self.root) == original, "read-only backup inspection repaired a journal")
        self.crash_child("append-recovery-truncated", self.root)
        self.assertTrue(path.read_bytes() == before)
        self.assertTrue(storage._append_journal_path(path).exists())
        with storage.locked_jsonl(path):
            pass
        self.assertTrue(path.read_bytes() == before)
        self.assertFalse(storage._append_journal_path(path).exists())

    def test_invalid_append_journal_and_same_size_external_changes_preserve_evidence(self):
        for corruption in ("magic", "payload-length", "existence-flag", "append-bytes", "replacement-inode"):
            with self.subTest(corruption=corruption):
                root = self.root / corruption
                path, _ = self.prepare_append(root)
                journal = storage._append_journal_path(path)
                value = journal.read_bytes()
                if corruption == "magic":
                    journal.write_bytes(b"X" + value[1:])
                elif corruption == "payload-length":
                    journal.write_bytes(value[:-1])
                elif corruption == "existence-flag":
                    index = len(storage._APPEND_MAGIC)
                    journal.write_bytes(value[:index] + b"\x02" + value[index + 1:])
                elif corruption == "append-bytes":
                    value = path.read_bytes()
                    path.write_bytes(value[:-1] + b"X")
                else:
                    info = path.stat()
                    replacement = root / "replacement.tmp"
                    replacement.write_bytes(path.read_bytes())
                    os.utime(replacement, ns=(info.st_atime_ns, info.st_mtime_ns))
                    os.replace(replacement, path)
                before = self.fingerprint(root)
                with self.assertRaises(ValueError):
                    with storage.locked_jsonl(path):
                        pass
                # Lock creation is an allowed coordination sidecar, not target or journal mutation.
                after = self.fingerprint(root)
                self.assertTrue(all(after[name] == signature for name, signature in before.items()), "invalid recovery altered target bytes or the journal")
                self.assertTrue(journal.exists())

    def test_enospc_blocks_append_and_rollback_but_keeps_a_retryable_journal(self):
        path = self.root / "append.jsonl"
        before = b'{"id":"before"}\n'
        path.write_bytes(before)
        original_open, original_sync = Path.open, storage.os.fsync
        rollback_started = False

        class PartialWriter:
            def __init__(self, handle): self.handle = handle
            def __getattr__(self, name): return getattr(self.handle, name)
            def __enter__(self): return self
            def __exit__(self, *args): return self.handle.__exit__(*args)
            def write(self, data):
                nonlocal rollback_started
                self.handle.write(data[:9])
                self.handle.flush()
                rollback_started = True
                raise OSError(errno.ENOSPC, "synthetic append exhaustion")

        def open_file(candidate, mode="r", *args, **kwargs):
            handle = original_open(candidate, mode, *args, **kwargs)
            return PartialWriter(handle) if candidate == path and mode == "ab" else handle

        def failed_rollback_sync(descriptor):
            if rollback_started and os.fstat(descriptor).st_ino == path.stat().st_ino:
                raise OSError(errno.ENOSPC, "synthetic rollback sync exhaustion")
            return original_sync(descriptor)

        with patch.object(Path, "open", open_file), patch.object(storage.os, "fsync", failed_rollback_sync):
            with self.assertRaises(OSError) as raised:
                storage.atomic_append_jsonl(path, {"id": "uncommitted"}, expected_signature=storage.jsonl_snapshot_key(path))
        self.assertEqual(raised.exception.errno, errno.ENOSPC)
        self.assertTrue(path.read_bytes() == before)
        self.assertTrue(storage._append_journal_path(path).exists())
        with storage.locked_jsonl(path):
            pass
        self.assertTrue(path.read_bytes() == before)
        self.assertFalse(storage._append_journal_path(path).exists())

    def test_real_os_lock_timeout_and_holder_termination_release_waiting_writer(self):
        path = self.root / "contended.jsonl"
        path.write_bytes(b'{"id":"before"}\n')
        holder = self.start_child("hold-lock", self.root)
        self.wait_for(self.root / "holder.ready", holder)
        before = path.read_bytes()
        with patch.object(storage, "monotonic", side_effect=[0, 31]):
            with self.assertRaisesRegex(ValueError, "JSONL file is busy"):
                with storage.locked_jsonl(path, read_only=True):
                    pass
        self.assertTrue(path.read_bytes() == before)
        writer = self.start_child("waiting-writer", self.root)
        self.wait_for(self.root / "writer.started", writer)
        time.sleep(0.15)
        self.assertFalse((self.root / "writer.done").exists(), "writer bypassed a real process-held lock")
        holder.kill()
        holder.communicate(timeout=5)
        stdout, stderr = writer.communicate(timeout=12)
        self.assertTrue(writer.returncode == 0 and not stdout and not stderr, "waiting writer did not acquire the released OS lock")
        self.assertTrue((self.root / "writer.done").exists())
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        self.assertEqual([record["id"] for record in records], ["before", "writer"])


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(sys.argv[2], Path(sys.argv[3]))
    else:
        unittest.main(verbosity=1)
