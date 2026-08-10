# PRIV-01 validation receipt

## Finding

- 제목: `/api/health`, `/api/artifacts`의 절대 경로와 상세 로컬 인벤토리 노출
- candidate id: `PRIV-01`
- instance key: `public-runtime-diagnostics-redaction`
- ledger row id: 제공되지 않음
- 기존 source: unauthenticated diagnostics request
- 기존 sink: HTTP JSON response
- root controls: `reader_site/runtime_status.py:268`, `:332`
- affected locations: `/api/health`, `/api/artifacts`
- source reference: 2026-07-29 외부 독립 검증 보고서

## Preconditions

공격자가 reader의 diagnostics endpoint에 접근한다. 기존 응답은 사용자명·디렉터리 구조·원전·노트·artifact·모델 상태를 상세히 노출했다.

## Validation method

실제 임시 HTTP 서버 응답과 builder 결과를 재귀적으로 검사해 민감 key와 절대 경로 문자열이 없는지 확인했다. 상세 로컬 maintenance builder의 기존 계약도 별도로 검사했다.

## Rubric

- [x] 공개 health와 artifact builder가 상세 local builder와 분리됐다.
- [x] 경로·노트·모델명·raw error·파일 상세 key가 HTTP payload에 없다.
- [x] repository/site 절대 경로 문자열을 재귀적으로 검사한다.
- [x] 최소 readiness 정보와 상세 로컬 manifest 생성 기능이 보존된다.
- [ ] 수정본이 불변 GitHub commit에서 재현 가능하다.

## Evidence

- redacted artifact builder: `runtime_status.py:268-286`
- redacted health builder: `runtime_status.py:332-346`
- HTTP handler가 redacted builder만 호출: `server.py:90-96`
- source-light recursive key/path 검사: `scripts/check_server_boundary.py:188`
- 실제 HTTP forbidden-key 검사: `scripts/check_static_routes.py:144-164`
- 상세·공개 API 계약 분리: `scripts/check_api_contracts.py`
- 실행 결과:
  - `python .\scripts\check_server_boundary.py` → `server boundary ok`
  - `python .\scripts\check_api_contracts.py` → `api contracts ok`
  - `python .\scripts\check_static_routes.py` → `static routes ok`

금지 key에는 `site_root`, `corpus_root`, `source_root`, `primary_output`, `path`, `notes`, `models`, `base_url`, `error`, `bytes`, `modified_at`, `sha256`, 환경 override와 regeneration command가 포함됐다.

## Counterevidence

공개 응답에는 `status`, corpus readiness, search readiness, Gemma `reachable`·`model_count`가 남아 정상 UI와 local health 확인이 가능하다. 상세 `build_runtime_health()`와 `build_artifact_manifest.py`는 HTTP 경계 밖에서 계속 동작한다.

## Assessment

- code remediation: **CLOSED**
- validation disposition: `suppressed on patched tree`
- survives: `no`
- confidence: **high (0.85)**
- publication verification: **BLOCKED**

## Remaining uncertainty

다른 API는 기능상 원전·개인 상태를 반환할 수 있지만 reader의 loopback-only 경계로 다뤄지며 이 finding은 두 diagnostics endpoint의 불필요한 상세 노출에 한정된다. 수정본은 아직 GitHub commit으로 게시되지 않았다.

## Minimal next step

수정 commit을 게시한 뒤 별도 clean checkout에서 실제 HTTP 응답을 저장하고 금지 key·절대 경로 검사를 다시 실행한다.

## Artifacts

- `reader_site/scripts/check_server_boundary.py`
- `reader_site/scripts/check_api_contracts.py`
- `reader_site/scripts/check_static_routes.py`
- 이 validation receipt
