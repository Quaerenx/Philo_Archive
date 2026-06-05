# Corpus Schema Contract

This document defines the current common data contract for the Personal Archive of Literature reader site.

The goal is not to erase the differences between Nietzsche, Bible, Kierkegaard, and Wittgenstein. The goal is to give the reader, search, notes, and study layers a stable shared vocabulary.

## Core Terms

- `corpus`: A major collection such as `nietzsche`, `bible`, `kierkegaard`, or `wittgenstein`.
- `work`: The main reading unit inside a corpus. This can be a published work, biblical book/source pair, SKS work, manuscript, source item, or metadata item.
- `variant`: A source or representation of a work, such as text, commentary, textual account, diplomatic transcription, normalized text, source metadata, OSHB, SBLGNT, or LXX.
- `segment`: The smallest stable citation and note target exposed to the site. Examples: Nietzsche section/paragraph, Bible verse, SKS paragraph, Wittgenstein paragraph/block.
- `citation target`: A URL of the form `/work/<corpus_id>/<work_id>#<segment_id>` or `/work/<corpus_id>/<work_id>?variant=<variant_id>#<segment_id>`.

## Metadata File

Each corpus has one metadata file:

```text
reader_site/data/<corpus_id>_metadata.json
```

Required top-level fields:

```json
{
  "schema_version": 1,
  "corpus_id": "nietzsche",
  "generated_at": "2026-06-05T00:00:00",
  "works": {}
}
```

Each `works` entry must use its `work_id` as the object key and include:

```json
{
  "corpus_id": "nietzsche",
  "work_id": "M",
  "title": "Morgenroethe",
  "display_title": "Morgenroethe / Dawn",
  "work_url": "/work/nietzsche/M",
  "language": "de",
  "category_id": "major_published_books",
  "category_title": "Major Published Books",
  "segment_scheme": "section_paragraph",
  "variant_ids": [],
  "concept_ids": [],
  "source_path": "...",
  "source_url": "/source?path=..."
}
```

If a work has source variants, `source_path` and `source_url` may live inside `variants` instead:

```json
{
  "variant_ids": ["text", "commentary"],
  "variants": [
    {
      "variant_id": "text",
      "label": "Text",
      "source_path": "...",
      "source_url": "/source?path=..."
    }
  ]
}
```

## Segment JSONL

Each corpus has one segment file:

```text
reader_site/data/<corpus_id>_segments.jsonl
```

Every line must be a standalone JSON object. Required fields:

```json
{
  "schema_version": 1,
  "corpus_id": "nietzsche",
  "work_id": "M",
  "variant_id": "",
  "segment_id": "p-0001",
  "segment_type": "paragraph",
  "order": 1,
  "label": "Paragraph 1",
  "text_raw": "...",
  "text_preview": "...",
  "url": "/work/nietzsche/M#p-0001"
}
```

Rules:

- `work_id` must exist in the same corpus metadata file.
- `variant_id` must be empty or listed in the work's `variant_ids`.
- The tuple `(work_id, variant_id, segment_id)` must be unique inside the corpus.
- `order` must be a positive integer.
- `url` must point to the matching work page and include a fragment anchor.
- `text_raw` preserves the source-facing text used for reading and search. If a later builder adds normalization, it should add `text_normalized` rather than overwriting `text_raw`.

## Corpus-Specific Segment Schemes

Current `segment_scheme` values:

- `section_paragraph`: Nietzsche published-work pages.
- `chapter_verse`: Bible books and source editions.
- `sks_extract`: Kierkegaard SKS text/commentary/textual-account extracts.
- `transcription_block`: Wittgenstein source, transcription, and metadata blocks.

## Validation

Run:

```powershell
python .\scripts\check_corpus_schema.py
```

This validates all four metadata files and all four segment JSONL files. It is also included in:

```powershell
python .\scripts\rebuild_all.py
```
