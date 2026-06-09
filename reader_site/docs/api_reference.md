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

루트 페이지와 `/category/<corpus_id>` 페이지가 사용하는 archive index이다.

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

## `GET /api/health`

현재 로컬 reader site 실행 상태를 빠르게 확인하는 endpoint이다.

최상위 필드:

```json
{
  "status": "ok",
  "generated_at": "2026-06-04T03:00:00+00:00",
  "site_root": "C:\\Users\\PP\\PROJECT\\0.philosophy\\philosophy_crawl\\reader_site",
  "corpus_root": "C:\\Users\\PP\\PROJECT\\0.philosophy\\philosophy_crawl",
  "corpora": [],
  "search": {},
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

Notes:

- `issues[]` is empty when `status` is `ok`.
- `next_recommended_upgrades[]` is advisory and may change as implementation work progresses.

## `GET /api/artifacts`

현재 로컬 생성 산출물 manifest를 반환한다. `scripts/build_artifact_manifest.py`가 파일로 쓰는 내용과 같은 계열의 payload이다.

최상위 필드:

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-04T03:00:00+00:00",
  "site_root": "C:\\Users\\PP\\PROJECT\\0.philosophy\\philosophy_crawl\\reader_site",
  "corpus_root": "C:\\Users\\PP\\PROJECT\\0.philosophy\\philosophy_crawl",
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

`regeneration_commands[]` currently lists the local commands needed to rebuild metadata, segments, search, and the local artifact manifest.

Example:

```powershell
python .\scripts\build_nietzsche_metadata.py
python .\scripts\build_bible_metadata.py
python .\scripts\build_bible_segments.py
python .\scripts\build_search_index.py
python .\scripts\build_search_db.py
python .\scripts\build_artifact_manifest.py
```

Notes:

- The HTTP API does not write `data/artifact_manifest.local.json`.
- To write the manifest, run `python .\scripts\build_artifact_manifest.py`.
- Use `--checksums` only when SHA-256 hashes are needed, because it reads large generated files.

## `GET /api/search`

Cross-corpus segment search. Backed by `data/search_index.sqlite` when available, with JSONL fallback.

Query parameters:

```text
q=<search text>
corpus_id=<optional corpus id>
work_id=<optional work id>
variant_id=<optional variant id>
limit=<1-100, default 30>
```

General response:

```json
{
  "query": "ressentiment",
  "count": 20,
  "engine": "sqlite-fts5",
  "results": [],
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
