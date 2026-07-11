# Philo Archive v1.0 Release Baseline

## 0. Baseline decision

| Item | Result |
|---|---|
| Observation window | 2026-07-11 23:01-23:12 KST |
| Phase 0 result | GO - the release baseline is captured |
| Current v1 release readiness | NO-GO |
| Canonical repository | `C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl` |
| Production code changed by this phase | No |
| Repository file created by this phase | `reader_site/docs/release_v1_baseline.md` only |
| Next permitted phase | Phase 1 preservation and verified backup only |

Phase 0 is complete because the canonical repository, full dirty/untracked state, runtime topology, local data inventory, documentation drift, and prioritized release risks are recorded. The application is not ready to release. The Phase 0 `GO` means that Phase 1 may begin; it does not mean that v1 may be deployed.

This document records the pre-document working-tree snapshot. After this document is added, it is expected to appear as one additional untracked file until Phase 1 deliberately preserves the complete worktree.

## 1. Scope and method

This phase was read-only except for creating this baseline document. No application source, corpus, personal research record, database, service, scheduled task, firewall rule, Git ref, commit, tag, or remote branch was changed.

Evidence was collected using:

- read-only Git status/ref/remote/worktree commands;
- remote ref readback from the configured GitHub remote;
- filesystem inventory and JSON/JSONL validation;
- immutable/read-only SQLite queries and `PRAGMA quick_check`;
- process, listener, scheduled-task, proxy, and firewall readback;
- HTTP GET probes of the already-running Reader, health endpoint, Gemma model endpoint, and existing proxy routes;
- exact source and documentation searches for old ports and paths.

No rebuild, full release suite, mutation test, note write, AI generation, process restart, or deployment action was performed.

## 2. Canonical repository and Git baseline

### 2.1 Identity

| Item | Value |
|---|---|
| Repository | `C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl` |
| Remote | `https://github.com/Quaerenx/Philo_Archive.git` |
| Branch | `main` tracking `origin/main` |
| Worktrees | One, at the canonical repository |
| Local HEAD | `791bb0b2d26735bd2be15dce92a8a395a7d4e650` - `Clarify study records language` |
| Remote `main` | `07142a71e79f52a9d9d657941898aae88387d552` - `Clarify selected source status` |
| Ahead / behind | 461 / 0 |
| Latest release tag | `v0.1.19`, pointing to remote `main`, 461 commits behind local HEAD |
| Current description | `v0.1.19-461-g791bb0b-dirty` |

The remote also contains `codex/reader-site-upgrade` at `c86503a`. It is diverged from current `main` and has 24 commits not in `main`; its historical or recovery role is not yet documented.

### 2.2 Pre-document dirty state

- Staged: 0
- Modified tracked files: 13
- Untracked files: 7
- Deleted or renamed files: 0
- `HEAD` to tracked worktree: 13 files, `+1,206/-182`
- `origin/main` to local HEAD: 52 files, `+10,078/-2,074`
- `origin/main` to current tracked worktree: 57 files, `+11,281/-2,253`
- `git diff --check`: passed

Modified tracked files:

```text
reader_site/corpora/catalogs.py
reader_site/docs/api_reference.md
reader_site/run_reader_with_gemma.ps1
reader_site/runtime_status.py
reader_site/scripts/build_search_db.py
reader_site/scripts/check_api_contracts.py
reader_site/scripts/check_search_contracts.py
reader_site/scripts/check_sentence_translation_contracts.py
reader_site/scripts/check_source_target_contracts.py
reader_site/server.py
reader_site/services/search.py
reader_site/services/sentence_translations.py
reader_site/services/source_targets.py
```

Untracked files:

```text
reader_site/scripts/check_live_ui_smoke.py
reader_site/scripts/check_runtime_metrics_contracts.py
reader_site/services/bounded_cache.py
reader_site/services/gemma_response_cache.py
reader_site/services/gemma_runtime.py
reader_site/services/runtime_metrics.py
reader_site/start-server.ps1
```

All 20 pre-document changes are unstaged. Their last source-file modifications were on 2026-07-07 or 2026-07-10. Git status was unchanged during the observation window, and `.git/index.lock` was absent.

### 2.3 Untracked hard dependencies

Four untracked modules are mandatory imports of the currently modified runtime:

| Untracked module | Current importers |
|---|---|
| `services/bounded_cache.py` | `corpora/catalogs.py`, `services/search.py`, `services/source_targets.py` |
| `services/runtime_metrics.py` | `runtime_status.py`, `services/search.py`, `services/sentence_translations.py` |
| `services/gemma_runtime.py` | `runtime_status.py`, `services/sentence_translations.py`, translation contracts |
| `services/gemma_response_cache.py` | `services/sentence_translations.py`, translation contracts |

Committing only the 13 modified tracked files would produce a clean clone that fails at server import time. `scripts/check_clean_clone_contracts.py::REQUIRED_FILES` does not list these four modules, the two new check scripts, or `start-server.ps1`, so the current clean-clone guard can miss this failure.

### 2.4 Ignored state

`git ls-files --others -i --exclude-standard` reports 18,601 ignored paths.

| Category | Count |
|---|---:|
| Wittgenstein source collection | 15,537 |
| Kierkegaard source collection | 2,581 |
| Bible source collection | 176 Git-ignored paths |
| Nietzsche source collection | 96 |
| Python cache files | 129 |
| Visual QA | 59 |
| Runtime-local files | 11 |
| AI JSONL | 4 |
| Corpus segment JSONL | 4 |
| Search JSONL/SQLite | 2 |
| Notes JSONL | 1 |
| Local artifact manifest | 1 |

The ignore policy correctly keeps large or personal data out of the public repository. It also means that Git remote backup does not protect the source corpora, notes, AI records, search artifacts, runtime cache, or metrics.

## 3. Runtime baseline

### 3.1 Active listeners and probes

| Component | Binding | Process/state | Probe |
|---|---|---|---|
| Reader | `127.0.0.1:18170` | Python, running from the canonical `reader_site` launcher | `/` 200; `/api/health` 200 |
| Gemma | `127.0.0.1:8794` | `llama-server`, one model loaded | `/v1/models` 200 |
| Shared Caddy proxy | `0.0.0.0:8088` | Caddy, running | root and five configured routes 200 |
| Old Reader port | `8793` | No listener | Connection refused |
| Separate Chat Wiki port | `18180` | No listener | Connection refused; not a Philo blocker |

Reader health currently reports:

- `status=ok`, no reported issues;
- four source roots and primary outputs present;
- 225,442 search records with FTS5;
- Gemma reachable;
- Gemma concurrency 1, queue timeout 8 seconds, request timeout 180 seconds.

This health result describes the running dirty worktree; it is not release readiness evidence.

### 3.2 Scheduled tasks and network boundary

- `PhiloArchiveReaderGemma` is present and running. It launches `reader_site/run_reader_with_gemma.ps1` from the canonical repository. Its current-running result code is normal.
- `CodexLocalProxy-Caddy` is present and its listener is healthy. Its latest task result is `0x800710E0` even while the process is running; likely repeated-trigger/IgnoreNew behavior, but this is an observability mismatch.
- Both tasks start in the user logon context; neither is a pre-login Windows service.
- Reader and Gemma are loopback-only and are not directly reachable from the LAN.
- The firewall has a narrow TCP 8088 rule for the approved LAN host; broader Caddy rules are disabled.
- Caddy currently routes `/diet`, `/vertica`, `/workboard`, `/hero`, and `/beaconhub`. It has no Philo or Gemma route.

For a local-only v1, the current Philo network boundary is acceptable. If LAN use is part of v1, an authenticated or explicitly allow-listed Philo route remains a release requirement. Gemma should remain internal-only.

## 4. Corpus and artifact baseline

### 4.1 Source collections

The following recursive disk inventory includes hidden files where present.

| Corpus | Files | Bytes | GiB | Latest source-area modification |
|---|---:|---:|---:|---|
| Nietzsche | 96 | 25,831,061 | 0.024 | 2026-05-26 KST |
| Bible | 696 | 1,274,343,220 | 1.187 | 2026-05-27 KST |
| Kierkegaard | 2,581 | 675,639,676 | 0.629 | 2026-05-26 KST |
| Wittgenstein | 15,537 | 12,504,261,868 | 11.646 | 2026-05-27 KST |
| Total | 18,910 | 14,480,075,825 | 13.486 | - |

No external backup-and-restore evidence for this 13.486 GiB source set was found in the repository.

### 4.2 Metadata and segment artifacts

| Corpus | Works | Variants / edition references | Segments | Segment bytes |
|---|---:|---:|---:|---:|
| Nietzsche | 33 | 0 | 14,227 | 12,564,862 |
| Bible | 121 | 121 variant references / 3 edition IDs | 60,180 | 56,310,851 |
| Kierkegaard | 211 | 630 | 25,359 | 51,442,171 |
| Wittgenstein | 202 | 1,227 | 125,676 | 263,015,518 |
| Total | 567 | - | 225,442 | 383,333,402 |

Read-only validation found:

- valid JSON in all four segment files;
- zero blank or malformed rows;
- zero missing segment IDs;
- zero duplicates for `(corpus_id, work_id, variant_id, segment_id)`;
- all metadata-referenced source paths present under the canonical repository.

The health summary reports Bible variants as zero because it counts `variants` but not Bible `variant_ids`. This is an observability defect, not evidence that the Bible editions are missing.

### 4.3 Search artifacts

| Artifact | Size | Records | Modified |
|---|---:|---:|---|
| `search_index.jsonl` | 349,076,038 B | 225,442 | 2026-06-05 KST |
| `search_index.sqlite` | 555,675,648 B | 225,442 search rows and 225,442 FTS rows | 2026-07-07 KST |

The SQLite database passed immutable read-only `PRAGMA quick_check`. JSONL and SQLite counts match for every corpus.

### 4.4 Notes, AI, cache, and metrics

- Notes: `nietzsche_notes.jsonl` is 0 bytes and 0 rows; no other notes file currently exists. There is effectively no persisted note usage.
- AI records: 103 total (`Bible 42`, `Kierkegaard 2`, `Nietzsche 54`, `Wittgenstein 5`). All are `generated`; reviewed/rejected counts are zero. All rows parse and contain the required core fields.
- AI schemas 1 and 2 coexist. Under the runtime cache identity, Nietzsche contains six duplicate records, a concrete signal consistent with the known non-atomic append risk.
- Gemma response cache: 16,384 bytes, two entries, read-only `quick_check=ok`.
- Runtime metrics: 172 valid rows. They include 155 search events and test-only corpus values, so this file is contract-test-contaminated rather than reliable production telemetry.

### 4.5 Stale or partial verification evidence

- `data/artifact_manifest.local.json` was generated on 2026-06-09. Its stored sizes for `nietzsche_concepts.json` and `search_index.sqlite` do not match current files. It cannot be used as a v1 release manifest.
- Kierkegaard's verification covers the complete 1,906-row download manifest; six source URLs are known 404s, while locally present files passed missing/checksum/empty checks.
- Wittgenstein's current download manifest has 10,101 rows and 2,937 raw JPEGs, but the current verification report covers only 4,931 rows. Its `ok` flag does not prove the current full manifest. Full facsimile acquisition must not be claimed as complete.

## 5. Documentation and path drift

### 5.1 Reader port drift

Current executable defaults:

- `server.py`: `18170`
- `run_reader_with_gemma.ps1`: `18170`
- `start-server.ps1`: loopback `18170`
- Gemma: loopback `8794`

The old Reader port `8793` still appears in 42 operational documentation/code lines across 12 files. Important affected files include:

- root `README.md`;
- `reader_site/README.md`;
- `docs/local_operator_quickstart.md`;
- `docs/local_windows_autostart.md`;
- `docs/clean_clone_reproducibility.md`;
- `docs/release_handoff.md`;
- `docs/nietzsche_research_model.md`;
- `docs/project_handoff_for_expert.md`;
- `docs/project_usability_upgrade_review_2026-06-17.md`;
- `docs/upgrade_execution_review.md`;
- `scripts/check_live_ui_smoke.py`;
- `scripts/check_local_runtime.py`.

`scripts/check_live_ui_smoke.py` explicitly requires `http://127.0.0.1:8793`, so it cannot validate the current default service without an override and code change. `docs/local_operator_quickstart.md` still instructs users to expose `0.0.0.0:8793`, which contradicts the current loopback-only design.

No Markdown document currently names the new Reader port `18170`. Gemma port `8794` is consistent.

### 5.2 Old or host-specific paths

- `docs/clean_clone_reproducibility.md` and `docs/upgrade_completion_audit.md` use `C:\Users\PP\Documents\crawl` as a clone parent. That path is a separate no-commit workspace and must not be treated as Philo.
- The Bible extraction report and its validation script still contain `C:\Users\PP\Documents\crawl\bible-corpus`, a stale pre-move location.
- The Reader launcher/README contains a host-specific default model path. This works on the current PC but is not portable release configuration.
- No `mother-dashboard`, BeaconHub, or `reader-site-qa` reference was found in the active Reader README/docs/scripts set.

## 6. Concurrent work assessment

- Git status was identical at the beginning and end of the Git observation interval.
- `.git/index.lock` was absent.
- Source file modification times did not change during this audit.
- The only persistent processes explicitly tied to the canonical repository are the scheduled Philo Reader/Gemma launcher and its children. They write only ignored runtime logs during normal operation.
- No unrelated active Codex thread with the canonical repository as its working directory was found. Other active user threads target different projects.
- The baseline audit team itself performed read-only inspection. The parent task is the only intentional writer, and it creates this document only.

This evidence supports “no concurrent unrelated writer observed,” not a proof that no future writer can start.

## 7. Release risks

### P0 - release blockers

1. **461 local commits are absent from the remote.** Most post-`v0.1.19` application work exists only in this local repository.
2. **Four current runtime hard dependencies are untracked.** A partial commit or clean clone can fail immediately at import time.
3. **Git-excluded source and research data have no verified external backup/restore evidence.** This includes 13.486 GiB of source material, AI records, notes, and generated search artifacts.
4. **Mutable AI/notes storage is not proven concurrency-safe.** Six duplicate AI cache identities already exist, and current JSONL append/rewrite paths are not atomic. This must be resolved before v1 enables trusted mutable research workflows.

### P1 - must resolve before release candidate

1. The 20-file dirty runtime change mixes search, Gemma, cache, metrics, tests, and port migration without a safe commit boundary.
2. Clean-clone `REQUIRED_FILES` does not cover the new hard dependencies and can return a false negative.
3. Runtime defaults use 18170 while operator docs and live checks still use or require 8793; one operator guide still recommends direct LAN exposure.
4. The current service is running successfully from a dirty worktree, not from an identifiable release commit.
5. The local artifact manifest is stale and cannot attest to current search or concept artifacts.
6. Wittgenstein's verification report covers only part of the current manifest.
7. Runtime metrics are contaminated by contract-test traffic.
8. If LAN use is part of v1, there is no Philo proxy route or finalized authentication/allow-list policy yet. If v1 is local-only, this item is not a blocker.
9. Cache and JSONL code still has known thread-safety and transient-error handling risks that are not covered by release-level concurrency tests.

### P2 - cleanup or explicit documentation

1. All 103 AI records remain unreviewed and notes contain zero records, so the complete study loop has not been demonstrated through real persisted use.
2. AI record schemas 1 and 2 coexist without a documented migration policy.
3. Bible variants are incorrectly reported as zero in runtime health.
4. The Caddy task's latest result code looks erroneous while the listener is healthy; operator status interpretation should be documented or corrected.
5. The divergent remote upgrade branch and the meaning of the 20 rapid `v0.1.x` tags are undocumented.
6. The default model path is host-specific.
7. Historical handoff/review documents are not consistently marked superseded, so current and historical instructions are mixed.

## 8. Gate and rollback

### Phase 0 gate

**GO.** The baseline completion criteria are met:

- one canonical repository is confirmed;
- the complete pre-document modified/untracked list is preserved;
- listeners, processes, scheduled tasks, proxy routes, and network boundary are identified;
- source, metadata, segments, search, notes, AI, cache, and metrics are inventoried;
- port/path drift is enumerated;
- P0/P1/P2 risks are prioritized;
- production code was not changed.

### v1 release gate

**NO-GO.** No release branch, commit, push, tag, migration, or deployment should be performed from this state without Phase 1 preservation.

### Next phase entry

Phase 1 may begin, limited to preservation and verified backup. It must preserve both the existing 461-commit HEAD and all intended dirty/untracked code without force-push, history rewriting, corpus publication, or personal-data publication.

### Rollback for this phase

This phase changed no production code or external state. To roll back Phase 0 documentation only, remove `reader_site/docs/release_v1_baseline.md`. Do not alter any other pre-existing dirty or untracked file.
