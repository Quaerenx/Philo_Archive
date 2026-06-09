const form = document.getElementById("searchForm");
const queryInput = document.getElementById("queryInput");
const corpusSelect = document.getElementById("corpusSelect");
const workSelect = document.getElementById("workSelect");
const variantSelect = document.getElementById("variantSelect");
const statusEl = document.getElementById("searchStatus");
const resultsEl = document.getElementById("results");
const metadataCache = {};
const metadataEndpoints = {
  nietzsche: "/api/nietzsche/metadata",
  bible: "/api/bible/metadata",
  kierkegaard: "/api/kierkegaard/metadata",
  wittgenstein: "/api/wittgenstein/metadata"
};

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

function updateUrl(query, corpusId, workId, variantId) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (variantId) params.set("variant_id", variantId);
  history.replaceState(null, "", params.toString() ? `/search?${params}` : "/search");
}

function notesHref(result) {
  const params = new URLSearchParams();
  if (result.corpus_id) params.set("corpus_id", result.corpus_id);
  if (result.work_id) params.set("work_id", result.work_id);
  if (result.segment_id) params.set("target_id", result.segment_id);
  return `/notes?${params}`;
}

function renderResults(payload, query) {
  const workCount = Number(payload.work_count || 0);
  const segmentCount = Number(payload.count || 0);
  const noteCount = Number(payload.note_count || 0);
  if (payload.direct && payload.results && payload.results.length) {
    statusEl.textContent = `Direct Bible reference - ${workCount.toLocaleString()} matching works, ${segmentCount.toLocaleString()} matching segments, ${noteCount.toLocaleString()} matching notes`;
  } else {
    statusEl.textContent = workCount || segmentCount || noteCount
    ? `${workCount.toLocaleString()} matching works, ${segmentCount.toLocaleString()} matching segments, ${noteCount.toLocaleString()} matching notes`
    : query ? "No matching results." : "";
  }
  const workMarkup = (payload.work_results || [])
    .map((result) => {
      const meta = [
        result.corpus_id,
        result.work_id,
        result.category_title || result.label
      ].filter(Boolean).join(" / ");
      const variants = (result.variant_ids || []).slice(0, 8).map((variantId) => `<span class="tag">${escapeHtml(variantLabel(variantId))}</span>`).join("");
      return `<article class="result work-result">
        <div class="result-title">
          <a href="${escapeHtml(result.url)}">${escapeHtml(result.title || result.work_id)}</a>
          <span class="result-meta">${escapeHtml(meta)}</span>
        </div>
        <p class="snippet">${highlight(result.snippet || "", query)}</p>
        ${variants ? `<div class="tag-row">${variants}</div>` : ""}
        <div class="result-actions">
          <a href="${escapeHtml(result.url)}">Open work</a>
          <a href="/notes?corpus_id=${encodeURIComponent(result.corpus_id || "")}&work_id=${encodeURIComponent(result.work_id || "")}">Notes for work</a>
        </div>
      </article>`;
    })
    .join("");
  const segmentMarkup = (payload.results || [])
    .map((result) => {
      const meta = [
        result.corpus_id,
        result.work_id,
        result.variant_id,
        result.label
      ].filter(Boolean).join(" / ");
      return `<article class="result">
        <div class="result-title">
          <a href="${escapeHtml(result.url)}">${escapeHtml(result.title || result.work_id)}</a>
          <span class="result-meta">${escapeHtml(meta)}</span>
        </div>
        <p class="snippet">${highlight(result.snippet || "", query)}</p>
        <div class="result-actions">
          <a href="${escapeHtml(notesHref(result))}">Notes for target</a>
          <a href="/notes?corpus_id=${encodeURIComponent(result.corpus_id || "")}&work_id=${encodeURIComponent(result.work_id || "")}">Notes for work</a>
        </div>
      </article>`;
    })
    .join("");
  const noteMarkup = (payload.note_results || [])
    .map((result) => {
      const meta = [
        result.corpus_id,
        result.work_id,
        result.target_label,
        result.review_state
      ].filter(Boolean).join(" / ");
      const tags = (result.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const targetLink = result.url ? `<a href="${escapeHtml(result.url)}">Open target</a>` : "";
      return `<article class="result note-result">
        <div class="result-title">
          <a href="${escapeHtml(result.manage_url || notesHref(result))}">${escapeHtml(result.title || "Research note")}</a>
          <span class="result-meta">${escapeHtml(meta)}</span>
        </div>
        <p class="snippet">${highlight(result.snippet || "", query)}</p>
        ${tags ? `<div class="tag-row">${tags}</div>` : ""}
        <div class="result-actions">
          ${targetLink}
          <a href="${escapeHtml(result.manage_url || notesHref(result))}">Manage note</a>
        </div>
      </article>`;
    })
    .join("");
  const sections = [];
  if (workMarkup) {
    sections.push(`<section class="result-group"><h2>Works</h2>${workMarkup}</section>`);
  }
  if (segmentMarkup) {
    sections.push(`<section class="result-group"><h2>Segments</h2>${segmentMarkup}</section>`);
  }
  if (noteMarkup) {
    sections.push(`<section class="result-group"><h2>Notes</h2>${noteMarkup}</section>`);
  }
  resultsEl.innerHTML = sections.join("");
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
}

async function runSearch() {
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  const workId = workSelect.disabled ? "" : workSelect.value;
  const variantId = variantSelect.disabled ? "" : variantSelect.value;
  updateUrl(query, corpusId, workId, variantId);
  if (!query) {
    statusEl.textContent = "";
    resultsEl.innerHTML = "";
    return;
  }
  statusEl.textContent = "Searching...";
  resultsEl.innerHTML = "";
  const params = new URLSearchParams({ q: query, limit: "40" });
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (variantId) params.set("variant_id", variantId);
  const response = await fetch(`/api/search?${params}`);
  if (!response.ok) {
    statusEl.textContent = "Search failed.";
    return;
  }
  renderResults(await response.json(), query);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

corpusSelect.addEventListener("change", async () => {
  await populateFilters();
  runSearch();
});

workSelect.addEventListener("change", runSearch);
variantSelect.addEventListener("change", runSearch);

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
corpusSelect.value = initialParams.get("corpus_id") || "";
const initialWorkId = initialParams.get("work_id") || "";
const initialVariantId = initialParams.get("variant_id") || "";
populateFilters(initialWorkId, initialVariantId).then(() => {
  if (queryInput.value) {
    runSearch();
  }
});
