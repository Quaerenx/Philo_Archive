from __future__ import annotations

import ast
import hashlib
import http.client
import io
import json
import logging
import os
import re
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import ExitStack, closing, contextmanager, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(SITE / "scripts"))

import server
import build_search_db
import build_kierkegaard_segments
import build_wittgenstein_segments
import runtime_status
from build_segment_offset_index import build_segment_offset_index
from check_sentence_translation_contracts import passing_pipeline_output, synthetic_sentence_target
from corpora.kierkegaard_text import extract_texts, has_readable_text, reading_source_path
from rendering.documents import render_reading_document, render_segments_from_texts
from segment_utils import markdown_segments
from sentence_units import render_sentence_spans, sentence_units
from path_config import NIETZSCHE_SOURCE_ROOT
from services import notes, sentence_targets, sentence_translations as translations, study_sessions, translation_jobs
from services import jsonl_storage, search, segment_offsets, work_chunks
from corpora import catalogs
import rebuild_all
from services.rebuild_transaction import preserve_artifacts, preflight_registered_sources
from services.segment_offsets import probe_segment_offset_index
from services.search import search_result_from_row, rank_sqlite_rows
from services.translation_jobs import TranslationBusy, TranslationCancelled, cancel_translation, commit_translation, translation_checkpoint, translation_job


@contextmanager
def local_server(handler=server.Handler):
    class QuietHandler(handler):
        def log_message(self, *args):
            pass
    httpd = server.LoopbackThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=5)


@contextmanager
def indexed_fixture(corpus: str, records: list[dict], works: dict):
    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        source = root / f"{corpus}_segments.jsonl"
        source.write_text("".join(json.dumps({
            "schema_version": 1, "corpus_id": corpus, "variant_id": "v", "segment_type": "paragraph",
            "label": "fixture", "order": index, "url": f'/work/{corpus}/{record["work_id"]}#{record["segment_id"]}',
            **record,
        }, ensure_ascii=False) + "\n" for index, record in enumerate(records, 1)), encoding="utf-8")
        metadata = root / f"{corpus}_metadata.json"
        metadata.write_text(json.dumps({"works": works}), encoding="utf-8")
        sources = {corpus: source}
        index = root / "offsets.sqlite"
        build_segment_offset_index(index, sources)
        locations = partial(segment_offsets.indexed_work_segment_locations, index_path=index, segment_files=sources)
        read_records = partial(segment_offsets.read_indexed_segment_records, segment_files=sources)
        stack.enter_context(patch.object(catalogs, corpus.upper() + "_METADATA", metadata))
        if corpus == "bible":
            stack.enter_context(patch.object(catalogs, "BIBLE_SEGMENTS", source))
            stack.enter_context(patch.object(catalogs, "SEGMENT_OFFSET_INDEX", index))
        for module in (catalogs, work_chunks):
            stack.enter_context(patch.object(module, "indexed_work_segment_locations", locations))
            stack.enter_context(patch.object(module, "read_indexed_segment_records", read_records))
        stack.enter_context(patch.object(work_chunks, "SEGMENT_FILES", sources))
        stack.enter_context(patch.object(work_chunks, "SEGMENT_OFFSET_INDEX", index))
        try:
            yield source
        finally:
            work_chunks._cached_work_chunk_manifest.cache_clear()


class ReviewRegressions(unittest.TestCase):
    def test_metadata_cache_reuses_parsing_and_keeps_callers_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text('{"works":{"w":{"title":"before","tags":["a"]}}}', encoding="utf-8")
            catalogs._read_metadata_snapshot.cache_clear()
            with patch.object(catalogs.json, "load", wraps=json.load) as parse:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    values = list(pool.map(lambda _: catalogs.read_json(path), range(8)))
                self.assertEqual(parse.call_count, 1)
            values[0]["works"]["w"]["tags"].append("changed")
            self.assertEqual(catalogs.metadata_record(path, "w")["tags"], ["a"])
            path.write_text('{"works":{"w":{"title":"external replacement"}}}', encoding="utf-8")
            self.assertEqual(catalogs.metadata_record(path, "w")["title"], "external replacement")

    def test_bible_work_lookup_reads_only_its_indexed_records(self):
        records = [
            {"work_id": "v.Gen", "segment_id": "Gen.1.1", "text_raw": "Selected source.", "segment_type": "verse"},
            {"work_id": "v.Exod", "segment_id": "Exod.1.1", "text_raw": "Other source.", "segment_type": "verse"},
        ]
        works = {name: {"work_id": name, "variant_id": "v"} for name in ("v.Gen", "v.Exod")}
        with indexed_fixture("bible", records, works) as source, patch.object(catalogs, "load_bible_segments", side_effect=AssertionError("full corpus read")):
            reads = []
            original_open = Path.open
            class Reader:
                def __init__(self, handle): self.handle = handle
                def __enter__(self): self.handle.__enter__(); return self
                def __exit__(self, *args): return self.handle.__exit__(*args)
                def seek(self, *args): return self.handle.seek(*args)
                def read(self, size=-1): reads.append(size); return self.handle.read(size)
            def track(path, mode="r", *args, **kwargs):
                handle = original_open(path, mode, *args, **kwargs)
                return Reader(handle) if path == source and mode == "rb" else handle
            with patch.object(Path, "open", track):
                selected = catalogs.bible_segments_for_work("v.Gen")
            self.assertEqual([record["segment_id"] for record in selected], ["Gen.1.1"])
            self.assertEqual(len(reads), 1)
            self.assertTrue(0 < reads[0] < source.stat().st_size)
            selected[0]["text_raw"] = "caller mutation"
            with patch.object(catalogs, "read_indexed_segment_records", side_effect=AssertionError("uncached repeat")):
                self.assertEqual(catalogs.bible_segments_for_work("v.Gen")[0]["text_raw"], "Selected source.")
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(segment_offsets.SegmentOffsetIndexError):
                catalogs.bible_segments_for_work("v.Gen")

    def test_virtual_bible_keeps_chapter_anchors_and_hebrew_direction(self):
        records = [
            {"work_id": "v.Gen", "segment_id": identifier, "text_raw": "בראשית", "chapter": chapter, "segment_type": "verse"}
            for identifier, chapter in (("Gen.1.1", 1), ("Gen.1.2", 1), ("Gen.2.1", 2))
        ]
        works = {"v.Gen": {"work_id": "v.Gen", "variant_id": "v", "language": "hbo"}}
        with indexed_fixture("bible", records, works), patch.object(work_chunks, "VIRTUAL_WORK_MIN_SENTENCES", 2), patch.object(work_chunks, "WORK_CHUNK_MAX_SEGMENTS", 1):
            manifest = work_chunks.work_chunk_manifest("bible", "v.Gen", "v")
            self.assertEqual([item["id"] for item in manifest["toc"]], ["Gen.1", "Gen.2"])
            self.assertEqual(work_chunks.chunk_index_for_anchor(manifest, "Gen.2"), 2)
            markup = [work_chunks.render_chunk_records(chunk) for chunk in manifest["chunks"]]
            self.assertEqual("".join(markup).count('id="Gen.1"'), 1)
            self.assertTrue(all('dir="rtl"' in item for item in markup))

    def test_translation_summary_checks_each_source_segment_once(self):
        target = synthetic_sentence_target()
        record = translations.build_record(target, translations.build_sentence_prompt_bundle(target), passing_pipeline_output("fixture"))
        records = [{**record, "id": str(uuid.uuid4())} for _ in range(500)]
        query = {"corpus_id": [target["corpus_id"]], "work_id": [target["work_id"]], "current_sentences": ["1"]}
        with patch.object(translations, "iter_cached_records", return_value=records), patch.object(translations, "ai_record_paths_for_query", return_value=[Path("fixture")]), patch.object(translations, "resolve_segment_target", return_value={"text_raw": target["sentence_text"]}) as resolve:
            payload = translations.sentence_translations_summary_from_query(query)
        self.assertEqual(payload["sentence_state_count"], 1)
        self.assertEqual(payload["count"], 500)
        self.assertEqual(resolve.call_count, 1)

    def test_atomic_append_keeps_old_bytes_and_avoids_reserializing_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            original = b'{ "id": "first", "note": "legacy spacing" }'
            path.write_bytes(original)
            notes.read_jsonl(path)
            before = notes._read_jsonl_snapshot.cache_info()
            with patch.object(jsonl_storage.json, "dumps", wraps=json.dumps) as encode:
                notes.append_jsonl(path, {"id": "next", "note": "new"})
                self.assertEqual(encode.call_count, 1)
            self.assertTrue(path.read_bytes().startswith(original + b"\n"))
            self.assertEqual([item["id"] for item in notes.read_jsonl(path)], ["first", "next"])
            self.assertEqual(notes._read_jsonl_snapshot.cache_info().misses, before.misses)
            valid = path.read_bytes()
            with self.assertRaises(TypeError): notes.append_jsonl(path, {"id": object()})
            self.assertEqual(path.read_bytes(), valid)
            for operation in ("replace", "fsync"):
                with patch.object(jsonl_storage.os, operation, side_effect=OSError("synthetic storage failure")):
                    with self.assertRaises(OSError): notes.append_jsonl(path, {"id": "failed"})
                self.assertEqual(path.read_bytes(), valid)
            self.assertFalse(list(path.parent.glob(".*.tmp")))
            old_signature = jsonl_storage.jsonl_snapshot_key(path)
            path.write_text('{"id":"external"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                jsonl_storage.atomic_append_jsonl(path, {"id": "unsafe"}, expected_signature=old_signature)
            self.assertEqual(notes.read_jsonl(path)[0]["id"], "external")

    def test_jsonl_cache_retains_one_revision_per_file_and_obeys_byte_budget(self):
        cache = jsonl_storage.JsonlSnapshotCache(maxsize=2, max_bytes=100)
        for revision in range(5): cache.remember(("file", revision, revision, 20), ({"revision": revision},))
        self.assertEqual(cache.info().currsize, 1)
        cache.remember(("large", 1, 1, 101), ({"large": True},))
        self.assertEqual(cache.info().currsize, 1)
        for index in range(3): cache.remember((f"small-{index}", 1, 1, 40), ())
        self.assertEqual(cache.info().currsize, 2)

    def test_append_reads_a_bounded_tail_and_keeps_the_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            path.write_text(json.dumps({"id": "old", "body": "x" * (1024 * 1024)}) + "\n", encoding="utf-8")
            signature = jsonl_storage.jsonl_snapshot_key(path)
            inode = path.stat().st_ino
            reads = []
            original_open = Path.open

            class Reader:
                def __init__(self, handle): self.handle = handle
                def __getattr__(self, name): return getattr(self.handle, name)
                def __enter__(self): return self
                def __exit__(self, *_args): self.handle.close()
                def read(self, size=-1):
                    reads.append(size)
                    self.assert_bounded(size)
                    return self.handle.read(size)
                def assert_bounded(self, size):
                    if not 0 < size <= jsonl_storage._RECOVERY_TAIL_BYTES:
                        raise AssertionError("append attempted an unbounded history read")

            def open_file(candidate, mode="r", *args, **kwargs):
                handle = original_open(candidate, mode, *args, **kwargs)
                return Reader(handle) if candidate == path and mode == "rb" else handle

            with patch.object(Path, "open", open_file):
                jsonl_storage.atomic_append_jsonl(path, {"id": "new"}, expected_signature=signature)
            self.assertEqual(reads, [jsonl_storage._RECOVERY_TAIL_BYTES])
            self.assertEqual(path.stat().st_ino, inode)
            self.assertFalse(jsonl_storage._append_journal_path(path).exists())
            self.assertEqual([record["id"] for record in notes.read_jsonl(path)], ["old", "new"])

    def test_append_rolls_back_a_failed_data_sync_and_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            original = b'{"id":"old"}\n'
            path.write_bytes(original)
            real_sync, real_unlink = os.fsync, Path.unlink
            calls = 0

            def fail_data_sync(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("data fsync failed")
                return real_sync(descriptor)

            with patch.object(jsonl_storage.os, "fsync", fail_data_sync):
                with self.assertRaises(OSError): notes.append_jsonl(path, {"id": "not committed"})
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(jsonl_storage._append_journal_path(path).exists())
            failed = False

            def fail_commit(candidate, *args, **kwargs):
                nonlocal failed
                if candidate == jsonl_storage._append_journal_path(path) and not failed:
                    failed = True
                    raise OSError("commit unlink failed")
                return real_unlink(candidate, *args, **kwargs)

            with patch.object(Path, "unlink", fail_commit):
                with self.assertRaises(OSError): notes.append_jsonl(path, {"id": "not committed"})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual([record["id"] for record in notes.read_jsonl(path)], ["old"])
            self.assertFalse(jsonl_storage._append_journal_path(path).exists())

    def test_interrupted_append_recovers_before_the_next_read(self):
        code = '''
import os, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from services import jsonl_storage as storage
path, stage = Path(sys.argv[2]), sys.argv[3]
real_publish, real_sync, real_open = storage._publish_append_journal, os.fsync, Path.open
calls = 0
def publish(*args):
    real_publish(*args)
    if stage == 'intent': os._exit(71)
def sync(descriptor):
    global calls
    calls += 1
    real_sync(descriptor)
    if stage == 'synced' and calls == 2: os._exit(71)
class PartialWriter:
    def __init__(self, handle): self.handle = handle
    def __getattr__(self, name): return getattr(self.handle, name)
    def __enter__(self): return self
    def __exit__(self, *args): self.handle.close()
    def write(self, data):
        self.handle.write(data[:len(data)//2]); self.handle.flush(); real_sync(self.handle.fileno())
        os._exit(71)
def open_file(candidate, mode='r', *args, **kwargs):
    handle = real_open(candidate, mode, *args, **kwargs)
    return PartialWriter(handle) if candidate == path and mode == 'ab' and stage == 'partial' else handle
with patch.object(storage, '_publish_append_journal', publish), patch.object(storage.os, 'fsync', sync), patch.object(Path, 'open', open_file):
    storage.atomic_append_jsonl(path, {'id':'new'}, expected_signature=storage.jsonl_snapshot_key(path))
os._exit(71)
'''
        with tempfile.TemporaryDirectory() as directory:
            for existed in (True, False):
                for stage in ("intent", "partial", "synced", "committed"):
                    with self.subTest(existed=existed, stage=stage):
                        path = Path(directory) / f"{existed}-{stage}.jsonl"
                        original = b'{ "id": "old" }' if existed else b""
                        if existed: path.write_bytes(original)
                        result = subprocess.run([sys.executable, "-c", code, str(SITE), str(path), stage], capture_output=True, text=True, timeout=10)
                        self.assertEqual(result.returncode, 71, result.stderr)
                        expected = (["old"] if existed else []) + (["new"] if stage == "committed" else [])
                        self.assertEqual([record["id"] for record in notes.read_jsonl(path)], expected)
                        self.assertFalse(jsonl_storage._append_journal_path(path).exists())
                        if stage != "committed":
                            self.assertEqual(path.read_bytes() if path.exists() else b"", original)
                            self.assertEqual(path.exists(), existed)

    def test_recovery_preserves_an_unexpected_external_file_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            path.write_bytes(b'{"id":"old"}\n')
            info = path.stat()
            jsonl_storage._publish_append_journal(path, b'{"id":"new"}\n', info, path.read_bytes())
            with path.open("ab") as handle: handle.write(b'{"id":"external"}\n')
            external = path.read_bytes()
            with self.assertRaises(ValueError): notes.read_jsonl(path)
            self.assertEqual(path.read_bytes(), external)
            self.assertTrue(jsonl_storage._append_journal_path(path).exists())

    def test_cooperating_processes_append_without_losing_records(self):
        code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from services import notes
for index in range(20):
    notes.append_jsonl(Path(sys.argv[2]), {'id':sys.argv[3]+'-'+str(index)})
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            processes = [subprocess.Popen([sys.executable, "-c", code, str(SITE), str(path), str(index)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for index in range(4)]
            try:
                for process in processes:
                    _stdout, stderr = process.communicate(timeout=20)
                    self.assertEqual(process.returncode, 0, stderr)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            records = notes.read_jsonl(path)
            self.assertEqual(len(records), 80)
            self.assertEqual(len({record["id"] for record in records}), 80)

    def test_large_validated_files_avoid_reparsing_on_each_append(self):
        for service, cache_name, reader_name, append_name in (
            (notes, "_NOTE_SNAPSHOTS", "_read_jsonl_snapshot", "append_jsonl"),
            (translations, "_TRANSLATION_SNAPSHOTS", "_read_translation_snapshot", "append_record"),
        ):
            with self.subTest(service=service.__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "large.jsonl"
                path.write_text(json.dumps({"id": "old", "body": "x" * 1024}) + "\n", encoding="utf-8")
                cache = jsonl_storage.JsonlSnapshotCache(max_bytes=128)
                with patch.object(service, cache_name, cache), patch.object(service, reader_name, wraps=getattr(service, reader_name)) as reader:
                    append = getattr(service, append_name)
                    append(path, {"id": "new1"})
                    append(path, {"id": "new2"})
                    self.assertEqual(reader.call_count, 1)
                    self.assertEqual(cache.info().currsize, 0)
                    path.write_text('{"id":"external"}\ninvalid json\n', encoding="utf-8")
                    external = path.read_bytes()
                    with self.assertRaises(ValueError): append(path, {"id": "unsafe"})
                    self.assertEqual(path.read_bytes(), external)

    def test_snapshot_reader_waits_for_an_in_progress_append(self):
        code = '''
import os, sys, threading, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from services import notes
path, ready, release = map(Path, sys.argv[2:5])
real_open = Path.open
class PausedWriter:
    def __init__(self, handle): self.handle = handle
    def __getattr__(self, name): return getattr(self.handle, name)
    def __enter__(self): return self
    def __exit__(self, *args): self.handle.close()
    def write(self, data):
        split = len(data)//2
        self.handle.write(data[:split]); self.handle.flush(); os.fsync(self.handle.fileno())
        ready.write_bytes(b'ready')
        deadline = time.monotonic()+10
        while not release.exists():
            if time.monotonic()>deadline: raise TimeoutError('test barrier expired')
            threading.Event().wait(0.01)
        self.handle.write(data[split:])
        return len(data)
def open_file(candidate, mode='r', *args, **kwargs):
    handle = real_open(candidate, mode, *args, **kwargs)
    return PausedWriter(handle) if candidate == path and mode == 'ab' else handle
with patch.object(Path, 'open', open_file): notes.append_jsonl(path, {'id':'new'})
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, ready, release = (root / name for name in ("notes.jsonl", "ready", "release"))
            path.write_bytes(b'{"id":"old"}\n')
            process = subprocess.Popen([sys.executable, "-c", code, str(SITE), str(path), str(ready), str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 8
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    threading.Event().wait(0.01)
                self.assertTrue(ready.exists(), "writer did not reach its partial-append barrier")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(notes.read_jsonl, path)
                    try:
                        threading.Event().wait(0.1)
                        self.assertFalse(future.done(), "reader observed an uncommitted partial record")
                    finally:
                        release.write_bytes(b"release")
                    self.assertEqual([record["id"] for record in future.result(timeout=10)], ["old", "new"])
                _stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
            finally:
                release.write_bytes(b"release")
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_replaced_file_with_preserved_times_invalidates_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.jsonl"
            path.write_bytes(b'{"id":"old"}\n')
            original = path.stat()
            notes.read_jsonl(path)
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(b"broken json!\n")
            os.replace(replacement, path)
            external = path.read_bytes()
            real_stat = Path.stat

            def preserved_stat(candidate, *args, **kwargs):
                info = real_stat(candidate, *args, **kwargs)
                if candidate == path:
                    return SimpleNamespace(st_size=info.st_size, st_mtime_ns=original.st_mtime_ns, st_ctime_ns=original.st_ctime_ns, st_ctime=original.st_ctime, st_ino=info.st_ino)
                return info

            with patch.object(Path, "stat", preserved_stat):
                with self.assertRaises(ValueError): notes.append_jsonl(path, {"id": "unsafe"})
            self.assertEqual(path.read_bytes(), external)

    def test_fts_rank_traversal_preserves_ties_and_cached_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "search.jsonl"; output = root / "search.sqlite"
            source.write_text("".join(json.dumps({"corpus_id": "fixture", "work_id": "w", "variant_id": "v", "segment_id": f"p-{index:04d}", "segment_type": "paragraph", "title": "uniform", "label": "uniform", "url": f"/work/fixture/w#p-{index:04d}", "text": "uniform query sentence."}) + "\n" for index in range(1, 701)), encoding="utf-8")
            with patch.object(build_search_db, "JSONL", source), patch.object(build_search_db, "OUTPUT", output): build_search_db.build_database()
            with patch.object(search, "SEARCH_DB", output), closing(sqlite3.connect(output)) as connection:
                connection.row_factory = sqlite3.Row
                expected = connection.execute("SELECT id FROM search_segments_fts JOIN search_segments s ON s.id=search_segments_fts.rowid WHERE search_segments_fts MATCH ? ORDER BY bm25(search_segments_fts),s.id LIMIT 40 OFFSET 480", ('"query"',)).fetchall()
                actual = search.ranked_fts_rows(connection, "search_segments_fts MATCH ?", ['"query"'], 40, 480)
                self.assertEqual([row["id"] for row in actual], [row["id"] for row in expected])
                with patch.object(search, "rank_sqlite_rows", wraps=search.rank_sqlite_rows) as rank:
                    first = search.search_records_sqlite("query", "", "", "", 30, 0)
                    second = search.search_records_sqlite("query", "", "", "", 30, 30)
                    self.assertEqual(rank.call_count, 1)
                self.assertEqual(first["count"], 700)
                self.assertTrue({item["segment_id"] for item in first["results"]}.isdisjoint({item["segment_id"] for item in second["results"]}))
                first["results"][0]["snippet"] = "caller mutation"
                self.assertNotEqual(search.search_records_sqlite("query", "", "", "", 30, 0)["results"][0]["snippet"], "caller mutation")
                connection.execute("INSERT INTO search_segments_fts(search_segments_fts,rowid,title,label,search_text) SELECT 'delete',id,title,label,search_text FROM search_segments WHERE id=700")
                connection.execute("DELETE FROM search_segments WHERE id=700")
                connection.commit()
                info = output.stat(); os.utime(output, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
                # Readiness changes must not reuse the prior cached total.
                self.assertEqual(search.search_records_sqlite("query", "", "", "", 30, 0)["count"], 699)

    def test_large_jsonl_search_returns_rebuild_guidance_without_scanning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "index.jsonl"
            with source.open("wb") as handle: handle.truncate(search.MAX_REQUEST_JSONL_BYTES + 1)
            with patch.object(search, "SEARCH_INDEX", source), patch.object(search, "SEARCH_DB", root / "missing.sqlite"), patch.object(search, "search_records_jsonl", side_effect=AssertionError("unbounded scan")), patch.object(search, "attach_related_results", side_effect=lambda payload, *_: payload):
                payload = search.search_records("query")
                self.assertIn("build_search_db.py", payload["error"])

    def test_newer_search_index_rejects_the_previous_database_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "index.jsonl"; database = root / "index.sqlite"
            database.write_bytes(b"previous generation")
            source.write_text("new generation", encoding="utf-8")
            stamp = database.stat().st_mtime_ns + 1_000_000_000
            os.utime(source, ns=(stamp, stamp))
            with patch.object(search, "SEARCH_INDEX", source), patch.object(search, "SEARCH_DB", database), patch.object(search, "search_records_sqlite", side_effect=AssertionError("stale DB read")), patch.object(search, "attach_related_results", side_effect=lambda payload, *_: payload):
                self.assertIn("build_search_db.py", search.search_records("query")["error"])
            with patch.object(runtime_status, "SEARCH_INDEX", source), patch.object(runtime_status, "SEARCH_DB", database):
                self.assertIn("error", runtime_status.search_database_summary())

    def test_rebuild_db_skip_excludes_all_database_dependent_checks(self):
        steps = []
        with patch.object(rebuild_all, "run_step", side_effect=lambda step, *_: steps.append(step.script)), redirect_stdout(io.StringIO()):
            rebuild_all.rebuild(SimpleNamespace(skip_search_db=True, skip_manifest=True, no_checks=False))
        required = {step.script for step in rebuild_all.CHECK_STEPS if step.requires_search_db}
        self.assertTrue(required)
        self.assertFalse(required.intersection(steps))
        self.assertIn("check_work_chunk_contracts.py", steps)

    def test_search_health_handles_unopenable_and_disappearing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "index.sqlite"
            database.mkdir()
            with patch.object(runtime_status, "SEARCH_DB", database), patch.object(runtime_status, "SEARCH_INDEX", root / "missing.jsonl"):
                summary = runtime_status.search_database_summary()
                self.assertIn("error", summary)
                self.assertEqual(summary["records"], 0)
                self.assertFalse(summary["fts5"])

            database.rmdir()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE search_segments(corpus_id TEXT)")
                connection.commit()

            def remove_database(*_args):
                database.unlink()
                return False

            with patch.object(runtime_status, "SEARCH_DB", database), patch.object(search, "search_database_stale", side_effect=remove_database):
                summary = runtime_status.search_database_summary()
            self.assertIn("error", summary)
            self.assertFalse(database.exists(), "health checks must not recreate a missing database")

            database.write_bytes(b"fixture")
            with patch.object(search, "SEARCH_DB", database), patch.object(search, "search_database_stale", side_effect=OSError("artifact unavailable")), patch.object(search, "attach_related_results", side_effect=lambda payload, *_: payload):
                self.assertIn("build_search_db.py", search.search_records("query")["error"])

    def test_malformed_model_responses_return_502_and_release_translation_slot(self):
        bodies = (
            b"not-json", b"\xff", b'{"choices":[{"message":[]}]}',
            b'{"choices":[{"message":{"content":{"unexpected":"object"}}}]}',
        )
        for body in bodies:
            with self.subTest(body=body):
                @contextmanager
                def model_response(*_args, **_kwargs):
                    yield io.BytesIO(body)

                def generate(*_args, **_kwargs):
                    with translation_job():
                        return translations.call_llama_json("fixture", {}, {}, "fixture")

                with patch.object(translations, "urlopen", model_response), patch.object(server, "sentence_translation_from_payload", side_effect=generate), local_server() as httpd:
                    with closing(http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)) as connection:
                        connection.request("POST", "/api/sentence-translation", body="{}", headers={"Content-Type": "application/json"})
                        response = connection.getresponse()
                        self.assertEqual(response.status, 502)
                        self.assertFalse(json.loads(response.read())["ok"])
                    with translation_job():
                        translation_checkpoint()

    def test_model_transport_interrupts_a_call_waiting_for_headers(self):
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                entered, released, disconnected, model_stopped = (threading.Event() for _ in range(4))
                results = []
                class Model(server.Handler):
                    def do_POST(self):
                        self.rfile.read(int(self.headers["Content-Length"]))
                        entered.set()
                        while not released.wait(0.02):
                            if self.client_disconnected(): model_stopped.set(); return
                        self.send_json({"choices": [{"message": {"content": "{}"}}]})
                identifier = str(uuid.uuid4())
                def generate():
                    try:
                        with translation_job(identifier, disconnected.is_set):
                            translations.call_llama_json("fixture", {}, {}, "fixture")
                    except TranslationCancelled: results.append("cancelled")
                with local_server(Model) as model, patch.object(translations, "LLAMA_BASE_URL", f"http://127.0.0.1:{model.server_port}"):
                    worker = threading.Thread(target=generate)
                    worker.start()
                    try:
                        self.assertTrue(entered.wait(3))
                        if explicit: cancel_translation(identifier)
                        else: disconnected.set()
                        worker.join(timeout=2)
                        self.assertFalse(worker.is_alive(), "model header wait retained the translation slot")
                        self.assertEqual(results, ["cancelled"])
                        self.assertTrue(model_stopped.wait(2), "upstream model connection did not close")
                        with translation_job(): commit_translation(lambda: None)
                    finally:
                        released.set(); worker.join(timeout=3)

    def test_request_timing_logs_hide_query_strings_and_target_ids(self):
        with local_server() as httpd:
            httpd.request_timings = True
            with self.assertLogs("reader.timings", level="INFO") as output:
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port)
                connection.request("GET", "/work/unknown/private-target?q=private-query")
                response = connection.getresponse(); response.read(); connection.close()
                deadline = time.monotonic() + 1
                while not output.output and time.monotonic() < deadline: threading.Event().wait(0.01)
            text = "\n".join(output.output)
            self.assertIn("/work/*/*", text)
            self.assertIn("status=404", text)
            self.assertNotIn("private-target", text)
            self.assertNotIn("private-query", text)

    def test_local_acquisition_retries_transient_failures_and_caches_manifest_lookups(self):
        roots = [
            SITE.parent / "키르케고르_원서수집/kierkegaard/kierkegaard/src",
            SITE.parent / "비트겐슈타인_원서수집/wittgenstein_archive_runner_20260526_002009/src",
        ]
        if not all((root / "wittgenstein_archive/manifest.py").is_file() for root in roots):
            self.skipTest("local acquisition packages are absent in a source-light clone")
        from collections import Counter
        from copy import deepcopy
        for root in roots:
            with self.subTest(root=root), tempfile.TemporaryDirectory() as directory:
                namespace = {"Path": Path, "json": json, "Counter": Counter, "deepcopy": deepcopy, "Iterable": list, "ManifestRecord": SimpleNamespace, "ensure_dir": lambda path: path.mkdir(parents=True, exist_ok=True)}
                tree = ast.parse((root / "wittgenstein_archive/manifest.py").read_text(encoding="utf-8"))
                declaration = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ManifestStore")
                exec(compile(ast.Module(body=[declaration], type_ignores=[]), "manifest-fixture", "exec"), namespace)
                manifest_path = Path(directory) / "manifest.jsonl"
                manifest_path.write_text(json.dumps({"local_path": "missing.json", "http_status": 503, "extra": {"flag": True}}) + "\n", encoding="utf-8")
                store = namespace["ManifestStore"](manifest_path)
                with patch.object(store, "read", wraps=store.read) as read:
                    for _ in range(8): self.assertEqual(store.latest_record("missing.json")["http_status"], 503)
                    self.assertEqual(read.call_count, 1)
                    store.latest_record("missing.json")["extra"]["flag"] = False
                    self.assertTrue(store.latest_record("missing.json")["extra"]["flag"])
                    store.append(SimpleNamespace(to_dict=lambda: {"local_path": "other.json", "http_status": 200}))
                    self.assertEqual(store.latest_record("other.json")["http_status"], 200)
                    self.assertEqual(read.call_count, 1)
                tree = ast.parse((root / "kierkegaard_archive/crawler.py").read_text(encoding="utf-8"))
                declaration = next(node for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == "KierkegaardCrawler" for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_fetch_to_path")
                namespace.update(HttpResponse=SimpleNamespace, relpath=lambda path, base: path.relative_to(base).as_posix())
                exec(compile(ast.Module(body=[declaration], type_ignores=[]), "crawler-fixture", "exec"), namespace)
                crawler = SimpleNamespace(resume=True, root=Path(directory), manifest=store, client=SimpleNamespace(get=unittest.mock.Mock(return_value=SimpleNamespace(status=200, body=b"ok"))), _log=lambda _: None, _save_response=unittest.mock.Mock())
                arguments = {"kind": "fixture", "item_siglum": None, "page_siglum": None, "license_name": "fixture", "rights_note": "fixture"}
                namespace["_fetch_to_path"](crawler, "https://example.invalid/fixture", Path(directory) / "missing.json", **arguments)
                self.assertEqual(crawler.client.get.call_count, 1)
                store.append(SimpleNamespace(to_dict=lambda: {"local_path": "missing.json", "http_status": 404}))
                namespace["_fetch_to_path"](crawler, "https://example.invalid/fixture", Path(directory) / "missing.json", **arguments)
                self.assertEqual(crawler.client.get.call_count, 1)
                manifest_path.write_text('{"local_path":"missing.json","http_status":200}\n', encoding="utf-8")
                self.assertEqual(store.latest_record("missing.json")["http_status"], 200)

    def test_missing_registered_sources_preserve_existing_segment_files(self):
        for builder, suffix, source in (
            (build_kierkegaard_segments, ".json", '{"response":{"document":{"text_tesim":["Readable source."]}}}'),
            (build_wittgenstein_segments, ".md", "Readable source."),
        ):
            with self.subTest(builder=builder.__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ("present" + suffix)).write_text(source, encoding="utf-8")
                metadata = root / "metadata.json"
                metadata.write_text(json.dumps({"works": {
                    name: {"work_id": name, "variants": [{"variant_id": "text", "source_path": name + suffix}]}
                    for name in ("present", "missing")
                }}), encoding="utf-8")
                output = root / "segments.jsonl"
                original = b'{"work_id":"present"}\n{"work_id":"missing"}\n'
                output.write_bytes(original)
                with patch.object(builder, "ROOT", root), patch.object(builder, "METADATA", metadata), patch.object(builder, "OUTPUT", output), patch.object(sys, "argv", [builder.__name__]):
                    with self.assertRaises(FileNotFoundError):
                        builder.main()
                self.assertEqual(output.read_bytes(), original)

    def test_rebuild_preflight_rejects_missing_sources_before_metadata_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "kierkegaard_metadata.json"
            original = json.dumps({"works": {"w": {"variants": [{"variant_id": "text", "source_path": "missing.json"}]}}}).encode()
            metadata.write_bytes(original)
            with self.assertRaises(FileNotFoundError):
                preflight_registered_sources(root, root)
            self.assertEqual(metadata.read_bytes(), original)

    def test_rebuild_failure_and_interrupt_restore_previous_generation(self):
        for error in (RuntimeError("check failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)
                original = data / "search_index.sqlite"
                created = data / "kierkegaard_segments.jsonl"
                original.write_bytes(b"previous database")
                stamp = original.stat().st_mtime_ns
                with self.assertRaises(type(error)):
                    with preserve_artifacts(data):
                        original.write_bytes(b"incomplete generation")
                        created.write_bytes(b"new partial artifact")
                        raise error
                self.assertEqual(original.read_bytes(), b"previous database")
                self.assertEqual(original.stat().st_mtime_ns, stamp)
                self.assertFalse(created.exists())
                self.assertFalse(list(data.glob(".rebuild-backup-*")))

    def test_study_session_and_exports_keep_variant_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(translations, "AI_DIR", Path(directory) / "ai"), patch.object(notes, "NOTES_DIR", Path(directory) / "notes"):
            for variant in ("text", "commentary", ""):
                translations.append_record(translations.ai_record_path("kierkegaard"), {
                    "record_type": "ai_sentence_translation", "id": str(uuid.uuid4()), "corpus_id": "kierkegaard", "work_id": "aa",
                    "variant_id": variant, "sentence_id": "sks-0001.s001", "review_state": "reviewed",
                })
                notes.append_jsonl(notes.note_storage_path("kierkegaard"), {
                    "id": str(uuid.uuid4()), "corpus_id": "kierkegaard", "work_id": "aa", "variant_id": variant,
                    "target_id": "sks-0001.s001", "review_state": "reviewed",
                })
            for variant in ("text", "commentary", ""):
                query = {"corpus_id": ["kierkegaard"], "work_id": ["aa"], "variant_id": [variant]}
                result = study_sessions.study_session_payload_from_query(query)
                self.assertEqual([item["variant_id"] for item in result["translations"]], [variant])
                self.assertEqual([item["variant_id"] for item in result["notes"]], [variant])
                self.assertEqual([item["variant_id"] for item in notes.notes_payload_from_query(query)["notes"]], [variant])
            self.assertEqual(len(translations.sentence_translations_for_export({"corpus_id": ["kierkegaard"]})), 3)

    def test_human_approval_survives_model_changes_without_model_or_prompt_calls(self):
        target = synthetic_sentence_target()
        approved = translations.build_record(target, translations.build_sentence_prompt_bundle(target), passing_pipeline_output("model original"))
        approved.update(review_state="reviewed", human_translation="Human confirmed.", pipeline_contract_sha256="older pipeline")
        with tempfile.TemporaryDirectory() as directory, patch.object(translations, "AI_DIR", Path(directory)), patch.object(translations, "sentence_target_bundle", return_value=target):
            translations.append_record(translations.ai_record_path(target["corpus_id"]), approved)
            request = {key: target[key] for key in ("corpus_id", "work_id", "segment_id", "sentence_id", "variant_id")}
            with patch.object(translations, "build_sentence_prompt_bundle", side_effect=AssertionError("human lookup must not build a model prompt")), patch.object(translations, "run_translation_pipeline", side_effect=AssertionError("human lookup must not call a model")):
                result = translations.sentence_translation_from_payload(request)
            self.assertTrue(result["cached"])
            self.assertEqual(result["record"]["human_translation"], "Human confirmed.")
            for field in ("variant_id", "sentence_text_sha256"):
                self.assertIsNone(translations.find_reviewed_record(translations.ai_record_path(target["corpus_id"]), {**target, field: "different"}))
            with patch.object(translations, "run_translation_pipeline", return_value=passing_pipeline_output("explicit new draft")) as model:
                fresh = translations.sentence_translation_from_payload({**request, "regenerate": True})
            self.assertFalse(fresh["cached"])
            self.assertEqual(model.call_count, 1)
            stored = translations.iter_cached_records(translations.ai_record_path(target["corpus_id"]))
            self.assertEqual(len(stored), 2)
            self.assertEqual(stored[0]["human_translation"], "Human confirmed.")

    def test_cancelled_generation_queues_one_replacement_and_can_cancel_the_queue(self):
        for cancel_waiter in (False, True):
            with self.subTest(cancel_waiter=cancel_waiter):
                entered, release = threading.Event(), threading.Event()
                results = {}
                calls = []
                def pipeline(_bundle):
                    calls.append("model")
                    if len(calls) == 1:
                        entered.set()
                        self.assertTrue(release.wait(5))
                    return passing_pipeline_output("temporary output")
                def post(port, route, payload):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
                    try:
                        connection.request("POST", route, json.dumps(payload), {"Content-Type": "application/json"})
                        response = connection.getresponse()
                        return response.status, json.loads(response.read())
                    finally:
                        connection.close()
                with tempfile.TemporaryDirectory() as directory, local_server() as httpd:
                    with patch.object(translations, "AI_DIR", Path(directory)), patch.object(translations, "sentence_target_bundle", return_value=synthetic_sentence_target()), patch.object(translations, "run_translation_pipeline", side_effect=pipeline):
                        first = {"corpus_id": "nietzsche", "work_id": "GM", "segment_id": "p-0001", "sentence_id": "p-0001.s001", "request_id": str(uuid.uuid4())}
                        second = {**first, "request_id": str(uuid.uuid4())}
                        workers = []
                        for label, payload in (("first", first), ("second", second)):
                            worker = threading.Thread(target=lambda label=label, payload=payload: results.update({label: post(httpd.server_port, "/api/sentence-translation", payload)}))
                            workers.append(worker)
                            worker.start()
                            if label == "first":
                                self.assertTrue(entered.wait(5))
                                ack = post(httpd.server_port, "/api/sentence-translation/cancel", {"request_id": first["request_id"]})
                                self.assertEqual(ack[1]["state"], "cancelling")
                                self.assertFalse(ack[1]["execution_released"])
                        try:
                            deadline = time.monotonic() + 3
                            queued = False
                            while time.monotonic() < deadline and "second" not in results:
                                with translation_jobs._guard:
                                    queued = second["request_id"] in translation_jobs._running
                                if queued:
                                    break
                                threading.Event().wait(0.01)
                            self.assertTrue(queued, results)
                            self.assertEqual(len(calls), 1)
                            if cancel_waiter:
                                post(httpd.server_port, "/api/sentence-translation/cancel", {"request_id": second["request_id"]})
                                workers[1].join(timeout=3)
                                self.assertEqual(results["second"][0], 409)
                        finally:
                            release.set()
                            for worker in workers:
                                worker.join(timeout=5)
                        self.assertEqual(results["first"][0], 409)
                        self.assertEqual(results["second"][0], 409 if cancel_waiter else 200)
                        self.assertEqual(len(calls), 1 if cancel_waiter else 2)
                        self.assertEqual(len(translations.iter_cached_records(translations.ai_record_path("nietzsche"))), 0 if cancel_waiter else 1)

    def test_offset_readiness_checks_missing_and_stale_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "segments.jsonl"
            source.write_text(json.dumps({"corpus_id": "nietzsche", "work_id": "GM", "variant_id": "", "segment_id": "p", "text_raw": "Source."}) + "\n", encoding="utf-8")
            index = root / "offsets.sqlite"
            build_segment_offset_index(index, {"nietzsche": source})
            self.assertTrue(probe_segment_offset_index(index, {"nietzsche": source})["ready"])
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                probe_segment_offset_index(index, {"nietzsche": source})
            healthy = [{"corpus_id": "nietzsche", "title": "Nietzsche", "source_root_exists": True, "primary_output_exists": True, "metadata": {"exists": True}, "segments": {"exists": True}, "work_count": 1}]
            with patch.object(runtime_status, "SEGMENT_OFFSET_INDEX", root / "missing.sqlite"), patch.object(runtime_status, "cached_corpus_statuses", return_value=healthy), patch.object(runtime_status, "cached_search_database_summary", return_value={"exists": True, "fts5": True, "records": 1}), patch.object(runtime_status, "cached_gemma_runtime_summary", return_value={"reachable": True, "model_count": 1, "state": "ready"}):
                runtime_status.clear_runtime_health_caches()
                result = runtime_status.build_public_runtime_health()
                self.assertFalse(result["reader_ready"])
                self.assertFalse(result["translation_ready"])
                self.assertEqual(result["status"], "warning")
            runtime_status.clear_runtime_health_caches()

    def test_runtime_cli_fails_on_core_data_warning(self):
        class Response:
            status = 200
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return json.dumps(self.payload).encode()
        def response(url, **_kwargs):
            return Response({"status": "warning", "issues": ["missing segment artifact: nietzsche"]} if url.endswith("/api/health") else {"data": [{"id": "fixture"}]})
        with patch("urllib.request.urlopen", side_effect=response), patch.object(sys, "argv", ["check_local_runtime.py", "--plain"]), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as failure:
                runpy.run_path(str(SITE / "scripts/check_local_runtime.py"), run_name="__main__")
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("Reader: NOT READY", output.getvalue())

    def test_index_variants_keep_reference_anchors_without_translation_controls(self):
        document = render_segments_from_texts(["Index " * 1500], "p", include_sentences=False, preserve_sentence_anchors=True)
        self.assertIn('id="p-0001.s001"', document["html"])
        self.assertNotIn('class="reader-sentence"', document["html"])
        with patch.object(sentence_targets, "resolve_segment_target", return_value={"variant_id": "source_transcription_normalized.index", "text_raw": "Index " * 1500}), patch.object(sentence_targets, "structural_source_context") as context:
            with self.assertRaisesRegex(ValueError, "색인"):
                sentence_targets.resolve_sentence_target("wittgenstein", "Ms-102", "p-0001", "p-0001.s001")
            context.assert_not_called()

    def test_kierkegaard_preserves_existing_extracts_and_reads_html_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sks-example.json"
            html_path = path.with_suffix(".html")
            html_path.write_text('<nav>outside</nav><div class="collection-sks"><h2>Title</h2><p>En <em>god</em> tekst.<span class="symbol">noise</span></p><script>unsafe</script><div class="comment-stuff">popup</div><p>Anden tekst.</p></div><footer>outside</footer>', encoding="utf-8")
            path.write_text(json.dumps({"response": {"document": {"text_tesim": ["Existing source."]}}}), encoding="utf-8")
            self.assertEqual(extract_texts(path), ["Existing source."])
            self.assertEqual(reading_source_path(path), path)
            path.write_text('{"response":{"document":{}}}', encoding="utf-8")
            self.assertEqual(reading_source_path(path), html_path)
            self.assertEqual(extract_texts(path), ["Title", "En god tekst.", "Anden tekst."])
            html_path.unlink()
            self.assertEqual(extract_texts(path), [])

    def test_abbreviations_keep_unaffected_ids_and_legacy_links(self):
        cases = [
            ("Von Dr. Friedrich Nietzsche. Weiter.", ["Von Dr. Friedrich Nietzsche.", "Weiter."], ["p.s001", "p.s003"]),
            ("Er meint d. h. dies. Danach.", ["Er meint d. h. dies.", "Danach."], ["p.s001", "p.s004"]),
            ("Verlag von E. W. Fritzsch. 1887.", ["Verlag von E. W. Fritzsch.", "1887."], ["p.s001", "p.s004"]),
            ("Wert 1.25. Danach:", ["Wert 1.25.", "Danach:"], ["p.s001", "p.s002"]),
            ("Tydeligt ( ɔ: en Forklaring). Næste:", ["Tydeligt ( ɔ: en Forklaring).", "Næste:"], ["p.s001", "p.s003"]),
            ("Tydeligt ɔ: en Forklaring. Næste:", ["Tydeligt ɔ: en Forklaring.", "Næste:"], ["p.s001", "p.s003"]),
            ("Se dette: Et eksempel.", ["Se dette:", "Et eksempel."], ["p.s001", "p.s002"]),
        ]
        for source, texts, identifiers in cases:
            with self.subTest(source=source):
                units = sentence_units("p", source)
                self.assertEqual([unit["text_raw"] for unit in units], texts)
                self.assertEqual([unit["sentence_id"] for unit in units], identifiers)
                self.assertEqual([unit["sentence_index"] for unit in units], list(range(1, len(units) + 1)))
        source = "Von Dr. Friedrich Nietzsche. Weiter."
        html = render_sentence_spans("p", source)
        self.assertIn('id="p.s002" data-sentence-alias="p.s001"', html)
        segment = {"text_raw": source, "source_text_sha256": translations.sha256_text(source), "url": "/work/nietzsche/x#p", "label": "p"}
        with patch.object(sentence_targets, "resolve_segment_target", return_value=segment), patch.object(sentence_targets, "structural_source_context", return_value={"source_context": source, "context_segments": []}):
            target = sentence_targets.resolve_sentence_target("nietzsche", "x", "p", "p.s002")
        self.assertEqual(target["sentence_id"], "p.s001")
        self.assertEqual(target["sentence_text"], "Von Dr. Friedrich Nietzsche.")

    def test_historical_explanation_restores_parenthesis_keeps_following_ids_and_invalidates_old_hash(self):
        before = "Denne Modsigelse er den eneste dialektisk consequente, der baade magter Springet og Immanentsen ( ɔ:"
        restored = before + " det vil sige den senere Immanents)."
        source = restored + " Ved Adam s første Synd kom altsaa Synden ind i Verden."
        units = sentence_units("sks-0034", source)
        self.assertEqual([u["text_raw"] for u in units], [restored, "Ved Adam s første Synd kom altsaa Synden ind i Verden."])
        self.assertEqual([u["sentence_id"] for u in units], ["sks-0034.s001", "sks-0034.s003"])
        self.assertEqual(units[0]["legacy_sentence_ids"], ["sks-0034.s002"])
        html = render_sentence_spans("sks-0034", source)
        self.assertIn('id="sks-0034.s002" data-sentence-alias="sks-0034.s001"', html)
        segment = {"text_raw": source, "source_text_sha256": translations.sha256_text(source), "url": "/work/kierkegaard/ba#sks-0034", "label": "p"}
        with patch.object(sentence_targets, "resolve_segment_target", return_value=segment), patch.object(sentence_targets, "structural_source_context", return_value={"source_context": source, "context_segments": []}):
            target = sentence_targets.resolve_sentence_target("kierkegaard", "ba", "sks-0034", "sks-0034.s002", "text")
        self.assertEqual(target["sentence_id"], "sks-0034.s001")
        self.assertEqual(target["sentence_text"], restored)
        self.assertEqual(target["sentence_text_sha256"], translations.sha256_text(restored))
        self.assertNotEqual(target["sentence_text_sha256"], translations.sha256_text(before))

    def test_reviewed_equivalents_and_corrected_reading_preserve_meaning_checks(self):
        from services.translation_profiles import translation_policy_bundle, render_translation_policy
        scopes = [
            ("nietzsche", "GM", "", "p-0004.s001", "Wir sind uns unbekannt, wir Erkennenden, wir selbst uns selbst:", "인식하는 자들인 우리는 우리 자신을 알지 못한다. 바로 우리 자신이 우리 자신을 모르는 것이다:"),
            ("wittgenstein", "Group_ItemsInEnglish", "idp_transcription_linear", "p-0001.s002", "If only these || those signs which contain proper names were complex then propositions containing nothing but apparent variables would be simple.", "고유명을 포함하는 기호들만이 복합적이라면, 속박변수만을 포함하는 명제들은 단순할 것이다."),
        ]
        for corpus, work, variant, sentence, source, good in scopes:
            policy = translation_policy_bundle(corpus, work, variant, sentence, sentence_text_sha256=translations.sha256_text(source))
            bundle = {"source_context": "<TARGET_SENTENCE>" + source + "</TARGET_SENTENCE>", "approved_terminology": policy["terminology"], "approved_sentence_rules": policy["sentence_rules"]}
            audit = translations.merge_approved_policy_audit(bundle, good, {"verdict": "pass", "issues": []})
            self.assertEqual(audit, {"verdict": "pass", "issues": []})
            if corpus == "nietzsche":
                bad = "인식하는 자들인 우리는 존재한다. 바로 우리 자신이 그러한 것이다:"
                self.assertTrue(translations.approved_sentence_rule_issues(bundle, bad))
                self.assertIn("알지 못한다", render_translation_policy(policy))
                wrong_subject = "우리 스스로가 우리 자신에게 미지다."
                self.assertTrue(translations.approved_sentence_rule_issues(bundle, wrong_subject))
            else:
                broken_scope = good.replace("기호들만이 복합적이라면", "기호들이 복합적이기만 하다면")
                self.assertTrue(translations.approved_sentence_rule_issues(bundle, broken_scope))
                broken_marker = good.replace("기호들만이", "|| 저 기호들만이")
                self.assertTrue(translations.approved_sentence_rule_issues(bundle, broken_marker))
                self.assertIn("Only when the translation contains ‘||’", render_translation_policy(policy))

    def test_r23_reviewed_meaning_rejects_repeated_model_pass_without_changing_other_scopes(self):
        from services.translation_profiles import translation_policy_bundle, render_translation_policy
        from check_translation_quality_regressions import load_cases, prepare_bad_case
        case = next(case for case in load_cases() if case["case_id"] == "kierkegaard-ba-r23-magter-causal-substitution")
        bundle, _ = prepare_bad_case(case)
        false_pass = {"verdict": "pass", "issues": []}
        audit = translations.merge_approved_policy_audit(bundle, case["known_bad_translation"], false_pass)
        self.assertEqual(audit["verdict"], "revise")
        self.assertTrue(any(issue["category"] == "semantic_substitution" and issue["severity"] == "major" for issue in audit["issues"]))
        self.assertEqual(false_pass, {"verdict": "pass", "issues": []})
        good = "이 모순만이 변증법적으로 일관되며, 도약과 내재성(즉, 이후의 내재성)을 모두 다룰 수 있다."
        for translation in [good, good.replace("다룰 수 있다", "감당할 수 있다")]:
            self.assertEqual(translations.merge_approved_policy_audit(bundle, translation, false_pass), false_pass)
        rendered = render_translation_policy({"sentence_rules": bundle["approved_sentence_rules"]})
        self.assertIn("서술보어", rendered)
        self.assertIn("이후의 내재성", rendered)
        # The same sentence ID with its old truncated hash must not inherit this review.
        stale = translation_policy_bundle("kierkegaard", "ba", "text", "sks-0034.s001", sentence_text_sha256="7acbdaae101a2278c57adaca0e1388339ee3b5f9eea3862d845da724d6b279ef")
        self.assertEqual(stale["sentence_rules"], [])
        unrelated = translation_policy_bundle("kierkegaard", "fb", "text", "sks-0034.s001", sentence_text_sha256=bundle["target"]["sentence_text_sha256"])
        self.assertEqual(unrelated["sentence_rules"], [])
        k02 = translation_policy_bundle("kierkegaard", "ba", "text", "sks-0047.s007", sentence_text_sha256="360807eddde1ee6d6d8728a4db0868fd369a4b34f213fd28080abc07f145e36a")
        self.assertEqual(len(k02["sentence_rules"]), 1)
        self.assertEqual(k02["sentence_rules"][0]["source_case_id"], "expansion-20260909-k02")

    def test_approved_alternatives_and_conditional_marker_require_valid_metadata(self):
        from services.translation_profiles import read_translation_profiles
        profile = {
            "profile_id": "synthetic", "corpus_id": "nietzsche", "work_id": "demo", "approval_state": "approved",
            "terminology": [{"source": "word", "target": "용어", "alternatives": ["다른 용어"]}],
            "sentence_rules": [{"sentence_id": "p.s001", "forbidden_translation_fragments": [{"text": "오역", "category": "terminology", "severity": "major", "explanation": "검사"}],
                                "required_translation_fragments": [{"source_span": "word", "alternatives": ["용어"], "when_translation_contains": "||", "category": "omission", "severity": "major", "explanation": "검사"}]}],
        }
        with tempfile.TemporaryDirectory(prefix="philo_policy_alternatives_") as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            path.write_text(json.dumps({"schema_version": 1, "profiles": [profile]}), encoding="utf-8")
            self.assertEqual(read_translation_profiles(path)[0], profile)
            for field, bad in [("alternatives", []), ("alternatives", [""]), ("alternatives", ["같음", " 같음 "]), ("alternatives", True), ("when_translation_contains", ""), ("when_translation_contains", False)]:
                changed = json.loads(json.dumps(profile))
                if field == "alternatives":
                    changed["terminology"][0][field] = bad
                else:
                    changed["sentence_rules"][0]["required_translation_fragments"][0][field] = bad
                path.write_text(json.dumps({"schema_version": 1, "profiles": [changed]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_translation_profiles(path)

    def test_source_entry_labels_are_not_translatable_prose(self):
        texts = ["P259:259:1", "P259:259:2", "P259:259:3"]
        self.assertFalse(has_readable_text(texts))
        self.assertTrue(has_readable_text([*texts, "Et læsbart afsnit."]))
        document = render_segments_from_texts(texts, "sks", include_sentences=False)
        self.assertNotIn("reader-sentence", document["html"])
        self.assertIn('id="sks-0003"', document["html"])
        with patch.object(sentence_targets, "resolve_segment_target", return_value={"segment_type": "section", "text_raw": texts[0]}):
            with self.assertRaisesRegex(ValueError, "no sentence text"):
                sentence_targets.resolve_sentence_target("kierkegaard", "p259", "sks-0001", "sks-0001.s001")

    def test_invalid_request_identifier_is_rejected_before_cache_lookup(self):
        payload = {"corpus_id": "nietzsche", "work_id": "GM", "segment_id": "p-0001", "sentence_id": "p-0001.s001", "request_id": "invalid"}
        with patch.object(translations, "find_cached_record") as cached:
            with self.assertRaisesRegex(ValueError, "invalid translation request_id"):
                translations.sentence_translation_from_payload(payload)
            cached.assert_not_called()

    def test_markdown_index_anchors_exist_in_rendered_document(self):
        source = "## [Die sieben Siegel. (Oder: das Ja- und Amen-Lied.)](javascript:;)\n\nText.\n\n> Quotation.\n\n## 2\n\nNext."
        records = markdown_segments(source)
        html = render_reading_document(source)["html"]
        for record in records:
            self.assertIn(f'id="{record["segment_id"]}"', html)
        self.assertNotIn("javascript:;", html)

    def test_corrupt_translation_records_block_all_mutations(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(translations, "AI_DIR", Path(directory)):
            path = translations.ai_record_path("nietzsche")
            for invalid in ['{"recoverable":', '["not an object"]']:
                original = ('{"id":"saved"}\n' + invalid + "\n").encode()
                for action in (
                    lambda: translations.append_record(path, {"id": "new"}),
                    lambda: translations.update_sentence_translation_review({"corpus_id": "nietzsche", "review_state": "reviewed"}, "saved"),
                    lambda: translations.delete_sentence_translation("nietzsche", "saved"),
                ):
                    path.write_bytes(original)
                    with self.assertRaises(ValueError):
                        action()
                    self.assertEqual(path.read_bytes(), original)

    def test_system_prompts_and_options_change_request_identity(self):
        target = synthetic_sentence_target()
        original = translations.build_sentence_prompt_bundle(target)
        for name in ("TRANSLATOR_SYSTEM_PROMPT", "CRITIC_SYSTEM_PROMPT", "REVISION_SYSTEM_PROMPT"):
            with self.subTest(name=name), patch.object(translations, name, getattr(translations, name) + " Changed instruction."):
                changed = translations.build_sentence_prompt_bundle(target)
                self.assertNotEqual(original["pipeline_contract_sha256"], changed["pipeline_contract_sha256"])
                if name == "TRANSLATOR_SYSTEM_PROMPT":
                    self.assertNotEqual(original["request_contract_sha256"], changed["request_contract_sha256"])
        with patch.object(translations, "CHAT_TEMPLATE_KWARGS", {"enable_thinking": True}):
            changed = translations.build_sentence_prompt_bundle(target)
            self.assertNotEqual(original["request_contract_sha256"], changed["request_contract_sha256"])
        self.assertEqual(translations.infer_source_language("wittgenstein", "10.7.10"), "de/en")
        self.assertEqual(translations.infer_source_language("wittgenstein", "10.7.10", "en"), "en")

    def test_failed_database_build_preserves_previous_database(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "search.jsonl"
            output = Path(directory) / "search.sqlite"
            connection = sqlite3.connect(output)
            connection.execute("CREATE TABLE preserved(value TEXT)")
            connection.execute("INSERT INTO preserved VALUES ('original')")
            connection.commit()
            connection.close()
            before = output.read_bytes()
            source.write_text('{"broken":', encoding="utf-8")
            with patch.object(build_search_db, "JSONL", source), patch.object(build_search_db, "OUTPUT", output):
                with self.assertRaises(json.JSONDecodeError):
                    build_search_db.build_database()
            self.assertEqual(before, output.read_bytes())
            self.assertFalse(list(Path(directory).glob(".*.tmp")))

    def test_search_snippet_includes_late_match(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "search.jsonl"
            output = Path(directory) / "search.sqlite"
            text = "Vorspann " * 450 + "Ressentiment und seine Folgen."
            source.write_text(json.dumps({"corpus_id": "nietzsche", "work_id": "GM", "segment_id": "p", "text": text, "text_preview": text[:220]}) + "\n", encoding="utf-8")
            with patch.object(build_search_db, "JSONL", source), patch.object(build_search_db, "OUTPUT", output):
                self.assertEqual(build_search_db.build_database(), 1)
            connection = sqlite3.connect(output)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute("SELECT * FROM search_segments LIMIT 1").fetchone()
                result = search_result_from_row(row, ["ressentiment"], 1)
                self.assertIn("Ressentiment", result["snippet"])
            finally:
                connection.close()

    def test_http_origin_host_content_type_and_json_object_boundary(self):
        with local_server() as httpd, patch.object(server, "create_note_from_payload", return_value={"id": "temporary"}) as create:
            origin = f"http://127.0.0.1:{httpd.server_port}"
            cases = [
                ({"Content-Type": "text/plain", "Origin": "http://untrusted.invalid", "Sec-Fetch-Site": "cross-site"}, "{}", 403),
                ({"Content-Type": "application/json", "Origin": "null"}, "{}", 403),
                ({"Content-Type": "application/json", "Host": "untrusted.invalid"}, "{}", 403),
                ({"Content-Type": "text/plain", "Origin": origin}, "{}", 403),
                ({"Content-Type": "application/json", "Origin": origin}, "[]", 400),
                ({"Content-Type": "application/json", "Origin": origin, "Sec-Fetch-Site": "same-origin"}, "{}", 201),
                ({"Content-Type": "application/json"}, "{}", 201),
            ]
            for headers, body, expected in cases:
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                try:
                    connection.request("POST", "/api/notes", body=body, headers=headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                finally:
                    connection.close()
            self.assertEqual(create.call_count, 2)
            with patch.object(server, "sentence_translations_summary_from_query", return_value={"ok": True}) as summary:
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                try:
                    connection.request("GET", "/api/sentence-translations/summary?corpus_id=nietzsche&variant_id=")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    self.assertEqual(summary.call_args.args[0]["variant_id"], [""])
                finally:
                    connection.close()

    def test_duplicate_passages_have_stable_order_despite_title_lengths(self):
        body = "Sprachspiel mit Farben."
        rows = []
        for work, title in (("z-view", "Short"), ("a-view", "A longer descriptive title")):
            rows.append({"corpus_id": "wittgenstein", "work_id": work, "variant_id": "text", "segment_id": "p", "segment_type": "paragraph", "label": "Paragraph", "title": title, "url": "/work/" + work, "snippet": body, "search_text": (title + " Paragraph " + body).lower()})
        self.assertEqual([row["work_id"] for row in rank_sqlite_rows(rows, ["sprachspiel"])], ["a-view", "z-view"])
        rows[0]["search_text"] += " Different omitted ending."
        self.assertEqual([row["work_id"] for row in rank_sqlite_rows(rows, ["sprachspiel"])], ["z-view", "a-view"])

    def test_cancellation_before_start_during_work_and_after_commit(self):
        early = str(uuid.uuid4())
        cancel_translation(early)
        with self.assertRaises(TranslationCancelled), translation_job(early):
            self.fail("early cancellation was ignored")
        active = str(uuid.uuid4())
        writes = []
        with translation_job(active):
            self.assertTrue(cancel_translation(active)["cancelled"])
            with self.assertRaises(TranslationCancelled):
                commit_translation(lambda: writes.append("wrong"))
        self.assertEqual(writes, [])
        completed = str(uuid.uuid4())
        with translation_job(completed):
            commit_translation(lambda: writes.append("saved"))
            self.assertFalse(cancel_translation(completed)["cancelled"])
        with translation_job():
            with self.assertRaises(TranslationBusy), translation_job():
                self.fail("overlapping model execution was accepted")
        self.assertEqual(writes, ["saved"])

    def test_disconnected_http_translation_is_not_saved(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        class FinishedHandler(server.Handler):
            def finish(self):
                try:
                    super().finish()
                finally:
                    finished.set()
        def pipeline(_bundle):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test pipeline timed out")
            return passing_pipeline_output("temporary translation")
        with tempfile.TemporaryDirectory() as directory, local_server(FinishedHandler) as httpd:
            with patch.object(translations, "AI_DIR", Path(directory)), patch.object(translations, "sentence_target_bundle", return_value=synthetic_sentence_target()), patch.object(translations, "run_translation_pipeline", side_effect=pipeline):
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                try:
                    connection.request("POST", "/api/sentence-translation", body=json.dumps({"corpus_id": "nietzsche", "work_id": "GM", "segment_id": "p-0001", "sentence_id": "p-0001.s001", "request_id": str(uuid.uuid4())}), headers={"Content-Type": "application/json"})
                    self.assertTrue(entered.wait(5))
                    connection.close()
                    release.set()
                    self.assertTrue(finished.wait(5))
                    self.assertFalse(list(Path(directory).glob("*.jsonl")))
                finally:
                    connection.close()
                    release.set()

    def test_summary_does_not_mark_legacy_fragments_or_other_variants_as_studied(self):
        target = synthetic_sentence_target()
        record = translations.build_record(target, translations.build_sentence_prompt_bundle(target), passing_pipeline_output("translation"))
        with tempfile.TemporaryDirectory() as directory, patch.object(translations, "AI_DIR", Path(directory)):
            translations.append_record(translations.ai_record_path("nietzsche"), record)
            query = {"corpus_id": ["nietzsche"], "work_id": [target["work_id"]], "variant_id": [""], "current_sentences": ["1"]}
            with patch.object(translations, "resolve_segment_target", return_value={"text_raw": target["sentence_text"] + " Changed."}):
                current = translations.sentence_translations_summary_from_query(query)
                self.assertEqual(current["count"], 1)
                self.assertEqual(current["sentence_state_count"], 1)
            with patch.object(translations, "resolve_segment_target", return_value={"text_raw": "Different source."}):
                self.assertEqual(translations.sentence_translations_summary_from_query(query)["sentence_state_count"], 0)
            query["variant_id"] = ["another"]
            self.assertEqual(translations.sentence_translations_summary_from_query(query)["count"], 0)

    def test_local_crawler_retries_incomplete_works(self):
        paths = [NIETZSCHE_SOURCE_ROOT / "crawler.py", NIETZSCHE_SOURCE_ROOT / "nietzsche" / "nietzsche" / "crawler.py"]
        if not all(path.is_file() for path in paths):
            self.skipTest("local acquisition scripts are absent in a source-light clone")
        for path in paths:
            with self.subTest(path=path.name), tempfile.TemporaryDirectory() as directory:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"crawl_work", "atomic_crawl_write", "completed_work"}]
                fail = [True]
                calls = []
                def fetch(url):
                    calls.append(url)
                    if url.endswith("/2") and fail[0]:
                        return None
                    return type("Response", (), {"content": url.encode()})()
                namespace = {
                    "Path": Path, "os": os, "json": json, "hashlib": hashlib, "tempfile": tempfile,
                    "OUTPUT_DIR": Path(directory), "TEXT_URL": "http://fixture.invalid/text",
                    "logger": logging.getLogger("review-fixture"), "re": re, "fetch": fetch,
                    "BeautifulSoup": lambda value, *_args, **_kwargs: value.decode(),
                    "get_page_title": lambda *_args: "Title",
                    "extract_section_links": lambda *_args: ["http://fixture.invalid/1", "http://fixture.invalid/2"],
                    "extract_main_content": lambda value: value,
                    "md": lambda value, **_kwargs: value,
                    "tqdm": lambda values, **_kwargs: values, "polite_sleep": lambda _delay: None,
                }
                exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
                namespace["crawl_work"]("GM", 0, True)
                output = Path(directory) / "works" / "GM.md"
                self.assertFalse(output.exists())
                self.assertTrue(output.with_suffix(".incomplete.json").exists())
                fail[0] = False
                namespace["crawl_work"]("GM", 0, True)
                self.assertIn("http://fixture.invalid/2", output.read_text(encoding="utf-8"))
                count = len(calls)
                namespace["crawl_work"]("GM", 0, True)
                self.assertEqual(len(calls), count)
                output.write_text("interrupted output", encoding="utf-8")
                namespace["crawl_work"]("GM", 0, True)
                self.assertGreater(len(calls), count)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewRegressions))
    if not result.wasSuccessful():
        raise SystemExit(1)
    node = shutil.which("node")
    if node:
        subprocess.run([node, str(SITE / "scripts" / "check_reader_async_contracts.js")], check=True)
    else:
        print("reader async JS regressions skipped: Node.js is unavailable")
