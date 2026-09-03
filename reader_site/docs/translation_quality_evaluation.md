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

모델 출력이나 자동 비평 결과를 사람 평가처럼 입력해서는 안 된다. 표본을 늘릴 때는 코퍼스별 시대, 장르, 문장 길이, 난도와 고유 용어가 한쪽으로 치우치지 않게 확장한다.
