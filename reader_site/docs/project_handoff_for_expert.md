# Personal Archive of Literature 인수인계 문서

작성일: 2026-05-28  
대상: 웹/데이터 구조를 이어받아 표준화·확장할 개발자 또는 디지털 인문학/문헌 데이터 전문가

## 1. 프로젝트 개요

이 프로젝트는 철학·문학·종교 원전을 개인 연구와 공부에 사용할 수 있도록 수집 자료를 웹 리더로 정리하는 작업이다.

현재 사이트명은:

```text
Personal Archive of Literature
```

현재 로컬 서버:

```text
http://127.0.0.1:8787/
```

주요 코드 위치:

```text
C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\reader_site
```

현재 사이트가 다루는 코퍼스:

| corpus_id | 표시명 | 현재 상태 |
|---|---|---|
| `nietzsche` | 니체 | Phase 1, Phase 2, Phase 2.5 적용 후 공통 work page 모델에 편입 |
| `bible` | 성경 | OSHB/SBLGNT/LXX 책 단위 work page와 절 앵커 적용 |
| `kierkegaard` | 키르케고르 | SKS 저작 단위 work page와 Text/Commentary/Textual Account variant 적용 |
| `wittgenstein` | 비트겐슈타인 | siglum 단위 work page와 source/IDP variant 적용 |

2026-06-04 현재 추가로 적용된 공통 기반:

- `/work/<corpus_id>/<work_id>` 공통 route가 네 코퍼스에 적용되어 있다.
- `/api/search`는 SQLite FTS5를 우선 사용하고, 성경 직접 참조 검색(`Gen 1:1`, `John 3:16`, `창 1:1`, `요 3:16`, `요일 5:7`, `lxx Gen 1:1`)을 지원한다.
- `/api/notes`는 `corpus_id` 중심의 조회/생성/수정/삭제를 지원한다.
- `/notes`는 전체 코퍼스의 개인 주석을 모아보고 직접 수정/삭제/검토 완료 처리할 수 있는 index page이다.
- `/api/study`는 reviewed notes를 corpus/work별 bundle로 묶어 반환한다.
- `/api/study/export`는 reviewed note bundle을 Markdown 또는 JSON으로 내보낸다.
- `/study`는 reviewed note bundle을 조용히 읽는 study-note view이다.
- `/api/notes/export`는 notes를 JSON, JSONL, Markdown으로 export한다.
- `/search`는 corpus/work/variant 필터를 제공하고, 검색 결과에서 work/target notes 페이지로 이동할 수 있다.

## 2. 현재 작업 단계 요약

### Phase 1: 읽기 가능한 서고 만들기

니체에 적용 완료.

완료된 항목:

- 니체 저작 카탈로그 수동 보정
- 발간 저작 / 시대착오적 고찰 / 후기 원고 / 강연·논문 / 유고 / 편지 분류
- raw source와 reading/work page 분리
- `javascript:;`, `about_the_edition` 등 Markdown 찌꺼기 제거
- `/work/nietzsche/M` 같은 작품 페이지 추가
- `#sec-1`, `#p-0001` 같은 절/문단 안정 앵커 생성
- 니체 Markdown 91개 UTF-8 검증

### Phase 2: 연구 가능한 서고 만들기

니체에 적용 완료.

완료된 항목:

- 문헌별 metadata JSON 생성
- 문단/절 안정 URL 기반 citation target 연결
- 인용 복사 UI
- 개인 주석 JSONL 저장
- 니체 개념 사전 초안

### Phase 2.5: 니체 연구 기능 안정화

니체 기준 모델 정리 완료.

완료된 항목:

- 작품 페이지 HTML 분리: `templates/nietzsche_work.html`
- 작품 페이지 CSS 분리: `assets/work-page.css`
- citation/note JS 분리: `assets/work-page.js`
- metadata 재생성 스크립트 추가: `scripts/build_nietzsche_metadata.py`
- 연구 모델 문서 추가: `docs/nietzsche_research_model.md`

## 3. 현재 파일 구조

중요 파일:

```text
reader_site/
  index.html
  app.js
  styles.css
  server.py
  README.md
  RESEARCH_UPGRADE_ROADMAP.md

  assets/
    header-strip.svg
    nietzsche-1882.jpg
    nietzsche-header-left.png
    work-page.css
    work-page.js

  templates/
    nietzsche_work.html

  scripts/
    build_nietzsche_metadata.py

  data/
    nietzsche_catalog.json
    nietzsche_metadata.json
    nietzsche_concepts.json
    nietzsche_encoding_report.json
    nietzsche_notes_schema.json
    notes/
      nietzsche_notes.jsonl

  docs/
    nietzsche_research_model.md
    corpus_standardization_review.md
    project_handoff_for_expert.md
```

원본/수집 데이터 위치:

```text
C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\니체_원서수집
C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\성경_원서수집
C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\키르케고르_원서수집
C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\비트겐슈타인_원서수집
```

주의:

- 원본 수집 파일은 직접 수정하지 않는 방향이다.
- 표시용/연구용 구조는 `reader_site/data`, `reader_site/templates`, `reader_site/assets`, `reader_site/scripts` 쪽에서 만든다.

## 4. 서버 구조

메인 서버:

```text
server.py
```

실행:

```powershell
python .\server.py --port 8787
```

주요 역할:

- 네 코퍼스의 파일 목록을 읽어 `/api/archive` 생성
- 정적 파일 제공
- `/source?path=...` raw source viewer 제공
- `/read?path=...` 기본 Markdown reading viewer 제공
- `/work/<corpus_id>/<work_id>` 공통 작품 페이지 제공
- corpus별 metadata API 제공
- search, notes, health, artifact API 제공

현재 라우트:

| 라우트 | 역할 |
|---|---|
| `/` | 루트 카테고리 목록 |
| `/category/<corpus_id>` | 코퍼스별 섹션/링크 목록 |
| `/work/<corpus_id>/<work_id>` | 공통 작품 페이지 |
| `/search` | 전체 코퍼스 검색 페이지 |
| `/notes` | 전체 코퍼스 주석 index/export 페이지 |
| `/study` | reviewed notes 읽기 화면 |
| `/read?path=<path>` | Markdown 읽기 화면 |
| `/source?path=<path>` | raw source 확인 화면 |
| `/api/archive` | 전체 archive 구조 |
| `/api/health` | 로컬 원천/산출물/search readiness 진단 |
| `/api/artifacts` | 생성 산출물 manifest payload |
| `/api/search?q=<query>` | cross-corpus segment 검색 |
| `/api/notes?corpus_id=nietzsche&work_id=M` | corpus별 notes 조회 |
| `POST /api/notes` | notes 저장 |
| `PUT /api/notes/<note_id>` | notes 수정 |
| `DELETE /api/notes/<note_id>` | notes 삭제 |
| `/api/notes/export?format=markdown` | notes export |
| `/api/study` | reviewed notes bundle |
| `/api/study/export?format=markdown` | reviewed notes bundle export |

중요한 제한:

- legacy `author=nietzsche` 형태는 호환용으로만 남아 있다.
- 새 코드와 새 문서는 `corpus_id` 중심으로 작성해야 한다.

## 5. 현재 코퍼스 상태

현재 `/api/archive` 기준:

| 코퍼스 | 파일/링크 수 | 섹션 |
|---|---:|---|
| 니체 | 91 | 주요 발간 저작 13, 시대착오적 고찰 4, 후기 원고 4, 강연·논문 12, 유고 20, 편지 38 |
| 성경 | 125 files / 124 links | Hebrew Bible 40, Greek NT 28, LXX/Deuterocanon 56 |
| 키르케고르 | 630 | Text 211, Commentary 210, Textual Account 209 |
| 비트겐슈타인 | 1228 files / 1227 links | IDP diplomatic 179, IDP linear 179, Source normalized 332, Source diplomatic 332, Metadata 205 |

### 니체

현재 가장 많이 정리된 기준 모델이다.

source 위치:

```text
니체_원서수집\nietzsche\nietzsche\output
  works\
  nachlass\
  briefe\
```

적용된 구조:

- `works/*.md` 중 33개 저작을 수동 카탈로그로 분류
- 주요 발간 저작은 `/work/nietzsche/<work_id>`로 연결
- 유고/편지는 아직 `/read?path=...` 수준

니체 work_id 예:

| work_id | 작품 |
|---|---|
| `M` | Morgenröthe / 아침놀 |
| `FW` | Die fröhliche Wissenschaft / 즐거운 학문 |
| `JGB` | Jenseits von Gut und Böse / 선악의 저편 |
| `GM` | Zur Genealogie der Moral / 도덕의 계보 |
| `Za-I`~`Za-IV` | Also sprach Zarathustra I~IV |

### 성경

현재는 소스/책별 Markdown 목록 수준이다.

source 위치:

```text
성경_원서수집\bible\bible\output
  markdown\
    core_original\
      hebrew_bible_oshb\
      greek_nt_sblgnt\
    lxx_and_deuterocanon\
      lxx_swete\
  mapping\
    canonical_books.csv
    book_aliases.csv
    canon_layers.csv
    source_inventory.csv
    versification_map.csv
```

현재 Markdown 예:

```md
# Genesis / 창세기

## Chapter 1

**Gen.1.1**
...
```

성경은 니체식 section/paragraph 모델이 아니라 책/장/절 모델이 맞다.

권장 모델:

```text
corpus_id: bible
work_id: oshb.Gen 또는 sblgnt.Matt
variant_id: oshb_morphhb, sblgnt, lxx_swete
segment_id: Gen.1.1
segment_type: verse
```

### 키르케고르

현재는 SKS raw JSON을 `Text / Commentary / Textual Account`로 나눠 노출한다.

source 위치:

```text
키르케고르_원서수집\kierkegaard\kierkegaard\data\kierkegaard\raw\texts
```

샘플 구조:

```text
texts\aas\text\sks-aas-txt-root.json
texts\aas\commentary\sks-aas-kom-root.json
texts\aas\textual_account\sks-aas-txr-root.json
```

권장 모델:

```text
corpus_id: kierkegaard
work_id: aas
variant_id: text, commentary, textual_account
segment_id: SKS 내부 node/section id
```

핵심은 주석과 본문비평을 별개 작품처럼 취급하지 않고, 한 작품 페이지 안에서 탭/연결 레이어로 보여주는 것이다.

### 비트겐슈타인

현재는 export kind별 목록 수준이다.

source 위치:

```text
비트겐슈타인_원서수집\wittgenstein\wittgenstein\output
  _manifest.json
  idp_diplomatic\
  idp_linear\
  source_normalized\
  source_diplomatic\
  metadata\
```

manifest record는 `kind`, `siglum`, `variant`, `source_url`, `raw_path`, `output_md`, `license`, `rights_note` 등을 가진다.

권장 모델:

```text
corpus_id: wittgenstein
work_id: siglum 또는 source item id
variant_id: idp_diplomatic, idp_linear, source_normalized, source_diplomatic
segment_id: source page/block id
```

비트겐슈타인은 저작명보다 원고/전사본/정규화본 관계가 중요하다.

## 6. 데이터 구조화 방식

### 6.1 현재 니체 카탈로그

파일:

```text
data/nietzsche_catalog.json
```

역할:

- 원본 파일명 정렬을 연구용 분류로 바꿈
- `works/*.md`를 발간 저작/후기 원고/강연·논문 등으로 그룹화
- 사용자에게 보이는 제목과 한국어 보조 정보를 제공

구조:

```json
{
  "sections": [
    {
      "id": "major_published_books",
      "title": "주요 발간 저작",
      "meta": "...",
      "works": [
        {
          "file": "M.md",
          "label": "Morgenröthe",
          "meta": "1881 · 아침놀"
        }
      ]
    }
  ]
}
```

### 6.2 현재 니체 metadata

파일:

```text
data/nietzsche_metadata.json
```

생성:

```powershell
python .\scripts\build_nietzsche_metadata.py
```

검증:

```powershell
python .\scripts\build_nietzsche_metadata.py --check
```

역할:

- 작품별 title, source path, URL, SHA256, heading/paragraph count, concept ids 저장
- 작품 페이지와 나중의 검색/인용/주석 기능의 기반

현재 한계:

- 니체 전용 필드명과 생성 로직이다.
- 다른 코퍼스 적용 전 공통 schema로 일반화해야 한다.

### 6.3 현재 니체 concept seed

파일:

```text
data/nietzsche_concepts.json
```

역할:

- 작품과 연결되는 개념 사전 초안
- 예: Genealogy, Ressentiment, Free Spirit, Eternal Recurrence

현재 한계:

- seed 수준이다.
- 위치/문단 기반 개념 연결은 아직 없다.

### 6.4 현재 notes

스키마 문서:

```text
data/nietzsche_notes_schema.json
docs/nietzsche_research_model.md
```

저장 위치:

```text
data/notes/nietzsche_notes.jsonl
```

현재 record:

```json
{
  "id": "hex uuid",
  "created_at": "local ISO timestamp",
  "author": "nietzsche",
  "work_id": "M",
  "target_id": "sec-1",
  "target_label": "§ 1",
  "quote": "",
  "note": "",
  "tags": [],
  "url": "/work/nietzsche/M#sec-1"
}
```

확장 권장 record:

```json
{
  "id": "hex uuid",
  "created_at": "local ISO timestamp",
  "corpus_id": "nietzsche",
  "work_id": "M",
  "variant_id": "",
  "target_id": "sec-1",
  "target_type": "section",
  "target_label": "§ 1",
  "quote": "",
  "note": "",
  "tags": [],
  "url": "/work/nietzsche/M#sec-1"
}
```

## 7. 현재 UI/레이아웃 구조

현재 레이아웃 원칙:

```text
background area: 회색
page frame: 1000px
reader container: 764px, 흰색
```

홈/카테고리 페이지:

- `index.html`
- `styles.css`
- `app.js`

공통 작품 페이지:

- `templates/work.html`
- `assets/reader-work.css`
- `assets/reader-work.js`

주의:

- `templates/nietzsche_work.html`, `assets/work-page.css`, `assets/work-page.js`는 과거 Phase 2.5 산출물이었으나 현재 제거되었다.
- 현재 공통 route는 `templates/work.html`과 `assets/reader-work.*`를 사용한다.

## 8. 현재 표준화가 필요한 지점

### 8.1 라우트 표준화

완료된 기준:

```text
/work/nietzsche/<work_id>
/work/bible/<work_id>
/work/kierkegaard/<work_id>
/work/wittgenstein/<work_id>
/api/nietzsche/metadata
/api/nietzsche/concepts
/api/notes?corpus_id=nietzsche&work_id=M
```

권장:

```text
/work/<corpus_id>/<work_id>
/api/<corpus_id>/metadata
/api/<corpus_id>/concepts
/api/notes?corpus_id=<corpus_id>&work_id=<work_id>
```

### 8.2 template 표준화

현재:

```text
templates/nietzsche_work.html
```

권장:

```text
templates/work.html
```

단, 내부에는 코퍼스별 slot을 둔다.

예:

```text
{{VARIANT_TABS}}
{{CONCEPTS}}
{{SOURCE_NOTICE}}
{{RIGHTS_NOTICE}}
{{READING_BODY}}
```

### 8.3 metadata schema 표준화

모든 코퍼스가 다음 공통 필드를 가져야 한다.

```json
{
  "schema_version": 1,
  "corpus_id": "bible",
  "generated_at": "...",
  "works": {
    "oshb.Gen": {
      "corpus_id": "bible",
      "work_id": "oshb.Gen",
      "title": "Genesis",
      "display_title": "Genesis / 창세기",
      "category_id": "hebrew_bible",
      "category_title": "Hebrew Bible",
      "language": "hbo",
      "source_path": "...",
      "work_url": "/work/bible/oshb.Gen",
      "source_url": "/source?path=...",
      "segment_scheme": "chapter_verse",
      "variant_ids": ["oshb_morphhb"],
      "license": "...",
      "sha256": "...",
      "concept_ids": []
    }
  }
}
```

### 8.4 segment schema 표준화

권장:

```json
{
  "segment_id": "Gen.1.1",
  "segment_type": "verse",
  "work_id": "oshb.Gen",
  "variant_id": "oshb_morphhb",
  "order": 1,
  "label": "Genesis 1:1",
  "text_preview": "..."
}
```

코퍼스별 segment scheme:

| 코퍼스 | scheme | 예 |
|---|---|---|
| 니체 | `section_paragraph` | `sec-1`, `p-0001` |
| 성경 | `chapter_verse` | `Gen.1.1` |
| 키르케고르 | `sks_node` | SKS internal id |
| 비트겐슈타인 | `transcription_block` | page/block/source id |

### 8.5 notes API 표준화

현재 notes는 니체 전용이다.

전문가가 먼저 고쳐야 할 부분:

- `author` -> `corpus_id`
- 저장 파일도 `data/notes/<corpus_id>_notes.jsonl` 또는 단일 `data/notes/notes.jsonl` 중 결정
- note target에 `variant_id`, `target_type` 추가

### 8.6 citation 표준화

현재 citation은 단순 문자열이다.

권장:

- Phase 3까지는 단순 문자열 유지
- Phase 4에서 CSL/Zotero export 고려

코퍼스별 citation 예:

```text
Nietzsche:
Friedrich Nietzsche, Morgenröthe (M), § 1. Personal Archive of Literature. /work/nietzsche/M#sec-1

Bible:
Genesis 1:1, OSHB MorphHB. Personal Archive of Literature. /work/bible/oshb.Gen#Gen.1.1

Kierkegaard:
Søren Kierkegaard, Aabenbart Skriftemaal, Text. Personal Archive of Literature. /work/kierkegaard/aas#...

Wittgenstein:
Ludwig Wittgenstein, MS/TS item, normalized transcription. Personal Archive of Literature. /work/wittgenstein/...#...
```

## 9. 전문가에게 전달할 핵심 판단

### 판단 1. 모든 자료를 니체식으로 맞추면 안 된다

니체는 저작 중심이다.  
성경은 책/장/절 중심이다.  
키르케고르는 본문/주석/본문비평 관계 중심이다.  
비트겐슈타인은 원고/전사본 variant 중심이다.

따라서 표준화 대상은 "자료 구조의 의미"가 아니라:

- URL 규칙
- metadata schema
- notes/citation API
- reader shell layout
- source/raw 보존 원칙

이다.

### 판단 2. 성경이 다음 확장 대상으로 가장 적합하다

성경은 이미:

- canonical book map
- book aliases
- versification map
- source inventory
- Markdown book files

이 존재한다.

따라서 니체 다음에는 성경이 가장 확장하기 쉽다.

### 판단 3. 키르케고르와 비트겐슈타인은 variant/tab 모델 이후가 좋다

키르케고르와 비트겐슈타인은 단일 reading body보다 variant 관계가 중요하다.

먼저 공통 work page에 variant tabs를 만들고 적용하는 편이 좋다.

## 10. 권장 다음 작업

### Step 1. 공통 work page 모델 일반화

완료:

```text
templates/work.html
assets/reader-work.css
assets/reader-work.js
```

서버는 corpus별 model builder를 거쳐 공통 renderer로 보낸다.

### Step 2. notes API 일반화

완료:

```text
GET /api/notes?corpus_id=nietzsche&work_id=M
POST /api/notes
PUT /api/notes/<note_id>
DELETE /api/notes/<note_id>
GET /api/notes/export?format=markdown
```

POST payload는 `corpus_id`, `variant_id`, `target_type`을 받는다.

### Step 3. 성경 metadata builder 작성

추가할 파일:

```text
scripts/build_bible_metadata.py
data/bible_metadata.json
```

성경 work_id 예:

```text
bible.oshb.Gen
bible.sblgnt.Matt
bible.lxx.Gen
```

또는 더 짧게:

```text
oshb.Gen
sblgnt.Matt
lxx.Gen
```

둘 중 하나를 먼저 결정해야 한다.

권장:

```text
oshb.Gen
sblgnt.Matt
lxx.Gen
```

이유:

- corpus_id가 이미 `bible`이므로 work_id에 `bible.`을 반복할 필요가 없다.
- source variant가 앞에 있어 성경 내 소스 구분이 쉽다.

### Step 4. 성경 work page 추가

예:

```text
/work/bible/oshb.Gen
/work/bible/sblgnt.Matt
/work/bible/lxx.Gen
```

segment:

```text
#Gen.1.1
#Matt.1.1
```

### Step 5. variant tabs 도입

성경 이후, 키르케고르와 비트겐슈타인을 위해 공통 work page에 variant tabs를 도입한다.

예:

```text
Kierkegaard:
[Text] [Commentary] [Textual Account]

Wittgenstein:
[Diplomatic] [Linear] [Normalized] [Metadata]
```

## 11. 검증 명령

서버 컴파일:

```powershell
python -m py_compile .\server.py
```

니체 metadata 재생성:

```powershell
python .\scripts\build_nietzsche_metadata.py
```

니체 metadata 최신성 확인:

```powershell
python .\scripts\build_nietzsche_metadata.py --check
```

JSON 검증:

```powershell
python -m json.tool .\data\nietzsche_metadata.json > $null
python -m json.tool .\data\nietzsche_concepts.json > $null
python -m json.tool .\data\nietzsche_notes_schema.json > $null
```

서버 실행:

```powershell
python .\server.py --port 8787
```

브라우저 확인:

```text
http://127.0.0.1:8787/
http://127.0.0.1:8787/category/nietzsche
http://127.0.0.1:8787/work/nietzsche/M#sec-1
```

## 12. 리스크와 주의사항

### 원본 보존

원본 코퍼스 파일은 수정하지 않는다.  
정리본, metadata, notes, concept, segment는 `reader_site/data`에서 관리한다.

### 권리/라이선스

비트겐슈타인 WAB 자료는 restricted/all-rights-reserved 성격이 있다.  
공유/export 기능을 붙일 때 source rights note를 반드시 고려해야 한다.

### 코퍼스별 의미 보존

성경, 키르케고르, 비트겐슈타인을 모두 "작품 Markdown"으로 평탄화하면 연구 가치가 떨어진다.

반드시 다음 차이를 유지한다.

- 성경: 본문 소스와 canon layer
- 키르케고르: text/commentary/textual_account 관계
- 비트겐슈타인: transcription variant와 source metadata

### 서버 구조

현재 서버는 단일 `server.py` 기반이다.  
기능이 더 커지면 다음 분리가 필요하다.

```text
reader_site/
  server.py
  core/
    archive.py
    render.py
    notes.py
    metadata.py
  corpora/
    nietzsche.py
    bible.py
    kierkegaard.py
    wittgenstein.py
```

단, 지금 당장 과한 리팩터링보다 공통 work page 모델과 notes API 일반화가 우선이다.

## 13. 한 줄 요약

현재 프로젝트는 니체를 기준 모델로 Phase 2.5까지 구현되어 있다. 다음 전문 작업은 니체 전용 구조를 공통 work page/metadata/notes 모델로 일반화한 뒤, 성경의 책/장/절 구조에 먼저 적용하는 것이다.

## 14. 2026-06-04 현재 구현 업데이트

이 문서 작성 이후 공통화 작업이 더 진행되었다. 현재 코드는 니체 전용 구조에서 벗어나 네 개 코퍼스 모두에 공통 work page route를 제공한다.

현재 확인된 대표 route:

```text
/work/nietzsche/M
/work/bible/oshb.Gen
/work/kierkegaard/aas
/work/wittgenstein/Ms-101
```

현재 주요 모듈:

```text
reader_site/
  server.py
  runtime_status.py
  corpora/
    archive.py
    catalogs.py
    work_models.py
  rendering/
    documents.py
    static_pages.py
    work_markup.py
  services/
    notes.py
    search.py
    sources.py
```

역할:

- `server.py`: HTTP route, note/search API glue, static file response, work response, read/source error mapping을 담당한다.
- `corpora/archive.py`: `/api/archive` root/category index를 구성한다.
- `corpora/catalogs.py`: metadata loading, work validation, Bible segment lookup을 담당한다.
- `corpora/work_models.py`: corpus별 work page model을 만든다.
- `rendering/documents.py`: Markdown, Bible verse, Kierkegaard JSON, generic segment를 HTML reading body로 변환한다.
- `rendering/work_markup.py`: 공통 work page template 치환, TOC, concepts, variant tabs, source notice를 담당한다.
- `services/search.py`: SQLite FTS5, LIKE fallback, JSONL fallback 검색을 담당한다.
- `services/notes.py`: corpus별 notes JSONL 읽기/쓰기/필터/수정/삭제를 담당한다.
- `services/sources.py`: source path validation과 `/read`, `/source` HTML assembly를 담당한다.
- `docs/api_reference.md`: `/api/archive`, `/api/health`, `/api/artifacts` 응답 구조를 문서화한다.
- `scripts/check_api_contracts.py`: runtime API payload의 필수 schema를 검사한다.
- `scripts/check_search_contracts.py`: search filter와 Bible direct lookup 동작을 검사한다.
- `scripts/check_notes_contracts.py`: notes 저장, 필터, 수정, 삭제 동작을 검사한다.

현재 검증 수치:

```text
nietzsche      6 archive sections, 91 links, 91 files
bible          3 archive sections, 121 links, 122 files
kierkegaard    1 archive section, 211 links, 630 source files
wittgenstein   2 archive sections, 202 links, 1228 source files
search         225,442 records, SQLite FTS5 enabled
```

현재 남은 우선 과제:

1. deuterocanon/alternative title alias, notes search, corpus별 ranking 등 검색 품질을 개선한다.
2. reviewed notes 기반 요약/인쇄용 출력 bundle을 개선한다.
3. search regression check를 더 넓힌다.
4. 공통 page frame과 corpus별 visual identity를 분리한다.
5. route table이 더 커질 경우 static file serving과 API dispatch를 별도 route module로 분리한다.

## 2026-06-05 Reproducibility Addendum

The project now has a single local rebuild command:

```powershell
cd C:\Users\PP\PROJECT\0.philosophy\philosophy_crawl\reader_site
python .\scripts\rebuild_all.py
```

This command runs the metadata builders, segment builders, search index/database builders, artifact manifest builder, and contract checks in order. For lighter runs, use:

```powershell
python .\scripts\rebuild_all.py --skip-search-db
python .\scripts\rebuild_all.py --skip-manifest --no-checks
```

Additional contract gate:

```powershell
python .\scripts\check_static_routes.py
```

That route test boots a temporary local HTTP server and checks the archive page, category page, search, notes, study, a representative work page, `/api/health`, and `/api/study`.
