# Personal Archive of Literature

Local reader site for collected primary texts.

The Git repository stores the reader application, metadata builders, templates, docs, and small metadata files. It does not store the large source corpora or large generated search artifacts.

## Expected Local Layout

By default the app expects the source corpus folders next to `reader_site`:

```text
philosophy_crawl/
  reader_site/
  니체_원서수집/
  성경_원서수집/
  키르케고르_원서수집/
  비트겐슈타인_원서수집/
```

If the source folders live somewhere else, set `PHILOSOPHY_CRAWL_ROOT` to the directory that contains those four source folders.

```powershell
$env:PHILOSOPHY_CRAWL_ROOT="D:\archives\philosophy_crawl"
```

## Run

```powershell
cd .\reader_site
python .\server.py --port 8787
```

Open:

```text
http://127.0.0.1:8787/
```

## Regenerate Local Artifacts

Run these after cloning on another local machine with the source corpora available:

```powershell
cd .\reader_site
python .\scripts\build_nietzsche_metadata.py
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
python .\scripts\build_kierkegaard_metadata.py
python .\scripts\build_wittgenstein_metadata.py
python .\scripts\build_nietzsche_segments.py
python .\scripts\build_kierkegaard_segments.py
python .\scripts\build_wittgenstein_segments.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
```

Large generated files are ignored by Git:

- `reader_site/data/*_segments.jsonl`
- `reader_site/data/search_index.jsonl`
- `reader_site/data/search_index.sqlite`
- personal notes under `reader_site/data/notes/*.jsonl`
