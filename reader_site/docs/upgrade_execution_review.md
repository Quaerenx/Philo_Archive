# Upgrade Execution Review

작성일: 2026-06-04

## 판단

이전 검토에서 제안한 고도화 순서는 타당하다.

다만 우선순위는 새 기능을 바로 늘리는 것보다, 다음 세 가지 기반을 먼저 고정하는 쪽이 적절하다.

1. 로컬 원서 폴더와 생성 산출물의 상태를 확인할 수 있어야 한다.
2. 대형 산출물은 Git에서 제외하되, 어떤 파일이 필요한지 manifest로 설명할 수 있어야 한다.
3. `server.py`의 기능을 점진적으로 분리할 수 있는 작은 모듈 경계가 필요하다.

## 이번 적용 내용

이번 고도화에서는 다음 기반을 추가했다.

- `runtime_status.py`
  - corpus source root 존재 여부
  - metadata/segment/notes 파일 존재 여부
  - metadata work/variant count
  - search SQLite record count
  - FTS5 적용 여부
  - artifact manifest payload 생성
- `/api/health`
  - 현재 로컬 reader site가 읽기/연구에 필요한 자료를 갖추었는지 확인한다.
- `/api/artifacts`
  - 현재 생성 산출물 목록을 API로 확인한다.
- `scripts/build_artifact_manifest.py`
  - 로컬 상태 기록용 `data/artifact_manifest.local.json`을 생성한다.
  - `--checksums`를 붙이면 대형 산출물의 SHA-256도 계산한다.
- `scripts/build_search_db.py`
  - 기존 `search_segments` 테이블을 유지하면서 `search_segments_fts` FTS5 virtual table을 함께 생성한다.
- `/api/search`
  - FTS5 테이블이 있으면 `sqlite-fts5` 엔진을 우선 사용한다.
  - FTS5가 없거나 쿼리가 실패하면 기존 `sqlite-like` 검색으로 fallback한다.
- `services/search.py`
  - 검색 정규화, FTS5 조회, LIKE fallback, JSONL fallback을 `server.py`에서 분리했다.
  - `server.py`는 이제 `search_records()`만 import해서 `/api/search` 응답에 사용한다.
- `services/notes.py`
  - notes JSONL 저장 경로, 읽기, 쓰기, legacy `author` 필드 보정 로직을 `server.py`에서 분리했다.
  - cross-corpus notes 조회와 JSONL/Markdown export 변환도 담당한다.
  - `server.py`는 HTTP payload 검증과 work target 검증을 담당하고, 실제 notes 저장소 접근은 서비스에 맡긴다.
- `corpora/catalogs.py`
  - Nietzsche catalog/metadata/concepts 조회를 분리했다.
  - Bible/Kierkegaard/Wittgenstein metadata 조회를 분리했다.
  - Bible segment JSONL cache와 work 단위 segment 조회를 분리했다.
  - work id 검증과 work target resolution을 `server.py` 밖으로 이동했다.
- `rendering/work_markup.py`
  - table of contents, concept list, variant tabs, source notice HTML 조각 생성을 분리했다.
  - 공통 `work.html` 템플릿 치환과 research JSON embedding을 `server.py` 밖으로 이동했다.
- `rendering/static_pages.py`
  - `/read`와 `/source` 페이지 템플릿 치환을 `server.py` 밖으로 이동했다.
  - 기존 inline HTML/CSS를 `templates/reading.html`, `templates/source.html`, `assets/static-reader.css`로 분리했다.
- `.gitignore`
  - `data/artifact_manifest.local.json`을 로컬 전용 산출물로 제외한다.
- `assets/design-tokens.css`
  - `--page-frame-width: 1000px`
  - `--reader-column-width: 764px`
  - 페이지 프레임, 배경, 본문 컨테이너, 헤더 이미지의 공통 이름을 정의한다.

## 다음 고도화 순서

### 1. 서버 분리

`server.py`는 현재 라우팅, 렌더링, corpus loader, notes, search가 한 파일에 모여 있다. 다음 작업은 아래 구조로 나누는 것이다.

```text
reader_site/
  server.py
  runtime_status.py
  core/
    paths.py
    io.py
    rendering.py
  corpora/
    nietzsche.py
    bible.py
    kierkegaard.py
    wittgenstein.py
  services/
    search.py
    notes.py
```

검색 계층은 `services/search.py`로, notes 저장소 처리는 `services/notes.py`로, source/read page assembly는 `services/sources.py`로, corpus catalog/metadata 조회는 `corpora/catalogs.py`로, corpus별 work model은 `corpora/work_models.py`로, archive index 생성은 `corpora/archive.py`로, work page markup은 `rendering/work_markup.py`로, read/source template rendering은 `rendering/static_pages.py`로 분리되었다. 다음 분리 후보는 route table이 더 커질 경우의 API dispatch/static file serving이다.

### 2. 검색 품질 개선

FTS5 전환은 적용되었다. 다음 작업은 검색 품질이다.

- corpus별 랭킹 가중치 조정
- 성경 책/장/절 직접 이동 검색
- 원어/정규화/로마자 검색 분리
- notes 검색 통합

### 3. 공통 UI 토큰화

기본 CSS 토큰은 적용되었다.

```css
:root {
  --page-frame-width: 1000px;
  --reader-column-width: 764px;
}
```

다음 작업은 반복되는 `.page`, `.reader`, `.spacer` 스타일 자체를 공통 CSS 파일로 더 모으는 것이다.

### 4. notes/citation 완전 공통화

API는 이미 `corpus_id` 중심으로 움직이기 시작했지만, legacy Nietzsche 전용 파일과 문서가 남아 있다. 다음 단계에서 legacy template/assets를 정리하고, 모든 corpus에서 같은 note/citation 모델을 쓰게 만든다.

현재 notes 파일 입출력은 서비스로 분리되었고, 수정/삭제, tag filtering, work/target filtering, raw/reviewed filtering, export, cross-work notes index page, dashboard 직접 수정/삭제/검토 완료 처리까지 추가되었다. 검색 결과에는 work/target notes backlink가 추가되었다. `/study`는 reviewed notes를 corpus/work별로 묶어 읽는 전용 화면이다.

## 보류한 것

- Gemma4/AI 해석 기능은 아직 붙이지 않는다.
- 이유: segment, citation, manifest, search가 먼저 안정되어야 AI 해석 결과도 출처와 함께 관리할 수 있다.
- 성경/키르케고르/비트겐슈타인 전용 심화 기능도 서버 분리와 검색 전환 이후가 적절하다.

## 2026-06-04 추가 적용

이번 후속 고도화에서는 `server.py`에 남아 있던 archive index 생성 책임을 분리했다.

- `corpora/archive.py`
  - `/api/archive` 응답을 생성한다.
  - Nietzsche, Bible, Kierkegaard, Wittgenstein의 루트 카테고리와 category page 링크를 구성한다.
  - corpus별 source folder, metadata, manifest, mapping CSV를 읽어 index용 `sections`, `links`, `counts`를 만든다.
  - `server.py`는 이제 `build_archive()`를 import해서 HTTP 응답만 담당한다.
- `corpora/work_models.py`
  - corpus별 work page model 생성을 담당한다.
  - `/work/nietzsche/M`, `/work/bible/oshb.Gen`, `/work/kierkegaard/aas`, `/work/wittgenstein/Ms-101` 같은 공통 route 뒤의 실제 데이터 조립을 담당한다.
- `rendering/documents.py`
  - Markdown reading HTML, Bible verse HTML, Kierkegaard JSON text extraction, generic segment rendering을 담당한다.
- `server.py`
  - line count가 약 789줄에서 약 418줄로 줄었다.
  - route dispatch, note/search API glue, static/source/read serving, common work-page response에 집중한다.
- `services/sources.py`
  - source path validation과 `/read`, `/source` HTML assembly를 담당한다.
  - `server.py`는 read/source route에서 이 서비스를 호출하고 HTTP status mapping만 처리한다.
  - 이 후속 분리로 `server.py` line count는 약 360줄까지 줄었다.
- `docs/api_reference.md`
  - `/api/archive`, `/api/health`, `/api/artifacts`의 현재 JSON 응답 구조를 문서화한다.
  - 프론트엔드와 진단 도구가 기대하는 필드 계약을 기록한다.
- `scripts/check_api_contracts.py`
  - HTTP 서버 없이 `build_archive()`, `build_runtime_health()`, `build_artifact_manifest()`를 직접 호출해 필수 JSON 필드를 검증한다.
- `services/search.py`
  - Bible direct lookup을 추가했다.
  - `Gen 1:1`, `Genesis 1:1`, `John 3:16`, `1 John 5:7`, `lxx Gen 1:1` 같은 reference query를 full-text search 전에 verse URL로 해석한다.
- `scripts/check_search_contracts.py`
  - Bible direct lookup, corpus filter, variant filter가 깨지지 않는지 검사한다.
- `services/notes.py`
  - `q`, `tag`, `target_id`, `work_id` 기반 notes filtering을 지원한다.
  - note update/delete를 JSONL rewrite 방식으로 지원한다.
  - 전체 notes 조회와 JSONL/Markdown export를 지원한다.
- `/api/notes`
  - `GET` 필터 조회, `POST` 생성, `PUT /api/notes/<id>` 수정, `DELETE /api/notes/<id>` 삭제를 지원한다.
- `/api/notes/export`
  - 전체 또는 corpus별 notes를 JSON, JSONL, Markdown으로 내보낸다.
- `/notes`
  - 모든 corpus의 notes를 한 곳에서 필터링, 직접 수정/삭제, 검토 완료 처리, export할 수 있는 연구 notes index page이다.
- `/api/study`
  - reviewed notes를 corpus/work별 bundle로 묶어 반환한다.
- `/api/study/export`
  - reviewed note bundle을 Markdown 또는 JSON으로 내보낸다.
- `/study`
  - `/api/study` bundle을 읽는 study-note view이다.
- `scripts/check_notes_contracts.py`
  - notes 저장, 필터, 수정, 삭제 계약을 검사한다.

검증:

```powershell
python -m py_compile .\server.py .\corpora\archive.py .\corpora\work_models.py .\rendering\documents.py .\services\search.py .\services\notes.py .\runtime_status.py
```

대표 archive 결과:

```text
nietzsche      6 sections, 91 links, 91 files
bible          3 sections, 121 links, 122 files
kierkegaard    1 section, 211 links, 630 files
wittgenstein   2 sections, 202 links, 1228 files
```

## 다음 우선순위

1. 검색을 다음 단계로 고도화한다.
   - deuterocanon/alternative title alias 확장
   - corpus/work/variant filter UX 세부 polish
   - notes search integration
   - FTS5 ranking tuning
2. reviewed notes 기반 요약/인쇄용 출력 bundle을 개선한다.
3. search regression check를 더 넓힌다.
4. 공통 page frame과 corpus-specific header/visual identity를 더 명확히 분리한다.
5. route table이 더 커질 경우 static file serving과 API dispatch를 별도 route module로 분리한다.

## 2026-06-05 reproducibility gate

The next stabilization pass added a single rebuild entrypoint and a route-level smoke test.

- `scripts/rebuild_all.py`
  - Runs metadata builders, segment builders, search index/database builders, artifact manifest generation, and contract checks in order.
  - Supports `--skip-search-db`, `--skip-manifest`, `--manifest-checksums`, and `--no-checks`.
- `scripts/check_static_routes.py`
  - Starts a temporary localhost server on an ephemeral port.
  - Verifies `/`, `/category/nietzsche`, `/search`, `/notes`, `/study`, a representative `/work/...` page, `/api/health`, and `/api/study`.
- `runtime_status.py`
  - Adds `python .\scripts\rebuild_all.py` to the regeneration command list so `/api/artifacts` exposes the preferred rebuild command.

This does not replace the individual builder scripts. It gives the project a reproducible release-style gate while keeping each low-level builder independently runnable.

## 2026-06-05 search-note integration

Search now returns personal research notes alongside segment matches.

- `services/search.py`
  - Adds `note_count` and `note_results` to every `/api/search` payload.
  - Uses the same `q`, `corpus_id`, and `work_id` filters for notes.
  - Keeps segment search and Bible direct lookup unchanged.
- `assets/search.js`
  - Renders separate `Segments` and `Notes` result groups.
  - Notes include target links, manage links, review state, and tags.
- `scripts/check_search_contracts.py`
  - Creates a temporary note and verifies search returns it through `note_results`.

## 2026-06-05 work alias search

Search now returns work-level matches in addition to segment and note matches.

- `services/search.py`
  - Adds `work_count` and `work_results` to every `/api/search` payload.
  - Builds aliases from metadata fields such as `work_id`, `title`, `display_title`, `book_id`, `book_name_en`, `book_name_ko`, `siglum`, category, and variant IDs.
  - Keeps work matching separate from segment FTS so a query like `GM` can point directly to `/work/nietzsche/GM`.
- `assets/search.js`
  - Renders `Works`, `Segments`, and `Notes` as separate result groups.
- `scripts/check_search_contracts.py`
  - Verifies Nietzsche `GM` and Bible `John` work aliases.

## 2026-06-05 work ranking refinement

Work alias ranking now has stricter ordering and filtering rules.

- Exact compact aliases rank above prefix and partial matches.
- One-letter aliases such as `M` no longer leak unrelated works whose title merely contains the same letter.
- Multi-term aliases such as `1 John` must match all terms unless the compact alias is exact or prefix-matched.
- Bible work aliases prefer primary textual layers by default: SBLGNT for New Testament, OSHB for Hebrew Bible, then LXX.
- Source-prefixed work queries such as `lxx Genesis` constrain work results to the requested source layer.

## 2026-06-05 study bundle summaries

Reviewed note bundles now expose deterministic study summaries.

- `services/notes.py`
  - Adds `summary`, `target_count`, `tag_counts`, and `reviewed_range` to each `/api/study` group.
  - Adds summary, reviewed range, and tag-count lines to Markdown study export.
- `assets/study.js`
  - Renders group summaries, reviewed date ranges, and tag counts before note lists.
- `assets/study.css`
  - Adds print-friendly rules that hide navigation/filter controls and keep study groups/notes readable on paper.
- `scripts/check_notes_contracts.py`
  - Verifies group summaries, tag counts, reviewed ranges, and Markdown export metadata.

## 2026-06-05 layout contract gate

The reader-site visual vocabulary now has a static regression gate.

- `styles.css`
  - Keeps the desktop archive index `nav-column` at the shared 764px reader-column width.
  - Folds the home reader column to 100% width inside the page frame below 860px, matching the reader/work/notes/study responsive breakpoint.
- `scripts/check_layout_contracts.py`
  - Verifies the common design tokens: 1000px page frame, 764px reader column, and white reader background.
  - Verifies that the main entrypoints and shared templates load `assets/design-tokens.css`.
  - Verifies that home, work, read/source, notes, and study CSS preserve the page-frame and reader-column contracts.
- `scripts/rebuild_all.py`
  - Runs the layout contract check as part of the normal check sequence.

This static gate does not replace browser screenshot QA. It prevents accidental drift in the structural layout contract while the browser QA pass remains a separate product-facing task.

## 2026-06-05 release contract gate

The Git upload policy now has a reproducible release check.

- `docs/release_handoff.md`
  - Documents which files belong in Git and which local corpus/generated files must stay out.
  - Documents how another machine can point to external source corpora through `PHILOSOPHY_CRAWL_ROOT`.
  - Provides a pre-push command list.
- `scripts/check_release_contracts.py`
  - Verifies source corpus folders and generated search/segment artifacts are ignored.
  - Verifies forbidden large/generated/local files are not tracked.
  - Verifies tracked files stay under the release-size threshold.
  - Verifies the README handoff instructions still exist.
- `README.md` and `reader_site/README.md`
  - Link the release policy and include the release contract check in the validation flow.

This gate proves release readiness policy, not an actual GitHub push. Branch selection, staging, commit, and push remain separate user-visible release actions.

## 2026-06-05 AI provenance policy gate

AI/Gemma interpretation remains intentionally inactive, but it now has a provenance policy and contract check.

- `docs/ai_interpretation_policy.md`
  - Defines the non-replacement rule: generated interpretation is not source text.
  - Defines source target boundaries, required JSONL fields, model/prompt metadata, source text checksums, UI labels, privacy boundaries, and pre-implementation gates.
- `.gitignore`
  - Ignores generated AI interpretation JSONL/SQLite files under `reader_site/data/ai/`.
- `reader_site/data/ai/.gitkeep`
  - Keeps the local AI storage directory visible without tracking generated output.
- `scripts/check_provenance_contracts.py`
  - Verifies the policy document, required schema fields, generated-output ignore rules, and the absence of premature `/api/ai`, `/api/gemma`, or `/api/interpret` routes.
- `scripts/rebuild_all.py`
  - Runs the provenance contract check with the other project checks.

The next AI step, if desired, is not "turn on Gemma" in the reader body. It is a small prototype that resolves one selected segment, computes `source_text_sha256`, sends only that bounded source text to the model, stores the result under `data/ai/`, and renders it with a visible "Generated interpretation" label.

## 2026-06-05 search ranking refinement

Segment search now uses a stronger ranking score on top of SQLite FTS5.

- `services/search.py`
  - Adds phrase-match boosts for exact source-language phrases.
  - Adds title/label boosts so direct heading and title matches remain visible.
  - Adds segment-type boosts so substantive paragraphs, verses, and blocks are not buried by generic hits.
  - Preserves FTS5 ordering as a smaller signal rather than ignoring it entirely.
  - Applies the same scoring shape to SQLite FTS5, SQLite LIKE fallback, and JSONL fallback.
- `scripts/check_search_contracts.py`
  - Adds representative ranking checks for `ressentiment`, `Gut Böse`, `language game`, and `Gud`.
  - Keeps direct Bible lookup, LXX/deuterocanonical aliases, work alias ranking, filters, and note search checks intact.

This is a first-pass relevance improvement. Translation or semantic search is still out of scope for the current source-text FTS index.

## 2026-06-05 release stage manifest

GitHub upload preparation now has a staging review manifest.

- `scripts/build_release_stage_manifest.py`
  - Reads `git status --porcelain -uall`.
  - Classifies changed paths as `stage`, `review`, or `block`.
  - Blocks local source corpus folders, generated segment/search artifacts, personal notes, generated AI outputs, env files, local manifests, and over-large tracked files.
  - Recognizes expected release categories such as app code, scripts, templates, docs, UI assets, entrypoints, and small metadata.
  - Supports `--write` for a local JSON file at `data/release_stage_manifest.local.json`.
- `.gitignore`
  - Ignores `reader_site/data/release_stage_manifest.local.json`.
- `docs/release_handoff.md`, root `README.md`, and `reader_site/README.md`
  - Include the stage manifest check in the pre-push flow.

Current result: 70 changed paths are classified as `stage`, with 0 `review` and 0 `block`. No staging, commit, or push was performed.

## 2026-06-05 headless browser layout QA

The in-app browser runtime was unavailable, so the visual pass used local headless Edge screenshots against the running server at `http://127.0.0.1:8787`.

Screenshots checked:

- home desktop;
- home mobile;
- Nietzsche work page desktop;
- Nietzsche work page mobile;
- search desktop with `ressentiment`;
- notes desktop.

Findings:

- The 1000px page frame remains visually distinct from the gray background.
- The 764px white reader column is centered on desktop and folds inside the page frame on mobile.
- Search and notes pages render inside the same frame vocabulary.
- Mobile work-page QA found toolbar/citation overflow at the right edge.

Fix:

- `assets/reader-work.css`
  - Strengthened citation wrapping.
  - Added mobile toolbar grid wrapping.
  - Added mobile reader/card overflow protection.

Follow-up screenshot confirmed the work-page mobile toolbar no longer clips `Source mode`, and citation URLs remain visible.

## 2026-06-05 deuterocanonical search aliases

Bible search now handles more LXX/deuterocanonical aliases without changing generated metadata.

- `services/search.py`
  - Adds a shared `book_id` alias map for work alias search and Bible direct lookup.
  - Covers shorthand and alternate titles such as `Tob`, `Wis`, `Sir`, `Ecclesiasticus`, `EpJer`, `Psalm 151`, `Psalms of Solomon`, `Susanna`, `Bel and the Dragon`, and `Additions to Daniel`.
  - Lets direct lookup try chapter `0` when a single-chapter LXX work is entered naturally as chapter `1`.
- `scripts/check_search_contracts.py`
  - Verifies deuterocanonical direct lookup and work alias search cases.

## 2026-06-05 static route boundary

Static file resolution is now separated from `server.py`.

- `services/static_files.py`
  - Resolves `/`, `/category/...`, `/search`, `/notes`, `/study`, and asset paths to files under the reader site root.
  - Builds file response payloads with MIME type, charset, content length, and optional inline disposition.
  - Keeps site-root boundary checks out of the request handler.
- `server.py`
  - Delegates static target resolution and file payload construction to the service.
- `scripts/check_static_routes.py`
  - Verifies a real CSS asset, missing asset 404, and path traversal 403 in addition to page route smoke tests.

## 2026-06-05 notes API payload boundary

Notes and study API payload construction is now separated from `server.py`.

- `services/notes.py`
  - Adds query helpers for notes list/export and study list/export payloads.
  - Owns note create/update/delete record normalization, tag parsing, timestamp fields, legacy `author` compatibility, and work-target validation.
  - Keeps JSON, JSONL, Markdown, and study Markdown export shape in one service module.
- `server.py`
  - Keeps only HTTP payload reading, error-to-status mapping, and response sending for notes/study routes.
- `scripts/check_notes_contracts.py`
  - Verifies notes payload helpers, notes export helpers, study payload/export helpers, and update/delete request helpers.

## 2026-06-05 work page assembly boundary

Work page HTML assembly is now separated from `server.py`.

- `services/work_pages.py`
  - Selects the corpus-specific work model builder for Nietzsche, Bible, Kierkegaard, and Wittgenstein.
  - Applies the common `templates/work.html` template through `rendering/work_markup.py`.
  - Raises the same `ValueError`, `PermissionError`, and `FileNotFoundError` classes that the HTTP handler already maps to status codes.
- `server.py`
  - Keeps only `/work/<corpus_id>/<work_id>` request parsing, query variant extraction, error-to-status mapping, and response sending.
- `scripts/check_static_routes.py`
  - Verifies representative work routes for all four corpora: Nietzsche, Bible, Kierkegaard, and Wittgenstein.

## 2026-06-05 read/source response boundary

Reading and source viewer response decisions are now separated from `server.py`.

- `services/sources.py`
  - Adds response helpers for `/read` and `/source`.
  - Owns source path resolution, allowed suffix checks, corpus-root boundary checks, Markdown reading HTML rendering, source HTML rendering, and PDF inline-file decisions.
- `server.py`
  - Delegates read/source route decisions to the service and only maps exceptions to HTTP status codes.
- `scripts/check_static_routes.py`
  - Follows a real archive read/source link pair and verifies missing `/read` path returns 400.

## 2026-06-05 search query payload boundary

Search query normalization is now separated from `server.py`.

- `services/search.py`
  - Adds a query helper for `/api/search`.
  - Owns `q`, `corpus_id`, `work_id`, `variant_id`, and `limit` extraction from parsed query strings.
  - Keeps invalid limit fallback and `corpus_id` slug normalization alongside search runtime behavior.
- `server.py`
  - Delegates `/api/search` payload construction to the search service and only sends the JSON response.
- `scripts/check_search_contracts.py`
  - Verifies query helper behavior for corpus slug normalization and limit fallback/clamping.

## 2026-06-05 Bible segments API payload boundary

Bible segment API payload assembly is now separated from `server.py`.

- `corpora/catalogs.py`
  - Adds a query helper for `/api/bible/segments`.
  - Owns `work_id` extraction, missing-query empty payload behavior, Bible work validation, and segment list lookup.
- `server.py`
  - Delegates `/api/bible/segments` payload construction to the catalog layer and only maps errors to HTTP status codes.
- `scripts/check_api_contracts.py`
  - Verifies empty query behavior, Genesis segment payload shape, and missing-work errors.

## 2026-06-05 server boundary contract

The server/router boundary is now enforced by a dedicated check.

- `scripts/check_server_boundary.py`
  - Parses `server.py` with `ast`.
  - Rejects direct imports from low-level rendering and corpus work-model modules.
  - Rejects direct imports of note storage/export helpers, source rendering helpers, and the raw search runtime.
  - Verifies that the request handler imports the intended boundary helpers for static files, work pages, read/source responses, notes/study payloads, search payloads, and Bible segment payloads.
- `scripts/rebuild_all.py`
  - Runs the server boundary check before the other contract checks.

## 2026-06-05 completion audit

The current upgrade state is summarized in `docs/upgrade_completion_audit.md`.

- It records proven completed areas, partially complete areas, and remaining decisions.
- It uses contract checks, corpus counts, search DB readiness, and server-boundary checks as evidence.
- It now treats the foundational upgrade goal as complete after visual QA fallback, release handoff, GitHub PR creation, and AI/Gemma provenance policy work were verified.

## 2026-06-09 follow-up hardening

The post-review hardening pass added concrete gates for the remaining review items.

- `scripts/check_ai_records_contracts.py`
  - Validates local AI interpretation JSONL records against the documented schema before any generated interpretation UI is enabled.
- `data/search_eval_queries.json`
- `scripts/check_search_relevance.py`
  - Adds a small representative search relevance query set for cross-corpus regression checks.
- `scripts/check_visual_smoke.py`
  - Starts the local reader on a temporary port and captures desktop/mobile browser screenshots for key routes.
- `scripts/build_artifact_manifest.py`
  - Disables argparse abbreviation and adds an explicit non-writing `--check` mode.
- `runtime_status.py`
  - Updates recommended next work so visual QA is treated as an automated smoke workflow plus targeted product review, not as an unresolved foundational blocker.

## 2026-06-09 source-light CI and publication boundary

The next hardening pass prioritized repo reproducibility and public-source boundaries over adding reader features.

Rationale:

- Clean-clone reproducibility and source-publication boundaries are prerequisites for a safe public repository.
- Search, notes, schema, and layout already have local deterministic contracts.
- Full corpus rebuilds cannot run in public CI because source corpora and generated segment/search artifacts are intentionally excluded.
- Reader UX and AI/Gemma features should build on the source-light contracts rather than widening the release surface first.

Implemented:

- `.github/workflows/reader-site-source-light.yml`
  - Runs the source-light clean clone checks on pull requests and pushes.
  - Uses `actions/checkout@v6`, `actions/setup-python@v6`, `ubuntu-latest`, and Python 3.13.
  - Points `PHILOSOPHY_CRAWL_ROOT` at an empty temporary directory so CI proves the public clone shape, not local corpus availability.
- `scripts/check_ci_contracts.py`
  - Verifies the workflow stays source-light and does not invoke source-heavy rebuild/search/static route checks.
- `docs/source_publication_policy.md`
- `scripts/check_source_publication_contracts.py`
  - Makes the publication boundary explicit: tracked metadata may contain source paths, URLs, labels, and license notes, but must not contain full source text, generated segments, personal notes, or generated AI output.
- `scripts/check_clean_clone_contracts.py`
  - Includes CI and source-publication checks in the source-light command set.

## 2026-06-09 source target resolver gate

The next pass kept the clean-clone contract source-light while adding a local full-restore check for exact reading targets.

Implemented:

- `services/source_targets.py`
  - Resolves corpus/work/variant/segment tuples from regenerated segment JSONL files.
  - Returns the reader URL, source `text_raw`, preview text, and `source_text_sha256`.
- `scripts/check_source_target_contracts.py`
  - Verifies representative Nietzsche, Bible, Kierkegaard, and Wittgenstein source targets.
  - Verifies that missing targets fail explicitly instead of silently returning an unrelated segment.
- `scripts/check_provenance_contracts.py`
  - Now checks that the source target resolver and validator exist before any AI/Gemma route is enabled.
- `scripts/rebuild_all.py`
  - Runs source target contracts as part of local full rebuild validation.

Boundary:

- This check is intentionally not part of source-light CI because it requires regenerated local segment JSONL files.
- Clean clones still prove structure, docs, GitHub Actions, publication boundaries, encoding, layout, server boundaries, and AI record contracts without local corpora.

## 2026-06-09 restore readiness gate

The next pass added a command-line check for the other side of clean-clone reproducibility: after a public clone is connected to local source corpora, the project should be able to prove that the restored local environment is actually usable.

Implemented:

- `scripts/check_restore_readiness.py`
  - Verifies all four source roots.
  - Verifies the primary output folder expected by each corpus builder.
  - Verifies metadata and segment artifacts exist and are non-empty.
  - Verifies the portable search index and SQLite search database exist.
  - Verifies search records cover Nietzsche, Bible, Kierkegaard, and Wittgenstein.
  - Requires FTS5 by default, with `--allow-degraded-search` for environments that intentionally accept LIKE fallback.
- `scripts/rebuild_all.py`
  - Runs restore readiness as part of the full local rebuild check sequence.
  - Skips it when `--skip-search-db` is used, because that option deliberately permits a lighter rebuild.

Boundary:

- `check_restore_readiness.py` is a local full-restore gate, not a source-light CI gate.
- `check_clean_clone_contracts.py --run-source-light-checks` remains the public clone gate for environments without source corpora.

## 2026-06-09 path contract gate

The next small hardening pass addressed duplicated source-root knowledge without doing a broad path refactor.

Implemented:

- `scripts/check_path_contracts.py`
  - Verifies that runtime diagnostics, source serving, release checks, source-publication checks, encoding checks, and release-stage checks agree on the same four Korean source-root names.
  - Verifies that each runtime `primary_output` path matches the corresponding builder constant.
  - Runs as part of the source-light clean-clone command set because it validates code constants, not local corpus availability.
- `scripts/rebuild_all.py`
  - Runs path contracts with the other local checks.

This gives a stable guard before any future central path-configuration refactor.

## 2026-06-09 path configuration centralization

The follow-up pass used the path contract as a safety net and introduced the first central path configuration module.

Implemented:

- `path_config.py`
  - Defines `PHILOSOPHY_CRAWL_ROOT`, the four Korean source-root names, source-root paths, and primary output paths.
  - Exposes `CORPUS_ROOTS` and `PRIMARY_OUTPUTS` for runtime and validation modules.
- Runtime modules now import shared path constants:
  - `runtime_status.py`
  - `services/sources.py`
  - `corpora/archive.py`
  - `corpora/catalogs.py`
  - `corpora/work_models.py`
- Builder and validation scripts now import the same baseline:
  - metadata builders;
  - segment builders;
  - release stage, release, source-publication, clean-clone, encoding, and path checks.

This reduces the number of places where a future source-folder move can silently drift.
