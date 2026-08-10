# Corpus Standardization Review

작성일: 2026-05-28

2026-06-04 현재 상태:

- 이 문서의 권장 방향 중 공통 route, 공통 work page, `reader-work.css/js`, `corpus_id` 중심 notes API는 이미 적용되었다.
- 현재 공통 route는 `/work/<corpus_id>/<work_id>`이고, notes API는 `/api/notes?corpus_id=<corpus_id>&work_id=<work_id>`이다.
- `templates/nietzsche_work.html`, `assets/work-page.css`, `assets/work-page.js` 언급은 Phase 2.5 당시의 과거 기준으로 읽어야 한다. 현재 파일은 공통 `templates/work.html`, `assets/reader-work.css`, `assets/reader-work.js`로 대체되었다.
- 다음 표준화 과제는 legacy 파일 정리, notes dashboard 직접 편집, 검색 ranking/alias 확장, corpus별 visual identity 분리이다.

## 결론

니체에서 만든 구조는 좋은 기준 모델이지만, 그대로 성경·키르케고르·비트겐슈타인에 복사하면 안 된다.

필요한 것은 하나의 획일적 자료 모델이 아니라:

1. 공통 리더 셸
2. 공통 연구 기능
3. 코퍼스별 metadata builder
4. 코퍼스별 segment 규칙
5. 코퍼스별 citation 규칙

즉, 방향은 다음이 가장 안정적이다.

```text
공통 UI/연구 기능은 표준화
자료 해석 단위는 코퍼스별로 유지
```

## 현재 니체 기준 모델

니체에는 다음 구조가 이미 적용되어 있다.

- 카테고리 카탈로그: `data/nietzsche_catalog.json`
- 작품 metadata: `data/nietzsche_metadata.json`
- 개념 사전: `data/nietzsche_concepts.json`
- 주석 스키마: `data/nietzsche_notes_schema.json`
- 작품 페이지: `/work/nietzsche/<work_id>`
- 안정 앵커: `#sec-1`, `#p-0001`
- 원문 확인: `/source?path=...`
- 읽기/연구 UI:
  - `templates/nietzsche_work.html`
  - `assets/work-page.css`
  - `assets/work-page.js`

이 모델에서 다른 코퍼스로 가져갈 수 있는 것은 "레이아웃과 연구 기능"이다.

그대로 가져가면 안 되는 것은 "work_id와 segment를 해석하는 방식"이다.

## 표준화해야 할 공통 구조

### 1. 공통 라우트

권장 라우트:

```text
/category/<corpus_id>
/work/<corpus_id>/<work_id>
/work/<corpus_id>/<work_id>#<segment_id>
/source?path=<source_path>
/api/<corpus_id>/metadata
/api/<corpus_id>/concepts
/api/notes?corpus_id=<corpus_id>&work_id=<work_id>
```

현재 니체는 `/work/nietzsche/M`를 쓰고 있으므로 이 방향과 맞는다.

작성 당시 notes API는 `author=nietzsche` 중심이었다. 현재는 `corpus_id=nietzsche` 중심으로 일반화되어 있다.

### 2. 공통 work metadata

모든 코퍼스는 다음 최소 필드를 가져야 한다.

```json
{
  "schema_version": 1,
  "corpus_id": "nietzsche",
  "generated_at": "2026-05-28T00:00:00",
  "works": {
    "M": {
      "corpus_id": "nietzsche",
      "work_id": "M",
      "title": "Morgenröthe",
      "display_title": "Morgenröthe / 아침놀",
      "category_id": "major_published_books",
      "category_title": "주요 발간 저작",
      "language": "de",
      "source_path": "...",
      "work_url": "/work/nietzsche/M",
      "source_url": "/source?path=...",
      "segment_scheme": "section_paragraph",
      "variant_ids": [],
      "license": "",
      "sha256": "",
      "concept_ids": []
    }
  }
}
```

필드는 공통으로 유지하되, 값의 의미는 코퍼스별로 달라질 수 있다.

### 3. 공통 segment 규칙

segment는 인용과 주석의 최소 단위다.

공통 필드:

```json
{
  "segment_id": "sec-1",
  "segment_type": "section",
  "label": "§ 1",
  "work_id": "M",
  "order": 1,
  "text_preview": "..."
}
```

코퍼스별 권장 segment:

| 코퍼스 | work 단위 | segment 단위 |
|---|---|---|
| 니체 | 저작, 후기 원고, 강연 텍스트 | section, paragraph |
| 성경 | 책 + 본문 소스 | chapter, verse |
| 키르케고르 | SKS 저작 | text section, commentary note, textual account item |
| 비트겐슈타인 | 원고/타이프스크립트/컬렉션 항목 | manuscript section, page/block, transcription segment |

### 4. 공통 research panel

모든 작품 페이지에 같은 위치와 같은 기능을 둔다.

구성:

1. Citation
2. Notes
3. Concepts / Tags
4. Source mode
5. Contents

레이아웃:

```text
page frame, 1000px
  header image area
  reader container, 764px
    reader header
    toolbar
    contents
    research panel
    reading body
```

니체에서 만든 `assets/work-page.css`와 `assets/work-page.js`는 공통화 후보이다. 다만 파일명은 나중에 `reader-work.css`, `reader-work.js`처럼 바꾸는 편이 더 좋다.

### 5. 공통 note schema

현재 니체 notes는 아래 방식이다.

```json
{
  "author": "nietzsche",
  "work_id": "M",
  "target_id": "sec-1",
  "note": "...",
  "tags": []
}
```

확장용 표준은 이렇게 바꾸는 편이 좋다.

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

이렇게 해야 성경의 `Gen.1.1`, 키르케고르 주석, 비트겐슈타인 전사본에도 같은 notes API를 쓸 수 있다.

## 코퍼스별 적용 방식

### 니체

현재 상태:

- 가장 잘 정리됨.
- 작품 중심 모델이 잘 맞음.
- Phase 1, Phase 2, Phase 2.5가 기준 모델 역할을 할 수 있음.

다음 정리:

- `work-page.css/js`를 완전 공통 파일로 이름 변경
- notes API를 `author`가 아니라 `corpus_id` 중심으로 변경

### 성경

성경은 니체처럼 "저작 하나를 처음부터 끝까지 읽는 모델"도 가능하지만, 실제 연구 단위는 책/장/절이다.

권장 구조:

```text
corpus_id: bible
work_id: oshb/Gen 또는 sblgnt/Matt
variant_id: oshb_morphhb, sblgnt, lxx_swete
segment_id: Gen.1.1
segment_type: verse
```

화면 구조:

- 작품 페이지 = 성경 책 하나
- Contents = 장 목록
- Reading body = 절 단위
- Citation = `Genesis 1:1, OSHB`
- Concepts = creation, covenant, law, gospel 같은 주제 태그

주의:

- OSHB, SBLGNT, LXX는 서로 다른 본문 소스다.
- LXX/제2경전은 canon layer가 다르므로 Protestant canon과 한 화면에 억지로 합치면 안 된다.
- 성경은 `output/mapping/*.csv`가 이미 있으므로 metadata builder의 근거로 쓰면 좋다.

### 키르케고르

키르케고르는 `Text / Commentary / Textual Account`가 분리되어 있다. 이것을 별도 작품처럼 보여주면 읽기 흐름이 끊긴다.

권장 구조:

```text
corpus_id: kierkegaard
work_id: aas
variant_id: text, commentary, textual_account
segment_id: sks-aas-...
```

화면 구조:

- 작품 페이지 = SKS 저작 하나
- 상단 탭 = Text / Commentary / Textual Account
- Reading body = 본문
- Side/research area = 주석과 본문비평 연결

주의:

- 주석은 독립 텍스트라기보다 본문에 연결되는 레이어다.
- 따라서 키르케고르는 "variant tabs + linked commentary"가 핵심이다.

### 비트겐슈타인

비트겐슈타인은 작품보다 원고/전사본/정규화본 관계가 중요하다.

권장 구조:

```text
corpus_id: wittgenstein
work_id: siglum 또는 source item id
variant_id: idp_diplomatic, idp_linear, source_normalized, source_diplomatic
segment_id: source page/block id
```

화면 구조:

- 작품 페이지 = manuscript/siglum/item
- 상단 탭 = diplomatic / linear / normalized / metadata
- Citation = source URL과 local URL 모두 표시
- Concepts = language game, picture theory, grammar, rule-following 등

주의:

- WAB 자료는 rights note가 제한적이므로 export/공유 기능을 조심해야 한다.
- source metadata를 반드시 작품 페이지에 표시해야 한다.

## 구현 순서 제안

### Step 1. 공통 모델부터 정리

먼저 니체 전용 명칭을 공통 명칭으로 일반화한다.

- `templates/nietzsche_work.html` -> `templates/work.html`
- `assets/work-page.css` 유지 또는 `reader-work.css`로 변경
- `assets/work-page.js`를 `corpus_id` 기반으로 수정
- 완료: `/api/notes?author=nietzsche` 호환 형태에서 `/api/notes?corpus_id=nietzsche` 중심으로 이동

### Step 2. metadata builder 패턴 고정

현재:

```text
scripts/build_nietzsche_metadata.py
```

다음:

```text
scripts/build_bible_metadata.py
scripts/build_kierkegaard_metadata.py
scripts/build_wittgenstein_metadata.py
```

각 스크립트는 같은 schema를 출력하되, segment 규칙은 코퍼스별로 둔다.

### Step 3. 성경부터 확장

성경은 이미 책/장/절 구조가 명확하고 mapping CSV가 있으므로, 니체 다음 확장 대상으로 가장 적합하다.

성경에서 먼저 만들 것:

1. `data/bible_metadata.json`
2. `/work/bible/oshb.Gen`
3. `#Gen.1.1` verse anchor
4. citation preview
5. source/language/license 표시

### Step 4. 키르케고르와 비트겐슈타인은 variant model 확정 후 적용

이 둘은 단순 리더보다 "variant/tab 관계"가 중요하다.

- 키르케고르: text/commentary/textual_account
- 비트겐슈타인: diplomatic/linear/normalized/metadata

따라서 공통 work page에 variant tabs가 생긴 뒤 적용하는 것이 좋다.

## 판단

표준화가 필요하다. 다만 표준화 대상은 "내용 분류 방식"이 아니라 "페이지 구조, metadata schema, notes/citation API"다.

가장 좋은 다음 작업은:

```text
니체 전용 Phase 2.5 구조를 공통 work page 모델로 일반화한 뒤,
성경에 먼저 적용한다.
```

이렇게 하면 니체에서 만든 좋은 구조를 보존하면서도, 성경·키르케고르·비트겐슈타인의 고유 구조를 망가뜨리지 않을 수 있다.
