# Project Usability Upgrade Review - 2026-06-17

이 문서는 Personal Archive of Literature / Philo Archive reader site를 사용자 편의성, 운영 안정성, 데이터 구조, AI 학습 보조 흐름 관점에서 검토한 현재 상태 기록이다. 목적은 "원전 연구 아카이브"를 장기적으로 읽고, 찾아보고, 주석을 남기고, 로컬 Gemma로 문장 단위 번역 학습까지 이어가는 방향으로 고도화하는 것이다.

## 1. 현재 확인한 상태

- Git 작업트리는 검토 시작 시점에 `main...origin/main` 동기화 상태였다.
- Reader 서버는 `0.0.0.0:8793`에서 정상 응답한다.
- Gemma llama.cpp sidecar는 `127.0.0.1:8794`에서 정상 응답한다.
- Windows 작업 스케줄러 `PhiloArchiveReaderGemma`가 사용자 로그인 시 `run_reader_with_gemma.ps1`을 실행하도록 등록되어 있다.
- `/api/health` 기준 네 코퍼스의 source root, metadata, segment artifact가 모두 존재한다.
- 검색 인덱스는 SQLite FTS5를 사용하며 총 225,442 records를 가진다.

코퍼스별 검색 record 수:

| Corpus | Records |
| --- | ---: |
| bible | 60,180 |
| kierkegaard | 25,359 |
| nietzsche | 14,227 |
| wittgenstein | 125,676 |

## 2. 실행한 검증

아래 검사는 모두 통과했다.

```powershell
python -B .\scripts\check_path_contracts.py
python -B .\scripts\check_encoding_contracts.py
python -B .\scripts\check_source_publication_contracts.py
python -B .\scripts\check_sentence_translation_contracts.py --with-source-targets
python -B .\scripts\check_static_routes.py
python -B .\scripts\check_api_contracts.py
python -B .\scripts\check_release_contracts.py
python -B .\scripts\check_restore_readiness.py
python -B .\scripts\check_layout_contracts.py
python -B .\scripts\check_prompt_template_contracts.py --with-source-targets
python -B .\scripts\check_note_target_integrity.py
python -B .\scripts\check_clean_clone_contracts.py --run-source-light-checks
git diff --check
```

검증 결과가 의미하는 바:

- 현재 저장소는 원문 대용량 데이터를 Git에 포함하지 않는 reader scaffold 정책을 유지한다.
- 경로, 인코딩, 공개 경계, release/restore 계약이 깨지지 않았다.
- Gemma 문장 번역은 임의 prompt 입력이 아니라 기존 source target에서만 문장을 가져오는 계약을 유지한다.
- UI 레이아웃의 page frame, reader column, 공통 work page 계약이 유지된다.

## 3. 강점

현재 프로젝트는 이미 단순 크롤링 결과물보다 한 단계 위의 "연구용 로컬 아카이브" 형태를 갖추고 있다.

- 네 코퍼스가 공통 `work` route와 metadata/segment/search contract로 묶여 있다.
- Nietzsche에서 시작한 책 단위 정리 모델이 Bible, Kierkegaard, Wittgenstein까지 확장 가능한 공통 구조로 이동했다.
- 원문 source와 generated metadata/search artifact가 분리되어 있어 GitHub 공개 범위가 비교적 안전하다.
- `/api/source-target`와 `/api/sentence-translation`이 원문 범위를 해시로 고정하고 있어 AI 출력이 원문에 섞이지 않는다.
- 로컬 Gemma 번역은 사용자가 클릭한 한 문장 중심으로 작동하므로 비용, 속도, 저장량, 검증 가능성 측면에서 적절하다.

## 4. 현재 가장 중요한 사용성 문제

### 4.1 문장 읽기 흐름

현재 원문 문장을 클릭하면 우측 패널에 번역/해설이 뜬다. 구조는 적합하지만 장시간 읽기에는 아직 마우스 클릭 의존도가 높다.

권장 개선:

- 선택 문장 기준 `Previous sentence`, `Next sentence` 이동 버튼 추가
- 키보드 `ArrowUp`, `ArrowDown`, `j`, `k` 이동 지원
- 선택 문장이 화면 중간 근처에 오도록 부드러운 scroll alignment 적용
- 우측 패널 상단에 현재 문장 위치를 짧게 표시

### 4.2 번역 패널의 정보 밀도

최근 `Literal gloss`, `Key terms`, 모델/해시 메타데이터는 UI에서 제거되어 좋아졌다. 다음 단계는 읽기 모드와 학습 모드를 분리하는 것이다.

권장 개선:

- 기본 Reading mode: 원문 + 자연스러운 한국어 번역만 표시
- Study mode: Commentary, Cautions, source excerpt를 접이식으로 표시
- `Regenerate`는 항상 보이기보다 작은 secondary action으로 낮춤
- 상태 문구 `Loaded cached translation`, `Generated translation saved locally`는 몇 초 뒤 사라지게 처리

### 4.3 우측 패널 카드 경쟁

우측에는 번역, 인용, 노트, 개념 카드가 함께 있다. 연구 기능으로는 좋지만 읽기 중에는 서로 경쟁한다.

권장 개선:

- 우측 패널을 `Translation`, `Notes`, `Citation`, `Concepts` 탭으로 나누기
- 기본 탭은 Translation
- Notes 저장 후에는 선택 문장/문단 anchor가 명확히 남도록 표시
- Citation/Source bundle은 접힌 도구 영역으로 이동

### 4.4 모바일과 좁은 화면

현재 860px 이하에서는 2면 구조가 단일 컬럼으로 접힌다. 구조적으로 안전하지만, 번역 결과가 원문 아래로 밀리므로 "문장을 누르고 위아래로 움직이는" 문제가 다시 생긴다.

권장 개선:

- 모바일에서는 번역 패널을 하단 sheet처럼 고정
- 선택 문장을 누르면 하단 sheet가 열리고 번역만 먼저 표시
- 해설/노트는 sheet 안에서 접이식으로 유지

## 5. 운영과 재현성 개선 후보

### 5.1 자동 실행 설정의 문서화

현재 자동 실행은 Windows 작업 스케줄러에 등록되어 있지만, 이 상태는 Git 저장소 안에 직접 기록되지 않는다. 다른 로컬이나 재설치 시 재현하려면 문서/스크립트가 필요하다.

권장 개선:

- `docs/local_windows_autostart.md` 추가
- 작업 이름, trigger, action, 권한 수준, 포트, 로그 위치 기록
- 자동 실행 등록/해제 스크립트 제공
- `/api/health` 또는 별도 진단에서 Gemma sidecar reachable 여부 표시

### 5.2 Runtime health 메시지 최신화

검토 중 `/api/health`의 `next_recommended_upgrades`가 과거 "Gemma prototype" 단계 문구를 포함하고 있었다. 현재는 문장 번역 기능이 구현되어 있으므로, 다음 단계는 "2면 읽기 UX"와 "AI record review/export" 쪽이어야 한다.

조치:

- `runtime_status.py`의 추천 문구를 현재 상태에 맞게 수정했다.

### 5.3 Visual smoke 범위 확대

현재 계약 검사는 탄탄하지만, 실제 읽기/번역 UI는 브라우저 상태와 상호작용을 더 많이 탄다.

권장 개선:

- `check_visual_smoke.py`에 다음 상태 추가:
  - Nietzsche work page 2-pane desktop
  - mobile translation bottom-sheet 또는 collapsed mode
  - selected sentence highlight
  - cached translation 표시
  - Gemma runtime down 상태

## 6. 데이터와 AI 기록 개선 후보

### 6.1 AI record v2

현재 내부 호환성 때문에 `literal_gloss`, `key_terms` 필드는 빈 값으로 저장될 수 있다. UI에서는 숨기지만 장기적으로는 schema v2에서 제거하는 편이 더 깨끗하다.

권장 개선:

- `ai_sentence_translation` schema v2 정의
- legacy v1 reader 유지
- validator를 v1/v2 모두 허용하도록 개정
- 기존 JSONL local record migration script 제공

### 6.2 Review/export 흐름

AI 출력은 원문이 아니므로, 생성 후 바로 신뢰하는 구조보다 "검토됨" 상태를 별도로 두는 것이 좋다.

권장 개선:

- 번역 카드에 `Mark reviewed`, `Reject`, `Edit note from translation` 추가
- `review_state: generated | reviewed | rejected`를 UI에서 수정 가능하게 함
- reviewed translation만 Markdown/JSON export 가능하게 분리

### 6.3 검색 품질 보정

FTS5는 적용되어 있지만, 실제 사용자의 공부 질문에 맞는 relevance calibration은 아직 별도 축적이 필요하다.

권장 개선:

- `data/search_eval_queries.json`을 실제 사용 쿼리 중심으로 확장
- corpus별 대표 쿼리 20개 이상 작성
- 검색 결과의 top 5에 기대 work/segment가 들어오는지 검사

## 7. 우선순위 로드맵

### Phase A - 읽기 흐름 개선

목표: 원문과 번역을 실제 책처럼 오래 읽기 좋게 만든다.

- Previous/Next sentence 버튼
- 키보드 문장 이동
- Reading/Study mode toggle
- 번역 상태 문구 자동 fade
- 우측 카드 탭 구조

### Phase B - AI 학습 기록 정리

목표: Gemma 출력이 단순 팝업이 아니라 누적 가능한 학습 자료가 되게 한다.

- AI record v2
- generated/reviewed/rejected UI
- reviewed 번역 export
- local cache 관리 화면

### Phase C - 코퍼스별 탐색 고도화

목표: Nietzsche 수준의 분류/정렬 감각을 Bible, Kierkegaard, Wittgenstein에도 더 명확히 적용한다.

- Bible: canon layer, testament, source variant 필터
- Kierkegaard: work/volume/translation variant 그룹 정리
- Wittgenstein: normalized/diplomatic/full/index variant 선택 UI 정돈
- category page에서 corpus별 핵심 reading path 제공

### Phase D - 운영/재현성

목표: 다른 로컬에서도 쉽게 되살릴 수 있는 개인 아카이브 운영 체계를 만든다.

- Windows autostart 문서화
- setup/check script 추가
- `/api/health`에 Gemma sidecar status 포함
- visual smoke에 AI panel 상태 추가

## 8. 다음 작업 추천

가장 먼저 할 일은 Phase A의 일부를 작게 구현하는 것이다.

추천 순서:

1. 우측 번역 패널에 `Previous` / `Next` 버튼 추가
2. 키보드 이동 지원
3. Reading/Study mode toggle 추가
4. Citation/Notes/Concepts를 탭 또는 접이식으로 낮추기

이 네 가지가 적용되면 "문장을 클릭해서 번역을 확인한다"에서 "원서를 한 문장씩 읽어 나간다"로 경험이 바뀐다.

## 9. Implementation Addendum

Applied after this review:

- Previous/Next sentence buttons on work pages.
- Keyboard sentence navigation with `ArrowUp`, `ArrowDown`, `j`, and `k`.
- Reading/Study display mode toggle for generated translations.
- Less intrusive translation status text with automatic clearing.
- Right-side study companion tabs for Translation, Notes, Citation, and Concepts.
- Mobile sticky study companion panel behavior.
- Sentence translation review actions: mark reviewed, reject, draft note.
- Reviewed sentence translation export endpoint.
- New schema version 2 for generated sentence translation records; legacy v1 records remain readable.
- `/api/health` Gemma runtime status.
- Local Windows autostart documentation and register/unregister scripts.
- Local runtime check script.
- Category page reading path and section/filter controls.
- Visual smoke checks for the new work-page study companion markers.

Deferred for explicit human review:

- Final Bible canon-layer taxonomy and deuterocanonical grouping labels.
- Final Kierkegaard work/volume/variant grouping semantics.
- Final Wittgenstein normalized/diplomatic/full/index vocabulary and default variant policy.
- A dedicated full cache-management page for local Gemma records.
