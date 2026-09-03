# Source Publication Policy

This repository is a reader application and reproducible local archive scaffold. It is not a public mirror of the collected primary-source corpora.

## Publication Boundary

Git may contain:

- reader-site code, templates, styles, and scripts;
- small metadata/catalog JSON files;
- source paths, source URLs, source labels, and license notes;
- validation contracts and handoff documentation.

Git must not contain:

- local source-corpus folders;
- full primary-source text exports;
- generated segment JSONL files;
- the generated local archive catalog;
- generated search indexes or SQLite databases;
- personal notes;
- generated AI interpretations;
- local visual QA screenshots.

## Metadata Rule

Tracked metadata may describe where a source lives and how it should be cited. It must not duplicate the full source body.

Allowed metadata examples:

- `source_path`
- `source_url`
- `external_source_url`
- `license`
- `text_preview` only when it is a short schema/example preview, not a generated corpus segment file.

Disallowed tracked metadata examples:

- `text_raw`
- `source_text`
- `full_text`
- `body`
- `content`
- large generated JSONL segment rows

## Evaluation Fixture Exception

The sole bounded exception is `reader_site/data/translation_quality_goldset.json`. It may contain manually selected, sentence-sized `source_text` excerpts and candidate/reference translations only for reproducible human evaluation; it is not runtime history and is not evidence that translation quality has already been validated.

The fixture is limited to 64 cases, 1,000 source characters per case, 20,000 source characters in total, 4,000 characters per candidate/reference translation, and 64 KiB for the whole file. It must not contain local paths, prompts, model/runtime identifiers, full segments, or corpus exports. `check_source_publication_contracts.py` enforces these limits.

## Local Restore Rule

Full reading/search behavior is restored locally by placing the source corpora under `PHILOSOPHY_CRAWL_ROOT` and running:

```powershell
python .\scripts\rebuild_all.py
```

After local segment files are regenerated, run `python .\scripts\build_segment_offset_index.py`. `services/source_targets.py` uses the ignored SQLite sidecar to seek directly to one JSONL record and may compute source-text checksums for that bounded reading target. The sidecar, checksums, generated segment JSONL files, and full source text all stay out of Git.

The local `/api/source-target` runtime endpoint may return exact source text for one selected generated segment on the user's machine. It must not include local filesystem paths such as `source_path`, `source_root`, or absolute corpus locations in its response.

Run `python .\scripts\check_restore_readiness.py` after restore to confirm that local source folders and generated artifacts are available without publishing them.

The public repository should remain useful without those corpora through source-light checks, documentation, and small metadata files.

## Verification

Run:

```powershell
python .\scripts\check_source_publication_contracts.py
```

This contract checks Git-tracked paths, `.gitignore`, release documentation, metadata JSON shape, and obvious accidental source-text fields.
