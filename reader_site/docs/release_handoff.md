# Release Handoff

Date: 2026-06-05

This document defines how to publish or move the Personal Archive of Literature project without committing the large primary-source corpora.

## Repository Policy

Git should store:

- reader-site application code;
- templates, CSS, JavaScript, and static UI assets;
- metadata builders and validation scripts;
- small catalog/metadata JSON files;
- documentation and handoff notes.

Git should not store:

- local source corpus folders;
- generated `*_segments.jsonl` files;
- generated search indexes and SQLite databases;
- local artifact manifests;
- personal note JSONL files;
- generated AI interpretation JSONL/SQLite files;
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
python .\server.py --port 8787
```

5. Open:

```text
http://127.0.0.1:8787/
```

## Pre-Push Checks

Run these before staging or pushing a release branch:

```powershell
cd .\reader_site
python .\scripts\build_release_stage_manifest.py --check
python .\scripts\check_release_contracts.py
python .\scripts\check_layout_contracts.py
python .\scripts\check_server_boundary.py
python .\scripts\check_provenance_contracts.py
python .\scripts\check_corpus_schema.py
python .\scripts\check_api_contracts.py
python .\scripts\check_search_contracts.py
python .\scripts\check_notes_contracts.py
python .\scripts\check_static_routes.py
python .\scripts\build_search_db.py --check
git diff --check
git status --short
```

`check_release_contracts.py` verifies that large corpus/generated files are not tracked, relevant existing local artifacts are ignored, no tracked file exceeds the release-size threshold, and README handoff instructions remain present.

`build_release_stage_manifest.py --check` classifies current Git changes as `stage`, `review`, or `block`. Use `--write` when you want a local JSON manifest at `data/release_stage_manifest.local.json`; that file is intentionally ignored by Git.

## Public Release Notes

This repository is a local research reader, not a public mirror of every primary source file. A clean clone needs access to the local source corpora before the full search and reading artifacts can be regenerated.

Small metadata files are kept in Git so the project structure, work catalog, route model, and validation code remain inspectable even without the large source folders.
