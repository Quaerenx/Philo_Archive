# Search Quality Calibration - 2026-07-30

## 결과

`next_search_quality_prompt_ko.md`의 절차를 실행해 검색 평가 범위를 20건에서 36건으로 확대하고, 발음기호가 포함된 작품 제목을 ASCII로 입력했을 때 작품 결과가 누락되는 공통 원인을 수정했다.

검색 DB, 소스 코퍼스, 개인 노트, 로컬 AI 기록은 변경하지 않았다. 사용자 검색어를 자동 기록하거나 저장하는 기능도 추가하지 않았다.

## 평가 범위 확대

추가한 16건은 실제 메타데이터와 현재 연구 흐름에서 선택했다.

- Nietzsche
  - 한글 작품명 `도덕의 계보`
  - ASCII 작품명 `Morgenrothe`, `Frohliche Wissenschaft`, `Gotzen-Dammerung`, `Jenseits von Gut und Bose`
  - `GM` work 필터가 적용된 `ressentiment`
- Kierkegaard
  - 전체 제목 `Begrebet Angest`, `Philosophiske Smuler`
  - ASCII 작품명 `Frygt og Baeven`
- Bible
  - 한글 직접 참조 `창 1:1`, `요 3:16`
  - 소스 지정 직접 참조 `lxx Gen 1:1`
  - 대체 명칭 직접 참조 `EpJer 1:1`
- Wittgenstein
  - 공백형 그룹 별칭 `Group Works`
  - `language game`의 normalized/diplomatic variant 필터와 기대 문단

평가기는 이제 다음을 검증·보고한다.

- 사례 ID 중복과 필수 질의/기대 결과
- 양수인 limit 및 기대 최대 순위
- 작품·문단·variant 기대 순위
- 통과/실패 사례 수
- MRR
- Recall@1, Recall@3, Recall@10
- 사람이 읽는 기본 출력과 `--format json` 구조화 출력

## 기준선과 개선 결과

| 평가 시점 | 통과 | MRR | Recall@1 | Recall@3 | Recall@10 |
|---|---:|---:|---:|---:|---:|
| 기존 20건 | 20/20 | 0.9750 | 0.9500 | 1.0000 | 1.0000 |
| 36건 확대 직후 | 31/36 | 0.8472 | 0.8333 | 0.8611 | 0.8611 |
| 일반 별칭 수정 후 | 36/36 | 0.9861 | 0.9722 | 1.0000 | 1.0000 |

기존 20건의 수정 후 지표는 MRR 0.9750, Recall@1 0.9500, Recall@3/10 1.0000으로 그대로 유지됐다.

## 확인된 원인

확장 기준선에서 실패한 5건은 모두 작품 메타데이터에는 발음기호가 있지만 사용자가 ASCII로 입력한 경우였다.

- `Morgenröthe` / `Morgenrothe`
- `Die fröhliche Wissenschaft` / `Frohliche Wissenschaft`
- `Götzen-Dämmerung` / `Gotzen-Dammerung`
- `Jenseits von Gut und Böse` / `Jenseits von Gut und Bose`
- `Frygt og Bæven` / `Frygt og Baeven`

문단 검색은 일부 ASCII slug 덕분에 결과가 나오기도 했지만, 정확한 작품 바로가기는 생성되지 않았다.

## 구현

`services/search.py`의 작품 별칭 키 생성에 다음 일반 규칙을 적용했다.

1. 검색 문자열을 소문자와 공백 기준으로 정규화한다.
2. `æ`, `ø`, `ß`, `œ` 등 NFKD만으로 충분히 분해되지 않는 문자를 ASCII 대응 형태로 변환한다.
3. Unicode NFKD 분해 후 결합 문자를 제거한다.
4. NFC로 다시 결합해 한글과 비라틴 문자 체계를 안정적으로 유지한다.
5. 문장부호와 밑줄을 제거한 compact key로 작품 별칭을 비교한다.

작품별 별칭과 질의별 term compact key를 한 번씩만 계산하도록 중복 정규화도 제거했다.

이 변경은 특정 작품명 목록을 검색 로직에 하드코딩하지 않으며, 기존 Bible 한글 약칭과 소스 접두사 처리를 유지한다.

## 검증

다음 검증이 통과했다.

- Python 구문 검사: `services/search.py`, `check_search_relevance.py`, `check_search_contracts.py`
- 검색 평가 기본 출력: 36/36, MRR 0.9861
- 검색 평가 JSON 출력 파싱 및 핵심 수치 확인
- 검색 기능 계약
- API 계약과 서버 경계 계약
- 검색 산출물 무결성: 225,442 records
- 레이아웃 및 정적 라우트 계약
- 25개 라우트 HTML visual smoke
- 인코딩, 릴리스, 소스 공개 경계 및 소스 라이트 clean-clone 계약
- 릴리스 stage manifest: `block: 0`, `review: 0`
- `git diff --check`

검색 UI 마크업은 변경하지 않았으므로 새 전체 스크린샷 세트는 만들지 않았고, HTML visual smoke와 기존 레이아웃·정적 라우트 검사를 사용했다.

## 남은 한계

- 36건은 저장된 메타데이터와 대표 연구 흐름에서 선별한 재현 가능한 사례이며, 실제 사용자 세션 전체를 대표하지는 않는다.
- 다음 보정은 사용자가 명시적으로 선택해 추가한 실제 실패 질의를 평가 JSON에 편입한 뒤 진행해야 한다.
- 개인정보 보호를 위해 검색어 자동 로깅은 계속 사용하지 않는다.
- 이번 작업은 작품 별칭 매칭을 개선한 것이다. 원문 문단의 광범위한 철자 변형이나 언어별 형태소 분석은 포함하지 않는다.
