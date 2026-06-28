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
const pageTitleEl = document.getElementById("translationsPageTitle");
let lastRecords = [];
let activeController = null;
let activeRequest = 0;
let recentlyChangedRecordId = "";
let archiveCorpora = [];
let pendingReviewQueueFocus = false;
let pendingReviewQueueMessage = "";

const DEFAULT_CORPUS = "";
const LAST_CORPUS_STORAGE_KEY = "philoArchive.lastCorpusId";
const PAGE_TITLE_SUFFIX = "Personal Archive of Literature";
const REVIEW_LABELS = {
  all: "전체",
  generated: "검토할 번역",
  reviewed: "저장한 번역",
  rejected: "제외한 번역"
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

function compactWorkMeta(meta) {
  return cleanText(meta).replace(/\s*·\s*\d[\d,]*\s+(verses?|segments?|files?|works?)\b.*$/i, "");
}

function workDisplayName(corpusId, workId) {
  const id = cleanText(workId || "");
  if (!id) return "";
  const corpus = archiveCorpusById(corpusId);
  for (const section of corpus?.sections || []) {
    const match = (section.links || []).find((link) => cleanText(link.work_id || "") === id);
    if (match) {
      const label = cleanText(match.label || id);
      const meta = compactWorkMeta(match.meta || "");
      return meta ? `${label} / ${meta}` : label;
    }
  }
  return id;
}

function sentenceDisplayName(record) {
  const id = cleanText(record.sentence_id || record.target_id || "");
  const bibleMatch = /^([A-Za-z0-9]+)\.(\d+)\.(\d+)\.s(\d+)$/i.exec(id);
  if (bibleMatch) {
    const sentenceNumber = Number(bibleMatch[4]);
    const suffix = sentenceNumber > 1 ? `, 문장 ${sentenceNumber}` : "";
    return `${bibleMatch[1]} ${Number(bibleMatch[2])}:${Number(bibleMatch[3])}${suffix}`;
  }
  const match = /^p-(\d+)\.s(\d+)$/i.exec(id);
  if (match) {
    return `문단 ${Number(match[1])}, 문장 ${Number(match[2])}`;
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
    ? (options.length ? "문서 선택" : "문서 직접 입력")
    : "자료 선택 후 문서 선택";
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

function currentPageHeading() {
  const reviewState = reviewSelect.value || "all";
  if (reviewState === "generated" && !hasSearchFilters()) return "검토할 번역";
  if (reviewState === "reviewed" && !hasSearchFilters()) return "저장한 번역";
  if (reviewState === "rejected" && !hasSearchFilters()) return "제외한 번역";
  if (hasActiveFilters()) return "번역 찾기";
  return "번역 목록";
}

function updatePageHeading() {
  const heading = currentPageHeading();
  if (pageTitleEl) {
    pageTitleEl.textContent = heading;
  }
  document.title = `${heading} / ${PAGE_TITLE_SUFFIX}`;
}

function isReviewQueueOnlyView() {
  return (reviewSelect.value || "all") === "generated" &&
    !hasSearchFilters() &&
    generatedRecords(lastRecords).length > 0;
}

function isReviewedOnlyView() {
  return (reviewSelect.value || "all") === "reviewed" &&
    !hasSearchFilters();
}

function renderFilterChip(filterName, label, value) {
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="${escapeHtml(label)} 조건 제거">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">x</span>
  </button>`;
}

function updateFilterSummary() {
  if (!activeFiltersEl) return;
  const chips = [];
  const query = queryInput.value.trim();
  const workId = workInput.value.trim();
  if (query) chips.push(renderFilterChip("query", "본문", query));
  if (corpusSelect.value) {
    chips.push(renderFilterChip("corpus", "자료", selectedOptionText(corpusSelect)));
  }
  if (workId) chips.push(renderFilterChip("work", "문서", workId));
  if (reviewSelect.value !== "all" && hasSearchFilters()) {
    chips.push(renderFilterChip("review", "상태", selectedOptionText(reviewSelect)));
  }
  activeFiltersEl.hidden = chips.length === 0;
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">조건</span>${chips.join("")}`
    : "";
}

function updateClearState(isBusy = form.classList.contains("is-loading")) {
  clearButton.disabled = isBusy || !hasActiveFilters();
  updateFilterSummary();
}

function updateTranslationsListChrome(count = lastRecords.length) {
  const activeFilters = hasActiveFilters();
  const shouldOpenTools = hasSearchFilters();
  const inReviewQueue = isReviewQueueOnlyView();
  const showTools = !inReviewQueue && (count > 0 || activeFilters);
  if (listTools) {
    listTools.hidden = !showTools;
    listTools.open = shouldOpenTools;
  }
  form.hidden = !showTools;
  updateFilterSummary();
}

function updateUrl() {
  const params = urlParams();
  history.replaceState(null, "", params.toString() ? `/translations?${params}` : "/translations");
  updatePageHeading();
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
  reviewQueueButton.hidden = generatedCount === 0 || isReviewQueueOnlyView();
  reviewQueueButton.textContent = "검토할 번역";
  reviewQueueButton.disabled = form.classList.contains("is-loading") || generatedCount === 0;
  reviewQueueButton.title = generatedCount
    ? `${generatedCount.toLocaleString()}개 검토 대기`
    : "검토할 번역 없음";
  reviewQueueButton.setAttribute(
    "aria-label",
    generatedCount ? `검토할 번역 ${generatedCount.toLocaleString()}개로 이동` : "검토할 번역 없음"
  );
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

function visibleSummaryStates(counts) {
  return ["generated", "reviewed", "rejected"].filter((state) => counts[state] > 0);
}

function summaryButton(filter, label, count) {
  const selected = (filter || "all") === (reviewSelect.value || "all");
  const detail = `${label} ${Number(count || 0).toLocaleString()}개`;
  return `<button type="button" class="${selected ? "active" : ""}" data-translation-summary-filter="${escapeHtml(filter)}" aria-pressed="${selected ? "true" : "false"}" aria-label="${escapeHtml(detail)}" title="${escapeHtml(detail)}">
    <span>${escapeHtml(label)}</span>
  </button>`;
}

function renderSummary(records) {
  const counts = summaryCounts(records);
  if (counts.total <= 0) return "";
  if (visibleSummaryStates(counts).length <= 1) return "";
  const buttons = [
    summaryButton("all", "전체", counts.total),
    counts.generated ? summaryButton("generated", "검토 대기", counts.generated) : "",
    counts.reviewed ? summaryButton("reviewed", "저장한 번역", counts.reviewed) : "",
    counts.rejected ? summaryButton("rejected", "제외한 번역", counts.rejected) : ""
  ].filter(Boolean).join("");
  return `<nav class="translation-record-summary-tools translation-record-summary" aria-label="번역 상태 요약">
    ${buttons}
  </nav>`;
}

function renderEmptyRecords() {
  const filtered = hasActiveFilters();
  const statusOnly = (reviewSelect.value || "all") !== "all" && !hasSearchFilters();
  const title = statusOnly
    ? `${selectedOptionText(reviewSelect)}이 없습니다.`
    : (filtered ? "조건에 맞는 번역이 없습니다." : "아직 번역이 없습니다.");
  const body = filtered && !statusOnly
    ? "조건을 지우거나 문서와 상태 범위를 넓혀보세요."
    : "";
  const clearAction = filtered
    ? `<button type="button" data-empty-action="clear-filters">${statusOnly ? "전체 번역" : "조건 지우기"}</button>`
    : "";
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      <a href="/">읽기 시작</a>
    </div>
  </section>`;
}

function recordTitle(record) {
  return cleanText(record.target_label || sentenceDisplayName(record) || record.work_id || "번역");
}

function recordContext(record) {
  const hasWork = Boolean(cleanText(record.work_id || ""));
  return [
    corpusDisplayName(record.corpus_id),
    hasWork ? workDisplayName(record.corpus_id, record.work_id) : ""
  ].filter(Boolean).join(" / ");
}

function recordGroupKey(record) {
  return [
    cleanText(record.corpus_id || ""),
    cleanText(record.work_id || "")
  ].join("\u001f");
}

function groupedTranslationRecords(records) {
  const groups = [];
  const indexes = new Map();
  for (const record of records) {
    const key = recordGroupKey(record);
    let group = indexes.get(key);
    if (!group) {
      group = {
        key,
        corpusId: cleanText(record.corpus_id || ""),
        workId: cleanText(record.work_id || ""),
        label: recordContext(record) || corpusDisplayName(record.corpus_id) || "번역",
        records: [],
        reviewedCount: 0
      };
      indexes.set(key, group);
      groups.push(group);
    }
    if (normalizedReviewState(record) === "reviewed") {
      group.reviewedCount += 1;
    }
    group.records.push(record);
  }
  return groups;
}

function groupWorkUrl(group) {
  if (!group.corpusId || !group.workId) return "";
  return `/work/${encodeURIComponent(group.corpusId)}/${encodeURIComponent(group.workId)}`;
}

function groupSavedExportUrl(group) {
  if (!group.corpusId || !group.reviewedCount) return "";
  const params = new URLSearchParams({
    format: "markdown",
    review_state: "reviewed",
    corpus_id: group.corpusId
  });
  if (group.workId) params.set("work_id", group.workId);
  return `/api/sentence-translations/export?${params}`;
}

function renderGroupActions(group) {
  const workUrl = groupWorkUrl(group);
  const savedExportUrl = groupSavedExportUrl(group);
  const workTitle = cleanText(group.title || group.workId || "원문");
  const readLabel = `원문 읽기: ${workTitle}`;
  const actions = [
    workUrl ? `<a href="${escapeHtml(workUrl)}" aria-label="${escapeHtml(readLabel)}" title="${escapeHtml(readLabel)}">원문 읽기</a>` : "",
    savedExportUrl ? `<a href="${escapeHtml(savedExportUrl)}">저장본</a>` : ""
  ].filter(Boolean).join("");
  return actions ? `<span class="translation-record-group-actions">${actions}</span>` : "";
}

function visibleReviewStates(records) {
  return new Set(records.map(normalizedReviewState));
}

function renderRecord(record, options) {
  options = options || {};
  const reviewState = normalizedReviewState(record);
  const title = recordTitle(record) || "번역";
  const context = recordContext(record);
  const source = cleanText(record.source_text_excerpt || "");
  const translation = cleanText(record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const targetUrl = cleanText(record.target_url || "");
  const isRecent = record.id === recentlyChangedRecordId;
  const reviewLabel = REVIEW_LABELS[reviewState] || reviewState;
  const showReviewBadge = options.showReviewBadge !== false;
  const showReviewActions = options.showReviewActions === true;
  const showContext = options.showContext !== false;
  const showSourceDetail = options.showSourceDetail === true;
  const openCommentary = options.openCommentary === true;
  const reviewKicker = showReviewBadge
    ? `<div class="translation-record-kicker">
        <span class="review-badge" aria-label="검토 상태: ${escapeHtml(reviewLabel)}">${escapeHtml(reviewLabel)}</span>
      </div>`
    : "";
  const resetAction = reviewState !== "generated"
    ? '<button type="button" data-review-state="generated" aria-keyshortcuts="G" title="검토할 번역으로 되돌리기" aria-label="검토할 번역으로 되돌리기">검토로 되돌리기</button>'
    : "";
  const rejectAction = reviewState !== "rejected"
    ? `<details class="translation-danger-actions">
        <summary>제외</summary>
        <button type="button" data-review-state="rejected" aria-keyshortcuts="X" title="이 번역 제외하기" aria-label="이 번역 제외하기">제외하기</button>
      </details>`
    : "";
  const moreActions = [resetAction, rejectAction].filter(Boolean).join("");
  const moreAction = moreActions
    ? `<details class="translation-more-actions">
        <summary>더보기</summary>
        <div class="translation-more-actions-body">
          ${moreActions}
        </div>
      </details>`
    : "";
  const sourceAction = targetUrl
    ? `<a href="${escapeHtml(targetUrl)}" data-open-source aria-keyshortcuts="O" title="원문으로 이동" aria-label="원문 읽기: ${escapeHtml(title)}">원문 읽기</a>`
    : "";
  const actions = showReviewActions ? [
    reviewState !== "reviewed"
      ? '<button type="button" class="primary-review-action" data-review-state="reviewed" aria-keyshortcuts="R" title="저장한 번역으로 표시" aria-label="저장한 번역으로 표시">저장</button>'
      : "",
    sourceAction,
    moreAction
  ].filter(Boolean).join("") : "";
  return `<article class="translation-record-card${isRecent ? " is-recent" : ""}" tabindex="-1" data-record-id="${escapeHtml(record.id)}" data-corpus-id="${escapeHtml(record.corpus_id)}" data-review-state="${escapeHtml(reviewState)}">
    <header class="translation-record-heading">
      <h2 class="translation-record-title">${targetUrl ? `<a href="${escapeHtml(targetUrl)}" data-open-source aria-keyshortcuts="O" title="원문으로 이동">${escapeHtml(title)}</a>` : escapeHtml(title)}</h2>
      ${reviewKicker}
      ${showContext && context ? `<div class="translation-record-context">${escapeHtml(context)}</div>` : ""}
    </header>
    ${translation ? `<p class="translation-text">${escapeHtml(translation)}</p>` : ""}
    ${commentary ? `<details class="translation-commentary"${openCommentary ? " open" : ""} aria-label="해설"><summary>해설</summary><p>${escapeHtml(commentary)}</p></details>` : ""}
    ${source && showSourceDetail ? `<details class="translation-source"><summary>선택 문장</summary><blockquote>${escapeHtml(source)}</blockquote></details>` : ""}
    ${actions ? `<footer class="translation-record-footer">
      <div class="translation-actions">
        ${actions}
      </div>
    </footer>` : ""}
  </article>`;
}

function renderRecordGroups(records, options) {
  options = options || {};
  const showGroupActions = options.showGroupActions !== false;
  return groupedTranslationRecords(records).map((group, groupIndex) => `
    <section class="translation-record-group" data-translation-record-group="${groupIndex + 1}">
      <div class="translation-record-group-title">
        <span>${escapeHtml(group.label)}</span>
        ${showGroupActions ? renderGroupActions(group) : ""}
      </div>
      ${group.records.map((record, recordIndex) => renderRecord(record, {
        ...options,
        showContext: false,
        openCommentary: options.openFirstCommentary === true && groupIndex === 0 && recordIndex === 0
      })).join("")}
    </section>`).join("");
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
  const showReviewBadges = reviewActionsVisible() && visibleReviewStates(visible).size > 1;
  const showReviewActions = reviewActionsVisible();
  const inReviewQueue = isReviewQueueOnlyView();
  const inSavedReading = isReviewedOnlyView();
  statusEl.textContent = "";
  resultsEl.innerHTML = queryMatched.length
    ? renderSummary(queryMatched) + (visible.length ? renderRecordGroups(visible, { showReviewBadge: showReviewBadges, showReviewActions, showGroupActions: !inReviewQueue, showSourceDetail: showReviewActions, openFirstCommentary: inReviewQueue || inSavedReading }) : renderEmptyRecords())
    : renderEmptyRecords();
  if (pendingReviewQueueFocus) {
    const reviewMessage = pendingReviewQueueMessage;
    pendingReviewQueueFocus = false;
    pendingReviewQueueMessage = "";
    if (focusFirstReviewQueueRecord()) {
      statusEl.textContent = reviewMessage || "";
    } else if (reviewSelect.value === "generated") {
      statusEl.textContent = reviewMessage ? "모든 번역을 검토했습니다." : "검토할 번역이 없습니다.";
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
    statusEl.textContent = "검토할 번역이 없습니다.";
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

function reviewActionMessage(reviewState) {
  if (reviewState === "reviewed") return "저장한 번역으로 표시했습니다.";
  if (reviewState === "rejected") return "제외한 번역으로 옮겼습니다.";
  if (reviewState === "generated") return "검토할 번역으로 되돌렸습니다.";
  return "반영했습니다.";
}

async function loadCorpora() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) return;
    const payload = await response.json();
    archiveCorpora = payload.corpora || [];
    const current = corpusSelect.value || DEFAULT_CORPUS;
    corpusSelect.innerHTML = '<option value="">전체 자료</option>' + archiveCorpora
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title || corpus.id)}</option>`)
      .join("");
    const hasCurrent = Array.from(corpusSelect.options).some((option) => option.value === current);
    if (!hasCurrent) {
      const fallback = document.createElement("option");
      fallback.value = current;
      fallback.textContent = current || "전체 자료";
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
  rememberCorpusId(corpusSelect.value);
  updateUrl();
  updateExportLinks();
  const controller = new AbortController();
  activeController = controller;
  renderPending();
  try {
    const response = await fetch(`/api/sentence-translations/export?${fetchParams("json")}`, { signal: controller.signal });
    if (requestId !== activeRequest) return;
    if (!response.ok) {
      statusEl.textContent = "번역을 불러오지 못했습니다.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    renderRecords(payload.records || []);
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (requestId === activeRequest) {
      statusEl.textContent = "번역을 불러오지 못했습니다.";
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
    const actionMessage = reviewActionMessage(nextState);
    if (ok) {
      recentlyChangedRecordId = recordId;
      pendingReviewQueueFocus = reviewSelect.value === "generated" && nextState !== "generated";
      pendingReviewQueueMessage = pendingReviewQueueFocus ? actionMessage : "";
    }
    statusEl.textContent = ok ? actionMessage : "변경하지 못했습니다.";
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
corpusSelect.value = initialParams.get("corpus_id") || (location.search ? DEFAULT_CORPUS : rememberedCorpusId());
workInput.value = initialParams.get("work_id") || "";
reviewSelect.value = initialParams.get("review_state") || "all";

updateClearState();
loadCorpora().then(loadRecords);
