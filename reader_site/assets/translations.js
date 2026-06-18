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
const exportMarkdown = document.getElementById("translationsExportMarkdown");
const exportJson = document.getElementById("translationsExportJson");
let lastRecords = [];
let activeController = null;
let activeRequest = 0;
let recentlyChangedRecordId = "";
let archiveCorpora = [];

const DEFAULT_CORPUS = "nietzsche";
const REVIEW_LABELS = {
  all: "All",
  generated: "Generated",
  reviewed: "Reviewed",
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

function selectedOptionText(select) {
  const option = select.options[select.selectedIndex];
  return option ? option.textContent.trim() : select.value;
}

function selectedCorpusArchive() {
  const corpusId = corpusSelect.value || DEFAULT_CORPUS;
  return archiveCorpora.find((corpus) => corpus.id === corpusId) || null;
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
  workInput.placeholder = options.length ? `${options.length.toLocaleString()} works` : "work id";
}

function fetchParams(format = "json") {
  const params = new URLSearchParams({
    corpus_id: corpusSelect.value || DEFAULT_CORPUS,
    format,
    review_state: "all"
  });
  const workId = workInput.value.trim();
  if (workId) params.set("work_id", workId);
  return params;
}

function exportParams(format = "markdown") {
  const params = new URLSearchParams({
    corpus_id: corpusSelect.value || DEFAULT_CORPUS,
    format,
    review_state: reviewSelect.value || "all"
  });
  const workId = workInput.value.trim();
  if (workId) params.set("work_id", workId);
  return params;
}

function urlParams() {
  const params = new URLSearchParams();
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value || DEFAULT_CORPUS;
  const workId = workInput.value.trim();
  const reviewState = reviewSelect.value || "all";
  if (query) params.set("q", query);
  if (corpusId !== DEFAULT_CORPUS) params.set("corpus_id", corpusId);
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
    (corpusSelect.value && corpusSelect.value !== DEFAULT_CORPUS) ||
    workInput.value.trim() ||
    reviewSelect.value !== "all"
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
  if (query) chips.push(renderFilterChip("query", "Query", query));
  if (corpusSelect.value && corpusSelect.value !== DEFAULT_CORPUS) {
    chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  }
  if (workId) chips.push(renderFilterChip("work", "Work", workId));
  if (reviewSelect.value !== "all") {
    chips.push(renderFilterChip("review", "Review", selectedOptionText(reviewSelect)));
  }
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">Filters</span>${chips.join("")}`
    : "";
}

function updateClearState(isBusy = form.classList.contains("is-loading")) {
  clearButton.disabled = isBusy || !hasActiveFilters();
  updateFilterSummary();
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
  statusEl.textContent = "Loading AI translation records...";
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

function recordMatchesReview(record) {
  const selected = reviewSelect.value || "all";
  return selected === "all" || normalizedReviewState(record) === selected;
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
  return `<nav class="translation-record-summary" aria-label="Visible AI translations by review state">
    ${summaryButton("all", "All", counts.total)}
    ${summaryButton("generated", "Generated", counts.generated)}
    ${summaryButton("reviewed", "Reviewed", counts.reviewed)}
    ${summaryButton("rejected", "Rejected", counts.rejected)}
  </nav>`;
}

function renderEmptyRecords() {
  const filtered = hasActiveFilters();
  const title = filtered ? "No AI translation records match these filters." : "No AI translation records for this corpus yet.";
  const body = filtered
    ? "Try clearing the filters, or choose a broader review state and work id."
    : "Open a work page, select a sentence, and let Gemma generate a translation to create a local study record.";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">Clear filters</button>'
    : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    <p>${escapeHtml(body)}</p>
    <div class="empty-actions">
      ${clearAction}
      <a href="/search">Find a work</a>
      <a href="/study">Study reviewed notes</a>
    </div>
  </section>`;
}

function recordTitle(record) {
  return [record.corpus_id, record.work_id, record.sentence_id || record.target_id].filter(Boolean).join(" / ");
}

function renderRecord(record) {
  const reviewState = normalizedReviewState(record);
  const title = recordTitle(record) || "AI translation record";
  const date = record.updated_at || record.reviewed_at || record.generated_at || record.created_at || "";
  const source = cleanText(record.source_text_excerpt || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const targetUrl = cleanText(record.target_url || "");
  const isRecent = record.id === recentlyChangedRecordId;
  return `<article class="translation-record-card${isRecent ? " is-recent" : ""}" data-record-id="${escapeHtml(record.id)}" data-corpus-id="${escapeHtml(record.corpus_id)}" data-review-state="${escapeHtml(reviewState)}">
    <div class="note-title">
      ${targetUrl ? `<a href="${escapeHtml(targetUrl)}">${escapeHtml(title)}</a>` : escapeHtml(title)}
      <span class="note-meta">${escapeHtml(cleanText(date))}</span>
      <span class="review-badge ${escapeHtml(reviewState)}">${escapeHtml(REVIEW_LABELS[reviewState] || reviewState)}</span>
    </div>
    ${source ? `<blockquote class="translation-source">${escapeHtml(source)}</blockquote>` : ""}
    ${translation ? `<p class="translation-text">${escapeHtml(translation)}</p>` : ""}
    ${commentary ? `<details class="translation-commentary"><summary>Commentary</summary><p>${escapeHtml(commentary)}</p></details>` : ""}
    <div class="translation-actions">
      ${targetUrl ? `<a href="${escapeHtml(targetUrl)}">Open source</a>` : ""}
      <button type="button" data-review-state="reviewed" ${reviewState === "reviewed" ? "disabled" : ""}>Mark reviewed</button>
      <button type="button" data-review-state="generated" ${reviewState === "generated" ? "disabled" : ""}>Mark generated</button>
      <button type="button" data-review-state="rejected" ${reviewState === "rejected" ? "disabled" : ""}>Reject</button>
    </div>
  </article>`;
}

function renderRecords(records) {
  lastRecords = records;
  const queryMatched = records.filter(recordMatchesQuery);
  const visible = queryMatched.filter(recordMatchesReview);
  statusEl.textContent = visible.length
    ? `${visible.length.toLocaleString()} AI translation records`
    : "No AI translation records found.";
  resultsEl.innerHTML = queryMatched.length
    ? renderSummary(queryMatched) + (visible.length ? visible.map(renderRecord).join("") : renderEmptyRecords())
    : renderEmptyRecords();
  recentlyChangedRecordId = "";
}

function clearFilters() {
  queryInput.value = "";
  corpusSelect.value = DEFAULT_CORPUS;
  workInput.value = "";
  reviewSelect.value = "all";
  loadRecords();
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
    corpusSelect.innerHTML = archiveCorpora
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title || corpus.id)}</option>`)
      .join("");
    const hasCurrent = Array.from(corpusSelect.options).some((option) => option.value === current);
    if (!hasCurrent) {
      const fallback = document.createElement("option");
      fallback.value = current;
      fallback.textContent = current;
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
      statusEl.textContent = "Could not load AI translation records.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    renderRecords(payload.records || []);
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (requestId === activeRequest) {
      statusEl.textContent = "Could not load AI translation records.";
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
    }
    statusEl.textContent = ok ? "AI translation review state updated." : "Could not update AI translation review state.";
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
