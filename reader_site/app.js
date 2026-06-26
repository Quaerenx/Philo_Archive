const state = {
  archive: null,
  categoryQuery: "",
  activeSection: "all",
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

function normalize(value) {
  return String(value ?? "").toLowerCase();
}

function currentCategoryId() {
  const match = window.location.pathname.match(/^\/category\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function filteredSections(corpus) {
  return corpus.sections.filter((section) => section.links.length || section.count);
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
  const primary = sections.find((section) => /주요|core|hebrew|works/i.test(`${section.title} ${section.meta || ""}`)) || sections[0];
  return primary ? primary.links.slice(0, 6) : [];
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

  renderShell("Personal Archive of Literature", "Primary Texts / Authors / Traditions");
  const visibleCorpora = state.archive.corpora;

  if (!visibleCorpora.length) {
    el.archiveLinks.innerHTML = `<div class="empty">Archive categories are not available.</div>`;
    return;
  }

  el.archiveLinks.innerHTML = visibleCorpora
    .map((corpus) => `<a class="root-link" href="/category/${encodeURIComponent(corpus.id)}">${escapeHtml(corpus.title)}</a>`)
    .join("");
}

function renderCategory(categoryId) {
  const corpus = state.archive.corpora.find((item) => item.id === categoryId);
  if (!corpus) {
    renderShell("Not found", "Unknown category");
    el.archiveLinks.innerHTML = [
      `<a class="back-link" href="/">Archive index</a>`,
      `<div class="empty">Category not found.</div>`,
    ].join("");
    return;
  }

  renderShell(corpus.title, corpus.subtitle || corpus.id);
  const baseSections = filteredSections(corpus);
  if (state.activeSection !== "all" && !baseSections.some((section) => section.title === state.activeSection)) {
    state.activeSection = "all";
  }
  const sections = filteredCategorySections(corpus);
  if (!sections.length) {
    el.archiveLinks.innerHTML = [
      `<a class="back-link" href="/">Archive index</a>`,
      categoryControls(corpus, baseSections),
      `<div class="empty">No works match this filter.</div>`,
    ].join("");
    return;
  }

  el.archiveLinks.innerHTML = [
    `<a class="back-link" href="/">Archive index</a>`,
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

function categoryControls(corpus, sections) {
  const pathLinks = readingPathLinks(corpus)
    .map((link, index) => `<a class="reading-path-link${index === 0 ? " primary" : ""}" href="${escapeHtml(link.href)}">${escapeHtml(link.label)}</a>`)
    .join("");
  const sectionButtons = [
    `<button type="button" class="section-filter${state.activeSection === "all" ? " active" : ""}" data-section-filter="all">All</button>`,
    ...sections.map((section) => (
      `<button type="button" class="section-filter${state.activeSection === section.title ? " active" : ""}" data-section-filter="${escapeHtml(section.title)}">${escapeHtml(section.title)}</button>`
    )),
  ].join("");
  return `<section class="category-tools">
    <div class="reading-path"><strong>Start reading</strong><div class="reading-path-links">${pathLinks || '<span class="empty">No starting works available.</span>'}</div></div>
    <label class="category-filter">Find within this category<input id="categoryFilter" value="${escapeHtml(state.categoryQuery)}" autocomplete="off" placeholder="Title or siglum"></label>
    <div class="section-filters" aria-label="Sections">${sectionButtons}</div>
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
}

async function init() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.archive = await response.json();
    renderArchive();
  } catch (error) {
    el.archiveLinks.innerHTML = `<div class="empty">Archive could not be loaded.</div>`;
  }
}

init();
