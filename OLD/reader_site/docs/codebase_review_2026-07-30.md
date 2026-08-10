# Codebase Review and Optimization - 2026-07-30

## Outcome

This pass reviewed the reader application end to end and implemented the improvements with the clearest evidence-to-risk ratio:

1. Permanent deletion of an individual local sentence-translation record from the existing Translations workflow.
2. Bounded, file-change-aware read caches for note and sentence-translation JSONL snapshots.
3. Complete release-stage classification for all current top-level reader HTML entrypoints.

The work preserves the existing loopback-only server boundary, static-file allowlist, atomic JSONL replacement, and per-file mutation locks. No dependency, public data schema, source-corpus file, or generated search artifact was changed.

## Reviewed Surface

The review covered:

- HTTP routing and boundary helpers in `server.py`;
- search, note, source, and sentence-translation services;
- JSONL mutation and concurrency behavior;
- the archive, search, notes, study, and translations user flows;
- the largest JavaScript and CSS assets;
- existing roadmap, handoff, security, API, and usability documents;
- contract, route, layout, interaction, and release-oriented checks;
- the existing dirty working tree, including the security remediation already in progress.

## Implemented Feature

### Permanent sentence-translation deletion

The existing Translations page already served as the practical review and cache-management surface, but it could only move records among `generated`, `reviewed`, and `rejected`.

The page now exposes a nested **Permanent delete** action when review actions are visible. The action:

- requires an explicit irreversible-action confirmation;
- calls `DELETE /api/sentence-translations/<record_id>?corpus_id=<corpus_id>`;
- removes exactly one record through the same per-file lock and atomic rewrite used by review updates;
- supports stable generated IDs and legacy public IDs;
- reports `400` for a missing/invalid corpus and `404` for a missing record;
- refreshes the visible list only after a successful deletion.

The HTTP route is intentionally a thin wrapper around a service boundary helper.

## Implemented Efficiency Improvement

### JSONL snapshot read caches

Note lists, translation exports, summaries, and review screens previously reparsed the complete JSONL file on every request, even when the file had not changed.

Both services now use an independent `lru_cache(maxsize=16)` keyed by:

- resolved file path;
- nanosecond modification time;
- change time;
- file size.

Each read returns new top-level record dictionaries so normal caller updates do not alter the cached dictionaries. Every successful in-process atomic write clears the service cache. An external file replacement or edit changes the file signature and therefore produces a cache miss. JSONL remains the authoritative storage layer.

### Local microbenchmark

Method: 5,000 synthetic records, 30 complete list reads, one cold read followed by unchanged reads, measured in the same local Python process.

| Service | Before | After | Change |
|---|---:|---:|---:|
| Notes | 0.2563 s total / 8.54 ms per read | 0.0621 s total / 2.07 ms per read | 75.8% lower total time (about 4.1x) |
| Sentence translations | 0.2684 s total / 8.95 ms per read | 0.0564 s total / 1.88 ms per read | 79.0% lower total time (about 4.8x) |

The measured cache state for each service was one miss and 29 hits. This is a local microbenchmark, not an end-to-end browser latency claim.

## Regression Coverage Added

The contracts now verify:

- unchanged snapshots produce cache hits;
- the caches are bounded;
- returned top-level dictionaries do not leak caller scalar mutations into the cache;
- an external translation JSONL edit invalidates the signature;
- concurrent translation deletion does not lose unrelated records;
- legacy public IDs support permanent deletion;
- repeated deletion returns not-found;
- the server imports only the service-level delete helper;
- the real local HTTP route deletes only a temporary isolated record;
- the UI contains the confirmation-gated DELETE workflow.

## Follow-up Modularization

### Work-reader browser storage boundary

The first responsibility-based split of `assets/reader-work.js` is complete. Browser persistence now lives in the DOM-independent `assets/reader-work-storage.js` adapter, while the main reader controller still constructs payloads from the current document and selection state.

The adapter owns:

- the unchanged `philo.reader.recentWork` local-storage record;
- the unchanged `philo.reader.studyPanelExpanded` local-storage value;
- the unchanged `philo.reader.noteDraft:<corpus>:<work>:<variant>` session-storage key and JSON payload;
- guarded storage access, JSON parsing/stringification, and deletion;
- a frozen `window.ReaderWorkStorage` API loaded before the main controller.

`reader-work.js` no longer calls `localStorage`, `sessionStorage`, `getItem`, `setItem`, or `removeItem` directly. It decreased from 3,216 to 3,174 lines; the more important result is that persistence can now be tested independently and changed without entering the DOM-heavy controller.

The layout contract fixes the module API, exact keys, absence of DOM/server dependencies, absence of direct storage calls in the controller, and script loading order. Browser checks now verify the actual recent-work payload, both study-panel values, and the existing note-draft fields (`note`, `tags`, `locked_target`, and `updated_at`).

### Browser interaction runner

The direct Chromium `--dump-dom` runner repeatedly failed on the current Windows browser build before reaching page assertions because the GPU process did not become usable. The dedicated reader interaction check now prefers the already available Node/Playwright path and keeps the direct launcher as a fallback. It preserves one browser context while moving from the selected work URL to the home page, so recent-work persistence remains an end-to-end assertion rather than a source-only check.

The reusable Korean execution prompt for this pass is `next_reader_work_modularization_prompt_ko.md`.

### Follow-up validation

The final modularization state passed:

- Node syntax checks for both reader scripts;
- an independent in-memory storage round trip for exact draft-key construction, recent work, both panel values, note draft save/read/delete, and malformed JSON isolation;
- Python compilation for the changed contract scripts;
- layout and static-route contracts;
- 25 routed HTML smoke cases;
- the dedicated desktop/mobile reader interaction smoke through both the default browser and explicit Chrome;
- 50 final Playwright desktop/mobile screenshots, including live recent-work, panel persistence, and note-draft payload assertions;
- the complete source-light clean-clone contract set;
- release-stage classification with `block: 0` and `review: 0`.

## Release Automation Fix

The stage-manifest allowlist covered the existing index, search, notes, and study HTML entrypoints but omitted `translations.html`. That caused a normal translation-page change to remain in the manual-review bucket.

The entrypoint is now classified consistently, and the release contract discovers every current top-level `*.html` page and requires the stage manifest to classify it as a reader entrypoint. The current working-tree manifest therefore has no blocked or unknown-review paths.

## Validation Results

Passed checks include:

- Python compileall for the server, services, and changed contract scripts;
- `node --check assets/translations.js`;
- notes, sentence-translation (including restored source targets), server-boundary, API, layout, and static-route contracts;
- an isolated HTTP DELETE test using a temporary AI directory, including `200`, repeated-delete `404`, and missing-corpus `400`;
- search contracts, 20-case search relevance, and 225,442-record search-artifact integrity;
- prompt, provenance, source-target, note-target, AI-record, path, encoding, source-publication, restore, corpus-schema, CI, release, and source-light clean-clone contracts;
- 25 routed HTML visual-smoke cases and 50 desktop/mobile browser screenshots;
- `git diff --check`;
- release-stage manifest: `block: 0`, `review: 0`.

No real sentence-translation record was deleted during validation; destructive route checks used an isolated temporary `PHILO_AI_DIR`. No live Gemma generation call was needed for this pass.

## Recommendations Deliberately Deferred

### Search ranking calibration

An initial follow-up calibration is complete in `search_quality_calibration_2026-07-30.md`. It expanded the deterministic evaluation set from 20 to 36 metadata- and corpus-derived cases and fixed general Unicode/ASCII work-title alias matching. The original 20 cases remain unchanged at MRR 0.9750, while all 36 expanded cases now pass at MRR 0.9861.

The remaining step is to append explicitly curated queries from real study sessions. Automatic query logging remains deliberately out of scope for privacy, and broad speculative weighting changes are still not justified.

### Further reader JavaScript splits

The browser-storage boundary is now separate. `assets/reader-work.js` remains the largest application source file, so any further split should still follow a measured responsibility boundary rather than line count. The strongest remaining candidates are translation request/review orchestration, note-list rendering and filtering, and the mobile panel gesture lifecycle. Inspect their callers and shared mutable state before choosing only one for the next pass.

### JSONL-to-SQLite migration

Atomic JSONL mutation still rewrites the complete file and is therefore O(n). That is acceptable for the current personal archive and keeps backups transparent. If note or translation stores grow to tens of thousands of frequently mutated records, benchmark writes and then consider a transactional SQLite store with indexed corpus/work/review fields and an explicit JSONL export path.

### Route registry extraction

`server.py` remains mostly HTTP dispatch and error mapping, and the boundary contract prevents low-level responsibilities from returning. Extract a route registry only when route growth creates repeated dispatch logic or makes isolated route testing materially harder.

## Current Risk

- The cache protects top-level record dictionaries; nested values are treated as read-only by current callers.
- File signatures are metadata-based. In-process writes explicitly clear caches, while normal external edits or replacements change at least one signature field.
- Permanent deletion is intentionally irreversible at the application layer. The confirmation copy and local-only server boundary reduce accidental or remote use, but backups remain the recovery mechanism.
