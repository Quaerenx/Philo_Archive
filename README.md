# Personal Archive of Literature

Local reader site for collected primary texts.

The Git repository stores the reader application, metadata builders, templates, docs, and small metadata files. It does not store the large source corpora or large generated search artifacts.

The reader app is split by responsibility:

- `reader_site/server.py`: local HTTP routes and static/source/read responses.
- `reader_site/corpora/archive.py`: `/api/archive` root and category index construction.
- `reader_site/corpora/catalogs.py`: metadata loading, work resolution, and Bible segment lookup.
- `reader_site/corpora/work_models.py`: corpus-specific work-page model builders.
- `reader_site/rendering/`: common work, reading, source, and document HTML rendering.
- `reader_site/services/`: search, notes storage, and source/read page services.

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
python .\server.py --port 8787
```

Open:

```text
http://127.0.0.1:8787/
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
python .\scripts\build_wittgenstein_metadata.py
python .\scripts\build_nietzsche_segments.py
python .\scripts\build_kierkegaard_segments.py
python .\scripts\build_wittgenstein_segments.py
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

After starting the server, check the local runtime state at:

- `http://127.0.0.1:8787/api/health`
- `http://127.0.0.1:8787/api/artifacts`

Key validation commands:

```powershell
cd .\reader_site
python .\scripts\build_release_stage_manifest.py --check
python .\scripts\check_encoding_contracts.py
python .\scripts\check_release_contracts.py
python .\scripts\check_layout_contracts.py
python .\scripts\check_server_boundary.py
python .\scripts\check_provenance_contracts.py
python .\scripts\check_corpus_schema.py
python .\scripts\check_api_contracts.py
python .\scripts\check_search_contracts.py
python .\scripts\check_search_relevance.py
python .\scripts\check_notes_contracts.py
python .\scripts\check_ai_records_contracts.py
python .\scripts\check_static_routes.py
```

Before pushing to GitHub, read `reader_site/docs/release_handoff.md`, run `python .\scripts\build_release_stage_manifest.py --check`, `python .\scripts\check_encoding_contracts.py`, and `python .\scripts\check_release_contracts.py` to verify that local source corpora, large generated artifacts, personal notes, generated AI interpretations, and Korean path names are handled correctly.
