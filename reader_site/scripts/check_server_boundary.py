from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
SERVER = SITE / "server.py"
LAUNCHER = SITE / "run_reader_with_gemma.ps1"
sys.path.insert(0, str(SITE))

import runtime_status  # noqa: E402
from server import Handler, LoopbackThreadingHTTPServer, validate_reader_host  # noqa: E402
from services.static_files import resolve_static_file  # noqa: E402

BANNED_IMPORT_PREFIXES = {
    "corpora.work_models",
    "rendering.",
}

BANNED_IMPORTED_NAMES = {
    "append_note",
    "delete_note",
    "export_notes_jsonl",
    "export_notes_markdown",
    "export_study_markdown",
    "read_all_notes",
    "read_notes",
    "render_reading_viewer_html",
    "render_source_viewer_html",
    "render_work_page_html",
    "resolve_source_path",
    "search_records",
    "study_note_groups",
    "update_note",
}

REQUIRED_IMPORTED_NAMES = {
    "bible_segments_payload_from_query",
    "build_archive_summary",
    "build_file_payload",
    "build_public_artifact_manifest",
    "build_public_gemma_health",
    "build_public_runtime_health",
    "build_read_response",
    "build_source_response",
    "build_work_page_html",
    "create_note_from_payload",
    "delete_note_from_query",
    "delete_sentence_translation_from_query",
    "notes_export_from_query",
    "notes_payload_from_query",
    "resolve_static_file",
    "search_payload_from_query",
    "sentence_translation_from_payload",
    "sentence_translations_export_from_query",
    "sentence_translations_summary_from_query",
    "static_cache_control",
    "study_export_from_query",
    "study_payload_from_query",
    "study_session_export_from_query",
    "update_sentence_translation_review",
    "update_note_from_payload",
    "work_chunk_payload_from_query",
}

FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS = {
    "base_url",
    "bytes",
    "corpus_root",
    "error",
    "metadata_error",
    "models",
    "modified_at",
    "notes",
    "path",
    "primary_output",
    "regeneration_commands",
    "sha256",
    "site_root",
    "source_root",
    "uses_env_corpus_root",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def import_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def nested_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(nested_keys(child))
    return keys


def nested_strings(value) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            strings.extend(nested_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(nested_strings(child))
    return strings


def check_loopback_boundary() -> None:
    for host in ("127.0.0.1", "127.12.34.56"):
        require(validate_reader_host(host) == host, f"loopback host should be accepted: {host}")
    require(validate_reader_host("localhost") == "127.0.0.1", "localhost should normalize to an explicit loopback")
    for host in ("", "0.0.0.0", "::", "::1", "[::1]", "192.168.1.10", "reader.local"):
        try:
            validate_reader_host(host)
        except ValueError:
            pass
        else:
            raise AssertionError(f"non-loopback host should be rejected: {host!r}")
    try:
        LoopbackThreadingHTTPServer(("0.0.0.0", 0), Handler)
    except ValueError:
        pass
    else:
        raise AssertionError("reader HTTP server should reject non-loopback binds")

    launcher = LAUNCHER.read_text(encoding="utf-8-sig")
    require('[string]$ReaderHost = "127.0.0.1"' in launcher, "launcher must default to loopback")
    require("Same LAN:" not in launcher, "launcher must not advertise unauthenticated LAN URLs")
    require("Test-PortLoopbackOnly" in launcher, "launcher must reject an existing non-loopback listener")


def check_static_publication_boundary() -> None:
    for path in ("/", "/category/nietzsche", "/search", "/styles.css", "/app.js", "/assets/design-tokens.css"):
        require(resolve_static_file(path).is_file(), f"public static route should resolve: {path}")

    for path in (
        "/server.py",
        "/runtime_status.py",
        "/path_config.py",
        "/run_reader_with_gemma.ps1",
        "/README.md",
        "/templates/work.html",
        "/data/notes/nietzsche_notes.jsonl",
        "/data/segment_offset_index.sqlite",
        "/data/search_index.sqlite",
        "/%2e%2e/server.py",
        "/assets/..%5cserver.py",
    ):
        try:
            resolve_static_file(path)
        except PermissionError:
            pass
        else:
            raise AssertionError(f"private site file should be denied: {path}")

    try:
        resolve_static_file("/assets/missing.css")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing public asset should remain a 404")


def check_public_diagnostics_boundary() -> None:
    original_gemma_summary = runtime_status.gemma_runtime_summary
    runtime_status.gemma_runtime_summary = lambda: {
        "base_url": "http://127.0.0.1:9999",
        "reachable": False,
        "model_count": 0,
        "models": [],
        "state": "failed",
        "error": f"private runtime path: {SITE}",
    }
    try:
        payloads = [
            runtime_status.build_public_runtime_health(),
            runtime_status.build_public_artifact_manifest(),
        ]
    finally:
        runtime_status.gemma_runtime_summary = original_gemma_summary

    for payload in payloads:
        exposed_keys = sorted(FORBIDDEN_PUBLIC_DIAGNOSTIC_KEYS & nested_keys(payload))
        require(not exposed_keys, "public diagnostics expose private keys: " + ", ".join(exposed_keys))
        for value in nested_strings(payload):
            require(str(SITE) not in value, "public diagnostics expose the site path")
            require(str(runtime_status.ROOT) not in value, "public diagnostics expose the corpus path")
        json.dumps(payload, ensure_ascii=False)


def main() -> None:
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = import_modules(tree)
    names = imported_names(tree)

    banned_modules = [
        module
        for module in modules
        if any(module == prefix.rstrip(".") or module.startswith(prefix) for prefix in BANNED_IMPORT_PREFIXES)
    ]
    require(not banned_modules, "server imports low-level modules: " + ", ".join(sorted(banned_modules)))

    banned_names = sorted(BANNED_IMPORTED_NAMES & names)
    require(not banned_names, "server imports low-level helper names: " + ", ".join(banned_names))

    missing_names = sorted(REQUIRED_IMPORTED_NAMES - names)
    require(not missing_names, "server missing boundary helper imports: " + ", ".join(missing_names))
    require(
        "payload = self.read_json_payload(max_length=65536)" in source,
        "human translation review payload limit must accommodate 12,000 UTF-8 characters",
    )

    require("class Handler(BaseHTTPRequestHandler)" in source, "server should keep the HTTP handler")
    require("class LoopbackThreadingHTTPServer(ThreadingHTTPServer)" in source, "server should enforce loopback binding")
    require("def main()" in source, "server should keep the CLI entrypoint")
    check_loopback_boundary()
    check_static_publication_boundary()
    check_public_diagnostics_boundary()
    print("server boundary ok")


if __name__ == "__main__":
    main()
