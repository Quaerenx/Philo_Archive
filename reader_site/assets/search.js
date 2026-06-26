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
  ["nietzsche", "Nietzsche"],
  ["bible", "Bible"],
  ["kierkegaard", "Kierkegaard"],
  ["wittgenstein", "Wittgenstein"]
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
  if (state === "reviewed") return "Reviewed";
  if (state === "rejected") return "Rejected";
  if (state === "generated") return "Generated";
  return state ? variantLabel(state) : "";
}

function resultMeta(parts) {
  return parts.map(cleanText).filter(Boolean).join(" / ");
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
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="Remove ${escapeHtml(label)} filter">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">x</span>
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
  if (query) chips.push(renderFilterChip("query", "Text", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  if (!workSelect.disabled && workSelect.value) chips.push(renderFilterChip("work", "Work", selectedOptionText(workSelect)));
  if (!variantSelect.disabled && variantSelect.value) chips.push(renderFilterChip("variant", "Variant", selectedOptionText(variantSelect)));
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">Filters</span>${chips.join("")}`
    : "";
}

function updateSearchClearState(isBusy = form.classList.contains("is-searching")) {
  if (!searchClear) return;
  searchClear.disabled = isBusy || !searchHasActiveFilters();
  updateSearchFilterSummary();
}

function notesSearchHref(query) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (corpusSelect.value) params.set("corpus_id", corpusSelect.value);
  if (!workSelect.disabled && workSelect.value) params.set("work_id", workSelect.value);
  return params.toString() ? `/notes?${params}` : "/notes";
}

function renderEmptySearch(query) {
  const filtered = searchHasActiveFilters();
  const title = query ? "No matching passages." : "Search the archive.";
  const body = query
    ? "Try a broader term, clear filters, or check saved notes."
    : "";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-search">Clear search</button>'
    : "";
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      <a href="${escapeHtml(notesSearchHref(query))}">Search notes</a>
      <a href="/">Archive</a>
    </div>
  </section>`;
}

function renderSearchStart() {
  const links = startCorpora
    .map(([corpusId, label]) => `<a href="/category/${escapeHtml(corpusId)}">${escapeHtml(label)}</a>`)
    .join("");
  return `<section class="search-start" aria-label="Browse archive">
    <h2>Browse</h2>
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

function pluralize(count, singular, plural = `${singular}s`) {
  const value = Number(count || 0);
  return `${value.toLocaleString()} ${value === 1 ? "result" : "results"}`;
}

function resultGroupHeader(label, count, noun) {
  return `<div class="result-group-header">
    <h2>${escapeHtml(label)}</h2>
    <span class="result-group-count">${escapeHtml(pluralize(count, noun))}</span>
  </div>`;
}

function resultKind(label, className) {
  return `<span class="result-kind ${escapeHtml(className)}">${escapeHtml(label)}</span>`;
}

function resultSnippet(href, text, query) {
  const content = highlight(text || "", query);
  const cleanHref = cleanText(href || "");
  if (!cleanHref) {
    return `<p class="snippet">${content}</p>`;
  }
  return `<a class="snippet snippet-link" href="${escapeHtml(cleanHref)}">${content}</a>`;
}

function resultSummaryNav(groups) {
  if (!Array.isArray(groups) || groups.length < 2) return "";
  const links = groups
    .map((group) => `<a class="result-summary-link" href="#${escapeHtml(group.id)}">
      <span>${escapeHtml(group.label)}</span>
      <strong>${Number(group.count || 0).toLocaleString()}</strong>
    </a>`)
    .join("");
  return `<nav class="result-summary-nav" aria-label="Search result groups">${links}</nav>`;
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

function compactCount(count, label) {
  const value = Number(count || 0);
  return `${value.toLocaleString()} ${label}${value === 1 ? "" : "s"}`;
}

function searchStatusText(workCount, segmentCount, noteCount, query, direct) {
  return "";
}

function resultFooter(meta, actions) {
  const cleanMeta = cleanText(meta || "");
  const cleanActions = cleanText(actions || "");
  const actionsMarkup = !cleanActions
    ? ""
    : `<nav class="result-actions result-actions-inline" aria-label="Result actions">${actions}</nav>`;
  if (!cleanMeta && !cleanActions) return "";
  return `<footer class="result-footer">
    ${cleanMeta ? `<div class="result-meta">${escapeHtml(cleanMeta)}</div>` : ""}
    ${actionsMarkup}
  </footer>`;
}

function renderSearchPending(query) {
  const label = query ? `Searching "${query}"...` : "Searching...";
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
  const workCount = Number(payload.work_count || 0);
  const segmentCount = Number(payload.count || 0);
  const noteCount = Number(payload.note_count || 0);
  const workResults = payload.work_results || [];
  const segmentResults = payload.results || [];
  const noteResults = payload.note_results || [];
  statusEl.textContent = searchStatusText(workCount, segmentCount, noteCount, query, Boolean(payload.direct));
  const workMarkup = (payload.work_results || [])
    .map((result) => {
      const meta = resultMeta([
        corpusLabel(result.corpus_id),
        result.category_title || result.label
      ]);
      const variants = (result.variant_ids || []).slice(0, 8).map((variantId) => `<span class="tag">${escapeHtml(variantLabel(variantId))}</span>`).join("");
      const actions = `<a href="${escapeHtml(result.url)}">Read</a><a href="/notes?corpus_id=${encodeURIComponent(result.corpus_id || "")}&work_id=${encodeURIComponent(result.work_id || "")}">Notes</a>`;
      return `<article class="result work-result">
        <div class="result-title">
          ${resultKind("Work", "work")}
          <a href="${escapeHtml(result.url)}">${escapeHtml(result.title || result.work_id)}</a>
        </div>
        ${resultSnippet(result.url, result.snippet || "", query)}
        ${variants ? `<div class="tag-row">${variants}</div>` : ""}
        ${resultFooter(meta, actions)}
      </article>`;
    })
    .join("");
  const segmentMarkup = segmentResults
    .map((result) => {
      const meta = resultMeta([
        corpusLabel(result.corpus_id),
        result.label,
        result.variant_id ? variantLabel(result.variant_id) : ""
      ]);
      const actions = `<a href="${escapeHtml(result.url)}">Read</a><a href="${escapeHtml(notesHref(result))}">Notes</a>`;
      return `<article class="result">
        <div class="result-title">
          ${resultKind("Passage", "segment")}
          <a href="${escapeHtml(result.url)}">${escapeHtml(result.title || result.work_id)}</a>
        </div>
        ${resultSnippet(result.url, result.snippet || "", query)}
        ${resultFooter(meta, actions)}
      </article>`;
    })
    .join("");
  const noteMarkup = noteResults
    .map((result) => {
      const meta = resultMeta([
        corpusLabel(result.corpus_id),
        result.target_label,
        reviewStateLabel(result.review_state)
      ]);
      const tags = (result.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const actions = result.url ? `<a href="${escapeHtml(result.url)}">Source</a>` : "";
      return `<article class="result note-result">
        <div class="result-title">
          ${resultKind("Note", "note")}
          <a href="${escapeHtml(result.manage_url || notesHref(result))}">${escapeHtml(result.title || "Research note")}</a>
        </div>
        ${resultSnippet(result.manage_url || notesHref(result), result.snippet || "", query)}
        ${tags ? `<div class="tag-row">${tags}</div>` : ""}
        ${resultFooter(meta, actions)}
      </article>`;
    })
    .join("");
  const groups = [];
  if (workMarkup) {
    groups.push({
      id: "search-results-works",
      label: "Works",
      count: workResults.length,
      markup: `<section id="search-results-works" class="result-group">${resultGroupHeader("Works", workResults.length, "work")}${workMarkup}</section>`
    });
  }
  if (segmentMarkup) {
    groups.push({
      id: "search-results-segments",
      label: "Passages",
      count: segmentResults.length,
      markup: `<section id="search-results-segments" class="result-group">${resultGroupHeader("Passages", segmentResults.length, "passage")}${segmentMarkup}</section>`
    });
  }
  if (noteMarkup) {
    groups.push({
      id: "search-results-notes",
      label: "Notes",
      count: noteResults.length,
      markup: `<section id="search-results-notes" class="result-group">${resultGroupHeader("Notes", noteResults.length, "note")}${noteMarkup}</section>`
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
  workSelect.innerHTML = `<option value="">All works</option>`;
  variantSelect.innerHTML = `<option value="">All variants</option>`;
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
    workSelect.innerHTML = `<option value="">All works</option>${options}`;
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
    variantSelect.innerHTML = `<option value="">All variants</option>${options}`;
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
      statusEl.textContent = "Could not complete search.";
      resultsEl.innerHTML = "";
      return;
    }
    renderResults(await response.json(), query);
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeSearchRequest) {
      statusEl.textContent = "Could not complete search.";
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
