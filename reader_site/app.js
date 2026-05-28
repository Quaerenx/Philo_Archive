const state = {
  archive: null,
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
    el.archiveLinks.innerHTML = `<div class="empty">No matching texts.</div>`;
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
      `<div class="empty">No matching category.</div>`,
    ].join("");
    return;
  }

  renderShell(corpus.title, corpus.subtitle || corpus.id);
  const sections = filteredSections(corpus);
  if (!sections.length) {
    el.archiveLinks.innerHTML = [
      `<a class="back-link" href="/">Archive index</a>`,
      `<div class="empty">No matching texts.</div>`,
    ].join("");
    return;
  }

  el.archiveLinks.innerHTML = [
    `<a class="back-link" href="/">Archive index</a>`,
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
}

async function init() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.archive = await response.json();
    renderArchive();
  } catch (error) {
    el.archiveLinks.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

init();
