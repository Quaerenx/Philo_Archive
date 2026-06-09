# Upgrade Completion Audit

Date: 2026-06-09

This audit records the current evidence for the reader-site upgrade goal:
review the proposed enhancement order, apply the parts judged sound, and keep the project moving toward a stable research archive rather than a one-off crawler output.

## Current Verdict

The stabilization and standardization phase is complete for the current non-AI research-reader scope.

The project now has:

- a common four-corpus reader route model;
- cross-corpus metadata and segment contracts;
- search, notes, study, artifact, and route checks;
- search relevance and AI JSONL record checks;
- local browser visual smoke QA automation;
- a thin HTTP server guarded by an explicit boundary check;
- documented rebuild and validation commands.

The branch has been pushed and GitHub PR #1 has been opened. Remaining work should be treated as post-merge product iteration: visual taste polish, real-query search calibration, and an optional AI/Gemma runtime only after the documented provenance gates remain satisfied.

## Evidence Snapshot

Latest verified checks:

```powershell
python .\scripts\check_server_boundary.py
python .\scripts\check_layout_contracts.py
python .\scripts\build_release_stage_manifest.py --check
python .\scripts\check_release_contracts.py
python .\scripts\check_provenance_contracts.py
python -m compileall -q .\server.py .\runtime_status.py .\corpora .\rendering .\services .\scripts
python .\scripts\check_api_contracts.py
python .\scripts\check_static_routes.py
python .\scripts\check_search_contracts.py
python .\scripts\check_search_relevance.py
python .\scripts\check_notes_contracts.py
python .\scripts\check_ai_records_contracts.py
python .\scripts\check_corpus_schema.py
python .\scripts\build_search_db.py --check
git diff --check
```

Observed results:

- `server boundary ok`
- `layout contracts ok`
- `release stage manifest` with `block: 0`, `review: 0`, and current changes classified as stage candidates
- `release contracts ok`
- `provenance contracts ok`
- `api contracts ok`
- `static routes ok`
- `search contracts ok`
- `notes contracts ok`
- `corpus schema ok`
- `search sqlite db exists (225442 records, fts5=True)`
- `git diff --check` exits successfully, with existing CRLF warnings for `reader_site/docs/project_handoff_for_expert.md` and `reader_site/server.py`.

Current corpus schema counts:

| Corpus | Works | Segments |
|---|---:|---:|
| Nietzsche | 33 | 14,227 |
| Bible | 121 | 60,180 |
| Kierkegaard | 211 | 25,359 |
| Wittgenstein | 202 | 125,676 |

## Completed Requirements

### Cross-Corpus Structure

Evidence:

- `docs/corpus_schema.md`
- `scripts/check_corpus_schema.py`
- `data/*_metadata.json`
- `data/*_segments.jsonl`

Status: complete for the current four-corpus scope.

Nietzsche, Bible, Kierkegaard, and Wittgenstein all expose common work, variant, and segment fields. The schema check verifies required metadata/segment fields and the current work/segment counts.

### Common Work Pages

Evidence:

- `corpora/work_models.py`
- `services/work_pages.py`
- `templates/work.html`
- `assets/reader-work.css`
- `scripts/check_static_routes.py`

Status: complete for representative work routes.

The static route check verifies:

- `/work/nietzsche/M`
- `/work/bible/oshb.Gen`
- `/work/kierkegaard/aas`
- `/work/wittgenstein/Ms-101`

### Search

Evidence:

- `services/search.py`
- `data/search_index.sqlite`
- `scripts/check_search_contracts.py`

Status: complete for the current contract.

Search supports:

- SQLite FTS5 segment search;
- segment ranking with phrase, title/label, segment-type, and FTS-order signals;
- work alias results;
- note results;
- Bible direct lookup;
- source-prefixed Bible lookup;
- LXX/deuterocanonical aliases such as `Tob`, `Wis`, `Sir`, `EpJer`, `Psalm 151`, and `Additions to Daniel`.

The search contract now includes representative ranking checks for Nietzsche, Wittgenstein, and Kierkegaard source-language queries. Further tuning should be driven by collected real study queries rather than broad speculative ranking changes.

### Notes And Study

Evidence:

- `services/notes.py`
- `notes.html`
- `study.html`
- `assets/notes.js`
- `assets/study.js`
- `scripts/check_notes_contracts.py`

Status: complete for the current non-AI research workflow.

The site supports:

- note create/update/delete;
- raw/reviewed workflow;
- tag, target, work, corpus, and query filtering;
- JSON, JSONL, Markdown export;
- reviewed-note study bundles;
- deterministic study summaries;
- tag counts and reviewed ranges;
- print-friendly study CSS.

### Runtime Diagnostics And Rebuild Flow

Evidence:

- `runtime_status.py`
- `scripts/rebuild_all.py`
- `scripts/build_artifact_manifest.py`
- `/api/health`
- `/api/artifacts`

Status: complete for local reproducibility.

`rebuild_all.py` runs metadata builders, segment builders, search index/database builders, artifact manifest generation, and contract checks.

### Server Boundary

Evidence:

- `server.py`
- `scripts/check_server_boundary.py`
- `services/static_files.py`
- `services/work_pages.py`
- `services/sources.py`
- `services/search.py`
- `services/notes.py`
- `corpora/archive.py`
- `corpora/catalogs.py`

Status: complete for the current route size.

`server.py` is now a thin HTTP handler. The boundary check prevents it from directly importing low-level rendering, work-model, note-storage/export, source-rendering, and raw search helpers.

Current server size: 291 lines.

## Partially Complete Or Open

### Visual Identity And Page-Frame QA

Status: representative headless-browser QA complete; interactive in-app browser QA unavailable.

The layout vocabulary is centralized in `assets/design-tokens.css`, including:

- page frame: 1000px;
- reader column: 764px.

`scripts/check_layout_contracts.py` now verifies that the main entrypoints and shared reader pages use the same page-frame and reader-column tokens. The home index also folds the 764px reader column to the page frame on smaller screens.

The in-app browser connection was unavailable in this session, but representative headless Edge screenshots were captured for:

- `/` desktop and mobile;
- `/work/nietzsche/M` desktop and mobile;
- `/search?q=ressentiment&corpus_id=nietzsche` desktop;
- `/notes` desktop.

The screenshot pass verified page-frame/background separation, white reader-column separation, centered desktop layout, mobile reader folding, search result readability, and notes layout. It also caught and fixed a mobile work-page toolbar/citation overflow in `assets/reader-work.css`.

Remaining visual work should be treated as product polish rather than an unverified structural layout blocker.

`scripts/check_visual_smoke.py` now makes this local screenshot pass repeatable for `/`, `/category/nietzsche`, `/work/nietzsche/GM`, `/read`, `/source`, `/search`, `/notes`, and `/study` across desktop and mobile viewports.

### AI/Gemma Interpretation

Status: policy complete; runtime feature intentionally deferred.

Evidence:

- `docs/ai_interpretation_policy.md`
- `scripts/check_provenance_contracts.py`
- `scripts/check_ai_records_contracts.py`
- `.gitignore`
- `data/ai/.gitkeep`
- `docs/release_handoff.md`

The policy now defines:

- the non-replacement rule: AI output is not source text;
- allowed source target boundaries;
- required AI JSONL record fields;
- model, prompt, timestamp, citation, and checksum metadata;
- local-only storage under `data/ai/`;
- UI labels for original source, personal notes, and generated interpretation;
- privacy boundaries for selected source text and notes;
- pre-implementation gates before adding any AI endpoint or UI.

The provenance contract verifies that the policy remains present, generated AI output is ignored by Git, an AI JSONL record validator exists, and no active `/api/ai`, `/api/gemma`, or `/api/interpret` route has been exposed before those gates are implemented.

### Route Dispatch Module

Status: not currently necessary.

`server.py` is thin enough for now. A separate route table/module should be added only if the handler starts growing again.

### Release And Git Handoff

Status: release gate complete; branch pushed and GitHub PR #1 opened.

Evidence:

- `.gitignore`
- `docs/release_handoff.md`
- `scripts/build_release_stage_manifest.py`
- `scripts/check_release_contracts.py`
- `scripts/check_search_relevance.py`
- `scripts/check_ai_records_contracts.py`
- `scripts/check_visual_smoke.py`
- root `README.md`
- `reader_site/README.md`

The release contract verifies:

- source corpus folders are ignored;
- generated segment/search/artifact files are ignored;
- visual QA screenshots, personal note JSONL files, and local path/env files are ignored;
- forbidden large generated files are not tracked;
- tracked files stay below the release-size threshold;
- clone/rebuild instructions remain present in the READMEs.

The stage manifest classifies the current Git change set before commit/push and currently reports no blocked or review-required paths.

The audit proves branch push and PR creation, but not merge to `main`.

## Recommended Next Phase

1. Merge and post-merge smoke pass.
   Merge PR #1 when ready, then rerun the release, corpus, search, note, route, AI-record, and visual smoke checks on the target branch.

2. Search relevance calibration.
   Expand `data/search_eval_queries.json` with real study queries from use and tune work/segment/note result ordering from that evidence.

3. Visual identity polish.
   Use `scripts/check_visual_smoke.py` plus targeted browser review for corpus-specific headers, page-frame tone, and reader-frame consistency.

4. AI interpretation prototype.
   Implement Gemma/AI only after `scripts/check_ai_records_contracts.py` and the documented provenance gates remain satisfied in code and UI.

## Completion Position

The broad archive-upgrade foundation is complete for the current non-AI reader scope.

The remaining work is product iteration: merge/post-merge verification, larger real-query calibration, visual taste refinement, and an optional AI interpretation runtime.
