const form = document.getElementById("notesForm");
const queryInput = document.getElementById("notesQuery");
const corpusSelect = document.getElementById("notesCorpus");
const workInput = document.getElementById("notesWork");
const tagInput = document.getElementById("notesTag");
const reviewSelect = document.getElementById("notesReview");
const notesSubmit = document.getElementById("notesSubmit");
const notesClear = document.getElementById("notesClear");
const activeFiltersEl = document.getElementById("notesActiveFilters");
const statusEl = document.getElementById("notesStatus");
const resultsEl = document.getElementById("notesResults");
const exportTools = document.getElementById("notesExportTools");
const exportJson = document.getElementById("exportJson");
const exportJsonl = document.getElementById("exportJsonl");
const exportMarkdown = document.getElementById("exportMarkdown");
let lastNotes = [];
let requestedCorpusId = "";
let requestedTargetId = "";
let activeNotesController = null;
let activeNotesRequest = 0;
let recentlyChangedNoteId = "";
let archiveCorpora = [];

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

function noteTitle(note) {
  return cleanText(note.target_label || note.target_id || note.work_id || "Untitled note");
}

function noteContext(note) {
  return [
    corpusDisplayName(note.corpus_id),
    workDisplayName(note.corpus_id, note.work_id)
  ].filter(Boolean).join(" / ");
}

function splitTags(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function currentParams(format = "json") {
  const params = new URLSearchParams({ format });
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  const workId = workInput.value.trim();
  const tag = tagInput.value.trim().replace(/^#/, "");
  const reviewState = reviewSelect.value;
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  if (workId) params.set("work_id", workId);
  if (requestedTargetId) params.set("target_id", requestedTargetId);
  if (tag) params.set("tag", tag);
  if (reviewState) params.set("review_state", reviewState);
  return params;
}

function updateExportLinks() {
  exportJson.href = `/api/notes/export?${currentParams("json")}`;
  exportJsonl.href = `/api/notes/export?${currentParams("jsonl")}`;
  exportMarkdown.href = `/api/notes/export?${currentParams("markdown")}`;
}

function updateUrl() {
  const params = currentParams("json");
  params.delete("format");
  history.replaceState(null, "", params.toString() ? `/notes?${params}` : "/notes");
  updateNotesClearState();
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
    tagInput.value.trim() ||
    reviewSelect.value ||
    requestedTargetId
  );
}

function renderFilterChip(filterName, label, value) {
  return `<button type="button" class="filter-chip" data-filter="${escapeHtml(filterName)}" aria-label="Remove ${escapeHtml(label)} filter">
    <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
    <span aria-hidden="true">x</span>
  </button>`;
}

function updateNotesFilterSummary() {
  if (!activeFiltersEl) return;
  const chips = [];
  const query = queryInput.value.trim();
  const workId = workInput.value.trim();
  const tag = tagInput.value.trim().replace(/^#/, "");
  if (query) chips.push(renderFilterChip("query", "Text", query));
  if (corpusSelect.value) chips.push(renderFilterChip("corpus", "Corpus", selectedOptionText(corpusSelect)));
  if (workId) chips.push(renderFilterChip("work", "Work", workId));
  if (tag) chips.push(renderFilterChip("tag", "Tag", tag));
  if (reviewSelect.value) chips.push(renderFilterChip("review", "Status", selectedOptionText(reviewSelect)));
  if (requestedTargetId) chips.push(renderFilterChip("target", "Target", requestedTargetId));
  activeFiltersEl.hidden = chips.length === 0;
  activeFiltersEl.classList.toggle("has-filters", chips.length > 0);
  activeFiltersEl.innerHTML = chips.length
    ? `<span class="active-filters-label">Filters</span>${chips.join("")}`
    : "";
}

function updateNotesClearState(isBusy = form.classList.contains("is-loading")) {
  if (!notesClear) return;
  notesClear.disabled = isBusy || !hasActiveFilters();
  updateNotesFilterSummary();
}

function updateNotesListChrome(count = lastNotes.length) {
  const showTools = count > 0 || hasActiveFilters();
  form.hidden = !showTools;
  if (activeFiltersEl) {
    activeFiltersEl.hidden = !hasActiveFilters();
  }
}

function renderEmptyNotes() {
  const filtered = hasActiveFilters();
  const title = filtered ? "No notes match these filters." : "No notes yet.";
  const body = filtered ? "Clear filters, or broaden the work, tag, and status fields." : "";
  const clearAction = filtered
    ? '<button type="button" data-empty-action="clear-filters">Clear filters</button>'
    : "";
  const bodyMarkup = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<section class="empty empty-state">
    <h2>${escapeHtml(title)}</h2>
    ${bodyMarkup}
    <div class="empty-actions">
      ${clearAction}
      <a href="/search">Find work</a>
    </div>
  </section>`;
}

function clearNotesFilters() {
  queryInput.value = "";
  corpusSelect.value = "";
  workInput.value = "";
  tagInput.value = "";
  reviewSelect.value = "";
  requestedCorpusId = "";
  requestedTargetId = "";
  loadNotes();
  queryInput.focus();
}

function removeNotesFilter(filterName) {
  if (filterName === "query") {
    queryInput.value = "";
  } else if (filterName === "corpus") {
    corpusSelect.value = "";
    requestedCorpusId = "";
  } else if (filterName === "work") {
    workInput.value = "";
  } else if (filterName === "tag") {
    tagInput.value = "";
  } else if (filterName === "review") {
    reviewSelect.value = "";
  } else if (filterName === "target") {
    requestedTargetId = "";
  }
  loadNotes();
}

function setNotesBusy(isBusy) {
  form.classList.toggle("is-loading", isBusy);
  resultsEl.setAttribute("aria-busy", isBusy ? "true" : "false");
  if (notesSubmit) {
    notesSubmit.disabled = isBusy;
    notesSubmit.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
  updateNotesClearState(isBusy);
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

function renderNotesPending() {
  statusEl.textContent = "";
  resultsEl.innerHTML = `
    <article class="note-card notes-skeleton" aria-hidden="true">
      <span class="notes-skeleton-line title"></span>
      <span class="notes-skeleton-line"></span>
      <span class="notes-skeleton-line short"></span>
    </article>
    <article class="note-card notes-skeleton" aria-hidden="true">
      <span class="notes-skeleton-line title"></span>
      <span class="notes-skeleton-line"></span>
      <span class="notes-skeleton-line short"></span>
    </article>`;
  setNotesBusy(true);
}

function notesSummaryCounts(notes) {
  return notes.reduce((counts, note) => {
    const reviewState = note.review_state === "reviewed" ? "reviewed" : "raw";
    counts.total += 1;
    counts[reviewState] += 1;
    return counts;
  }, { total: 0, raw: 0, reviewed: 0 });
}

function notesSummaryButton(filter, label, count) {
  const selected = (filter || "") === reviewSelect.value;
  return `<button type="button" class="notes-summary-filter${selected ? " active" : ""}" data-notes-summary-filter="${escapeHtml(filter)}" aria-pressed="${selected ? "true" : "false"}">
    <span>${escapeHtml(label)}</span>
    <strong>${Number(count || 0).toLocaleString()}</strong>
  </button>`;
}

function renderNotesSummary(notes) {
  if (!notes.length) return "";
  const counts = notesSummaryCounts(notes);
  return `<nav class="notes-summary-nav" aria-label="Visible notes by status">
    ${notesSummaryButton("", "All", counts.total)}
    ${notesSummaryButton("raw", "Working", counts.raw)}
    ${notesSummaryButton("reviewed", "Saved", counts.reviewed)}
  </nav>`;
}

function renderNoteFooter(meta, actions) {
  const cleanMeta = cleanText(meta || "");
  if (!cleanMeta && !actions) return "";
  return `<footer class="note-footer">
    ${cleanMeta ? `<div class="note-meta">${escapeHtml(cleanMeta)}</div>` : "<div></div>"}
    ${actions ? `<div class="note-actions">${actions}</div>` : ""}
  </footer>`;
}

function renderNotes(notes) {
  lastNotes = notes;
  updateNotesListChrome(notes.length);
  if (exportTools) {
    exportTools.hidden = notes.length === 0;
    if (!notes.length) exportTools.open = false;
  }
  statusEl.textContent = "";
  resultsEl.innerHTML = notes.length
    ? renderNotesSummary(notes) + notes.map((note) => {
      const title = noteTitle(note);
      const context = noteContext(note);
      const tags = (note.tags || []).join(", ");
      const reviewState = note.review_state || "raw";
      const reviewAction = reviewState === "reviewed" ? "mark-raw" : "mark-reviewed";
      const reviewActionLabel = reviewState === "reviewed" ? "Reopen" : "Save";
      const quote = note.quote ? `<blockquote class="note-quote">${escapeHtml(cleanText(note.quote))}</blockquote>` : "";
      const href = note.url ? `<a href="${escapeHtml(note.url)}">${escapeHtml(title || "Open note target")}</a>` : escapeHtml(title || "Untitled note");
      const isRecent = note.id === recentlyChangedNoteId;
      const recentAttrs = isRecent ? ' tabindex="-1" aria-label="Recently changed note"' : "";
      const meta = [
        tags ? `# ${tags}` : ""
      ].filter(Boolean).join(" / ");
      const actions = `
          <button type="button" data-action="${escapeHtml(reviewAction)}">${escapeHtml(reviewActionLabel)}</button>
          <button type="button" data-action="edit">Edit</button>
          <details class="note-danger-actions">
            <summary>Delete</summary>
            <button type="button" data-action="delete">Confirm</button>
          </details>`;
      return `<article class="note-card${isRecent ? " is-recent" : ""}" data-note-id="${escapeHtml(note.id)}" data-corpus-id="${escapeHtml(note.corpus_id)}" data-review-state="${escapeHtml(reviewState)}"${recentAttrs}>
        <div class="note-title">
          ${href}
        </div>
        ${context ? `<div class="note-context">${escapeHtml(context)}</div>` : ""}
        <p class="note-text">${escapeHtml(cleanText(note.note))}</p>
        ${quote}
        ${renderNoteFooter(meta, actions)}
        <form class="note-edit-form" hidden>
          <label>Tags<input name="tags" value="${escapeHtml(tags)}" autocomplete="off"></label>
          <label>Note<textarea name="note" required>${escapeHtml(note.note)}</textarea></label>
          <div class="note-edit-actions">
            <button type="submit">Save</button>
            <button type="button" data-action="cancel">Cancel</button>
          </div>
        </form>
      </article>`;
    }).join("")
    : renderEmptyNotes();
  revealRecentlyChangedNote();
}

function noteById(noteId) {
  return lastNotes.find((note) => note.id === noteId);
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function revealRecentlyChangedNote() {
  if (!recentlyChangedNoteId) return;
  const recentNote = Array.from(resultsEl.querySelectorAll(".note-card"))
    .find((card) => card.dataset.noteId === recentlyChangedNoteId);
  if (!recentNote) {
    statusEl.textContent = "Recently changed note is hidden by the current filters.";
    return;
  }
  if (typeof recentNote.scrollIntoView === "function") {
    recentNote.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
  if (typeof recentNote.focus === "function") {
    try {
      recentNote.focus({ preventScroll: true });
    } catch {
      recentNote.focus();
    }
  }
  recentlyChangedNoteId = "";
}

function focusNoteEditor(card) {
  const formEl = card.querySelector(".note-edit-form");
  if (!formEl || formEl.hidden) return;
  const noteField = formEl.elements.note;
  if (typeof formEl.scrollIntoView === "function") {
    formEl.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
  if (noteField && typeof noteField.focus === "function") {
    window.setTimeout(() => {
      try {
        noteField.focus({ preventScroll: true });
      } catch {
        noteField.focus();
      }
      if (typeof noteField.setSelectionRange === "function") {
        const end = noteField.value.length;
        noteField.setSelectionRange(end, end);
      }
    }, 0);
  }
}

function resetNoteEditor(card) {
  const noteId = card.dataset.noteId || "";
  const note = noteById(noteId);
  const formEl = card.querySelector(".note-edit-form");
  if (note && formEl) {
    formEl.elements.note.value = note.note || "";
    formEl.elements.tags.value = (note.tags || []).join(", ");
  }
}

function toggleEditor(card, forceOpen = null) {
  const formEl = card.querySelector(".note-edit-form");
  const actionsEl = card.querySelector(".note-actions");
  const nextOpen = forceOpen === null ? formEl.hidden : forceOpen;
  formEl.hidden = !nextOpen;
  actionsEl.hidden = nextOpen;
  card.classList.toggle("is-editing", nextOpen);
  if (nextOpen) {
    focusNoteEditor(card);
  }
}

async function updateNote(noteId, corpusId, noteText, tags) {
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpus_id: corpusId,
      note: noteText,
      tags
    })
  });
  return response.ok;
}

async function updateReviewState(noteId, corpusId, reviewState) {
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpus_id: corpusId,
      review_state: reviewState
    })
  });
  return response.ok;
}

async function deleteNote(noteId, corpusId) {
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}?corpus_id=${encodeURIComponent(corpusId)}`, {
    method: "DELETE"
  });
  return response.ok;
}

async function loadCorpora() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) return;
    const payload = await response.json();
    archiveCorpora = payload.corpora || [];
    const current = corpusSelect.value || requestedCorpusId;
    corpusSelect.innerHTML = `<option value="">All</option>` + archiveCorpora
      .map((corpus) => `<option value="${escapeHtml(corpus.id)}">${escapeHtml(corpus.title)}</option>`)
      .join("");
    corpusSelect.value = current;
  } catch {
    // The hard-coded All option is enough when archive metadata is unavailable.
  }
}

async function loadNotes() {
  const requestId = activeNotesRequest + 1;
  activeNotesRequest = requestId;
  if (activeNotesController) {
    activeNotesController.abort();
    activeNotesController = null;
  }
  updateUrl();
  updateExportLinks();
  const controller = new AbortController();
  activeNotesController = controller;
  renderNotesPending();
  try {
    const response = await fetch(`/api/notes/export?${currentParams("json")}`, { signal: controller.signal });
    if (requestId !== activeNotesRequest) return;
    if (!response.ok) {
      statusEl.textContent = "Could not load notes.";
      resultsEl.innerHTML = "";
      return;
    }
    const payload = await response.json();
    renderNotes(payload.notes || []);
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    if (requestId === activeNotesRequest) {
      statusEl.textContent = "Could not load notes.";
      resultsEl.innerHTML = "";
    }
  } finally {
    if (requestId === activeNotesRequest) {
      activeNotesController = null;
      setNotesBusy(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadNotes();
});

if (notesClear) {
  notesClear.addEventListener("click", clearNotesFilters);
}

if (activeFiltersEl) {
  activeFiltersEl.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    removeNotesFilter(button.dataset.filter || "");
  });
}

resultsEl.addEventListener("click", async (event) => {
  const summaryFilter = event.target.closest("[data-notes-summary-filter]");
  if (summaryFilter) {
    reviewSelect.value = summaryFilter.dataset.notesSummaryFilter || "";
    loadNotes();
    return;
  }
  const emptyAction = event.target.closest("[data-empty-action]");
  if (emptyAction) {
    if (emptyAction.dataset.emptyAction === "clear-filters") {
      clearNotesFilters();
    }
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest(".note-card");
  if (!card) return;
  const noteId = card.dataset.noteId || "";
  const corpusId = card.dataset.corpusId || "";
  if (button.dataset.action === "edit") {
    toggleEditor(card, true);
    return;
  }
  if (button.dataset.action === "mark-reviewed" || button.dataset.action === "mark-raw") {
    const nextState = button.dataset.action === "mark-reviewed" ? "reviewed" : "raw";
    setActionButtonBusy(button, true);
    try {
      const ok = await updateReviewState(noteId, corpusId, nextState);
      if (ok) {
        recentlyChangedNoteId = noteId;
      }
      statusEl.textContent = ok
        ? (nextState === "reviewed" ? "Saved." : "Reopened.")
        : "Could not save.";
      await loadNotes();
    } finally {
      setActionButtonBusy(button, false);
    }
    return;
  }
  if (button.dataset.action === "cancel") {
    resetNoteEditor(card);
    toggleEditor(card, false);
    return;
  }
  if (button.dataset.action === "delete") {
    if (!window.confirm("Delete this note?")) return;
    setActionButtonBusy(button, true);
    try {
      const ok = await deleteNote(noteId, corpusId);
      statusEl.textContent = ok ? "Note deleted." : "Could not delete note.";
      await loadNotes();
    } finally {
      setActionButtonBusy(button, false);
    }
  }
});

resultsEl.addEventListener("keydown", (event) => {
  const editForm = event.target.closest(".note-edit-form");
  if (!editForm) return;
  const card = editForm.closest(".note-card");
  if (!card) return;
  if (event.key === "Escape") {
    event.preventDefault();
    resetNoteEditor(card);
    toggleEditor(card, false);
    statusEl.textContent = "Edit cancelled.";
    return;
  }
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    if (typeof editForm.requestSubmit === "function") {
      editForm.requestSubmit();
    }
  }
});

resultsEl.addEventListener("submit", async (event) => {
  const editForm = event.target.closest(".note-edit-form");
  if (!editForm) return;
  event.preventDefault();
  const card = editForm.closest(".note-card");
  const noteId = card.dataset.noteId || "";
  const corpusId = card.dataset.corpusId || "";
  const noteText = editForm.elements.note.value.trim();
  if (!noteText) {
    statusEl.textContent = "Note text is required.";
    editForm.elements.note.focus();
    return;
  }
  const saveButton = editForm.querySelector("button[type='submit']");
  setActionButtonBusy(saveButton, true);
  try {
    const ok = await updateNote(noteId, corpusId, noteText, splitTags(editForm.elements.tags.value));
    if (ok) {
      recentlyChangedNoteId = noteId;
    }
    statusEl.textContent = ok ? "Note updated." : "Could not update note.";
    await loadNotes();
  } finally {
    setActionButtonBusy(saveButton, false);
  }
});

for (const field of [queryInput, corpusSelect, workInput, tagInput, reviewSelect]) {
  field.addEventListener("change", loadNotes);
}

for (const field of [queryInput, workInput, tagInput]) {
  field.addEventListener("input", updateNotesClearState);
}

for (const field of [corpusSelect, reviewSelect]) {
  field.addEventListener("change", updateNotesClearState);
}

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
workInput.value = initialParams.get("work_id") || "";
tagInput.value = initialParams.get("tag") || "";
reviewSelect.value = initialParams.get("review_state") || "";
requestedCorpusId = initialParams.get("corpus_id") || "";
requestedTargetId = initialParams.get("target_id") || "";
corpusSelect.value = requestedCorpusId;

updateNotesClearState();
loadCorpora().then(loadNotes);
