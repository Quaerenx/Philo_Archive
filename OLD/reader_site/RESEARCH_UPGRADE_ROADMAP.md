# Personal Archive of Literature 고도화 로드맵

작성일: 2026-05-27

## 1. 현재 상태 요약

현재 사이트는 `Personal Archive of Literature`라는 이름 아래 네 개의 수집 컬렉션을 제공한다.

| 컬렉션 | 현재 섹션 | 문헌 링크 수 | 상태 |
|---|---:|---:|---|
| 니체 | 주요 발간 저작 / 시대착오적 고찰 / 후기 원고 / 강연·논문 / 유고 / 편지 | 91 | 1차 저작 카탈로그와 reading mode 적용 |
| 성경 | Hebrew Bible / Greek New Testament / LXX | 124 | 책/장/절 리더 고도화 가능 |
| 키르케고르 | Text / Commentary / Textual Account | 630 | 원문/주석/본문비평 구분 가능 |
| 비트겐슈타인 | IDP / Source / Metadata 계열 | 1,227 | 원고/전사본/메타데이터 구분 가능 |

현재 구현은 다음 단계에 있다.

- 홈: 루트 카테고리 목록
- 카테고리: 섹션별 파일 링크
- 읽기 뷰어: `/read?path=...`의 흰색 본문 컨테이너
- 원문 뷰어: `/source?path=...`의 raw source 확인 화면
- 데이터 생성: `server.py`가 파일시스템을 읽어서 `/api/archive` 생성
- 수동 보정: `data/nietzsche_catalog.json`이 니체 저작의 읽기용 분류를 제공

현재 병목은 "저작 단위 분류"에서 한 단계 더 나아가 "문단/절 단위 안정 주소, 인용, 주석"을 만드는 일이다.

## 2. 참고 사례와 근거

### Nietzsche Source

Nietzsche Source의 eKGWB는 니체의 저작, 유고, 편지를 디지털 비평판으로 제공한다. 특히 학술 인용을 위해 안정적인 URL과 통용 약어(sigla)를 쓴다는 점이 중요하다.

참고: https://doc.nietzschesource.org/en/ekgwb

적용점:

- 니체 파일명을 `M`, `FW`, `JGB` 같은 약어 그대로만 보여주지 말고, "아침놀 / Morgenröthe / M"처럼 저작명과 약어를 함께 표시한다.
- 각 저작·절·단락에 안정적인 내부 주소를 만든다.
- 원문 파일 경로보다 "저작 ID + 위치"를 인용 기준으로 삼는다.

### Scaife Viewer / Perseus

Scaife Viewer는 고전 텍스트를 원어와 번역 중심으로 읽게 하는 환경이다. 홈은 "Browse Library"와 "Text Search"로 시작하고, 고대 텍스트 컬렉션을 읽기 환경으로 제공한다.

참고: https://scaife-reader.perseus.tufts.edu/

적용점:

- 파일 목록보다 "작품 → 책/장/절/단락" 구조가 우선이어야 한다.
- 원어, 번역, 주석, 형태소 정보를 나란히 확장할 수 있는 구조가 필요하다.
- 성경, 고전철학, 문헌학 자료에 특히 적합하다.

### Sefaria

Sefaria는 텍스트를 검색 가능하고 상호 연결된 라이브러리로 제공하며, 사용자가 소스 시트를 만들고 API로 데이터를 재사용할 수 있게 한다.

참고: https://help.sefaria.org/hc/en-us/articles/17388247452956-What-is-Sefaria

적용점:

- 원전 간 연결을 일급 기능으로 둔다. 예: 바울-아우구스티누스-루터-니체, 플라톤-기독교-독일관념론.
- 개인 노트를 "소스 시트"처럼 만들 수 있게 한다.
- 특정 구절/문단에서 관련 문헌으로 이동할 수 있어야 한다.

### OpenITI

OpenITI는 GitHub 작업 버전과 Zenodo 릴리스를 구분한다. 연구 재현성을 위해 특정 릴리스 번호를 인용하도록 안내한다.

참고: https://openiti.org/documentation/

적용점:

- 수집 원본, 정리본, 주석본을 분리한다.
- 각 코퍼스 export에 생성일, 소스 commit, checksum, 내부 버전을 기록한다.
- "오늘 보는 원문"과 "논문에 인용할 고정판"을 구분한다.

### TEI

TEI Guidelines는 전자 텍스트 인코딩과 교환을 위한 대표 표준이다. TEI Header는 텍스트 자체, 소스, 인코딩, 수정 이력을 담을 수 있다.

참고: https://guidelines.tei-c.de/en/html/index.html

적용점:

- 당장 TEI 전체를 도입하지 않아도, TEI식 메타데이터 원칙을 따른다.
- 각 문헌에 `source`, `edition`, `language`, `license`, `revision`, `normalization` 필드를 둔다.
- 원문(raw)과 표시용(display/normalized)을 분리한다.

### IIIF

IIIF Presentation API는 이미지, 원고, 복합 디지털 객체를 사람이 볼 수 있는 구조로 제시하기 위한 표준이다.

참고: https://iiif.io/api/presentation/3.0/

적용점:

- 장기적으로 원고 이미지나 팩시밀리를 붙일 때 파일 경로가 아니라 manifest 단위로 연결한다.
- 텍스트 리더와 원본 이미지 뷰어를 분리하지 않고, 같은 작품 페이지에서 "읽기 / 원본 이미지 / 메타데이터"로 전환할 수 있게 한다.
- 비트겐슈타인 원고 이미지나 성경 사본 이미지 같은 시각 자료를 붙일 때 확장 경로가 열린다.

### W3C Web Annotation

W3C Web Annotation Data Model은 주석을 서로 다른 시스템에서 공유하고 재사용할 수 있는 구조로 표현한다.

참고: https://www.w3.org/TR/annotation-model/

적용점:

- 개인 주석을 단순 텍스트 파일이 아니라 "대상 문헌 + 위치 + 본문 + 태그 + 생성일" 구조로 저장한다.
- 나중에 Obsidian, Zotero, 다른 웹 리더와 연결할 수 있다.
- 원문을 직접 수정하지 않고 주석을 별도 레이어로 쌓는다.

### 학습 연구: 회상 연습과 개념 지도

Roediger와 Karpicke의 연구는 시험/회상 연습이 장기 기억을 강화한다는 근거를 제공한다. Karpicke와 Roediger의 2007년 연구도 반복 회상이 장기 보존의 핵심이라고 보고한다.

참고:

- https://journals.sagepub.com/doi/10.1111/j.1467-9280.2006.01693.x
- https://profiles.wustl.edu/en/publications/repeated-retrieval-during-learning-is-the-key-to-long-term-retent/

적용점:

- 단순 읽기보다 "읽은 뒤 질문 만들기", "개념 회상", "인용문 카드"가 필요하다.
- 원문 단락에서 바로 개인 질문/카드를 만들 수 있게 한다.
- 장기적으로는 spaced review나 Anki export까지 고려한다.

## 3. 사이트 정체성

현재 사이트는 "크롤링 결과물"에서 "개인 원전 연구 서고"로 넘어가는 중이다. 따라서 핵심 문장은 다음이 좋다.

> Personal Archive of Literature: 원전, 저자, 전통, 주석을 이어 읽는 개인 연구 서고.

이 정체성에서 중요한 것은 네 가지다.

1. 보관: 원문과 출처를 안정적으로 보존한다.
2. 읽기: 원전이 편안하게 읽혀야 한다.
3. 연구: 인용, 판본, 주석, 연결을 관리한다.
4. 학습: 읽은 내용을 회상·요약·질문으로 변환한다.

## 4. 정보구조 개선안

### 4.1 루트 카테고리

홈은 지금처럼 네 개 컬렉션을 보여주되, 장기적으로는 분야와 인물을 함께 제공한다.

- Authors: Nietzsche, Kierkegaard, Wittgenstein
- Traditions: Philosophy, Theology, Literature, Biblical Studies
- Languages: German, Greek, Hebrew, Latin, English
- Forms: Works, Letters, Fragments, Manuscripts, Commentary

### 4.2 니체 카테고리 재구성

니체는 폴더 기준보다 저작 성격 기준이 더 좋다.

권장 분류:

| 새 섹션 | 파일 |
|---|---|
| 주요 저작 | GT, MA-I, MA-II, M, FW, Za-I, Za-II, Za-III, Za-IV, JGB, GM, GD, WA |
| 후기/사후 출간 저작 | AC, EH, NW, DD |
| 시대착오적 고찰 | DS, HL, SE, WB |
| 초기 강연·논문·미완성 저작 | BA, CV, DW, GG, GMD, PHG, SGT, ST, WL, MD, NJ, IM |
| 유고 | NF-* |
| 편지 | BVN-* |

표시 형식:

```text
아침놀
Morgenröthe / M / 1881

즐거운 학문
Die fröhliche Wissenschaft / FW / 1882, 1887
```

구현 방식:

- `reader_site/data/nietzsche_catalog.json` 같은 수동 보정 카탈로그를 만든다.
- `server.py`의 `build_nietzsche()`가 이 카탈로그를 읽어 섹션을 생성한다.
- 원본 파일명은 숨기지 말고 메타데이터로 보존한다.

### 4.3 성경 카테고리

성경은 파일 링크가 아니라 책/장/절 리더가 중심이어야 한다.

권장 구조:

- Hebrew Bible
  - Torah
  - Prophets
  - Writings
- Greek New Testament
  - Gospels
  - Acts
  - Pauline Epistles
  - Catholic Epistles
  - Revelation
- Septuagint / Deuterocanon
  - LXX core
  - Deuterocanon
  - Additions

기능:

- 책 → 장 → 절 이동
- 원어 토큰 표시 토글
- lemma/morphology 패널
- 구절 단위 citation URL

### 4.4 키르케고르와 비트겐슈타인

키르케고르는 `Text / Commentary / Textual Account`를 유지하되, 같은 작품의 세 레이어를 묶어야 한다.

```text
작품 A
- Text
- Commentary
- Textual Account
```

비트겐슈타인은 manuscript/source 중심으로 다음 구조가 적합하다.

```text
원고/타입스크립트
- Diplomatic transcription
- Linear transcription
- Normalized source
- Metadata
```

## 5. 읽기 화면 개선안

현재 `/source`는 원문을 `<pre>`로 보여준다. 연구용으로는 세 모드가 필요하다.

### 5.1 Reading Mode

목적: 사람이 읽기 좋게 정리한 화면.

- `### [1.](javascript:;)` 같은 링크 찌꺼기 제거
- Markdown heading을 실제 제목으로 렌더링
- 문단 간격 정리
- 원문 텍스트만 표시
- 필요할 때만 경로/메타데이터 노출

### 5.2 Source Mode

목적: 수집된 파일을 그대로 검토.

- 현재 `<pre>` 방식 유지
- raw file path, checksum, source info 표시
- 디버깅/검증용

### 5.3 Study Mode

목적: 읽고 연구하기.

- 선택 문장 하이라이트
- 개인 메모
- 태그
- 개념 링크
- 인용 저장
- 질문 카드 생성

## 6. 데이터 품질 우선순위

### 6.1 니체 독일어 인코딩 검증

니체 Markdown 파일 자체는 UTF-8로 읽을 때 `Morgenröthe`, `fröhliche` 같은 독일어 문자가 정상 표시된다. 다만 Windows 콘솔이나 중간 처리 과정에서 mojibake처럼 보일 수 있으므로, 실제 파일·API·브라우저 표시를 분리해서 검증해야 한다.

검증 결과:

- `data/nietzsche_encoding_report.json`에 91개 Markdown 파일 검증 결과를 기록했다.
- U+FFFD 대체 문자는 0개다.
- `works/M.md`의 `Morgenröthe`, `works/FW.md`의 `fröhliche Wissenschaft` 샘플이 정상 확인됐다.

향후 조치:

- 파일을 UTF-8로 읽었을 때 대체 문자 `�`가 생기는지 검사한다.
- API 응답과 브라우저 표시에서 독일어 확장 문자가 유지되는지 검사한다.
- raw는 보존하고, 표시용 정리가 필요할 때만 `display_clean` 또는 `normalized` 레이어를 별도로 만든다.

### 6.2 Markdown 찌꺼기 제거

읽기용 표시에서는 다음을 정리한다.

- `(javascript:;)`
- `# _#_eKGWB$about_the_edition_#_`
- 메뉴/문서 링크용 heading
- HTML 변환 잔재

단, raw source에서는 그대로 보존한다.

### 6.3 메타데이터 보강

각 문헌에 최소 필드를 둔다.

```json
{
  "corpus": "nietzsche",
  "work_id": "M",
  "title_ko": "아침놀",
  "title_original": "Morgenröthe",
  "author": "Friedrich Nietzsche",
  "year": "1881",
  "source": "eKGWB",
  "source_path": ".../M.md",
  "license": "...",
  "checksum": "..."
}
```

## 7. UI/레이아웃 방향

현재 1000px 페이지 프레임과 764px 읽기 컨테이너는 좋은 출발점이다. 앞으로는 화면 종류별로 분명히 나누는 것이 좋다.

| 화면 | 목적 | 권장 레이아웃 |
|---|---|---|
| 홈 | 전체 서고 입구 | 764px 중앙 목록 |
| 카테고리 | 저자/전통 책장 | 섹션별 책 목록 |
| 작품 | 한 저작의 목차 | 저작 메타 + 목차 |
| 읽기 | 실제 원문 읽기 | 흰색 764px 본문 |
| 연구 | 주석/인용/개념 | 본문 + 오른쪽 연구 패널 |
| raw source | 검증 | pre 기반 원문 |

원칙:

- 설명문보다 구조가 말하게 한다.
- 통계 텍스트는 숨기고, 필요할 때 `metadata` 화면에서만 보여준다.
- 색은 배경/프레임/본문 구분에만 쓴다.
- 본문 가독성은 고정폭 764px을 유지한다.

## 8. 연구 기능 제안

### 8.1 주석

저장 형식은 JSONL이 좋다.

```json
{
  "id": "note_001",
  "target": {
    "corpus": "nietzsche",
    "work_id": "M",
    "selector": "section:1"
  },
  "quote": "...",
  "body": "내 메모",
  "tags": ["nihilism", "morality"],
  "created_at": "2026-05-27T00:00:00+09:00"
}
```

W3C Web Annotation 구조와 맞추면 나중에 이식성이 좋다.

### 8.2 개념 사전

개념을 저작과 연결한다.

```text
nihilism
- Nietzsche / AC / section 7
- Nietzsche / GM / essay 3
- Bible / Ecclesiastes
```

### 8.3 인용 저장

각 문단/절마다 "copy citation" 기능을 둔다.

예:

```text
Nietzsche, Morgenröthe, §1.
Personal Archive of Literature, /work/nietzsche/M#s1
```

### 8.4 학습 카드

원문에서 바로 질문을 만든다.

```text
Q. 니체가 "도덕의 계보"에서 원한 개념을 어떻게 설명하는가?
A. ...
Source: GM, Essay I, §10
```

## 9. 기술 구조 제안

### 9.1 단기

현재 Python 서버를 유지한다.

- `server.py`: API와 파일 제공
- `app.js`: 홈/카테고리/작품 화면
- `data/*.json`: 수동 보정 카탈로그
- `output/display/*.jsonl`: 표시용 정리 텍스트

### 9.2 중기

SQLite를 도입한다.

- `works`
- `documents`
- `segments`
- `notes`
- `tags`
- `links`
- `sources`

SQLite FTS5를 쓰면 검색을 다시 넣더라도 조용하고 강력하게 만들 수 있다. 검색창을 항상 노출하지 않고, `Find` 화면이나 단축키 기반으로 둘 수 있다.

### 9.3 장기

표준 호환을 고려한다.

- TEI export: 학술 텍스트 구조
- IIIF manifest: 원고 이미지/팩시밀리
- W3C Web Annotation: 주석
- CSL/Zotero export: 인용 관리

## 10. 구현 우선순위

### Phase 1: 읽기 가능한 서고 만들기

1. 완료: 니체 카탈로그 수동 보정
2. 완료: 니체 저작을 실제 출간/저작 단위로 구분
3. 완료: raw source와 reading mode 분리
4. 완료: reading mode에서 `javascript:;`와 about-the-edition heading 제거
5. 완료: `/work/nietzsche/M` 같은 작품 페이지 추가
6. 완료: 문단/절 단위 안정 URL 생성
7. 완료: 니체 독일어 UTF-8 인코딩 검증

### Phase 2: 연구 가능한 서고 만들기

1. 완료: 니체 문헌별 metadata JSON 생성
2. 완료: 문단/절 단위 안정 URL 기반 citation target 연결
3. 완료: 인용 복사 기능
4. 완료: 개인 주석 JSONL 저장
5. 완료: 니체 태그/개념 사전 초안

### Phase 2.5: 니체 연구 기능 안정화

1. 완료: 니체 작품 페이지 HTML을 `templates/nietzsche_work.html`로 분리
2. 완료: 작품 페이지 CSS를 `assets/work-page.css`로 분리
3. 완료: citation/note 클라이언트 로직을 `assets/work-page.js`로 분리
4. 완료: metadata 재생성 스크립트 `scripts/build_nietzsche_metadata.py` 추가
5. 완료: 연구 모델 문서 `docs/nietzsche_research_model.md` 추가

### Phase 3: 공부 가능한 서고 만들기

1. 읽은 문헌 표시
2. 메모에서 질문 카드 생성
3. 회상 연습 목록
4. 개념 지도
5. 텍스트 간 연결

### Phase 4: 학술판에 가까운 서고 만들기

1. TEI-like metadata
2. source checksum/version
3. release snapshot
4. Zotero/CSL citation export
5. IIIF/원고 이미지 연동

## 11. 바로 다음 작업 추천

니체 기준 모델에는 Phase 2 연구 기능까지 적용되었으므로, 가장 효용이 큰 다음 작업은 공부 기능 또는 다른 코퍼스 확장이다.

1. 니체 Phase 3: 읽은 문헌 표시, 질문 카드, 회상 연습
2. 성경: 책/장/절 기준 작품 페이지 패턴 확장
3. 키르케고르: Text / Commentary / Textual Account를 저작 단위로 묶기
4. 비트겐슈타인: 원고군 / 전사본 / 정규화본 관계 모델 만들기
5. 공통 notes/citation API를 니체 전용에서 전체 코퍼스용으로 일반화

이 순서가 좋은 이유:

- 현재 사용자가 바로 체감한다.
- 재수집이 필요 없다.
- 프로젝트 정체성인 "개인 문헌 아카이브"와 맞다.
- 이후 성경, 키르케고르, 비트겐슈타인에도 같은 모델을 확장할 수 있다.

## 12. 하지 않는 편이 좋은 일

- 검색창을 먼저 크게 만들기: 아직 데이터 구조가 정리되지 않아 결과가 혼란스럽다.
- AI 요약을 먼저 붙이기: 원문·판본·인용 구조가 안정되기 전에는 연구 신뢰도를 해칠 수 있다.
- 모든 코퍼스를 한 번에 TEI로 변환하기: 비용이 크고 당장 읽기 효용이 낮다.
- 화면을 대시보드처럼 만들기: 이 사이트의 중심은 관리가 아니라 읽기다.

## 13. 결론

이 프로젝트의 다음 단계는 "더 많은 자료 수집"이 아니라 "저작 단위 정리와 읽기/연구 단위 생성"이다. 니체를 첫 사례로 삼아 작품 카탈로그, reading mode, 문단 URL, 주석 구조를 만들면 나머지 코퍼스에도 같은 패턴을 적용할 수 있다.

가장 먼저 만들 기반인 니체 작품 카탈로그, 작품 페이지, 안정 앵커는 적용되었다. 다음은 인용/주석 구조다.
