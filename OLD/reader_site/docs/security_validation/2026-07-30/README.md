# Security remediation revalidation — 2026-07-30

## 판정

- 검증 대상: `main`의 기준 커밋 `6b2237bcbca7c5e7098465d083184487b5241ddd` 위 로컬 working tree
- remote: `https://github.com/Quaerenx/Philo_Archive.git`
- 로컬 코드 remediation: **4/4 CLOSED**
- 원래 finding survives: **4/4 no**
- GitHub publication verification: **BLOCKED**
- 차단 이유: 수정본이 아직 커밋·푸시되지 않아 불변 GitHub revision이 없다.

이 판정은 [외부 독립 재검증 프롬프트](../../external_security_revalidation_prompt_ko.md)를 현재 작업 트리에 실제로 수행한 결과다.

## 공통 rubric

- [x] 공격 입력과 sink 사이의 가장 가까운 control이 구현됐다.
- [x] 실제 HTTP·CLI·파일 mutation 경로에서 양성·음성 대조 검사가 통과했다.
- [x] 항목별 회귀 검사가 존재하고 source-light 검증에 포함된다.
- [x] loopback reader, 공개 페이지·asset, CRUD, 상세 로컬 manifest 같은 정상 경로가 보존됐다.
- [ ] 수정 코드가 불변 GitHub 커밋에서 제3자에게 재현 가능하다.

마지막 항목은 코드 결함이 아니라 publication proof gap이다.

## 실행 증거

| 명령 | 결과 |
|---|---|
| `git diff --check` | exit 0 |
| `python -m compileall -q server.py runtime_status.py services scripts` | exit 0 |
| `python .\scripts\check_server_boundary.py` | `server boundary ok` |
| `python .\scripts\check_notes_contracts.py` | `notes contracts ok` |
| `python .\scripts\check_sentence_translation_contracts.py` | `sentence translation contracts ok` |
| `python .\scripts\check_api_contracts.py` | `api contracts ok` |
| `python .\scripts\check_static_routes.py` | `static routes ok` |
| `python .\scripts\check_clean_clone_contracts.py --run-source-light-checks` | `clean clone contracts ok`, release stage `block=0`, `review=0` |
| `python .\server.py --host 0.0.0.0 --port 0` 거부 검사 | expected exit 2, `loopback-only` 확인 |
| `run_reader_with_gemma.ps1 -ReaderHost 0.0.0.0` 거부 검사 | non-zero exit, `loopback-only` 확인 |
| PowerShell parser syntax 검사 | `PowerShell launcher syntax ok` |

## Closure table

| ID | root control | entrypoint | sink | 방법 | disposition | survives | confidence | proof gap |
|---|---|---|---|---|---|---|---|---|
| SEC-01 | `services/static_files.py:43` | HTTP static path | `target.read_bytes()` file response | 실제 HTTP + resolver 대조군 | suppressed on patched tree / CLOSED | no | high (0.85) | 수정 SHA 미게시 |
| SEC-02 | `server.py:50`, `server.py:65`, launcher `:3`, `:49` | CLI·PowerShell bind host | `ThreadingHTTPServer.server_bind` | 실제 CLI·launcher 거부 + 임시 loopback HTTP | suppressed on patched tree / CLOSED | no | high (0.85) | 수정 SHA 미게시 |
| DATA-01 | `services/jsonl_storage.py:31`, `:53` | note/AI concurrent mutation | JSONL snapshot replacement | thread-pool append/update/delete/review + 실패 보존 | suppressed on patched tree / CLOSED | no | high (0.85) | multi-process writer는 지원 범위 밖; 수정 SHA 미게시 |
| PRIV-01 | `runtime_status.py:268`, `:332` | `/api/health`, `/api/artifacts` | JSON response | 실제 HTTP + recursive forbidden-key/path 검사 | suppressed on patched tree / CLOSED | no | high (0.85) | 수정 SHA 미게시 |

## 항목별 receipt

- [SEC-01 — 정적 파일 공개 경계](SEC-01.md)
- [SEC-02 — loopback 실행 경계](SEC-02.md)
- [DATA-01 — JSONL 동시성·원자성](DATA-01.md)
- [PRIV-01 — 공개 진단 redaction](PRIV-01.md)

## 정상 기능 보존

- `/`, category, search, notes, study, translations와 대표 work/read/source 흐름은 실제 임시 HTTP 서버 검사에서 통과했다.
- `styles.css`, `app.js`, `/assets/design-tokens.css`는 계속 제공된다.
- 노트와 sentence translation의 기존 CRUD·review·export 계약이 통과했다.
- `build_runtime_health()`와 `build_artifact_manifest.py`의 상세 로컬 maintenance 경로는 유지되고 HTTP handler만 redacted builder를 사용한다.
- source-light clean-clone 계약과 release-stage 정책이 통과했다.

## 범위와 남은 별도 항목

- `SEC-03`의 Content-Type·Origin·CSRF/PNA 문제는 기존 보고서의 별도 P2 항목이며 이번 네 finding의 종료 판정에 포함하지 않았다.
- JSONL lock은 지원되는 단일 reader 프로세스의 thread 동시성을 다룬다. 서로 다른 여러 reader 프로세스가 같은 저장소에 쓰는 구성은 지원하지 않는다.
- full-local 네 코퍼스 데이터 품질, 실제 Gemma 모델 실행, 실제 외부 백업·fresh restore는 이 보안 재검증 범위가 아니다.
- 이전 브라우저 DOM smoke 시도는 Edge와 Chrome 모두 headless `--dump-dom` 45초 timeout으로 끝났으며, 이번 판정은 성공한 실제 HTTP route 검사와 계약 검사에 근거한다.

## 공개 재검증을 완료하는 최소 다음 단계

1. 현재 수정 파일을 검토해 하나의 remediation commit으로 만든다.
2. 해당 commit을 GitHub에 게시한다.
3. 프롬프트의 `<REMEDIATION_COMMIT_SHA>`를 실제 SHA로 교체한다.
4. 별도 clean checkout에서 같은 명령을 다시 실행한다.
5. 네 receipt의 publication checklist를 완료하고 `BLOCKED`를 `VERIFIED`로 바꾼다.
