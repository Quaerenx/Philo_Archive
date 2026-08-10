# Philo Archive 수정 4건 외부 독립 재검증 프롬프트

아래 프롬프트는 2026-07-29 외부 검증에서 확인된 `SEC-01`, `SEC-02`, `DATA-01`, `PRIV-01`의 수정 여부만 독립적으로 다시 검증하기 위한 것이다.

현재 수정본은 기준 커밋 `6b2237bcbca7c5e7098465d083184487b5241ddd` 위의 로컬 작업 트리에 있으며 아직 커밋·푸시되지 않았다. 따라서 외부 검증자는 수정 커밋 SHA 또는 패치 파일을 별도로 받아야 한다. 불변 GitHub 커밋을 받지 못하면 코드 판정과 별개로 **공개 재현 상태를 `BLOCKED`**로 기록해야 한다.

---

## 검증자에게 전달할 프롬프트

당신은 Philo Archive의 외부 독립 보안 검증자다. 저장소를 수정하거나 GitHub 원격 상태를 변경하지 말고 읽기·실행 검증만 수행하라.

### 목표

기존 보고서에서 확인된 다음 네 항목이 제공된 수정 리비전에서 실제로 종료됐는지 판단한다.

1. `SEC-01`: `reader_site` 내부 임의 정적 파일 제공
2. `SEC-02`: LAN에 노출 가능한 인증 없는 원전·개인 상태·쓰기 API
3. `DATA-01`: 노트·AI JSONL의 비원자적 동시 rewrite
4. `PRIV-01`: `/api/health`, `/api/artifacts`의 절대 경로와 상세 로컬 인벤토리 노출

새 취약점 전체 스캔으로 범위를 확장하지 말라. 다만 수정 때문에 생긴 직접적인 우회 또는 회귀는 기록하라. `SEC-03`의 Content-Type·Origin·CSRF 문제처럼 기존 보고서에서 별도 항목이었던 사항을 네 항목의 종료 조건과 혼합하지 말라.

### 검증 대상

- 저장소: `https://github.com/Quaerenx/Philo_Archive`
- 취약 기준 커밋: `6b2237bcbca7c5e7098465d083184487b5241ddd`
- 수정 대상 커밋: `<REMEDIATION_COMMIT_SHA>`
- 기준 브랜치: `main`

먼저 다음을 확인하라.

```bash
git status --short
git rev-parse HEAD
git remote -v
```

`<REMEDIATION_COMMIT_SHA>`가 제공되지 않았거나 GitHub에서 읽을 수 없으면:

- 제공된 로컬 patch 또는 working tree는 검증할 수 있다.
- 그러나 “GitHub에서 독립 재현 가능”이라고 판정하면 안 된다.
- 최종 보고서에 `publication verification: BLOCKED`라고 명시한다.

### 프로젝트 경계

- 이 프로젝트는 네 코퍼스를 통합한 개인 연구용 로컬 reader다.
- reader API는 원전·검색·개인 노트·학습 기록·로컬 AI 번역 기록을 다룬다.
- 지원되는 보안 경계는 단일 reader 프로세스와 IPv4 loopback이다.
- 원전 원본, 생성 segment/search DB, 개인 노트, AI 기록은 공개 Git 범위 밖일 수 있다.
- source-light 검증과 full-local 데이터 검증을 구분한다.

### 기준 커밋의 핵심 GitHub 링크

아래 링크는 취약 기준 커밋의 역사적 증거다. 수정 여부는 반드시 수정 커밋의 같은 경로와 비교해야 한다.

- [서버와 API 라우트](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/server.py)
- [정적 파일 resolver](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/services/static_files.py)
- [노트 JSONL 저장](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/services/notes.py)
- [AI 번역 JSONL 저장](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/services/sentence_translations.py)
- [진단 payload](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/runtime_status.py)
- [Windows launcher](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/run_reader_with_gemma.ps1)
- [API 문서](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/docs/api_reference.md)
- [로컬 운영 quickstart](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/docs/local_operator_quickstart.md)
- [clean-clone 재현 문서](https://github.com/Quaerenx/Philo_Archive/blob/6b2237bcbca7c5e7098465d083184487b5241ddd/reader_site/docs/clean_clone_reproducibility.md)

수정 커밋이 게시되면 위 URL의 SHA만 `<REMEDIATION_COMMIT_SHA>`로 교체해 불변 링크로 인용하라.

### 공통 검증 rubric

각 항목에 대해 다음 다섯 기준을 `- [x]` 또는 `- [ ]`로 판정하라.

1. 공격자 입력에서 위험 sink까지의 기존 경로가 가장 가까운 control에서 차단된다.
2. 실제 HTTP·CLI·파일 mutation 인터페이스에서 양성·음성 대조군이 모두 기대대로 동작한다.
3. 수정 경로를 고정하는 회귀 검사가 존재하고 source-light 환경에서도 실행된다.
4. 정상 로컬 reader 페이지, 공개 asset, 노트·번역 CRUD와 상세 로컬 manifest 생성은 보존된다.
5. 판정한 코드가 불변 GitHub 커밋에서 제3자에게 재현 가능하다.

### 필수 공통 명령

저장소 루트에서:

```powershell
git diff --check
cd .\reader_site
python -m compileall -q server.py runtime_status.py services scripts
python .\scripts\check_server_boundary.py
python .\scripts\check_notes_contracts.py
python .\scripts\check_sentence_translation_contracts.py
python .\scripts\check_api_contracts.py
python .\scripts\check_static_routes.py
python .\scripts\check_clean_clone_contracts.py --run-source-light-checks
```

각 명령의 종료 코드와 핵심 출력을 기록하라. 테스트가 없거나 실행할 수 없으면 코드만 보고 종료 판정을 확정하지 말고 정확한 proof gap을 기록하라.

### `SEC-01` 검증

공격 입력은 HTTP path이며 sink는 `SITE` 아래 파일의 byte 응답이다.

다음을 확인하라.

- `/`, `/search`, `/styles.css`, `/app.js`, `/assets/design-tokens.css`는 정상 제공된다.
- `/server.py`, `/runtime_status.py`, `/README.md`, `/templates/work.html`은 거부된다.
- `/data/notes/nietzsche_notes.jsonl`, `/data/search_index.sqlite`는 파일 존재 여부와 관계없이 거부된다.
- `/%2e%2e/server.py`, `/assets/..%5cserver.py` 우회도 거부된다.
- 허용된 asset 경로의 없는 파일은 404다.
- 허용 판단은 단순히 `SITE` 내부인지가 아니라 명시적 page/root asset/`assets` 정책으로 이뤄진다.

종료 조건: 민감 경로가 403 또는 보수적인 404이고, 공개 페이지와 asset 대조군은 200이어야 한다.

### `SEC-02` 검증

공격 전제는 reader가 신뢰되지 않는 LAN 주소에 bind되는 것이다. 가장 가까운 control은 서버 bind와 Windows launcher다.

다음을 확인하라.

- 기본 host가 `127.0.0.1`이다.
- `server.py --host 0.0.0.0`이 서버를 열기 전에 실패한다.
- 서버 클래스 자체도 `0.0.0.0` bind를 거부해 CLI 검사를 우회할 수 없다.
- launcher가 `0.0.0.0`을 거부하고 LAN URL을 출력하지 않는다.
- launcher가 기존 포트의 `0.0.0.0` 또는 다른 non-loopback listener를 안전한 reader로 재사용하지 않는다.
- 정상 `127.0.0.1` 임시 서버는 API·페이지 검사를 통과한다.

Windows에서 가능하면 다음 거부 경로도 실행하라.

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned `
  -File .\run_reader_with_gemma.ps1 -ReaderHost 0.0.0.0
```

종료 조건: 지원되는 시작 경로와 서버 객체 모두 IPv4 loopback 밖에 bind할 수 없어야 한다.

### `DATA-01` 검증

공격 또는 실패 입력은 같은 JSONL 파일에 대한 동시 append/update/delete/review 및 write 중 예외다. sink는 기존 파일의 교체다.

다음을 확인하라.

- mutation 전체 read-modify-write 구간이 동일 파일의 lock으로 직렬화된다.
- 임시 파일은 대상과 같은 디렉터리에 생성된다.
- 임시 파일을 flush하고 `fsync`한 뒤 `os.replace`한다.
- 예외가 발생하면 기존 정상 snapshot이 유지되고 임시 파일이 제거된다.
- 노트의 동시 append/update/delete와 AI 기록의 동시 append/review에서 record 손실이 없다.
- 상세 저장 형식과 정상 CRUD 결과는 이전 계약을 유지한다.

종료 조건: 지원되는 단일 reader 프로세스의 `ThreadingHTTPServer` 동시성에서 lost update와 부분 rewrite가 재현되지 않아야 한다.

여러 reader 프로세스가 같은 JSONL 저장소를 동시에 쓰는 구성은 별도 전제로 기록하라. 프로세스 간 lock이나 SQLite가 없다면 그 구성까지 안전하다고 확대 해석하지 말라.

### `PRIV-01` 검증

공격 입력은 `/api/health`, `/api/artifacts` 요청이며 sink는 JSON 응답이다.

다음을 확인하라.

- HTTP 응답에 `site_root`, `corpus_root`, `source_root`, `primary_output`, `path`가 없다.
- `notes`, `models`, `base_url`, raw `error`가 없다.
- 파일 `bytes`, `modified_at`, `sha256`와 환경 override 정보가 없다.
- 응답 문자열 어디에도 저장소·사용자 홈의 절대 경로가 없다.
- 상태, corpus readiness, search readiness, Gemma reachable/model count처럼 필요한 최소 정보는 남는다.
- 상세 로컬 manifest 생성기는 HTTP 응답과 분리되어 계속 동작한다.

종료 조건: 공개 진단 payload가 bounded readiness 정보만 반환하고 상세 로컬 상태는 HTTP 경계를 넘지 않아야 한다.

### 판정 규칙

각 항목을 다음 중 하나로 판정하라.

- `CLOSED`: 정확한 공격 경로가 동적·정적 증거로 차단되고 회귀 검사가 통과한다.
- `PARTIAL`: 대표 경로는 막혔지만 같은 인스턴스의 우회 또는 필수 proof gap이 남는다.
- `OPEN`: 원래 공격 경로가 여전히 재현된다.
- `BLOCKED`: 필요한 revision, 환경 또는 산출물이 없어 판정할 수 없다.

코드가 로컬 patch에서 `CLOSED`여도 수정 커밋이 공개되지 않았다면 다음 두 상태를 분리하라.

- `code remediation`: 예: `CLOSED`
- `publication verification`: `BLOCKED`

### 결과 형식

보고서는 한국어로 작성하고 다음을 포함하라.

1. 대상 remote, branch, 정확한 SHA, working tree 상태
2. 최대 다섯 항목의 공통 rubric
3. 항목별 공격 입력, sink/control, precondition
4. 실행한 명령과 종료 코드
5. 항목별 체크리스트, 관찰 증거, 반대 증거, 잔여 불확실성
6. 다음 열을 가진 closure table

| ID | root control | entrypoint | sink | 방법 | 판정 | survives | confidence | proof gap |
|---|---|---|---|---|---|---|---|---|

7. 정상 기능 보존 여부
8. 로컬 코드 판정과 GitHub 공개 재현 판정의 분리
9. 남은 별도 항목을 이번 네 건의 미수정으로 오인하지 않도록 범위 설명

검증하지 않은 사실을 검증했다고 쓰지 말고, GitHub 링크는 실제로 읽은 불변 커밋 URL만 인용하라.

---

## 현재 로컬 수행 결과의 위치

이 프롬프트를 현재 작업 트리에 수행한 결과와 항목별 validation receipt는 `docs/security_validation/2026-07-30/`에 저장한다. 수정 커밋이 게시되면 이 문서의 `<REMEDIATION_COMMIT_SHA>`를 실제 SHA로 교체하고 외부 환경에서 같은 명령을 다시 실행해야 공개 재검증이 완료된다.
