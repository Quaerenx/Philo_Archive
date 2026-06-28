const form = document.getElementById("studyForm");
const listTools = document.getElementById("studyListTools");
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
const exportTranslations = document.getElementById("studyExportTranslations");
let requestedCorpusId = "";
let activeStudyController = null;
let activeStudyRequest = 0;
let archiveCorpora = [];

const LAST_CORPUS_STORAGE_KEY = "philoArchive.lastCorpusId";

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

function rememberedCorpusId() {
  try {
    return cleanText(window.localStorage.getItem(LAST_CORPUS_STORAGE_KEY) || "");
  } catch {
    return "";
  }
}

function rememberCorpusId(corpusId) {
  try {
    const id = cleanText(corpusId || "");
    if (id) {
      window.localStorage.setItem(LAST_CORPUS_STORAGE_KEY, id);
    } else {
      window.localStorage.removeItem(LAST_CORPUS_STORAGE_KEY);
    }
  } catch {
    // Local storage can be unavailable in restricted browser contexts.
  }
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
  if (exportTranslations) {
    exportTranslations.href = `/api/sentence-translations/export?${translationExportParams("markdown")}`;
  }
}

function translationSummaryParams() {
  const params = new URLSearchParams();
  const corpusId = corpusSelect.value;
  const workId = workInput.value.trim();
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  return params;
}

function translationExportParams(format = "markdown") {
  const params = new URLSearchParams({
    format,
    review_state: "reviewed"
  });
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  const workId = workInput.value.trim();
  if (query) params.set("q", query);
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
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="${escapeHtml(label)} 조건 제거">
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
  if (query) chips.push(renderFilterChip("query", "본문", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "자료", selectedOptionText(corpusSelect)));
  if (workId) chips.push(renderFilterChip("work", "문서", workId));
  if (tag) chips.push(renderFilterChip("tag", "태그", tag));
  activeFiltersEl.hidden = chips.length === 0;
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">조건</span>${chips.join("")}`
    : "";
}

function updateStudyClearState(isBusy = form.classList.contains("is-loading")) {
  if (!studyClear) return;
  studyClear.disabled = isBusy || !hasActiveFilters();
  updateStudyFilterSummary();
}

function updateStudyListChrome(count = 0) {
  const activeFilters = hasActiveFilters();
  const showTools = count > 0 || activeFilters;
  if (listTools) {
    listTools.hidden = !showTools;
    listTools.open = activeFilters;
  }
  form.hidden = !showTools;
  if (activeFiltersEl) {
    activeFiltersEl.hidden = !activeFilters;
  }
}

function studyTranslationHref(reviewState) {
  const params = translationSummaryParams();
  params.set("review_state", reviewState);
  return `/translations?${params}`;
}

function emptyTranslationAction(href, label, accessibleLabel) {
  return `<a class="empty-primary-action" href="${escapeHtml(href)}" aria-label="${escapeHtml(accessibleLabel)}" title="${escapeHtml(accessibleLabel)}">${escapeHtml(label)}</a>`;
}

function renderEmptyStudy(translationSummary = null) {
  const filtered = hasActiveFilters();
  const counts = translationSummary?.review_state_counts || {};
  const generated = Number(counts.generated || 0);
  const reviewed = Number(counts.reviewed || 0);
  const title = filtered
    ? "조건에 맞는 학습 기록이 없습니다."
    : (generated > 0
      ? "검토할 번역이 있습니다."
      : (reviewed > 0 ? "저장한 번역이 있습니다." : "아직 저장한 학습 기록이 없습니다."));
  const body = filtered ? "조건을 지우거나 범위를 넓혀보세요." : "";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">조건 지우기</button>'
    : "";
  const translationAction = generated > 0
    ? emptyTranslationAction(studyTranslationHref("generated"), "검토하기", `검토할 번역 ${generated.toLocaleString()}개로 이동`)
    : (reviewed > 0 ? emptyTranslationAction(studyTranslationHref("reviewed"), "번역 보기", `저장한 번역 ${reviewed.toLocaleString()}개 보기`) : "");
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      ${translationAction}
      <a href="/">읽기 시작</a>
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

function studyGroupTitle(group) {
  return workDisplayName(group.corpus_id, group.work_id) || corpusDisplayName(group.corpus_id) || "저장한 노트";
}

function studyGroupWorkHref(group) {
  return group.corpus_id && group.work_id ? `/work/${encodeURIComponent(group.corpus_id)}/${encodeURIComponent(group.work_id)}` : "";
}

function renderNote(note) {
  const target = note.target_label || note.target_id || "대상";
  const tags = (note.tags || []).join(", ");
  const quote = note.quote ? `<blockquote class="note-quote">${escapeHtml(cleanText(note.quote))}</blockquote>` : "";
  const targetLink = note.url
    ? `<a href="${escapeHtml(note.url)}">${escapeHtml(target)}</a>`
    : escapeHtml(target);
  const missingTarget = note.url ? "" : "원문 위치 없음";
  const manageHref = noteManageHref(note);
  const meta = [
    tags ? `# ${tags}` : "",
    missingTarget
  ].filter(Boolean).join(" / ");
  const sourceLabel = `원문 읽기: ${cleanText(target)}`;
  const sourceAction = note.url
    ? `<a href="${escapeHtml(note.url)}" aria-label="${escapeHtml(sourceLabel)}" title="${escapeHtml(sourceLabel)}">원문 읽기</a>`
    : "";
  const editLabel = `노트 수정: ${cleanText(target)}`;
  const actions = `${sourceAction}<a href="${escapeHtml(manageHref)}" aria-label="${escapeHtml(editLabel)}" title="${escapeHtml(editLabel)}">노트 수정</a>`;
  return `<article class="study-note">
    <div class="note-title">
      ${targetLink}
    </div>
    <p class="note-text">${escapeHtml(cleanText(note.note))}</p>
    ${quote}
    ${renderNoteFooter(meta, actions)}
  </article>`;
}

function studyCountLabel(count, label) {
  return `${label} ${count.toLocaleString()}개`;
}

function continueStudyLink(payload) {
  const group = (payload.groups || []).find(studyGroupWorkHref);
  if (!group) return "";
  const title = studyGroupTitle(group);
  const href = studyGroupWorkHref(group);
  const label = `이어 읽기: ${title}`;
  return `<a class="study-overview-primary" href="${escapeHtml(href)}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">이어 읽기</a>`;
}

function translationStatusLink(reviewState, label, count, accessibleLabel) {
  if (!count) return "";
  const detail = accessibleLabel || `${label} ${Number(count || 0).toLocaleString()}개`;
  return `<a href="${escapeHtml(studyTranslationHref(reviewState))}" aria-label="${escapeHtml(detail)}" title="${escapeHtml(detail)}">${escapeHtml(label)}</a>`;
}

function renderStudyOverview(payload, translationSummary) {
  if (!studyOverview) return;
  const noteCount = Number(payload.count || 0);
  const groupCount = Number(payload.group_count || payload.groups?.length || 0);
  const counts = translationSummary?.review_state_counts || {};
  const generated = Number(counts.generated || 0);
  const reviewed = Number(counts.reviewed || 0);
  const hasOverview = noteCount > 0;
  studyOverview.hidden = !hasOverview;
  if (!hasOverview) {
    studyOverview.innerHTML = "";
    return;
  }
  const notesLabel = noteCount > 0
    ? (groupCount > 1
      ? `${studyCountLabel(noteCount, "저장한 노트")} / ${studyCountLabel(groupCount, "문서")}`
      : studyCountLabel(noteCount, "저장한 노트"))
    : "";
  const notesMarkup = notesLabel
    ? `<div class="study-overview-notes">${escapeHtml(notesLabel)}</div>`
    : "";
  const continueMarkup = continueStudyLink(payload);
  const translationLinks = [
    translationStatusLink("generated", "검토할 번역", generated, `검토할 번역 ${generated.toLocaleString()}개로 이동`),
    translationStatusLink("reviewed", "저장한 번역", reviewed, `저장한 번역 ${reviewed.toLocaleString()}개 보기`)
  ].filter(Boolean).join("");
  studyOverview.innerHTML = `${continueMarkup}${notesMarkup}
    ${translationLinks ? `<nav class="study-overview-translations" aria-label="번역 학습 상태">${translationLinks}</nav>` : ""}`;
}

function studyGroupMeta(group) {
  const noteCount = Number(group.count || group.notes?.length || 0);
  const targetCount = Number(group.target_count || 0);
  const parts = [
    noteCount ? studyCountLabel(noteCount, "저장한 노트") : "",
    targetCount > 1 ? studyCountLabel(targetCount, "대상") : ""
  ].filter(Boolean);
  return parts.join(" / ");
}

function renderStudy(payload, translationSummary = null) {
  const groups = payload.groups || [];
  const count = payload.count || 0;
  const translationCounts = translationSummary?.review_state_counts || {};
  const reviewedTranslationCount = Number(translationCounts.reviewed || 0);
  updateStudyListChrome(count);
  renderStudyOverview(payload, translationSummary);
  if (exportTools) {
    exportTools.hidden = count === 0 && reviewedTranslationCount === 0;
    if (exportTools.hidden) exportTools.open = false;
  }
  if (exportTranslations) {
    exportTranslations.hidden = reviewedTranslationCount === 0;
  }
  statusEl.textContent = "";
  resultsEl.innerHTML = groups.length
    ? groups.map((group) => {
      const title = studyGroupTitle(group);
      const context = group.work_id ? corpusDisplayName(group.corpus_id) : "";
      const workHref = studyGroupWorkHref(group);
      const notesHref = `/notes?corpus_id=${encodeURIComponent(group.corpus_id)}&work_id=${encodeURIComponent(group.work_id)}&review_state=reviewed`;
      const readLabel = `이어 읽기: ${title}`;
      const notesLabel = `노트 보기: ${title}`;
      const tagCounts = (group.tag_counts || [])
        .map((item) => `<span class="study-tag">${escapeHtml(item.tag)} <span>${Number(item.count || 0).toLocaleString()}</span></span>`)
        .join("");
      const tagsPanel = tagCounts
        ? `<details class="study-tags-panel"><summary>태그</summary><div class="study-tags">${tagCounts}</div></details>`
        : "";
      return `<section class="study-group">
        <h2>${escapeHtml(title)}</h2>
        ${context ? `<div class="study-group-context">${escapeHtml(context)}</div>` : ""}
        <div class="group-meta">${escapeHtml(studyGroupMeta(group))}</div>
        ${tagsPanel}
        ${group.notes.map(renderNote).join("")}
        <div class="group-actions">
          ${workHref ? `<a href="${escapeHtml(workHref)}" aria-label="${escapeHtml(readLabel)}" title="${escapeHtml(readLabel)}">이어 읽기</a>` : ""}
          <a href="${escapeHtml(notesHref)}" aria-label="${escapeHtml(notesLabel)}" title="${escapeHtml(notesLabel)}">노트 보기</a>
        </div>
      </section>`;
    }).join("")
    : renderEmptyStudy(translationSummary);
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
    corpusSelect.innerHTML = `<option value="">전체</option>` + archiveCorpora
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title)}</option>`)
      .join("");
    corpusSelect.value = current;
  } catch {
    // The hard-coded fallback option remains usable without archive metadata.
  }
}

async function loadStudy() {
  const requestId = activeStudyRequest + 1;
  activeStudyRequest = requestId;
  if (activeStudyController) {
    activeStudyController.abort();
    activeStudyController = null;
  }
  rememberCorpusId(corpusSelect.value || requestedCorpusId);
  updateUrl();
  updateLinks();
  const controller = new AbortController();
  activeStudyController = controller;
  renderStudyPending();
  try {
    const response = await fetch(`/api/study?${currentParams("json")}`, { signal: controller.signal });
    if (requestId !== activeStudyRequest) return;
    if (!response.ok) {
      statusEl.textContent = "학습 기록을 불러오지 못했습니다.";
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
      statusEl.textContent = "학습 기록을 불러오지 못했습니다.";
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
if (!requestedCorpusId && !location.search) {
  requestedCorpusId = rememberedCorpusId();
}
corpusSelect.value = requestedCorpusId;

updateStudyClearState();
loadCorpora().then(loadStudy);
