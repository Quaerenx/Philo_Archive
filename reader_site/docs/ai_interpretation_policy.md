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

The local `POST /api/sentence-translation` endpoint is the first active AI runtime boundary. It accepts only a selected `corpus_id`, `work_id`, `variant_id`, `segment_id`, and `sentence_id`; it does not accept arbitrary user prompt text. The server resolves the sentence from local generated segment records, marks it with `<TARGET_SENTENCE>`, and builds a structural context from the target segment and adjacent paragraphs, verses, or equivalent source units while enforcing a 6,000-character ceiling. Context truncation prefers complete sentences and falls back to a character excerpt only when no complete neighboring sentence fits. It computes separate hashes for the selected segment, sentence, structural context, translator prompt, approved translation policy, translator request contract, and complete quality-pipeline contract before calling a local-only llama.cpp server. Both the reader and llama.cpp server must bind to loopback; unauthenticated LAN exposure is unsupported.

## Record Schema

Future AI records should be stored as JSONL objects under `reader_site/data/ai/`.

Sentence translation records use `record_type: "ai_sentence_translation"`. New records use schema version 5. In addition to the version 4 translator request metadata, they record the quality-pipeline contract, critic and revision prompt metadata, critic audit, automatic `quality_state`, and bounded revision count. Versions 1 through 4 remain readable for compatibility. New records do not store `literal_gloss`, `key_terms`, or a duplicate `interpretation` copy of `commentary`, and the reader UI must not render those legacy fields. These records remain generated study aids, not source text.

Sentence translation review state can be updated locally through `/api/sentence-translations/<record_id>`. Human `review_state` and automated `quality_state` are independent: a critic pass is not a human review, and a user review does not rewrite the critic result. Reviewed records can be exported through `/api/sentence-translations/export`; rejected records and automatically flagged records must not be returned as cached defaults for new reading sessions unless the record was explicitly human-reviewed.

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
reader_site/data/ai/<corpus_id>_sentence_translations.jsonl
reader_site/data/ai/ai_interpretation_index.sqlite
```

These files are intentionally ignored by Git. A public repository should contain the policy, code, templates, and validation scripts, but not the user's generated interpretations.

If the user later wants to version selected AI interpretations, they should be exported through a deliberate review/export command rather than committed from the live local storage directory.

## User-Visible Labels

Every AI surface must clearly label generated material.

Minimum labels:

- "Generated interpretation" for AI output;
- "Generated translation & commentary" for sentence translation output;
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
- all other generation parameters, including the decoding seed and token limit;
- `generated_at`;
- exact source target URLs;
- `source_text_sha256`;
- the exact structural-context hash and ordered context segment hashes for sentence translation;
- the enforced response-schema name and approved translation-policy hash.
- a request-contract hash that covers the translator prompt, model identity, generation parameters, and response schema;
- a pipeline-contract hash that additionally covers the critic and revision templates, parameters, schemas, version, and maximum revision count.

If local Gemma is used, `model_version` includes the model tag and runtime identifier. The bundled launcher computes and caches a SHA-256 for the configured GGUF file and exposes it to new translation records as `model_file_sha256`; direct server starts may leave that field empty unless `PHILO_GEMMA_MODEL_SHA256` is set.

The tracked prompt template registry lives in `reader_site/data/ai_prompt_templates.json`. The current defaults are `segment_interpretation_v2` and `sentence_translation_study_v3`; the quality stages use `sentence_translation_critic_v1` and `sentence_translation_revision_v1`. The interpretation prompt labels direct textual claims separately from reasoned inference. The translation prompt keeps the Korean translation free of commentary, preserves logical relations, morphology, word families, imagery, unusual wording, and meaningful ambiguity before naturalness, and forbids unsupported technical, legal, theological, or philosophical substitution. Source excerpts are quoted data rather than instructions. Linguistic knowledge may help parse the supplied wording, but outside biography, doctrine, background facts, and prior translations may not be introduced as evidence.

Every new draft receives a fresh critic request containing only the approved policy, source context, and draft translation; translator commentary is deliberately absent. A `pass` result is saved without revision. Minor-only issues are saved as `needs_human_review` without automatic rewriting. Any major issue permits exactly one schema-constrained revision followed by one final critic request. The system never enters an open-ended repair loop. Critic or revision failures are preserved explicitly as `critic_error` with a caution instead of being represented as a pass.

Human-approved work terminology and style decisions live separately in `reader_site/data/translation_profiles.json`. The application only reads entries whose `approval_state` is `approved`; it has no code path that automatically accumulates model suggestions into this registry. An empty registry means that the model must not invent a fixed work-level terminology rule.

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

The bounded sentence-translation path now implements local model invocation, local JSONL storage, visible generated-output labels, review/export behavior, and runtime checks. The general segment-interpretation route remains unimplemented: `services/interpretation_prompts.py` and its contracts are still a model-free provenance foundation, not an active `/api/interpret` endpoint.
