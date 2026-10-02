# 원문 경계와 번역 노트 검사

괄호 안의 설명이 중간에서 끊기면 모델이 받은 번역 대상 자체가 불완전해진다. 또한 자연스러운 번역이나 유창한 번역 노트만으로 문법 설명과 어의 선택의 정확성을 보장할 수 없다. 이 변경은 원문 경계를 보존하고, 본문 번역 검사와 최종 노트 검사를 각각 기록한다.

## 적용 기준과 버전

기준은 공개 `main` 커밋 `6a26d18a0a58b4ccc5649fcd0cb539b15e9b1c5a`이다. 이 커밋의 번역 프롬프트는 `study_v4`, critic/revision은 각각 `v2`, 품질 파이프라인은 2, 번역 기록 스키마는 5였다. 별도 로컬 환경에서 운영되는 v9/v10 소스는 이 저장소에 포함되어 있지 않다. 이 문서의 파이프라인 3은 공개 main의 다음 버전이며 운영 v10에 적용됐다는 뜻이 아니다.

새 프롬프트 ID는 기존 내용과 구별된다.

| 단계 | 프롬프트 ID |
| --- | --- |
| 번역 | `sentence_translation_study_v4_context_notes_v1` |
| 본문 검사 | `sentence_translation_critic_v2_context_v1` |
| 본문 수정 | `sentence_translation_revision_v2_context_notes_v1` |
| 최종 노트 검사 | `sentence_translation_commentary_audit_v1` |

기존 프롬프트와 사람 승인 용어 정책은 보존된다. 새 지침은 지배 동사·목적어·문맥에 따른 어의 선택, 능력과 인과관계의 구별, 주어와 서술보어의 구별, 상대적 시간 표현과 괄호 부연의 범위를 다룬다. 특정 검토 문장의 정답이나 단어별 강제 치환표를 생산 프롬프트에 넣지 않는다.

## 문장 ID와 인덱스 이행

분절기는 기존 경계 후보를 계산하면서 원괄호·대괄호·중괄호 안의 후보를 합친다. 중첩과 전각 괄호도 처리한다. 괄호 밖 콜론·세미콜론 경계는 기존 관례를 유지하므로, 의도적으로 콜론에서 끝나는 검토 단위를 일괄 오류로 취급하지 않는다.

`First ( ɔ: a gloss). Next.`의 첫 문장은 예전 두 조각이 합쳐진다. 합쳐진 문장은 첫 기존 슬롯인 `.s001`을 사용하고 뒤 문장은 `.s003`을 유지한다. 표시 순서인 `sentence_index`는 1, 2처럼 연속이다. 문장 ID의 숫자를 화면 위치로 계산하면 안 된다.

흡수된 `.s002`를 뒤 문장에 다시 배정하거나 자동 연결하지 않는다. 그 ID를 직접 요청하면 찾을 수 없다고 반환한다. 기존 기록은 그대로 남는다. 확장된 `.s001`도 문장 본문 해시가 달라지므로 옛 번역을 새 본문 캐시로 재사용하지 않는다. 화면의 검토 표시 역시 현재 문장 해시와 기록의 해시·작품·판본이 맞는 경우에만 적용한다.

닫히지 않은 여는 괄호는 문단 끝까지 보수적으로 유지하며, 없는 부호나 문장을 보충하지 않는다. `end.) Next.` 또는 ASCII 닫는 따옴표 뒤처럼 예전 분절기가 인식하지 않던 새 경계는 이번에 추가하지 않는다. 새 경계 도입에는 별도 ID 이행이 필요하다.

오프셋 인덱스는 문장 수를 저장하므로 계산 규칙 변경도 인덱스 버전에 포함한다. 버전 2 인덱스는 원문 파일의 크기·시간·해시가 같아도 오래된 것으로 차단한다. 기존 원문 segment 파일이 있는 로컬 환경에서는 적용 후 다음 명령으로 버전 3 인덱스를 만든다.

```powershell
cd .\reader_site
python .\scripts\build_segment_offset_index.py
```

공개 clone에 원문 segment 파일이 없다면 먼저 기존 복원 절차로 코퍼스를 복원해야 한다. 사람 번역이나 주석을 자동으로 새 문장으로 옮기는 작업은 수행하지 않는다.

## 최종 번역 노트 검사

실행 순서는 번역 → 본문 검사 → 필요한 경우 한 번 수정 및 재검사 → 최종 노트 검사이다. 본문 critic에는 번역자의 노트를 전달하지 않는다. 노트가 비어 있으면 추가 모델 호출이 없고, 노트가 있으면 최종 저장 대상에 대해 최대 한 번 검사한다. 전체 모델 호출은 최대 5회이며 노트 재수정 반복은 없다. 본문 검사에 실패해 `critic_error`가 된 경우에는 추가 노트 요청을 하지 않고 `not_run`으로 남긴다.

검사 대상은 노트가 실제로 한 주장이다.

- `grammar`: 주어·보어·수식 관계 등 문법 설명의 오류.
- `source_support`: 없는 원문 인용이나 제공 근거를 벗어난 설명.
- `translation_match`: 한국어에 실제로 없는 특징을 보존했다고 설명하는 오류.
- `approval_claim`: 등록된 범위를 넘어서는 인간 승인 주장.

허용 용어나 정확한 조각의 등록은 그 범위에 대해서만 근거가 된다. 문장 전체나 새 후보의 인간 검토 완료를 뜻하지 않는다. 반대로 실제 등록된 조각의 승인을 정확히 설명했다면 `승인`이라는 단어 자체를 오류로 처리하지 않는다.

각 이슈는 실제 노트의 인용 구절을 포함해야 한다. 원문에 없는 인용을 지적할 때는 틀린 인용을 `commentary_span`에 남기고 `source_span`은 빈 값으로 둔다. 지적할 다른 주제가 노트에 없다는 사실만으로 이슈를 만들지 않는다.

새 번역 기록은 스키마 6을 사용한다. `translation_quality_state`는 본문 검사 결과를, `commentary_audit`는 노트 검사 결과를, `quality_state`는 두 결과를 합친 상태를 보존한다. 노트 오류 또는 노트 검사 실패가 있으면 전체 상태는 `needs_human_review`이며, 자동 통과 캐시로 사용하지 않는다. 원문·승인 정책·최종 번역·최종 노트의 해시로 검사 대상을 고정한다. 모델 감사 결과가 `review_state=generated`를 인간 검토 완료로 변경하지 않는다. 스키마 1~5의 이전 기록도 계속 읽고 검증한다.

## AI 평가 기록 가져오기

AI 평가는 기존 인간 골드셋과 별도인 `data/ai/translation_ai_reviews.jsonl`에 저장한다. 평가 JSON 한 개를 가져오는 명령은 다음과 같다. 이전 기록을 참조하는 새 기록은 참조 대상 다음에 가져온다.

```powershell
python .\scripts\import_translation_ai_review.py C:\review_package\r23_ai_review_01.json
python .\scripts\import_translation_ai_review.py C:\review_package\r23_ai_review_02.json
python .\scripts\check_translation_ai_reviews.py --require-records
```

같은 ID와 내용의 재수입은 성공으로 처리하며 파일을 바꾸지 않는다. 같은 ID의 내용을 바꾸거나 모르는 후보 ID를 임의로 채워 넣지 않는다. 해당 JSON·JSONL 파일은 사용자별 검토 자료로 보관하고 Git에는 넣지 않는다.

## 동일 문항으로 모델 비교하기

`scripts/run_translation_comparison.py`는 파일로 제공된 동일 원문과 문맥으로 지정한 checkout의 파이프라인을 실행한다. `group=regression`은 이미 검토한 사례, `group=reserved_evaluation`은 별도로 남긴 평가 문항이다. 검토 메모·그룹 이름·기대 정답을 모델 입력에 넣지 않는다. source와 case 해시, 선택한 checkout과 프롬프트·모델·생성 옵션, 실제 실행 상태를 결과에 남긴다. 사람 점수는 생성하지 않는다.

다음은 저장소 루트에서 실행하는 예다. `C:\review_package\r23_comparison_cases.json`을 실제 검토 파일 경로로 바꾼다. 별도 worktree는 공개 main 기준을 보관하며 현재 소스나 운영 checkout을 덮어쓰지 않는다.

```powershell
git worktree add --detach ..\Philo_Archive_base 6a26d18a0a58b4ccc5649fcd0cb539b15e9b1c5a

python .\reader_site\scripts\run_translation_comparison.py --cases C:\review_package\r23_comparison_cases.json --site ..\Philo_Archive_base\reader_site --label public-main --output .\reader_site\data\runtime.local\comparisons\public-main.jsonl --with-model

python .\reader_site\scripts\run_translation_comparison.py --cases C:\review_package\r23_comparison_cases.json --site .\reader_site --label context-notes --output .\reader_site\data\runtime.local\comparisons\context-notes.jsonl --with-model
```

동일한 로컬 모델 서버와 설정을 사용한다. `--with-model`을 빼면 입력 검증만 수행하고 `validated_only`로 기록한다. 기존 출력 파일은 덮어쓰지 않으므로 다시 실행할 때는 새 파일명을 쓴다. 실패한 모델 요청은 성공 번역이나 점수로 바꾸지 않고 실패 상태를 남긴다.

번역 비교에서는 복구된 전체 대상 문장과 문맥을 양쪽에 동일하게 전달한다. 분절 수정의 효과는 별도의 원문 경계 회귀검사에서 비교한다. 이 구분으로 원문 누락 복구와 프롬프트 변경 효과를 혼동하지 않는다.

기존 사례의 정답 재현을 별도 평가 문항의 성능 향상으로 계산하지 않는다. 합성 문항은 일반화 점검에 도움이 되지만 여러 저자·시대·장르를 대표하는 문헌 품질 평가를 대신하지 않는다. 실제 모델 출력과 별도 인간 평가가 없으면 정확도 향상이나 품질 합격을 주장하지 않는다.

## 검증

원문 코퍼스와 모델 없이 계약을 검사할 수 있다.

```powershell
python .\scripts\check_clean_clone_contracts.py --run-source-light-checks
```

새 검사는 괄호 분절·ID 보존, 오래된 인덱스 차단·재빌드, 최종 노트 호출과 상태·해시, AI 평가 기록 불변성과 승인 분리, 비교 실행의 입력 분리를 다룬다. 모델 응답을 대체한 계약 검사 통과는 모델의 실제 문법 판단이나 번역 품질이 검증됐다는 뜻이 아니다.
