# 번역 품질 인간 평가

`data/translation_quality_goldset.json`은 네 코퍼스를 모두 포함하는 최소 평가 표본이다. 초기 항목은 의도적으로 `pending` 상태이며, 사람이 원문과 후보 번역을 검토하기 전에는 골드 번역이나 품질 합격으로 계산하지 않는다.

평가자는 각 항목에 다음 정보를 기록한다.

1. `reference_translation`: 사람이 직접 교정하고 확정한 번역
2. `human_evaluation.status`: `evaluated`
3. `evaluator`: 평가자를 구분할 수 있는 이름 또는 내부 식별자
4. `evaluated_at`: 시간대가 포함된 ISO 8601 시각
5. `scores`: 충실성, 완전성, 용어, 한국어 가독성의 1점부터 5점까지 정수 점수
6. `notes`: 판정 근거와 주요 오류

구조와 코퍼스 범위는 다음 명령으로 검사한다.

```powershell
python .\scripts\check_translation_goldset.py
```

모든 항목의 실제 인간 평가가 끝났는지는 엄격 모드로 검사한다. `pending` 항목이 하나라도 있으면 실패한다.

```powershell
python .\scripts\check_translation_goldset.py --require-complete
```

릴리스 품질 게이트는 다음 명령을 사용한다. 이 모드는 `pending` 항목뿐 아니라 평가된 네 차원 중 하나라도 `passing_score_per_dimension`보다 낮은 항목을 모두 차단하며, 실패 메시지에 항목 ID와 미달 차원을 표시한다.

```powershell
python .\scripts\check_translation_goldset.py --require-passing
```

## Wittgenstein `term` 문맥 조사

`wittgenstein-10-7-10-p-0001-s001`은 평가자가 `term`의 의미를 확정할 문맥이 부족해 보류한 항목이다. 동일 기록의 바로 다음 설명은 파일명 `Lent30a01r` 가운데 `Lent30a`가 “the first set of summaries of the Lent 1930 notes”를 뜻한다고 밝힌다. 따라서 이 문장의 `term`은 일반적인 “용어”가 아니라 대학의 “학기”이다.

재평가용 제안 번역은 다음과 같다.

> 기록 주석 F. 각 노트 페이지가 다루는 학기에 관한 정보는 각 팩시밀리 파일명의 일부에 체계적으로 표시되어 있다.

이 조사는 어휘 의미를 판정할 근거만 보충한다. 평가자가 확정 번역과 네 차원의 점수를 다시 제출하기 전까지 JSON 항목은 계속 `pending`이며 합격 건수에 포함되지 않는다.

번역 파이프라인을 바꾼 뒤 생성한 비교 번역은 새 인간 평가의 입력일 뿐 기존 점수를 자동으로 대체하지 않는다. 특히 모델 비평의 `critic_pass`는 사람의 네 차원 합격 판정과 동일하지 않다. 개선 번역은 평가자가 다시 점수를 제출한 뒤에만 골드셋 후보와 점수를 갱신한다.

모델 출력이나 자동 비평 결과를 사람 평가처럼 입력해서는 안 된다. 표본을 늘릴 때는 코퍼스별 시대, 장르, 문장 길이, 난도와 고유 용어가 한쪽으로 치우치지 않게 확장한다.

## 다섯 차원의 별도 AI 검토 기록

`services/translation_ai_reviews.py`는 사용자 답변 양식의 누락·추가 / 논리 / 용어 / 한국어 가독성 / 번역 노트 정확성을 별도 AI 검토 기록으로 저장한다. 이 기록은 위 네 차원의 인간 골드셋으로 자동 변환하지 않는다. `evaluator_type=ai`, `authored_by`, `reviewer_label`, `human_approval=pending`을 함께 보존한다. 표시용 평가자 이름만으로 인간 평가라고 판단하지 않는다.

기본 파일은 Git에서 제외되는 `data/ai/translation_ai_reviews.jsonl`이다. `PHILO_AI_DIR`이 있으면 해당 디렉터리를 쓴다. 평가 점수의 대상인 `scored_candidate`와 AI가 채택한 `revised_translation`을 구분하고, 후보 ID가 알려지지 않았으면 `null`로 남긴다. 평가 기록 UUID는 후보 ID를 대신하지 않는다. 각 텍스트의 SHA-256은 동일한 입력인지 확인하는 무결성 값이며 인간 승인이나 저작자의 신원을 증명하지 않는다.

원문과 후보가 달라진 재검토는 `related_review_ids`로 연결한다. 원문이 달라졌다면 `source_change_reason`도 필요하다. 동일 원문·동일 후보에 대한 새 평가만 `supersedes_review_id`를 쓸 수 있다. 어느 경우든 이전 기록은 덮어쓰지 않는다. 원문 경계가 불완전하면 `hold`만 허용하며, `adopt_revision`은 AI가 교정안을 채택했다는 뜻이다. 인간 검토 완료를 뜻하지 않는다.

노트가 없는 후보의 노트 정확성 점수는 `null`이다. 노트가 있는 경우에만 1~5점을 기록한다. 노트의 정확성과 다룬 주제의 수는 다르다. 실제로 적힌 문법·인용·번역 설명의 오류를 평가하며, 다른 문제를 언급하지 않았다는 이유만으로 노트 정확성을 감점하지 않는다.

구조, 점수 순서, 원문·후보·노트 해시, 승인 구분과 기록 연결을 검사한다.

```powershell
python .\scripts\check_translation_ai_reviews.py --require-records
```

원문 경계 수정, 자동 노트 검사, 기존/예약 평가 문항의 분리 실행은 [translation_context_audit.md](translation_context_audit.md)에 설명한다.
