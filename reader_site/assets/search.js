const form = document.getElementById("searchForm");
const queryInput = document.getElementById("queryInput");
const corpusSelect = document.getElementById("corpusSelect");
const workSelect = document.getElementById("workSelect");
const variantSelect = document.getElementById("variantSelect");
const searchSubmit = document.getElementById("searchSubmit");
const searchClear = document.getElementById("searchClear");
const activeFiltersEl = document.getElementById("searchActiveFilters");
const statusEl = document.getElementById("searchStatus");
const resultsEl = document.getElementById("results");
const metadataCache = {};
let activeSearchController = null;
let activeSearchRequest = 0;
const metadataEndpoints = {
  nietzsche: "/api/nietzsche/metadata",
  bible: "/api/bible/metadata",
  kierkegaard: "/api/kierkegaard/metadata",
  wittgenstein: "/api/wittgenstein/metadata"
};
const startCorpora = [
  ["nietzsche", "니체"],
  ["bible", "성경"],
  ["kierkegaard", "키르케고르"],
  ["wittgenstein", "비트겐슈타인"]
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function highlight(value, query) {
  let output = escapeHtml(value);
  const terms = String(query || "").trim().split(/\s+/).filter(Boolean);
  for (const term of terms) {
    const safe = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    output = output.replace(new RegExp(`(${safe})`, "gi"), "<mark>$1</mark>");
  }
  return output;
}

function cleanText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function corpusLabel(value) {
  const corpusId = String(value || "");
  const entry = startCorpora.find(([id]) => id === corpusId);
  return entry ? entry[1] : variantLabel(corpusId);
}

function reviewStateLabel(value) {
  const state = String(value || "").toLowerCase();
  if (state === "reviewed") return "저장한 노트";
  if (state === "raw") return "작성 중인 노트";
  if (state === "rejected") return "제외한 번역";
  if (state === "generated") return "검토할 번역";
  return state ? variantLabel(state) : "";
}

function displayMetaLabel(value) {
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

function resultMeta(parts) {
  return parts.map(displayMetaLabel).map(cleanText).filter(Boolean).join(" / ");
}

function resultCorpusMeta(corpusId) {
  return corpusSelect.value ? "" : corpusLabel(corpusId);
}

function updateUrl(query, corpusId, workId, variantId) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (variantId) params.set("variant_id", variantId);
  history.replaceState(null, "", params.toString() ? `/search?${params}` : "/search");
}

function selectedOptionText(select) {
  const option = select.options[select.selectedIndex];
  return option ? option.textContent.trim() : select.value;
}

function renderFilterChip(filterName, label, value) {
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="${escapeHtml(label)} 조건 제거">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">×</span>
  </button>`;
}

function searchHasActiveFilters() {
  return Boolean(
    queryInput.value.trim() ||
    corpusSelect.value ||
    (!workSelect.disabled && workSelect.value) ||
    (!variantSelect.disabled && variantSelect.value)
  );
}

function updateSearchFilterSummary() {
  if (!activeFiltersEl) return;
  const chips = [];
  const query = queryInput.value.trim();
  if (query) chips.push(renderFilterChip("query", "본문", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "자료", selectedOptionText(corpusSelect)));
  if (!workSelect.disabled && workSelect.value) chips.push(renderFilterChip("work", "문서", selectedOptionText(workSelect)));
  if (!variantSelect.disabled && variantSelect.value) chips.push(renderFilterChip("variant", "판본", selectedOptionText(variantSelect)));
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">조건</span>${chips.join("")}`
    : "";
}

function updateSearchClearState(isBusy = form.classList.contains("is-searching")) {
  if (!searchClear) return;
  searchClear.disabled = isBusy || !searchHasActiveFilters();
  updateSearchFilterSummary();
}

function renderEmptySearch(query) {
  const filtered = searchHasActiveFilters();
  const title = query ? "검색 결과가 없습니다." : "검색어를 입력하세요.";
  const body = query
    ? "검색어를 줄이거나 자료 범위를 넓혀보세요."
    : "";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-search">검색 지우기</button>'
    : "";
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      <a href="/">아카이브 보기</a>
    </div>
  </section>`;
}

function renderSearchStart() {
  const links = startCorpora
    .map(([corpusId, label]) => `<a href="/category/${escapeHtml(corpusId)}">${escapeHtml(label)}</a>`)
    .join("");
  return `<section class="search-start" aria-label="자료 선택">
    <h2>읽기 시작</h2>
    <div class="search-start-links">
      ${links}
    </div>
  </section>`;
}

async function clearSearchFilters() {
  activeSearchRequest += 1;
  if (activeSearchController) {
    activeSearchController.abort();
    activeSearchController = null;
  }
  queryInput.value = "";
  corpusSelect.value = "";
  workSelect.value = "";
  variantSelect.value = "";
  await populateFilters();
  updateUrl("", "", "", "");
  statusEl.textContent = "";
  resultsEl.innerHTML = "";
  setSearchBusy(false);
  updateSearchClearState();
  queryInput.focus();
}

function notesHref(result) {
  const params = new URLSearchParams();
  if (result.corpus_id) params.set("corpus_id", result.corpus_id);
  if (result.work_id) params.set("work_id", result.work_id);
  if (result.segment_id) params.set("target_id", result.segment_id);
  return `/notes?${params}`;
}

function resultGroupHeader(label) {
  return `<div class="result-group-header">
    <h2>${escapeHtml(label)}</h2>
  </div>`;
}

function resultReadLabel(title) {
  return `읽기: ${cleanText(title || "본문")}`;
}

function resultSnippet(href, text, query, linkLabel = "") {
  const content = highlight(text || "", query);
  const cleanHref = cleanText(href || "");
  if (!cleanHref) {
    return `<p class="snippet">${content}</p>`;
  }
  const labelAttrs = linkLabel
    ? ` aria-label="${escapeHtml(linkLabel)}" title="${escapeHtml(linkLabel)}"`
    : "";
  return `<a class="snippet snippet-link" href="${escapeHtml(cleanHref)}"${labelAttrs}>${content}</a>`;
}

function resultSummaryNav(groups) {
  if (!Array.isArray(groups) || groups.length < 2) return "";
  const links = groups
    .map((group) => {
      const detail = `${group.label} ${Number(group.count || 0).toLocaleString()}건`;
      return `<a class="result-summary-link" href="#${escapeHtml(group.id)}" aria-label="${escapeHtml(detail)}" title="${escapeHtml(detail)}">
      <span>${escapeHtml(group.label)}</span>
    </a>`;
    })
    .join("");
  return `<nav class="result-summary-nav" aria-label="검색 결과 묶음">${links}</nav>`;
}

function setSearchBusy(isBusy) {
  form.classList.toggle("is-searching", isBusy);
  resultsEl.setAttribute("aria-busy", isBusy ? "true" : "false");
  if (searchSubmit) {
    searchSubmit.disabled = isBusy;
    searchSubmit.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
  updateSearchClearState(isBusy);
}

function resultFooter(meta, actions) {
  const cleanMeta = cleanText(meta || "");
  const cleanActions = cleanText(actions || "");
  const actionsMarkup = !cleanActions
    ? ""
    : `<nav class="result-actions result-actions-inline" aria-label="검색 결과 동작">${actions}</nav>`;
  if (!cleanMeta && !cleanActions) return "";
  return `<footer class="result-footer">
    ${cleanMeta ? `<div class="result-meta">${escapeHtml(cleanMeta)}</div>` : ""}
    ${actionsMarkup}
  </footer>`;
}

function renderSearchPending(query) {
  const label = query ? `"${query}" 검색 중...` : "검색 중...";
  statusEl.textContent = label;
  resultsEl.innerHTML = `
    <article class="result search-skeleton" aria-hidden="true">
      <span class="search-skeleton-line title"></span>
      <span class="search-skeleton-line"></span>
      <span class="search-skeleton-line short"></span>
    </article>
    <article class="result search-skeleton" aria-hidden="true">
      <span class="search-skeleton-line title"></span>
      <span class="search-skeleton-line"></span>
      <span class="search-skeleton-line short"></span>
    </article>`;
  setSearchBusy(true);
}

function renderResults(payload, query) {
  const workResults = payload.work_results || [];
  const segmentResults = payload.results || [];
  const noteResults = payload.note_results || [];
  statusEl.textContent = "";
  const workMarkup = (payload.work_results || [])
    .map((result) => {
      const title = result.title || result.work_id;
      const readLabel = resultReadLabel(title);
      const meta = resultMeta([
        resultCorpusMeta(result.corpus_id),
        result.category_title || result.label
      ]);
      const variants = (result.variant_ids || []).slice(0, 8).map((variantId) => `<span class="tag">${escapeHtml(variantLabel(variantId))}</span>`).join("");
      return `<article class="result work-result">
        <div class="result-title">
          <a href="${escapeHtml(result.url)}" aria-label="${escapeHtml(readLabel)}" title="${escapeHtml(readLabel)}">${escapeHtml(title)}</a>
        </div>
        ${resultSnippet(result.url, result.snippet || "", query, readLabel)}
        ${variants ? `<div class="tag-row">${variants}</div>` : ""}
        ${resultFooter(meta, "")}
      </article>`;
    })
    .join("");
  const segmentMarkup = segmentResults
    .map((result) => {
      const title = result.title || result.work_id;
      const readLabel = resultReadLabel(title);
      const meta = resultMeta([
        resultCorpusMeta(result.corpus_id),
        result.label,
        result.variant_id ? variantLabel(result.variant_id) : ""
      ]);
      return `<article class="result segment-result">
        <div class="result-title">
          <a href="${escapeHtml(result.url)}" aria-label="${escapeHtml(readLabel)}" title="${escapeHtml(readLabel)}">${escapeHtml(title)}</a>
        </div>
        ${resultSnippet(result.url, result.snippet || "", query, readLabel)}
        ${resultFooter(meta, "")}
      </article>`;
    })
    .join("");
  const noteMarkup = noteResults
    .map((result) => {
      const title = result.title || "연구 노트";
      const noteLabel = `노트 보기: ${cleanText(title)}`;
      const sourceLabel = resultReadLabel(result.target_label || title);
      const meta = resultMeta([
        resultCorpusMeta(result.corpus_id),
        result.target_label,
        reviewStateLabel(result.review_state)
      ]);
      const snippetHref = result.url || result.manage_url || notesHref(result);
      const snippetLabel = result.url ? sourceLabel : noteLabel;
      const tags = (result.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const actions = result.url ? `<a class="result-action-read" href="${escapeHtml(result.url)}" aria-label="${escapeHtml(sourceLabel)}" title="${escapeHtml(sourceLabel)}">원문 읽기</a>` : "";
      return `<article class="result note-result">
        <div class="result-title">
          <a href="${escapeHtml(result.manage_url || notesHref(result))}" aria-label="${escapeHtml(noteLabel)}" title="${escapeHtml(noteLabel)}">${escapeHtml(title)}</a>
        </div>
        ${resultSnippet(snippetHref, result.snippet || "", query, snippetLabel)}
        ${tags ? `<div class="tag-row">${tags}</div>` : ""}
        ${resultFooter(meta, actions)}
      </article>`;
    })
    .join("");
  const groups = [];
  if (workMarkup) {
    groups.push({
      id: "search-results-works",
      label: "문서",
      count: workResults.length,
      markup: `<section id="search-results-works" class="result-group">${resultGroupHeader("문서")}${workMarkup}</section>`
    });
  }
  if (segmentMarkup) {
    groups.push({
      id: "search-results-segments",
      label: "본문",
      count: segmentResults.length,
      markup: `<section id="search-results-segments" class="result-group">${resultGroupHeader("본문")}${segmentMarkup}</section>`
    });
  }
  if (noteMarkup) {
    groups.push({
      id: "search-results-notes",
      label: "노트",
      count: noteResults.length,
      markup: `<section id="search-results-notes" class="result-group">${resultGroupHeader("노트")}${noteMarkup}</section>`
    });
  }
  resultsEl.innerHTML = groups.length
    ? `${resultSummaryNav(groups)}${groups.map((group) => group.markup).join("")}`
    : renderEmptySearch(query);
}

async function loadMetadata(corpusId) {
  if (!corpusId || !metadataEndpoints[corpusId]) return null;
  if (metadataCache[corpusId]) return metadataCache[corpusId];
  const response = await fetch(metadataEndpoints[corpusId]);
  if (!response.ok) return null;
  metadataCache[corpusId] = await response.json();
  return metadataCache[corpusId];
}

function workLabel(work) {
  return work.display_title || work.title || work.work_id || "";
}

function variantLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function populateFilters(preserveWork = "", preserveVariant = "") {
  const corpusId = corpusSelect.value;
  workSelect.innerHTML = `<option value="">전체 문서</option>`;
  variantSelect.innerHTML = `<option value="">전체 판본</option>`;
  workSelect.disabled = true;
  variantSelect.disabled = true;
  if (!corpusId) return;

  const metadata = await loadMetadata(corpusId);
  const works = metadata && metadata.works ? Object.values(metadata.works) : [];
  if (works.length) {
    const options = works
      .sort((left, right) => workLabel(left).localeCompare(workLabel(right)))
      .map((work) => `<option value="${escapeHtml(work.work_id)}">${escapeHtml(workLabel(work))}</option>`)
      .join("");
    workSelect.innerHTML = `<option value="">전체 문서</option>${options}`;
    workSelect.disabled = false;
  }

  const variants = new Set();
  for (const work of works) {
    for (const variantId of work.variant_ids || []) {
      if (variantId) variants.add(variantId);
    }
    for (const variant of work.variants || []) {
      if (variant.variant_id) variants.add(variant.variant_id);
    }
    if (work.variant_id) variants.add(work.variant_id);
  }
  if (variants.size) {
    const options = [...variants]
      .sort()
      .map((variantId) => `<option value="${escapeHtml(variantId)}">${escapeHtml(variantLabel(variantId))}</option>`)
      .join("");
    variantSelect.innerHTML = `<option value="">전체 판본</option>${options}`;
    variantSelect.disabled = false;
  }
  workSelect.value = preserveWork;
  variantSelect.value = preserveVariant;
  updateSearchFilterSummary();
}

async function removeSearchFilter(filterName) {
  if (filterName === "query") {
    queryInput.value = "";
  } else if (filterName === "corpus") {
    corpusSelect.value = "";
    workSelect.value = "";
    variantSelect.value = "";
    await populateFilters();
  } else if (filterName === "work") {
    workSelect.value = "";
  } else if (filterName === "variant") {
    variantSelect.value = "";
  }
  runSearch();
}

async function runSearch() {
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  const workId = workSelect.disabled ? "" : workSelect.value;
  const variantId = variantSelect.disabled ? "" : variantSelect.value;
  const requestId = activeSearchRequest + 1;
  activeSearchRequest = requestId;
  if (activeSearchController) {
    activeSearchController.abort();
    activeSearchController = null;
  }
  updateUrl(query, corpusId, workId, variantId);
  updateSearchClearState();
  if (!query) {
    statusEl.textContent = "";
    resultsEl.innerHTML = renderSearchStart();
    setSearchBusy(false);
    return;
  }
  const controller = new AbortController();
  activeSearchController = controller;
  renderSearchPending(query);
  const params = new URLSearchParams({ q: query, limit: "40" });
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (variantId) params.set("variant_id", variantId);
  try {
    const response = await fetch(`/api/search?${params}`, { signal: controller.signal });
    if (requestId !== activeSearchRequest) return;
    if (!response.ok) {
      statusEl.textContent = "검색을 완료하지 못했습니다.";
      resultsEl.innerHTML = "";
      return;
    }
    renderResults(await response.json(), query);
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeSearchRequest) {
      statusEl.textContent = "검색을 완료하지 못했습니다.";
      resultsEl.innerHTML = "";
    }
  } finally {
    if (requestId === activeSearchRequest) {
      activeSearchController = null;
      setSearchBusy(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

if (searchClear) {
  searchClear.addEventListener("click", clearSearchFilters);
}

if (activeFiltersEl) {
  activeFiltersEl.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    await removeSearchFilter(button.dataset.filter || "");
  });
}

resultsEl.addEventListener("click", async (event) => {
  const emptyAction = event.target.closest("[data-empty-action]");
  if (!emptyAction) return;
  if (emptyAction.dataset.emptyAction === "clear-search") {
    await clearSearchFilters();
  }
});

corpusSelect.addEventListener("change", async () => {
  await populateFilters();
  runSearch();
});

workSelect.addEventListener("change", runSearch);
variantSelect.addEventListener("change", runSearch);
queryInput.addEventListener("input", updateSearchClearState);

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
corpusSelect.value = initialParams.get("corpus_id") || "";
const initialWorkId = initialParams.get("work_id") || "";
const initialVariantId = initialParams.get("variant_id") || "";
populateFilters(initialWorkId, initialVariantId).then(() => {
  updateSearchClearState();
  if (queryInput.value) {
    runSearch();
  } else {
    resultsEl.innerHTML = renderSearchStart();
  }
});
