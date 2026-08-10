# 다음 작업 프롬프트: Reader 작업 화면의 안전한 모듈 분리

아래 프롬프트는 Personal Archive of Literature 프로젝트의 `reader-work.js`를 책임 경계에 따라 점진적으로 분리하는 작업을 다른 Codex 작업이나 외부 검증자에게 그대로 전달할 수 있도록 작성되었다.

```text
당신은 Personal Archive of Literature 로컬 리더의 프런트엔드 유지보수 담당자다.

목표
- 3,000줄 이상인 reader_site/assets/reader-work.js에서 독립성이 검증된 책임 하나만 분리한다.
- 이번 단계에서는 최근 작업, 학습 패널 펼침 상태, 노트 초안에 쓰이는 브라우저 저장소 접근을 별도 어댑터로 옮긴다.
- 사용자 동작, 저장 키, 저장 JSON 형식, 페이지 로딩 방식과 공개 HTTP 계약을 그대로 유지한다.

필수 입력
- reader_site/assets/reader-work.js
- reader_site/templates/work.html
- reader_site/scripts/check_layout_contracts.py
- reader_site/scripts/check_visual_smoke.py
- reader_site/scripts/check_reader_interaction_smoke.py
- reader_site/docs/codebase_review_2026-07-30.md

작업 절차
1. Git 작업 트리와 기존 사용자 변경을 확인하고 보존한다.
2. localStorage/sessionStorage의 모든 직접 호출과 그 호출자를 찾는다.
3. 키 관리, JSON 직렬화·역직렬화, 저장소 접근 예외 처리를 DOM에 의존하지 않는 작은 고전 스크립트로 추출한다.
4. reader-work.js에는 현재 문서·선택 상태로 저장 payload를 만드는 UI 책임만 남긴다.
5. 새 저장소 스크립트를 reader-work.js보다 먼저 로드하고 두 파일의 캐시 버전을 명시적으로 관리한다.
6. 기존 키를 정확히 유지한다.
   - philo.reader.recentWork
   - philo.reader.studyPanelExpanded
   - philo.reader.noteDraft:<corpus>:<work>:<variant>
7. reader-work.js가 localStorage/sessionStorage와 getItem/setItem/removeItem을 직접 호출하지 않는 계약을 추가한다.
8. 저장소 모듈의 API, 키, JSON 처리, 오류 격리와 스크립트 로딩 순서를 계약 검사로 고정한다.
9. 구문 검사, 정적·레이아웃 계약, 실제 리더 상호작용, 데스크톱·모바일 시각 회귀 검사를 실행한다.
10. 변경 전후 책임과 남은 다음 분리 후보를 문서화하고 최종 diff를 점검한다.

성공 기준
- 최근 작업 링크가 계속 기록되고 홈 화면에서 복원된다.
- 학습 패널 펼침 상태가 기존과 같은 localStorage 값으로 유지된다.
- 노트 초안의 본문, 태그, 고정 대상이 기존과 같은 sessionStorage 형식으로 저장·복원·삭제된다.
- reader-work.js에는 브라우저 저장소 직접 접근이 남지 않는다.
- 새 모듈은 DOM과 서버 API에 의존하지 않는다.
- 기존 정적 라우트·레이아웃·상호작용 계약이 모두 통과한다.
- 25개 라우트와 데스크톱·모바일을 합친 50개 시각 검사가 통과한다.
- 릴리스 분류 결과가 block 0, review 0이다.

제약
- 줄 수만 줄이기 위한 임의 분할을 하지 않는다.
- ES module이나 번들러를 새로 도입하지 않는다.
- 저장 키, 저장 기간(local/session), JSON 필드, 공개 API, CSS와 화면 문구를 바꾸지 않는다.
- 새 운영 의존성을 추가하지 않는다.
- 소스 코퍼스, 개인 노트, 번역 기록, 생성 검색 DB를 수정하지 않는다.
- 커밋, 푸시, 배포는 별도 요청이 없으면 수행하지 않는다.

최종 보고
- 추출한 책임과 새 모듈 API
- 보존한 저장 호환성
- 실행한 검증과 결과
- 미검증 항목과 남은 위험
- 다음으로 분리할 가치가 있는 책임 후보
```

## 이번 실행

이 프롬프트는 2026-07-30 작업에서 곧바로 실행한다. 구현 결과와 검증 근거는 `codebase_review_2026-07-30.md`에 이어서 기록한다.
