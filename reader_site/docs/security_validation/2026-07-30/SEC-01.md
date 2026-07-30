# SEC-01 validation receipt

## Finding

- 제목: `reader_site` 내부 임의 정적 파일 제공
- candidate id: `SEC-01`
- instance key: `reader_site-static-publication-boundary`
- ledger row id: 제공되지 않음
- 기존 source: HTTP request path
- 기존 sink: `reader_site` 아래 임의 파일의 byte response
- root control: `reader_site/services/static_files.py:43`
- affected locations: `reader_site/services/static_files.py`, `reader_site/server.py`
- source reference: 2026-07-29 외부 독립 검증 보고서

## Preconditions

공격자가 reader HTTP endpoint에 접근할 수 있고 `reader_site` 안의 민감 파일명을 추측한다.

## Validation method

실제 임시 loopback HTTP 서버와 resolver 단위 대조군을 함께 사용했다.

## Rubric

- [x] `SITE` 포함 여부만 보던 control이 명시적 public root/page/asset allowlist로 교체됐다.
- [x] 공개 page·asset은 200이고 민감 파일은 403이다.
- [x] encoded traversal과 Windows separator 우회가 거부된다.
- [x] 없는 허용 asset은 404이며 정상 페이지 흐름이 보존된다.
- [ ] 수정본이 불변 GitHub commit에서 재현 가능하다.

## Evidence

- `PUBLIC_ROOT_FILES`와 `PUBLIC_ASSET_SUFFIXES`: `services/static_files.py:14-26`
- resolver의 공개 경로 판정: `services/static_files.py:43-63`
- source-light denial 대조군: `scripts/check_server_boundary.py:157`
- 실제 HTTP private-path table: `scripts/check_static_routes.py:98`
- 실행 결과:
  - `python .\scripts\check_server_boundary.py` → `server boundary ok`
  - `python .\scripts\check_static_routes.py` → `static routes ok`

거부 대조군에는 `/server.py`, `/runtime_status.py`, `/README.md`, `/templates/work.html`, `/data/notes/nietzsche_notes.jsonl`, `/data/search_index.sqlite`, traversal 인코딩이 포함됐다. 허용 대조군에는 `/`, `/search`, `/styles.css`, `/app.js`, `/assets/design-tokens.css`가 포함됐다.

## Counterevidence

검사한 공개 page와 asset은 그대로 동작했고 허용 asset의 missing case는 404로 유지됐다. 같은 인스턴스에서 allowlist를 우회하는 경로는 관찰되지 않았다.

## Assessment

- code remediation: **CLOSED**
- validation disposition: `suppressed on patched tree`
- survives: `no`
- confidence: **high (0.85)**
- publication verification: **BLOCKED**

## Remaining uncertainty

새 asset 형식을 추가할 때 allowlist를 명시적으로 갱신해야 한다. 현재 수정본은 아직 GitHub commit으로 게시되지 않았다.

## Minimal next step

수정 commit을 게시한 뒤 해당 SHA의 `services/static_files.py`와 두 회귀 검사를 별도 clean checkout에서 다시 실행한다.

## Artifacts

- `reader_site/scripts/check_server_boundary.py`
- `reader_site/scripts/check_static_routes.py`
- 이 validation receipt
