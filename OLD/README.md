# OLD Archive

Archived on 2026-08-08 during a repository-wide structure and reference review.

The archive preserves useful history without presenting superseded material as current instructions. Paths below retain their original repository-relative layout under `OLD/`, so a file can be restored by moving it back to the same path without the `OLD/` prefix.

## Tracked Historical Material

`OLD/reader_site/docs/` contains:

- completed planning and implementation records: `corpus_standardization_review.md`, `upgrade_execution_review.md`, `upgrade_completion_audit.md`, and `codebase_review_2026-07-30.md`;
- superseded handoff/product documents: `project_handoff_for_expert.md`, `project_usability_upgrade_review_2026-06-17.md`, and `nietzsche_research_model.md`;
- already-executed task prompts and their dated result: `next_reader_work_modularization_prompt_ko.md`, `next_search_quality_prompt_ko.md`, and `search_quality_calibration_2026-07-30.md`;
- the 2026-07-30 security revalidation prompt and receipts, which describe a pre-publication working tree and therefore are historical rather than current release instructions.

`OLD/reader_site/RESEARCH_UPGRADE_ROADMAP.md` is the original May 2026 roadmap. Its implemented phases, legacy file names, and known replacement characters make it unsuitable as a current plan.

`OLD/reader_site/data/` contains the one-time Nietzsche encoding receipt and the retired Nietzsche-only `author`-based note schema. Current notes use the cross-corpus service contract.

`OLD/reader_site/assets/nietzsche-1882.jpg` is an unreferenced portrait source superseded by the active `nietzsche-header-left.png` asset.

## Local-Only Material

`OLD/local-only/` is intentionally ignored by Git. It contains regenerable Python bytecode caches, prior visual-QA captures, five unreferenced legacy runtime log/summary files, and an empty extracted-package directory. Personal notes, generated AI translations, source corpora, search indexes, current runtime state, and acquisition manifests were not moved.

For active documentation, use [`reader_site/docs/README.md`](../reader_site/docs/README.md).
