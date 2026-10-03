# Reader에 적용한 다섯 UX 원칙

2026-09-30. 읽기·번역 검토·검색 흐름에 적용했다. 선택 시간, 포인터 이동 시간, 기억에 대한 서로 다른 원칙을 구별했으며 실제 사용자 작업시간이 감소했다고 주장하지 않는다.

| 원칙 | 조사 결과 | 적용 |
|---|---|---|
| 힉스의 법칙 | 선택지와 불확실성이 늘면 선택 반응 시간이 늘 수 있다. 익숙함과 선택 확률의 영향도 있으므로 모든 기능을 숨기는 규칙으로 사용하지 않는다. | 번역 가까이에 이전·다음 이동을 함께 제공하고 다음을 주행동으로 구분했다. 보기·재생성·내보내기 등 부가 기능은 기존 접기 구조를 유지한다. 검색은 입력·검색·지우기를 먼저 제시하고 범위 선택을 아래에 묶었다. |
| 피츠의 법칙 | 목표가 작거나 멀수록 포인터 이동이 어려워진다. 선택지를 이해하는 시간과는 별개다. | 주요 버튼·탭·접기 항목·입력의 클릭 영역을 44 CSSpx 이상으로 확보했다. 관련 행동을 결과 가까이 두고 이동 버튼 사이 간격을 8px로 맞췄다. |
| 제이콥의 법칙 | 사용자는 다른 제품에서 익힌 관례를 기대한다. 수학적 예측식이 아니라 사용성 지침이다. | 링크·버튼·탭·네이티브 접기의 의미와 키보드 동작을 유지했다. 검색 라벨·Enter 안내·포커스 표시를 제공하고 지우기 후 읽기 시작 안내를 복원했다. |
| 근접성의 법칙 | 가까운 요소는 관련 집단으로 지각된다. 유사성 등 다른 지각 요인도 함께 작용한다. | 검색 입력과 실행을 한 그룹으로 배치했다. 열린 Reader 설정은 문장·학습·설정 제목을 보이게 하고 그룹 내부 간격 8px, 그룹 사이 간격과 경계 여백 16px로 구분했다. 검색 결과 사이 간격도 관련 정보 내부보다 넓혔다. |
| 폰 레스토프 효과 | 비슷한 항목들 중 구별되는 항목을 더 잘 기억하는 격리 효과다. 강한 색이 클릭이나 기억을 항상 보장하지 않는다. | 검색과 다음 문장의 주행동만 강조하고, 자동 통과 상태는 중립적으로 표시했다. 검토 필요·비평 오류는 글자·굵기·경계로 함께 강조한다. 사람 확정문 옆의 자동 판정에는 `모델 원본:`을 붙여 확정문과 모델 평가를 구분한다. |

44px는 이번 UI의 설계 목표다. 피츠 법칙 자체가 정한 의무 수치가 아니다. WCAG 2.2의 [목표 크기 최소, AA](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)는 예외를 포함한 24×24 CSSpx 기준이고, [강화 기준, AAA](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html)는 44×44 CSSpx다. 연속적인 원문 안의 문장·인라인 링크를 모두 큰 버튼으로 바꾸지는 않았다. 색 이외의 상태 설명은 [Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)에 맞춰 유지한다. 전체 WCAG 준수 인증을 뜻하지 않는다.

## 확인한 출처

- 힉스: [Hick, 1952](https://journals.sagepub.com/doi/10.1080/17470215208416600)의 서지·초록, 적용 범위와 변수는 [Proctor & Schneider, 2018](https://journals.sagepub.com/doi/abs/10.1080/17470218.2017.1322622).
- 피츠: [Fitts, 1954](https://doi.org/10.1037/h0055392)의 서지·초록, UI와 터치 적용은 [NN/g의 Fitts’s Law 설명](https://www.nngroup.com/articles/fitts-law/).
- 제이콥: 원저자 Jakob Nielsen의 [The Need for Web Design Standards](https://www.nngroup.com/articles/the-need-for-web-design-standards/).
- 근접성: [Wertheimer, 1923의 영어 번역](https://www.yorku.ca/pclassic/Wertheimer/Forms/forms.htm), 행동과 대상의 배치는 [Nielsen의 Closeness of Actions and Objects](https://www.nngroup.com/articles/closeness-of-actions-and-objects-gui/).
- 폰 레스토프: [von Restorff, 1933](https://link.springer.com/article/10.1007/BF02409636)의 서지, 해석은 [Hunt, 1995](https://pubmed.ncbi.nlm.nih.gov/24203592/)와 [Hunt & Lamb, 2001](https://pubmed.ncbi.nlm.nih.gov/11713872/)의 초록.
- 구현 검토: [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)의 의미 있는 HTML·레이블·키보드·포커스·상태 피드백·넘침·동작 감소 지침.

출판사에서 전문을 열지 못한 자료는 서지·초록 확인 범위로 구별했다. Firecrawl CLI는 설치돼 있지 않아 웹 검색으로 조사했다. 새 의존성은 설치하지 않았다.

## 변경 범위와 검증

검색 HTML/CSS와 지우기 후 표시, Reader 템플릿·CSS와 이전 문장 버튼 및 모델 평가 설명을 변경했다. 저장·번역 생성 API와 운영 기록은 변경하지 않는다. CSS/JS 버전을 갱신해 브라우저가 새 파일을 받게 했다.

브라우저 검증은 실제 원문·확정본의 읽기 확인과 별도 임시 AI/노트 저장소의 기능 검사로 구분한다. 새 디자인에 맞는 크기·그룹·이동 요구를 검사하고, 기존 검토·취소·비동기 경쟁·문장 위치·모바일 패널·사람 확정문 보존 검사는 유지한다. 자동 검사는 조작 가능성과 화면 배치를 검증하며 사용자 이해도·기억·작업시간은 별도의 사용성 실험 대상이다.

검증 결과:

- 전체 `check_clean_clone_contracts.py --run-source-light-checks` 통과. 운영 AI 4파일·191건의 계약 검사도 포함한다.
- 최종 CSS/JS 버전의 레이아웃 검사, JavaScript 문법 및 Reader 비동기 검사 통과.
- 기존 Reader 상호작용 스모크 통과. HTML 스모크 25개 경로 통과.
- 변경 범위 5개 경로(선택 문장·개념 탭·번역기 오프라인·검색 시작·검색 결과)를 1365×768, 390×844 화면에서 검사해 10개 화면과 동작 검사 통과. 모델은 비활성 로컬 포트, 기록은 임시 저장소다.
- 실제 운영 Reader에서 N01 확정 번역과 평가 맥락, 검색 Enter·지우기·접힌 범위·모바일 입력 16px를 확인했다. 작업 전후 AI·노트·골드셋의 6개 파일 SHA-256가 일치한다.

[검증 요약](../data/runtime.local/ux-laws-20260930/validation-summary.json)과 [화면 기록](../data/runtime.local/ux-laws-20260930/screens/)은 Git 제외 로컬 자료다. 실제 사용자의 기억률·선택 시간·오클릭률·보조기술 전체 조합은 측정하지 않았다.

## 2026-10-01 스크롤바와 화면 전환의 가로 이동 수정

공통 문서에는 스크롤바 공간 예약이 없고 Reader 내부 패널에만 있었다. Windows Edge에서 짧은 검색 화면에 긴 내용을 추가하면 폭을 차지하는 스크롤바 15px가 생기면서 가운데 프레임과 입력창이 7.5px 왼쪽으로 이동했다. 내용을 제거하면 원래 위치로 돌아왔다.

공통 `design-tokens.css`의 루트 `html`에 `scrollbar-gutter: stable`을 적용해 스크롤바가 없을 때도 같은 공간을 확보한다. 미지원 브라우저에는 `overflow-y: scroll` 대체 규칙을 적용한다. 8개 HTML 진입점은 공통 스타일 버전을 `frame7`로 갱신했다. 화면별 의도된 프레임 폭, 기존 내부 패널 예약, 원문·번역·노트와 생성 로직은 유지한다. 이 속성의 루트 적용 및 공간 예약은 [CSS Overflow 표준](https://drafts.csswg.org/css-overflow/#scrollbar-gutter-property), 일반 스크롤바와 오버레이 스크롤바의 차이는 [MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/scrollbar-gutter)에서 확인했다. Firecrawl 조회는 크레딧 부족으로 실패해 다른 웹 조회 도구로 문서를 확인했다.

기존 Playwright headless 실행은 기본 `--hide-scrollbars` 때문에 폭 변화가 나타나지 않았다. Reader 상호작용 검사에 이 기본 옵션을 제외한 회귀 검사를 추가했다. 실제 15px 스크롤바가 나타남을 확인한 뒤 1365×900·390×844·1040×900·1041×900에서 내용 증감, 패널 내용 증감, 번역·노트·인용 전환 및 복귀를 검사한다. 변경 후 프레임·입력·패널·탭의 가로 위치와 폭 변화는 모두 0px였다. 미지원 구형 브라우저를 직접 실행한 검증은 하지 않았다.

[전후 좌표와 화면 자료](../data/runtime.local/scrollbar-layout-20261001/)에 측정값을 보관한다. 레이아웃 계약 검사, HTML 25개 경로 검사, 기존 문장 이동·가상 문서·검색 준비 검사와 새 스크롤바 회귀 검사는 통과했다.

전체 source-light 검사도 통과했으며 AI·노트·골드셋 6개 파일의 작업 전후 SHA-256가 일치한다. 현재 Reader는 재시작 없이 새 공통 스타일을 제공한다. 이미 열린 화면은 새로고침해야 새 스타일 버전을 받는다.
