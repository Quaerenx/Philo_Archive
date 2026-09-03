// Reader translation rendering, requests, and review actions.
function renderList(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<ul>${values.map((value) => `<li>${escapeHtml(cleanText(value))}</li>`).join("")}</ul>`;
}

function optionalCautions(record) {
  const cautions = renderList(record.cautions);
  if (!cautions) return "";
  return `<details class="translation-section translation-cautions translation-extra" data-translation-section="cautions">
      <summary>주의</summary>
      ${cautions}
    </details>`;
}

function renderCommentary(commentary) {
  const text = cleanText(commentary || "");
  return `
    <section class="translation-section translation-commentary" data-translation-section="commentary">
      <h3>해설</h3>
      <p>${escapeHtml(text)}</p>
    </section>`;
}

function renderTranslationQuality(record) {
  const qualityState = cleanText(record.quality_state || "");
  if (!qualityState || !TRANSLATION_QUALITY_LABELS[qualityState]) return "";
  const revisionCount = Number(record.revision_count || 0);
  const revisionLabel = revisionCount > 0 ? ` · 자동 수정 ${revisionCount}회` : "";
  const label = `${TRANSLATION_QUALITY_LABELS[qualityState]}${revisionLabel}`;
  return `<p class="translation-quality-summary" data-quality-state="${escapeHtml(qualityState)}">${escapeHtml(label)}</p>`;
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
  const nextSentenceDisabled = selectedIndex < 0 || selectedIndex >= totalSentenceCount() - 1
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
  if (!translationErrorIsRuntime(message)) {
    return cleanText(message || "번역을 사용할 수 없습니다.");
  }
  if (gemmaRuntimeState === "starting") {
    return "번역기를 시작하고 있습니다. 준비되면 번역 다시 시도를 눌러주세요.";
  }
  return "번역기를 켜면 이 문장을 이어서 번역할 수 있습니다.";
}

function reflectTranslationRuntimeFailure() {
  if (gemmaRuntimeState === "starting") {
    scheduleGemmaRuntimeCheck();
    return;
  }
  if (gemmaRuntimeState === "failed") return;
  setGemmaRuntimeIndicator("offline", "번역 준비 필요", "번역기를 켜면 이어서 번역할 수 있습니다.");
}

function runtimeRecoveryMarkup(message) {
  if (!translationErrorIsRuntime(message)) return "";
  return `
      <details class="translation-runtime-help">
        <summary>번역기 시작</summary>
        <div class="translation-runtime-details">
          <p class="translation-runtime-note">아래 명령을 PowerShell에서 실행하세요.</p>
          <button type="button" data-translation-copy-runtime>명령 복사</button>
          <code class="translation-runtime-command">${escapeHtml(GEMMA_RUNTIME_COMMAND)}</code>
        </div>
      </details>`;
}

function renderTranslationError(message) {
  selectedTranslationRecord = null;
  const retryMode = pendingTranslationRegenerate ? "regenerate" : "translate";
  const retryLabel = pendingTranslationRegenerate ? "다시 생성" : "번역 다시 시도";
  const cleanMessage = cleanText(message || "번역 준비가 필요합니다.");
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
        <p class="translation-primary translation-unavailable-copy">번역 준비가 필요합니다.</p>
      </section>
      <section class="translation-section translation-commentary" data-translation-section="commentary">
        <h3>해설</h3>
        <p class="translation-unavailable-copy">${escapeHtml(displayMessage)}</p>
      </section>
      <div class="translation-recovery-panel">
        <div class="translation-error-actions">
          <button type="button" data-translation-retry="${escapeHtml(retryMode)}">${escapeHtml(retryLabel)}</button>
          ${isRuntimeError ? '<button type="button" data-translation-check-runtime>번역기 확인</button>' : ""}
        </div>
        ${runtimeRecoveryMarkup(cleanMessage)}
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
        : (item.human_translation || item.translation || item.commentary || item.source_text_excerpt || ""));
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

async function openSessionPreviewTarget(targetId) {
  const id = cleanText(targetId);
  let node = id ? document.getElementById(id) : null;
  if (!node && virtualDocument) {
    try {
      node = await virtualWork.ensureTarget(id);
    } catch (error) {
      node = null;
    }
  }
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
  const modelTranslation = cleanText(record.translation || "");
  const humanTranslation = cleanText(record.human_translation || "");
  const displayedTranslation = humanTranslation || modelTranslation;
  const modelOriginal = humanTranslation && modelTranslation && humanTranslation !== modelTranslation
    ? `<details class="translation-model-original"><summary>모델 원본</summary><p>${escapeHtml(modelTranslation)}</p></details>`
    : "";
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
        <h3>${humanTranslation ? "확정 번역" : "번역"}</h3>
        <p class="translation-primary">${escapeHtml(displayedTranslation)}</p>
        ${modelOriginal}
        ${renderTranslationQuality(record)}
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
      const message = cleanText(payload.error || "번역 준비가 필요합니다.");
      if (translationErrorIsRuntime(message)) {
        reflectTranslationRuntimeFailure();
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
      const message = cleanText(error && error.message ? error.message : "번역 준비가 필요합니다.");
      if (translationErrorIsRuntime(message)) {
        reflectTranslationRuntimeFailure();
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
