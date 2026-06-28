const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const noteFilterClear = document.getElementById("noteFilterClear");
const noteSort = document.getElementById("noteSort");
const noteListSummary = document.getElementById("noteListSummary");
const notesFilterTools = document.querySelector(".notes-filter-tools");
const noteTargetPreview = document.getElementById("noteTargetPreview");
const lockNoteTargetButton = document.getElementById("lockNoteTarget");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const readingPosition = document.getElementById("readingPosition");
const sentenceContextTools = document.querySelector(".sentence-context-tools");
const sentenceContext = document.getElementById("sentenceContext");
const previousSentenceButton = document.getElementById("previousSentence");
const nextSentenceButton = document.getElementById("nextSentence");
const nextUnstudiedSentenceButton = document.getElementById("nextUnstudiedSentence");
const nextReviewSentenceButton = document.getElementById("nextReviewSentence");
const regenerateSentenceButton = document.getElementById("regenerateSentence");
const markTranslationReviewedButton = document.getElementById("markTranslationReviewed");
const rejectTranslationButton = document.getElementById("rejectTranslation");
const copyStudyCardButton = document.getElementById("copyStudyCard");
const draftTranslationNoteButton = document.getElementById("draftTranslationNote");
const readingModeButton = document.getElementById("readingMode");
const studyModeButton = document.getElementById("studyMode");
const translationStatus = document.getElementById("translationStatus");
const gemmaRuntimeStatus = document.getElementById("gemmaRuntimeStatus");
const gemmaRuntimeStatusText = document.getElementById("gemmaRuntimeStatusText");
const gemmaRuntimeCheckButton = document.getElementById("gemmaRuntimeCheck");
const translationOutput = document.getElementById("translationOutput");
const translationUtility = document.querySelector(".translation-utility");
const translationCard = document.querySelector(".translation-card");
const studyPage = document.querySelector(".study-page");
const studyPanelToggle = document.getElementById("studyPanelToggle");
const studyPanelScrim = document.getElementById("studyPanelScrim");
const translationRecordsSummary = document.getElementById("translationRecordsSummary");
const studyProgress = document.getElementById("studyProgress");
const studyProgressText = document.getElementById("studyProgressText");
const continueStudyButton = document.getElementById("continueStudy");
const exportReviewedTranslations = document.getElementById("exportReviewedTranslations");
const exportAllTranslations = document.getElementById("exportAllTranslations");
const exportStudySession = document.getElementById("exportStudySession");
const studySessionSummary = document.getElementById("studySessionSummary");
const noteTags = document.getElementById("noteTags");
const noteText = document.getElementById("noteText");
const noteSaveButton = noteForm.querySelector("button[type='submit']");
const studyTabsContainer = document.querySelector(".study-tabs");
const studyTabs = Array.from(document.querySelectorAll(".study-tab"));
const studyPanels = Array.from(document.querySelectorAll(".study-panel"));
const sentenceNodes = Array.from(document.querySelectorAll(".reader-sentence"));
const sourceBundleTargetTypes = new Set(["segment", "section", "paragraph", "verse"]);
let selectedSentence = null;
let selectedTranslationRecord = null;
let activeTranslationRequest = 0;
let activeTranslationController = null;
let activeTranslationTargetKey = "";
let pendingTranslationRegenerate = false;
let translationMode = "reading";
let translationStatusTimer = null;
let translationRevealTimer = 0;
let sentenceRevealTimer = 0;
let sourceFocusTimer = 0;
let translationReviewFlashTimer = 0;
let sentenceReviewFlashTimer = 0;
let translationSentenceStates = new Map();
let translationSentenceStatesLoaded = false;
let gemmaRuntimeCheckController = null;
let recentlyChangedNoteId = "";
let activeReadingCueNode = null;
let readingPositionRefreshHandle = 0;
let noteDraftSaveTimer = 0;
let lockedNoteTarget = null;
let studyPanelDragState = null;
let ignoreNextStudyPanelToggleClick = false;
let pendingActionConfirmation = "";
let actionConfirmationTimer = 0;
const visibleSentenceNodes = new Set();
const RECENT_WORK_STORAGE_KEY = "philo.reader.recentWork";
const STUDY_PANEL_STORAGE_KEY = "philo.reader.studyPanelExpanded";
const STUDY_PANEL_DRAG_THRESHOLD = 36;
const ACTION_CONFIRM_MS = 4500;
const GEMMA_RUNTIME_COMMAND = ".\\run_reader_with_gemma.ps1";
const TRANSLATION_STATE_LABELS = {
  generated: "검토할 번역",
  reviewed: "저장한 번역",
  rejected: "제외한 번역"
};
const TRANSLATION_REVIEW_CHIP_LABELS = {
  generated: "검토",
  reviewed: "저장됨",
  rejected: "제외됨"
};
const TRANSLATION_REVIEW_CHIP_HINTS = {
  generated: "검토할 번역",
  reviewed: "저장된 번역",
  rejected: "제외된 번역"
};
const TRANSLATION_STATE_SHORT = {
  generated: "AI",
  reviewed: "저장",
  rejected: "제외"
};
const NOTE_DRAFT_STORAGE_KEY = [
  "philo.reader.noteDraft",
  researchData.corpus_id || researchData.author_id || "",
  researchData.work_id || "",
  researchData.variant_id || ""
].join(":");

function cleanText(value) {
  return String(value || "").replace(/[#¶]/g, "").replace(/\s+/g, " ").trim();
}

function currentWorkHref() {
  return `${location.pathname}${location.search}${location.hash || ""}`;
}

function rememberRecentWork() {
  try {
    const storage = window.localStorage;
    if (!storage) return;
    storage.setItem(RECENT_WORK_STORAGE_KEY, JSON.stringify({
      href: currentWorkHref(),
      title: cleanText(researchData.title || document.title || researchData.work_id || "현재 문서"),
      corpus_id: cleanText(researchData.corpus_id || researchData.author_id || ""),
      corpus_title: cleanText(researchData.corpus_title || ""),
      work_id: cleanText(researchData.work_id || ""),
      updated_at: new Date().toISOString()
    }));
  } catch (error) {
    return;
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStudyPanel(name, focusTab = false) {
  const targetTab = studyTabs.find((tab) => tab.dataset.studyTab === name);
  if (targetTab?.hidden) {
    name = "translation";
  }
  let activeTab = null;
  studyTabs.forEach((tab) => {
    const active = tab.dataset.studyTab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.tabIndex = active ? 0 : -1;
    if (active) {
      activeTab = tab;
    }
    if (active && focusTab) {
      tab.focus();
    }
  });
  studyPanels.forEach((panel) => {
    const active = panel.dataset.studyPanel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  ensureActiveStudyTabVisible(activeTab);
}

function visibleStudyTabs() {
  return studyTabs.filter((tab) => !tab.hidden);
}

function ensureActiveStudyTabVisible(tab) {
  if (!tab || !studyTabsContainer || !isMobileStudyLayout()) return;
  if (typeof tab.scrollIntoView !== "function") return;
  tab.scrollIntoView({
    block: "nearest",
    inline: "nearest",
    behavior: prefersReducedMotion() ? "auto" : "smooth"
  });
}

function activateStudyTabByIndex(index) {
  const tabs = visibleStudyTabs();
  if (!tabs.length) return;
  const nextIndex = (index + tabs.length) % tabs.length;
  const nextTab = tabs[nextIndex];
  setStudyPanel(nextTab.dataset.studyTab || "translation", true);
  setStudyPanelExpanded(true);
}

function storedStudyPanelExpanded() {
  try {
    return window.localStorage.getItem(STUDY_PANEL_STORAGE_KEY) === "true";
  } catch (error) {
    return false;
  }
}

function rememberStudyPanelExpanded(expanded) {
  try {
    window.localStorage.setItem(STUDY_PANEL_STORAGE_KEY, expanded ? "true" : "false");
  } catch (error) {
    return;
  }
}

function selectedSentencePositionLabel() {
  if (!selectedSentence) return "문장 선택";
  const index = sentenceIndex(selectedSentence.sentenceId);
  return index >= 0 ? `문장 ${index + 1} / ${sentenceNodes.length}` : selectedSentence.sentenceId;
}

function studyPanelToggleSummary() {
  if (!selectedSentence) return "문장 선택";
  if (translationCard && translationCard.classList.contains("is-loading")) {
    return "번역 중";
  }
  if (translationOutput && translationOutput.querySelector(".translation-error")) {
    return "다시 시도 필요";
  }
  if (selectedTranslationRecord) {
    return "번역 완료";
  }
  return "선택한 문장";
}

function updateStudyPanelToggleLabel() {
  if (!studyPage || !studyPanelToggle) return;
  const expanded = studyPage.classList.contains("is-expanded");
  const action = expanded ? "본문 보기" : "학습 열기";
  const summary = studyPanelToggleSummary();
  studyPanelToggle.innerHTML = `
    <span class="study-panel-toggle-action">${escapeHtml(action)}</span>
    <span class="study-panel-toggle-summary">${escapeHtml(summary)}</span>`;
  studyPanelToggle.setAttribute("aria-label", `${action}. ${summary}`);
}

function setStudyPanelExpanded(expanded, remember = false) {
  if (!studyPage || !studyPanelToggle) return;
  studyPage.classList.toggle("is-expanded", expanded);
  studyPanelToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  updateStudyPanelToggleLabel();
  updateStudyPanelScrim();
  if (remember) {
    rememberStudyPanelExpanded(expanded);
  }
}

function returnToSelectedSourceAfterPanelCollapse() {
  if (!isMobileStudyLayout()) return;
  const node = selectedSentenceNode();
  if (!node) return;
  window.requestAnimationFrame(() => {
    scrollSentenceIntoView(node);
    updateReadingPosition(node);
    updateTranslationTargetViewState();
    flashSourceFocus(node);
  });
}

function updateStudyPanelScrim() {
  if (!studyPanelScrim || !studyPage) return;
  const visible = isMobileStudyLayout() && studyPage.classList.contains("is-expanded");
  studyPanelScrim.hidden = !visible;
  studyPanelScrim.setAttribute("aria-hidden", visible ? "false" : "true");
}

function beginStudyPanelDrag(event) {
  if (!isMobileStudyLayout() || !studyPage || !studyPanelToggle) return;
  if (event.button !== undefined && event.button !== 0) return;
  studyPanelDragState = {
    pointerId: event.pointerId,
    startY: event.clientY,
    deltaY: 0,
    moved: false
  };
  studyPage.classList.add("is-dragging");
  if (studyPanelToggle.setPointerCapture) {
    studyPanelToggle.setPointerCapture(event.pointerId);
  }
}

function updateStudyPanelDrag(event) {
  if (!studyPanelDragState || event.pointerId !== studyPanelDragState.pointerId) return;
  studyPanelDragState.deltaY = event.clientY - studyPanelDragState.startY;
  if (Math.abs(studyPanelDragState.deltaY) > 8) {
    studyPanelDragState.moved = true;
    event.preventDefault();
  }
}

function finishStudyPanelDrag(event) {
  if (!studyPanelDragState || event.pointerId !== studyPanelDragState.pointerId) return;
  const { deltaY, moved } = studyPanelDragState;
  studyPanelDragState = null;
  studyPage.classList.remove("is-dragging");
  if (studyPanelToggle.releasePointerCapture) {
    try {
      studyPanelToggle.releasePointerCapture(event.pointerId);
    } catch (error) {
      // Pointer capture may already be released by the browser.
    }
  }
  if (!moved) return;
  ignoreNextStudyPanelToggleClick = true;
  if (deltaY <= -STUDY_PANEL_DRAG_THRESHOLD) {
    setStudyPanelExpanded(true, true);
  }
  if (deltaY >= STUDY_PANEL_DRAG_THRESHOLD) {
    setStudyPanelExpanded(false, true);
  }
}

function cancelStudyPanelDrag() {
  studyPanelDragState = null;
  if (studyPage) {
    studyPage.classList.remove("is-dragging");
  }
}

function syncTranslationModeDensity() {
  // Reading mode hides tools and metadata; translation and commentary stay readable.
  if (!translationCard) return;
  translationCard.classList.toggle("reading-mode", translationMode === "reading");
  translationCard.classList.toggle("study-mode", translationMode === "study");
}

function setTranslationMode(mode) {
  translationMode = mode === "study" ? "study" : "reading";
  readingModeButton.classList.toggle("active", translationMode === "reading");
  studyModeButton.classList.toggle("active", translationMode === "study");
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  syncTranslationModeDensity();
}

function setTranslationStatus(message, persistent = false) {
  window.clearTimeout(translationStatusTimer);
  translationStatus.textContent = message || "";
  translationStatus.classList.toggle("visible", Boolean(message));
  if (message && !persistent) {
    translationStatusTimer = window.setTimeout(() => {
      translationStatus.textContent = "";
      translationStatus.classList.remove("visible");
    }, 3200);
  }
}

function setTranslationUtilityVisible(visible) {
  if (!translationUtility) return;
  translationUtility.hidden = !visible;
}

function setGemmaRuntimeIndicator(state, text, title = "") {
  if (!gemmaRuntimeStatus || !gemmaRuntimeStatusText) return;
  gemmaRuntimeStatus.dataset.runtimeState = state;
  gemmaRuntimeStatusText.textContent = text;
  gemmaRuntimeStatus.title = title || text;
}

async function checkGemmaRuntimeStatus(announce = false) {
  if (!gemmaRuntimeStatus) return;
  if (gemmaRuntimeCheckController) {
    gemmaRuntimeCheckController.abort();
  }
  const controller = new AbortController();
  gemmaRuntimeCheckController = controller;
  const timeout = window.setTimeout(() => controller.abort(), 2500);
  setGemmaRuntimeIndicator("checking", "번역기 확인 중", "번역기 상태");
  setActionButtonBusy(gemmaRuntimeCheckButton, true);
  try {
    const response = await fetch("/api/health", { signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error("Runtime status unavailable");
    }
    const gemma = payload.gemma || {};
    if (gemma.reachable) {
      const model = Array.isArray(gemma.models) ? cleanText(gemma.models[0] || "") : "";
      const title = model ? `번역기 준비됨: ${model}` : "번역기 준비됨";
      setGemmaRuntimeIndicator("ready", "번역기 준비됨", title);
      if (announce) {
        setTranslationStatus("번역기 준비됨.");
      }
      return;
    }
    const error = cleanText(gemma.error || "번역기를 시작한 뒤 다시 확인하세요.");
    setGemmaRuntimeIndicator("offline", "번역기 꺼짐", error);
    if (announce) {
      setTranslationStatus("번역기가 꺼져 있습니다.", true);
    }
  } catch (error) {
    if (error && error.name === "AbortError" && gemmaRuntimeCheckController !== controller) {
      return;
    }
    const label = error && error.name === "AbortError" ? "번역기 확인 시간이 초과되었습니다" : "번역기를 사용할 수 없습니다";
    setGemmaRuntimeIndicator("unavailable", label, "리더 서버와 번역 서비스가 실행 중인지 확인하세요.");
    if (announce) {
      setTranslationStatus(label, true);
    }
  } finally {
    window.clearTimeout(timeout);
    if (gemmaRuntimeCheckController === controller) {
      gemmaRuntimeCheckController = null;
      setActionButtonBusy(gemmaRuntimeCheckButton, false);
    }
  }
}

function setTranslationRecordsSummary(text, state = "empty", counts = null) {
  if (!translationRecordsSummary) return;
  translationRecordsSummary.dataset.recordsState = state;
  if (!counts) {
    translationRecordsSummary.textContent = text;
    translationRecordsSummary.removeAttribute("aria-label");
    translationRecordsSummary.removeAttribute("title");
    return;
  }
  const total = Number(counts.total || 0);
  const sentenceCount = Number(counts.sentenceCount || 0);
  const generated = Number(counts.generated || 0);
  const reviewed = Number(counts.reviewed || 0);
  const rejected = Number(counts.rejected || 0);
  const reviewHint = total
    ? (generated
      ? `${generated.toLocaleString()}개 검토할 번역`
      : `${(reviewed || total).toLocaleString()}개 준비됨`)
    : "";
  const detailLabel = [
    text,
    total ? `${total.toLocaleString()}개 번역` : "저장된 번역 없음",
    sentenceCount ? `${sentenceCount.toLocaleString()}개 문장 학습됨` : "",
    generated ? `${generated.toLocaleString()}개 검토할 번역` : "",
    reviewed ? `${reviewed.toLocaleString()}개 저장됨` : "",
    rejected ? `${rejected.toLocaleString()}개 제외됨` : ""
  ].filter(Boolean).join(". ") + ".";
  translationRecordsSummary.setAttribute(
    "aria-label",
    detailLabel
  );
  translationRecordsSummary.title = detailLabel;
  translationRecordsSummary.innerHTML = `
    <span class="translation-records-summary-main">${escapeHtml(text)}</span>
    ${reviewHint ? `<span class="translation-records-summary-hint">${escapeHtml(reviewHint)}</span>` : ""}`;
}

function updateTranslationExportLinks(total, reviewed) {
  if (exportReviewedTranslations) {
    exportReviewedTranslations.dataset.exportCount = String(reviewed);
    exportReviewedTranslations.classList.toggle("is-empty", reviewed === 0);
    exportReviewedTranslations.title = reviewed
      ? `저장한 번역 ${reviewed}개 다운로드`
      : "아직 저장한 번역이 없습니다";
  }
  if (exportAllTranslations) {
    exportAllTranslations.dataset.exportCount = String(total);
    exportAllTranslations.classList.toggle("is-empty", total === 0);
    exportAllTranslations.title = total
      ? `번역 ${total}개 다운로드`
      : "아직 저장한 번역이 없습니다";
  }
}

function setStudyProgress(text, state = "loading", detail = "") {
  if (studyProgressText) {
    studyProgressText.textContent = text;
  }
  if (studyProgress) {
    studyProgress.dataset.progressState = state;
    if (detail) {
      studyProgress.setAttribute("aria-label", detail);
      studyProgress.title = detail;
    } else {
      studyProgress.removeAttribute("aria-label");
      studyProgress.removeAttribute("title");
    }
  }
}

function translationStateCountsFromSentences() {
  const counts = { generated: 0, reviewed: 0, rejected: 0 };
  translationSentenceStates.forEach((state) => {
    const reviewState = normalizedTranslationReviewState(state.reviewState);
    counts[reviewState] += 1;
  });
  return counts;
}

function updateStudyProgress() {
  if (!studyProgress) return;
  if (!translationSentenceStatesLoaded) {
    setStudyProgress("진행 확인 중", "loading", "학습 진행 상태를 확인하는 중입니다.");
    if (continueStudyButton) {
      continueStudyButton.textContent = "이어 읽기";
      continueStudyButton.disabled = true;
      continueStudyButton.title = "번역 상태를 불러오는 중입니다";
      continueStudyButton.dataset.studyAction = "continue";
    }
    return;
  }
  const studied = translationSentenceStates.size;
  const total = sentenceNodes.length;
  const remaining = Math.max(0, total - studied);
  const stateCounts = translationStateCountsFromSentences();
  const pendingReview = stateCounts.generated;
  const state = remaining > 0
    ? (studied ? "active" : "empty")
    : (pendingReview ? "review" : "complete");
  const progressText = remaining > 0
    ? (studied ? "읽던 곳부터 계속" : "첫 문장부터 시작")
    : (pendingReview ? "검토할 번역" : (stateCounts.reviewed ? "학습 기록 준비됨" : "모든 문장 학습 완료"));
  const detail = [
    `${total.toLocaleString()}개 문장 중 ${studied.toLocaleString()}개 번역됨`,
    remaining ? `${remaining.toLocaleString()}개 남음` : "남은 미번역 문장 없음",
    pendingReview ? `${pendingReview.toLocaleString()}개 검토할 번역` : ""
  ].filter(Boolean).join(". ") + ".";
  setStudyProgress(progressText, state, detail);
  if (continueStudyButton) {
    const wantsReview = remaining === 0 && pendingReview > 0;
    const wantsPreview = remaining === 0 && pendingReview === 0 && stateCounts.reviewed > 0;
    const nextIndex = wantsReview ? nextGeneratedSentenceIndex() : continueStudySentenceIndex();
    const nextLabel = nextIndex >= 0 ? sentencePositionText(sentenceNodeId(sentenceNodes[nextIndex])) : "";
    if (wantsPreview) {
      continueStudyButton.textContent = "기록 보기";
      continueStudyButton.dataset.studyAction = "preview-session";
      continueStudyButton.disabled = false;
      continueStudyButton.title = "노트와 번역 기록 보기";
      continueStudyButton.setAttribute("aria-label", "학습 기록 보기");
    } else {
      continueStudyButton.textContent = wantsReview ? "검토 계속" : "이어 읽기";
      continueStudyButton.dataset.studyAction = wantsReview ? "review-generated" : "continue";
      continueStudyButton.disabled = nextIndex < 0;
      continueStudyButton.title = nextIndex >= 0
        ? `${wantsReview ? "검토" : "이어 읽기"} ${nextLabel}`
        : (wantsReview ? "검토할 번역이 없습니다" : "모든 문장이 번역되었습니다");
      continueStudyButton.setAttribute("aria-label", nextIndex >= 0
        ? `${nextLabel} ${wantsReview ? "번역 검토" : "부터 이어 읽기"}`
        : (wantsReview ? "검토할 번역이 없습니다" : "학습 진행 완료"));
    }
  }
}

function normalizedTranslationReviewState(value) {
  const state = cleanText(value).toLowerCase();
  return TRANSLATION_STATE_LABELS[state] ? state : "generated";
}

function applySentenceTranslationState(item, flash = false) {
  const sentenceId = cleanText(item && (item.sentence_id || item.target_id));
  if (!sentenceId) return false;
  const node = document.getElementById(sentenceId);
  if (!node || !node.classList.contains("reader-sentence")) return false;
  const reviewState = normalizedTranslationReviewState(item.review_state);
  const label = TRANSLATION_STATE_LABELS[reviewState];
  translationSentenceStates.set(sentenceId, {
    reviewState,
    label,
    recordId: cleanText(item.record_id || item.id || ""),
    updatedAt: cleanText(item.updated_at || item.reviewed_at || item.generated_at || "")
  });
  if (!Object.prototype.hasOwnProperty.call(node.dataset, "originalTitle")) {
    node.dataset.originalTitle = node.getAttribute("title") || "";
  }
  node.classList.add("has-translation-state");
  node.dataset.translationState = reviewState;
  node.dataset.translationStateShort = TRANSLATION_STATE_SHORT[reviewState];
  node.dataset.translationStateLabel = label;
  const originalTitle = node.dataset.originalTitle;
  node.setAttribute("title", `${originalTitle ? `${originalTitle} / ` : ""}${label}`);
  if (flash) {
    flashSentenceReviewState(node, reviewState);
  }
  return true;
}

function clearSentenceTranslationStates(markLoaded = false) {
  translationSentenceStates = new Map();
  translationSentenceStatesLoaded = markLoaded;
  sentenceNodes.forEach((node) => {
    node.classList.remove("has-translation-state");
    node.removeAttribute("data-translation-state");
    node.removeAttribute("data-translation-state-short");
    node.removeAttribute("data-translation-state-label");
    if (Object.prototype.hasOwnProperty.call(node.dataset, "originalTitle")) {
      const originalTitle = node.dataset.originalTitle;
      if (originalTitle) {
        node.setAttribute("title", originalTitle);
      } else {
        node.removeAttribute("title");
      }
      delete node.dataset.originalTitle;
    }
  });
  updateStudyProgress();
  updateSentenceControls();
}

function applySentenceTranslationStates(states) {
  clearSentenceTranslationStates();
  translationSentenceStatesLoaded = true;
  if (!Array.isArray(states)) return;
  states.forEach((item) => {
    applySentenceTranslationState(item, false);
  });
  updateStudyProgress();
  updateSentenceControls();
}

function setStudySessionSummary(text, state = "empty", detail = "") {
  if (!studySessionSummary) return;
  studySessionSummary.textContent = text;
  studySessionSummary.dataset.sessionState = state;
  if (detail) {
    studySessionSummary.setAttribute("aria-label", detail);
    studySessionSummary.title = detail;
  } else {
    studySessionSummary.removeAttribute("aria-label");
    studySessionSummary.removeAttribute("title");
  }
}

function updateStudySessionExportLink(noteCount, translationCount) {
  if (!exportStudySession) return;
  const total = noteCount + translationCount;
  exportStudySession.dataset.exportCount = String(total);
  exportStudySession.classList.toggle("is-empty", total === 0);
  exportStudySession.title = total
    ? `학습 기록 다운로드: 노트 ${noteCount}개, 번역 ${translationCount}개`
    : "아직 이 기록에 노트나 번역이 없습니다";
}

function studySessionExportUrl(format = "json") {
  const params = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    notes_review_state: "reviewed",
    translation_review_state: "reviewed",
    format
  });
  return `/api/study-session/export?${params}`;
}

async function loadStudySessionSummary() {
  if (!studySessionSummary) return;
  try {
    const response = await fetch(studySessionExportUrl("json"));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "학습 기록을 사용할 수 없습니다");
    }
    const noteCount = Number(payload.note_count || 0);
    const translationCount = Number(payload.translation_count || 0);
    const total = noteCount + translationCount;
    const detail = total
      ? `내보낼 수 있습니다. 노트 ${noteCount.toLocaleString()}개, 번역 ${translationCount.toLocaleString()}개.`
      : "아직 내보낼 저장 항목이 없습니다.";
    setStudySessionSummary(
      total ? "내보내기 가능" : "내보낼 항목 없음",
      total ? "has-content" : "empty",
      detail
    );
    updateStudySessionExportLink(noteCount, translationCount);
  } catch (error) {
    setStudySessionSummary("학습 기록을 사용할 수 없습니다.", "unavailable");
    updateStudySessionExportLink(0, 0);
  }
}

async function loadTranslationRecordsSummary() {
  if (!translationRecordsSummary) return;
  const params = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || ""
  });
  try {
    const response = await fetch(`/api/sentence-translations/summary?${params}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "번역 기록을 사용할 수 없습니다");
    }
    const counts = payload.review_state_counts || {};
    const total = Number(payload.count || 0);
    const generated = Number(counts.generated || 0);
    const reviewed = Number(counts.reviewed || 0);
    const rejected = Number(counts.rejected || 0);
    const sentenceCount = Number(payload.sentence_state_count || 0);
    const summaryText = generated
      ? "검토할 번역"
      : (total ? "저장한 번역" : "아직 번역 없음");
    applySentenceTranslationStates(payload.sentence_states || []);
    setTranslationRecordsSummary(
      summaryText,
      generated ? "needs-review" : (total ? "has-records" : "empty"),
      { total, sentenceCount, generated, reviewed, rejected }
    );
    updateTranslationExportLinks(total, reviewed);
  } catch (error) {
    clearSentenceTranslationStates(false);
    setTranslationRecordsSummary("번역 기록을 사용할 수 없습니다.", "unavailable");
    updateTranslationExportLinks(0, 0);
  }
}

function setActionButtonBusy(button, isBusy) {
  if (!button) return;
  if (isBusy) {
    button.dataset.wasDisabled = button.disabled ? "true" : "false";
    button.disabled = true;
    button.classList.add("is-working");
    button.setAttribute("aria-busy", "true");
    return;
  }
  button.classList.remove("is-working");
  button.setAttribute("aria-busy", "false");
  if (button.dataset.wasDisabled !== "true") {
    button.disabled = false;
  }
  delete button.dataset.wasDisabled;
}

function actionConfirmationConfig(action) {
  if (action === "regenerate") {
    return {
      button: regenerateSentenceButton,
      defaultText: "다시 생성",
      defaultTitle: "번역 다시 생성",
      defaultAria: "번역 다시 생성",
      confirmText: "다시 생성 확인",
      confirmTitle: "이 번역을 바꾸려면 한 번 더 누르세요",
      confirmAria: "번역 다시 생성 확인",
      status: "한 번 더 누르면 이 번역을 새로 만듭니다.",
      blockMessage: selectedSentence ? "" : "문장을 먼저 선택하세요.",
      run: () => requestSentenceTranslation(true)
    };
  }
  if (action === "reject") {
    return {
      button: rejectTranslationButton,
      defaultText: "제외",
      defaultTitle: "번역 제외",
      defaultAria: "번역 제외",
      confirmText: "제외 확인",
      confirmTitle: "이 번역을 제외하려면 한 번 더 누르세요",
      confirmAria: "번역 제외 확인",
      status: "한 번 더 누르면 이 번역을 제외합니다.",
      blockMessage: selectedTranslationRecord && selectedTranslationRecord.id ? "" : "번역을 먼저 선택하세요.",
      run: () => updateTranslationReview("rejected")
    };
  }
  return null;
}

function resetActionConfirmationButton(config) {
  if (!config || !config.button) return;
  config.button.classList.remove("needs-confirm");
  config.button.textContent = config.defaultText;
  config.button.title = config.defaultTitle;
  config.button.setAttribute("aria-label", config.defaultAria);
}

function clearActionConfirmations(message = "") {
  window.clearTimeout(actionConfirmationTimer);
  actionConfirmationTimer = 0;
  pendingActionConfirmation = "";
  resetActionConfirmationButton(actionConfirmationConfig("regenerate"));
  resetActionConfirmationButton(actionConfirmationConfig("reject"));
  if (message) {
    setTranslationStatus(message);
  }
}

function hasPendingActionConfirmation() {
  return Boolean(pendingActionConfirmation);
}

function armActionConfirmation(action) {
  const config = actionConfirmationConfig(action);
  if (!config) return;
  clearActionConfirmations();
  pendingActionConfirmation = action;
  config.button.classList.add("needs-confirm");
  config.button.textContent = config.confirmText;
  config.button.title = config.confirmTitle;
  config.button.setAttribute("aria-label", config.confirmAria);
  setTranslationStatus(config.status, true);
  actionConfirmationTimer = window.setTimeout(() => clearActionConfirmations("동작을 취소했습니다."), ACTION_CONFIRM_MS);
}

function handleConfirmedAction(action) {
  const config = actionConfirmationConfig(action);
  if (!config) return;
  if (config.blockMessage) {
    setTranslationStatus(config.blockMessage, true);
    return;
  }
  if (pendingActionConfirmation !== action) {
    armActionConfirmation(action);
    return;
  }
  clearActionConfirmations();
  config.run();
}

function sentenceIndex(sentenceId) {
  return sentenceNodes.findIndex((node) => (node.dataset.sentenceId || node.id) === sentenceId);
}

function sentenceNodeId(node) {
  return node ? (node.dataset.sentenceId || node.id || "") : "";
}

function sentenceHasTranslationState(node) {
  const sentenceId = sentenceNodeId(node);
  return Boolean(sentenceId && translationSentenceStates.has(sentenceId));
}

function sentenceTranslationState(node) {
  const sentenceId = sentenceNodeId(node);
  const state = sentenceId ? translationSentenceStates.get(sentenceId) : null;
  return state ? normalizedTranslationReviewState(state.reviewState) : "";
}

function nextUnstudiedSentenceIndex() {
  if (!translationSentenceStatesLoaded || !sentenceNodes.length) return -1;
  const currentIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  for (let index = currentIndex + 1; index < sentenceNodes.length; index += 1) {
    if (!sentenceHasTranslationState(sentenceNodes[index])) {
      return index;
    }
  }
  return -1;
}

function firstUnstudiedSentenceIndex() {
  if (!translationSentenceStatesLoaded || !sentenceNodes.length) return -1;
  return sentenceNodes.findIndex((node) => !sentenceHasTranslationState(node));
}

function continueStudySentenceIndex() {
  const nextIndex = nextUnstudiedSentenceIndex();
  return nextIndex >= 0 ? nextIndex : firstUnstudiedSentenceIndex();
}

function nextGeneratedSentenceIndex() {
  if (!translationSentenceStatesLoaded || !sentenceNodes.length) return -1;
  const currentIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  for (let index = currentIndex + 1; index < sentenceNodes.length; index += 1) {
    if (sentenceTranslationState(sentenceNodes[index]) === "generated") {
      return index;
    }
  }
  return sentenceNodes.findIndex((node) => sentenceTranslationState(node) === "generated");
}

function sentencePositionText(sentenceId) {
  const index = sentenceIndex(sentenceId);
  return index >= 0 ? `문장 ${index + 1} / ${sentenceNodes.length}` : sentenceId;
}

function displayPositionLabel(value) {
  const text = cleanText(value);
  const paragraphMatch = /^Paragraph\s+(\d+)$/i.exec(text);
  if (paragraphMatch) return `문단 ${paragraphMatch[1]}`;
  const sectionMatch = /^Section\s+(.+)$/i.exec(text);
  if (sectionMatch) return `구역 ${sectionMatch[1]}`;
  const verseMatch = /^Verse\s+(.+)$/i.exec(text);
  if (verseMatch) return `절 ${verseMatch[1]}`;
  const quoteMatch = /^Quote\s+(\d+)$/i.exec(text);
  if (quoteMatch) return `인용 ${quoteMatch[1]}`;
  const lineMatch = /^Line\s+(.+)$/i.exec(text);
  if (lineMatch) return `행 ${lineMatch[1]}`;
  return text;
}

function selectedSentenceNode() {
  return selectedSentence ? document.getElementById(selectedSentence.sentenceId) : null;
}

function selectedSentenceIsVisible() {
  const node = selectedSentenceNode();
  if (!node) return false;
  const rect = node.getBoundingClientRect();
  const safeTop = isMobileStudyLayout() ? visibleViewportTop() : 0;
  const safeBottom = isMobileStudyLayout() ? mobileSentenceSafeBottom() : window.innerHeight;
  return rect.bottom > safeTop && rect.top < safeBottom;
}

function updateTranslationTargetViewState() {
  if (!translationTarget || !selectedSentence) return;
  const sourceVisible = selectedSentenceIsVisible();
  const sourceState = sourceVisible ? "visible" : "away";
  translationTarget.classList.toggle("is-source-visible", sourceVisible);
  translationTarget.classList.toggle("is-source-away", !sourceVisible);
  translationTarget.dataset.sourceState = sourceState;
  const status = translationTarget.querySelector("[data-selected-source-status]");
  if (status) {
    const statusLabel = sourceVisible ? "원문이 화면에 있음" : "원문이 화면 밖에 있음";
    status.dataset.sourceState = sourceState;
    status.textContent = statusLabel;
    status.setAttribute("aria-label", statusLabel);
  }
  const jumpButton = translationTarget.querySelector("[data-selected-source-jump]");
  if (jumpButton) {
    jumpButton.classList.toggle("is-source-away", !sourceVisible);
    jumpButton.textContent = sourceVisible ? "가운데로" : "원문 보기";
    jumpButton.setAttribute("aria-keyshortcuts", "S");
    jumpButton.setAttribute(
      "title",
      sourceVisible ? "선택한 원문 문장을 가운데로 이동" : "선택한 원문 문장 보기"
    );
    jumpButton.setAttribute(
      "aria-label",
      `선택한 원문 문장 ${selectedSentence.sentenceId} ${sourceVisible ? "가운데로 이동" : "보기"}`
    );
  }
}

function renderTranslationTarget() {
  if (!translationTarget) return;
  if (!selectedSentence) {
    translationTarget.textContent = "문장을 선택하세요.";
    translationTarget.classList.remove("is-source-visible", "is-source-away");
    delete translationTarget.dataset.sourceState;
    return;
  }
  const position = selectedSentencePositionLabel();
  const sourceText = cleanText(selectedSentence.text || "");
  translationTarget.innerHTML = `
    <div class="translation-target-main">
      <span class="translation-target-label">원문</span>
      <strong class="translation-target-id">${escapeHtml(position)}</strong>
      <span class="translation-target-status visually-hidden" data-selected-source-status></span>
      <p class="translation-target-excerpt" title="${escapeHtml(sourceText)}">${escapeHtml(sourceText)}</p>
    </div>
    <button type="button" data-selected-source-jump aria-keyshortcuts="S">원문 보기</button>`;
  updateTranslationTargetViewState();
}

function flashSourceFocus(node) {
  if (!node) return;
  window.clearTimeout(sourceFocusTimer);
  node.classList.remove("source-focus");
  void node.offsetWidth;
  node.classList.add("source-focus");
  sourceFocusTimer = window.setTimeout(() => {
    node.classList.remove("source-focus");
    sourceFocusTimer = 0;
  }, prefersReducedMotion() ? 0 : 1300);
}

function focusSelectedSourceSentence() {
  if (!selectedSentence) {
    setTranslationStatus("문장을 먼저 선택하세요.", true);
    return false;
  }
  const node = selectedSentenceNode();
  if (!node) {
    setTranslationStatus("선택한 원문을 이 페이지에서 찾을 수 없습니다.", true);
    return false;
  }
  scrollSentenceIntoView(node);
  updateReadingPosition(node);
  updateTranslationTargetViewState();
  flashSourceFocus(node);
  setTranslationStatus("선택한 원문으로 이동했습니다.");
  return true;
}

function readingCueTargetLine() {
  if (isMobileStudyLayout()) {
    return visibleViewportTop() + Math.max(120, visibleViewportHeight() * 0.34);
  }
  return window.innerHeight * 0.48;
}

function updateReadingPosition(node) {
  if (!node || !readingPosition) return;
  readingPosition.hidden = false;
  if (activeReadingCueNode && activeReadingCueNode !== node) {
    activeReadingCueNode.classList.remove("reading-cue");
  }
  activeReadingCueNode = node;
  activeReadingCueNode.classList.add("reading-cue");
  const sentenceId = node.dataset.sentenceId || node.id || "";
  const label = sentencePositionText(sentenceId);
  const isSelected = Boolean(selectedSentence && selectedSentence.sentenceId === sentenceId);
  const excerpt = cleanText(node.textContent);
  readingPosition.classList.toggle("is-selected-cue", isSelected);
  readingPosition.classList.toggle("is-selectable-cue", !isSelected);
  const action = isSelected
    ? '<span class="reading-position-current">선택됨</span>'
    : '<button type="button" data-reading-cue-select>이 문장 학습</button>';
  readingPosition.innerHTML = `
    <div class="reading-position-main">
      <span>읽는 위치</span>
      <strong>${escapeHtml(label)}</strong>
      ${action}
    </div>
    <p class="reading-position-excerpt" title="${escapeHtml(excerpt)}">${escapeHtml(excerpt)}</p>`;
  readingPosition.setAttribute("aria-label", `현재 읽는 위치: ${label}. ${excerpt}`);
}

function studyReadingCueSentence() {
  const node = activeReadingCueNode;
  if (!node || !node.classList.contains("reader-sentence")) return;
  const sentenceId = node.dataset.sentenceId || node.id || "";
  const wasSelected = selectedSentence && selectedSentence.sentenceId === sentenceId;
  selectSentence(node);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(node);
  if (!wasSelected || !selectedTranslationRecord) {
    requestSentenceTranslation(false);
  }
}

function refreshReadingPosition() {
  readingPositionRefreshHandle = 0;
  if (!sentenceNodes.length || !readingPosition) return;
  const candidates = visibleSentenceNodes.size ? Array.from(visibleSentenceNodes) : sentenceNodes;
  const targetLine = readingCueTargetLine();
  let bestNode = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  candidates.forEach((node) => {
    const rect = node.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) return;
    const center = rect.top + rect.height / 2;
    const distance = Math.abs(center - targetLine);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestNode = node;
    }
  });
  if (bestNode) {
    updateReadingPosition(bestNode);
  }
  updateTranslationTargetViewState();
}

function scheduleReadingPositionRefresh() {
  if (readingPositionRefreshHandle) return;
  readingPositionRefreshHandle = window.requestAnimationFrame(refreshReadingPosition);
}

function handleViewportLayoutChange() {
  scheduleReadingPositionRefresh();
  updateStudyPanelScrim();
  keepSentenceAboveStudyPanel(selectedSentenceNode());
  updateTranslationTargetViewState();
}

function initializeReadingPositionTracker() {
  if (!readingPosition || !sentenceNodes.length) return;
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          visibleSentenceNodes.add(entry.target);
        } else {
          visibleSentenceNodes.delete(entry.target);
        }
      });
      scheduleReadingPositionRefresh();
    }, {
      root: null,
      rootMargin: "-18% 0px -32% 0px",
      threshold: 0
    });
    sentenceNodes.forEach((node) => observer.observe(node));
  }
  window.addEventListener("scroll", scheduleReadingPositionRefresh, { passive: true });
  window.addEventListener("resize", handleViewportLayoutChange);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", handleViewportLayoutChange);
  }
  scheduleReadingPositionRefresh();
}

function updateSentenceContext() {
  if (!sentenceContext || !selectedSentence) {
    if (sentenceContext) {
      sentenceContext.hidden = true;
      sentenceContext.innerHTML = "";
    }
    if (sentenceContextTools) {
      sentenceContextTools.hidden = true;
    }
    return;
  }
  const index = sentenceIndex(selectedSentence.sentenceId);
  if (index < 0) {
    sentenceContext.hidden = true;
    sentenceContext.innerHTML = "";
    if (sentenceContextTools) {
      sentenceContextTools.hidden = true;
    }
    return;
  }
  const rows = [
    ["이전", index - 1],
    ["현재", index],
    ["다음", index + 1]
  ].filter((entry) => entry[1] >= 0 && entry[1] < sentenceNodes.length);
  if (sentenceContextTools) {
    sentenceContextTools.hidden = false;
  }
  sentenceContext.hidden = false;
  sentenceContext.innerHTML = rows.map(([label, rowIndex]) => {
    const node = sentenceNodes[rowIndex];
    const sentenceId = node.dataset.sentenceId || node.id || "";
    const isCurrent = sentenceId === selectedSentence.sentenceId;
    return `<button type="button" class="sentence-context-item${isCurrent ? " current" : ""}" data-sentence-id="${escapeHtml(sentenceId)}">
      <span class="sentence-context-label">${escapeHtml(label)}</span>
      <span class="sentence-context-text">${escapeHtml(cleanText(node.textContent))}</span>
    </button>`;
  }).join("");
}

function updateSentenceControls() {
  const index = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const hasSelection = index >= 0;
  const nextUnstudiedIndex = nextUnstudiedSentenceIndex();
  const nextReviewIndex = nextGeneratedSentenceIndex();
  previousSentenceButton.disabled = !hasSelection || index === 0;
  nextSentenceButton.disabled = !hasSelection || index === sentenceNodes.length - 1;
  if (nextUnstudiedSentenceButton) {
    nextUnstudiedSentenceButton.disabled = nextUnstudiedIndex < 0;
    const nextLabel = nextUnstudiedIndex >= 0
      ? sentencePositionText(sentenceNodeId(sentenceNodes[nextUnstudiedIndex]))
      : (translationSentenceStatesLoaded ? "현재 위치 뒤에 미번역 문장이 없습니다" : "번역 상태를 불러오는 중입니다");
    nextUnstudiedSentenceButton.title = nextUnstudiedIndex >= 0
      ? `${nextLabel}로 이동`
      : nextLabel;
    nextUnstudiedSentenceButton.setAttribute("aria-label", nextUnstudiedIndex >= 0
      ? `다음 미번역 문장, ${nextLabel}`
      : nextLabel);
  }
  if (nextReviewSentenceButton) {
    nextReviewSentenceButton.disabled = nextReviewIndex < 0;
    const nextReviewLabel = nextReviewIndex >= 0
      ? sentencePositionText(sentenceNodeId(sentenceNodes[nextReviewIndex]))
      : (translationSentenceStatesLoaded ? "검토할 번역이 없습니다" : "번역 상태를 불러오는 중입니다");
    nextReviewSentenceButton.title = nextReviewIndex >= 0
      ? `${nextReviewLabel} 검토`
      : nextReviewLabel;
    nextReviewSentenceButton.setAttribute("aria-label", nextReviewIndex >= 0
      ? `검토할 다음 번역, ${nextReviewLabel}`
      : nextReviewLabel);
  }
  updateStudyProgress();
  regenerateSentenceButton.disabled = !hasSelection;
  const hasRecord = Boolean(selectedTranslationRecord && selectedTranslationRecord.id);
  markTranslationReviewedButton.disabled = !hasRecord || selectedTranslationRecord.review_state === "reviewed";
  rejectTranslationButton.disabled = !hasRecord || selectedTranslationRecord.review_state === "rejected";
  copyStudyCardButton.disabled = !hasRecord;
  draftTranslationNoteButton.disabled = !hasRecord;
}

function currentTarget() {
  const id = decodeURIComponent(location.hash.replace(/^#/, "")) || "work";
  const node = id === "work" ? null : document.getElementById(id);
  const isSentence = Boolean(node && node.classList.contains("reader-sentence"));
  const label = node
    ? (isSentence ? sentencePositionText(id) : displayPositionLabel(node.dataset.label || node.textContent))
    : researchData.title;
  const type = node
    ? (isSentence ? "sentence" : (node.dataset.targetType || researchData.default_target_type || "segment"))
    : "work";
  const baseUrl = location.origin + location.pathname + location.search;
  const url = id === "work"
    ? baseUrl
    : baseUrl + "#" + encodeURIComponent(id);
  return { id, label, type, url };
}

function targetSnapshot(target = currentTarget()) {
  return {
    id: target.id || "work",
    label: displayPositionLabel(target.label || researchData.title || "현재 문서"),
    type: target.type || "work",
    url: target.url || location.href
  };
}

function selectedSentenceTargetSnapshot() {
  if (!selectedSentence) return targetSnapshot();
  const baseUrl = location.origin + location.pathname + location.search;
  return targetSnapshot({
    id: selectedSentence.sentenceId,
    label: selectedSentencePositionLabel(),
    type: "sentence",
    url: `${baseUrl}#${encodeURIComponent(selectedSentence.sentenceId)}`
  });
}

function noteTargetForSave() {
  return lockedNoteTarget || targetSnapshot();
}

function noteTargetTypeLabel(type) {
  if (type === "work") return "문서";
  if (type === "paragraph") return "문단";
  if (type === "verse") return "절";
  if (type === "section") return "구역";
  if (type === "sentence") return "문장";
  return cleanText(type || "대상");
}

function noteTargetDisplayText(target) {
  const safeTarget = targetSnapshot(target);
  const typeLabel = noteTargetTypeLabel(safeTarget.type);
  const label = displayPositionLabel(safeTarget.label || safeTarget.id);
  if (!label || label === typeLabel || label.startsWith(`${typeLabel} `)) {
    return label || typeLabel;
  }
  return `${typeLabel} / ${label}`;
}

function updateNoteTargetPreview() {
  if (!noteTargetPreview || !lockNoteTargetButton) return;
  const target = noteTargetForSave();
  const locked = Boolean(lockedNoteTarget);
  noteTargetPreview.classList.toggle("is-locked", locked);
  noteTargetPreview.innerHTML = `
    <span>${locked ? "고정된 노트 대상" : "선택 문장을 따라감"}</span>
    <strong>${escapeHtml(noteTargetDisplayText(target))}</strong>`;
  noteTargetPreview.setAttribute("aria-label", `${locked ? "고정된 노트 대상" : "노트 대상"}: ${noteTargetDisplayText(target)}`);
  lockNoteTargetButton.textContent = locked ? "고정 해제" : "대상 고정";
  lockNoteTargetButton.setAttribute("aria-pressed", locked ? "true" : "false");
}

function lockCurrentNoteTarget(announce = true) {
  lockedNoteTarget = targetSnapshot();
  updateNoteTargetPreview();
  saveNoteDraft();
  if (announce) {
    noteStatus.textContent = "노트 대상을 고정했습니다.";
  }
}

function unlockNoteTarget(announce = true) {
  lockedNoteTarget = null;
  updateNoteTargetPreview();
  saveNoteDraft(false);
  if (announce) {
    noteStatus.textContent = "노트 대상이 선택 문장을 따라갑니다.";
  }
}

function syncTargetDependentViews() {
  updateCitationPreview();
  updateNoteTargetPreview();
}

function selectedTranslationTargetKey() {
  if (!selectedSentence) return "";
  return [
    researchData.corpus_id || researchData.author_id || "",
    researchData.work_id || "",
    researchData.variant_id || "",
    selectedSentence.segmentId,
    selectedSentence.sentenceId
  ].join("|");
}

function citationText() {
  const target = currentTarget();
  if (researchData.corpus_id === "bible") {
    const source = researchData.source_label || researchData.variant_id || "Bible";
    const label = target.id === "work" ? (researchData.citation_title || researchData.title) : target.label;
    return `${label}, ${source}. Personal Archive of Literature. ${target.url}`;
  }
  const position = target.id === "work" ? "" : `, ${target.label}`;
  const author = researchData.author || researchData.corpus_title || researchData.corpus_id;
  return `${author}, ${researchData.title} (${researchData.work_id})${position}. Personal Archive of Literature. ${target.url}`;
}

function citationPreviewText() {
  const target = currentTarget();
  if (researchData.corpus_id === "bible") {
    const source = researchData.source_label || researchData.variant_id || "Bible";
    const label = target.id === "work" ? (researchData.citation_title || researchData.title) : target.label;
    return `${label}, ${source}. Personal Archive of Literature.`;
  }
  const position = target.id === "work" ? "" : `, ${target.label}`;
  const author = researchData.author || researchData.corpus_title || researchData.corpus_id;
  return `${author}, ${researchData.title} (${researchData.work_id})${position}. Personal Archive of Literature.`;
}

function sourceBundleUrl() {
  const target = currentTarget();
  if (!sourceBundleTargetTypes.has(target.type) || !target.id || target.id === "work") {
    return "";
  }
  const params = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    target_id: target.id
  });
  if (researchData.variant_id) {
    params.set("variant_id", researchData.variant_id);
  }
  return `${location.origin}/api/source-target?${params}`;
}

function sentenceFromNode(node) {
  if (!node || !node.classList || !node.classList.contains("reader-sentence")) {
    return null;
  }
  const parent = node.closest("[data-target-type='paragraph'], .verse");
  return {
    sentenceId: node.dataset.sentenceId || node.id || "",
    segmentId: node.dataset.segmentId || (parent ? parent.id : ""),
    label: cleanText(node.dataset.label || node.textContent),
    text: cleanText(node.textContent)
  };
}

function selectSentence(node, updateHash = true) {
  const sentence = sentenceFromNode(node);
  if (!sentence || !sentence.sentenceId || !sentence.segmentId) return;
  const sameSentence = selectedSentence && selectedSentence.sentenceId === sentence.sentenceId;
  document.querySelectorAll(".reader-sentence.selected").forEach((item) => {
    item.classList.remove("selected");
  });
  node.classList.add("selected");
  selectedSentence = sentence;
  if (!sameSentence) {
    selectedTranslationRecord = null;
    clearActionConfirmations();
  }
  renderTranslationTarget();
  updateSentenceContext();
  updateSentenceControls();
  updateStudyPanelToggleLabel();
  updateReadingPosition(node);
  if (updateHash) {
    history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(sentence.sentenceId)}`);
  }
  rememberRecentWork();
  syncTargetDependentViews();
}

function selectSentenceFromHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!id) return;
  const node = document.getElementById(id);
  if (node && node.classList.contains("reader-sentence")) {
    selectSentence(node, false);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    scrollSentenceIntoView(node);
    keepSentenceAboveStudyPanel(node);
  }
}

function prefersReducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function sentenceScrollBlock() {
  return window.matchMedia && window.matchMedia("(max-width: 860px)").matches ? "start" : "center";
}

function isMobileStudyLayout() {
  return Boolean(window.matchMedia && window.matchMedia("(max-width: 860px)").matches);
}

function visibleViewportTop() {
  return window.visualViewport ? window.visualViewport.offsetTop : 0;
}

function visibleViewportHeight() {
  return window.visualViewport ? window.visualViewport.height : window.innerHeight;
}

function visibleViewportBottom() {
  return visibleViewportTop() + visibleViewportHeight();
}

function studyPanelViewportHeight() {
  if (!isMobileStudyLayout() || !studyPage) return 0;
  return Math.ceil(studyPage.getBoundingClientRect().height);
}

function mobileSentenceSafeBottom() {
  const bottom = visibleViewportBottom() - studyPanelViewportHeight() - 18;
  return Math.max(visibleViewportTop() + 96, bottom);
}

function adjustSentenceAboveStudyPanel(node) {
  const rect = node.getBoundingClientRect();
  const safeBottom = mobileSentenceSafeBottom();
  if (rect.bottom > safeBottom) {
    window.scrollBy({
      top: rect.bottom - safeBottom,
      left: 0,
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
}

function keepSentenceAboveStudyPanel(node) {
  if (!node || !isMobileStudyLayout()) return;
  window.requestAnimationFrame(() => adjustSentenceAboveStudyPanel(node));
  window.setTimeout(() => adjustSentenceAboveStudyPanel(node), prefersReducedMotion() ? 0 : 230);
}

function scrollSentenceIntoView(node) {
  if (!node || typeof node.scrollIntoView !== "function") return;
  node.scrollIntoView({
    block: sentenceScrollBlock(),
    inline: "nearest",
    behavior: prefersReducedMotion() ? "auto" : "smooth"
  });
  keepSentenceAboveStudyPanel(node);
}

function navigateSentence(delta) {
  if (!sentenceNodes.length) return;
  const currentIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const initialIndex = delta < 0 ? sentenceNodes.length - 1 : 0;
  const nextIndex = currentIndex < 0
    ? initialIndex
    : Math.min(sentenceNodes.length - 1, Math.max(0, currentIndex + delta));
  const nextNode = sentenceNodes[nextIndex];
  if (!nextNode) return;
  const nextSentenceId = nextNode.dataset.sentenceId || nextNode.id || "";
  const wasSelected = selectedSentence && selectedSentence.sentenceId === nextSentenceId;
  selectSentence(nextNode);
  scrollSentenceIntoView(nextNode);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(nextNode);
  if (!wasSelected || !selectedTranslationRecord) {
    requestSentenceTranslation(false);
  }
}

function navigateToNextUnstudiedSentence() {
  const nextIndex = nextUnstudiedSentenceIndex();
  if (nextIndex < 0) {
    setTranslationStatus(
      translationSentenceStatesLoaded
        ? "현재 위치 뒤에 미번역 문장이 없습니다."
        : "번역 상태를 아직 불러오는 중입니다.",
      true
    );
    return;
  }
  const nextNode = sentenceNodes[nextIndex];
  if (!nextNode) return;
  selectSentence(nextNode);
  scrollSentenceIntoView(nextNode);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(nextNode);
  requestSentenceTranslation(false);
}

function navigateToNextReviewSentence() {
  const nextIndex = nextGeneratedSentenceIndex();
  if (nextIndex < 0) {
    setTranslationStatus(
      translationSentenceStatesLoaded
        ? "검토할 번역이 없습니다."
        : "번역 상태를 아직 불러오는 중입니다.",
      true
    );
    return;
  }
  const nextNode = sentenceNodes[nextIndex];
  if (!nextNode) return;
  selectSentence(nextNode);
  scrollSentenceIntoView(nextNode);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(nextNode);
  requestSentenceTranslation(false);
}

function continueStudy() {
  const action = continueStudyButton?.dataset.studyAction || "continue";
  if (action === "preview-session") {
    previewStudySession();
    return;
  }
  const nextIndex = action === "review-generated"
    ? nextGeneratedSentenceIndex()
    : continueStudySentenceIndex();
  if (nextIndex < 0) {
    setTranslationStatus(
      translationSentenceStatesLoaded
        ? (action === "review-generated" ? "검토할 번역이 없습니다." : "모든 문장이 번역되었습니다.")
        : "번역 상태를 아직 불러오는 중입니다.",
      true
    );
    return;
  }
  const nextNode = sentenceNodes[nextIndex];
  if (!nextNode) return;
  selectSentence(nextNode);
  scrollSentenceIntoView(nextNode);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(nextNode);
  requestSentenceTranslation(false);
}

function renderList(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<ul>${values.map((value) => `<li>${escapeHtml(cleanText(value))}</li>`).join("")}</ul>`;
}

function optionalCautions(record) {
  const cautions = renderList(record.cautions);
  if (!cautions) return "";
  return `<section class="translation-section translation-extra" data-translation-section="cautions">
      <h3>주의</h3>
      ${cautions}
    </section>`;
}

function renderCommentary(commentary) {
  const text = cleanText(commentary || "");
  return `
    <section class="translation-section translation-commentary" data-translation-section="commentary">
      <h3>해설</h3>
      <p>${escapeHtml(text)}</p>
    </section>`;
}

function renderTranslationEmptyState() {
  if (!translationOutput || selectedSentence) return;
  setTranslationUtilityVisible(false);
  translationOutput.hidden = false;
  translationOutput.setAttribute("aria-busy", "false");
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  translationOutput.innerHTML = `
    <div class="translation-result translation-empty-state" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>번역</h3>
        <p class="translation-primary translation-empty-copy">문장을 누르면 번역됩니다.</p>
      </section>
    </div>`;
}

function translationJumpNav(record) {
  const hasCommentary = Boolean(cleanText(record.commentary || record.interpretation || ""));
  const buttons = [
    ["translation", "번역"],
    hasCommentary ? ["commentary", "해설"] : null
  ].filter(Boolean);
  return `<div class="translation-jump-nav" aria-label="번역 결과 구역">
    <button type="button" data-selected-source-jump aria-keyshortcuts="S">원문</button>
    ${buttons.map(([section, label]) => `<button type="button" data-translation-jump="${escapeHtml(section)}">${escapeHtml(label)}</button>`).join("")}
  </div>`;
}

function translationResultToolbar(record, _cached, reviewState) {
  const targetLabel = selectedSentence
    ? selectedSentencePositionLabel()
    : cleanText(record.sentence_id || "문장");
  const sourceText = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  const stateLabel = TRANSLATION_REVIEW_CHIP_LABELS[normalizedReviewState];
  const stateHint = TRANSLATION_REVIEW_CHIP_HINTS[normalizedReviewState] || stateLabel;
  const reviewLabel = stateHint || stateLabel;
  return `<details class="translation-result-toolbar translation-result-details translation-extra">
    <summary>
      <span>원문</span>
    </summary>
    <div class="translation-result-detail-body">
      <div class="translation-result-meta">
        <span class="translation-result-kicker">문장</span>
        <strong class="translation-result-target">${escapeHtml(targetLabel)}</strong>
        <span class="translation-review-state" data-review-state="${escapeHtml(normalizedReviewState)}" title="${escapeHtml(reviewLabel)}" aria-label="${escapeHtml(reviewLabel)}">
          <span>${escapeHtml(stateLabel)}</span>
        </span>
      </div>
      ${sourceText ? `<section class="translation-section translation-source-detail">
        <h3>원문</h3>
        <p>${escapeHtml(sourceText)}</p>
      </section>` : ""}
      ${translationJumpNav(record)}
    </div>
  </details>`;
}

function translationQuickActions(reviewState) {
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  const reviewAction = normalizedReviewState === "reviewed"
    ? '<span class="translation-quick-state" data-review-state="reviewed" title="저장된 번역" aria-label="저장된 번역">저장됨</span>'
    : '<button type="button" data-translation-quick-action="mark-reviewed" title="번역 저장" aria-label="번역 저장">저장</button>';
  const selectedIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const nextSentenceDisabled = selectedIndex < 0 || selectedIndex >= sentenceNodes.length - 1
    ? " disabled"
    : "";
  return `<div class="translation-reading-actions" aria-label="학습 동작">
      <button type="button" data-translation-quick-action="next-sentence" title="다음 문장을 선택하고 번역" aria-label="다음 문장을 선택하고 번역"${nextSentenceDisabled}>다음 문장</button>
      <details class="translation-secondary-actions" aria-label="번역 저장 또는 메모">
        <summary>저장 · 메모</summary>
        <div class="translation-secondary-actions-body">
          <button type="button" data-translation-quick-action="draft-note" title="번역으로 메모 추가" aria-label="번역으로 메모 추가">메모 추가</button>
          ${reviewAction}
        </div>
      </details>
    </div>
    <div class="translation-quick-actions translation-extra" aria-label="학습 대기열">
      <button type="button" data-translation-quick-action="continue" title="이어 읽기">이어 읽기</button>
    </div>`;
}

function focusNextSentenceAction() {
  const nextAction = translationOutput?.querySelector('[data-translation-quick-action="next-sentence"]:not(:disabled)');
  if (!nextAction || typeof nextAction.focus !== "function") return false;
  window.requestAnimationFrame(() => {
    try {
      nextAction.focus({ preventScroll: true });
    } catch (error) {
      nextAction.focus();
    }
  });
  return true;
}

function setTranslationReviewVisualState(reviewState) {
  if (!translationCard) return;
  const normalizedReviewState = reviewState ? normalizedTranslationReviewState(reviewState) : "";
  if (normalizedReviewState) {
    translationCard.dataset.reviewState = normalizedReviewState;
  } else {
    delete translationCard.dataset.reviewState;
  }
}

function flashTranslationReviewState(reviewState) {
  if (!translationCard) return;
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  window.clearTimeout(translationReviewFlashTimer);
  translationCard.classList.remove("review-state-changed", "review-state-reviewed", "review-state-rejected", "review-state-generated");
  void translationCard.offsetWidth;
  translationCard.classList.add("review-state-changed", `review-state-${normalizedReviewState}`);
  translationReviewFlashTimer = window.setTimeout(() => {
    translationCard.classList.remove("review-state-changed", "review-state-reviewed", "review-state-rejected", "review-state-generated");
    translationReviewFlashTimer = 0;
  }, prefersReducedMotion() ? 0 : 1450);
}

function setTranslationBusy(isBusy) {
  if (translationCard) {
    translationCard.classList.toggle("is-loading", isBusy);
  }
  translationOutput.setAttribute("aria-busy", isBusy ? "true" : "false");
  updateStudyPanelToggleLabel();
}

function translationOutputUsesInternalScroll() {
  if (!translationOutput) return false;
  const styles = window.getComputedStyle ? window.getComputedStyle(translationOutput) : null;
  const overflowY = styles ? styles.overflowY : "";
  if (overflowY === "visible" || overflowY === "clip") return false;
  return translationOutput.scrollHeight > translationOutput.clientHeight + 1;
}

function resetTranslationOutputScroll() {
  translationOutput.scrollTop = 0;
  if (!translationOutputUsesInternalScroll() && studyPage) {
    studyPage.scrollTop = 0;
  }
}

function studyPanelStickyOffset() {
  if (!isMobileStudyLayout() || !studyPage?.classList.contains("is-expanded")) return 0;
  const toggleHeight = studyPanelToggle ? studyPanelToggle.offsetHeight + 8 : 0;
  const tabsHeight = studyTabsContainer ? studyTabsContainer.offsetHeight : 0;
  return toggleHeight + tabsHeight + 8;
}

function scrollTranslationSectionIntoView(sectionName) {
  const section = Array.from(translationOutput.querySelectorAll("[data-translation-section]"))
    .find((item) => item.dataset.translationSection === sectionName);
  if (!section) return;
  const stickyOffset = 8;
  const behavior = prefersReducedMotion() ? "auto" : "smooth";
  if (translationOutputUsesInternalScroll()) {
    const top = Math.max(0, section.offsetTop - translationOutput.offsetTop - stickyOffset);
    translationOutput.scrollTo({ top, behavior });
  } else if (studyPage) {
    const containerRect = studyPage.getBoundingClientRect();
    const sectionRect = section.getBoundingClientRect();
    const top = Math.max(0, studyPage.scrollTop + sectionRect.top - containerRect.top - stickyOffset - studyPanelStickyOffset());
    studyPage.scrollTo({ top, behavior });
  } else {
    section.scrollIntoView({ block: "start", inline: "nearest", behavior });
  }
  section.classList.add("is-jump-target");
  window.setTimeout(() => section.classList.remove("is-jump-target"), prefersReducedMotion() ? 0 : 900);
}

function renderTranslationPending(regenerate = false) {
  selectedTranslationRecord = null;
  pendingTranslationRegenerate = Boolean(regenerate);
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  setTranslationBusy(true);
  resetTranslationOutputScroll();
  const actionLabel = regenerate ? "다시 생성 중" : "번역 중";
  const commentaryLabel = regenerate ? "해설 다시 준비 중" : "해설 준비 중";
  translationOutput.innerHTML = `
    <div class="translation-result translation-pending-result" role="status" aria-live="polite" aria-label="${escapeHtml(actionLabel)}">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>번역</h3>
        <p class="translation-primary translation-pending-copy">${escapeHtml(actionLabel)}</p>
      </section>
      <section class="translation-section translation-commentary translation-pending-commentary" data-translation-section="commentary">
        <h3>해설</h3>
        <p class="translation-unavailable-copy">${escapeHtml(commentaryLabel)}</p>
      </section>
      <div class="translation-loading-actions">
        <button type="button" data-translation-cancel>취소</button>
      </div>
    </div>`;
  updateSentenceControls();
}

function translationErrorIsRuntime(message) {
  const text = cleanText(message).toLowerCase();
  if (!text) return true;
  return (
    text.includes("gemma runtime") ||
    text.includes("translator is offline") ||
    text.includes("translator offline") ||
    text.includes("runtime is not") ||
    text.includes("translation service is not running") ||
    text.includes("failed to fetch") ||
    text.includes("networkerror") ||
    text.includes("load failed") ||
    text.includes("번역기") ||
    text.includes("번역 서비스")
  );
}

function translationErrorDisplayMessage(message) {
  return translationErrorIsRuntime(message)
    ? "번역기를 시작한 뒤 다시 시도하세요."
    : cleanText(message || "번역을 사용할 수 없습니다.");
}

function runtimeRecoveryMarkup(message) {
  if (!translationErrorIsRuntime(message)) return "";
  return `
      <div class="translation-runtime-help">
        <p class="translation-runtime-note">명령을 복사해 PowerShell에 붙여넣으세요.</p>
        <button type="button" data-translation-copy-runtime>명령 복사</button>
        <details class="translation-runtime-details">
          <summary>명령 보기</summary>
          <code class="translation-runtime-command">${escapeHtml(GEMMA_RUNTIME_COMMAND)}</code>
        </details>
      </div>`;
}

function renderTranslationError(message) {
  selectedTranslationRecord = null;
  const retryMode = pendingTranslationRegenerate ? "regenerate" : "translate";
  const retryLabel = pendingTranslationRegenerate ? "다시 생성" : "번역 다시 시도";
  const cleanMessage = cleanText(message || "번역기가 꺼져 있습니다.");
  const isRuntimeError = translationErrorIsRuntime(cleanMessage);
  const displayMessage = translationErrorDisplayMessage(cleanMessage);
  pendingTranslationRegenerate = false;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-result translation-error" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>번역</h3>
        <p class="translation-primary translation-unavailable-copy">번역을 사용할 수 없습니다.</p>
      </section>
      <section class="translation-section translation-commentary" data-translation-section="commentary">
        <h3>해설</h3>
        <p class="translation-unavailable-copy">${escapeHtml(displayMessage)}</p>
      </section>
      <div class="translation-recovery-panel">
        ${runtimeRecoveryMarkup(cleanMessage)}
        <div class="translation-error-actions">
          <button type="button" data-translation-retry="${escapeHtml(retryMode)}">${escapeHtml(retryLabel)}</button>
          ${isRuntimeError ? '<button type="button" data-translation-check-runtime>번역기 확인</button>' : ""}
        </div>
      </div>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function renderTranslationCancelled(message = "번역 요청이 취소되었습니다.") {
  selectedTranslationRecord = null;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  resetTranslationOutputScroll();
  const position = selectedSentence ? selectedSentencePositionLabel() : "선택한 문장";
  const retryMode = pendingTranslationRegenerate ? "regenerate" : "translate";
  const retryLabel = pendingTranslationRegenerate ? "다시 생성" : "다시 시도";
  pendingTranslationRegenerate = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  translationOutput.innerHTML = `
    <div class="translation-result translation-cancelled" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>번역</h3>
        <p class="translation-primary translation-unavailable-copy">번역이 취소되었습니다.</p>
      </section>
      <section class="translation-section translation-commentary" data-translation-section="commentary">
        <h3>해설</h3>
        <p class="translation-unavailable-copy">${escapeHtml(cleanText(message))} ${escapeHtml(position)}에는 번역을 저장하지 않았습니다.</p>
      </section>
      <div class="translation-recovery-panel translation-error-actions">
        <button type="button" data-translation-retry="${escapeHtml(retryMode)}">${escapeHtml(retryLabel)}</button>
      </div>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function renderStudySessionPreviewPending() {
  selectedTranslationRecord = null;
  pendingTranslationRegenerate = false;
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", false);
  translationOutput.classList.toggle("study-mode", true);
  setTranslationBusy(true);
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-loading" role="status" aria-live="polite" aria-label="학습 기록 불러오는 중">
      <span class="loading-spinner" aria-hidden="true"></span>
      <span class="translation-loading-copy">
        <strong>학습 기록 불러오는 중</strong>
        <span>노트와 번역</span>
      </span>
    </div>
    <div class="translation-skeleton translation-study-skeleton" aria-hidden="true">
      <div class="translation-skeleton-block primary">
        <span class="translation-skeleton-heading"></span>
        <span class="translation-skeleton-line wide"></span>
        <span class="translation-skeleton-line"></span>
      </div>
    </div>`;
}

function sessionPreviewItems(items, kind) {
  if (!Array.isArray(items) || !items.length) {
    const label = kind === "notes" ? "노트" : "번역";
    return `<p class="session-preview-empty">이 기록에 ${escapeHtml(label)}이 없습니다.</p>`;
  }
  const hasMore = items.length > 3;
  return `<div class="session-preview-group${hasMore ? " is-collapsed" : ""}" data-session-preview-group>
    <ol class="session-preview-list">
    ${items.map((item, index) => {
      const label = cleanText(item.target_label || item.sentence_id || item.target_id || item.work_id || "학습 항목");
      const body = cleanText(kind === "notes"
        ? (item.note || item.quote || "")
        : (item.translation || item.commentary || item.source_text_excerpt || ""));
      const targetId = sessionPreviewTargetId(item);
      return `<li${index >= 3 ? ' class="session-preview-extra"' : ""}>
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(body || "저장된 학습 항목")}</span>
        </div>
        ${targetId ? `<button type="button" data-session-preview-target="${escapeHtml(targetId)}">열기</button>` : ""}
      </li>`;
    }).join("")}
    </ol>
    ${hasMore ? `<button type="button" class="session-preview-toggle" data-session-preview-toggle aria-expanded="false">전체 ${items.length}개 보기</button>` : ""}
  </div>`;
}

function sessionPreviewTargetId(item) {
  const directId = cleanText(item && (item.sentence_id || item.target_id || ""));
  if (directId) return directId;
  const url = cleanText(item && (item.target_url || item.url || ""));
  const hashIndex = url.indexOf("#");
  if (hashIndex === -1 || hashIndex === url.length - 1) return "";
  return decodeURIComponent(url.slice(hashIndex + 1));
}

function openSessionPreviewTarget(targetId) {
  const id = cleanText(targetId);
  const node = id ? document.getElementById(id) : null;
  if (!node) {
    setTranslationStatus("이 페이지에서 해당 원문 위치를 찾을 수 없습니다.", true);
    return;
  }
  if (node.classList.contains("reader-sentence")) {
    selectSentence(node);
    scrollSentenceIntoView(node);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    keepSentenceAboveStudyPanel(node);
    requestSentenceTranslation(false);
    return;
  }
  history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(id)}`);
  node.scrollIntoView({
    block: "center",
    inline: "nearest",
    behavior: prefersReducedMotion() ? "auto" : "smooth"
  });
  setTranslationStatus("원문 위치를 열었습니다.");
}

function toggleSessionPreviewGroup(button) {
  const group = button.closest("[data-session-preview-group]");
  if (!group) return;
  const expanded = group.classList.toggle("is-expanded");
  group.classList.toggle("is-collapsed", !expanded);
  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  button.textContent = expanded ? "접기" : `전체 ${group.querySelectorAll("li").length}개 보기`;
}

async function copyStudySessionMarkdown(button) {
  setActionButtonBusy(button, true);
  setTranslationStatus("학습 기록을 복사하는 중입니다...", true);
  try {
    const response = await fetch(studySessionExportUrl("markdown"));
    if (!response.ok) {
      throw new Error("학습 기록을 불러오지 못했습니다.");
    }
    const markdown = await response.text();
    await copyText(markdown);
    setTranslationStatus("학습 기록을 복사했습니다.");
  } catch (error) {
    const message = cleanText(error && error.message ? error.message : "학습 기록을 복사하지 못했습니다.");
    setTranslationStatus(message, true);
  } finally {
    setActionButtonBusy(button, false);
  }
}

function renderStudySessionPreview(payload) {
  selectedTranslationRecord = null;
  pendingTranslationRegenerate = false;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", false);
  translationOutput.classList.toggle("study-mode", true);
  resetTranslationOutputScroll();
  const noteCount = Number(payload.note_count || 0);
  const translationCount = Number(payload.translation_count || 0);
  const exportUrl = studySessionExportUrl("markdown");
  translationOutput.innerHTML = `
    <div class="study-session-preview">
      <div class="study-session-preview-header">
        <span>학습 기록</span>
        <strong>${escapeHtml(researchData.title || researchData.work_id || "현재 문서")}</strong>
        <div class="study-session-preview-actions">
          <button type="button" data-session-preview-copy>기록 복사</button>
          <a href="${escapeHtml(exportUrl)}">기록 열기</a>
        </div>
      </div>
      <div class="study-session-preview-counts" aria-label="학습 기록 수">
        <span>노트 ${noteCount}개</span>
        <span>번역 ${translationCount}개</span>
      </div>
      <section>
        <h3>노트</h3>
        ${sessionPreviewItems(payload.notes, "notes")}
      </section>
      <section>
        <h3>번역</h3>
        ${sessionPreviewItems(payload.translations, "translations")}
      </section>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function renderStudySessionPreviewError(message) {
  selectedTranslationRecord = null;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-error" role="note">
      <h3>학습 기록을 볼 수 없습니다</h3>
      <p>${escapeHtml(cleanText(message || "검토된 학습 기록을 불러오지 못했습니다."))}</p>
      <div class="translation-error-actions">
        <a href="${escapeHtml(studySessionExportUrl("markdown"))}">기록 열기</a>
      </div>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

async function previewStudySession() {
  clearActionConfirmations();
  renderStudySessionPreviewPending();
  setTranslationStatus("학습 기록을 불러오는 중입니다...", true);
  setActionButtonBusy(continueStudyButton, true);
  try {
    const response = await fetch(studySessionExportUrl("json"));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "학습 기록을 볼 수 없습니다");
    }
    renderStudySessionPreview(payload);
    setTranslationStatus("학습 기록이 준비되었습니다.");
  } catch (error) {
    const message = cleanText(error && error.message ? error.message : "학습 기록을 볼 수 없습니다.");
    renderStudySessionPreviewError(message);
    setTranslationStatus(message, true);
  } finally {
    setActionButtonBusy(continueStudyButton, false);
    updateStudyProgress();
  }
}

function renderTranslationRecord(record, cached, reviewFlashState = "") {
  selectedTranslationRecord = record;
  pendingTranslationRegenerate = false;
  const reviewState = normalizedTranslationReviewState(record.review_state || "generated");
  setTranslationBusy(false);
  setTranslationReviewVisualState(reviewState);
  setTranslationUtilityVisible(true);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-result">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>번역</h3>
        <p class="translation-primary">${escapeHtml(cleanText(record.translation || ""))}</p>
      </section>
      ${renderCommentary(record.commentary || record.interpretation || "")}
      ${translationQuickActions(reviewState)}
      ${optionalCautions(record)}
      ${translationResultToolbar(record, cached, reviewState)}
    </div>
  `;
  applySentenceTranslationState(record, Boolean(reviewFlashState));
  if (reviewFlashState) {
    flashTranslationReviewState(reviewFlashState);
  } else {
    revealFreshTranslationResult(cached);
  }
  syncTranslationModeDensity();
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function revealFreshTranslationResult(cached) {
  const sentenceNode = selectedSentenceNode();
  if (translationOutput) {
    window.clearTimeout(translationRevealTimer);
    translationOutput.classList.remove("has-fresh-result", "has-fresh-cached-result");
    void translationOutput.offsetWidth;
    translationOutput.classList.add(cached ? "has-fresh-cached-result" : "has-fresh-result");
    translationRevealTimer = window.setTimeout(() => {
      translationOutput.classList.remove("has-fresh-result", "has-fresh-cached-result");
      translationRevealTimer = 0;
    }, prefersReducedMotion() ? 0 : 1500);
  }
  if (!sentenceNode) return;
  window.clearTimeout(sentenceRevealTimer);
  sentenceNode.classList.remove("just-studied", "just-loaded-cache");
  void sentenceNode.offsetWidth;
  sentenceNode.classList.add(cached ? "just-loaded-cache" : "just-studied");
  sentenceRevealTimer = window.setTimeout(() => {
    sentenceNode.classList.remove("just-studied", "just-loaded-cache");
    sentenceRevealTimer = 0;
  }, prefersReducedMotion() ? 0 : 1700);
}

function flashSentenceReviewState(node, reviewState) {
  if (!node) return;
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  window.clearTimeout(sentenceReviewFlashTimer);
  node.classList.remove("review-state-changed", "review-state-reviewed", "review-state-rejected", "review-state-generated");
  void node.offsetWidth;
  node.classList.add("review-state-changed", `review-state-${normalizedReviewState}`);
  sentenceReviewFlashTimer = window.setTimeout(() => {
    node.classList.remove("review-state-changed", "review-state-reviewed", "review-state-rejected", "review-state-generated");
    sentenceReviewFlashTimer = 0;
  }, prefersReducedMotion() ? 0 : 1600);
}

function cancelTranslationRequest() {
  if (!activeTranslationController) {
    setTranslationStatus("실행 중인 번역 요청이 없습니다.");
    return;
  }
  const controller = activeTranslationController;
  activeTranslationRequest += 1;
  activeTranslationController = null;
  activeTranslationTargetKey = "";
  controller.abort();
  const sentenceNode = selectedSentenceNode();
  if (sentenceNode) {
    sentenceNode.classList.remove("loading");
  }
  renderTranslationCancelled();
  setTranslationStatus("번역 요청을 취소했습니다.");
}

async function requestSentenceTranslation(regenerate = false) {
  clearActionConfirmations();
  if (!selectedSentence) {
    setTranslationStatus("문장을 먼저 선택하세요.", true);
    return;
  }
  const targetKey = selectedTranslationTargetKey();
  if (!regenerate && activeTranslationController && activeTranslationTargetKey === targetKey) {
    setTranslationStatus("이미 번역 중입니다.", true);
    return;
  }
  if (activeTranslationController) {
    activeTranslationController.abort();
  }
  const requestId = activeTranslationRequest + 1;
  activeTranslationRequest = requestId;
  const controller = new AbortController();
  activeTranslationController = controller;
  activeTranslationTargetKey = targetKey;
  const sentenceNode = document.getElementById(selectedSentence.sentenceId);
  setTranslationStatus(regenerate ? "다시 생성 중" : "번역 중", true);
  renderTranslationPending(regenerate);
  regenerateSentenceButton.disabled = true;
  if (sentenceNode) {
    sentenceNode.classList.add("loading");
  }
  try {
    const response = await fetch("/api/sentence-translation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id || "",
        work_id: researchData.work_id || "",
        variant_id: researchData.variant_id || "",
        segment_id: selectedSentence.segmentId,
        sentence_id: selectedSentence.sentenceId,
        regenerate
      }),
      signal: controller.signal
    });
    const payload = await response.json().catch(() => ({}));
    if (requestId !== activeTranslationRequest) return;
    if (!response.ok || !payload.ok) {
      const message = cleanText(payload.error || "번역기가 꺼져 있습니다.");
      if (translationErrorIsRuntime(message)) {
        setGemmaRuntimeIndicator("offline", "번역기 꺼짐", "번역기를 시작한 뒤 다시 시도하세요.");
      }
      setTranslationStatus(translationErrorDisplayMessage(message), true);
      renderTranslationError(message);
      return;
    }
    if (!payload.cached) {
      setGemmaRuntimeIndicator("ready", "번역기 준비됨", "번역 서비스가 이 요청에 응답했습니다.");
    }
    renderTranslationRecord(payload.record, payload.cached);
    if (!payload.cached) {
      loadTranslationRecordsSummary();
    }
    setTranslationStatus(payload.cached ? "저장된 번역" : "번역 완료");
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeTranslationRequest) {
      const message = cleanText(error && error.message ? error.message : "번역기가 꺼져 있습니다.");
      if (translationErrorIsRuntime(message)) {
        setGemmaRuntimeIndicator("offline", "번역기 꺼짐", "번역기를 시작한 뒤 다시 시도하세요.");
      }
      setTranslationStatus(translationErrorDisplayMessage(message), true);
      renderTranslationError(message);
    }
  } finally {
    if (requestId === activeTranslationRequest) {
      activeTranslationController = null;
      activeTranslationTargetKey = "";
      updateSentenceControls();
    }
    if (sentenceNode) {
      sentenceNode.classList.remove("loading");
    }
  }
}

async function updateTranslationReview(reviewState, triggerButton = null) {
  if (!selectedTranslationRecord || !selectedTranslationRecord.id) {
    setTranslationStatus("번역을 먼저 선택하세요.", true);
    return;
  }
  clearActionConfirmations();
  const actionButton = reviewState === "reviewed" ? markTranslationReviewedButton : rejectTranslationButton;
  setActionButtonBusy(actionButton, true);
  if (triggerButton && triggerButton !== actionButton) {
    setActionButtonBusy(triggerButton, true);
  }
  setTranslationStatus(reviewState === "reviewed" ? "저장 중..." : "업데이트 중...", true);
  try {
    const response = await fetch(`/api/sentence-translations/${encodeURIComponent(selectedTranslationRecord.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id || "",
        review_state: reviewState
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      setTranslationStatus(payload.error || "번역을 저장하지 못했습니다.", true);
      return;
    }
    renderTranslationRecord(payload.record, true, reviewState);
    loadTranslationRecordsSummary();
    loadStudySessionSummary();
    setTranslationStatus(reviewState === "reviewed" ? "저장했습니다." : "제외했습니다.");
    if (reviewState === "reviewed") {
      focusNextSentenceAction();
    }
  } catch (error) {
    const message = error && error.message ? error.message : "번역을 저장하지 못했습니다.";
    setTranslationStatus(message, true);
  } finally {
    setActionButtonBusy(actionButton, false);
    if (triggerButton && triggerButton !== actionButton) {
      setActionButtonBusy(triggerButton, false);
    }
    updateSentenceControls();
  }
}

function translationNoteDraftText(record) {
  if (!record) return "";
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const lines = [];
  if (translation) {
    lines.push("번역", translation);
  }
  if (commentary) {
    if (lines.length) lines.push("");
    lines.push("해설", commentary);
  }
  return lines.join("\n");
}

function focusNoteComposer() {
  const focus = () => {
    if (isMobileStudyLayout() && noteForm && typeof noteForm.scrollIntoView === "function") {
      noteForm.scrollIntoView({
        block: "start",
        inline: "nearest",
        behavior: prefersReducedMotion() ? "auto" : "smooth"
      });
    }
    try {
      noteText.focus({ preventScroll: isMobileStudyLayout() });
    } catch (error) {
      noteText.focus();
    }
    if (noteText.setSelectionRange) {
      const noteEnd = noteText.value.length;
      noteText.setSelectionRange(noteEnd, noteEnd);
    }
  };
  window.requestAnimationFrame(focus);
}

function noteAlreadyIncludesDraft(draftText) {
  const normalize = (value) => String(value || "").replace(/\r\n?/g, "\n").trim();
  const draft = normalize(draftText);
  return Boolean(draft && normalize(noteText.value).includes(draft));
}

function draftNoteFromTranslation() {
  if (!selectedTranslationRecord) return;
  const draftText = translationNoteDraftText(selectedTranslationRecord);
  if (!draftText) return;
  const existingNote = noteText.value.trim();
  const alreadyDrafted = noteAlreadyIncludesDraft(draftText);
  if (!alreadyDrafted) {
    noteText.value = existingNote ? `${existingNote}\n\n---\n\n${draftText}` : draftText;
  }
  const existingTags = noteTags.value.split(",").map((item) => item.trim()).filter(Boolean);
  const mergedTags = Array.from(new Set([...existingTags, "ai-translation"]));
  noteTags.value = mergedTags.join(", ");
  lockedNoteTarget = selectedSentenceTargetSnapshot();
  updateNoteTargetPreview();
  saveNoteDraft();
  setStudyPanel("notes");
  setStudyPanelExpanded(true);
  focusNoteComposer();
  if (alreadyDrafted) {
    noteStatus.textContent = "이미 이 노트에 있습니다.";
    setTranslationStatus("이미 노트에 있습니다.");
    return;
  }
  noteStatus.textContent = existingNote ? "노트 초안에 추가했습니다." : "노트 초안을 만들었습니다.";
  setTranslationStatus(existingNote ? "노트 초안에 추가했습니다." : "노트 초안으로 옮겼습니다.");
}

function translationStudyCardText(record) {
  if (!record) return "";
  const lines = [];
  const source = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  if (source) {
    lines.push("원문", source);
  }
  if (translation) {
    lines.push("번역", translation);
  }
  if (commentary) {
    lines.push("해설", commentary);
  }
  return lines.join("\n");
}

function noteDraftPayload() {
  return {
    note: noteText.value,
    tags: noteTags.value,
    locked_target: lockedNoteTarget ? targetSnapshot(lockedNoteTarget) : null,
    updated_at: new Date().toISOString()
  };
}

function hasNoteDraftValue(payload) {
  return Boolean(cleanText(payload.note || "") || cleanText(payload.tags || ""));
}

function readerSessionStorage() {
  try {
    return window.sessionStorage || null;
  } catch (error) {
    return null;
  }
}

function saveNoteDraft(autoLockTarget = true) {
  const storage = readerSessionStorage();
  if (!storage) return;
  if (autoLockTarget && !lockedNoteTarget && hasNoteDraftValue({ note: noteText.value, tags: noteTags.value })) {
    lockedNoteTarget = targetSnapshot();
    updateNoteTargetPreview();
  }
  const payload = noteDraftPayload();
  try {
    if (hasNoteDraftValue(payload)) {
      storage.setItem(NOTE_DRAFT_STORAGE_KEY, JSON.stringify(payload));
    } else {
      storage.removeItem(NOTE_DRAFT_STORAGE_KEY);
    }
  } catch (error) {
    return;
  }
}

function scheduleNoteDraftSave() {
  if (!lockedNoteTarget && hasNoteDraftValue({ note: noteText.value, tags: noteTags.value })) {
    lockedNoteTarget = targetSnapshot();
    updateNoteTargetPreview();
  }
  window.clearTimeout(noteDraftSaveTimer);
  noteDraftSaveTimer = window.setTimeout(saveNoteDraft, 180);
}

function restoreNoteDraft() {
  const storage = readerSessionStorage();
  if (!storage) return;
  try {
    const rawDraft = storage.getItem(NOTE_DRAFT_STORAGE_KEY);
    if (!rawDraft) return;
    const draft = JSON.parse(rawDraft);
    if (!hasNoteDraftValue(draft)) return;
    if (draft.locked_target) {
      lockedNoteTarget = targetSnapshot(draft.locked_target);
      updateNoteTargetPreview();
    }
    if (!noteText.value) {
      noteText.value = draft.note || "";
    }
    if (!noteTags.value) {
      noteTags.value = draft.tags || "";
    }
    if (hasNoteDraftValue(noteDraftPayload())) {
      noteStatus.textContent = "노트 초안을 복원했습니다.";
    }
  } catch (error) {
    return;
  }
}

function clearNoteDraft() {
  window.clearTimeout(noteDraftSaveTimer);
  const storage = readerSessionStorage();
  if (!storage) return;
  try {
    storage.removeItem(NOTE_DRAFT_STORAGE_KEY);
  } catch (error) {
    return;
  }
}

async function copyStudyCard() {
  if (!selectedTranslationRecord) {
    setTranslationStatus("번역을 먼저 선택하세요.", true);
    return;
  }
  setActionButtonBusy(copyStudyCardButton, true);
  try {
    await copyText(translationStudyCardText(selectedTranslationRecord));
    setTranslationStatus("학습 노트를 복사했습니다.");
  } catch (error) {
    setTranslationStatus("학습 노트를 복사하지 못했습니다.", true);
  } finally {
    setActionButtonBusy(copyStudyCardButton, false);
    updateSentenceControls();
  }
}

function updateCitationPreview() {
  const preview = citationPreviewText();
  citationPreview.textContent = preview;
  citationPreview.title = "복사할 때 원문 URL이 함께 포함됩니다.";
  citationPreview.setAttribute("aria-label", `${preview} 복사할 때 원문 URL이 함께 포함됩니다.`);
}

async function copyText(value) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (error) {
      // Fall through to the legacy copy path when browser permissions are strict.
    }
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-9999px";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.focus();
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) {
    throw new Error("클립보드 복사에 실패했습니다");
  }
}

function noteTimestamp(note) {
  const value = note.updated_at || note.created_at || "";
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

function sortedNotes(notes) {
  const items = Array.isArray(notes) ? [...notes] : [];
  const sortMode = noteSort ? noteSort.value : "recent";
  if (sortMode === "target") {
    return items.sort((a, b) => {
      const labelCompare = cleanText(a.target_label || "").localeCompare(cleanText(b.target_label || ""));
      return labelCompare || noteTimestamp(b) - noteTimestamp(a);
    });
  }
  return items.sort((a, b) => noteTimestamp(b) - noteTimestamp(a));
}

function updateNoteFilterClearState() {
  if (!noteFilterClear || !noteFilter) return;
  noteFilterClear.disabled = !noteFilter.value.trim();
}

function clearNoteFilter() {
  if (!noteFilter) return;
  noteFilter.value = "";
  updateNoteFilterClearState();
  if (noteStatus) {
    noteStatus.textContent = "노트 필터를 지웠습니다.";
  }
  loadNotes();
  noteFilter.focus();
}

function normalizedNoteReviewState(note) {
  return note && note.review_state === "reviewed" ? "reviewed" : "raw";
}

function noteReviewLabel(reviewState) {
  return reviewState === "reviewed" ? "저장됨" : "작성 중";
}

function noteReviewAction(reviewState) {
  return reviewState === "reviewed" ? "mark-raw-note" : "mark-reviewed-note";
}

function noteReviewActionLabel(reviewState) {
  return reviewState === "reviewed" ? "다시 열기" : "저장";
}

function noteTargetHref(note) {
  const url = cleanText(note.url || "");
  if (url.startsWith("/work/") || url.startsWith("/read?") || url.startsWith("/source?")) {
    return url;
  }
  const targetId = cleanText(note.target_id || "");
  if (targetId && targetId !== "work") {
    return `${location.pathname}${location.search}#${encodeURIComponent(targetId)}`;
  }
  return location.pathname + location.search;
}

function renderNotesPending() {
  notesList.setAttribute("aria-busy", "true");
  if (noteListSummary) {
    noteListSummary.textContent = "노트 불러오는 중...";
  }
  notesList.innerHTML = `
    <div class="notes-list-pending" aria-hidden="true">
      <span class="notes-list-skeleton wide"></span>
      <span class="notes-list-skeleton"></span>
      <span class="notes-list-skeleton short"></span>
    </div>`;
}

function noteListSummaryText(items, filter = "") {
  if (!items.length) return "";
  return cleanText(filter) ? `필터 결과 ${items.length.toLocaleString()}개` : "";
}

function renderNotesUnavailable() {
  notesList.setAttribute("aria-busy", "false");
  syncNotesFilterToolsVisibility(0, "");
  if (noteListSummary) {
    noteListSummary.textContent = "";
  }
  notesList.innerHTML = '<div class="notes-empty">노트를 사용할 수 없습니다.</div>';
}

function syncNotesFilterToolsVisibility(itemCount, filter) {
  if (!notesFilterTools) return;
  const showTools = itemCount > 0 || Boolean(cleanText(filter || ""));
  notesFilterTools.hidden = !showTools;
  if (!showTools) {
    notesFilterTools.open = false;
  }
}

function renderNotesList(notes) {
  const items = sortedNotes(notes);
  const filter = noteFilter ? noteFilter.value.trim() : "";
  notesList.setAttribute("aria-busy", "false");
  syncNotesFilterToolsVisibility(items.length, filter);
  if (noteListSummary) {
    noteListSummary.textContent = noteListSummaryText(items, filter);
  }
  if (!items.length) {
    notesList.innerHTML = filter
      ? `<div class="notes-empty">
          <span>이 필터에 맞는 노트가 없습니다.</span>
          <div class="notes-empty-actions">
            <button type="button" data-notes-empty-action="clear-filter">필터 지우기</button>
          </div>
        </div>`
      : '<div class="notes-empty">아직 노트가 없습니다.</div>';
    return;
  }
  notesList.innerHTML = items.map((note) => {
    const tags = (note.tags || []).join(", ");
    const updated = note.updated_at ? ` / 수정 ${cleanText(note.updated_at)}` : "";
    const isRecent = note.id === recentlyChangedNoteId;
    const recentClass = isRecent ? " is-recent" : "";
    const recentAttrs = isRecent ? ' tabindex="-1" aria-label="최근 변경된 노트"' : "";
    const targetHref = noteTargetHref(note);
    const reviewState = normalizedNoteReviewState(note);
    return `<div class="note-item${recentClass}" data-note-id="${escapeHtml(note.id)}" data-note-tags="${escapeHtml(tags)}" data-review-state="${escapeHtml(reviewState)}"${recentAttrs}>
      <div class="note-item-title">
        <strong>${escapeHtml(cleanText(note.target_label))}</strong>
        <span class="review-badge ${escapeHtml(reviewState)}">${escapeHtml(noteReviewLabel(reviewState))}</span>
      </div>
      <div class="note-text">${escapeHtml(cleanText(note.note))}</div>
      <small>${escapeHtml(cleanText(tags))}${escapeHtml(updated)}</small>
      <div class="note-actions">
        <a class="note-target-link" href="${escapeHtml(targetHref)}">원문</a>
        <button type="button" data-action="${escapeHtml(noteReviewAction(reviewState))}" data-note-id="${escapeHtml(note.id)}">${escapeHtml(noteReviewActionLabel(reviewState))}</button>
        <button type="button" data-action="edit-note" data-note-id="${escapeHtml(note.id)}">수정</button>
        <details class="note-danger-actions">
          <summary>삭제</summary>
          <button type="button" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">삭제</button>
        </details>
      </div>
    </div>`;
  }).join("");
}

function revealRecentNote(recentNote) {
  if (!recentNote) return;
  if (typeof recentNote.scrollIntoView === "function") {
    recentNote.scrollIntoView({
      block: isMobileStudyLayout() ? "center" : "nearest",
      inline: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
  if (typeof recentNote.focus === "function") {
    try {
      recentNote.focus({ preventScroll: true });
    } catch (error) {
      recentNote.focus();
    }
  }
}

async function loadNotes() {
  const corpusId = researchData.corpus_id || researchData.author_id || "";
  const workId = researchData.work_id || "";
  const params = new URLSearchParams({ corpus_id: corpusId, work_id: workId });
  const filter = noteFilter ? noteFilter.value.trim() : "";
  if (filter.startsWith("#") && filter.length > 1) {
    params.set("tag", filter.slice(1));
  } else if (filter) {
    params.set("q", filter);
  }
  renderNotesPending();
  try {
    const response = await fetch(`/api/notes?${params}`);
    if (!response.ok) {
      renderNotesUnavailable();
      noteStatus.textContent = "노트를 불러오지 못했습니다.";
      return;
    }
    const payload = await response.json();
    renderNotesList(payload.notes || []);
    if (recentlyChangedNoteId) {
      const recentNote = Array.from(notesList.querySelectorAll(".note-item"))
        .find((item) => item.dataset.noteId === recentlyChangedNoteId);
      if (recentNote) {
        revealRecentNote(recentNote);
      } else if (filter && noteStatus) {
        noteStatus.textContent = "최근 변경한 노트가 현재 필터에 가려져 있습니다. 필터를 지우면 볼 수 있습니다.";
      }
    }
  } catch (error) {
    renderNotesUnavailable();
    noteStatus.textContent = "노트를 불러오지 못했습니다.";
  }
}

async function updateNote(noteId, note, tags) {
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id,
        note,
        tags
      })
    });
    if (!response.ok) return null;
    const payload = await response.json().catch(() => ({}));
    return payload.note || null;
  } catch (error) {
    return null;
  }
}

async function updateNoteReview(noteId, reviewState) {
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id,
        review_state: reviewState
      })
    });
    if (!response.ok) return null;
    const payload = await response.json().catch(() => ({}));
    return payload.note || null;
  } catch (error) {
    return null;
  }
}

async function deleteNote(noteId) {
  const corpusId = encodeURIComponent(researchData.corpus_id || researchData.author_id || "");
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}?corpus_id=${corpusId}`, {
      method: "DELETE"
    });
    return response.ok;
  } catch (error) {
    return false;
  }
}

document.getElementById("copyCitation").addEventListener("click", async () => {
  await copyText(citationText());
  noteStatus.textContent = "인용을 복사했습니다.";
});

document.getElementById("copyUrl").addEventListener("click", async () => {
  await copyText(currentTarget().url);
  noteStatus.textContent = "URL을 복사했습니다.";
});

copySourceBundleButton.addEventListener("click", async () => {
  const bundleUrl = sourceBundleUrl();
  if (!bundleUrl) {
    noteStatus.textContent = "원문 묶음은 섹션, 문단, 절 대상에서 사용할 수 있습니다.";
    return;
  }
  await copyText(bundleUrl);
  noteStatus.textContent = "원문 묶음 URL을 복사했습니다.";
});

regenerateSentenceButton.addEventListener("click", () => handleConfirmedAction("regenerate"));
previousSentenceButton.addEventListener("click", () => navigateSentence(-1));
nextSentenceButton.addEventListener("click", () => navigateSentence(1));
if (nextUnstudiedSentenceButton) {
  nextUnstudiedSentenceButton.addEventListener("click", navigateToNextUnstudiedSentence);
}
if (nextReviewSentenceButton) {
  nextReviewSentenceButton.addEventListener("click", navigateToNextReviewSentence);
}
if (continueStudyButton) {
  continueStudyButton.addEventListener("click", continueStudy);
}
markTranslationReviewedButton.addEventListener("click", () => updateTranslationReview("reviewed"));
rejectTranslationButton.addEventListener("click", () => handleConfirmedAction("reject"));
copyStudyCardButton.addEventListener("click", copyStudyCard);
draftTranslationNoteButton.addEventListener("click", draftNoteFromTranslation);
readingModeButton.addEventListener("click", () => setTranslationMode("reading"));
studyModeButton.addEventListener("click", () => setTranslationMode("study"));
if (gemmaRuntimeCheckButton) {
  gemmaRuntimeCheckButton.addEventListener("click", () => checkGemmaRuntimeStatus(true));
}
lockNoteTargetButton.addEventListener("click", () => {
  if (lockedNoteTarget) {
    unlockNoteTarget();
  } else {
    lockCurrentNoteTarget();
  }
});
if (studyPanelToggle && studyPage) {
  studyPanelToggle.addEventListener("click", () => {
    if (ignoreNextStudyPanelToggleClick) {
      ignoreNextStudyPanelToggleClick = false;
      return;
    }
    const wasExpanded = studyPage.classList.contains("is-expanded");
    setStudyPanelExpanded(!wasExpanded, true);
    if (wasExpanded) {
      returnToSelectedSourceAfterPanelCollapse();
    }
  });
  studyPanelToggle.addEventListener("pointerdown", beginStudyPanelDrag);
  studyPanelToggle.addEventListener("pointermove", updateStudyPanelDrag);
  studyPanelToggle.addEventListener("pointerup", finishStudyPanelDrag);
  studyPanelToggle.addEventListener("pointercancel", cancelStudyPanelDrag);
}

if (studyPanelScrim) {
  studyPanelScrim.addEventListener("click", () => {
    setStudyPanelExpanded(false, true);
  });
}

if (sentenceContext) {
  sentenceContext.addEventListener("click", (event) => {
    const item = event.target.closest("[data-sentence-id]");
    if (!item) return;
    const sentenceId = item.dataset.sentenceId || "";
    const node = document.getElementById(sentenceId);
    if (!node || !node.classList.contains("reader-sentence")) return;
    const wasSelected = selectedSentence && selectedSentence.sentenceId === sentenceId;
    selectSentence(node);
    scrollSentenceIntoView(node);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    keepSentenceAboveStudyPanel(node);
    if (!wasSelected || !selectedTranslationRecord) {
      requestSentenceTranslation(false);
    }
  });
}

if (translationTarget) {
  translationTarget.addEventListener("click", (event) => {
    const jumpButton = event.target.closest("[data-selected-source-jump]");
    if (!jumpButton || !selectedSentence) return;
    focusSelectedSourceSentence();
  });
}

if (readingPosition) {
  readingPosition.addEventListener("click", (event) => {
    const button = event.target.closest("[data-reading-cue-select]");
    if (!button) return;
    studyReadingCueSentence();
  });
}

translationOutput.addEventListener("click", (event) => {
  const quickAction = event.target.closest("[data-translation-quick-action]");
  if (quickAction) {
    const action = quickAction.dataset.translationQuickAction || "";
    if (action === "next-sentence") {
      navigateSentence(1);
      return;
    }
    if (action === "mark-reviewed") {
      updateTranslationReview("reviewed", quickAction);
      return;
    }
    if (action === "draft-note") {
      draftNoteFromTranslation();
      return;
    }
    if (action === "continue") {
      continueStudy();
      return;
    }
  }
  const sourceJump = event.target.closest("[data-selected-source-jump]");
  if (sourceJump) {
    focusSelectedSourceSentence();
    return;
  }
  const cancel = event.target.closest("[data-translation-cancel]");
  if (cancel) {
    cancelTranslationRequest();
    return;
  }
  const retry = event.target.closest("[data-translation-retry]");
  if (retry) {
    requestSentenceTranslation(retry.dataset.translationRetry === "regenerate");
    return;
  }
  const copyRuntime = event.target.closest("[data-translation-copy-runtime]");
  if (copyRuntime) {
    copyText(GEMMA_RUNTIME_COMMAND)
      .then(() => setTranslationStatus("명령을 복사했습니다."))
      .catch(() => setTranslationStatus("명령을 복사하지 못했습니다.", true));
    return;
  }
  const checkRuntime = event.target.closest("[data-translation-check-runtime]");
  if (checkRuntime) {
    checkGemmaRuntimeStatus(true);
    return;
  }
  const jump = event.target.closest("[data-translation-jump]");
  if (jump) {
    scrollTranslationSectionIntoView(jump.dataset.translationJump || "");
    return;
  }
  const sessionTarget = event.target.closest("[data-session-preview-target]");
  if (sessionTarget) {
    openSessionPreviewTarget(sessionTarget.dataset.sessionPreviewTarget || "");
    return;
  }
  const sessionToggle = event.target.closest("[data-session-preview-toggle]");
  if (sessionToggle) {
    toggleSessionPreviewGroup(sessionToggle);
    return;
  }
  const sessionCopy = event.target.closest("[data-session-preview-copy]");
  if (sessionCopy) {
    copyStudySessionMarkdown(sessionCopy);
  }
});

studyTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setStudyPanel(tab.dataset.studyTab || "translation");
    setStudyPanelExpanded(true);
  });
});

if (studyTabsContainer) {
  studyTabsContainer.addEventListener("keydown", (event) => {
    const tabs = visibleStudyTabs();
    const currentIndex = tabs.indexOf(event.target);
    if (currentIndex < 0) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      activateStudyTabByIndex(currentIndex + 1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      activateStudyTabByIndex(currentIndex - 1);
    }
    if (event.key === "Home") {
      event.preventDefault();
      activateStudyTabByIndex(0);
    }
    if (event.key === "End") {
      event.preventDefault();
      activateStudyTabByIndex(tabs.length - 1);
    }
  });
}

document.querySelector(".reading-body").addEventListener("click", (event) => {
  const sentence = event.target.closest(".reader-sentence");
  if (sentence) {
    const sentenceId = sentence.dataset.sentenceId || sentence.id || "";
    const wasSelected = selectedSentence && selectedSentence.sentenceId === sentenceId;
    selectSentence(sentence);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    keepSentenceAboveStudyPanel(sentence);
    if (!wasSelected || !selectedTranslationRecord) {
      requestSentenceTranslation(false);
    }
  }
});

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const isTyping = target && (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
  if (isTyping || event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === "Escape" && hasPendingActionConfirmation()) {
    event.preventDefault();
    clearActionConfirmations();
    setTranslationStatus("동작을 취소했습니다.");
    return;
  }
  if (event.key === "Escape" && isMobileStudyLayout() && studyPage?.classList.contains("is-expanded")) {
    event.preventDefault();
    setStudyPanelExpanded(false, true);
    return;
  }
  if (event.key.toLowerCase() === "s") {
    event.preventDefault();
    focusSelectedSourceSentence();
    return;
  }
  if (
    (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "j" || event.key === "k") &&
    target?.closest?.(".study-page")
  ) {
    return;
  }
  if (event.key === "ArrowDown" || event.key === "j") {
    event.preventDefault();
    navigateSentence(1);
  }
  if (event.key === "ArrowUp" || event.key === "k") {
    event.preventDefault();
    navigateSentence(-1);
  }
});

noteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setActionButtonBusy(noteSaveButton, true);
  const target = noteTargetForSave();
  const note = document.getElementById("noteText").value.trim();
  const tags = document.getElementById("noteTags").value.split(",").map((item) => item.trim()).filter(Boolean);
  const selection = window.getSelection ? window.getSelection().toString().trim() : "";
  noteStatus.textContent = "노트 저장 중...";
  try {
    const response = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id,
        work_id: researchData.work_id,
        variant_id: researchData.variant_id || "",
        target_id: target.id,
        target_type: target.type,
        target_label: target.label,
        quote: selection,
        note,
        tags
      })
    });
    if (response.ok) {
      const payload = await response.json().catch(() => ({}));
      recentlyChangedNoteId = payload.note?.id || "";
      clearNoteDraft();
      noteForm.reset();
      unlockNoteTarget(false);
      noteStatus.textContent = "노트를 저장하고 표시했습니다.";
      await loadNotes();
      await loadStudySessionSummary();
    } else {
      noteStatus.textContent = "노트를 저장하지 못했습니다.";
    }
  } catch (error) {
    noteStatus.textContent = "노트를 저장하지 못했습니다.";
  } finally {
    setActionButtonBusy(noteSaveButton, false);
  }
});

if (noteFilter) {
  noteFilter.addEventListener("input", () => {
    window.clearTimeout(noteFilter._timer);
    updateNoteFilterClearState();
    noteFilter._timer = window.setTimeout(loadNotes, 180);
  });
  updateNoteFilterClearState();
}

if (noteFilterClear && noteFilter) {
  noteFilterClear.addEventListener("click", () => {
    clearNoteFilter();
  });
}

if (noteSort) {
  noteSort.addEventListener("change", loadNotes);
}

[noteText, noteTags].forEach((field) => {
  if (!field) return;
  field.addEventListener("input", scheduleNoteDraftSave);
});

notesList.addEventListener("click", async (event) => {
  const emptyAction = event.target.closest("button[data-notes-empty-action]");
  if (emptyAction) {
    if (emptyAction.dataset.notesEmptyAction === "clear-filter") {
      clearNoteFilter();
    }
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const noteId = button.dataset.noteId;
  const item = button.closest(".note-item");
  const currentText = item ? cleanText(item.querySelector(".note-text")?.textContent || "") : "";
  const currentTags = item ? cleanText(item.dataset.noteTags || "") : "";
  if (button.dataset.action === "mark-reviewed-note" || button.dataset.action === "mark-raw-note") {
    const nextState = button.dataset.action === "mark-reviewed-note" ? "reviewed" : "raw";
    setActionButtonBusy(button, true);
    const updatedNote = await updateNoteReview(noteId, nextState);
    noteStatus.textContent = updatedNote
      ? (nextState === "reviewed" ? "노트를 저장했습니다." : "노트를 다시 열었습니다.")
      : "노트를 업데이트하지 못했습니다.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
    return;
  }
  if (button.dataset.action === "edit-note") {
    const nextNote = window.prompt("노트 수정", currentText);
    if (nextNote === null) return;
    const nextTags = window.prompt("Tags", currentTags) || "";
    setActionButtonBusy(button, true);
    const updatedNote = await updateNote(noteId, nextNote.trim(), nextTags.split(",").map((value) => value.trim()).filter(Boolean));
    noteStatus.textContent = updatedNote ? "노트를 수정하고 표시했습니다." : "노트를 업데이트하지 못했습니다.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
  }
  if (button.dataset.action === "delete-note") {
    if (!window.confirm("이 노트를 삭제할까요?")) return;
    setActionButtonBusy(button, true);
    const ok = await deleteNote(noteId);
    noteStatus.textContent = ok ? "노트를 삭제했습니다." : "노트를 삭제하지 못했습니다.";
    if (ok) {
      if (recentlyChangedNoteId === noteId) {
        recentlyChangedNoteId = "";
      }
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
  }
});

window.addEventListener("hashchange", () => {
  selectSentenceFromHash();
  syncTargetDependentViews();
  updateSentenceControls();
});

function initializeStudyCompanion() {
  rememberRecentWork();
  setTranslationMode("reading");
  restoreNoteDraft();
  setStudyPanelExpanded(storedStudyPanelExpanded());
  setStudyPanel("translation");
  renderTranslationEmptyState();
  const exportParams = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    review_state: "reviewed",
    format: "markdown"
  });
  exportReviewedTranslations.href = `/api/sentence-translations/export?${exportParams}`;
  const exportAllParams = new URLSearchParams(exportParams);
  exportAllParams.set("review_state", "all");
  if (exportAllTranslations) {
    exportAllTranslations.href = `/api/sentence-translations/export?${exportAllParams}`;
  }
  if (exportStudySession) {
    exportStudySession.href = studySessionExportUrl("markdown");
    exportStudySession.title = "이 문서의 학습 기록 다운로드";
  }
  syncConceptsPanelAvailability();
  selectSentenceFromHash();
  if (selectedSentence) {
    requestSentenceTranslation(false);
  }
  updateSentenceControls();
  syncTargetDependentViews();
  updateStudyPanelScrim();
  checkGemmaRuntimeStatus(false);
  loadTranslationRecordsSummary();
  loadStudySessionSummary();
}

function syncConceptsPanelAvailability() {
  const conceptsPanel = document.querySelector('[data-study-panel="concepts"]');
  const conceptsTab = document.querySelector('[data-study-tab="concepts"]');
  if (!conceptsPanel || !conceptsTab) return;
  const hasConcepts = Boolean(conceptsPanel.textContent.trim());
  if (hasConcepts) return;
  conceptsTab.hidden = true;
  conceptsTab.classList.remove("active");
  conceptsTab.setAttribute("aria-selected", "false");
  conceptsTab.tabIndex = -1;
  conceptsPanel.hidden = true;
  conceptsPanel.classList.remove("active");
}

initializeStudyCompanion();
initializeReadingPositionTracker();
loadNotes();
