# SEC-02 validation receipt

## Finding

- 제목: LAN에 노출 가능한 인증 없는 원전·개인 상태·쓰기 API
- candidate id: `SEC-02`
- instance key: `reader-loopback-bind-boundary`
- ledger row id: 제공되지 않음
- 기존 source: CLI 또는 Windows launcher의 reader host
- 기존 sink: `ThreadingHTTPServer` network bind
- root controls: `reader_site/server.py:50`, `reader_site/server.py:65`, `reader_site/run_reader_with_gemma.ps1:3`, `:49`
- affected locations: server CLI, server class, launcher 기본값과 기존 listener 재사용
- source reference: 2026-07-29 외부 독립 검증 보고서

## Preconditions

reader가 `0.0.0.0` 또는 다른 신뢰되지 않는 인터페이스에 bind되어 같은 LAN의 공격자가 인증 없는 API에 접근한다.

## Validation method

실제 server CLI와 PowerShell launcher의 거부 경로, server class 직접 생성, 정상 loopback 임시 HTTP 서버를 검증했다.

## Rubric

- [x] 기본 launcher host가 `127.0.0.1`이다.
- [x] CLI와 server class가 non-loopback bind를 거부한다.
- [x] launcher가 non-loopback 입력과 기존 non-loopback listener 재사용을 거부한다.
- [x] 정상 loopback reader의 API·페이지가 계속 동작한다.
- [ ] 수정본이 불변 GitHub commit에서 재현 가능하다.

## Evidence

- host 정규화·거부: `server.py:50-62`
- server class의 bind-time enforcement: `server.py:65-70`
- launcher 기본값: `run_reader_with_gemma.ps1:3`
- 기존 listener 주소 검사: `run_reader_with_gemma.ps1:49-67`, `:165-171`
- launcher 입력 거부: `run_reader_with_gemma.ps1:150-155`
- 회귀 검사: `scripts/check_server_boundary.py:133`
- 실행 결과:
  - `python .\server.py --host 0.0.0.0 --port 0` → expected exit 2와 `loopback-only`
  - `run_reader_with_gemma.ps1 -ReaderHost 0.0.0.0` → non-zero exit와 `loopback-only`
  - PowerShell parser → `PowerShell launcher syntax ok`
  - `python .\scripts\check_static_routes.py` → 정상 loopback HTTP `static routes ok`

## Counterevidence

지원되는 startup 경로에서 non-loopback listener를 생성하는 branch는 확인되지 않았다. `LoopbackThreadingHTTPServer`를 직접 `0.0.0.0`으로 생성하는 우회도 실패한다.

## Assessment

- code remediation: **CLOSED**
- validation disposition: `suppressed on patched tree`
- survives: `no`
- confidence: **high (0.85)**
- publication verification: **BLOCKED**

## Remaining uncertainty

이 수정은 의도적으로 LAN 기능을 제거한다. 향후 remote-device 기능을 다시 추가하려면 별도 인증·세션·Origin/Host 정책을 설계해야 한다. 현재 수정본은 아직 GitHub commit으로 게시되지 않았다.

## Minimal next step

수정 commit을 게시한 뒤 Windows clean checkout에서 launcher 거부와 Linux/Windows clean checkout에서 server class 거부를 각각 다시 실행한다.

## Artifacts

- `reader_site/scripts/check_server_boundary.py`
- `reader_site/scripts/check_static_routes.py`
- 이 validation receipt
