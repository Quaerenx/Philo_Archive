const state = {
  archive: null,
  categoryQuery: "",
  activeSection: "all",
  workSearchResults: [],
  workSearchCount: 0,
  workSearchState: "idle",
  workQuery: "",
  workResultQuery: "",
  workSearchOpen: false,
  activeWorkResult: -1,
};

const RECENT_WORK_STORAGE_KEY = "philo.reader.recentWork";
const START_READING_LIMIT = 6;
const WORK_SEARCH_RESULT_LIMIT = 8;
const WORK_SEARCH_DEBOUNCE_MS = 140;
let workSearchTimer = 0;
let activeWorkSearchController = null;
let removeHomeSearchOutsideListener = () => {};
const START_READING_WORK_IDS = {
  nietzsche: ["M", "FW", "Za-I", "JGB", "GM", "GD"],
  bible: ["oshb.Gen", "oshb.Ps", "oshb.Isa", "sblgnt.Matt", "sblgnt.John", "sblgnt.Rom"],
  kierkegaard: ["ee1", "ee2", "fb", "g", "ba", "ps"],
  wittgenstein: [
    "Group_Notebooks",
    "Group_BigTypescriptCorpus",
    "Group_BrownBookCorpus",
    "Group_PICorpus",
    "Group_RFMCorpus",
    "Group_RPPCorpus"
  ],
};

const ROOT_LINK_LABELS = {
  nietzsche: "니체 / Nietzsche",
  bible: "성경 / Bible",
  kierkegaard: "키르케고르 / Kierkegaard",
  wittgenstein: "비트겐슈타인 / Wittgenstein",
};

const CATEGORY_SUBTITLES = {
  nietzsche: "출간 저작과 독서 경로",
  bible: "히브리어 성경, 그리스어 신약, 칠십인역",
  kierkegaard: "읽기용으로 정리한 원전",
  wittgenstein: "노트, 단상, 철학적 탐구",
};

const CATEGORY_BODY_CLASSES = Object.keys(ROOT_LINK_LABELS).map((id) => `category-${id}`);

const el = {
  archiveLinks: document.querySelector("#archiveLinks"),
  pageSubtitle: document.querySelector("#pageSubtitle"),
  pageTitle: document.querySelector("#pageTitle"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function normalize(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase();
}

function storedRecentWork() {
  try {
    const storage = window.localStorage;
    const raw = storage ? storage.getItem(RECENT_WORK_STORAGE_KEY) : "";
    if (!raw) return null;
    const item = JSON.parse(raw);
    if (!item || typeof item !== "object") return null;
    const href = cleanText(item.href || "");
    if (!href.startsWith("/work/")) return null;
    const title = cleanText(item.title || item.work_id || "최근 문서");
    const corpus = cleanText(item.corpus_title || item.corpus_id || "");
    return {
      href,
      title,
      meta: corpus
    };
  } catch (error) {
    return null;
  }
}

function recentWorkMarkup() {
  const recent = storedRecentWork();
  if (!recent) return "";
  const meta = recent.meta ? `<span class="recent-work-meta">${escapeHtml(recent.meta)}</span>` : "";
  return `<section class="recent-work">
    <a class="recent-work-link" href="${escapeHtml(recent.href)}" aria-label="이어 읽기: ${escapeHtml(recent.title)}">
      <span class="recent-work-label">이어 읽기</span>
      <span class="recent-work-title">${escapeHtml(recent.title)}</span>
    </a>
    ${meta}
  </section>`;
}

function currentCategoryId() {
  const match = window.location.pathname.match(/^\/category\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function syncCategoryBodyClass(categoryId = "") {
  document.body.classList.remove(...CATEGORY_BODY_CLASSES);
  if (CATEGORY_BODY_CLASSES.includes(`category-${categoryId}`)) {
    document.body.classList.add(`category-${categoryId}`);
  }
}

function filteredSections(corpus) {
  return (corpus.sections || []).filter((section) => section.links.length || section.count);
}

function corpusLinks(corpus) {
  return filteredSections(corpus).flatMap((section) => section.links || []);
}

function uniqueLinks(links) {
  const seen = new Set();
  return links.filter((link) => {
    const key = link.work_id || link.href || link.label;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizedContains(value, query) {
  return normalize(value).includes(normalize(query));
}

function homeSearchMarkup() {
  return `<div class="corpus-search">
    <div class="corpus-search-heading">
      <label class="corpus-search-label" for="corpusSearchInput">전체 작품명 검색</label>
      <a class="corpus-text-search" href="/search">작품 본문에서 찾기</a>
    </div>
    <div class="corpus-search-control">
      <input id="corpusSearchInput" class="corpus-search-input" type="search" autocomplete="off" spellcheck="false" placeholder="예: 아침놀, Genesis" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" aria-controls="corpusSearchResults" aria-expanded="false">
      <div id="corpusSearchPreview" class="corpus-search-preview" hidden>
        <div id="corpusSearchStatus" class="corpus-search-status" role="status" aria-live="polite"></div>
        <div id="corpusSearchResults" class="corpus-search-results" role="listbox" aria-label="작품명 검색 결과"></div>
        <div id="corpusSearchActions" class="corpus-search-actions"></div>
      </div>
    </div>
  </div>`;
}

function normalizedMatchRange(value, query) {
  const cleanValue = cleanText(value);
  const normalizedQuery = normalize(cleanText(query));
  if (!normalizedQuery) return null;

  let normalizedValue = "";
  const sourceRanges = [];
  let sourceOffset = 0;
  for (const character of cleanValue) {
    const sourceEnd = sourceOffset + character.length;
    const normalizedCharacter = normalize(character);
    normalizedValue += normalizedCharacter;
    for (let index = 0; index < normalizedCharacter.length; index += 1) {
      sourceRanges.push([sourceOffset, sourceEnd]);
    }
    sourceOffset = sourceEnd;
  }
  const matchIndex = normalizedValue.indexOf(normalizedQuery);
  if (matchIndex < 0 || !sourceRanges[matchIndex] || !sourceRanges[matchIndex + normalizedQuery.length - 1]) return null;
  return [sourceRanges[matchIndex][0], sourceRanges[matchIndex + normalizedQuery.length - 1][1]];
}

function highlightedTitle(title, query) {
  const cleanTitle = cleanText(title);
  const matchRange = normalizedMatchRange(cleanTitle, query);
  if (!matchRange) return escapeHtml(cleanTitle);
  const [start, end] = matchRange;
  return `${escapeHtml(cleanTitle.slice(0, start))}<mark>${escapeHtml(cleanTitle.slice(start, end))}</mark>${escapeHtml(cleanTitle.slice(end))}`;
}

function workSearchResultMarkup(work, index) {
  const active = index === state.activeWorkResult;
  const context = [work.corpus_title, work.section_title].filter(Boolean).join(" · ");
  return `<a id="corpusSearchResult-${index}" class="corpus-search-result${active ? " is-active" : ""}" href="${escapeHtml(work.href)}" role="option" aria-selected="${active}" aria-label="${escapeHtml(`${context}: ${work.display_title}`)}">
    <span class="corpus-search-context">${escapeHtml(context)}</span>
    <span class="corpus-search-title">${highlightedTitle(work.display_title, state.workQuery)}</span>
  </a>`;
}

function fullTextSearchHref(query = "") {
  return query ? `/search?q=${encodeURIComponent(query)}` : "/search";
}

function bindWorkSearchActions() {
  const retry = document.querySelector("[data-work-search-retry]");
  if (retry) retry.addEventListener("click", () => requestWorkSearch(state.workQuery));
}

function renderWorkSearchPreview() {
  const input = document.querySelector("#corpusSearchInput");
  const preview = document.querySelector("#corpusSearchPreview");
  const status = document.querySelector("#corpusSearchStatus");
  const results = document.querySelector("#corpusSearchResults");
  const actions = document.querySelector("#corpusSearchActions");
  const fullTextLink = document.querySelector(".corpus-text-search");
  if (!input || !preview || !status || !results || !actions || !fullTextLink) return;

  fullTextLink.setAttribute("href", fullTextSearchHref(state.workQuery));
  input.removeAttribute("aria-activedescendant");
  if (!state.workQuery || !state.workSearchOpen) {
    preview.hidden = true;
    input.setAttribute("aria-expanded", "false");
    status.textContent = "";
    results.innerHTML = "";
    actions.innerHTML = "";
    return;
  }

  preview.hidden = false;
  input.setAttribute("aria-expanded", "true");
  actions.innerHTML = "";
  if (state.workSearchState === "loading" || state.workSearchState === "idle") {
    status.textContent = "작품명을 찾는 중...";
    results.innerHTML = "";
    return;
  }
  if (state.workSearchState === "error") {
    status.textContent = "작품명 검색을 불러오지 못했습니다.";
    results.innerHTML = "";
    actions.innerHTML = `<button type="button" data-work-search-retry>다시 시도</button><a href="${escapeHtml(fullTextSearchHref(state.workQuery))}">본문 검색으로 이동</a>`;
    bindWorkSearchActions();
    return;
  }

  if (state.workResultQuery !== state.workQuery) {
    status.textContent = "작품명을 찾는 중...";
    results.innerHTML = "";
    return;
  }
  if (!state.workSearchResults.length) {
    status.textContent = "일치하는 작품이 없습니다.";
    results.innerHTML = "";
    actions.innerHTML = `<a href="${escapeHtml(fullTextSearchHref(state.workQuery))}">이 검색어를 본문에서 찾기</a>`;
    return;
  }

  const resultNote = state.workSearchCount > state.workSearchResults.length ? `, ${state.workSearchResults.length}개 미리보기` : "";
  status.textContent = `${state.workSearchCount.toLocaleString("ko-KR")}개 작품${resultNote}`;
  results.innerHTML = state.workSearchResults.map(workSearchResultMarkup).join("");
  if (state.workSearchCount > state.workSearchResults.length) {
    actions.innerHTML = `<a href="${escapeHtml(fullTextSearchHref(state.workQuery))}">전체 검색에서 더 보기</a>`;
  }
  if (state.activeWorkResult >= 0 && state.activeWorkResult < state.workSearchResults.length) {
    input.setAttribute("aria-activedescendant", `corpusSearchResult-${state.activeWorkResult}`);
  }
}

function setActiveWorkResult(index) {
  const visibleCount = state.workSearchResults.length;
  if (!visibleCount) return;
  state.activeWorkResult = (index + visibleCount) % visibleCount;
  renderWorkSearchPreview();
  document.querySelector(`#corpusSearchResult-${state.activeWorkResult}`)?.scrollIntoView({ block: "nearest" });
}

async function requestWorkSearch(query) {
  const requestedQuery = cleanText(query);
  if (!requestedQuery) return;
  activeWorkSearchController?.abort();
  const controller = new AbortController();
  activeWorkSearchController = controller;
  state.workSearchState = "loading";
  renderWorkSearchPreview();
  try {
    const response = await fetch(`/api/archive/titles?q=${encodeURIComponent(requestedQuery)}&limit=${WORK_SEARCH_RESULT_LIMIT}`, { signal: controller.signal });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const payload = await response.json();
    if (requestedQuery !== state.workQuery) return;
    state.workSearchResults = Array.isArray(payload.results) ? payload.results : [];
    state.workSearchCount = Number(payload.count) || 0;
    state.workResultQuery = requestedQuery;
    state.workSearchState = "ready";
  } catch (error) {
    if (error.name === "AbortError" || requestedQuery !== state.workQuery) return;
    state.workSearchResults = [];
    state.workSearchCount = 0;
    state.workResultQuery = requestedQuery;
    state.workSearchState = "error";
  } finally {
    if (activeWorkSearchController === controller) activeWorkSearchController = null;
  }
  renderWorkSearchPreview();
}

function scheduleWorkSearch() {
  window.clearTimeout(workSearchTimer);
  activeWorkSearchController?.abort();
  state.workSearchResults = [];
  state.workSearchCount = 0;
  state.workResultQuery = "";
  if (!state.workQuery) {
    state.workSearchState = "idle";
    renderWorkSearchPreview();
    return;
  }
  state.workSearchState = "loading";
  renderWorkSearchPreview();
  workSearchTimer = window.setTimeout(() => requestWorkSearch(state.workQuery), WORK_SEARCH_DEBOUNCE_MS);
}

function closeWorkSearch() {
  state.workSearchOpen = false;
  state.activeWorkResult = -1;
  renderWorkSearchPreview();
}

function bindHomeSearch() {
  const input = document.querySelector("#corpusSearchInput");
  const search = input?.closest(".corpus-search");
  if (!input) return;
  removeHomeSearchOutsideListener();
  input.value = state.workQuery;
  const openSearch = () => {
    if (!state.workQuery) return;
    state.workSearchOpen = true;
    renderWorkSearchPreview();
    if (state.workResultQuery !== state.workQuery) scheduleWorkSearch();
  };
  input.addEventListener("focus", openSearch);
  input.addEventListener("click", openSearch);
  input.addEventListener("input", () => {
    state.workQuery = input.value.trim();
    state.workSearchOpen = Boolean(state.workQuery);
    state.activeWorkResult = -1;
    scheduleWorkSearch();
  });
  input.addEventListener("keydown", (event) => {
    if (event.isComposing || event.keyCode === 229) return;
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && state.workQuery && !state.workSearchOpen) {
      state.workSearchOpen = true;
      renderWorkSearchPreview();
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveWorkResult(state.activeWorkResult + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveWorkResult(state.activeWorkResult < 0 ? -1 : state.activeWorkResult - 1);
    } else if (event.key === "Enter" && state.workSearchOpen) {
      const target = state.workSearchResults[state.activeWorkResult < 0 ? 0 : state.activeWorkResult];
      if (target) {
        event.preventDefault();
        window.location.assign(target.href);
      }
    } else if (event.key === "Escape" && state.workSearchOpen) {
      event.preventDefault();
      closeWorkSearch();
    }
  });
  const handleOutsidePointer = (event) => {
    if (state.workSearchOpen && search && !search.contains(event.target)) closeWorkSearch();
  };
  document.addEventListener("pointerdown", handleOutsidePointer);
  removeHomeSearchOutsideListener = () => document.removeEventListener("pointerdown", handleOutsidePointer);
}

function filteredCategorySections(corpus) {
  const sections = filteredSections(corpus)
    .filter((section) => state.activeSection === "all" || section.title === state.activeSection)
    .map((section) => {
      const links = section.links.filter((link) => {
        if (!state.categoryQuery) return true;
        return [
          link.label,
          link.meta,
          link.work_id,
          section.title,
          section.meta,
        ].some((value) => normalizedContains(value, state.categoryQuery));
      });
      return { ...section, links, count: links.length };
    });
  return sections.filter((section) => section.links.length);
}

function readingPathLinks(corpus) {
  const sections = filteredSections(corpus);
  const links = corpusLinks(corpus);
  const linksByWorkId = new Map(links.map((link) => [link.work_id, link]));
  const priorityLinks = (START_READING_WORK_IDS[corpus.id] || [])
    .map((workId) => linksByWorkId.get(workId))
    .filter(Boolean);
  const primary = sections.find((section) => /주요|core|hebrew|works/i.test(`${section.title} ${section.meta || ""}`)) || sections[0];
  const fallbackLinks = primary ? primary.links : links;
  return uniqueLinks([...priorityLinks, ...fallbackLinks]).slice(0, START_READING_LIMIT);
}

function startReadingLabel(link) {
  return link.display_title || link.label;
}

function startReadingTitle(link) {
  const displayLabel = startReadingLabel(link);
  return displayLabel !== link.label ? ` title="${escapeHtml(link.label)}"` : "";
}

function startReadingAriaLabel(link, index) {
  if (index !== 0) return "";
  return ` aria-label="추천 읽기 시작: ${escapeHtml(startReadingLabel(link))}"`;
}

function rootLinkLabel(corpus) {
  return ROOT_LINK_LABELS[corpus.id] || corpus.title;
}

function categorySubtitle(corpus) {
  return CATEGORY_SUBTITLES[corpus.id] || corpus.subtitle || corpus.id;
}

function archiveDisplayMeta(value) {
  const text = cleanText(value);
  if (!text) return "";
  const parts = text.split(/\s*·\s*/).map(cleanText).filter(Boolean);
  const useful = parts.filter((part) => !/^\d[\d,]*\s+(verses?|segments?|files?|works?|tokens?|chapters?)$/i.test(part));
  return useful.join(" · ");
}

function renderShell(title, subtitle) {
  el.pageTitle.textContent = title;
  el.pageSubtitle.textContent = subtitle;
  document.title = title === "Personal Archive of Literature"
    ? title
    : `${title} / Personal Archive of Literature`;
}

function renderArchive() {
  if (!state.archive) return;
  const categoryId = currentCategoryId();
  if (categoryId) {
    renderCategory(categoryId);
    return;
  }

  syncCategoryBodyClass("");
  renderShell("Personal Archive of Literature", "원전 / 저자 / 전통");
  const visibleCorpora = state.archive.corpora;

  if (!visibleCorpora.length) {
    el.archiveLinks.innerHTML = `<div class="empty">아카이브 카테고리를 불러올 수 없습니다.</div>`;
    return;
  }

  el.archiveLinks.innerHTML = [
    recentWorkMarkup(),
    `<section class="root-links" aria-label="Corpus 목록">
      <h2>Corpus 목록</h2>
      ${homeSearchMarkup()}
      <div class="root-link-list">
        ${visibleCorpora
          .map((corpus) => `<a class="root-link" href="/category/${encodeURIComponent(corpus.id)}">${escapeHtml(rootLinkLabel(corpus))}</a>`)
          .join("")}
      </div>
    </section>`
  ].join("");
  bindHomeSearch();
}

function renderCategory(categoryId) {
  syncCategoryBodyClass(categoryId);
  const corpus = state.archive.corpora.find((item) => item.id === categoryId);
  if (!corpus) {
    renderShell("찾을 수 없음", "알 수 없는 카테고리");
    el.archiveLinks.innerHTML = [
      `<a class="back-link" href="/">아카이브</a>`,
      `<div class="empty">카테고리를 찾을 수 없습니다.</div>`,
    ].join("");
    return;
  }

  renderShell(corpus.title, categorySubtitle(corpus));
  const baseSections = filteredSections(corpus);
  if (state.activeSection !== "all" && !baseSections.some((section) => section.title === state.activeSection)) {
    state.activeSection = "all";
  }
  const sections = filteredCategorySections(corpus);
  if (!sections.length) {
    el.archiveLinks.innerHTML = [
      `<a class="back-link" href="/">아카이브</a>`,
      categoryControls(corpus, baseSections),
      categoryEmptyState(),
    ].join("");
    bindCategoryControls();
    return;
  }

  el.archiveLinks.innerHTML = [
    `<a class="back-link" href="/">아카이브</a>`,
    categoryControls(corpus, baseSections),
    sections
      .map((section) => {
        const sectionMetaText = archiveDisplayMeta(section.meta);
        const sectionMeta = sectionMetaText ? `<div class="section-meta">${escapeHtml(sectionMetaText)}</div>` : "";
        const links = section.links
          .map((link) => {
            const metaText = archiveDisplayMeta(link.meta);
            const meta = metaText ? `<span class="work-meta">${escapeHtml(metaText)}</span>` : "";
            return `<a class="work-link" href="${escapeHtml(link.href)}"><span class="work-title">${escapeHtml(link.display_title || link.label)}</span>${meta}</a>`;
          })
          .join("");
        return `<section class="category-section"><h2>${escapeHtml(section.title)}</h2>${sectionMeta}<div class="work-links">${links}</div></section>`;
      })
      .join(""),
  ].join("");
  bindCategoryControls();
}

function hasCategoryFilters() {
  return Boolean(state.categoryQuery || state.activeSection !== "all");
}

function categoryEmptyState() {
  const clearAction = hasCategoryFilters()
    ? `<div class="category-empty-actions"><button type="button" data-category-action="clear-filters">필터 지우기</button></div>`
    : "";
  return `<div class="empty category-empty">조건에 맞는 작품이 없습니다.${clearAction}</div>`;
}

function categoryControls(corpus, sections) {
  const browseToolsOpen = hasCategoryFilters() ? " open" : "";
  const pathLinks = readingPathLinks(corpus)
    .map((link, index) => `<a class="reading-path-link${index === 0 ? " primary" : ""}" href="${escapeHtml(link.href)}"${startReadingTitle(link)}${startReadingAriaLabel(link, index)}>${escapeHtml(startReadingLabel(link))}</a>`)
    .join("");
  const sectionButtons = [
    `<button type="button" class="section-filter${state.activeSection === "all" ? " active" : ""}" data-section-filter="all">전체</button>`,
    ...sections.map((section) => (
      `<button type="button" class="section-filter${state.activeSection === section.title ? " active" : ""}" data-section-filter="${escapeHtml(section.title)}">${escapeHtml(section.title)}</button>`
    )),
  ].join("");
  return `<section class="category-tools">
    <div class="reading-path"><strong>바로 읽기</strong><div class="reading-path-links">${pathLinks || '<span class="empty">시작 문서가 없습니다.</span>'}</div></div>
    <details class="category-browse-tools"${browseToolsOpen}>
      <summary>작품 찾기</summary>
      <div class="category-browse-body">
        <label class="category-filter">작품 찾기<input id="categoryFilter" value="${escapeHtml(state.categoryQuery)}" autocomplete="off" placeholder="제목 또는 약호"></label>
        <div class="section-filters" aria-label="분류">${sectionButtons}</div>
      </div>
    </details>
  </section>`;
}

function bindCategoryControls() {
  const filter = document.querySelector("#categoryFilter");
  if (filter) {
    filter.addEventListener("input", () => {
      state.categoryQuery = filter.value.trim();
      renderArchive();
      const nextFilter = document.querySelector("#categoryFilter");
      if (nextFilter) {
        nextFilter.focus();
        nextFilter.setSelectionRange(nextFilter.value.length, nextFilter.value.length);
      }
    });
  }
  document.querySelectorAll(".section-filter").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeSection = button.dataset.sectionFilter || "all";
      renderArchive();
    });
  });
  document.querySelectorAll("[data-category-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.categoryAction !== "clear-filters") return;
      state.categoryQuery = "";
      state.activeSection = "all";
      renderArchive();
      const nextFilter = document.querySelector("#categoryFilter");
      if (nextFilter) {
        nextFilter.focus();
      }
    });
  });
}

async function init() {
  try {
    const archiveEndpoint = currentCategoryId() ? "/api/archive" : "/api/archive/summary";
    const response = await fetch(archiveEndpoint);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.archive = await response.json();
    renderArchive();
  } catch (error) {
    el.archiveLinks.innerHTML = `<div class="empty">아카이브를 불러올 수 없습니다.</div>`;
  }
}

init();
