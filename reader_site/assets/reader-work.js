const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const noteFilterClear = document.getElementById("noteFilterClear");
const noteSort = document.getElementById("noteSort");
const noteListSummary = document.getElementById("noteListSummary");
const noteTargetPreview = document.getElementById("noteTargetPreview");
const lockNoteTargetButton = document.getElementById("lockNoteTarget");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const readingPosition = document.getElementById("readingPosition");
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
const COMMENTARY_COLLAPSE_LENGTH = 420;
const STUDY_PANEL_STORAGE_KEY = "philo.reader.studyPanelExpanded";
const STUDY_PANEL_DRAG_THRESHOLD = 36;
const ACTION_CONFIRM_MS = 4500;
const GEMMA_RUNTIME_COMMAND = ".\\run_reader_with_gemma.ps1";
const TRANSLATION_STATE_LABELS = {
  generated: "Needs review",
  reviewed: "Reviewed translation",
  rejected: "Rejected translation"
};
const TRANSLATION_REVIEW_CHIP_LABELS = {
  generated: "Needs review",
  reviewed: "Reviewed",
  rejected: "Rejected"
};
const TRANSLATION_REVIEW_CHIP_HINTS = {
  generated: "Translation awaiting review",
  reviewed: "Reviewed translation",
  rejected: "Rejected translation"
};
const TRANSLATION_STATE_SHORT = {
  generated: "AI",
  reviewed: "OK",
  rejected: "NO"
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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStudyPanel(name, focusTab = false) {
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
  if (!studyTabs.length) return;
  const nextIndex = (index + studyTabs.length) % studyTabs.length;
  const nextTab = studyTabs[nextIndex];
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
  if (!selectedSentence) return "Select sentence";
  const index = sentenceIndex(selectedSentence.sentenceId);
  return index >= 0 ? `Sentence ${index + 1} of ${sentenceNodes.length}` : selectedSentence.sentenceId;
}

function studyPanelToggleSummary() {
  if (!selectedSentence) return "Select sentence";
  const position = selectedSentencePositionLabel();
  if (translationCard && translationCard.classList.contains("is-loading")) {
    return `${position} / working`;
  }
  if (translationOutput && translationOutput.querySelector(".translation-error")) {
    return `${position} / retry needed`;
  }
  if (selectedTranslationRecord) {
    return `${position} / ready`;
  }
  return position;
}

function updateStudyPanelToggleLabel() {
  if (!studyPage || !studyPanelToggle) return;
  const expanded = studyPage.classList.contains("is-expanded");
  const action = expanded ? "Close" : "Study";
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

function setCommentaryExpanded(commentary, expanded) {
  if (!commentary) return;
  const toggle = commentary.querySelector(".commentary-toggle");
  if (!toggle) return;
  commentary.classList.toggle("is-expanded", expanded);
  commentary.classList.toggle("is-collapsed", !expanded);
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  toggle.setAttribute("aria-label", expanded ? "Show less commentary" : "Read full commentary");
  toggle.textContent = expanded ? "Show less" : "Read full commentary";
}

function syncTranslationModeDensity() {
  if (!translationOutput) return;
  const commentary = translationOutput.querySelector(".translation-commentary");
  if (!commentary) return;
  setCommentaryExpanded(commentary, translationMode === "study");
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
  setGemmaRuntimeIndicator("checking", "Checking local AI", "Local AI status");
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
      const title = model ? `Local AI ready: ${model}` : "Local AI ready";
      setGemmaRuntimeIndicator("ready", "AI ready", title);
      if (announce) {
        setTranslationStatus("AI ready.");
      }
      return;
    }
    const error = cleanText(gemma.error || "Start .\\run_reader_with_gemma.ps1, then check again.");
    setGemmaRuntimeIndicator("offline", "AI offline", error);
    if (announce) {
      setTranslationStatus("AI offline.", true);
    }
  } catch (error) {
    if (error && error.name === "AbortError" && gemmaRuntimeCheckController !== controller) {
      return;
    }
    const label = error && error.name === "AbortError" ? "AI check timed out" : "AI unavailable";
    setGemmaRuntimeIndicator("unavailable", label, "Check whether the reader server and local AI are running.");
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

function translationRecordSummaryChip(label, value, reviewState = "") {
  return `<span class="translation-record-chip"${reviewState ? ` data-review-state="${escapeHtml(reviewState)}"` : ""}>
    <span>${escapeHtml(label)}</span>
    <strong>${Number(value || 0).toLocaleString()}</strong>
  </span>`;
}

function setTranslationRecordsSummary(text, state = "empty", counts = null) {
  if (!translationRecordsSummary) return;
  translationRecordsSummary.dataset.recordsState = state;
  if (!counts) {
    translationRecordsSummary.textContent = text;
    translationRecordsSummary.removeAttribute("aria-label");
    return;
  }
  const total = Number(counts.total || 0);
  const sentenceCount = Number(counts.sentenceCount || 0);
  const generated = Number(counts.generated || 0);
  const reviewed = Number(counts.reviewed || 0);
  const rejected = Number(counts.rejected || 0);
  const reviewHint = total
    ? (generated ? `${generated} need review.` : "No review needed.")
    : "No translations yet.";
  translationRecordsSummary.setAttribute(
    "aria-label",
    `${text}. ${total} translation records, ${sentenceCount} sentences, ${generated} generated, ${reviewed} reviewed, ${rejected} rejected. ${reviewHint}`
  );
  translationRecordsSummary.innerHTML = `
    <span class="translation-records-summary-main">${escapeHtml(text)}</span>
    <span class="translation-records-summary-hint">${escapeHtml(reviewHint)}</span>
    <span class="translation-record-counts" aria-hidden="true">
      ${translationRecordSummaryChip("Total", total)}
      ${translationRecordSummaryChip("Sentences", sentenceCount)}
      ${translationRecordSummaryChip("Review", generated, "generated")}
      ${translationRecordSummaryChip("Reviewed", reviewed, "reviewed")}
      ${translationRecordSummaryChip("Rejected", rejected, "rejected")}
    </span>`;
}

function updateTranslationExportLinks(total, reviewed) {
  if (exportReviewedTranslations) {
    exportReviewedTranslations.dataset.exportCount = String(reviewed);
    exportReviewedTranslations.classList.toggle("is-empty", reviewed === 0);
    exportReviewedTranslations.title = reviewed
      ? `Download ${reviewed} reviewed translations`
      : "No reviewed translations yet";
  }
  if (exportAllTranslations) {
    exportAllTranslations.dataset.exportCount = String(total);
    exportAllTranslations.classList.toggle("is-empty", total === 0);
    exportAllTranslations.title = total
      ? `Download ${total} translation records`
      : "No translation records yet";
  }
}

function setStudyProgress(text, state = "loading") {
  if (studyProgressText) {
    studyProgressText.textContent = text;
  }
  if (studyProgress) {
    studyProgress.dataset.progressState = state;
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
    setStudyProgress("Progress", "loading");
    if (continueStudyButton) {
      continueStudyButton.textContent = "Continue study";
      continueStudyButton.disabled = true;
      continueStudyButton.title = "Translation states are loading";
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
  const reviewText = pendingReview ? ` · ${pendingReview} review` : "";
  setStudyProgress(`${studied}/${total} translated · ${remaining} left${reviewText}`, state);
  if (continueStudyButton) {
    const wantsReview = remaining === 0 && pendingReview > 0;
    const wantsPreview = remaining === 0 && pendingReview === 0 && stateCounts.reviewed > 0;
    const nextIndex = wantsReview ? nextGeneratedSentenceIndex() : continueStudySentenceIndex();
    const nextLabel = nextIndex >= 0 ? sentencePositionText(sentenceNodeId(sentenceNodes[nextIndex])) : "";
    if (wantsPreview) {
      continueStudyButton.textContent = "Preview session";
      continueStudyButton.dataset.studyAction = "preview-session";
      continueStudyButton.disabled = false;
      continueStudyButton.title = "Preview notes and translations";
      continueStudyButton.setAttribute("aria-label", "Preview study bundle");
    } else {
      continueStudyButton.textContent = wantsReview ? "Review next" : "Continue study";
      continueStudyButton.dataset.studyAction = wantsReview ? "review-generated" : "continue";
      continueStudyButton.disabled = nextIndex < 0;
      continueStudyButton.title = nextIndex >= 0
        ? `${wantsReview ? "Review" : "Continue at"} ${nextLabel}`
        : (wantsReview ? "No translations need review" : "All sentences have translations");
      continueStudyButton.setAttribute("aria-label", nextIndex >= 0
        ? `${wantsReview ? "Review translation at" : "Continue study at"} ${nextLabel}`
        : (wantsReview ? "No translations need review" : "Study progress complete"));
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

function setStudySessionSummary(text, state = "empty") {
  if (!studySessionSummary) return;
  studySessionSummary.textContent = text;
  studySessionSummary.dataset.sessionState = state;
}

function updateStudySessionExportLink(noteCount, translationCount) {
  if (!exportStudySession) return;
  const total = noteCount + translationCount;
  exportStudySession.dataset.exportCount = String(total);
  exportStudySession.classList.toggle("is-empty", total === 0);
  exportStudySession.title = total
    ? `Download study bundle: ${noteCount} notes and ${translationCount} translations`
    : "No notes or translations for this bundle yet";
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
      throw new Error(payload.error || "Study session unavailable");
    }
    const noteCount = Number(payload.note_count || 0);
    const translationCount = Number(payload.translation_count || 0);
    setStudySessionSummary(
      `Study bundle: ${noteCount} notes / ${translationCount} translations`,
      noteCount + translationCount ? "has-content" : "empty"
    );
    updateStudySessionExportLink(noteCount, translationCount);
  } catch (error) {
    setStudySessionSummary("Study bundle unavailable.", "unavailable");
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
      throw new Error(payload.error || "Translation records unavailable");
    }
    const counts = payload.review_state_counts || {};
    const total = Number(payload.count || 0);
    const generated = Number(counts.generated || 0);
    const reviewed = Number(counts.reviewed || 0);
    const rejected = Number(counts.rejected || 0);
    const sentenceCount = Number(payload.sentence_state_count || 0);
    applySentenceTranslationStates(payload.sentence_states || []);
    setTranslationRecordsSummary(
      "Translations",
      generated ? "needs-review" : (total ? "has-records" : "empty"),
      { total, sentenceCount, generated, reviewed, rejected }
    );
    updateTranslationExportLinks(total, reviewed);
  } catch (error) {
    clearSentenceTranslationStates(false);
    setTranslationRecordsSummary("Translations unavailable.", "unavailable");
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
      defaultText: "Regenerate",
      defaultTitle: "Regenerate translation",
      defaultAria: "Regenerate translation",
      confirmText: "Confirm regenerate",
      confirmTitle: "Click again to replace this translation",
      confirmAria: "Confirm regenerate translation",
      status: "Click Confirm regenerate to replace this translation.",
      blockMessage: selectedSentence ? "" : "Select a sentence first.",
      run: () => requestSentenceTranslation(true)
    };
  }
  if (action === "reject") {
    return {
      button: rejectTranslationButton,
      defaultText: "Reject",
      defaultTitle: "Reject translation",
      defaultAria: "Reject translation",
      confirmText: "Confirm reject",
      confirmTitle: "Click again to mark this translation rejected",
      confirmAria: "Confirm reject translation",
      status: "Click Confirm reject to exclude this cached translation.",
      blockMessage: selectedTranslationRecord && selectedTranslationRecord.id ? "" : "No translation record selected.",
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
  actionConfirmationTimer = window.setTimeout(() => clearActionConfirmations("Pending action expired."), ACTION_CONFIRM_MS);
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
  return index >= 0 ? `Sentence ${index + 1} of ${sentenceNodes.length}` : sentenceId;
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
    status.dataset.sourceState = sourceState;
    status.textContent = sourceVisible ? "Source in view" : "Source off screen";
  }
  const jumpButton = translationTarget.querySelector("[data-selected-source-jump]");
  if (jumpButton) {
    jumpButton.classList.toggle("is-source-away", !sourceVisible);
    jumpButton.textContent = sourceVisible ? "Center" : "Show source";
    jumpButton.setAttribute("aria-keyshortcuts", "S");
    jumpButton.setAttribute(
      "title",
      sourceVisible ? "Center selected source sentence" : "Show selected source sentence"
    );
    jumpButton.setAttribute(
      "aria-label",
      `${sourceVisible ? "Center" : "Show"} selected source sentence ${selectedSentence.sentenceId}`
    );
  }
}

function renderTranslationTarget() {
  if (!translationTarget) return;
  if (!selectedSentence) {
    translationTarget.textContent = "Select a sentence in the source page.";
    translationTarget.classList.remove("is-source-visible", "is-source-away");
    delete translationTarget.dataset.sourceState;
    return;
  }
  const position = selectedSentencePositionLabel();
  const sourceText = cleanText(selectedSentence.text || "");
  translationTarget.innerHTML = `
    <div class="translation-target-main">
      <span class="translation-target-label">Selected source</span>
      <strong class="translation-target-id">${escapeHtml(position)}</strong>
      <span class="translation-target-status" data-selected-source-status></span>
      <p class="translation-target-excerpt" title="${escapeHtml(sourceText)}">${escapeHtml(sourceText)}</p>
    </div>
    <button type="button" data-selected-source-jump aria-keyshortcuts="S">Show source</button>`;
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
    setTranslationStatus("Select a sentence first.", true);
    return false;
  }
  const node = selectedSentenceNode();
  if (!node) {
    setTranslationStatus("Selected source is not available on this page.", true);
    return false;
  }
  scrollSentenceIntoView(node);
  updateReadingPosition(node);
  updateTranslationTargetViewState();
  flashSourceFocus(node);
  setTranslationStatus("Selected source centered.");
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
    ? '<span class="reading-position-current">Selected</span>'
    : '<button type="button" data-reading-cue-select>Study this</button>';
  readingPosition.innerHTML = `
    <div class="reading-position-main">
      <span>Reading near</span>
      <strong>${escapeHtml(label)}</strong>
      ${action}
    </div>
    <p class="reading-position-excerpt" title="${escapeHtml(excerpt)}">${escapeHtml(excerpt)}</p>`;
  readingPosition.setAttribute("aria-label", `Current reading position: ${label}. ${excerpt}`);
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
    return;
  }
  const index = sentenceIndex(selectedSentence.sentenceId);
  if (index < 0) {
    sentenceContext.hidden = true;
    sentenceContext.innerHTML = "";
    return;
  }
  const rows = [
    ["Previous", index - 1],
    ["Current", index],
    ["Next", index + 1]
  ].filter((entry) => entry[1] >= 0 && entry[1] < sentenceNodes.length);
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
      : (translationSentenceStatesLoaded ? "No unstudied sentence after current position" : "Translation states are loading");
    nextUnstudiedSentenceButton.title = nextUnstudiedIndex >= 0
      ? `Jump to ${nextLabel}`
      : nextLabel;
    nextUnstudiedSentenceButton.setAttribute("aria-label", nextUnstudiedIndex >= 0
      ? `Next unstudied sentence, ${nextLabel}`
      : nextLabel);
  }
  if (nextReviewSentenceButton) {
    nextReviewSentenceButton.disabled = nextReviewIndex < 0;
    const nextReviewLabel = nextReviewIndex >= 0
      ? sentencePositionText(sentenceNodeId(sentenceNodes[nextReviewIndex]))
      : (translationSentenceStatesLoaded ? "No translations need review" : "Translation states are loading");
    nextReviewSentenceButton.title = nextReviewIndex >= 0
      ? `Review ${nextReviewLabel}`
      : nextReviewLabel;
    nextReviewSentenceButton.setAttribute("aria-label", nextReviewIndex >= 0
      ? `Next translation to review, ${nextReviewLabel}`
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
    ? (isSentence ? sentencePositionText(id) : cleanText(node.dataset.label || node.textContent))
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
    label: cleanText(target.label || researchData.title || "Current work"),
    type: target.type || "work",
    url: target.url || location.href
  };
}

function selectedSentenceTargetSnapshot() {
  if (!selectedSentence) return targetSnapshot();
  const baseUrl = location.origin + location.pathname + location.search;
  return targetSnapshot({
    id: selectedSentence.sentenceId,
    label: `${selectedSentencePositionLabel()} / ${selectedSentence.sentenceId}`,
    type: "sentence",
    url: `${baseUrl}#${encodeURIComponent(selectedSentence.sentenceId)}`
  });
}

function noteTargetForSave() {
  return lockedNoteTarget || targetSnapshot();
}

function noteTargetTypeLabel(type) {
  if (type === "work") return "Work";
  if (type === "paragraph") return "Paragraph";
  if (type === "verse") return "Verse";
  if (type === "section") return "Section";
  if (type === "sentence") return "Sentence";
  return cleanText(type || "Target");
}

function noteTargetDisplayText(target) {
  const safeTarget = targetSnapshot(target);
  return `${noteTargetTypeLabel(safeTarget.type)} / ${safeTarget.label || safeTarget.id}`;
}

function updateNoteTargetPreview() {
  if (!noteTargetPreview || !lockNoteTargetButton) return;
  const target = noteTargetForSave();
  const locked = Boolean(lockedNoteTarget);
  noteTargetPreview.classList.toggle("is-locked", locked);
  noteTargetPreview.innerHTML = `
    <span>${locked ? "Locked note target" : "Note target follows selection"}</span>
    <strong>${escapeHtml(noteTargetDisplayText(target))}</strong>`;
  noteTargetPreview.setAttribute("aria-label", `${locked ? "Locked note target" : "Note target"}: ${noteTargetDisplayText(target)}`);
  lockNoteTargetButton.textContent = locked ? "Unlock target" : "Lock target";
  lockNoteTargetButton.setAttribute("aria-pressed", locked ? "true" : "false");
}

function lockCurrentNoteTarget(announce = true) {
  lockedNoteTarget = targetSnapshot();
  updateNoteTargetPreview();
  saveNoteDraft();
  if (announce) {
    noteStatus.textContent = "Note target locked.";
  }
}

function unlockNoteTarget(announce = true) {
  lockedNoteTarget = null;
  updateNoteTargetPreview();
  saveNoteDraft(false);
  if (announce) {
    noteStatus.textContent = "Note target follows selection.";
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
        ? "No unstudied sentence after current position."
        : "Translation states are still loading.",
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
        ? "No translations need review."
        : "Translation states are still loading.",
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
        ? (action === "review-generated" ? "No translations need review." : "All sentences have translations.")
        : "Translation states are still loading.",
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
      <h3>Cautions</h3>
      ${cautions}
    </section>`;
}

function renderCommentary(commentary) {
  const text = cleanText(commentary || "");
  const shouldCollapse = text.length > COMMENTARY_COLLAPSE_LENGTH;
  return `
    <section class="translation-section translation-commentary${shouldCollapse ? " is-collapsed" : ""}" data-translation-section="commentary">
      <h3>Commentary</h3>
      <p>${escapeHtml(text)}</p>
      ${shouldCollapse ? '<button type="button" class="commentary-toggle" aria-expanded="false" aria-label="Read full commentary">Read full commentary</button>' : ""}
    </section>`;
}

function renderTranslationEmptyState() {
  if (!translationOutput || selectedSentence) return;
  translationOutput.hidden = false;
  translationOutput.setAttribute("aria-busy", "false");
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  translationOutput.innerHTML = `
    <div class="translation-result translation-empty-state" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>Translation</h3>
        <p class="translation-primary translation-empty-copy">Click a sentence to read translation and commentary.</p>
      </section>
    </div>`;
}

function translationJumpNav(record) {
  const hasCommentary = Boolean(cleanText(record.commentary || record.interpretation || ""));
  const buttons = [
    ["translation", "Translation"],
    hasCommentary ? ["commentary", "Commentary"] : null
  ].filter(Boolean);
  return `<div class="translation-jump-nav" aria-label="Translation result sections">
    <button type="button" data-selected-source-jump aria-keyshortcuts="S">Source</button>
    ${buttons.map(([section, label]) => `<button type="button" data-translation-jump="${escapeHtml(section)}">${escapeHtml(label)}</button>`).join("")}
  </div>`;
}

function translationResultToolbar(record, cached, reviewState) {
  const targetLabel = selectedSentence
    ? selectedSentencePositionLabel()
    : cleanText(record.sentence_id || "Selected sentence");
  const sourceText = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  const stateLabel = TRANSLATION_REVIEW_CHIP_LABELS[normalizedReviewState];
  const stateHint = TRANSLATION_REVIEW_CHIP_HINTS[normalizedReviewState] || stateLabel;
  const sourceLabel = cached ? "Cached result" : "New result";
  const reviewLabel = `${stateHint}; ${sourceLabel}`;
  return `<details class="translation-result-toolbar translation-result-details translation-extra">
    <summary>
      <span>Source details</span>
    </summary>
    <div class="translation-result-detail-body">
      <div class="translation-result-meta">
        <span class="translation-result-kicker">Selected sentence</span>
        <strong class="translation-result-target">${escapeHtml(targetLabel)}</strong>
        <span class="translation-review-state" data-review-state="${escapeHtml(normalizedReviewState)}" title="${escapeHtml(reviewLabel)}" aria-label="${escapeHtml(reviewLabel)}">
          <span>${escapeHtml(stateLabel)}</span>
          <small>${escapeHtml(sourceLabel)}</small>
        </span>
      </div>
      ${sourceText ? `<section class="translation-section translation-source-detail">
        <h3>Original source</h3>
        <p>${escapeHtml(sourceText)}</p>
      </section>` : ""}
      ${translationJumpNav(record)}
    </div>
  </details>`;
}

function translationQuickActions(reviewState) {
  const normalizedReviewState = normalizedTranslationReviewState(reviewState);
  const reviewAction = normalizedReviewState === "reviewed"
    ? '<span class="translation-quick-state" data-review-state="reviewed">Reviewed</span>'
    : '<button type="button" data-translation-quick-action="mark-reviewed">Mark reviewed</button>';
  return `<div class="translation-quick-actions" aria-label="Study actions">
      ${reviewAction}
      <button type="button" data-translation-quick-action="draft-note">Draft note</button>
      <button type="button" data-translation-quick-action="continue">Next</button>
    </div>`;
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
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  setTranslationBusy(true);
  resetTranslationOutputScroll();
  const actionLabel = regenerate ? "Refreshing study card" : "Preparing translation";
  const commentaryLabel = regenerate ? "Updating commentary for this sentence." : "Commentary will appear with the translation.";
  const position = selectedSentencePositionLabel();
  translationOutput.innerHTML = `
    <div class="translation-result translation-pending-result" role="status" aria-live="polite" aria-label="${escapeHtml(`${actionLabel}: ${position}`)}">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>Translation</h3>
        <p class="translation-primary translation-pending-copy">${escapeHtml(actionLabel)}...</p>
        <p class="translation-pending-context">${escapeHtml(position)}</p>
        <div class="translation-skeleton translation-study-skeleton" aria-hidden="true">
          <div class="translation-skeleton-block primary">
            <span class="translation-skeleton-line wide"></span>
            <span class="translation-skeleton-line"></span>
          </div>
        </div>
      </section>
      <section class="translation-section translation-commentary translation-pending-commentary" data-translation-section="commentary">
        <h3>Commentary</h3>
        <p class="translation-unavailable-copy">${escapeHtml(commentaryLabel)}</p>
      </section>
      <div class="translation-loading-actions">
        <button type="button" data-translation-cancel>Cancel request</button>
      </div>
    </div>`;
  updateSentenceControls();
}

function translationErrorIsRuntime(message) {
  const text = cleanText(message).toLowerCase();
  if (!text) return true;
  return (
    text.includes("gemma runtime") ||
    text.includes("runtime is not") ||
    text.includes("failed to fetch") ||
    text.includes("networkerror") ||
    text.includes("load failed")
  );
}

function translationErrorDisplayMessage(message) {
  return translationErrorIsRuntime(message)
    ? "Local AI is not running. Start it, then try this sentence again."
    : cleanText(message || "Translation unavailable.");
}

function runtimeRecoveryMarkup(message) {
  if (!translationErrorIsRuntime(message)) return "";
  return `
      <p class="translation-runtime-hint">Start local AI, then retry this sentence.</p>
      <div class="translation-runtime-command-row">
        <code class="translation-runtime-command">${escapeHtml(GEMMA_RUNTIME_COMMAND)}</code>
        <button type="button" data-translation-copy-runtime>Copy command</button>
      </div>`;
}

function renderTranslationError(message) {
  selectedTranslationRecord = null;
  const retryMode = pendingTranslationRegenerate ? "regenerate" : "translate";
  const retryLabel = pendingTranslationRegenerate ? "Regenerate again" : "Try again";
  const cleanMessage = cleanText(message || "Local AI is not running.");
  const isRuntimeError = translationErrorIsRuntime(cleanMessage);
  const displayMessage = translationErrorDisplayMessage(cleanMessage);
  pendingTranslationRegenerate = false;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-result translation-error" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>Translation</h3>
        <p class="translation-primary translation-unavailable-copy">Translation unavailable.</p>
      </section>
      <section class="translation-section translation-commentary" data-translation-section="commentary">
        <h3>Commentary</h3>
        <p class="translation-unavailable-copy">${escapeHtml(displayMessage)}</p>
      </section>
      <div class="translation-recovery-panel">
        ${runtimeRecoveryMarkup(cleanMessage)}
        <div class="translation-error-actions">
          <button type="button" data-translation-retry="${escapeHtml(retryMode)}">${escapeHtml(retryLabel)}</button>
          ${isRuntimeError ? '<button type="button" data-translation-check-runtime>Check runtime</button>' : ""}
        </div>
      </div>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function renderTranslationCancelled(message = "Translation request cancelled.") {
  selectedTranslationRecord = null;
  setTranslationBusy(false);
  setTranslationReviewVisualState("");
  translationOutput.hidden = false;
  resetTranslationOutputScroll();
  const position = selectedSentence ? selectedSentencePositionLabel() : "selected sentence";
  const retryMode = pendingTranslationRegenerate ? "regenerate" : "translate";
  const retryLabel = pendingTranslationRegenerate ? "Regenerate again" : "Try again";
  pendingTranslationRegenerate = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  translationOutput.innerHTML = `
    <div class="translation-result translation-cancelled" role="note">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>Translation</h3>
        <p class="translation-primary translation-unavailable-copy">Translation cancelled.</p>
      </section>
      <section class="translation-section translation-commentary" data-translation-section="commentary">
        <h3>Commentary</h3>
        <p class="translation-unavailable-copy">${escapeHtml(cleanText(message))} No translation was saved for ${escapeHtml(position)}.</p>
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
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", false);
  translationOutput.classList.toggle("study-mode", true);
  setTranslationBusy(true);
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-loading" role="status" aria-live="polite" aria-label="Loading study session preview">
      <span class="loading-spinner" aria-hidden="true"></span>
      <span class="translation-loading-copy">
        <strong>Loading study session preview</strong>
        <span>Notes and translations</span>
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
    return `<p class="session-preview-empty">No ${escapeHtml(kind)} in this bundle.</p>`;
  }
  const hasMore = items.length > 3;
  return `<div class="session-preview-group${hasMore ? " is-collapsed" : ""}" data-session-preview-group>
    <ol class="session-preview-list">
    ${items.map((item, index) => {
      const label = cleanText(item.target_label || item.sentence_id || item.target_id || item.work_id || "Study item");
      const body = cleanText(kind === "notes"
        ? (item.note || item.quote || "")
        : (item.translation || item.commentary || item.source_text_excerpt || ""));
      const targetId = sessionPreviewTargetId(item);
      return `<li${index >= 3 ? ' class="session-preview-extra"' : ""}>
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(body || "Reviewed study item")}</span>
        </div>
        ${targetId ? `<button type="button" data-session-preview-target="${escapeHtml(targetId)}">Open</button>` : ""}
      </li>`;
    }).join("")}
    </ol>
    ${hasMore ? `<button type="button" class="session-preview-toggle" data-session-preview-toggle aria-expanded="false">Show all ${items.length}</button>` : ""}
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
    setTranslationStatus("Could not find that source target in this page.", true);
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
  setTranslationStatus("Opened source target.");
}

function toggleSessionPreviewGroup(button) {
  const group = button.closest("[data-session-preview-group]");
  if (!group) return;
  const expanded = group.classList.toggle("is-expanded");
  group.classList.toggle("is-collapsed", !expanded);
  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  button.textContent = expanded ? "Show less" : `Show all ${group.querySelectorAll("li").length}`;
}

async function copyStudySessionMarkdown(button) {
  setActionButtonBusy(button, true);
  setTranslationStatus("Copying study bundle...", true);
  try {
    const response = await fetch(studySessionExportUrl("markdown"));
    if (!response.ok) {
      throw new Error("Could not load study bundle.");
    }
    const markdown = await response.text();
    await copyText(markdown);
    setTranslationStatus("Study bundle copied.");
  } catch (error) {
    const message = cleanText(error && error.message ? error.message : "Could not copy study bundle.");
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
        <span>Study session</span>
        <strong>${escapeHtml(researchData.title || researchData.work_id || "Current work")}</strong>
        <div class="study-session-preview-actions">
          <button type="button" data-session-preview-copy>Copy bundle</button>
          <a href="${escapeHtml(exportUrl)}">Open bundle</a>
        </div>
      </div>
      <div class="study-session-preview-counts" aria-label="Study session counts">
        <span>${noteCount} notes</span>
        <span>${translationCount} translations</span>
      </div>
      <section>
        <h3>Notes</h3>
        ${sessionPreviewItems(payload.notes, "notes")}
      </section>
      <section>
        <h3>Translations</h3>
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
  translationOutput.hidden = false;
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-error" role="note">
      <h3>Study session preview unavailable</h3>
      <p>${escapeHtml(cleanText(message || "Could not load the reviewed study session."))}</p>
      <div class="translation-error-actions">
        <a href="${escapeHtml(studySessionExportUrl("markdown"))}">Open bundle</a>
      </div>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

async function previewStudySession() {
  clearActionConfirmations();
  renderStudySessionPreviewPending();
  setTranslationStatus("Loading study session preview...", true);
  setActionButtonBusy(continueStudyButton, true);
  try {
    const response = await fetch(studySessionExportUrl("json"));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Study session preview unavailable");
    }
    renderStudySessionPreview(payload);
    setTranslationStatus("Study session preview ready.");
  } catch (error) {
    const message = cleanText(error && error.message ? error.message : "Study session preview unavailable.");
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
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-result">
      <section class="translation-section translation-section-primary" data-translation-section="translation">
        <h3>Translation</h3>
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
    setTranslationStatus("No translation request is running.");
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
  setTranslationStatus("Translation request cancelled.");
}

async function requestSentenceTranslation(regenerate = false) {
  clearActionConfirmations();
  if (!selectedSentence) {
    setTranslationStatus("Select a sentence first.", true);
    return;
  }
  const targetKey = selectedTranslationTargetKey();
  if (!regenerate && activeTranslationController && activeTranslationTargetKey === targetKey) {
    setTranslationStatus("Translation is already running...", true);
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
  setTranslationStatus(regenerate ? "Regenerating..." : "Translating...", true);
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
      const message = cleanText(payload.error || "Gemma runtime is not running.");
      if (message.includes("Gemma runtime")) {
        setGemmaRuntimeIndicator("offline", "AI offline", "Start .\\run_reader_with_gemma.ps1, then retry.");
      }
      setTranslationStatus(translationErrorDisplayMessage(message), true);
      renderTranslationError(message);
      return;
    }
    if (!payload.cached) {
      setGemmaRuntimeIndicator("ready", "AI ready", "Local AI responded to this request.");
    }
    renderTranslationRecord(payload.record, payload.cached);
    if (!payload.cached) {
      loadTranslationRecordsSummary();
    }
    setTranslationStatus(payload.cached ? "Loaded translation." : "Translation saved locally.");
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeTranslationRequest) {
      const message = cleanText(error && error.message ? error.message : "Gemma runtime is not running.");
      if (message.includes("Gemma runtime")) {
        setGemmaRuntimeIndicator("offline", "AI offline", "Start .\\run_reader_with_gemma.ps1, then retry.");
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

async function updateTranslationReview(reviewState) {
  if (!selectedTranslationRecord || !selectedTranslationRecord.id) {
    setTranslationStatus("No translation record selected.", true);
    return;
  }
  clearActionConfirmations();
  const actionButton = reviewState === "reviewed" ? markTranslationReviewedButton : rejectTranslationButton;
  setActionButtonBusy(actionButton, true);
  setTranslationStatus(reviewState === "reviewed" ? "Marking reviewed..." : "Updating review state...", true);
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
      setTranslationStatus(payload.error || "Could not update translation review.", true);
      return;
    }
    renderTranslationRecord(payload.record, true, reviewState);
    loadTranslationRecordsSummary();
    loadStudySessionSummary();
    setTranslationStatus(reviewState === "reviewed" ? "Translation marked reviewed." : "Translation rejected.");
  } catch (error) {
    const message = error && error.message ? error.message : "Could not update translation review.";
    setTranslationStatus(message, true);
  } finally {
    setActionButtonBusy(actionButton, false);
    updateSentenceControls();
  }
}

function translationNoteDraftText(record) {
  if (!record) return "";
  const source = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const lines = [
    "Translation & commentary",
    `Target: ${selectedSentencePositionLabel()} / ${selectedSentence?.sentenceId || ""}`
  ];
  if (source) {
    lines.push("", "Original source", source);
  }
  if (translation) {
    lines.push("", "Korean translation", translation);
  }
  if (commentary) {
    lines.push("", "Commentary", commentary);
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
    noteStatus.textContent = "This translation is already in the note. Review and save.";
    setTranslationStatus("Translation is already in Notes.");
    return;
  }
  noteStatus.textContent = existingNote ? "Translation appended to this note. Review and save." : "Translation drafted into this note. Review and save.";
  setTranslationStatus(existingNote ? "Translation appended to Notes." : "Translation drafted into Notes.");
}

function translationStudyCardText(record) {
  if (!record) return "";
  const lines = [];
  const source = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  if (source) {
    lines.push("Original", source);
  }
  if (translation) {
    lines.push("Translation", translation);
  }
  if (commentary) {
    lines.push("Commentary", commentary);
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
      noteStatus.textContent = "Note draft restored.";
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
    setTranslationStatus("No translation record selected.", true);
    return;
  }
  setActionButtonBusy(copyStudyCardButton, true);
  try {
    await copyText(translationStudyCardText(selectedTranslationRecord));
    setTranslationStatus("Study card copied.");
  } catch (error) {
    setTranslationStatus("Could not copy study card.", true);
  } finally {
    setActionButtonBusy(copyStudyCardButton, false);
    updateSentenceControls();
  }
}

function updateCitationPreview() {
  citationPreview.textContent = citationText();
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
    throw new Error("Clipboard copy failed");
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
    noteStatus.textContent = "Note filter cleared.";
  }
  loadNotes();
  noteFilter.focus();
}

function normalizedNoteReviewState(note) {
  return note && note.review_state === "reviewed" ? "reviewed" : "raw";
}

function noteReviewLabel(reviewState) {
  return reviewState === "reviewed" ? "Reviewed" : "Draft";
}

function noteReviewAction(reviewState) {
  return reviewState === "reviewed" ? "mark-raw-note" : "mark-reviewed-note";
}

function noteReviewActionLabel(reviewState) {
  return reviewState === "reviewed" ? "Move to draft" : "Mark reviewed";
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
    noteListSummary.textContent = "Loading notes...";
  }
  notesList.innerHTML = `
    <div class="notes-list-pending" aria-hidden="true">
      <span class="notes-list-skeleton wide"></span>
      <span class="notes-list-skeleton"></span>
      <span class="notes-list-skeleton short"></span>
    </div>`;
}

function noteListSummaryText(items) {
  if (!items.length) return "";
  const sortLabel = noteSort && noteSort.value === "target" ? "target order" : "recent first";
  return `${items.length} notes / ${sortLabel}`;
}

function renderNotesUnavailable() {
  notesList.setAttribute("aria-busy", "false");
  if (noteListSummary) {
    noteListSummary.textContent = "";
  }
  notesList.innerHTML = '<div class="notes-empty">Notes unavailable.</div>';
}

function renderNotesList(notes) {
  const items = sortedNotes(notes);
  const filter = noteFilter ? noteFilter.value.trim() : "";
  notesList.setAttribute("aria-busy", "false");
  if (noteListSummary) {
    noteListSummary.textContent = noteListSummaryText(items);
  }
  if (!items.length) {
    notesList.innerHTML = filter
      ? `<div class="notes-empty">
          <span>No notes match this filter.</span>
          <div class="notes-empty-actions">
            <button type="button" data-notes-empty-action="clear-filter">Clear filter</button>
          </div>
        </div>`
      : '<div class="notes-empty">No notes yet.</div>';
    return;
  }
  notesList.innerHTML = items.map((note) => {
    const tags = (note.tags || []).join(", ");
    const updated = note.updated_at ? ` / edited ${cleanText(note.updated_at)}` : "";
    const isRecent = note.id === recentlyChangedNoteId;
    const recentClass = isRecent ? " is-recent" : "";
    const recentAttrs = isRecent ? ' tabindex="-1" aria-label="Recently changed note"' : "";
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
        <a class="note-target-link" href="${escapeHtml(targetHref)}">Open target</a>
        <button type="button" data-action="${escapeHtml(noteReviewAction(reviewState))}" data-note-id="${escapeHtml(note.id)}">${escapeHtml(noteReviewActionLabel(reviewState))}</button>
        <button type="button" data-action="edit-note" data-note-id="${escapeHtml(note.id)}">Edit</button>
        <button type="button" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">Delete</button>
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
      noteStatus.textContent = "Could not load notes.";
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
        noteStatus.textContent = "Recently changed note is hidden by the current filter. Use Clear filter to show it.";
      }
    }
  } catch (error) {
    renderNotesUnavailable();
    noteStatus.textContent = "Could not load notes.";
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
  noteStatus.textContent = "Citation copied.";
});

document.getElementById("copyUrl").addEventListener("click", async () => {
  await copyText(currentTarget().url);
  noteStatus.textContent = "URL copied.";
});

copySourceBundleButton.addEventListener("click", async () => {
  const bundleUrl = sourceBundleUrl();
  if (!bundleUrl) {
    noteStatus.textContent = "Source bundle requires a section, paragraph, or verse target.";
    return;
  }
  await copyText(bundleUrl);
  noteStatus.textContent = "Source bundle URL copied.";
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
    setStudyPanelExpanded(!studyPage.classList.contains("is-expanded"), true);
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
    if (action === "mark-reviewed") {
      updateTranslationReview("reviewed");
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
      .then(() => setTranslationStatus("Start command copied."))
      .catch(() => setTranslationStatus("Could not copy start command.", true));
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
    return;
  }
  const toggle = event.target.closest(".commentary-toggle");
  if (!toggle) return;
  const commentary = toggle.closest(".translation-commentary");
  if (!commentary) return;
  setCommentaryExpanded(commentary, !commentary.classList.contains("is-expanded"));
});

studyTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setStudyPanel(tab.dataset.studyTab || "translation");
    setStudyPanelExpanded(true);
  });
});

if (studyTabsContainer) {
  studyTabsContainer.addEventListener("keydown", (event) => {
    const currentIndex = studyTabs.indexOf(event.target);
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
      activateStudyTabByIndex(studyTabs.length - 1);
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
    setTranslationStatus("Pending action cancelled.");
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
  noteStatus.textContent = "Saving note...";
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
      noteStatus.textContent = "Note saved and highlighted.";
      await loadNotes();
      await loadStudySessionSummary();
    } else {
      noteStatus.textContent = "Could not save note.";
    }
  } catch (error) {
    noteStatus.textContent = "Could not save note.";
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
      ? (nextState === "reviewed" ? "Note marked reviewed." : "Note moved to drafts.")
      : "Could not update note.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
    return;
  }
  if (button.dataset.action === "edit-note") {
    const nextNote = window.prompt("Edit note", currentText);
    if (nextNote === null) return;
    const nextTags = window.prompt("Tags", currentTags) || "";
    setActionButtonBusy(button, true);
    const updatedNote = await updateNote(noteId, nextNote.trim(), nextTags.split(",").map((value) => value.trim()).filter(Boolean));
    noteStatus.textContent = updatedNote ? "Note updated and highlighted." : "Could not update note.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
  }
  if (button.dataset.action === "delete-note") {
    if (!window.confirm("Delete this note?")) return;
    setActionButtonBusy(button, true);
    const ok = await deleteNote(noteId);
    noteStatus.textContent = ok ? "Note deleted." : "Could not delete note.";
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
    exportStudySession.title = "Export notes and translations for this work";
  }
  const conceptsPanel = document.querySelector('[data-study-panel="concepts"]');
  if (conceptsPanel && !conceptsPanel.textContent.trim()) {
    conceptsPanel.innerHTML = '<section class="research-card"><h2>Concepts</h2><p class="source-notes">No concepts yet.</p></section>';
  }
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

initializeStudyCompanion();
initializeReadingPositionTracker();
loadNotes();
