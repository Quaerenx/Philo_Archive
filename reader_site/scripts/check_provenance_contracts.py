from __future__ import annotations

import ast
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
POLICY = SITE / "docs" / "ai_interpretation_policy.md"
GITIGNORE = REPO / ".gitignore"
SERVER = SITE / "server.py"
AI_RECORD_VALIDATOR = SITE / "scripts" / "check_ai_records_contracts.py"
SOURCE_TARGETS = SITE / "services" / "source_targets.py"
SOURCE_TARGET_VALIDATOR = SITE / "scripts" / "check_source_target_contracts.py"

REQUIRED_POLICY_SECTIONS = [
    "## Non-Replacement Rule",
    "## Source Boundary",
    "## Record Schema",
    "## Storage Policy",
    "## User-Visible Labels",
    "## Prompt And Model Metadata",
    "## Privacy Boundary",
    "## Pre-Implementation Gates",
]

REQUIRED_SCHEMA_FIELDS = [
    "schema_version",
    "record_type",
    "id",
    "created_at",
    "generated_at",
    "corpus_id",
    "work_id",
    "variant_id",
    "target_id",
    "target_url",
    "source_text_sha256",
    "source_text_excerpt",
    "source_language",
    "model_provider",
    "model_name",
    "model_version",
    "prompt_template_id",
    "prompt_sha256",
    "temperature",
    "interpretation",
    "citations",
    "review_state",
]

REQUIRED_GITIGNORE_RULES = [
    "reader_site/data/ai/*.jsonl",
    "reader_site/data/ai/*.sqlite",
    "reader_site/data/ai/*.sqlite-*",
]

FORBIDDEN_SERVER_ROUTE_NEEDLES = [
    "/api/ai",
    "/api/gemma",
    "/api/interpret",
]


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


def check_policy_document() -> None:
    require(POLICY.exists(), "missing docs/ai_interpretation_policy.md")
    text = POLICY.read_text(encoding="utf-8")
    for section in REQUIRED_POLICY_SECTIONS:
        require(section in text, f"AI policy missing section {section}")
    for field in REQUIRED_SCHEMA_FIELDS:
        require(f'"{field}"' in text or f"`{field}`" in text, f"AI policy missing schema field {field}")
    for phrase in [
        "AI output is not source text.",
        "overwrite `text_raw`",
        "reader_site/data/ai/",
        "Generated interpretation",
        "Original source",
        "Personal note",
        "source_text_sha256",
        "prompt_sha256",
        "services/source_targets.py",
        "check_source_target_contracts.py",
    ]:
        require(phrase in text, f"AI policy missing provenance phrase {phrase!r}")


def check_gitignore() -> None:
    text = GITIGNORE.read_text(encoding="utf-8")
    for rule in REQUIRED_GITIGNORE_RULES:
        require(rule in text, f".gitignore missing generated AI rule {rule}")
    require((SITE / "data" / "ai" / ".gitkeep").exists(), "missing data/ai/.gitkeep")


def check_no_active_ai_routes() -> None:
    source = SERVER.read_text(encoding="utf-8")
    for needle in FORBIDDEN_SERVER_ROUTE_NEEDLES:
        require(needle not in source, f"server exposes {needle} before provenance implementation gates")

    tree = ast.parse(source)
    names = imported_names(tree)
    suspicious_imports = sorted(name for name in names if name.lower() in {"openai", "ollama", "gemma"})
    require(not suspicious_imports, "server imports AI runtime before policy implementation: " + ", ".join(suspicious_imports))


def check_record_validator() -> None:
    require(AI_RECORD_VALIDATOR.exists(), "missing AI JSONL record validator")
    source = AI_RECORD_VALIDATOR.read_text(encoding="utf-8")
    for field in REQUIRED_SCHEMA_FIELDS:
        require(f'"{field}"' in source, f"AI record validator missing schema field {field}")


def check_source_target_resolver() -> None:
    require(SOURCE_TARGETS.exists(), "missing source target resolver")
    source = SOURCE_TARGETS.read_text(encoding="utf-8")
    for phrase in [
        "resolve_segment_target",
        "source_text_sha256",
        "sha256_text",
        "text_raw",
    ]:
        require(phrase in source, f"source target resolver missing {phrase}")

    require(SOURCE_TARGET_VALIDATOR.exists(), "missing source target contract check")
    validator = SOURCE_TARGET_VALIDATOR.read_text(encoding="utf-8")
    for corpus_id in ["nietzsche", "bible", "kierkegaard", "wittgenstein"]:
        require(f'"{corpus_id}"' in validator, f"source target check missing corpus case {corpus_id}")


def main() -> None:
    check_policy_document()
    check_gitignore()
    check_no_active_ai_routes()
    check_record_validator()
    check_source_target_resolver()
    print("provenance contracts ok")


if __name__ == "__main__":
    main()
