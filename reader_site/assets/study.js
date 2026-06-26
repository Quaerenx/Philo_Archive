const form = document.getElementById("studyForm");
const queryInput = document.getElementById("studyQuery");
const corpusSelect = document.getElementById("studyCorpus");
const workInput = document.getElementById("studyWork");
const tagInput = document.getElementById("studyTag");
const studySubmit = document.getElementById("studySubmit");
const studyClear = document.getElementById("studyClear");
const activeFiltersEl = document.getElementById("studyActiveFilters");
const studyOverview = document.getElementById("studyOverview");
const statusEl = document.getElementById("studyStatus");
const resultsEl = document.getElementById("studyResults");
const exportTools = document.getElementById("studyExportTools");
const exportMarkdown = document.getElementById("studyExportMarkdown");
let requestedCorpusId = "";
let activeStudyController = null;
let activeStudyRequest = 0;
let archiveCorpora = [];

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

function archiveCorpusById(corpusId) {
  const id = cleanText(corpusId || "");
  return archiveCorpora.find((corpus) => corpus.id === id) || null;
}

function corpusDisplayName(corpusId) {
  const corpus = archiveCorpusById(corpusId);
  return cleanText(corpus?.title || corpusId || "");
}

function workDisplayName(corpusId, workId) {
  const id = cleanText(workId || "");
  if (!id) return "";
  const corpus = archiveCorpusById(corpusId);
  for (const section of corpus?.sections || []) {
    const match = (section.links || []).find((link) => cleanText(link.work_id || "") === id);
    if (match) {
      return cleanText(match.label || id);
    }
  }
  return id;
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
}

function translationSummaryParams() {
  const params = new URLSearchParams();
  const corpusId = corpusSelect.value;
  const workId = workInput.value.trim();
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  return params;
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
  if (query) chips.push(renderFilterChip("query", "Text", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  if (workId) chips.push(renderFilterChip("work", "Work", workId));
  if (tag) chips.push(renderFilterChip("tag", "Tag", tag));
  activeFiltersEl.hidden = chips.length === 0;
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

function updateStudyListChrome(count = 0) {
  const showTools = count > 0 || hasActiveFilters();
  form.hidden = !showTools;
  if (activeFiltersEl) {
    activeFiltersEl.hidden = !hasActiveFilters();
  }
}

function renderEmptyStudy() {
  const filtered = hasActiveFilters();
  const title = filtered ? "No saved notes match these filters." : "No saved notes yet.";
  const body = filtered ? "Clear filters, or edit the saved notes list." : "";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">Clear filters</button>'
    : "";
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      <a href="/notes?review_state=raw">Working notes</a>
      <a href="/search">Find work</a>
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
  queryInput.focus();
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
  statusEl.textContent = "";
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

function renderNoteFooter(meta, actions) {
  const cleanMeta = cleanText(meta || "");
  if (!cleanMeta && !actions) return "";
  return `<footer class="note-footer">
    ${cleanMeta ? `<div class="note-meta">${escapeHtml(cleanMeta)}</div>` : "<div></div>"}
    ${actions ? `<div class="note-actions">${actions}</div>` : ""}
  </footer>`;
}

function renderNote(note) {
  const target = note.target_label || note.target_id || "Target";
  const tags = (note.tags || []).join(", ");
  const quote = note.quote ? `<blockquote class="note-quote">${escapeHtml(cleanText(note.quote))}</blockquote>` : "";
  const targetLink = note.url
    ? `<a href="${escapeHtml(note.url)}">${escapeHtml(target)}</a>`
    : escapeHtml(target);
  const missingTarget = note.url ? "" : "Target URL missing";
  const manageHref = noteManageHref(note);
  const meta = [
    tags ? `# ${tags}` : "",
    missingTarget
  ].filter(Boolean).join(" / ");
  const actions = `<a href="${escapeHtml(manageHref)}">Edit</a>`;
  return `<article class="study-note">
    <div class="note-title">
      ${targetLink}
    </div>
    <p class="note-text">${escapeHtml(cleanText(note.note))}</p>
    ${quote}
    ${renderNoteFooter(meta, actions)}
  </article>`;
}

function studyCountLabel(count, singular, plural = `${singular}s`) {
  return `${count.toLocaleString()} ${count === 1 ? singular : plural}`;
}

function translationStatusLink(reviewState, label, count) {
  if (!count) return "";
  const params = translationSummaryParams();
  params.set("review_state", reviewState);
  return `<a href="/translations?${params}"><span>${escapeHtml(label)}</span><strong>${Number(count || 0).toLocaleString()}</strong></a>`;
}

function renderStudyOverview(payload, translationSummary) {
  if (!studyOverview) return;
  const noteCount = Number(payload.count || 0);
  const groupCount = Number(payload.group_count || payload.groups?.length || 0);
  const counts = translationSummary?.review_state_counts || {};
  const generated = Number(counts.generated || 0);
  const reviewed = Number(counts.reviewed || 0);
  const rejected = Number(counts.rejected || 0);
  const translationCount = generated + reviewed + rejected;
  const hasOverview = noteCount > 0 || translationCount > 0;
  studyOverview.hidden = !hasOverview;
  if (!hasOverview) {
    studyOverview.innerHTML = "";
    return;
  }
  const notesLabel = groupCount > 1
    ? `${studyCountLabel(noteCount, "saved note")} / ${studyCountLabel(groupCount, "work")}`
    : studyCountLabel(noteCount, "saved note");
  const translationLinks = [
    translationStatusLink("generated", "To check", generated),
    translationStatusLink("reviewed", "Saved translations", reviewed),
    translationStatusLink("rejected", "Rejected", rejected)
  ].filter(Boolean).join("");
  studyOverview.innerHTML = `<div class="study-overview-notes">${escapeHtml(notesLabel)}</div>
    ${translationLinks ? `<nav class="study-overview-translations" aria-label="Translation study status">${translationLinks}</nav>` : ""}`;
}

function studyGroupMeta(group) {
  const noteCount = Number(group.count || group.notes?.length || 0);
  const targetCount = Number(group.target_count || 0);
  const parts = [
    noteCount ? studyCountLabel(noteCount, "saved note") : "",
    targetCount > 1 ? studyCountLabel(targetCount, "passage") : ""
  ].filter(Boolean);
  return parts.join(" / ");
}

function renderStudy(payload, translationSummary = null) {
  const groups = payload.groups || [];
  const count = payload.count || 0;
  updateStudyListChrome(count);
  renderStudyOverview(payload, translationSummary);
  if (exportTools) {
    exportTools.hidden = count === 0;
    if (count === 0) exportTools.open = false;
  }
  statusEl.textContent = "";
  resultsEl.innerHTML = groups.length
    ? groups.map((group) => {
      const title = workDisplayName(group.corpus_id, group.work_id) || corpusDisplayName(group.corpus_id) || "Saved notes";
      const context = group.work_id ? corpusDisplayName(group.corpus_id) : "";
      const workHref = group.corpus_id && group.work_id ? `/work/${encodeURIComponent(group.corpus_id)}/${encodeURIComponent(group.work_id)}` : "";
      const notesHref = `/notes?corpus_id=${encodeURIComponent(group.corpus_id)}&work_id=${encodeURIComponent(group.work_id)}&review_state=reviewed`;
      const tagCounts = (group.tag_counts || [])
        .map((item) => `<span class="study-tag">${escapeHtml(item.tag)} <span>${Number(item.count || 0).toLocaleString()}</span></span>`)
        .join("");
      const tagsPanel = tagCounts
        ? `<details class="study-tags-panel"><summary>Tags</summary><div class="study-tags">${tagCounts}</div></details>`
        : "";
      return `<section class="study-group">
        <h2>${escapeHtml(title)}</h2>
        ${context ? `<div class="study-group-context">${escapeHtml(context)}</div>` : ""}
        <div class="group-meta">${escapeHtml(studyGroupMeta(group))}</div>
        ${tagsPanel}
        ${group.notes.map(renderNote).join("")}
        <div class="group-actions">
          ${workHref ? `<a href="${escapeHtml(workHref)}">Read</a>` : ""}
          <a href="${escapeHtml(notesHref)}">Notes</a>
        </div>
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
    archiveCorpora = payload.corpora || [];
    const current = corpusSelect.value || requestedCorpusId;
    corpusSelect.innerHTML = `<option value="">All</option>` + archiveCorpora
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
      statusEl.textContent = "Could not load saved notes.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    let translationSummary = null;
    try {
      const summaryResponse = await fetch(`/api/sentence-translations/summary?${translationSummaryParams()}`, { signal: controller.signal });
      if (summaryResponse.ok) {
        translationSummary = await summaryResponse.json();
      }
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
    if (requestId !== activeStudyRequest) return;
    renderStudy(payload, translationSummary);
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeStudyRequest) {
      statusEl.textContent = "Could not load saved notes.";
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
