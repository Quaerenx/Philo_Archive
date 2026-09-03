// Reader sentence selection, position, and navigation.
function sentenceIndex(sentenceId) {
  const index = sentenceIndexById.get(sentenceId);
  return Number.isInteger(index) ? index : -1;
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
  const currentPosition = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) + 1 : 0;
  for (let localIndex = 0; localIndex < sentenceNodes.length; localIndex += 1) {
    const node = sentenceNodes[localIndex];
    if (sentencePosition(node) > currentPosition && !sentenceHasTranslationState(node)) {
      return localIndex;
    }
  }
  return -1;
}

function firstUnstudiedSentenceIndex() {
  if (!translationSentenceStatesLoaded || !sentenceNodes.length) return -1;
  for (let localIndex = 0; localIndex < sentenceNodes.length; localIndex += 1) {
    if (!sentenceHasTranslationState(sentenceNodes[localIndex])) return localIndex;
  }
  return -1;
}

function continueStudySentenceIndex() {
  const nextIndex = nextUnstudiedSentenceIndex();
  return nextIndex >= 0 ? nextIndex : firstUnstudiedSentenceIndex();
}

function nextGeneratedSentenceIndex() {
  if (!translationSentenceStatesLoaded || !sentenceNodes.length) return -1;
  const currentPosition = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) + 1 : 0;
  for (let localIndex = 0; localIndex < sentenceNodes.length; localIndex += 1) {
    const node = sentenceNodes[localIndex];
    if (sentencePosition(node) > currentPosition && sentenceTranslationState(node) === "generated") {
      return localIndex;
    }
  }
  for (let localIndex = 0; localIndex < sentenceNodes.length; localIndex += 1) {
    if (sentenceTranslationState(sentenceNodes[localIndex]) === "generated") return localIndex;
  }
  return -1;
}

function sentencePositionText(sentenceId) {
  const index = sentenceIndex(sentenceId);
  return index >= 0 ? `문장 ${index + 1} / ${totalSentenceCount()}` : sentenceId;
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
  let candidates = visibleSentenceNodes.size ? Array.from(visibleSentenceNodes) : sentenceNodes;
  if (virtualDocument) {
    const targetElement = document.elementFromPoint(
      Math.max(1, Math.floor(window.innerWidth * 0.35)),
      Math.max(1, Math.floor(readingCueTargetLine()))
    );
    const targetChunk = targetElement?.closest?.(".reader-chunk.is-loaded");
    candidates = targetChunk
      ? Array.from(targetChunk.querySelectorAll(".reader-sentence"))
      : sentenceNodes.filter((node) => {
        const rect = node.closest(".reader-chunk")?.getBoundingClientRect();
        return rect && rect.bottom >= 0 && rect.top <= window.innerHeight;
      });
  }
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
  if (!virtualDocument && "IntersectionObserver" in window) {
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
  ].filter((entry) => entry[1] >= 0 && entry[1] < totalSentenceCount())
    .map(([label, rowIndex]) => [label, sentenceNodeByPosition.get(rowIndex + 1)])
    .filter((entry) => Boolean(entry[1]));
  if (sentenceContextTools) {
    sentenceContextTools.hidden = false;
  }
  sentenceContext.hidden = false;
  sentenceContext.innerHTML = rows.map(([label, node]) => {
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
  nextSentenceButton.disabled = !hasSelection || index === totalSentenceCount() - 1;
  if (nextUnstudiedSentenceButton) {
    const canSearchVirtualUnstudied = Boolean(
      virtualDocument
      && translationSentenceStatesLoaded
      && translationSentenceStates.size < totalSentenceCount()
    );
    nextUnstudiedSentenceButton.disabled = nextUnstudiedIndex < 0 && !canSearchVirtualUnstudied;
    const nextLabel = nextUnstudiedIndex >= 0
      ? sentencePositionText(sentenceNodeId(sentenceNodes[nextUnstudiedIndex]))
      : (canSearchVirtualUnstudied
        ? "다음 문서 청크의 미번역 문장"
        : (translationSentenceStatesLoaded ? "현재 위치 뒤에 미번역 문장이 없습니다" : "번역 상태를 불러오는 중입니다"));
    nextUnstudiedSentenceButton.title = nextUnstudiedIndex >= 0
      ? `${nextLabel}로 이동`
      : nextLabel;
    nextUnstudiedSentenceButton.setAttribute("aria-label", nextUnstudiedIndex >= 0
      ? `다음 미번역 문장, ${nextLabel}`
      : nextLabel);
  }
  if (nextReviewSentenceButton) {
    const canSearchVirtualReview = Boolean(
      virtualDocument
      && translationSentenceStatesLoaded
      && translationStateCountsFromSentences().generated > 0
    );
    nextReviewSentenceButton.disabled = nextReviewIndex < 0 && !canSearchVirtualReview;
    const nextReviewLabel = nextReviewIndex >= 0
      ? sentencePositionText(sentenceNodeId(sentenceNodes[nextReviewIndex]))
      : (canSearchVirtualReview
        ? "다음 문서 청크의 검토할 번역"
        : (translationSentenceStatesLoaded ? "검토할 번역이 없습니다" : "번역 상태를 불러오는 중입니다"));
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
  const hasHumanTranslation = Boolean(hasRecord && cleanText(selectedTranslationRecord.human_translation || ""));
  markTranslationReviewedButton.disabled = !hasRecord || selectedTranslationRecord.review_state === "reviewed";
  rejectTranslationButton.disabled = !hasRecord || hasHumanTranslation || selectedTranslationRecord.review_state === "rejected";
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
    text: cleanText(node.textContent),
    position: sentencePosition(node),
    chunkIndex: virtualWork.chunkForNode(node)
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
  if (virtualDocument) {
    const chunkIndex = virtualWork.chunkForNode(node);
    if (chunkIndex >= 0) {
      virtualWork.setActiveChunkIndex(chunkIndex);
      virtualWork.warmChunks(chunkIndex);
      virtualWork.queueCleanup();
    }
  }
  if (updateHash) {
    history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(sentence.sentenceId)}`);
  }
  rememberRecentWork();
  syncTargetDependentViews();
}

async function selectSentenceFromHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!id) return;
  let node = document.getElementById(id);
  if (!node && virtualDocument) {
    try {
      node = await virtualWork.ensureTarget(id);
    } catch (error) {
      setTranslationStatus("요청한 원문 위치를 불러오지 못했습니다.", true);
      return;
    }
  }
  if (node && node.classList.contains("reader-sentence")) {
    selectSentence(node, false);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    scrollSentenceIntoView(node);
    keepSentenceAboveStudyPanel(node);
    return;
  }
  if (node && typeof node.scrollIntoView === "function") {
    node.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: virtualDocument || prefersReducedMotion() ? "auto" : "smooth"
    });
  }
}

function prefersReducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function sentenceScrollBlock() {
  return window.matchMedia && window.matchMedia("(max-width: 1040px)").matches ? "start" : "center";
}

function isMobileStudyLayout() {
  return Boolean(window.matchMedia && window.matchMedia("(max-width: 1040px)").matches);
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
    behavior: virtualDocument || prefersReducedMotion() ? "auto" : "smooth"
  });
  keepSentenceAboveStudyPanel(node);
}

async function navigateSentence(delta) {
  if (!sentenceNodes.length && !virtualDocument) return;
  const currentIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const total = totalSentenceCount();
  const initialIndex = delta < 0 ? total - 1 : 0;
  const nextIndex = currentIndex < 0
    ? initialIndex
    : Math.min(total - 1, Math.max(0, currentIndex + delta));
  if (nextIndex === currentIndex) return;
  let nextNode = sentenceNodeByPosition.get(nextIndex + 1);
  if (!nextNode && virtualDocument) {
    const chunkIndex = virtualWork.chunkIndexForPosition(nextIndex + 1);
    try {
      await virtualWork.ensureChunk(chunkIndex);
      virtualWork.setActiveChunkIndex(chunkIndex);
      nextNode = sentenceNodeByPosition.get(nextIndex + 1);
    } catch (error) {
      setTranslationStatus("다음 문장 청크를 불러오지 못했습니다.", true);
      return;
    }
  }
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
  virtualWork.warmChunks(virtualWork.chunkForNode(nextNode));
}

function activateSentenceForStudy(node) {
  if (!node) return false;
  selectSentence(node);
  scrollSentenceIntoView(node);
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  keepSentenceAboveStudyPanel(node);
  requestSentenceTranslation(false);
  return true;
}

async function nextVirtualUnstudiedSentenceNode() {
  if (!virtualDocument || !translationSentenceStatesLoaded) return null;
  const selectedChunkIndex = virtualWork.chunkForNode(selectedSentenceNode());
  const startingChunk = Math.max(
    0,
    selectedChunkIndex >= 0
      ? selectedChunkIndex
      : virtualWork.activeChunkIndex
  );
  for (let offset = 1; offset <= virtualChunkDescriptors.length; offset += 1) {
    const chunkIndex = (startingChunk + offset) % virtualChunkDescriptors.length;
    let chunk;
    try {
      chunk = await virtualWork.ensureChunk(chunkIndex);
    } catch (error) {
      continue;
    }
    const nodes = Array.from(chunk?.querySelectorAll(".reader-sentence") || []);
    const node = nodes.find((candidate) => !sentenceHasTranslationState(candidate));
    if (node) return node;
  }
  return null;
}

function nextGeneratedSentenceId() {
  if (!translationSentenceStatesLoaded) return "";
  const currentId = selectedSentence?.sentenceId || "";
  let firstId = "";
  let nextId = "";
  translationSentenceStates.forEach((state, sentenceId) => {
    if (normalizedTranslationReviewState(state.reviewState) !== "generated") return;
    if (!firstId || sentenceId.localeCompare(firstId) < 0) firstId = sentenceId;
    if (sentenceId.localeCompare(currentId) > 0 && (!nextId || sentenceId.localeCompare(nextId) < 0)) {
      nextId = sentenceId;
    }
  });
  return nextId || firstId;
}

async function nextVirtualReviewSentenceNode() {
  if (!virtualDocument) return null;
  const sentenceId = nextGeneratedSentenceId();
  if (!sentenceId) return null;
  try {
    return await virtualWork.ensureTarget(sentenceId);
  } catch (error) {
    return null;
  }
}

async function navigateToNextUnstudiedSentence() {
  const nextIndex = nextUnstudiedSentenceIndex();
  const nextNode = nextIndex >= 0
    ? sentenceNodes[nextIndex]
    : await nextVirtualUnstudiedSentenceNode();
  if (activateSentenceForStudy(nextNode)) return;
  setTranslationStatus(
    translationSentenceStatesLoaded
      ? "현재 위치 뒤에 미번역 문장이 없습니다."
      : "번역 상태를 아직 불러오는 중입니다.",
    true
  );
}

async function navigateToNextReviewSentence() {
  const nextIndex = nextGeneratedSentenceIndex();
  const nextNode = nextIndex >= 0
    ? sentenceNodes[nextIndex]
    : await nextVirtualReviewSentenceNode();
  if (activateSentenceForStudy(nextNode)) return;
  setTranslationStatus(
    translationSentenceStatesLoaded
      ? "검토할 번역이 없습니다."
      : "번역 상태를 아직 불러오는 중입니다.",
    true
  );
}

async function continueStudy() {
  const action = continueStudyButton?.dataset.studyAction || "continue";
  if (action === "preview-session") {
    previewStudySession();
    return;
  }
  const nextIndex = action === "review-generated"
    ? nextGeneratedSentenceIndex()
    : continueStudySentenceIndex();
  let nextNode = nextIndex >= 0 ? sentenceNodes[nextIndex] : null;
  if (!nextNode && virtualDocument) {
    nextNode = action === "review-generated"
      ? await nextVirtualReviewSentenceNode()
      : await nextVirtualUnstudiedSentenceNode();
  }
  if (!nextNode) {
    setTranslationStatus(
      translationSentenceStatesLoaded
        ? (action === "review-generated" ? "검토할 번역이 없습니다." : "모든 문장이 번역되었습니다.")
        : "번역 상태를 아직 불러오는 중입니다.",
      true
    );
    return;
  }
  activateSentenceForStudy(nextNode);
}
