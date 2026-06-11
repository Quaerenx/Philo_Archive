from __future__ import annotations

import ast
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
SERVER = SITE / "server.py"

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
    "build_file_payload",
    "build_read_response",
    "build_source_response",
    "build_work_page_html",
    "create_note_from_payload",
    "delete_note_from_query",
    "notes_export_from_query",
    "notes_payload_from_query",
    "resolve_static_file",
    "search_payload_from_query",
    "sentence_translation_from_payload",
    "study_export_from_query",
    "study_payload_from_query",
    "update_note_from_payload",
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

    require("class Handler(BaseHTTPRequestHandler)" in source, "server should keep the HTTP handler")
    require("def main()" in source, "server should keep the CLI entrypoint")
    print("server boundary ok")


if __name__ == "__main__":
    main()
