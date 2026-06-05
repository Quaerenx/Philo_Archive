const form = document.getElementById("studyForm");
const queryInput = document.getElementById("studyQuery");
const corpusSelect = document.getElementById("studyCorpus");
const workInput = document.getElementById("studyWork");
const tagInput = document.getElementById("studyTag");
const statusEl = document.getElementById("studyStatus");
const resultsEl = document.getElementById("studyResults");
const exportMarkdown = document.getElementById("studyExportMarkdown");
const manageLink = document.getElementById("studyManageLink");
let requestedCorpusId = "";

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
  const manageParams = currentParams("json");
  manageParams.delete("format");
  manageParams.set("review_state", "reviewed");
  manageLink.href = `/notes?${manageParams}`;
}

function updateUrl() {
  const params = currentParams("json");
  params.delete("format");
  history.replaceState(null, "", params.toString() ? `/study?${params}` : "/study");
}

function renderNote(note) {
  const target = note.target_label || note.target_id || "Target";
  const date = note.reviewed_at || note.updated_at || note.created_at || "";
  const tags = (note.tags || []).join(", ");
  const quote = note.quote ? `<blockquote class="note-quote">${escapeHtml(cleanText(note.quote))}</blockquote>` : "";
  const targetLink = note.url
    ? `<a href="${escapeHtml(note.url)}">${escapeHtml(target)}</a>`
    : escapeHtml(target);
  return `<article class="study-note">
    <div class="note-title">
      ${targetLink}
      <span class="note-meta">${escapeHtml(cleanText(date))}</span>
    </div>
    ${tags ? `<div class="note-tags">${escapeHtml(tags)}</div>` : ""}
    <p class="note-text">${escapeHtml(cleanText(note.note))}</p>
    ${quote}
  </article>`;
}

function renderStudy(payload) {
  const groups = payload.groups || [];
  const count = payload.count || 0;
  statusEl.textContent = count
    ? `${count.toLocaleString()} reviewed notes`
    : "No reviewed notes.";
  resultsEl.innerHTML = groups.length
    ? groups.map((group) => {
      const title = [group.corpus_id, group.work_id].filter(Boolean).join(" / ") || "Reviewed notes";
      const workHref = group.corpus_id && group.work_id ? `/work/${encodeURIComponent(group.corpus_id)}/${encodeURIComponent(group.work_id)}` : "";
      const notesHref = `/notes?corpus_id=${encodeURIComponent(group.corpus_id)}&work_id=${encodeURIComponent(group.work_id)}&review_state=reviewed`;
      const tagCounts = (group.tag_counts || [])
        .map((item) => `<span class="study-tag">${escapeHtml(item.tag)} <span>${Number(item.count || 0).toLocaleString()}</span></span>`)
        .join("");
      const reviewedRange = group.reviewed_range || {};
      const rangeText = reviewedRange.start || reviewedRange.end
        ? `${cleanText(reviewedRange.start)} - ${cleanText(reviewedRange.end)}`
        : "";
      return `<section class="study-group">
        <h2>${escapeHtml(title)}</h2>
        <div class="group-meta">${escapeHtml(group.summary || `${group.notes.length.toLocaleString()} reviewed notes`)}</div>
        ${rangeText ? `<div class="group-range">${escapeHtml(rangeText)}</div>` : ""}
        ${tagCounts ? `<div class="study-tags">${tagCounts}</div>` : ""}
        <div class="group-actions">
          ${workHref ? `<a href="${escapeHtml(workHref)}">Open work</a>` : ""}
          <a href="${escapeHtml(notesHref)}">Manage notes</a>
        </div>
        ${group.notes.map(renderNote).join("")}
      </section>`;
    }).join("")
    : `<div class="empty">No reviewed notes.</div>`;
}

async function loadCorpora() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) return;
    const payload = await response.json();
    const current = corpusSelect.value || requestedCorpusId;
    corpusSelect.innerHTML = `<option value="">All</option>` + (payload.corpora || [])
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title)}</option>`)
      .join("");
    corpusSelect.value = current;
  } catch {
    // The hard-coded All option remains usable without archive metadata.
  }
}

async function loadStudy() {
  updateUrl();
  updateLinks();
  statusEl.textContent = "Loading reviewed notes...";
  resultsEl.innerHTML = "";
  const response = await fetch(`/api/study?${currentParams("json")}`);
  if (!response.ok) {
    statusEl.textContent = "Could not load reviewed notes.";
    return;
  }
  const payload = await response.json();
  renderStudy(payload);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadStudy();
});

for (const field of [queryInput, corpusSelect, workInput, tagInput]) {
  field.addEventListener("change", loadStudy);
}

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
workInput.value = initialParams.get("work_id") || "";
tagInput.value = initialParams.get("tag") || "";
requestedCorpusId = initialParams.get("corpus_id") || "";
corpusSelect.value = requestedCorpusId;

loadCorpora().then(loadStudy);
