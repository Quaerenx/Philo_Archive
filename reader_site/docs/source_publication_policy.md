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

## Local Restore Rule

Full reading/search behavior is restored locally by placing the source corpora under `PHILOSOPHY_CRAWL_ROOT` and running:

```powershell
python .\scripts\rebuild_all.py
```

After local segment files are regenerated, `services/source_targets.py` may compute source-text checksums for bounded reading targets. Those checksums are validation/provenance metadata; the generated segment JSONL files and full source text still stay out of Git.

Run `python .\scripts\check_restore_readiness.py` after restore to confirm that local source folders and generated artifacts are available without publishing them.

The public repository should remain useful without those corpora through source-light checks, documentation, and small metadata files.

## Verification

Run:

```powershell
python .\scripts\check_source_publication_contracts.py
```

This contract checks Git-tracked paths, `.gitignore`, release documentation, metadata JSON shape, and obvious accidental source-text fields.
