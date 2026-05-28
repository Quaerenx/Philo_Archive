# Personal Archive of Literature Reader Site

Personal archive index for collected primary texts.

## Run

```powershell
python .\reader_site\server.py --port 8787
```

Then open:

```text
http://127.0.0.1:8787
```

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

Nietzsche works are grouped for reading through `data/nietzsche_catalog.json`; the original Markdown export files are left unchanged.

Markdown links open through `/read?path=...` by default so collected texts are presented as reading pages. `/source?path=...` remains available for raw source inspection.

Catalogued works have stable work pages through the common `/work/<corpus_id>/<work_id>` route. Nietzsche keeps URLs such as `/work/nietzsche/M`, with a table of contents plus section and paragraph anchors. Bible books use source-aware IDs such as `/work/bible/oshb.Gen`, with chapter and verse anchors such as `#Gen.1.1`. Kierkegaard and Wittgenstein work pages group related variants behind tabs, for example `/work/kierkegaard/aas` and `/work/wittgenstein/Ms-101`.

Nietzsche research data lives in:

- `data/nietzsche_metadata.json`
- `data/nietzsche_concepts.json`
- `data/nietzsche_notes_schema.json`
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
python .\scripts\build_nietzsche_segments.py
python .\scripts\build_kierkegaard_segments.py
python .\scripts\build_wittgenstein_segments.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
```

Search endpoints and page:

- `/search`
- `/api/search?q=ressentiment&corpus_id=nietzsche`
- `data/search_index.jsonl`
- `data/search_index.sqlite`

The current Nietzsche research model is documented in `docs/nietzsche_research_model.md`.

Cross-corpus standardization review is documented in `docs/corpus_standardization_review.md`.

Expert handoff document: `docs/project_handoff_for_expert.md`.

`/source?path=...` only serves files inside the known corpus roots.
