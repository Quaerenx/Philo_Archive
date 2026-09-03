// Reader translation runtime, progress, and action state.
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
  gemmaRuntimeState = state;
  if (!gemmaRuntimeStatus || !gemmaRuntimeStatusText) return;
  gemmaRuntimeStatus.dataset.runtimeState = state;
  gemmaRuntimeStatusText.textContent = text;
  gemmaRuntimeStatus.title = title || text;
}

function clearGemmaRuntimePoll() {
  window.clearTimeout(gemmaRuntimePollTimer);
  gemmaRuntimePollTimer = 0;
}

function scheduleGemmaRuntimeCheck() {
  clearGemmaRuntimePoll();
  gemmaRuntimePollTimer = window.setTimeout(() => {
    gemmaRuntimePollTimer = 0;
    checkGemmaRuntimeStatus(false);
  }, GEMMA_RUNTIME_POLL_MS);
}

async function checkGemmaRuntimeStatus(announce = false) {
  if (!gemmaRuntimeStatus) return;
  const previousState = gemmaRuntimeState;
  clearGemmaRuntimePoll();
  if (gemmaRuntimeCheckController) {
    gemmaRuntimeCheckController.abort();
  }
  const controller = new AbortController();
  gemmaRuntimeCheckController = controller;
  const timeout = window.setTimeout(() => controller.abort(), 2500);
  setGemmaRuntimeIndicator("checking", "번역기 확인 중", "번역기 상태");
  setActionButtonBusy(gemmaRuntimeCheckButton, true);
  try {
    const response = await fetch("/api/health/gemma", { signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error("Runtime status unavailable");
    }
    const gemma = payload.gemma || {};
    if (gemma.reachable) {
      clearGemmaRuntimePoll();
      const model = Array.isArray(gemma.models) ? cleanText(gemma.models[0] || "") : "";
      const title = model ? `번역기 준비됨: ${model}` : "번역기 준비됨";
      setGemmaRuntimeIndicator("ready", "번역기 준비됨", title);
      if (announce || previousState === "starting") {
        setTranslationStatus("번역기 준비됨.");
      }
      return;
    }
    const runtimeState = cleanText(gemma.state || "unavailable");
    if (runtimeState === "starting") {
      setGemmaRuntimeIndicator("starting", "번역기 시작 중", "모델을 불러오는 중입니다. 읽기와 검색은 바로 사용할 수 있습니다.");
      scheduleGemmaRuntimeCheck();
      if (announce) {
        setTranslationStatus("번역기를 시작하고 있습니다. 준비 상태를 자동으로 확인합니다.", true);
      }
      return;
    }
    clearGemmaRuntimePoll();
    if (runtimeState === "failed") {
      setGemmaRuntimeIndicator("failed", "번역기 시작 실패", "런처 경고와 data/runtime.local 로그를 확인하세요.");
      if (announce) {
        setTranslationStatus("번역기를 시작하지 못했습니다. 읽기와 검색은 계속 사용할 수 있습니다.", true);
      }
      return;
    }
    const error = cleanText(gemma.error || "번역기를 켜면 이어서 번역할 수 있습니다.");
    setGemmaRuntimeIndicator("offline", "번역 준비 필요", error);
    if (announce) {
      setTranslationStatus("번역기를 켜면 이어서 번역할 수 있습니다.", true);
    }
  } catch (error) {
    if (error && error.name === "AbortError" && gemmaRuntimeCheckController !== controller) {
      return;
    }
    if (previousState === "starting") {
      setGemmaRuntimeIndicator("starting", "번역기 시작 중", "상태 확인이 지연되어 다시 확인합니다.");
      scheduleGemmaRuntimeCheck();
      if (announce) {
        setTranslationStatus("번역기 준비 상태를 다시 확인합니다.", true);
      }
      return;
    }
    const label = error && error.name === "AbortError" ? "번역기 확인 지연" : "번역 상태 확인 필요";
    setGemmaRuntimeIndicator("unavailable", label, "리더와 번역기가 실행 중인지 확인하세요.");
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
  translationRecordsSummary.hidden = state === "empty";
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
  const reviewHint = generated ? "검토 필요" : "";
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
  const total = totalSentenceCount();
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
    const canSearchVirtual = Boolean(
      virtualDocument && (wantsReview ? pendingReview > 0 : remaining > 0)
    );
    if (wantsPreview) {
      continueStudyButton.textContent = "기록 보기";
      continueStudyButton.dataset.studyAction = "preview-session";
      continueStudyButton.disabled = false;
      continueStudyButton.title = "노트와 번역 기록 보기";
      continueStudyButton.setAttribute("aria-label", "학습 기록 보기");
    } else {
      continueStudyButton.textContent = wantsReview ? "검토 계속" : "이어 읽기";
      continueStudyButton.dataset.studyAction = wantsReview ? "review-generated" : "continue";
      continueStudyButton.disabled = nextIndex < 0 && !canSearchVirtual;
      continueStudyButton.title = nextIndex >= 0
        ? `${wantsReview ? "검토" : "이어 읽기"} ${nextLabel}`
        : (canSearchVirtual ? "다음 문서 청크에서 이어 읽기" : "")
          || (wantsReview ? "검토할 번역이 없습니다" : "모든 문장이 번역되었습니다");
      continueStudyButton.setAttribute("aria-label", nextIndex >= 0
        ? `${nextLabel} ${wantsReview ? "번역 검토" : "부터 이어 읽기"}`
        : (canSearchVirtual ? "다음 문서 청크에서 이어 읽기" : "")
          || (wantsReview ? "검토할 번역이 없습니다" : "학습 진행 완료"));
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
  const reviewState = normalizedTranslationReviewState(item.review_state);
  const label = TRANSLATION_STATE_LABELS[reviewState];
  const state = {
    reviewState,
    label,
    recordId: cleanText(item.record_id || item.id || ""),
    updatedAt: cleanText(item.updated_at || item.reviewed_at || item.generated_at || "")
  };
  translationSentenceStates.set(sentenceId, state);
  const node = sentenceNodeById.get(sentenceId) || document.getElementById(sentenceId);
  if (node && node.classList.contains("reader-sentence")) {
    applySentenceTranslationVisualState(node, state, flash);
  }
  return true;
}

function applySentenceTranslationVisualState(node, state, flash = false) {
  const reviewState = normalizedTranslationReviewState(state.reviewState);
  const label = TRANSLATION_STATE_LABELS[reviewState];
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
  studySessionSummary.hidden = state === "empty";
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
      ? `저장한 학습 기록: 노트 ${noteCount.toLocaleString()}개, 번역 ${translationCount.toLocaleString()}개.`
      : "아직 내보낼 저장 항목이 없습니다.";
    setStudySessionSummary(
      total ? "기록 준비됨" : "내보낼 항목 없음",
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
