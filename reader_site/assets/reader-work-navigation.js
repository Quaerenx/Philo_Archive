let automaticSentenceTranslation = false;
let pendingTranslationCacheOnly = false;

function initializeSentenceTranslationPreference() {
  const field = document.getElementById("automaticSentenceTranslation");
  if (!field) return;
  automaticSentenceTranslation = readerWorkStorage.readAutomaticTranslation();
  field.checked = automaticSentenceTranslation;
  const updateStatus = (saved = true) => {
    const status = automaticSentenceTranslation
      ? "문장을 선택하면 새 번역도 자동으로 생성합니다." : "문장 탐색은 저장된 번역만 확인합니다. 새 번역은 번역 버튼으로 생성하세요.";
    document.getElementById("automaticTranslationStatus").textContent = saved
      ? status : `${status} 브라우저에 설정을 저장하지 못해 이번 화면에만 적용됩니다.`;
  };
  updateStatus();
  field.addEventListener("change", () => {
    automaticSentenceTranslation = field.checked;
    updateStatus(readerWorkStorage.storeAutomaticTranslation(automaticSentenceTranslation));
  });
}

function requestSelectedTranslation() {
  return requestSentenceTranslation(false, !automaticSentenceTranslation);
}

function renderTranslationAwaitingAction() {
  selectedTranslationRecord = null;
  setTranslationBusy(false);
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  const index = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  translationOutput.innerHTML = `<div class="translation-result translation-awaiting-action">
    <section class="translation-section"><h3>선택한 원문</h3><p dir="auto">${escapeHtml(selectedSentence?.text || "")}</p></section>
    <p class="translation-unavailable-copy">저장된 번역이 없습니다. 원문을 계속 읽거나 이 문장을 번역하세요.</p>
    <button type="button" data-translation-generate>이 문장 번역</button>
    <div class="translation-sentence-navigation" role="group" aria-label="문장 탐색">
      <button type="button" data-translation-quick-action="previous-sentence"${index <= 0 ? " disabled" : ""}>이전 문장</button>
      <button type="button" data-translation-quick-action="next-sentence"${index >= totalSentenceCount() - 1 ? " disabled" : ""}>다음 문장</button>
    </div></div>`;
  updateReaderTerms();
  updateStudyPanelToggleLabel();
}
