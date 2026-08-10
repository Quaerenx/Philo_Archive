# DATA-01 validation receipt

## Finding

- 제목: 노트·AI JSONL의 비원자적 동시 rewrite
- candidate id: `DATA-01`
- instance key: `notes-and-sentence-translations-jsonl-mutation`
- ledger row id: 제공되지 않음
- 기존 source: concurrent append/update/delete/review 또는 write 중 예외
- 기존 sink: 같은 JSONL 파일의 truncate/rewrite
- root controls: `reader_site/services/jsonl_storage.py:31`, `:53`
- affected locations: `services/notes.py`, `services/sentence_translations.py`
- source reference: 2026-07-29 외부 독립 검증 보고서

## Preconditions

단일 reader 프로세스의 `ThreadingHTTPServer`에서 둘 이상의 요청이 같은 note 또는 AI translation JSONL 파일을 동시에 변경하거나 snapshot 생성 중 예외가 발생한다.

## Validation method

thread pool을 이용해 같은 파일에 concurrent append/update/delete/review를 수행하고 record 보존을 검사했다. 직렬화 실패를 주입해 기존 snapshot과 임시 파일 cleanup도 검사했다.

## Rubric

- [x] 전체 read-modify-write 구간이 파일별 재진입 lock으로 직렬화된다.
- [x] 같은 디렉터리 임시 파일을 flush·`fsync`한 후 `os.replace`한다.
- [x] 동시 append/update/delete/review에서 record 손실이 없다.
- [x] 실패한 write가 기존 snapshot을 바꾸지 않고 임시 파일을 남기지 않는다.
- [ ] 수정본이 불변 GitHub commit에서 재현 가능하다.

## Evidence

- 파일별 lock registry와 mutation context: `services/jsonl_storage.py:11-34`
- same-directory temp, file `fsync`, atomic replace: `services/jsonl_storage.py:53-78`
- note append/update/delete 적용: `services/notes.py:93`, `:495`, `:526`
- AI append/review 적용: `services/sentence_translations.py:301`, `:356`
- note concurrency와 실패 보존 검사: `scripts/check_notes_contracts.py:50-113`
- AI append/review concurrency 검사: `scripts/check_sentence_translation_contracts.py:47-96`
- 실행 결과:
  - `python .\scripts\check_notes_contracts.py` → `notes contracts ok`
  - `python .\scripts\check_sentence_translation_contracts.py` → `sentence translation contracts ok`

## Counterevidence

32개 concurrent note append와 update, 절반 delete 후 기대 record 집합이 보존됐다. 32개 AI record append와 review도 모두 보존됐다. 직렬화 실패 후 target bytes는 이전 snapshot과 동일했고 임시 파일이 남지 않았다.

## Assessment

- code remediation: **CLOSED**
- validation disposition: `suppressed on patched tree`
- survives: `no`
- confidence: **high (0.85)**
- publication verification: **BLOCKED**

## Remaining uncertainty

lock은 현재 reader 프로세스 안의 thread 동시성을 직렬화한다. 서로 다른 여러 reader 프로세스가 같은 JSONL 파일에 쓰는 구성에는 프로세스 간 lock이 없으며 지원 범위 밖이다. 디스크·파일시스템 자체의 전원 상실 보장은 해당 파일시스템의 `fsync`·atomic replace 의미에 의존한다.

## Minimal next step

수정 commit을 게시해 clean checkout concurrency 계약을 다시 실행한다. multi-process writer가 제품 요구가 되면 SQLite transaction 또는 OS-level inter-process lock으로 별도 설계한다.

## Artifacts

- `reader_site/services/jsonl_storage.py`
- `reader_site/scripts/check_notes_contracts.py`
- `reader_site/scripts/check_sentence_translation_contracts.py`
- 이 validation receipt
