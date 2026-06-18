const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const sentenceContext = document.getElementById("sentenceContext");
const previousSentenceButton = document.getElementById("previousSentence");
const nextSentenceButton = document.getElementById("nextSentence");
const regenerateSentenceButton = document.getElementById("regenerateSentence");
const markTranslationReviewedButton = document.getElementById("markTranslationReviewed");
const rejectTranslationButton = document.getElementById("rejectTranslation");
const copyStudyCardButton = document.getElementById("copyStudyCard");
const draftTranslationNoteButton = document.getElementById("draftTranslationNote");
const readingModeButton = document.getElementById("readingMode");
const studyModeButton = document.getElementById("studyMode");
const translationStatus = document.getElementById("translationStatus");
const translationOutput = document.getElementById("translationOutput");
const translationCard = document.querySelector(".translation-card");
const studyPage = document.querySelector(".study-page");
const studyPanelToggle = document.getElementById("studyPanelToggle");
const exportReviewedTranslations = document.getElementById("exportReviewedTranslations");
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
let translationMode = "reading";
let translationStatusTimer = null;
let recentlyChangedNoteId = "";
const COMMENTARY_COLLAPSE_LENGTH = 420;
const STUDY_PANEL_STORAGE_KEY = "philo.reader.studyPanelExpanded";

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
  studyTabs.forEach((tab) => {
    const active = tab.dataset.studyTab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.tabIndex = active ? 0 : -1;
    if (active && focusTab) {
      tab.focus();
    }
  });
  studyPanels.forEach((panel) => {
    const active = panel.dataset.studyPanel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
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
  if (!selectedSentence) return "Select a sentence";
  const index = sentenceIndex(selectedSentence.sentenceId);
  return index >= 0 ? `Sentence ${index + 1} of ${sentenceNodes.length}` : selectedSentence.sentenceId;
}

function studyPanelToggleSummary() {
  if (!selectedSentence) return "Select a sentence";
  const position = selectedSentencePositionLabel();
  if (translationCard && translationCard.classList.contains("is-loading")) {
    return `${position} / studying`;
  }
  if (translationOutput && translationOutput.querySelector(".translation-error")) {
    return `${position} / unavailable`;
  }
  if (selectedTranslationRecord) {
    return `${position} / translation ready`;
  }
  return position;
}

function updateStudyPanelToggleLabel() {
  if (!studyPage || !studyPanelToggle) return;
  const expanded = studyPage.classList.contains("is-expanded");
  const action = expanded ? "Compact study panel" : "Full study panel";
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
  if (remember) {
    rememberStudyPanelExpanded(expanded);
  }
}

function setTranslationMode(mode) {
  translationMode = mode === "study" ? "study" : "reading";
  readingModeButton.classList.toggle("active", translationMode === "reading");
  studyModeButton.classList.toggle("active", translationMode === "study");
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
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

function sentenceIndex(sentenceId) {
  return sentenceNodes.findIndex((node) => (node.dataset.sentenceId || node.id) === sentenceId);
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
  previousSentenceButton.disabled = !hasSelection || index === 0;
  nextSentenceButton.disabled = !hasSelection || index === sentenceNodes.length - 1;
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
  const label = node ? cleanText(node.dataset.label || node.textContent) : researchData.title;
  const type = node ? (node.dataset.targetType || researchData.default_target_type || "segment") : "work";
  const baseUrl = location.origin + location.pathname + location.search;
  const url = id === "work"
    ? baseUrl
    : baseUrl + "#" + encodeURIComponent(id);
  return { id, label, type, url };
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
  }
  const index = sentenceIndex(sentence.sentenceId);
  const position = index >= 0 ? `Sentence ${index + 1} of ${sentenceNodes.length}` : sentence.sentenceId;
  translationTarget.textContent = `${position} / ${sentence.sentenceId}`;
  updateSentenceContext();
  updateSentenceControls();
  updateStudyPanelToggleLabel();
  if (updateHash) {
    history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(sentence.sentenceId)}`);
  }
}

function selectSentenceFromHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!id) return;
  const node = document.getElementById(id);
  if (node && node.classList.contains("reader-sentence")) {
    selectSentence(node, false);
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

function studyPanelViewportHeight() {
  if (!isMobileStudyLayout() || !studyPage) return 0;
  return Math.ceil(studyPage.getBoundingClientRect().height);
}

function mobileSentenceSafeBottom() {
  return window.innerHeight - studyPanelViewportHeight() - 18;
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

function renderList(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<ul>${values.map((value) => `<li>${escapeHtml(cleanText(value))}</li>`).join("")}</ul>`;
}

function optionalCautions(record) {
  const cautions = renderList(record.cautions);
  if (!cautions) return "";
  return `<section class="translation-section translation-extra">
      <h3>Cautions</h3>
      ${cautions}
    </section>`;
}

function renderCommentary(commentary) {
  const text = cleanText(commentary || "");
  const shouldCollapse = text.length > COMMENTARY_COLLAPSE_LENGTH;
  return `
    <section class="translation-section translation-commentary${shouldCollapse ? " is-collapsed" : ""}">
      <h3>Commentary</h3>
      <p>${escapeHtml(text)}</p>
      ${shouldCollapse ? '<button type="button" class="commentary-toggle" aria-expanded="false">Show full commentary</button>' : ""}
    </section>`;
}

function setTranslationBusy(isBusy) {
  if (translationCard) {
    translationCard.classList.toggle("is-loading", isBusy);
  }
  translationOutput.setAttribute("aria-busy", isBusy ? "true" : "false");
  updateStudyPanelToggleLabel();
}

function resetTranslationOutputScroll() {
  translationOutput.scrollTop = 0;
}

function renderTranslationPending(regenerate = false) {
  selectedTranslationRecord = null;
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  setTranslationBusy(true);
  resetTranslationOutputScroll();
  const actionLabel = regenerate ? "Regenerating study note" : "Studying selected sentence";
  translationOutput.innerHTML = `
    <div class="translation-loading" role="status" aria-label="${escapeHtml(actionLabel)}">
      <span class="loading-spinner" aria-hidden="true"></span>
      <span>${escapeHtml(actionLabel)}</span>
    </div>
    <p class="translation-pending-source">${escapeHtml(cleanText(selectedSentence?.text || ""))}</p>
    <div class="translation-skeleton" aria-hidden="true">
      <span class="translation-skeleton-line wide"></span>
      <span class="translation-skeleton-line"></span>
      <span class="translation-skeleton-line short"></span>
    </div>`;
  updateSentenceControls();
}

function renderTranslationError(message) {
  selectedTranslationRecord = null;
  setTranslationBusy(false);
  translationOutput.hidden = false;
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-error" role="note">
      <h3>Translation unavailable</h3>
      <p>${escapeHtml(cleanText(message || "Gemma runtime is not running."))}</p>
    </div>`;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

function renderTranslationRecord(record, cached) {
  selectedTranslationRecord = record;
  const reviewState = cleanText(record.review_state || "generated");
  setTranslationBusy(false);
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  resetTranslationOutputScroll();
  translationOutput.innerHTML = `
    <div class="translation-result">
      <div class="translation-review-state">${escapeHtml(reviewState)}${cached ? " / cached" : ""}</div>
      <section class="translation-section translation-extra">
        <h3>Original source</h3>
        <p>${escapeHtml(cleanText(record.source_text_excerpt || selectedSentence?.text || ""))}</p>
      </section>
      <section class="translation-section translation-section-primary">
        <h3>Translation</h3>
        <p class="translation-primary">${escapeHtml(cleanText(record.translation || ""))}</p>
      </section>
      ${renderCommentary(record.commentary || record.interpretation || "")}
      ${optionalCautions(record)}
    </div>
  `;
  updateStudyPanelToggleLabel();
  updateSentenceControls();
}

async function requestSentenceTranslation(regenerate = false) {
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
  setTranslationStatus(regenerate ? "Regenerating with Gemma..." : "Translating with Gemma...", true);
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
      setTranslationStatus(payload.error || "Gemma runtime is not running.", true);
      renderTranslationError(payload.error || "Gemma runtime is not running.");
      return;
    }
    renderTranslationRecord(payload.record, payload.cached);
    setTranslationStatus(payload.cached ? "Loaded cached translation." : "Generated translation saved locally.");
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeTranslationRequest) {
      const message = error && error.message ? error.message : "Gemma runtime is not running.";
      setTranslationStatus(message, true);
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
    setTranslationStatus("No generated translation is selected.", true);
    return;
  }
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
    renderTranslationRecord(payload.record, true);
    setTranslationStatus(reviewState === "reviewed" ? "Translation marked reviewed." : "Translation rejected.");
  } catch (error) {
    const message = error && error.message ? error.message : "Could not update translation review.";
    setTranslationStatus(message, true);
  } finally {
    setActionButtonBusy(actionButton, false);
    updateSentenceControls();
  }
}

function draftNoteFromTranslation() {
  if (!selectedTranslationRecord) return;
  const translation = cleanText(selectedTranslationRecord.translation || "");
  const commentary = cleanText(selectedTranslationRecord.commentary || selectedTranslationRecord.interpretation || "");
  const parts = [];
  if (translation) {
    parts.push(`Translation:\n${translation}`);
  }
  if (commentary) {
    parts.push(`Commentary:\n${commentary}`);
  }
  noteText.value = parts.join("\n\n");
  const existingTags = noteTags.value.split(",").map((item) => item.trim()).filter(Boolean);
  const mergedTags = Array.from(new Set([...existingTags, "ai-translation"]));
  noteTags.value = mergedTags.join(", ");
  setStudyPanel("notes");
  setStudyPanelExpanded(true);
  noteText.focus();
  setTranslationStatus("Translation drafted into Notes.");
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

async function copyStudyCard() {
  if (!selectedTranslationRecord) {
    setTranslationStatus("No generated translation is selected.", true);
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
  try {
    const response = await fetch(`/api/notes?${params}`);
    if (!response.ok) return;
    const payload = await response.json();
    notesList.innerHTML = payload.notes.length
      ? payload.notes.map((note) => {
        const tags = (note.tags || []).join(", ");
        const updated = note.updated_at ? ` / edited ${cleanText(note.updated_at)}` : "";
        const recentClass = note.id === recentlyChangedNoteId ? " is-recent" : "";
        return `<div class="note-item${recentClass}" data-note-id="${escapeHtml(note.id)}" data-note-tags="${escapeHtml(tags)}">
          <strong>${escapeHtml(cleanText(note.target_label))}</strong><br>
          <div class="note-text">${escapeHtml(cleanText(note.note))}</div>
          <small>${escapeHtml(cleanText(tags))}${escapeHtml(updated)}</small>
          <div class="note-actions">
            <button type="button" data-action="edit-note" data-note-id="${escapeHtml(note.id)}">Edit</button>
            <button type="button" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">Delete</button>
          </div>
        </div>`;
      }).join("")
      : "";
    if (recentlyChangedNoteId) {
      const recentNote = Array.from(notesList.querySelectorAll(".note-item"))
        .find((item) => item.dataset.noteId === recentlyChangedNoteId);
      if (recentNote && typeof recentNote.scrollIntoView === "function") {
        recentNote.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    }
  } catch (error) {
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

regenerateSentenceButton.addEventListener("click", () => requestSentenceTranslation(true));
previousSentenceButton.addEventListener("click", () => navigateSentence(-1));
nextSentenceButton.addEventListener("click", () => navigateSentence(1));
markTranslationReviewedButton.addEventListener("click", () => updateTranslationReview("reviewed"));
rejectTranslationButton.addEventListener("click", () => updateTranslationReview("rejected"));
copyStudyCardButton.addEventListener("click", copyStudyCard);
draftTranslationNoteButton.addEventListener("click", draftNoteFromTranslation);
readingModeButton.addEventListener("click", () => setTranslationMode("reading"));
studyModeButton.addEventListener("click", () => setTranslationMode("study"));
if (studyPanelToggle && studyPage) {
  studyPanelToggle.addEventListener("click", () => {
    setStudyPanelExpanded(!studyPage.classList.contains("is-expanded"), true);
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

translationOutput.addEventListener("click", (event) => {
  const toggle = event.target.closest(".commentary-toggle");
  if (!toggle) return;
  const commentary = toggle.closest(".translation-commentary");
  if (!commentary) return;
  const expanded = commentary.classList.toggle("is-expanded");
  commentary.classList.toggle("is-collapsed", !expanded);
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  toggle.textContent = expanded ? "Collapse commentary" : "Show full commentary";
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
  const target = currentTarget();
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
      noteForm.reset();
      noteStatus.textContent = "Note saved and highlighted.";
      await loadNotes();
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
    noteFilter._timer = window.setTimeout(loadNotes, 180);
  });
}

notesList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const noteId = button.dataset.noteId;
  const item = button.closest(".note-item");
  const currentText = item ? cleanText(item.querySelector(".note-text")?.textContent || "") : "";
  const currentTags = item ? cleanText(item.dataset.noteTags || "") : "";
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
    }
    setActionButtonBusy(button, false);
  }
});

window.addEventListener("hashchange", () => {
  updateCitationPreview();
  selectSentenceFromHash();
  updateSentenceControls();
});

function initializeStudyCompanion() {
  setTranslationMode("reading");
  setStudyPanelExpanded(storedStudyPanelExpanded());
  setStudyPanel("translation");
  const exportParams = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    review_state: "reviewed",
    format: "markdown"
  });
  exportReviewedTranslations.href = `/api/sentence-translations/export?${exportParams}`;
  const conceptsPanel = document.querySelector('[data-study-panel="concepts"]');
  if (conceptsPanel && !conceptsPanel.textContent.trim()) {
    conceptsPanel.innerHTML = '<section class="research-card"><h2>Concepts</h2><p class="source-notes">No concept notes for this work.</p></section>';
  }
  selectSentenceFromHash();
  if (selectedSentence) {
    requestSentenceTranslation(false);
  }
  updateSentenceControls();
}

updateCitationPreview();
initializeStudyCompanion();
loadNotes();
