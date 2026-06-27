const state = {
  archive: null,
  categoryQuery: "",
  activeSection: "all",
};

const RECENT_WORK_STORAGE_KEY = "philo.reader.recentWork";
const START_READING_LIMIT = 6;
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

const START_READING_LABELS = {
  M: "Morgenröthe / 아침놀",
  FW: "Die fröhliche Wissenschaft / 즐거운 학문",
  JGB: "Jenseits von Gut und Böse / 선악의 저편",
  GM: "Zur Genealogie der Moral / 도덕의 계보",
  GD: "Götzen-Dämmerung / 우상의 황혼",
  ee1: "Enten - Eller I",
  ee2: "Enten - Eller II",
  Group_Notebooks: "Notebooks",
  Group_BigTypescriptCorpus: "Big Typescript",
  Group_BrownBookCorpus: "Brown Book",
  Group_PICorpus: "Philosophical Investigations",
  Group_RFMCorpus: "Remarks on Mathematics",
  Group_RPPCorpus: "Remarks on Psychology",
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
  return String(value ?? "").toLowerCase();
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

function filteredSections(corpus) {
  return corpus.sections.filter((section) => section.links.length || section.count);
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
  return START_READING_LABELS[link.work_id] || link.label;
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

  renderShell("Personal Archive of Literature", "원전 / 저자 / 전통");
  const visibleCorpora = state.archive.corpora;

  if (!visibleCorpora.length) {
    el.archiveLinks.innerHTML = `<div class="empty">아카이브 카테고리를 불러올 수 없습니다.</div>`;
    return;
  }

  el.archiveLinks.innerHTML = [
    recentWorkMarkup(),
    `<section class="root-links" aria-label="자료 선택">
      <h2>읽기 시작</h2>
      <div class="root-link-list">
        ${visibleCorpora
          .map((corpus) => `<a class="root-link" href="/category/${encodeURIComponent(corpus.id)}">${escapeHtml(rootLinkLabel(corpus))}</a>`)
          .join("")}
      </div>
    </section>`
  ].join("");
}

function renderCategory(categoryId) {
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
        const sectionMeta = section.meta ? `<div class="section-meta">${escapeHtml(section.meta)}</div>` : "";
        const links = section.links
          .map((link) => {
            const meta = link.meta ? `<span class="work-meta">${escapeHtml(link.meta)}</span>` : "";
            return `<a class="work-link" href="${escapeHtml(link.href)}"><span class="work-title">${escapeHtml(link.label)}</span>${meta}</a>`;
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
      <summary>목록 좁히기</summary>
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
    const response = await fetch("/api/archive");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.archive = await response.json();
    renderArchive();
  } catch (error) {
    el.archiveLinks.innerHTML = `<div class="empty">아카이브를 불러올 수 없습니다.</div>`;
  }
}

init();
