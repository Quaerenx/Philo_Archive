const form = document.getElementById("studyForm");
const queryInput = document.getElementById("studyQuery");
const corpusSelect = document.getElementById("studyCorpus");
const workInput = document.getElementById("studyWork");
const tagInput = document.getElementById("studyTag");
const studySubmit = document.getElementById("studySubmit");
const studyClear = document.getElementById("studyClear");
const activeFiltersEl = document.getElementById("studyActiveFilters");
const statusEl = document.getElementById("studyStatus");
const resultsEl = document.getElementById("studyResults");
const exportMarkdown = document.getElementById("studyExportMarkdown");
const manageLink = document.getElementById("studyManageLink");
let requestedCorpusId = "";
let activeStudyController = null;
let activeStudyRequest = 0;

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

function currentParams(format = "json") {
  const params = new URLSearchParams({ format });
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  const workId = workInput.value.trim();
  const tag = tagInput.value.trim().replace(/^#/, "");
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (tag) params.set("tag", tag);
  return params;
}

function updateLinks() {
  const exportParams = currentParams("markdown");
  exportMarkdown.href = `/api/study/export?${exportParams}`;
  const manageParams = currentParams("json");
  manageParams.delete("format");
  manageParams.set("review_state", "reviewed");
  manageLink.href = `/notes?${manageParams}`;
}

function updateUrl() {
  const params = currentParams("json");
  params.delete("format");
  history.replaceState(null, "", params.toString() ? `/study?${params}` : "/study");
  updateStudyClearState();
}

function selectedOptionText(select) {
  const option = select.options[select.selectedIndex];
  return option ? option.textContent.trim() : select.value;
}

function hasActiveFilters() {
  return Boolean(
    queryInput.value.trim() ||
    corpusSelect.value ||
    workInput.value.trim() ||
    tagInput.value.trim()
  );
}

function renderFilterChip(filterName, label, value) {
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="Remove ${escapeHtml(label)} filter">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">x</span>
  </button>`;
}

function updateStudyFilterSummary() {
  if (!activeFiltersEl) return;
  const chips = [];
  const query = queryInput.value.trim();
  const workId = workInput.value.trim();
  const tag = tagInput.value.trim().replace(/^#/, "");
  if (query) chips.push(renderFilterChip("query", "Query", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  if (workId) chips.push(renderFilterChip("work", "Work", workId));
  if (tag) chips.push(renderFilterChip("tag", "Tag", tag));
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">Filters</span>${chips.join("")}`
    : "";
}

function updateStudyClearState(isBusy = form.classList.contains("is-loading")) {
  if (!studyClear) return;
  studyClear.disabled = isBusy || !hasActiveFilters();
  updateStudyFilterSummary();
}

function renderEmptyStudy() {
  const filtered = hasActiveFilters();
  const title = filtered ? "No reviewed notes match these filters." : "No reviewed study notes yet.";
  const body = filtered
    ? "Clear the filters, or manage research notes and mark the strongest ones as reviewed."
    : "Mark research notes as reviewed when they are ready for focused study; they will appear here as a reading bundle.";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">Clear filters</button>'
    : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    <p>${escapeHtml(body)}</p>
    <div class="empty-actions">
      ${clearAction}
      <a href="/notes?review_state=raw">Review raw notes</a>
      <a href="/search">Search works</a>
    </div>
  </section>`;
}

function clearStudyFilters() {
  queryInput.value = "";
  corpusSelect.value = "";
  workInput.value = "";
  tagInput.value = "";
  requestedCorpusId = "";
  loadStudy();
}

function removeStudyFilter(filterName) {
  if (filterName === "query") {
    queryInput.value = "";
  } else if (filterName === "corpus") {
    corpusSelect.value = "";
    requestedCorpusId = "";
  } else if (filterName === "work") {
    workInput.value = "";
  } else if (filterName === "tag") {
    tagInput.value = "";
  }
  loadStudy();
}

function setStudyBusy(isBusy) {
  form.classList.toggle("is-loading", isBusy);
  resultsEl.setAttribute("aria-busy", isBusy ? "true" : "false");
  if (studySubmit) {
    studySubmit.disabled = isBusy;
    studySubmit.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
  updateStudyClearState(isBusy);
}

function renderStudyPending() {
  statusEl.textContent = "Loading reviewed notes...";
  resultsEl.innerHTML = `
    <section class="study-group study-skeleton" aria-hidden="true">
      <span class="study-skeleton-line title"></span>
      <span class="study-skeleton-line"></span>
      <span class="study-skeleton-line short"></span>
    </section>
    <section class="study-group study-skeleton" aria-hidden="true">
      <span class="study-skeleton-line title"></span>
      <span class="study-skeleton-line"></span>
      <span class="study-skeleton-line short"></span>
    </section>`;
  setStudyBusy(true);
}

function noteManageHref(note) {
  const params = new URLSearchParams({ review_state: "reviewed" });
  if (note.corpus_id) params.set("corpus_id", note.corpus_id);
  if (note.work_id) params.set("work_id", note.work_id);
  if (note.target_id) params.set("target_id", note.target_id);
  return `/notes?${params}`;
}

function noteTargetMeta(note) {
  const parts = [];
  const targetType = cleanText(note.target_type || "");
  const targetId = cleanText(note.target_id || "");
  const variantId = cleanText(note.variant_id || "");
  if (targetType || targetId) {
    parts.push([targetType, targetId].filter(Boolean).join(" / "));
  }
  if (variantId) {
    parts.push(`variant / ${variantId}`);
  }
  return parts;
}

function renderNote(note) {
  const target = note.target_label || note.target_id || "Target";
  const date = note.reviewed_at || note.updated_at || note.created_at || "";
  const tags = (note.tags || []).join(", ");
  const quote = note.quote ? `<blockquote class="note-quote">${escapeHtml(cleanText(note.quote))}</blockquote>` : "";
  const targetLink = note.url
    ? `<a href="${escapeHtml(note.url)}">${escapeHtml(target)}</a>`
    : escapeHtml(target);
  const targetMeta = noteTargetMeta(note)
    .map((item) => `<span>${escapeHtml(item)}</span>`)
    .join("");
  const missingTarget = note.url ? "" : `<span class="target-warning">Target URL missing</span>`;
  const openTarget = note.url ? `<a href="${escapeHtml(note.url)}">Open target</a>` : "";
  const manageHref = noteManageHref(note);
  return `<article class="study-note">
    <div class="note-title">
      ${targetLink}
      <span class="note-meta">${escapeHtml(cleanText(date))}</span>
    </div>
    ${targetMeta || missingTarget ? `<div class="target-meta">${targetMeta}${missingTarget}</div>` : ""}
    ${tags ? `<div class="note-tags">${escapeHtml(tags)}</div>` : ""}
    <p class="note-text">${escapeHtml(cleanText(note.note))}</p>
    ${quote}
    <div class="note-actions">
      ${openTarget}
      <a href="${escapeHtml(manageHref)}">Manage note</a>
    </div>
  </article>`;
}

function renderStudy(payload) {
  const groups = payload.groups || [];
  const count = payload.count || 0;
  statusEl.textContent = count ? `${count.toLocaleString()} reviewed notes` : "";
  resultsEl.innerHTML = groups.length
    ? groups.map((group) => {
      const title = [group.corpus_id, group.work_id].filter(Boolean).join(" / ") || "Reviewed notes";
      const workHref = group.corpus_id && group.work_id ? `/work/${encodeURIComponent(group.corpus_id)}/${encodeURIComponent(group.work_id)}` : "";
      const notesHref = `/notes?corpus_id=${encodeURIComponent(group.corpus_id)}&work_id=${encodeURIComponent(group.work_id)}&review_state=reviewed`;
      const tagCounts = (group.tag_counts || [])
        .map((item) => `<span class="study-tag">${escapeHtml(item.tag)} <span>${Number(item.count || 0).toLocaleString()}</span></span>`)
        .join("");
      const reviewedRange = group.reviewed_range || {};
      const rangeText = reviewedRange.start || reviewedRange.end
        ? `${cleanText(reviewedRange.start)} - ${cleanText(reviewedRange.end)}`
        : "";
      return `<section class="study-group">
        <h2>${escapeHtml(title)}</h2>
        <div class="group-meta">${escapeHtml(group.summary || `${group.notes.length.toLocaleString()} reviewed notes`)}</div>
        ${rangeText ? `<div class="group-range">${escapeHtml(rangeText)}</div>` : ""}
        ${tagCounts ? `<div class="study-tags">${tagCounts}</div>` : ""}
        <div class="group-actions">
          ${workHref ? `<a href="${escapeHtml(workHref)}">Open work</a>` : ""}
          <a href="${escapeHtml(notesHref)}">Manage notes</a>
        </div>
        ${group.notes.map(renderNote).join("")}
      </section>`;
    }).join("")
    : renderEmptyStudy();
}

resultsEl.addEventListener("click", (event) => {
  const emptyAction = event.target.closest("[data-empty-action]");
  if (!emptyAction) return;
  if (emptyAction.dataset.emptyAction === "clear-filters") {
    clearStudyFilters();
  }
});

async function loadCorpora() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) return;
    const payload = await response.json();
    const current = corpusSelect.value || requestedCorpusId;
    corpusSelect.innerHTML = `<option value="">All</option>` + (payload.corpora || [])
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title)}</option>`)
      .join("");
    corpusSelect.value = current;
  } catch {
    // The hard-coded All option remains usable without archive metadata.
  }
}

async function loadStudy() {
  const requestId = activeStudyRequest + 1;
  activeStudyRequest = requestId;
  if (activeStudyController) {
    activeStudyController.abort();
    activeStudyController = null;
  }
  updateUrl();
  updateLinks();
  const controller = new AbortController();
  activeStudyController = controller;
  renderStudyPending();
  try {
    const response = await fetch(`/api/study?${currentParams("json")}`, { signal: controller.signal });
    if (requestId !== activeStudyRequest) return;
    if (!response.ok) {
      statusEl.textContent = "Could not load reviewed notes.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    renderStudy(payload);
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeStudyRequest) {
      statusEl.textContent = "Could not load reviewed notes.";
      resultsEl.innerHTML = "";
    }
  } finally {
    if (requestId === activeStudyRequest) {
      activeStudyController = null;
      setStudyBusy(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadStudy();
});

if (studyClear) {
  studyClear.addEventListener("click", clearStudyFilters);
}

if (activeFiltersEl) {
  activeFiltersEl.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    removeStudyFilter(button.dataset.filter || "");
  });
}

for (const field of [queryInput, corpusSelect, workInput, tagInput]) {
  field.addEventListener("change", loadStudy);
}

for (const field of [queryInput, workInput, tagInput]) {
  field.addEventListener("input", updateStudyClearState);
}

corpusSelect.addEventListener("change", updateStudyClearState);

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
workInput.value = initialParams.get("work_id") || "";
tagInput.value = initialParams.get("tag") || "";
requestedCorpusId = initialParams.get("corpus_id") || "";
corpusSelect.value = requestedCorpusId;

updateStudyClearState();
loadCorpora().then(loadStudy);
