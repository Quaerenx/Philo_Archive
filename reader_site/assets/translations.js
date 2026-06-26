const form = document.getElementById("translationsForm");
const queryInput = document.getElementById("translationsQuery");
const corpusSelect = document.getElementById("translationsCorpus");
const workInput = document.getElementById("translationsWork");
const workOptionsList = document.getElementById("translationsWorkOptions");
const reviewSelect = document.getElementById("translationsReview");
const submitButton = document.getElementById("translationsSubmit");
const clearButton = document.getElementById("translationsClear");
const activeFiltersEl = document.getElementById("translationsActiveFilters");
const statusEl = document.getElementById("translationsStatus");
const resultsEl = document.getElementById("translationsResults");
const exportTools = document.getElementById("translationsExportTools");
const exportMarkdown = document.getElementById("translationsExportMarkdown");
const exportJson = document.getElementById("translationsExportJson");
const reviewQueueButton = document.getElementById("translationsReviewQueue");
const listTools = document.getElementById("translationsListTools");
let lastRecords = [];
let activeController = null;
let activeRequest = 0;
let recentlyChangedRecordId = "";
let archiveCorpora = [];
let pendingReviewQueueFocus = false;
let pendingReviewQueueMessage = "";

const DEFAULT_CORPUS = "";
const REVIEW_LABELS = {
  all: "All",
  generated: "To check",
  reviewed: "Saved",
  rejected: "Rejected"
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function selectedOptionText(select) {
  const option = select.options[select.selectedIndex];
  return option ? option.textContent.trim() : select.value;
}

function selectedCorpusArchive() {
  const corpusId = corpusSelect.value || DEFAULT_CORPUS;
  return archiveCorpora.find((corpus) => corpus.id === corpusId) || null;
}

function archiveCorpusById(corpusId) {
  const id = corpusId || DEFAULT_CORPUS;
  return archiveCorpora.find((corpus) => corpus.id === id) || null;
}

function corpusDisplayName(corpusId) {
  const corpus = archiveCorpusById(corpusId);
  return cleanText(corpus?.title || corpusId || "Archive");
}

function workDisplayName(corpusId, workId) {
  const id = cleanText(workId || "");
  if (!id) return "";
  const corpus = archiveCorpusById(corpusId);
  for (const section of corpus?.sections || []) {
    const match = (section.links || []).find((link) => cleanText(link.work_id || "") === id);
    if (match) {
      const label = cleanText(match.label || id);
      const meta = cleanText(match.meta || "");
      return meta ? `${label} / ${meta}` : label;
    }
  }
  return id;
}

function sentenceDisplayName(record) {
  const id = cleanText(record.sentence_id || record.target_id || "");
  const match = /^p-(\d+)\.s(\d+)$/i.exec(id);
  if (match) {
    return `Paragraph ${Number(match[1])}, sentence ${Number(match[2])}`;
  }
  return id;
}

function archiveWorkOptions(corpus) {
  const seen = new Set();
  const options = [];
  (corpus?.sections || []).forEach((section) => {
    (section.links || []).forEach((link) => {
      const workId = cleanText(link.work_id || "");
      if (!workId || seen.has(workId)) return;
      seen.add(workId);
      const label = cleanText(link.label || workId);
      const meta = cleanText(link.meta || "");
      options.push({
        workId,
        label: meta ? `${label} / ${meta}` : label
      });
    });
  });
  return options.sort((left, right) => left.workId.localeCompare(right.workId));
}

function updateWorkOptions() {
  if (!workOptionsList) return;
  const options = archiveWorkOptions(selectedCorpusArchive());
  workOptionsList.innerHTML = options
    .map((option) => `<option value="${escapeHtml(option.workId)}" label="${escapeHtml(option.label)}"></option>`)
    .join("");
  workInput.placeholder = corpusSelect.value
    ? (options.length ? `${options.length.toLocaleString()} works` : "work id")
    : "optional work id";
}

function fetchParams(format = "json") {
  const params = new URLSearchParams({
    format,
    review_state: "all"
  });
  if (corpusSelect.value) params.set("corpus_id", corpusSelect.value);
  const workId = workInput.value.trim();
  if (workId) params.set("work_id", workId);
  return params;
}

function exportParams(format = "markdown") {
  const params = new URLSearchParams({
    format,
    review_state: reviewSelect.value || "all"
  });
  const query = queryInput.value.trim();
  if (query) params.set("q", query);
  if (corpusSelect.value) params.set("corpus_id", corpusSelect.value);
  const workId = workInput.value.trim();
  if (workId) params.set("work_id", workId);
  return params;
}

function urlParams() {
  const params = new URLSearchParams();
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value || "";
  const workId = workInput.value.trim();
  const reviewState = reviewSelect.value || "all";
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (reviewState !== "all") params.set("review_state", reviewState);
  return params;
}

function updateExportLinks() {
  exportMarkdown.href = `/api/sentence-translations/export?${exportParams("markdown")}`;
  exportJson.href = `/api/sentence-translations/export?${exportParams("json")}`;
}

function hasActiveFilters() {
  return Boolean(
    queryInput.value.trim() ||
    corpusSelect.value ||
    workInput.value.trim() ||
    reviewSelect.value !== "all"
  );
}

function hasSearchFilters() {
  return Boolean(
    queryInput.value.trim() ||
    corpusSelect.value ||
    workInput.value.trim()
  );
}

function renderFilterChip(filterName, label, value) {
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="Remove ${escapeHtml(label)} filter">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">x</span>
  </button>`;
}

function updateFilterSummary() {
  if (!activeFiltersEl) return;
  const chips = [];
  const query = queryInput.value.trim();
  const workId = workInput.value.trim();
  if (query) chips.push(renderFilterChip("query", "Text", query));
  if (corpusSelect.value) {
    chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  }
  if (workId) chips.push(renderFilterChip("work", "Work", workId));
  if (reviewSelect.value !== "all") {
    chips.push(renderFilterChip("review", "Status", selectedOptionText(reviewSelect)));
  }
  activeFiltersEl.hidden = chips.length === 0;
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">Filters</span>${chips.join("")}`
    : "";
}

function updateClearState(isBusy = form.classList.contains("is-loading")) {
  clearButton.disabled = isBusy || !hasActiveFilters();
  updateFilterSummary();
}

function updateTranslationsListChrome(count = lastRecords.length) {
  const activeFilters = hasActiveFilters();
  const shouldOpenTools = hasSearchFilters();
  const showTools = count > 0 || activeFilters;
  if (listTools) {
    listTools.hidden = !showTools;
    listTools.open = shouldOpenTools;
  }
  form.hidden = !showTools;
  if (activeFiltersEl) {
    activeFiltersEl.hidden = !activeFilters;
  }
}

function updateUrl() {
  const params = urlParams();
  history.replaceState(null, "", params.toString() ? `/translations?${params}` : "/translations");
  updateClearState();
}

function setBusy(isBusy) {
  form.classList.toggle("is-loading", isBusy);
  resultsEl.setAttribute("aria-busy", isBusy ? "true" : "false");
  submitButton.disabled = isBusy;
  submitButton.setAttribute("aria-busy", isBusy ? "true" : "false");
  if (reviewQueueButton) {
    reviewQueueButton.disabled = isBusy || generatedRecords(lastRecords).length === 0;
  }
  updateClearState(isBusy);
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

function renderPending() {
  statusEl.textContent = "";
  resultsEl.innerHTML = `
    <article class="translation-record-card notes-skeleton" aria-hidden="true">
      <span class="notes-skeleton-line title"></span>
      <span class="notes-skeleton-line"></span>
      <span class="notes-skeleton-line short"></span>
    </article>
    <article class="translation-record-card notes-skeleton" aria-hidden="true">
      <span class="notes-skeleton-line title"></span>
      <span class="notes-skeleton-line"></span>
      <span class="notes-skeleton-line short"></span>
    </article>`;
  setBusy(true);
}

function recordMatchesQuery(record) {
  const query = queryInput.value.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    record.corpus_id,
    record.work_id,
    record.segment_id,
    record.sentence_id,
    record.source_text_excerpt,
    record.translation,
    record.commentary
  ].map(cleanText).join(" ").toLowerCase();
  return haystack.includes(query);
}

function normalizedReviewState(record) {
  const state = cleanText(record.review_state).toLowerCase();
  return ["generated", "reviewed", "rejected"].includes(state) ? state : "generated";
}

function generatedRecords(records) {
  return records.filter((record) => normalizedReviewState(record) === "generated");
}

function updateReviewQueueButton(records = lastRecords) {
  if (!reviewQueueButton) return;
  const generatedCount = generatedRecords(records).length;
  reviewQueueButton.hidden = generatedCount === 0;
  reviewQueueButton.textContent = generatedCount
    ? `Review queue (${generatedCount.toLocaleString()})`
    : "Review queue";
  reviewQueueButton.disabled = form.classList.contains("is-loading") || generatedCount === 0;
  reviewQueueButton.title = generatedCount
    ? `Review ${generatedCount.toLocaleString()} generated translations`
    : "Review queue is empty";
}

function recordMatchesReview(record) {
  const selected = reviewSelect.value || "all";
  return selected === "all" || normalizedReviewState(record) === selected;
}

function reviewActionsVisible() {
  return (reviewSelect.value || "all") !== "all";
}

function summaryCounts(records) {
  return records.reduce((counts, record) => {
    counts.total += 1;
    counts[normalizedReviewState(record)] += 1;
    return counts;
  }, { total: 0, generated: 0, reviewed: 0, rejected: 0 });
}

function summaryButton(filter, label, count) {
  const selected = (filter || "all") === (reviewSelect.value || "all");
  return `<button type="button" class="${selected ? "active" : ""}" data-translation-summary-filter="${escapeHtml(filter)}" aria-pressed="${selected ? "true" : "false"}">
    <span>${escapeHtml(label)}</span>
    <strong>${Number(count || 0).toLocaleString()}</strong>
  </button>`;
}

function renderSummary(records) {
  const counts = summaryCounts(records);
  const nonzeroStates = ["generated", "reviewed", "rejected"].filter((state) => counts[state] > 0);
  if (nonzeroStates.length < 2) return "";
  return `<details class="translation-record-summary-tools">
    <summary>Status</summary>
    <nav class="translation-record-summary" aria-label="Visible translations by status">
      ${summaryButton("all", "All", counts.total)}
      ${summaryButton("generated", "To check", counts.generated)}
      ${summaryButton("reviewed", "Saved", counts.reviewed)}
      ${summaryButton("rejected", "Rejected", counts.rejected)}
    </nav>
  </details>`;
}

function renderEmptyRecords() {
  const filtered = hasActiveFilters();
  const title = filtered ? "No translations match these filters." : "No translations yet.";
  const body = filtered
    ? "Clear filters, or choose a broader status and work id."
    : "Open a work and click a sentence. Translation and commentary will appear here for review.";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">Clear filters</button>'
    : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    <p>${escapeHtml(body)}</p>
    <div class="empty-actions">
      ${clearAction}
      <a href="/search">Find a work</a>
      <a href="/study">Study</a>
    </div>
  </section>`;
}

function recordTitle(record) {
  return cleanText(record.target_label || sentenceDisplayName(record) || record.work_id || "Translation record");
}

function recordContext(record) {
  const hasWork = Boolean(cleanText(record.work_id || ""));
  return [
    corpusDisplayName(record.corpus_id),
    hasWork ? workDisplayName(record.corpus_id, record.work_id) : ""
  ].filter(Boolean).join(" / ");
}

function visibleReviewStates(records) {
  return new Set(records.map(normalizedReviewState));
}

function renderRecord(record, options) {
  options = options || {};
  const reviewState = normalizedReviewState(record);
  const title = recordTitle(record) || "Translation record";
  const context = recordContext(record);
  const source = cleanText(record.source_text_excerpt || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const targetUrl = cleanText(record.target_url || "");
  const isRecent = record.id === recentlyChangedRecordId;
  const reviewLabel = REVIEW_LABELS[reviewState] || reviewState;
  const showReviewBadge = options.showReviewBadge !== false;
  const showReviewActions = options.showReviewActions === true;
  const reviewKicker = showReviewBadge
    ? `<div class="translation-record-kicker">
        <span class="review-badge" aria-label="Review status: ${escapeHtml(reviewLabel)}">${escapeHtml(reviewLabel)}</span>
      </div>`
    : "";
  const rejectAction = reviewState !== "rejected"
    ? `<details class="translation-more-actions">
        <summary>More</summary>
        <button type="button" data-review-state="rejected" aria-keyshortcuts="X" title="Reject">Reject</button>
      </details>`
    : "";
  const actions = showReviewActions ? [
    reviewState !== "reviewed"
      ? '<button type="button" class="primary-review-action" data-review-state="reviewed" aria-keyshortcuts="R" title="Save translation">Save</button>'
      : "",
    reviewState !== "generated"
      ? '<button type="button" data-review-state="generated" aria-keyshortcuts="G" title="Move back to check">To check</button>'
      : "",
    rejectAction
  ].filter(Boolean).join("") : "";
  return `<article class="translation-record-card${isRecent ? " is-recent" : ""}" tabindex="-1" data-record-id="${escapeHtml(record.id)}" data-corpus-id="${escapeHtml(record.corpus_id)}" data-review-state="${escapeHtml(reviewState)}">
    <header class="translation-record-heading">
      <h2 class="translation-record-title">${targetUrl ? `<a href="${escapeHtml(targetUrl)}" data-open-source aria-keyshortcuts="O" title="Open source">${escapeHtml(title)}</a>` : escapeHtml(title)}</h2>
      ${reviewKicker}
      ${context ? `<div class="translation-record-context">${escapeHtml(context)}</div>` : ""}
    </header>
    ${translation ? `<p class="translation-text">${escapeHtml(translation)}</p>` : ""}
    ${commentary ? `<section class="translation-commentary" aria-label="Commentary"><h3>Commentary</h3><p>${escapeHtml(commentary)}</p></section>` : ""}
    ${source ? `<details class="translation-source"><summary>Original source</summary><blockquote>${escapeHtml(source)}</blockquote></details>` : ""}
    ${actions ? `<footer class="translation-record-footer">
      <div class="translation-actions">
        ${actions}
      </div>
    </footer>` : ""}
  </article>`;
}

function renderRecords(records) {
  lastRecords = records;
  updateTranslationsListChrome(records.length);
  const queryMatched = records.filter(recordMatchesQuery);
  const visible = queryMatched.filter(recordMatchesReview);
  updateReviewQueueButton(records);
  if (exportTools) {
    exportTools.hidden = visible.length === 0;
    if (!visible.length) exportTools.open = false;
  }
  const showReviewBadges = visibleReviewStates(visible).size > 1;
  const showReviewActions = reviewActionsVisible();
  statusEl.textContent = "";
  resultsEl.innerHTML = queryMatched.length
    ? renderSummary(queryMatched) + (visible.length ? visible.map((record) => renderRecord(record, { showReviewBadge: showReviewBadges, showReviewActions })).join("") : renderEmptyRecords())
    : renderEmptyRecords();
  if (pendingReviewQueueFocus) {
    const reviewMessage = pendingReviewQueueMessage;
    pendingReviewQueueFocus = false;
    pendingReviewQueueMessage = "";
    if (focusFirstReviewQueueRecord()) {
      statusEl.textContent = reviewMessage
        ? `${reviewMessage} Next review item ready.`
        : `${visible.length.toLocaleString()} translations / review item ready.`;
    } else if (reviewSelect.value === "generated") {
      statusEl.textContent = reviewMessage ? `${reviewMessage} Review queue is empty.` : "Review queue is empty.";
    }
  }
  recentlyChangedRecordId = "";
}

function focusFirstReviewQueueRecord() {
  const card = resultsEl.querySelector('.translation-record-card[data-review-state="generated"]');
  if (!card) return false;
  return focusRecordCard(card, true);
}

function openReviewQueue() {
  if (!generatedRecords(lastRecords).length) {
    statusEl.textContent = "Review queue is empty.";
    return;
  }
  queryInput.value = "";
  reviewSelect.value = "generated";
  pendingReviewQueueFocus = true;
  pendingReviewQueueMessage = "";
  updateUrl();
  updateExportLinks();
  updateClearState();
  renderRecords(lastRecords);
}

function visibleRecordCards() {
  return Array.from(resultsEl.querySelectorAll(".translation-record-card:not(.notes-skeleton)"));
}

function focusedRecordCard() {
  return document.activeElement?.closest?.(".translation-record-card") || null;
}

function clearReviewTargetHighlight() {
  resultsEl.querySelectorAll(".translation-record-card.is-review-target").forEach((node) => {
    node.classList.remove("is-review-target");
  });
}

function focusRecordCard(card, reviewTarget = false) {
  if (!card) return false;
  clearReviewTargetHighlight();
  if (reviewTarget) {
    card.classList.add("is-review-target");
  }
  if (typeof card.scrollIntoView === "function") {
    card.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
  if (typeof card.focus === "function") {
    try {
      card.focus({ preventScroll: true });
    } catch {
      card.focus();
    }
  }
  return true;
}

function navigateRecordFocus(delta) {
  const cards = visibleRecordCards();
  if (!cards.length) return false;
  const current = focusedRecordCard();
  const currentIndex = current ? cards.indexOf(current) : -1;
  const nextIndex = currentIndex < 0
    ? (delta < 0 ? cards.length - 1 : 0)
    : Math.min(cards.length - 1, Math.max(0, currentIndex + delta));
  return focusRecordCard(cards[nextIndex]);
}

function triggerFocusedReviewAction(reviewState) {
  const card = focusedRecordCard();
  if (!card) return false;
  const button = card.querySelector(`button[data-review-state="${reviewState}"]`);
  if (!button || button.disabled) return false;
  button.click();
  return true;
}

function openFocusedSource() {
  const card = focusedRecordCard();
  if (!card) return false;
  const sourceLink = card.querySelector("[data-open-source]");
  if (!sourceLink) return false;
  sourceLink.click();
  return true;
}

function isTypingTarget(target) {
  return Boolean(target && (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  ));
}

function clearFilters() {
  queryInput.value = "";
  corpusSelect.value = DEFAULT_CORPUS;
  workInput.value = "";
  reviewSelect.value = "all";
  loadRecords();
  queryInput.focus();
}

function removeFilter(filterName) {
  if (filterName === "query") {
    queryInput.value = "";
  } else if (filterName === "corpus") {
    corpusSelect.value = DEFAULT_CORPUS;
  } else if (filterName === "work") {
    workInput.value = "";
  } else if (filterName === "review") {
    reviewSelect.value = "all";
  }
  loadRecords();
}

async function updateRecordReview(recordId, corpusId, reviewState) {
  const response = await fetch(`/api/sentence-translations/${encodeURIComponent(recordId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ corpus_id: corpusId, review_state: reviewState })
  });
  return response.ok;
}

async function loadCorpora() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) return;
    const payload = await response.json();
    archiveCorpora = payload.corpora || [];
    const current = corpusSelect.value || DEFAULT_CORPUS;
    corpusSelect.innerHTML = '<option value="">All corpora</option>' + archiveCorpora
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title || corpus.id)}</option>`)
      .join("");
    const hasCurrent = Array.from(corpusSelect.options).some((option) => option.value === current);
    if (!hasCurrent) {
      const fallback = document.createElement("option");
      fallback.value = current;
      fallback.textContent = current || "All corpora";
      corpusSelect.appendChild(fallback);
    }
    corpusSelect.value = current;
    updateWorkOptions();
  } catch {
    // The hard-coded corpus options remain usable without archive metadata.
  }
}

async function loadRecords() {
  const requestId = activeRequest + 1;
  activeRequest = requestId;
  if (activeController) {
    activeController.abort();
    activeController = null;
  }
  updateUrl();
  updateExportLinks();
  const controller = new AbortController();
  activeController = controller;
  renderPending();
  try {
    const response = await fetch(`/api/sentence-translations/export?${fetchParams("json")}`, { signal: controller.signal });
    if (requestId !== activeRequest) return;
    if (!response.ok) {
      statusEl.textContent = "Could not load translations.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    renderRecords(payload.records || []);
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (requestId === activeRequest) {
      statusEl.textContent = "Could not load translations.";
      resultsEl.innerHTML = "";
    }
  } finally {
    if (requestId === activeRequest) {
      activeController = null;
      setBusy(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadRecords();
});

clearButton.addEventListener("click", clearFilters);

if (reviewQueueButton) {
  reviewQueueButton.addEventListener("click", openReviewQueue);
}

document.addEventListener("keydown", (event) => {
  if (isTypingTarget(event.target) || event.altKey || event.ctrlKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  if (key === "q") {
    event.preventDefault();
    openReviewQueue();
    return;
  }
  if (key === "j" || event.key === "ArrowDown") {
    if (navigateRecordFocus(1)) {
      event.preventDefault();
    }
    return;
  }
  if (key === "k" || event.key === "ArrowUp") {
    if (navigateRecordFocus(-1)) {
      event.preventDefault();
    }
    return;
  }
  if (key === "r" || key === "x" || key === "g") {
    const state = key === "r" ? "reviewed" : (key === "x" ? "rejected" : "generated");
    if (triggerFocusedReviewAction(state)) {
      event.preventDefault();
    }
    return;
  }
  if (key === "o" && openFocusedSource()) {
    event.preventDefault();
  }
});

activeFiltersEl.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-filter]");
  if (!button) return;
  removeFilter(button.dataset.filter || "");
});

resultsEl.addEventListener("click", async (event) => {
  const summaryFilter = event.target.closest("[data-translation-summary-filter]");
  if (summaryFilter) {
    reviewSelect.value = summaryFilter.dataset.translationSummaryFilter || "all";
    renderRecords(lastRecords);
    updateUrl();
    updateExportLinks();
    updateClearState();
    return;
  }
  const emptyAction = event.target.closest("[data-empty-action]");
  if (emptyAction) {
    if (emptyAction.dataset.emptyAction === "clear-filters") {
      clearFilters();
    }
    return;
  }
  const reviewButton = event.target.closest("button[data-review-state]");
  if (!reviewButton) return;
  const card = reviewButton.closest(".translation-record-card");
  if (!card) return;
  const recordId = card.dataset.recordId || "";
  const corpusId = card.dataset.corpusId || corpusSelect.value || DEFAULT_CORPUS;
  const nextState = reviewButton.dataset.reviewState || "generated";
  setActionButtonBusy(reviewButton, true);
  try {
    const ok = await updateRecordReview(recordId, corpusId, nextState);
    if (ok) {
      recentlyChangedRecordId = recordId;
      pendingReviewQueueFocus = reviewSelect.value === "generated" && nextState !== "generated";
      pendingReviewQueueMessage = pendingReviewQueueFocus ? "Saved." : "";
    }
    statusEl.textContent = ok ? "Saved." : "Could not save.";
    await loadRecords();
  } finally {
    setActionButtonBusy(reviewButton, false);
  }
});

corpusSelect.addEventListener("change", () => {
  updateWorkOptions();
  loadRecords();
});

for (const field of [workInput, reviewSelect]) {
  field.addEventListener("change", loadRecords);
}

queryInput.addEventListener("input", () => {
  updateUrl();
  renderRecords(lastRecords);
});

for (const field of [queryInput, workInput]) {
  field.addEventListener("input", updateClearState);
}

for (const field of [corpusSelect, reviewSelect]) {
  field.addEventListener("change", updateClearState);
}

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
corpusSelect.value = initialParams.get("corpus_id") || DEFAULT_CORPUS;
workInput.value = initialParams.get("work_id") || "";
reviewSelect.value = initialParams.get("review_state") || "all";

updateClearState();
loadCorpora().then(loadRecords);
