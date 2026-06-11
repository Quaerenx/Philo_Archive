# Release Handoff

Date: 2026-06-05

This document defines how to publish or move the Personal Archive of Literature project without committing the large primary-source corpora.

## Repository Policy

Git should store:

- reader-site application code;
- shared local path configuration in `reader_site/path_config.py`;
- templates, CSS, JavaScript, and static UI assets;
- metadata builders and validation scripts;
- small catalog/metadata JSON files;
- documentation and handoff notes.

Git should not store:

- local source corpus folders;
- generated `*_segments.jsonl` files;
- generated search indexes and SQLite databases;
- local artifact manifests;
- local visual QA screenshots;
- personal note JSONL files;
- generated AI interpretation JSONL/SQLite files;
- local Gemma runtime logs;
- `.env` or machine-specific local path files.

The enforced source-corpus exclusions are:

- `니체_원서수집/`
- `비트겐슈타인_원서수집/`
- `성경_원서수집/`
- `키르케고르_원서수집/`

The enforced generated-artifact exclusions are:

- `reader_site/data/*_segments.jsonl`
- `reader_site/data/search_index.jsonl`
- `reader_site/data/search_index.sqlite`
- `reader_site/data/search_index.sqlite-*`
- `reader_site/data/artifact_manifest.local.json`
- `reader_site/data/release_stage_manifest.local.json`
- `reader_site/data/visual_qa.local/`
- `reader_site/data/visual_qa.local/*`
- `reader_site/data/runtime.local/`
- `reader_site/data/runtime.local/*`
- `reader_site/data/notes/*.jsonl`
- `reader_site/data/ai/*.jsonl`
- `reader_site/data/ai/*.sqlite`
- `reader_site/data/ai/*.sqlite-*`

## Restore On Another Local Machine

1. Clone the repository.

2. Put the four source corpus folders next to `reader_site`, or put them in another parent folder and set:

```powershell
$env:PHILOSOPHY_CRAWL_ROOT="D:\archives\philosophy_crawl"
```

3. Rebuild local generated artifacts:

```powershell
cd .\reader_site
python .\scripts\rebuild_all.py
```

4. Start the reader:

```powershell
python .\server.py --port 8793
```

5. Open:

```text
http://127.0.0.1:8793/
```

## Pre-Push Checks

Run these before staging or pushing a release branch:

```powershell
cd .\reader_site
python .\scripts\build_release_stage_manifest.py --check
python .\scripts\check_clean_clone_contracts.py --run-source-light-checks
python .\scripts\check_ci_contracts.py
python .\scripts\check_encoding_contracts.py
python .\scripts\check_path_contracts.py
python .\scripts\check_source_publication_contracts.py
python .\scripts\check_release_contracts.py
python .\scripts\check_layout_contracts.py
python .\scripts\check_server_boundary.py
python .\scripts\check_provenance_contracts.py
python .\scripts\check_prompt_template_contracts.py --with-source-targets
python .\scripts\check_sentence_translation_contracts.py --with-source-targets
python .\scripts\check_corpus_schema.py
python .\scripts\check_restore_readiness.py
python .\scripts\check_source_target_contracts.py
python .\scripts\check_api_contracts.py
python .\scripts\check_search_contracts.py
python .\scripts\check_search_relevance.py
python .\scripts\check_search_artifact_integrity.py
python .\scripts\check_notes_contracts.py
python .\scripts\check_note_target_integrity.py
python .\scripts\check_ai_records_contracts.py
python .\scripts\check_static_routes.py
python .\scripts\build_search_db.py --check
git diff --check
git status --short
```

`check_release_contracts.py` verifies that large corpus/generated files are not tracked, relevant existing local artifacts are ignored, no tracked file exceeds the release-size threshold, and README handoff instructions remain present.

`build_release_stage_manifest.py --check` classifies current Git changes as `stage`, `review`, or `block`. Use `--write` when you want a local JSON manifest at `data/release_stage_manifest.local.json`; that file is intentionally ignored by Git.

`check_clean_clone_contracts.py --run-source-light-checks` verifies that a source-light clone contains tracked restore documentation, validation scripts, and no forbidden source/generated artifacts while using an empty temporary corpus root. Use `--clone-smoke` after committing to create a real temporary clean clone; see `docs/clean_clone_reproducibility.md`.

`check_restore_readiness.py` verifies the local full-restore side of the same handoff: source roots, primary output folders, metadata, segment artifacts, portable search index, SQLite search database, and corpus coverage in search records.

`check_search_artifact_integrity.py` verifies that generated segment JSONL files, the portable search index, the SQLite search table, and the SQLite FTS table agree on target keys, URLs, text previews, and corpus record counts.

`check_note_target_integrity.py` verifies that local personal notes still resolve to existing works, and that paragraph/verse/segment notes point to generated segment records with canonical note target URLs.

`check_encoding_contracts.py` verifies UTF-8 tracked text, Korean source-root names, and common mojibake fragments. If Windows PowerShell displays Korean paths incorrectly, use `Get-Content -Encoding UTF8`; see `docs/encoding_policy.md`.

`check_path_contracts.py` verifies that `reader_site/path_config.py`, runtime diagnostics, source serving, builders, release checks, and source-light checks agree on the same four source-root names and primary output folders.

`check_prompt_template_contracts.py --with-source-targets` verifies that tracked AI prompt templates render deterministic prompt bundles from restored source targets, including `prompt_template_id`, `prompt_sha256`, `source_text_sha256`, and visible "Original source" / "Generated interpretation" labels. It does not call a model.

`check_sentence_translation_contracts.py --with-source-targets` verifies the on-demand sentence translation boundary, sentence IDs such as `p-0023.s001`, prompt checksums, and local JSONL record shape. It does not call Gemma.

GitHub pull requests run `.github/workflows/reader-site-source-light.yml`, which executes the source-light clean clone checks without local corpora.

`check_ci_contracts.py` verifies that the workflow remains source-light. `check_source_publication_contracts.py` verifies that tracked metadata and docs respect the publication boundary in `docs/source_publication_policy.md`.

For layout-facing changes, also run:

```powershell
python .\scripts\check_visual_smoke.py
```

This starts the local reader on a temporary port and writes ignored desktop/mobile PNG screenshots to `data/visual_qa.local/`.

## Public Release Notes

This repository is a local research reader, not a public mirror of every primary source file. A clean clone needs access to the local source corpora before the full search and reading artifacts can be regenerated.

Small metadata files are kept in Git so the project structure, work catalog, route model, and validation code remain inspectable even without the large source folders.
