# Personal Archive of Literature Reader Site

Personal archive index for collected primary texts.

## Run

Recommended daily start with local Gemma sentence translation:

```powershell
.\reader_site\run_reader_with_gemma.ps1
```

Then open:

```text
http://127.0.0.1:8793/
```

This starts Philo Archive on port `8793` and reuses or starts the shared local-only llama.cpp runtime at `http://127.0.0.1:9999`. The default model path is `C:\Users\PP\Downloads\gemma-4-26B-A4B-it-Q4_K_M.gguf`. The shared runtime remains running when the Reader stops; pass `-StopGemmaWithReader` only for an explicitly isolated run.

If you only need the reader without local translation:

```powershell
python .\reader_site\server.py --port 8793
```

Check the running local reader and Gemma sidecar:

```powershell
cd .\reader_site
python .\scripts\check_local_runtime.py --plain
```

For the short internal-user runbook, see `docs/local_operator_quickstart.md`.

The source corpus root defaults to the parent directory of `reader_site`. On another machine, either keep the same sibling-folder layout or set:

```powershell
$env:PHILOSOPHY_CRAWL_ROOT="D:\archives\philosophy_crawl"
```

## Data

The server builds `/api/archive` from the existing corpus folders without editing source files:

- Nietzsche Markdown exports
- Wittgenstein manifest exports
- Bible Markdown and inventory exports
- Kierkegaard SKS JSON exports

The home page uses the lightweight `/api/archive/summary` response and the bounded `/api/archive/titles?q=...` title-autocomplete response. Autocomplete searches a stale-safe in-memory title index and does not revalidate the source tree per query. Category and archive consumers keep the compatible full `/api/archive` payload. `build_archive_catalog.py` writes an ignored, versioned local catalog whose input signature covers the relevant metadata and source files; runtime use falls back to a live rebuild when the catalog is missing, corrupt, or stale.

Nietzsche works are grouped for reading through `data/nietzsche_catalog.json`; the original Markdown export files are left unchanged.

Markdown links open through `/read?path=...` by default so collected texts are presented as reading pages. `/source?path=...` remains available for raw source inspection.

Catalogued works have stable work pages through the common `/work/<corpus_id>/<work_id>` route. Nietzsche keeps URLs such as `/work/nietzsche/M`, with a table of contents plus section and paragraph anchors. Bible books use source-aware IDs such as `/work/bible/oshb.Gen`, with chapter and verse anchors such as `#Gen.1.1`. Kierkegaard and Wittgenstein work pages group related variants behind tabs, for example `/work/kierkegaard/aas` and `/work/wittgenstein/Ms-101`.

Nietzsche research data lives in:

- `data/nietzsche_metadata.json`
- `data/nietzsche_concepts.json`
- `data/notes/nietzsche_notes.jsonl` after the first saved note

Regenerate Nietzsche metadata with:

```powershell
python .\scripts\build_nietzsche_metadata.py
```

Regenerate Bible work metadata and verse segments with:

```powershell
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
```

Bible research data lives in:

- `data/bible_metadata.json`
- `data/bible_segments.jsonl`
- `data/notes/bible_notes.jsonl` after the first saved Bible note

Regenerate Kierkegaard and Wittgenstein grouped work metadata with:

```powershell
python .\scripts\build_kierkegaard_metadata.py
python .\scripts\build_wittgenstein_metadata.py
```

Their generated metadata lives in:

- `data/kierkegaard_metadata.json`
- `data/wittgenstein_metadata.json`

Regenerate the cross-corpus research segment index and search database with:

```powershell
python .\scripts\rebuild_all.py
```

The helper runs the metadata builders, segment builders, source-target byte-offset index builder, search index/database builders, artifact manifest builder, and contract checks in order. Use `--skip-search-db`, `--skip-manifest`, or `--no-checks` for a lighter local rebuild.

The explicit command sequence is:

```powershell
python .\scripts\build_nietzsche_metadata.py
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
python .\scripts\build_kierkegaard_metadata.py
python .\scripts\build_kierkegaard_segments.py
python .\scripts\build_wittgenstein_metadata.py
python .\scripts\build_wittgenstein_segments.py
python .\scripts\build_nietzsche_segments.py
python .\scripts\build_segment_offset_index.py
python .\scripts\build_archive_catalog.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
python .\scripts\build_artifact_manifest.py
```

Search endpoints and page:

- `/search`
- `/api/search?q=ressentiment&corpus_id=nietzsche`
- `/api/search?q=ressentiment&corpus_id=nietzsche&work_id=GM`
- `/api/search?q=Gen%201%3A1`
- `/api/search?q=%EC%B0%BD%201%3A1`
- `/api/search?q=John%203%3A16`
- `/api/search?q=%EC%9A%94%203%3A16`
- `/api/search?q=lxx%20Gen%201%3A1`
- `data/search_index.jsonl`
- `data/search_index.sqlite` with SQLite FTS5 search when regenerated by `build_search_db.py`
- `data/segment_offset_index.sqlite` for bounded source-target lookup; regenerate it with `python .\scripts\build_segment_offset_index.py`

Source-target and sentence-translation lookup never rebuilds the offset index during an HTTP request. The SQLite sidecar stores one `(corpus_id, work_id, variant_id, segment_id)` key with its JSONL byte offset, byte length, and record order. It also stores each source file's name, size, nanosecond mtime, SHA-256, and record count. Runtime lookups validate the inexpensive size/mtime signature, seek and parse one binary JSONL record, and fail with the rebuild command if the index is missing, stale, or corrupt. Run `python .\scripts\build_segment_offset_index.py --check` for the slower full SHA-256 validation.

Very large Wittgenstein works use the same verified byte-offset index for server-side chunk loading. A work is virtualized only when it has at least 2,000 generated segments and 2 MiB of indexed source text. The initial work response renders one chunk plus lightweight placeholders; the browser loads adjacent chunks through `/api/work-chunks`, keeps sentence and paragraph anchors stable, and removes distant loaded chunks while retaining their measured height. Normal-sized works keep the existing eager rendering path. Virtual pages expose an `전체 인쇄 보기` link that requests `view=print` and renders the complete work for printing.

Notes page and endpoints:

- `/notes`
- `/study`
- `/api/study?corpus_id=nietzsche`
- `/api/study/export?format=markdown&corpus_id=nietzsche`
- `/api/notes?corpus_id=nietzsche&work_id=M`
- `/api/notes/export?format=json`
- `/api/notes/export?format=jsonl`
- `/api/notes/export?format=markdown`

Search runtime code and `/api/search` query payload normalization live in `services/search.py`; `server.py` only exposes the HTTP route.
Bible lookup and work aliases also accept LXX/deuterocanonical shorthand such as `Tob`, `Wis`, `Sir`, `EpJer`, `Psalm 151`, and grouped labels such as `Additions to Daniel`.
Bible direct lookup handles references such as `Gen 1:1`, `Genesis 1:1`, `John 3:16`, `1 John 5:7`, Korean abbreviations such as `창 1:1`, `요 3:16`, `요일 5:7`, and source-prefixed `lxx Gen 1:1`.
Search responses include matching works through `work_results`, segment results through `results`, and matching personal notes through `note_results`.
Work alias search handles compact sigla and titles such as `GM`, `M`, `John`, `1 John`, `Genesis`, `Ecclesiasticus`, and source-prefixed queries such as `lxx Genesis`.
Work-title aliases are Unicode-folded for matching, so practical ASCII input such as `Morgenrothe`, `Gotzen-Dammerung`, `Jenseits von Gut und Bose`, and `Frygt og Baeven` resolves to titles stored with diacritics.
Search results link back into `/notes` by work and segment target. Notes storage, query/export payload assembly, and create/update/delete record normalization live in `services/notes.py`; the `/notes` page gives a cross-work notes index with direct edit/delete controls and a Working/Saved workflow (stored as raw/reviewed internally), while `/study` is backed by `/api/study` bundles and gives a quieter reading view for saved notes by corpus and work. Study bundles include deterministic summaries, tag counts, saved date ranges, Markdown export, and print-friendly CSS. JSON, JSONL, and Markdown export links remain available.
Source path validation plus `/read` and `/source` response assembly live in `services/sources.py`; `server.py` only maps errors to HTTP responses and sends the returned HTML or inline file.
Shared source-root and primary-output path constants live in `path_config.py`; runtime diagnostics, source serving, builders, and release checks use that file as the path baseline.
Static entrypoint resolution and file response metadata live in `services/static_files.py`; only named pages, top-level `app.js`/`styles.css`, and approved web assets under `/assets/` are publishable. Versioned JS/CSS responses use immutable browser caching, representation-specific ETags, Last-Modified validation, conditional `304` responses, and gzip negotiation. HTML is revalidated and API responses remain `no-store`. Code, templates, local data, logs, and configuration remain private even though they share the site directory.
Archive index construction for `/api/archive`, `/api/archive/summary`, and `/api/archive/titles` lives in `corpora/archive.py`; it turns the local corpus folders and generated metadata into category-page links while keeping the home response lightweight.
Corpus catalog, metadata, work resolution, Bible segment lookup, and `/api/bible/segments` payload assembly live in `corpora/catalogs.py`.
Corpus-specific work-page model builders live in `corpora/work_models.py`; they adapt Nietzsche, Bible, Kierkegaard, and Wittgenstein into the common work-page shape.
Work page HTML assembly lives in `services/work_pages.py`; it selects the corpus-specific work model and applies the common `templates/work.html` markup.
Work-page browser behavior is split into ordered feature scripts: `assets/reader-work.js` holds shared state and helpers, followed by panel, runtime, sentence, translation, notes/citation, and app-bootstrap modules. Browser persistence stays isolated in `assets/reader-work-storage.js`, while virtual document loading stays in `assets/reader-work-virtual.js`; both adapters load before the feature scripts. Work-page styling follows the same boundary with shell, study, controls, translation, notes, source, and responsive stylesheets, each kept below the reader module size budget enforced by the layout contract check.
Markdown, Bible verse, Kierkegaard JSON, and plain segment rendering helpers live in `rendering/documents.py`.
Common work-page markup and template rendering live in `rendering/work_markup.py`.
Reading/source page rendering lives in `rendering/static_pages.py`, backed by `templates/reading.html`, `templates/source.html`, and `assets/static-reader.css`.
Source target resolution for AI/Gemma interpretation lives in `services/source_targets.py`; it resolves selected segment URLs and computes `source_text_sha256` from local `text_raw` segment records.
The local `/api/source-target?corpus_id=...&work_id=...&target_id=...` endpoint returns a bounded source target bundle for one generated segment. It is a pre-AI input boundary only: it returns exact source text plus checksum, but it does not call Gemma or save generated interpretations.
Prompt template preparation lives in `data/ai_prompt_templates.json` and `services/interpretation_prompts.py`. It renders a selected source target into a deterministic prompt bundle with audit metadata kept outside the model-facing prompt. The default interpretation template distinguishes direct textual evidence from reasoned inference.
On-demand sentence translation lives in `services/sentence_targets.py` and `services/sentence_translations.py`. The browser sends only stable target IDs; the server resolves the canonical sentence, marks it inside a structural context of adjacent source units (up to 6,000 characters), and prefers complete sentence boundaries whenever context must be shortened. Local llama.cpp returns a strict JSON-Schema draft, then a fresh critic request checks only the approved policy, source context, and draft translation. Major issues permit one revision and one final critic; minor-only issues are left for human review, and there is no repair loop. Translation, material translation-decision commentary, uncertainty cautions, automated `quality_state`, and human `review_state` remain separate. Human-approved work terminology can be registered in `data/translation_profiles.json` and is never auto-populated from generated output. Generated schema-v5 records include distinct source-segment, sentence, context, translator-request, and full-pipeline hashes; they are stored locally under `data/ai/*_sentence_translations.jsonl` and intentionally ignored by Git. The Translations page groups repeated runs by sentence, shows the newest version first, keeps older versions collapsed, and stores a human-confirmed correction separately while preserving the model original. The per-corpus human evaluation seed set lives in `data/translation_quality_goldset.json`; pending samples are never counted as evaluated gold results.

The main navigation intentionally omits Notes and Study. Their direct pages and APIs remain available for backward compatibility while existing local data is retained.

Repeated note and sentence-translation list reads use bounded, file-signature-aware in-process caches. Successful atomic writes invalidate the relevant service cache, while external file changes are detected from file metadata. The JSONL files remain the source of truth.

Runtime diagnostics:

- `/api/health` reports redacted corpus, search, and Gemma readiness without local paths, model names, personal-note state, or detailed file inventory.
- `/api/health/gemma` reports only the redacted Gemma readiness needed by the Reader polling loop.
- `/api/artifacts` returns a redacted artifact-readiness manifest without paths, sizes, timestamps, checksums, or local configuration.

Corpus and search readiness use independent short-lived caches; Gemma readiness uses a shorter cache so startup and failure changes appear promptly. Cache construction is serialized per status source, so concurrent health requests do not duplicate the same filesystem or SQLite work.
- To write a local manifest for handoff or backup checks:

```powershell
python .\scripts\build_artifact_manifest.py
```

The default manifest output is `data/artifact_manifest.local.json`, which is intentionally ignored by Git because it records local machine state. Add `--checksums` when you need SHA-256 hashes for large generated artifacts.
Use `--check` when you only want to validate manifest generation and any existing local manifest JSON without writing.

The HTTP server accepts loopback bind addresses only. Its APIs can read local source material and mutate notes, so direct unauthenticated LAN exposure is deliberately unsupported.

Current documentation is indexed in `docs/README.md`. Superseded roadmaps, completed execution reviews, and dated security-validation receipts are preserved under `../OLD/`; see `../OLD/README.md` for the archive inventory and reasons.
Corpus-facing Korean labels and the default Bible, Kierkegaard, and Wittgenstein representation order are fixed in `docs/corpus_display_policy.md` and enforced by the layout contracts.

Check the release/Git handoff policy with:

```powershell
python .\scripts\build_release_stage_manifest.py --check
python .\scripts\check_clean_clone_contracts.py --run-source-light-checks
python .\scripts\check_ci_contracts.py
python .\scripts\check_encoding_contracts.py
python .\scripts\check_path_contracts.py
python .\scripts\check_source_publication_contracts.py
python .\scripts\check_prompt_template_contracts.py
python .\scripts\check_release_contracts.py
```

The clean clone contract verifies that a source-light Git clone contains the tracked code, docs, and validation gates needed to restore the archive elsewhere. `--run-source-light-checks` runs against an empty temporary corpus root so it cannot pass by accidentally using local source folders. See `docs/clean_clone_reproducibility.md`.

The CI contract verifies that the GitHub Actions workflow runs only source-light checks. The source publication contract verifies that the repository remains a reader scaffold, not a public mirror of primary-source corpora. See `docs/source_publication_policy.md`.

The encoding contract verifies that tracked text files are UTF-8 and that Korean source-root names remain uncorrupted. See `docs/encoding_policy.md`.

GitHub pull requests run the source-light subset through `.github/workflows/reader-site-source-light.yml`.

Check the documented runtime and layout contracts with:

```powershell
python .\scripts\check_server_boundary.py
python .\scripts\check_layout_contracts.py
python .\scripts\check_work_chunk_contracts.py
python .\scripts\check_provenance_contracts.py
python .\scripts\check_prompt_template_contracts.py --with-source-targets
python .\scripts\check_sentence_translation_contracts.py --with-source-targets
python .\scripts\check_corpus_schema.py
python .\scripts\check_restore_readiness.py
python .\scripts\check_source_target_contracts.py
python .\scripts\check_api_contracts.py
```

Check search behavior and Bible direct lookup with:

```powershell
python .\scripts\check_search_contracts.py
python .\scripts\check_search_relevance.py
python .\scripts\check_search_artifact_integrity.py
```

The relevance suite includes stable lookup benchmarks plus 12 manually curated research questions across all four corpora. It does not collect live user searches; see `docs/search_quality_policy.md`.

Check notes storage, filtering, update, delete, and export behavior with:

```powershell
python .\scripts\check_notes_contracts.py
python .\scripts\check_note_target_integrity.py
```

`check_note_target_integrity.py` scans local personal note JSONL files after restore. Work targets must still resolve, and paragraph/verse/segment notes must point to generated segment records with matching canonical work URLs.

Check local AI interpretation JSONL files before enabling or importing generated interpretation records:

```powershell
python .\scripts\check_ai_records_contracts.py
python .\scripts\check_translation_goldset.py
```

Use `python .\scripts\check_translation_goldset.py --require-complete` only when every seed case has been translated and scored by a real human evaluator. See `docs/translation_quality_evaluation.md`.

Capture local browser screenshots for visual smoke QA:

```powershell
python .\scripts\check_visual_smoke.py
```

The visual smoke script writes ignored PNG artifacts under `data/visual_qa.local/` and requires a local Edge, Chrome, or Chromium install. In locked-down browser environments, validate the routed HTML/UI markers without screenshots:

```powershell
python .\scripts\check_visual_smoke.py --html-only
```

To keep HTML marker validation while recording flaky local browser screenshot failures, use:

```powershell
python .\scripts\check_visual_smoke.py --allow-screenshot-failures
```

Validate the core reader interaction flow in a headless browser:

```powershell
python .\scripts\check_reader_interaction_smoke.py
```

This checks that a sentence URL selects the source sentence, opens the study panel state, keeps the selected sentence visible to the translation/commentary workflow, and carries the recent-work record back to the home page. It prefers the same local Node/Playwright runtime used by the visual smoke check and retains direct headless-browser capture as a fallback.

For manual browser QA of the work reader, open a cached sentence such as:

```text
http://127.0.0.1:8793/work/nietzsche/GM#p-0004.s001
```

Confirm that the selected sentence loads its cached translation, the Translation/Commentary jump buttons scroll within the study card, the mobile study panel opens/closes with the handle and outside tap, the Notes sort control updates the list summary, and mobile viewports do not create horizontal page overflow.

Check the static pages, representative work page, `/api/health`, and `/api/study` through a temporary local HTTP server with:

```powershell
python .\scripts\check_static_routes.py
```

Current documentation index: `docs/README.md`.

Runtime/API schema reference: `docs/api_reference.md`.

Common corpus/work/variant/segment schema contract: `docs/corpus_schema.md`.

AI/Gemma interpretation provenance policy: `docs/ai_interpretation_policy.md`.

Local Windows autostart: `docs/local_windows_autostart.md`.

Release handoff and Git upload policy: `docs/release_handoff.md`.

Historical planning, handoff, review, and validation material: `../OLD/README.md`.

Layout vocabulary is centralized in `assets/design-tokens.css`; use "page frame" for the 1000px outer archive frame and "reader column" for the 764px white content column.

`/source?path=...` only serves files inside the known corpus roots.
