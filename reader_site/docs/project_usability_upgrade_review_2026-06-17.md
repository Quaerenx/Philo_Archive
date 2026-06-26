# Project Usability Upgrade Review - 2026-06-17

Refreshed: 2026-06-27

This document records the usability direction for the Personal Archive of Literature reader site. The goal is not only to store primary-source corpora, but to make reading, searching, note-taking, and local sentence-level AI study practical for daily research.

## Current Position

The project is now a source-first research reader with four corpus families:

- Nietzsche
- Bible
- Kierkegaard
- Wittgenstein

The common reader structure is in place:

- archive and category entry pages;
- common `/work/<corpus_id>/<work_id>` work pages;
- sentence or segment anchors for reading targets;
- search, notes, study, and translations pages;
- local Gemma sentence translation through llama.cpp;
- local-only AI JSONL storage ignored by Git;
- source-light Git/release policy so large primary-source data is not committed.

## Current Daily Workflow

The intended human workflow is:

1. Open `Archive` or `Search`.
2. Open a work page.
3. Read the original source text.
4. Click a sentence.
5. Read translation and commentary in the study panel.
6. Use `Next sentence` to continue.
7. Use `Add note` when a sentence needs a personal research note.
8. Use `Save` when a translation should be kept.
9. Use `Translations` -> `Review (n)` to review generated local AI outputs.
10. Use `Study` as the quiet saved-notes/study-pack view.

The default reader experience should stay quiet. Technical provenance, model hashes, literal glosses, key-term dumps, and cache labels must not compete with the translation and commentary while reading.

## Applied Usability Decisions

### Reading Panel

Status: implemented.

- Work pages use a two-column reading desk on desktop.
- The original source stays on the left.
- The study companion stays beside the text on the right.
- On mobile, the study panel becomes a bottom companion panel.
- Clicking a source sentence starts translation directly.
- Translation and commentary are the first visible result sections.
- `Literal gloss`, `Key terms`, model/runtime metadata, and checksum fields are hidden from the reading card.
- Immediate actions are ordered as `Next sentence`, `Add note`, then `Save`.
- Study-only details are collapsed behind `More`.

### Translation Review

Status: implemented.

- Generated sentence translations use `review_state`.
- The reader can save, reject, regenerate, copy, or draft a note from a translation.
- The `Translations` page gives a review queue through `Review (n)`.
- Redundant status summaries are hidden when every translation is in the same state.
- Reviewed/local AI exports hide runtime-oriented labels and noisy metadata.

### Search

Status: implemented and still open for relevance tuning.

- Search supports corpus/work/variant filters.
- Search results include direct `Read` and `Notes` actions for source results.
- Work, passage, and note result groups are visually separated.
- The visible status line avoids duplicating the rendered result count.
- Further search ranking changes should be driven by collected real study queries, not speculative broad ranking tweaks.

### Notes And Study

Status: implemented.

- Notes are stored locally by corpus/work/target.
- Notes support raw/reviewed workflow, tags, filtering, update, delete, and export.
- Empty states stay quiet and use concise actions.
- `Study` focuses on saved notes and saved translation review links, without repeating zero-count summaries.

### Startup And Local Operation

Status: implemented.

- Daily startup is documented in `docs/local_operator_quickstart.md`.
- `run_reader_with_gemma.ps1` starts or checks the reader and local Gemma sidecar.
- Reader default port: `8793`.
- Local AI sidecar default port: `127.0.0.1:8794`.
- Windows autostart registration and removal scripts are documented.
- Local runtime health can be checked with `scripts/check_local_runtime.py --plain`.

## Current Verification Coverage

The project currently has checks for:

- static routes and representative work pages;
- cross-corpus category pages;
- layout/page-frame contracts;
- visual browser smoke screenshots;
- reader interaction smoke;
- source target and prompt contracts;
- sentence translation contracts;
- AI record JSONL contracts;
- notes contracts;
- search contracts and relevance checks;
- clean-clone/source-light release contracts.

The visual smoke suite now covers category pages for Nietzsche, Bible, Kierkegaard, and Wittgenstein, plus representative reader, search, notes, study, and translation screens.

## Known Deferred Items

These should remain deferred until a human chooses the product direction:

- Final Bible canon-layer taxonomy and deuterocanonical grouping labels.
- Final Kierkegaard text/commentary/textual-account vocabulary.
- Final Wittgenstein normalized/diplomatic/full/index vocabulary and default variant policy.
- A dedicated cache-management page for local Gemma sentence translations.
- Search relevance calibration from a real query set.
- Broader visual identity decisions beyond the current quiet archive frame.

## Product Principle

The archive should feel like a working research desk:

- source text first;
- translation and commentary when requested;
- notes and review tools close at hand;
- technical provenance available through contracts and exports, but not placed in the reader's way.
