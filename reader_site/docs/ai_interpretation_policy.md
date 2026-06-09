# AI Interpretation Provenance Policy

Date: 2026-06-05

This policy defines the minimum provenance and UI rules for any future Gemma/AI interpretation layer in the Personal Archive of Literature reader site.

The current site is a source reader, search index, citation tool, and personal-note workspace. AI interpretation must be an optional layer on top of that foundation. It must never replace, rewrite, or silently blend into original source text.

## Non-Replacement Rule

AI output is not source text.

AI output must not:

- overwrite `text_raw`, `text_preview`, source Markdown, source JSON, or source XML-derived records;
- be stored inside corpus metadata files as if it were catalog metadata;
- be rendered in the reader body without a visible generated-interpretation label;
- appear in citation copy as if it were the primary source;
- be used to fill missing source text, missing verses, missing paragraphs, or uncertain textual witnesses.

AI output may:

- summarize a selected source segment;
- explain vocabulary, context, structure, or philosophical/theological stakes;
- compare selected segments when all cited targets are explicit;
- help draft study prompts or reading questions;
- be promoted into a personal note only through a user-visible action.

## Source Boundary

Every AI interpretation must be tied to explicit source targets.

Allowed targets:

- a single work URL: `/work/<corpus_id>/<work_id>`;
- a single segment URL: `/work/<corpus_id>/<work_id>#<segment_id>`;
- a variant segment URL: `/work/<corpus_id>/<work_id>?variant=<variant_id>#<segment_id>`;
- a bounded list of segment URLs from the same request.

The AI request must use source text gathered from the current corpus segment records or rendered source records. It must not use hidden browser text, unbounded source folders, unrelated local files, personal notes, or prior generated outputs unless the user explicitly includes them.

The local `GET /api/source-target` endpoint is allowed before any AI runtime is enabled. It returns a bounded source target bundle for a single generated segment record: target URL, label, exact source text, source text preview, character count, and `source_text_sha256`. This endpoint does not call a model, does not store generated output, and must not be treated as an AI interpretation route.

## Record Schema

Future AI records should be stored as JSONL objects under `reader_site/data/ai/`.

Required fields:

```json
{
  "schema_version": 1,
  "record_type": "ai_interpretation",
  "id": "uuid",
  "created_at": "2026-06-05T00:00:00",
  "generated_at": "2026-06-05T00:00:00",
  "corpus_id": "nietzsche",
  "work_id": "M",
  "variant_id": "",
  "target_id": "p-0001",
  "target_url": "/work/nietzsche/M#p-0001",
  "source_text_sha256": "hex sha256 of exact source text sent to model",
  "source_text_excerpt": "short source excerpt shown to the user",
  "source_language": "de",
  "model_provider": "local",
  "model_name": "gemma",
  "model_version": "exact local model tag or file hash",
  "prompt_template_id": "segment_interpretation_v1",
  "prompt_sha256": "hex sha256 of full prompt text",
  "temperature": 0.2,
  "interpretation": "generated explanation text",
  "citations": [
    {
      "target_url": "/work/nietzsche/M#p-0001",
      "label": "M / Paragraph 1",
      "source_text_sha256": "hex sha256"
    }
  ],
  "review_state": "generated"
}
```

Allowed `review_state` values:

- `generated`: produced by a model and not reviewed;
- `reviewed`: user has reviewed it for personal study;
- `rejected`: user chose not to keep it.

If a generated interpretation is converted into a personal note, the note should record its AI origin, model name, and source `target_url`. The original AI record should remain separate.

## Storage Policy

Generated AI output is local state.

Default local paths:

```text
reader_site/data/ai/<corpus_id>_interpretations.jsonl
reader_site/data/ai/ai_interpretation_index.sqlite
```

These files are intentionally ignored by Git. A public repository should contain the policy, code, templates, and validation scripts, but not the user's generated interpretations.

If the user later wants to version selected AI interpretations, they should be exported through a deliberate review/export command rather than committed from the live local storage directory.

## User-Visible Labels

Every AI surface must clearly label generated material.

Minimum labels:

- "Generated interpretation" for AI output;
- "Original source" for source text excerpts;
- "Personal note" for user notes;
- model name/version visible in details or metadata;
- source target URL visible or copyable.

AI output must be visually separated from:

- the main reader body;
- source-mode output;
- personal notes;
- citation preview.

## Prompt And Model Metadata

Every saved AI record must preserve:

- `model_provider`;
- `model_name`;
- `model_version`;
- `prompt_template_id`;
- `prompt_sha256`;
- `temperature`;
- `generated_at`;
- exact source target URLs;
- `source_text_sha256`.

If local Gemma is used, `model_version` should include the model tag and, when available, the local model file hash or runtime identifier.

The tracked prompt template registry lives in `reader_site/data/ai_prompt_templates.json`. The current default template is `segment_interpretation_v1`.

Prompt rendering is deterministic and model-free in `reader_site/services/interpretation_prompts.py`: a selected `source_target_bundle` is rendered into an `interpretation_prompt_bundle` with `prompt_template_id`, `prompt_sha256`, `source_text_sha256`, `target_url`, and the full prompt text. This builder does not call Gemma, does not store generated output, and does not expose an interpretation API route.

Validate the prompt boundary with:

```powershell
python .\scripts\check_prompt_template_contracts.py
python .\scripts\check_prompt_template_contracts.py --with-source-targets
```

The first command is source-light and should pass in a clean clone. The second command uses restored segment artifacts to prove that real selected source text renders into reproducible prompt checksums.

## Privacy Boundary

By default, an AI interpretation request may use:

- selected source text;
- public metadata for the selected work;
- user-selected notes only when explicitly requested.

It must not automatically send:

- all personal notes;
- entire source corpora;
- filesystem paths outside the selected source target;
- private `.env` values;
- local artifact manifests with machine paths;
- browser history or unrelated local files.

## Pre-Implementation Gates

Before implementing an AI endpoint or UI control, complete these gates:

1. Define the exact prompt template and save a `prompt_template_id`.
2. Implement source target resolution from existing segment/work data in `services/source_targets.py`.
3. Compute `source_text_sha256` before model invocation.
4. Store generated output in `reader_site/data/ai/`, not in corpus metadata or source folders.
5. Run `python .\scripts\check_source_target_contracts.py` after local segment artifacts exist.
6. Run `python .\scripts\check_ai_records_contracts.py` against generated AI JSONL records.
7. Add visible UI labels that distinguish original source, personal notes, and generated interpretation.
8. Verify release checks still exclude generated AI output.

Gates 1-3 now have pre-AI code-level contracts through `data/ai_prompt_templates.json`, `services/source_targets.py`, `services/interpretation_prompts.py`, `check_source_target_contracts.py`, and `check_prompt_template_contracts.py`. Until storage, UI labels, review/export behavior, and model-runtime checks are complete, the site should keep AI/Gemma interpretation as a documented future layer, not an active reader feature.
