# Clean Clone Reproducibility

The public repository is intentionally source-light.

A clean clone should contain:

- reader-site application code;
- scripts, templates, CSS, and docs;
- small metadata/catalog files;
- validation contracts.
- the source-light GitHub Actions workflow.

A clean clone should not contain:

- the four local source-corpus folders;
- generated `*_segments.jsonl` files;
- generated search indexes or SQLite databases;
- personal notes;
- generated AI interpretations;
- local visual QA screenshots.

## Source-Light Checks

These checks should pass in a clean clone before source corpora are restored:

```powershell
cd .\reader_site
python .\scripts\check_clean_clone_contracts.py
python .\scripts\check_ci_contracts.py
python .\scripts\check_encoding_contracts.py
python .\scripts\check_path_contracts.py
python .\scripts\check_source_publication_contracts.py
python .\scripts\check_release_contracts.py
python .\scripts\check_layout_contracts.py
python .\scripts\check_server_boundary.py
python .\scripts\check_provenance_contracts.py
python .\scripts\check_ai_records_contracts.py
```

`check_clean_clone_contracts.py --run-source-light-checks` runs the source-light command set from one entrypoint.

The contract also guards against documentation drift:

- README rebuild command lists must match the actual `scripts/rebuild_all.py` order;
- source-root names in restore docs must match `path_config.py`;
- source-light checks must not call source-heavy rebuild, search, notes, static route, or full-restore checks.

## Local Clone Smoke

After committing local changes, run a real local clone smoke test:

```powershell
cd .\reader_site
python .\scripts\check_clean_clone_contracts.py --clone-smoke --clone-parent C:\Users\PP\Documents\crawl
```

The script clones the current Git branch into an ignored temporary folder, points `PHILOSOPHY_CRAWL_ROOT` at an empty directory, and verifies that source-light checks still pass without local corpora.

## Full Restore

To restore full reading/search behavior on another machine:

```powershell
git clone https://github.com/Quaerenx/Philo_Archive.git
cd .\Philo_Archive\reader_site
$env:PHILOSOPHY_CRAWL_ROOT="D:\archives\philosophy_crawl"
python .\scripts\rebuild_all.py
python .\server.py --port 8787
```

`PHILOSOPHY_CRAWL_ROOT` must contain these source folders:

- `니체_원서수집`
- `비트겐슈타인_원서수집`
- `성경_원서수집`
- `키르케고르_원서수집`

Without those folders, the source-light checks still prove that the clone is structurally valid, but full corpus routes, generated segments, and search indexes cannot be regenerated.

## GitHub Actions

Pull requests run the source-light subset through:

```text
.github/workflows/reader-site-source-light.yml
```

The workflow uses the official checkout and setup-python actions, points `PHILOSOPHY_CRAWL_ROOT` at an empty temporary directory, and runs:

```powershell
python scripts/check_clean_clone_contracts.py --run-source-light-checks
```

Full corpus rebuild checks remain local because the public repository intentionally excludes the source corpora and generated search/segment artifacts.

After a full local restore, also run:

```powershell
python .\scripts\check_restore_readiness.py
python .\scripts\check_source_target_contracts.py
python .\scripts\check_note_target_integrity.py
```

These checks intentionally are not part of the source-light CI subset because they require restored source folders and regenerated local artifacts. `check_restore_readiness.py` verifies source roots, primary output folders, metadata, segment artifacts, and search records. `check_source_target_contracts.py` proves that selected reading targets can be resolved back to exact `text_raw` records and stable SHA-256 source-text checksums. `check_note_target_integrity.py` verifies that local personal notes still point to existing works and generated segment targets.

The workflow shape is checked by:

```powershell
python .\scripts\check_ci_contracts.py
```
