# Reader Site API Reference

작성일: 2026-06-04

이 문서는 `reader_site/server.py`가 제공하는 주요 JSON API의 현재 응답 구조를 기록한다. 응답은 로컬 원천 코퍼스와 생성된 metadata/search artifact의 상태에 따라 값이 달라질 수 있지만, 아래 필드 구조는 프론트엔드와 진단 도구가 기대하는 계약이다.

## 공통 원칙

- 모든 JSON 응답은 UTF-8이다.
- 큰 원문 데이터 자체는 API 응답에 포함하지 않는다.
- 경로 필드는 가능한 한 `reader_site` 또는 corpus root 기준 상대 경로로 표시한다.
- `exists`, `source_root_exists`, `primary_output_exists`, `fts5`는 로컬 실행 환경의 현재 상태를 나타낸다.
- 시간 필드는 ISO 형식 문자열이다.

## `GET /api/archive`

This compatible endpoint remains the full archive index for `/category/<corpus_id>` and existing archive consumers. The response may come from the versioned local archive catalog when its input signature matches; a missing, corrupt, or stale catalog is rebuilt safely in memory.

`/category/<corpus_id>` 페이지와 기존 archive 소비자가 사용하는 전체 index이다.

최상위 필드:

```json
{
  "generated_at": "2026-06-04T12:00:00",
  "corpora": []
}
```

`corpora[]`:

```json
{
  "id": "nietzsche",
  "title": "니체",
  "subtitle": "eKGWB markdown exports, grouped for reading",
  "counts": {
    "files": 91,
    "links": 91,
    "bytes": 18729013
  },
  "links": [],
  "sections": []
}
```

`sections[]`:

```json
{
  "title": "주요 발간 저작",
  "meta": "optional section description",
  "count": 13,
  "links": []
}
```

`links[]`:

```json
{
  "label": "Morgenröthe",
  "display_title": "Morgenröthe / 아침놀",
  "href": "/work/nietzsche/M",
  "source_href": "/source?path=...",
  "path": "니체_원서수집/nietzsche/nietzsche/output/works/M.md",
  "meta": "1881 · 아침놀",
  "work_id": "M"
}
```

Notes:

- `links` at corpus level is a short preview subset.
- `sections[].links` is the authoritative category listing.
- `href` may point to `/work/...` for catalogued works or `/read?path=...` for raw Markdown-style reading pages.
- `source_href` points to the raw source viewer when available.
- `display_title` is the stable reader-facing title used by homepage search and reading recommendations.

## `GET /api/archive/titles?q=<query>&limit=8`

홈의 작품명 자동완성용 경량 API이다. 전체 `/api/archive`를 브라우저로 내려받지 않고 제목과 한국어 별칭만 검색한다. `limit`은 1부터 25까지이며 기본값은 8이다.

```json
{
  "schema_version": 2,
  "query": "아침",
  "count": 1,
  "results": [
    {
      "corpus_id": "nietzsche",
      "corpus_title": "니체",
      "section_title": "주요 발간 저작",
      "work_id": "M",
      "href": "/work/nietzsche/M",
      "display_title": "Morgenröthe / 아침놀"
    }
  ]
}
```

같은 제목이 여러 판본에 존재하면 `section_title`로 출처를 구분한다. 원본 경로나 전체 archive 메타데이터는 이 응답에 포함하지 않는다. 자동완성은 마지막으로 구성된 메모리 제목 index를 사용하며, 입력할 때마다 archive 원본 트리를 재검사하지 않는다.

홈의 제목 자동완성과 `/search`의 본문 FTS는 의도적으로 분리한다. 제목 자동완성은 짧은 동기식 탐색을 유지하고, 본문 검색이 필요하면 현재 검색어를 `/search?q=...`로 그대로 전달한다. 두 결과를 한 목록으로 합치는 방식은 본문 검색의 지연·필터·순위 정책을 함께 설계할 때 다시 검토한다.

## `GET /api/archive/summary`

The home page uses this lightweight response for the four corpus links. Title autocomplete uses `/api/archive/titles` instead of downloading every section and work link:

```json
{
  "schema_version": 2,
  "generated_at": "2026-07-30T12:00:00",
  "corpora": [
    {
      "id": "nietzsche",
      "title": "Nietzsche",
      "subtitle": "eKGWB markdown exports, grouped for reading"
    }
  ]
}
```

Each `corpora[]` entry contains only `id`, `title`, and `subtitle`. Use `/api/archive` when counts, sections, or work links are required.

## `GET /api/health`

The HTTP health response is intentionally redacted. It contains readiness fields only; absolute paths, local model names, personal-note state, raw backend errors, byte counts, timestamps, and detailed file inventory are excluded.

`reader_ready` reports core source, metadata, segment-index and search readiness separately from HTTP reachability. `translation_ready` additionally requires a loaded local model. `source_index.ready` checks the offset-index schema, corpus coverage and source size/mtime signatures using bounded metadata queries. `check_local_runtime.py` exits nonzero for core readiness failures or an unavailable model; an HTTP 200 alone is insufficient.

```json
{
  "status": "ok",
  "generated_at": "2026-07-30T03:00:00+00:00",
  "corpora": [
    {
      "corpus_id": "bible",
      "title": "Bible",
      "source_ready": true,
      "metadata_ready": true,
      "segments_ready": true
    }
  ],
  "search": {
    "ready": true,
    "fts5": true
  },
  "gemma": {
    "reachable": true,
    "model_count": 1,
    "state": "ready"
  },
  "issues": []
}
```

Corpus readiness and search-database readiness are cached independently for up to three seconds when healthy and one second when degraded. Gemma readiness is cached for one second when reachable and 0.5 seconds when unavailable, so a failure is not retained for the static-status TTL.

## `GET /api/health/gemma`

Returns only the redacted translation-sidecar readiness used by the Reader polling loop:

```json
{
  "status": "warning",
  "generated_at": "2026-07-30T03:00:00+00:00",
  "gemma": {
    "reachable": false,
    "model_count": 0,
    "state": "starting"
  }
}
```

The response preserves the same public Gemma fields and states as `/api/health`, without recalculating corpus or search readiness.

## Static response caching

JS and CSS URLs with a non-empty `v` query parameter return `Cache-Control: public, max-age=31536000, immutable`. Static responses include representation-specific weak ETags and Last-Modified, honor `If-None-Match` and `If-Modified-Since` with `304`, and negotiate gzip for compressible assets. `HEAD` preserves the selected representation's headers and Content-Length without a body. Unversioned assets and HTML use `no-cache`; JSON APIs and user-data responses use `no-store`.

The detailed structure below is retained for local maintenance builders such as `build_runtime_health()` and is not returned by the HTTP handler.

<details>
<summary>Detailed local maintenance payload</summary>

현재 로컬 reader site 실행 상태를 빠르게 확인하는 endpoint이다.

최상위 필드:

```json
{
  "status": "ok",
  "generated_at": "2026-06-04T03:00:00+00:00",
  "site_root": "<reader_site>",
  "corpus_root": "<corpus_root>",
  "corpora": [],
  "search": {},
  "gemma": {},
  "issues": [],
  "next_recommended_upgrades": []
}
```

`status`:

- `ok`: required source folders, metadata, segment artifacts, and search DB are currently usable.
- `warning`: one or more required local artifacts are missing or degraded.

`corpora[]`:

```json
{
  "corpus_id": "bible",
  "title": "Bible",
  "source_root": "../성경_원서수집",
  "source_root_exists": true,
  "primary_output": "../성경_원서수집/bible/bible/output",
  "primary_output_exists": true,
  "metadata": {},
  "segments": {},
  "notes": {},
  "work_count": 121,
  "variant_count": 0,
  "metadata_error": ""
}
```

File records such as `metadata`, `segments`, and `notes`:

```json
{
  "name": "bible_metadata",
  "kind": "metadata",
  "role": "work catalog",
  "path": "data/bible_metadata.json",
  "exists": true,
  "bytes": 160161,
  "modified_at": "2026-05-28T02:58:12+00:00"
}
```

`search`:

```json
{
  "name": "search_index.sqlite",
  "kind": "search",
  "role": "query database",
  "path": "data/search_index.sqlite",
  "exists": true,
  "bytes": 539590656,
  "modified_at": "2026-06-04T01:54:54+00:00",
  "records": 225442,
  "by_corpus": {
    "bible": 60180,
    "kierkegaard": 25359,
    "nietzsche": 14227,
    "wittgenstein": 125676
  },
  "fts5": true
}
```

The artifact list also includes the local source-target index:

```json
{
  "name": "segment_offset_index.sqlite",
  "kind": "index",
  "role": "source target byte-offset index",
  "path": "data/segment_offset_index.sqlite",
  "exists": true,
  "bytes": 31490048,
  "modified_at": "2026-07-30T08:54:26+00:00"
}
```

`gemma`:

```json
{
  "base_url": "http://127.0.0.1:9999",
  "reachable": true,
  "model_count": 1,
  "models": ["gemma-4-26B-A4B-it-Q4_K_M.gguf"],
  "state": "ready"
}
```

Notes:

- `issues[]` is empty when `status` is `ok`.
- `gemma.state` is one of `starting`, `ready`, `failed`, or `unavailable`.
- `next_recommended_upgrades[]` is advisory and may change as implementation work progresses.

</details>

## `GET /api/artifacts`

The HTTP response is a redacted readiness manifest. Paths, sizes, timestamps, checksums, local configuration, and regeneration commands are excluded.

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-30T03:00:00+00:00",
  "corpora": [],
  "artifacts": [
    {
      "name": "search_index.sqlite",
      "kind": "search",
      "role": "query database",
      "ready": true
    }
  ],
  "search": {
    "ready": true,
    "fts5": true
  }
}
```

For paths, byte sizes, timestamps, optional checksums, and rebuild commands, generate the ignored local manifest with `python .\scripts\build_artifact_manifest.py`.

<details>
<summary>Detailed local maintenance manifest</summary>

현재 로컬 생성 산출물 manifest를 반환한다. `scripts/build_artifact_manifest.py`가 파일로 쓰는 내용과 같은 계열의 payload이다.

최상위 필드:

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-04T03:00:00+00:00",
  "site_root": "<reader_site>",
  "corpus_root": "<corpus_root>",
  "uses_env_corpus_root": false,
  "corpora": [],
  "artifacts": [],
  "search": {},
  "regeneration_commands": []
}
```

`artifacts[]`:

```json
{
  "name": "search_index.sqlite",
  "kind": "search",
  "role": "query database",
  "path": "data/search_index.sqlite",
  "exists": true,
  "bytes": 539590656,
  "modified_at": "2026-06-04T01:54:54+00:00"
}
```

`regeneration_commands[]` currently lists the local commands needed to rebuild metadata, segments, the source-target byte-offset index, search, and the local artifact manifest.

Example:

```powershell
python .\scripts\build_nietzsche_metadata.py
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
python .\scripts\build_segment_offset_index.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
python .\scripts\build_artifact_manifest.py
```

Notes:

- The HTTP API does not write `data/artifact_manifest.local.json`.
- To write the manifest, run `python .\scripts\build_artifact_manifest.py`.
- Use `--checksums` only when SHA-256 hashes are needed, because it reads large generated files.

</details>

## `GET /api/search`

Cross-corpus segment search. Backed by `data/search_index.sqlite` when available, with JSONL fallback only for indexes up to 32 MiB. A missing database for a larger index, an unreadable database, or a database older than the regenerated JSONL returns an empty result payload with `error` containing the rebuild command. Query/filter counts and the fixed FTS re-ranking head are cached against the database file signature; ranking ties and pagination remain stable.

Query parameters:

```text
q=<search text>
corpus_id=<optional corpus id>
work_id=<optional work id>
variant_id=<optional variant id>
limit=<1-100, default 30>
page=<1-based page, default 1>
offset=<optional zero-based result offset; takes precedence over page>
```

General response:

```json
{
  "query": "ressentiment",
  "count": 20,
  "engine": "sqlite-fts5",
  "results": [],
  "limit": 40,
  "offset": 0,
  "page": 1,
  "total_pages": 1,
  "has_previous": false,
  "has_next": false,
  "work_count": 0,
  "work_results": [],
  "note_count": 0,
  "note_results": []
}
```

`work_results[]`:

```json
{
  "kind": "work",
  "corpus_id": "nietzsche",
  "work_id": "GM",
  "variant_id": "",
  "title": "Zur Genealogie der Moral",
  "label": "Major Published Books",
  "url": "/work/nietzsche/GM",
  "snippet": "nietzsche / GM / Zur Genealogie der Moral",
  "category_id": "major_published_books",
  "category_title": "Major Published Books",
  "variant_ids": [],
  "score": 1000
}
```

`results[]`:

```json
{
  "corpus_id": "nietzsche",
  "work_id": "GM",
  "variant_id": "",
  "segment_id": "p-0023",
  "segment_type": "paragraph",
  "title": "Zur Genealogie der Moral",
  "label": "Paragraph 23",
  "url": "/work/nietzsche/GM#p-0023",
  "snippet": "...",
  "score": 12
}
```

`note_results[]`:

```json
{
  "kind": "note",
  "id": "note-id",
  "corpus_id": "nietzsche",
  "work_id": "GM",
  "variant_id": "",
  "target_id": "p-0023",
  "target_label": "Paragraph 23",
  "title": "nietzsche / GM",
  "label": "Paragraph 23",
  "url": "/work/nietzsche/GM#p-0023",
  "manage_url": "/notes?corpus_id=nietzsche&work_id=GM&target_id=p-0023",
  "snippet": "...",
  "review_state": "reviewed",
  "tags": ["genealogy"],
  "score": 8
}
```

Work, segment, and note search use the same `q`, `corpus_id`, and `work_id` filters. `variant_id` applies to work and segment search.

Work alias ranking rules:

- Exact compact alias matches rank above prefix and partial matches.
- One-letter work queries such as `M` only return exact work aliases.
- Multi-term work queries must match all terms unless the compact alias is exact or prefix-matched.
- Bible work aliases prefer the primary source layer by default: SBLGNT for New Testament, OSHB for Hebrew Bible, then LXX.
- Bible source prefixes such as `lxx Genesis` constrain work alias results to that source layer.
- LXX/deuterocanonical work aliases include shorthand and alternate titles such as `Tob`, `Wis`, `Sir`, `Ecclesiasticus`, `EpJer`, `Psalm 151`, and `Additions to Daniel`.

## `GET /api/work-chunks`

Returns one rendered chunk for a work that exceeds the server's large-work virtualization thresholds. The reader uses this endpoint internally; existing work URLs, paragraph IDs, sentence IDs, translation targets, and note targets remain unchanged.

Virtualization applies across corpora at 4,000 selectable sentences, or both 2,000 segments and 2 MiB of source text. Bible chapter anchors and Hebrew text direction are preserved; Nietzsche headings and quotations do not contribute selectable sentence positions. Each virtual work exposes a complete `view=print` page.

Query parameters:

```text
corpus_id=wittgenstein
work_id=Group_BigTypescriptCorpus
variant_id=idp_transcription_linear
chunk=154
```

Use `anchor=p-3301.s001` instead of `chunk` to resolve a deep link to the chunk that contains that paragraph or sentence. The response contains stable first/last segment IDs, one-based global sentence positions, counts, an estimated placeholder height, and rendered HTML for only the requested chunk. Missing fields and works below the virtualization thresholds return `400`; unknown chunks and anchors return `404`.

The endpoint reads only the byte ranges listed in `segment_offset_index.sqlite`. It does not parse or retain the complete corpus JSONL in memory. The normal `/work/<corpus_id>/<work_id>` route remains eager for ordinary works. A virtual work's `view=print` query renders the complete document for printing.

## `GET /api/source-target`

Returns a bounded local source target bundle for one generated segment. This is the safe pre-AI boundary for a future Gemma/local-model interpretation layer: it resolves the selected target and returns the exact source text plus checksum, but it does not call a model or store generated output.

Query parameters:

```text
corpus_id=<required corpus id>
work_id=<required work id>
target_id=<required segment id>
variant_id=<optional variant id>
```

`segment_id` is accepted as an alias for `target_id`.

Response:

```json
{
  "target": {
    "schema_version": 1,
    "record_type": "source_target_bundle",
    "corpus_id": "wittgenstein",
    "work_id": "Ms-101",
    "variant_id": "source_transcription_normalized.full",
    "target_id": "p-0001",
    "target_url": "/work/wittgenstein/Ms-101?variant=source_transcription_normalized.full#p-0001",
    "segment_type": "paragraph",
    "label": "Paragraph 1",
    "source_text": "exact source text",
    "source_text_preview": "short source preview",
    "source_text_chars": 17,
    "source_text_sha256": "64-char sha256"
  }
}
```

Missing required fields or unknown corpus ids return `400`. Unknown work, variant, or segment targets return `404`.

Work pages expose this boundary through the Citation panel's `Copy source bundle` action. The button copies the local `/api/source-target` URL for the current section, paragraph, or verse anchor.

## `POST /api/sentence-translation`

Generates or loads a local cached Gemma study translation for one clicked sentence. The endpoint does not accept arbitrary source text or free-form prompts; it resolves the sentence from existing local segment records.

Write requests require the reader's local `Host` and port. Browser requests must come from the same `Origin`; POST and PUT bodies must use `Content-Type: application/json` and contain a JSON object. Local scripts may omit `Origin`. Invalid origin, host, or content type returns `403`; an invalid JSON payload returns `400`.

Request:

```json
{
  "corpus_id": "nietzsche",
  "work_id": "GM",
  "variant_id": "",
  "segment_id": "p-0023",
  "sentence_id": "p-0023.s001",
  "request_id": "17331330-e417-4d6d-b94e-48c7cd051553",
  "regenerate": false
}
```

Response:

```json
{
  "ok": true,
  "cached": false,
  "record": {
    "schema_version": 5,
    "record_type": "ai_sentence_translation",
    "target_url": "/work/nietzsche/GM#p-0023.s001",
    "translation": "generated Korean translation",
    "commentary": "source-bounded commentary",
    "cautions": ["caution"],
    "source_text_sha256": "64-char sha256",
    "sentence_text_sha256": "64-char sha256",
    "source_context_sha256": "64-char sha256",
    "prompt_sha256": "64-char sha256",
    "generation_parameters": {
      "temperature": 0.1,
      "top_p": 0.95,
      "max_tokens": 900,
      "seed": 0
    },
    "response_schema_name": "sentence_translation_response",
    "translation_policy_sha256": "64-char sha256",
    "request_contract_sha256": "64-char sha256",
    "pipeline_contract_sha256": "64-char sha256",
    "quality_pipeline_version": 8,
    "quality_state": "critic_pass",
    "revision_count": 0,
    "max_revision_count": 1,
    "critic": {
      "initial": {"verdict": "pass", "issues": []},
      "final": null
    }
  }
}
```

The server supplies the selected structural segment plus adjacent source units, up to 6,000 characters, and marks the selected sentence inside that context. When a unit must be shortened, complete sentences are preferred over arbitrary character cuts. llama.cpp first receives a strict JSON Schema requiring `translation` and `commentary` strings plus a string-array `cautions`; a non-empty commentary without Korean text is rejected. A fresh critic request then receives only the exact marked sentence, approved policy, and draft translation—but neither translator commentary nor adjacent context—and returns a strict `pass`/`revise` issue report. The initial translation retains bounded context for disambiguation, while revision receives only the exact marked target so it cannot defend an adjacent premise as repair evidence. The v7 pipeline checks semantic fidelity, marked-target boundaries, and material Korean readability defects such as opaque referents, source-order fragments, literal-calque redundancy, and claims imported from adjacent context; smoother wording alone is not an issue. Human-approved terminology, sentence-specific required meaning fragments, and forbidden fragments are then checked deterministically. A form-only complaint against all or part of an exact evaluator-approved fragment can be suppressed only while that full fragment is present; an exact unsupported-addition complaint can also be suppressed for that approved mapping alone. Unrelated semantic issues remain active, and a source-final continuation colon cannot be silently replaced by closing punctuation. Major issues and material korean_readability defects, even when minor, trigger at most one schema-constrained revision and one final critic; other minor-only findings stay for human review. A limiter must remain attached to the same source constituent, while splitting a source sentence into complete Korean clauses cannot add adjacent claims. A major syntax_or_scope finding remains active even when its span overlaps an approved fragment. Therefore an uncached request normally uses two model calls and a repair uses four, with no second revision. Invalid translator output is rejected with `502` and is not saved; critic or revision failure is saved explicitly as `quality_state: "critic_error"` with a caution. Automatically flagged records are not cache hits unless human-reviewed.

`quality_state` is one of `critic_pass`, `critic_pass_after_revision`, `needs_human_review`, or `critic_error`. It is automated evidence and remains separate from the human-owned `review_state` (`generated`, `reviewed`, or `rejected`). The `pipeline_contract_sha256` changes when any translator, critic, or revision contract changes, so records from an older quality pipeline cannot silently satisfy the current cache. Citation hashes have distinct meanings: `source_text_sha256` hashes the exact selected source segment, `sentence_text_sha256` hashes the clicked sentence, and `source_context_sha256` hashes the bounded context sent to the model.

Before building a model prompt, the endpoint looks for reviewed records matching the exact corpus, work, variant, sentence ID and sentence text hash. Records with a non-empty human correction take precedence over reviewed model output; the latest approval timestamp chooses between records in the same class. It returns that saved record with `cached: true` even if the model settings or prompt have changed. `regenerate: true` explicitly bypasses saved approvals and model caches; old records remain stored. Unreviewed model-cache reuse for generation continues to require matching prompt and pipeline hashes.

The optional boolean `cache_only: true` reads stored translations without preparing prompts, scheduling a generation, calling the model, or writing records. It cannot be combined with `regenerate: true`. This is the Reader's default sentence-navigation request. It first returns an exact-source reviewed record using the precedence above; otherwise it may show the latest non-rejected model record with its existing warnings, even from an older prompt or pipeline. This browsing result does not certify model quality. A hit returns `cached: true`, `requires_generation: false`, and the record. A miss returns `cached: false`, `requires_generation: true`, and `record: null`. Both return current-request metrics with zero model calls. A missing model runtime does not prevent this lookup.

`request_id` is optional and must be a fresh UUID when supplied. Keep it to cancel an active request. Only one model pipeline runs at a time. One replacement request may wait for a cancelled or disconnected active request to release its execution slot; it remains cancellable while waiting. Unrelated overlapping requests, additional waiters and cancelled requests return `409`. Replacement waiting is bounded to 210 seconds. Abbreviation fragments from older sentence links resolve to the merged sentence's canonical ID and full text. Reference-only Kierkegaard sections and Wittgenstein `.index` variants cannot be translated and return `400`; index pages preserve reference anchors without clickable translation spans.

If the shared llama.cpp runtime is not running at `127.0.0.1:9999`, the endpoint returns `503` with `{"ok": false, "error": "번역 준비가 필요합니다."}`. Generated JSONL files under `data/ai/` are local-only and ignored by Git. A malformed stored JSONL line blocks reads and writes instead of silently discarding records; repair it from a verified backup before retrying.

Local note and translation appends serialize only the new record, using a private fsynced intent journal and a process file lock instead of copying the entire history. An exception or process interruption restores the uncommitted append before a cooperating read or write. Unexpected external changes block recovery and preserve both files. Updates and deletions still replace a complete snapshot atomically. The JSONL schema and HTTP/export payloads are unchanged; direct file copies or edits require a stopped Reader or the storage lock described in the README. Backup manifest inspection remains read-only and rejects a pending recovery journal.

## `POST /api/sentence-translation/cancel`

Cancels a generation by its UUID. This endpoint can acknowledge cancellation before the generation reaches the server.

```json
{"request_id": "17331330-e417-4d6d-b94e-48c7cd051553"}
```

The response includes `ok`, `cancelled`, `state` and `execution_released`. For an active call, cancellation is acknowledged with `cancelled: true`, `state: "cancelling"` and `execution_released: false` until its execution slot is released. The model connection is shut down even while waiting for response headers or a response body; subsequent stages and storage are blocked. Early or queued cancellations use `state: "cancelled"` and `execution_released: true`. Already saved results return `cancelled: false` and `state: "completed"`. Cancellation and commit use the same lock, so an acknowledged cancellation cannot be followed by a new write from that request. Client disconnection is checked during model I/O at 100 ms intervals as well as while queued, between model calls and immediately before storage. The runtime is responsible for reacting to the closed model connection; an immediate GPU stop is not guaranteed. Cancellation IDs are remembered for the latest 256 finished or cancelled requests in this server process.

## `PUT /api/sentence-translations/<record_id>`

Updates the local review state for one generated sentence translation record. This does not call Gemma and does not edit source text.

Request:

```json
{
  "corpus_id": "nietzsche",
  "review_state": "reviewed"
}
```

Allowed `review_state` values are `generated`, `reviewed`, and `rejected`.

To save a direct human correction, send `review_state: "reviewed"` with a non-empty `human_translation` string of at most 12,000 characters. Internal paragraph breaks and spacing are preserved. The service stores it as `human_translation`, records `human_translation_updated_at`, and fingerprints the preserved model output in `human_translation_base_sha256`. It never overwrites `translation`. A human-confirmed record must remain reviewed; the client omits reset and rejection actions for it.

```json
{
  "corpus_id": "nietzsche",
  "review_state": "reviewed",
  "human_translation": "사람이 직접 교정하고 확정한 번역"
}
```

The optional string `expected_translation` protects a human correction from concurrent edits. Send the effective translation shown when editing started (the existing human correction, or the model translation when there is no human correction). The service compares trimmed text under the same storage lock as the update. A mismatch returns `400` with `error: "translation_changed_since_editing"` and does not write anything. The browser retains its draft, reloads the current text, and requires an explicit comparison/rebase before saving again. Omitting the field preserves compatibility with earlier clients; it does not enable this guard.

## `DELETE /api/sentence-translations/<record_id>`

Permanently removes one local generated sentence-translation record. The record is deleted from the corpus JSONL file; source text and notes are not changed.

Query parameters:

- `corpus_id`: required corpus id.

Example:

```text
DELETE /api/sentence-translations/record-id?corpus_id=nietzsche
```

Response:

```json
{
  "ok": true,
  "deleted": {
    "id": "record-id",
    "corpus_id": "nietzsche"
  }
}
```

The Translations page places this operation behind a permanent-delete action and an explicit browser confirmation. A missing `corpus_id` returns `400`; an unknown record returns `404`.

## `GET /api/sentence-translations/summary`

Returns local AI sentence translation counts without returning generated text.

Query parameters:

- `corpus_id`: required corpus id.
- `work_id`: optional work id filter.
- `variant_id`: optional exact variant filter, including an explicitly empty value.
- `current_sentences=1`: emit sentence states only when the saved sentence ID and text hash match a current canonical sentence. Historical record counts remain available.

`sentence_states` identifies each variant separately and includes the additive boolean `human_confirmed`. Its current record uses the same human-correction precedence as the Reader, with normalized approval timestamps. Historical record counts remain unchanged. The reader uses the current-sentence filter so an older abbreviation-fragment translation is retained in history without marking the merged sentence as studied.

Response:

```json
{
  "ok": true,
  "count": 3,
  "review_state_counts": {
    "generated": 1,
    "reviewed": 2,
    "rejected": 0
  },
  "latest_generated_at": "2026-06-19T00:00:00Z",
  "latest_reviewed_at": "2026-06-19T00:00:00Z"
}
```

## `GET /api/sentence-translations/export`

Exports local sentence translation records for study review.

An optional `variant_id` filters the exact variant, including an explicitly empty value. Omitting it retains the work-wide export behavior.

Query parameters:

- `corpus_id`: optional corpus id; omit it to export all corpora.
- `work_id`: optional work id filter.
- `q`: optional text filter matching corpus/work ids, source excerpts, translations, and commentary.
- `review_state`: `reviewed` by default; also accepts `generated`, `rejected`, or `all`.
- `format`: `markdown` by default; `json` returns structured records.
- `include_source_state=1`: optionally annotate returned records with `source_current`: `true` for an exact current canonical sentence/hash match, `false` for a changed/missing sentence or missing stored hash, and `null` when the source cannot be checked. Lookup is reused per distinct source segment. This read-only annotation is not stored. The translation list requests it to distinguish historical approvals from current-source confirmations.

Bible direct lookup:

LXX/deuterocanonical references accept shorthand such as `Tob 1:1`, `Wis 1:1`, `Sir 1:1`, `EpJer 1:1`, and `Psalm 151:1`. Single-chapter materials stored with chapter `0` can be entered with chapter `1`.

References such as `Gen 1:1`, `Genesis 1:1`, `John 3:16`, `1 John 5:7`, Korean abbreviations such as `창 1:1`, `요 3:16`, `요일 5:7`, and `lxx Gen 1:1` are resolved before full-text search.

Direct lookup response:

```json
{
  "query": "John 3:16",
  "count": 1,
  "engine": "sqlite-direct-bible",
  "direct": {
    "kind": "bible_reference",
    "book_id": "John",
    "chapter": "3",
    "verse": "16"
  },
  "results": [
    {
      "corpus_id": "bible",
      "work_id": "sblgnt.John",
      "variant_id": "sblgnt",
      "segment_id": "John.3.16",
      "segment_type": "verse",
      "title": "John / 요한복음",
      "label": "John 3:16",
      "url": "/work/bible/sblgnt.John?variant=sblgnt#John.3.16",
      "snippet": "...",
      "score": 10000
    }
  ]
}
```

Notes:

- Old Testament references default to OSHB when both OSHB and LXX have the same verse.
- New Testament references default to SBLGNT.
- Prefix `lxx` selects the LXX/Swete source when that verse exists.
- `work_id` and `variant_id` filters constrain direct lookup when provided.
- `note_results` are still included for the same query when matching personal notes exist.

## `GET /api/notes`

Reads personal notes from `data/notes/<corpus_id>_notes.jsonl`.

The optional `variant_id` parameter filters an exact variant, including an empty value. The same filter is supported by the notes export endpoint.

Query parameters:

```text
corpus_id=<required corpus id>
work_id=<optional work id>
target_id=<optional target id>
tag=<optional exact tag>
review_state=<optional raw|reviewed>
q=<optional substring search over label, quote, note, and tags>
```

Response:

```json
{
  "notes": [
    {
      "id": "hex uuid",
      "created_at": "2026-06-04T12:00:00",
      "updated_at": "2026-06-04T12:01:00",
      "corpus_id": "nietzsche",
      "work_id": "M",
      "variant_id": "",
      "target_id": "sec-1",
      "target_type": "section",
      "target_label": "Section 1",
      "quote": "",
      "note": "personal note text",
      "review_state": "raw",
      "reviewed_at": "",
      "tags": ["concept"],
      "url": "/work/nietzsche/M#sec-1"
    }
  ]
}
```

## `POST /api/notes`

Creates a note. The target work must exist. For `target_type=segment`, `target_type=paragraph`, and `target_type=verse`, the target must also resolve to a generated segment record. Section, chapter, and whole-work notes are allowed as work-level reading anchors.

When `variant_id` is present, the saved note URL preserves it as a `?variant=...` query before the target hash.

Request body:

```json
{
  "corpus_id": "nietzsche",
  "work_id": "M",
  "variant_id": "",
  "target_id": "sec-1",
  "target_type": "section",
  "target_label": "Section 1",
  "quote": "",
  "note": "personal note text",
  "tags": ["concept"]
}
```

Response:

```json
{
  "ok": true,
  "note": {}
}
```

## `PUT /api/notes/<note_id>`

Updates note text, tags, quote, target label, or review state.

Request body:

```json
{
  "corpus_id": "nietzsche",
  "note": "updated text",
  "tags": ["edited"],
  "review_state": "reviewed"
}
```

Response:

```json
{
  "ok": true,
  "note": {}
}
```

## `DELETE /api/notes/<note_id>`

Deletes a note from the corpus notes file.

Query parameters:

```text
corpus_id=<required corpus id>
```

Response:

```json
{
  "ok": true,
  "deleted": {
    "id": "hex uuid"
  }
}
```

## `GET /api/notes/export`

Exports notes across one corpus or all note files.

Query parameters:

```text
format=json|jsonl|markdown
corpus_id=<optional corpus id>
work_id=<optional work id>
target_id=<optional target id>
tag=<optional exact tag>
review_state=<optional raw|reviewed>
q=<optional substring search over label, quote, note, and tags>
```

JSON response:

```json
{
  "count": 1,
  "notes": []
}
```

Other formats:

- `format=jsonl` returns newline-delimited JSON with `application/x-ndjson`.
- `format=markdown` or `format=md` returns a Markdown research-notes document.

## `GET /api/study`

Returns reviewed notes grouped by corpus and work for the `/study` reading page.

Query parameters:

```text
corpus_id=<optional corpus id>
work_id=<optional work id>
tag=<optional exact tag>
q=<optional substring search over label, quote, note, and tags>
```

Response:

```json
{
  "count": 2,
  "group_count": 1,
  "groups": [
    {
      "corpus_id": "nietzsche",
      "work_id": "M",
      "title": "nietzsche / M",
      "count": 2,
      "target_count": 2,
      "summary": "2 reviewed notes / 2 targets / tags: morality, dawn",
      "tag_counts": [
        {
          "tag": "morality",
          "count": 1
        }
      ],
      "reviewed_range": {
        "start": "2026-06-04T12:02:00",
        "end": "2026-06-05T09:30:00"
      },
      "notes": [
        {
          "id": "hex uuid",
          "corpus_id": "nietzsche",
          "work_id": "M",
          "variant_id": "",
          "target_id": "p-0001",
          "target_type": "paragraph",
          "target_label": "Paragraph 1",
          "url": "/work/nietzsche/M#p-0001",
          "note": "reviewed study note",
          "quote": "",
          "tags": ["dawn"],
          "review_state": "reviewed",
          "reviewed_at": "2026-06-04T12:02:00"
        }
      ]
    }
  ]
}
```

The `/study` page uses each note's `url`, `target_type`, `target_id`, and `variant_id` to show a direct source-target link and compact target metadata.

## `GET /api/study/export`

Exports reviewed note bundles.

Query parameters are the same as `/api/study`, plus:

```text
format=markdown|json
```

`format=markdown` returns a grouped Markdown study-note bundle including deterministic group summaries, tag counts, and reviewed date ranges. `format=json` returns the same grouped payload as `/api/study`.

## `GET /api/study-session/export`

Exports one work-level study session by combining personal notes and generated Gemma sentence translations. By default this is a reviewed-study bundle: reviewed notes plus reviewed translations.

Use `variant_id` to constrain both notes and translations to one exact variant, including an empty value. Reader pages include their active variant. Without this parameter, all variants remain available; each item must be opened with its complete source URL so equal sentence IDs in different variants cannot resolve to the wrong text.

Query parameters:

```text
corpus_id=<required corpus id>
work_id=<optional work id>
notes_review_state=reviewed|raw|all
translation_review_state=reviewed|generated|rejected|all
format=markdown|json
```

`format=markdown` returns a single study document with separate Notes and Generated Translation & Commentary sections. The generated translation section is explicitly labeled as AI output and not source text.

## Translation-note binding and diagnostics (2026-10-01)

Sentence-translation records remain backward-readable through schema 6. `commentary` remains a string; public responses set it to an empty string when it is unbound, ungrounded, or refers to a different translation. `commentary_status` includes `current`, `none`, `legacy_unverified`, `translation_changed`, `source_changed`, `translation_review_required`, and `notes_review_required`; `translation_notes` contains only currently publishable `{source_span, note}` entries. Original model commentary is retained in the local record and is never silently relabelled as a note for a human edit.

`current_translation_issues` reports current sentence-specific meaning checks. The additive `current_note_issues` field reports independently documented false note assertions, bound to the corpus, work, variant, sentence ID and source SHA-256. When a current note matches one of those assertions, the public API and Markdown export hide its explanation and report `notes_review_required`; the stored original is preserved. These checks reject recorded whole assertions after whitespace normalization, not every possible paraphrase or a grammar term mentioned in a correction. An empty issue list does not certify linguistic accuracy or human approval.

`POST /api/sentence-translation` also returns `metrics`: current-request `model_calls`, allowlisted `model_usage` (stage, requested output tokens, actual prompt/completion tokens, context limit, available context, transport completion), and `context_truncated`. Cache hits return zero calls and an empty usage list. Unknown token/context values are null, not estimates or zero. New saved records retain generation metrics for the generation that created them; a cache hit does not reinterpret those historical calls as new work. No prompt, generated text, credential, local path, or target identity is included in these metrics.

Pipeline v10 adds `current_translation_issues` for dictionary-backed checks scoped to an exact sentence hash. These warnings apply to the currently displayed human/model translation without rewriting historical approval or model verdicts. A current note with a detected meaning issue is withheld as `translation_review_required`. Markdown exports retain the warning. The curated source-check hash is part of the pipeline contract.

A changed saved note-source hash is withheld as `source_changed`. Source-span presence alone cannot override the selected-sentence checksum.
