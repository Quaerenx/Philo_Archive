# Personal Archive of Literature

Local reader site for collected primary texts.

The Git repository stores the reader application, metadata builders, templates, docs, and small metadata files. It does not store the large source corpora or large generated search artifacts.

The reader app is split by responsibility:

- `reader_site/server.py`: local HTTP routes and static/source/read responses.
- `reader_site/path_config.py`: shared source-root and primary-output path configuration.
- `reader_site/corpora/archive.py`: `/api/archive` root and category index construction.
- `reader_site/corpora/catalogs.py`: metadata loading, work resolution, and Bible segment lookup.
- `reader_site/corpora/work_models.py`: corpus-specific work-page model builders.
- `reader_site/rendering/`: common work, reading, source, and document HTML rendering.
- `reader_site/services/`: search, notes storage, source/read page services, source target resolution, and local sentence translation services.

## Daily Use

For normal reading and sentence-by-sentence Gemma study, run:

```powershell
cd .\reader_site
.\run_reader_with_gemma.ps1
```

Then open:

```text
http://127.0.0.1:8793/
```

If you only need the reader without local translation:

```powershell
cd .\reader_site
python .\server.py --port 8793
```

To confirm that the reader and local translator are reachable:

```powershell
python .\scripts\check_local_runtime.py --plain
```

For the short internal-user runbook, see `reader_site/docs/local_operator_quickstart.md`.

## Expected Local Layout

By default the app expects the source corpus folders next to `reader_site`:

```text
philosophy_crawl/
  reader_site/
  니체_원서수집/
  성경_원서수집/
  키르케고르_원서수집/
  비트겐슈타인_원서수집/
```

If the source folders live somewhere else, set `PHILOSOPHY_CRAWL_ROOT` to the directory that contains those four source folders.

```powershell
$env:PHILOSOPHY_CRAWL_ROOT="D:\archives\philosophy_crawl"
```

## Run

```powershell
cd .\reader_site
python .\server.py --port 8793
```

For local Gemma sentence translation:

```powershell
.\run_reader_with_gemma.ps1
```

Open:

```text
http://127.0.0.1:8793/
```

## Regenerate Local Artifacts

Run this after cloning on another local machine with the source corpora available:

```powershell
cd .\reader_site
python .\scripts\rebuild_all.py
```

For slower machines or quick manifest-free rebuilds, the helper also supports:

```powershell
python .\scripts\rebuild_all.py --skip-search-db
python .\scripts\rebuild_all.py --skip-manifest --no-checks
```

The explicit rebuild sequence is:

```powershell
cd .\reader_site
python .\scripts\build_nietzsche_metadata.py
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
python .\scripts\build_kierkegaard_metadata.py
python .\scripts\build_kierkegaard_segments.py
python .\scripts\build_wittgenstein_metadata.py
python .\scripts\build_wittgenstein_segments.py
python .\scripts\build_nietzsche_segments.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
python .\scripts\build_artifact_manifest.py
```

`build_search_db.py` creates the local SQLite search database with FTS5 enabled when supported by the local Python SQLite build.

Large generated files are ignored by Git:

- `reader_site/data/*_segments.jsonl`
- `reader_site/data/search_index.jsonl`
- `reader_site/data/search_index.sqlite`
- `reader_site/data/artifact_manifest.local.json`
- personal notes under `reader_site/data/notes/*.jsonl`
- generated AI records under `reader_site/data/ai/*.jsonl`
- local Gemma runtime logs under `reader_site/data/runtime.local/`

After starting the server, check the local runtime state at:

- `http://127.0.0.1:8793/api/health`
- `http://127.0.0.1:8793/api/artifacts`

Key validation commands:

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
python .\scripts\check_prompt_template_contracts.py
python .\scripts\check_sentence_translation_contracts.py
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
```

GitHub pull requests run the source-light subset through `.github/workflows/reader-site-source-light.yml`. That workflow intentionally avoids full corpus rebuilds because the public repository does not include local source corpora or generated search artifacts.

Before pushing to GitHub, read `reader_site/docs/release_handoff.md`, run `python .\scripts\build_release_stage_manifest.py --check`, `python .\scripts\check_clean_clone_contracts.py --run-source-light-checks`, `python .\scripts\check_ci_contracts.py`, `python .\scripts\check_encoding_contracts.py`, `python .\scripts\check_path_contracts.py`, `python .\scripts\check_source_publication_contracts.py`, `python .\scripts\check_restore_readiness.py`, `python .\scripts\check_source_target_contracts.py`, `python .\scripts\check_prompt_template_contracts.py --with-source-targets`, `python .\scripts\check_sentence_translation_contracts.py --with-source-targets`, `python .\scripts\check_note_target_integrity.py`, and `python .\scripts\check_release_contracts.py` to verify that local source corpora, large generated artifacts, personal notes, generated AI interpretations/translations, source target checksums, prompt checksums, clean-clone restore paths, GitHub Actions, source publication boundaries, restore readiness, shared path contracts, and Korean path names are handled correctly.
