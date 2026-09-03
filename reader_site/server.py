from __future__ import annotations

import argparse
import ipaddress
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from corpora.archive import archive_title_search_from_query, build_archive, build_archive_summary
from corpora.catalogs import (
    bible_segments_payload_from_query,
    load_bible_metadata,
    load_kierkegaard_metadata,
    load_nietzsche_concepts,
    load_nietzsche_metadata,
    load_wittgenstein_metadata,
)
from runtime_status import build_public_artifact_manifest, build_public_gemma_health, build_public_runtime_health
from services.notes import (
    create_note_from_payload,
    delete_note_from_query,
    notes_export_from_query,
    notes_payload_from_query,
    study_export_from_query,
    study_payload_from_query,
    update_note_from_payload,
)
from services.search import search_payload_from_query
from services.sentence_translations import TranslationModelResponseError, sentence_translation_from_payload
from services.sentence_translations import (
    delete_sentence_translation_from_query,
    sentence_translations_export_from_query,
    sentence_translations_summary_from_query,
    update_sentence_translation_review,
)
from services.source_targets import source_target_payload_from_query
from services.sources import (
    build_read_response,
    build_source_response,
)
from services.static_files import build_file_payload, resolve_static_file, static_cache_control
from services.study_sessions import study_session_export_from_query
from services.work_chunks import work_chunk_payload_from_query
from services.work_pages import build_work_page_html


SITE = Path(__file__).resolve().parent


def validate_reader_host(host: str) -> str:
    candidate = str(host or "").strip()
    normalized = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    if normalized.lower() == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(normalized)
        is_loopback = address.version == 4 and address.is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ValueError("reader host must be IPv4 loopback-only (127.0.0.1 or localhost)")
    return normalized


class LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        host, *address_tail = self.server_address
        normalized_host = validate_reader_host(str(host))
        self.server_address = (normalized_host, *address_tail)
        super().server_bind()


def first_value(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonalArchiveReader/1.0"

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health/gemma":
            self.send_json(build_public_gemma_health())
            return
        if parsed.path == "/api/health":
            self.send_json(build_public_runtime_health())
            return
        if parsed.path == "/api/artifacts":
            self.send_json(build_public_artifact_manifest())
            return
        if parsed.path == "/api/archive":
            self.send_json(build_archive())
            return
        if parsed.path == "/api/archive/summary":
            self.send_json(build_archive_summary())
            return
        if parsed.path == "/api/archive/titles":
            self.handle_archive_title_search_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/nietzsche/metadata":
            self.send_json(load_nietzsche_metadata())
            return
        if parsed.path == "/api/nietzsche/concepts":
            self.send_json(load_nietzsche_concepts())
            return
        if parsed.path == "/api/bible/metadata":
            self.send_json(load_bible_metadata())
            return
        if parsed.path == "/api/bible/segments":
            self.handle_bible_segments_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/kierkegaard/metadata":
            self.send_json(load_kierkegaard_metadata())
            return
        if parsed.path == "/api/wittgenstein/metadata":
            self.send_json(load_wittgenstein_metadata())
            return
        if parsed.path == "/api/search":
            self.handle_search_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/source-target":
            self.handle_source_target_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/work-chunks":
            self.handle_work_chunk_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/study":
            self.handle_study_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/study/export":
            self.handle_study_export_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/study-session/export":
            self.handle_study_session_export_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/notes/export":
            self.handle_notes_export_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/sentence-translations/export":
            self.handle_sentence_translations_export_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/sentence-translations/summary":
            self.handle_sentence_translations_summary_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/notes":
            self.handle_notes_get(parse_qs(parsed.query))
            return
        work_match = re.fullmatch(r"/work/([^/]+)/([^/]+)/?", parsed.path)
        if work_match:
            self.handle_work(unquote(work_match.group(1)), unquote(work_match.group(2)), parse_qs(parsed.query))
            return
        if parsed.path == "/read":
            self.handle_read(parse_qs(parsed.query))
            return
        if parsed.path == "/source":
            self.handle_source(parse_qs(parsed.query))
            return
        self.serve_static(parsed.path, parsed.query)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/notes":
            self.handle_notes_post()
            return
        if parsed.path == "/api/sentence-translation":
            self.handle_sentence_translation_post()
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        note_match = re.fullmatch(r"/api/notes/([^/]+)/?", parsed.path)
        if note_match:
            self.handle_notes_put(unquote(note_match.group(1)))
            return
        translation_match = re.fullmatch(r"/api/sentence-translations/([^/]+)/?", parsed.path)
        if translation_match:
            self.handle_sentence_translation_review_put(unquote(translation_match.group(1)))
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        note_match = re.fullmatch(r"/api/notes/([^/]+)/?", parsed.path)
        if note_match:
            self.handle_notes_delete(unquote(note_match.group(1)), parse_qs(parsed.query))
            return
        translation_match = re.fullmatch(r"/api/sentence-translations/([^/]+)/?", parsed.path)
        if translation_match:
            self.handle_sentence_translation_delete(
                unquote(translation_match.group(1)),
                parse_qs(parsed.query),
            )
            return
        self.send_error(404)

    def read_json_payload(self, max_length: int = 65536) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > max_length:
            raise ValueError("invalid json payload")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc

    def handle_notes_get(self, query: dict[str, list[str]]) -> None:
        self.send_json(notes_payload_from_query(query))

    def handle_notes_export_get(self, query: dict[str, list[str]]) -> None:
        result = notes_export_from_query(query)
        if result["kind"] == "text":
            self.send_text(result["body"], result["content_type"])
            return
        self.send_json(result["payload"])

    def handle_study_get(self, query: dict[str, list[str]]) -> None:
        self.send_json(study_payload_from_query(query))

    def handle_study_export_get(self, query: dict[str, list[str]]) -> None:
        result = study_export_from_query(query)
        if result["kind"] == "text":
            self.send_text(result["body"], result["content_type"])
            return
        self.send_json(result["payload"])

    def handle_study_session_export_get(self, query: dict[str, list[str]]) -> None:
        try:
            result = study_session_export_from_query(query)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        if result["kind"] == "text":
            self.send_text(result["body"], result["content_type"])
            return
        self.send_json(result["payload"])

    def handle_sentence_translations_export_get(self, query: dict[str, list[str]]) -> None:
        try:
            result = sentence_translations_export_from_query(query)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        if result["kind"] == "text":
            self.send_text(result["body"], result["content_type"])
            return
        self.send_json(result["payload"])

    def handle_sentence_translations_summary_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = sentence_translations_summary_from_query(query)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        self.send_json(payload)

    def handle_notes_post(self) -> None:
        try:
            payload = self.read_json_payload()
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        try:
            record = create_note_from_payload(payload)
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            self.send_error(400, str(exc))
            return
        self.send_json({"ok": True, "note": record}, status=201)

    def handle_notes_put(self, note_id: str) -> None:
        try:
            payload = self.read_json_payload()
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        try:
            note = update_note_from_payload(note_id, payload)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_json({"ok": True, "note": note})

    def handle_notes_delete(self, note_id: str, query: dict[str, list[str]]) -> None:
        try:
            deleted = delete_note_from_query(note_id, query)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_json({"ok": True, "deleted": deleted})

    def handle_sentence_translation_delete(
        self,
        record_id: str,
        query: dict[str, list[str]],
    ) -> None:
        try:
            deleted = delete_sentence_translation_from_query(record_id, query)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=404)
            return
        self.send_json({"ok": True, "deleted": deleted})

    def handle_bible_segments_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = bible_segments_payload_from_query(query)
        except (ValueError, FileNotFoundError) as exc:
            self.send_error(404, str(exc))
            return
        self.send_json(payload)

    def handle_search_get(self, query: dict[str, list[str]]) -> None:
        self.send_json(search_payload_from_query(query))

    def handle_archive_title_search_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = archive_title_search_from_query(query)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self.send_json(payload)

    def handle_source_target_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = source_target_payload_from_query(query)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_json(payload)

    def handle_sentence_translation_post(self) -> None:
        try:
            payload = self.read_json_payload(max_length=32768)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        try:
            result = sentence_translation_from_payload(payload)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=404)
            return
        except ConnectionError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=503)
            return
        except TranslationModelResponseError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=502)
            return
        self.send_json(result)

    def handle_sentence_translation_review_put(self, record_id: str) -> None:
        try:
            payload = self.read_json_payload(max_length=8192)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        try:
            result = update_sentence_translation_review(payload, record_id)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=404)
            return
        self.send_json(result)

    def handle_work(self, corpus_id: str, work_id: str, query: dict[str, list[str]] | None = None) -> None:
        query = query or {}
        self.send_work_viewer(
            corpus_id,
            work_id,
            first_value(query.get("variant", [""])),
            view=first_value(query.get("view", [""])),
            initial_anchor=first_value(query.get("anchor", [""])),
        )

    def handle_work_chunk_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = work_chunk_payload_from_query(query)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except PermissionError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=403)
            return
        except FileNotFoundError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=404)
            return
        self.send_json(payload)

    def handle_read(self, query: dict[str, list[str]]) -> None:
        try:
            response = build_read_response(query.get("path", [""])[0])
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_source_response(response)

    def handle_source(self, query: dict[str, list[str]]) -> None:
        try:
            response = build_source_response(query.get("path", [""])[0])
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_source_response(response)

    def serve_static(self, request_path: str, query_string: str = "") -> None:
        try:
            target = resolve_static_file(request_path)
        except PermissionError:
            self.send_error(403)
            return
        except FileNotFoundError:
            self.send_error(404)
            return
        version_values = parse_qs(query_string, keep_blank_values=True).get("v", [])
        versioned = any(str(value).strip() for value in version_values)
        self.send_file(target, static_asset=True, versioned=versioned)

    def send_file(
        self,
        target: Path,
        inline: bool = False,
        *,
        static_asset: bool = False,
        versioned: bool = False,
    ) -> None:
        payload = build_file_payload(
            target,
            inline,
            accept_encoding=self.headers.get("Accept-Encoding", ""),
            if_none_match=self.headers.get("If-None-Match", ""),
            if_modified_since=self.headers.get("If-Modified-Since", ""),
            cache_control=static_cache_control(target, versioned) if static_asset else "no-cache",
            allow_compression=static_asset,
            head_only=self.command == "HEAD",
        )
        self.send_response(payload.status)
        self.send_header("Content-Type", payload.content_type)
        self.send_header("Cache-Control", payload.cache_control)
        self.send_header("ETag", payload.etag)
        self.send_header("Last-Modified", payload.last_modified)
        if payload.content_length is not None:
            self.send_header("Content-Length", str(payload.content_length))
        if payload.content_encoding:
            self.send_header("Content-Encoding", payload.content_encoding)
        if payload.vary_accept_encoding:
            self.send_header("Vary", "Accept-Encoding")
        if payload.content_disposition:
            self.send_header("Content-Disposition", payload.content_disposition)
        self.end_headers()
        if self.command != "HEAD" and payload.status != 304:
            self.wfile.write(payload.body)

    def send_work_viewer(
        self,
        corpus_id: str,
        work_id: str,
        variant_id: str = "",
        *,
        view: str = "",
        initial_anchor: str = "",
    ) -> None:
        try:
            body = build_work_page_html(
                corpus_id,
                work_id,
                variant_id,
                view=view,
                initial_anchor=initial_anchor,
            ).encode("utf-8")
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        except PermissionError as exc:
            self.send_error(403, str(exc))
            return
        except FileNotFoundError as exc:
            self.send_error(404, str(exc))
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_source_response(self, response: dict) -> None:
        if response.get("kind") == "file":
            self.send_file(response["target"], bool(response.get("inline")))
            return
        body = str(response.get("body", "")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8793)
    args = parser.parse_args()
    try:
        args.host = validate_reader_host(args.host)
    except ValueError as exc:
        parser.error(str(exc))
    server = LoopbackThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Personal Archive of Literature reader running at http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
