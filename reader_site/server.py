from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from corpora.archive import build_archive
from corpora.catalogs import (
    bible_segments_payload_from_query,
    load_bible_metadata,
    load_kierkegaard_metadata,
    load_nietzsche_concepts,
    load_nietzsche_metadata,
    load_wittgenstein_metadata,
)
from runtime_status import build_artifact_manifest, build_runtime_health
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
from services.source_targets import source_target_payload_from_query
from services.sources import (
    build_read_response,
    build_source_response,
)
from services.static_files import build_file_payload, resolve_static_file
from services.work_pages import build_work_page_html


SITE = Path(__file__).resolve().parent


def first_value(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if value:
        return str(value)
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonalArchiveReader/1.0"

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(build_runtime_health())
            return
        if parsed.path == "/api/artifacts":
            self.send_json(build_artifact_manifest())
            return
        if parsed.path == "/api/archive":
            self.send_json(build_archive())
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
        if parsed.path == "/api/study":
            self.handle_study_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/study/export":
            self.handle_study_export_get(parse_qs(parsed.query))
            return
        if parsed.path == "/api/notes/export":
            self.handle_notes_export_get(parse_qs(parsed.query))
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
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/notes":
            self.handle_notes_post()
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        note_match = re.fullmatch(r"/api/notes/([^/]+)/?", parsed.path)
        if note_match:
            self.handle_notes_put(unquote(note_match.group(1)))
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        note_match = re.fullmatch(r"/api/notes/([^/]+)/?", parsed.path)
        if note_match:
            self.handle_notes_delete(unquote(note_match.group(1)), parse_qs(parsed.query))
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

    def handle_bible_segments_get(self, query: dict[str, list[str]]) -> None:
        try:
            payload = bible_segments_payload_from_query(query)
        except (ValueError, FileNotFoundError) as exc:
            self.send_error(404, str(exc))
            return
        self.send_json(payload)

    def handle_search_get(self, query: dict[str, list[str]]) -> None:
        self.send_json(search_payload_from_query(query))

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

    def handle_work(self, corpus_id: str, work_id: str, query: dict[str, list[str]] | None = None) -> None:
        self.send_work_viewer(corpus_id, work_id, first_value((query or {}).get("variant", [""])))

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

    def serve_static(self, request_path: str) -> None:
        try:
            target = resolve_static_file(request_path)
        except PermissionError:
            self.send_error(403)
            return
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_file(target)

    def send_file(self, target: Path, inline: bool = False) -> None:
        payload = build_file_payload(target, inline)
        self.send_response(200)
        self.send_header("Content-Type", payload.content_type)
        self.send_header("Content-Length", str(len(payload.body)))
        if payload.content_disposition:
            self.send_header("Content-Disposition", payload.content_disposition)
        self.end_headers()
        self.wfile.write(payload.body)

    def send_work_viewer(self, corpus_id: str, work_id: str, variant_id: str = "") -> None:
        try:
            body = build_work_page_html(corpus_id, work_id, variant_id).encode("utf-8")
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
        self.end_headers()
        self.wfile.write(body)

    def send_source_response(self, response: dict) -> None:
        if response.get("kind") == "file":
            self.send_file(response["target"], bool(response.get("inline")))
            return
        body = str(response.get("body", "")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8793)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Personal Archive of Literature reader running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
