const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const previousSentenceButton = document.getElementById("previousSentence");
const nextSentenceButton = document.getElementById("nextSentence");
const regenerateSentenceButton = document.getElementById("regenerateSentence");
const markTranslationReviewedButton = document.getElementById("markTranslationReviewed");
const rejectTranslationButton = document.getElementById("rejectTranslation");
const draftTranslationNoteButton = document.getElementById("draftTranslationNote");
const readingModeButton = document.getElementById("readingMode");
const studyModeButton = document.getElementById("studyMode");
const translationStatus = document.getElementById("translationStatus");
const translationOutput = document.getElementById("translationOutput");
const exportReviewedTranslations = document.getElementById("exportReviewedTranslations");
const noteTags = document.getElementById("noteTags");
const noteText = document.getElementById("noteText");
const studyTabs = Array.from(document.querySelectorAll(".study-tab"));
const studyPanels = Array.from(document.querySelectorAll(".study-panel"));
const sentenceNodes = Array.from(document.querySelectorAll(".reader-sentence"));
const sourceBundleTargetTypes = new Set(["segment", "section", "paragraph", "verse"]);
let selectedSentence = null;
let selectedTranslationRecord = null;
let activeTranslationRequest = 0;
let translationMode = "reading";
let translationStatusTimer = null;

function cleanText(value) {
  return String(value || "").replace(/[#¶]/g, "").replace(/\s+/g, " ").trim();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStudyPanel(name) {
  studyTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.studyTab === name);
  });
  studyPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.studyPanel === name);
  });
}

function setTranslationMode(mode) {
  translationMode = mode === "study" ? "study" : "reading";
  readingModeButton.classList.toggle("active", translationMode === "reading");
  studyModeButton.classList.toggle("active", translationMode === "study");
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
}

function setTranslationStatus(message, persistent = false) {
  window.clearTimeout(translationStatusTimer);
  translationStatus.textContent = message || "";
  translationStatus.classList.toggle("visible", Boolean(message));
  if (message && !persistent) {
    translationStatusTimer = window.setTimeout(() => {
      translationStatus.textContent = "";
      translationStatus.classList.remove("visible");
    }, 3200);
  }
}

function sentenceIndex(sentenceId) {
  return sentenceNodes.findIndex((node) => (node.dataset.sentenceId || node.id) === sentenceId);
}

function updateSentenceControls() {
  const index = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const hasSelection = index >= 0;
  previousSentenceButton.disabled = !hasSelection || index === 0;
  nextSentenceButton.disabled = !hasSelection || index === sentenceNodes.length - 1;
  regenerateSentenceButton.disabled = !hasSelection;
  const hasRecord = Boolean(selectedTranslationRecord && selectedTranslationRecord.id);
  markTranslationReviewedButton.disabled = !hasRecord || selectedTranslationRecord.review_state === "reviewed";
  rejectTranslationButton.disabled = !hasRecord || selectedTranslationRecord.review_state === "rejected";
  draftTranslationNoteButton.disabled = !hasRecord;
}

function currentTarget() {
  const id = decodeURIComponent(location.hash.replace(/^#/, "")) || "work";
  const node = id === "work" ? null : document.getElementById(id);
  const label = node ? cleanText(node.dataset.label || node.textContent) : researchData.title;
  const type = node ? (node.dataset.targetType || researchData.default_target_type || "segment") : "work";
  const baseUrl = location.origin + location.pathname + location.search;
  const url = id === "work"
    ? baseUrl
    : baseUrl + "#" + encodeURIComponent(id);
  return { id, label, type, url };
}

function citationText() {
  const target = currentTarget();
  if (researchData.corpus_id === "bible") {
    const source = researchData.source_label || researchData.variant_id || "Bible";
    const label = target.id === "work" ? (researchData.citation_title || researchData.title) : target.label;
    return `${label}, ${source}. Personal Archive of Literature. ${target.url}`;
  }
  const position = target.id === "work" ? "" : `, ${target.label}`;
  const author = researchData.author || researchData.corpus_title || researchData.corpus_id;
  return `${author}, ${researchData.title} (${researchData.work_id})${position}. Personal Archive of Literature. ${target.url}`;
}

function sourceBundleUrl() {
  const target = currentTarget();
  if (!sourceBundleTargetTypes.has(target.type) || !target.id || target.id === "work") {
    return "";
  }
  const params = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    target_id: target.id
  });
  if (researchData.variant_id) {
    params.set("variant_id", researchData.variant_id);
  }
  return `${location.origin}/api/source-target?${params}`;
}

function sentenceFromNode(node) {
  if (!node || !node.classList || !node.classList.contains("reader-sentence")) {
    return null;
  }
  const parent = node.closest("[data-target-type='paragraph'], .verse");
  return {
    sentenceId: node.dataset.sentenceId || node.id || "",
    segmentId: node.dataset.segmentId || (parent ? parent.id : ""),
    label: cleanText(node.dataset.label || node.textContent),
    text: cleanText(node.textContent)
  };
}

function selectSentence(node, updateHash = true) {
  const sentence = sentenceFromNode(node);
  if (!sentence || !sentence.sentenceId || !sentence.segmentId) return;
  document.querySelectorAll(".reader-sentence.selected").forEach((item) => {
    item.classList.remove("selected");
  });
  node.classList.add("selected");
  selectedSentence = sentence;
  selectedTranslationRecord = null;
  const index = sentenceIndex(sentence.sentenceId);
  const position = index >= 0 ? `Sentence ${index + 1} of ${sentenceNodes.length}` : sentence.sentenceId;
  translationTarget.textContent = `${position} / ${sentence.sentenceId}`;
  updateSentenceControls();
  if (updateHash) {
    history.replaceState(null, "", `${location.pathname}${location.search}#${encodeURIComponent(sentence.sentenceId)}`);
  }
}

function selectSentenceFromHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!id) return;
  const node = document.getElementById(id);
  if (node && node.classList.contains("reader-sentence")) {
    selectSentence(node, false);
  }
}

function scrollSentenceIntoView(node) {
  if (!node || typeof node.scrollIntoView !== "function") return;
  node.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
}

function navigateSentence(delta) {
  if (!sentenceNodes.length) return;
  const currentIndex = selectedSentence ? sentenceIndex(selectedSentence.sentenceId) : -1;
  const nextIndex = Math.min(sentenceNodes.length - 1, Math.max(0, currentIndex + delta));
  const nextNode = sentenceNodes[nextIndex >= 0 ? nextIndex : 0];
  if (!nextNode) return;
  selectSentence(nextNode);
  scrollSentenceIntoView(nextNode);
  setStudyPanel("translation");
  requestSentenceTranslation(false);
}

function renderList(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<ul>${values.map((value) => `<li>${escapeHtml(cleanText(value))}</li>`).join("")}</ul>`;
}

function optionalCautions(record) {
  const cautions = renderList(record.cautions);
  if (!cautions) return "";
  return `<div class="translation-extra"><h3>Cautions</h3>${cautions}</div>`;
}

function renderTranslationRecord(record, cached) {
  selectedTranslationRecord = record;
  const reviewState = cleanText(record.review_state || "generated");
  translationOutput.hidden = false;
  translationOutput.classList.toggle("reading-mode", translationMode === "reading");
  translationOutput.classList.toggle("study-mode", translationMode === "study");
  translationOutput.innerHTML = `
    <div class="translation-review-state">${escapeHtml(reviewState)}${cached ? " / cached" : ""}</div>
    <div class="translation-extra">
      <h3>Original source</h3>
      <p>${escapeHtml(cleanText(record.source_text_excerpt || selectedSentence?.text || ""))}</p>
    </div>
    <h3>Translation</h3>
    <p class="translation-primary">${escapeHtml(cleanText(record.translation || ""))}</p>
    <div class="translation-commentary">
      <h3>Commentary</h3>
      <p>${escapeHtml(cleanText(record.commentary || record.interpretation || ""))}</p>
    </div>
    ${optionalCautions(record)}`;
  updateSentenceControls();
}

async function requestSentenceTranslation(regenerate = false) {
  if (!selectedSentence) {
    setTranslationStatus("Select a sentence first.", true);
    return;
  }
  const requestId = activeTranslationRequest + 1;
  activeTranslationRequest = requestId;
  const sentenceNode = document.getElementById(selectedSentence.sentenceId);
  setTranslationStatus(regenerate ? "Regenerating with Gemma..." : "Translating with Gemma...", true);
  regenerateSentenceButton.disabled = true;
  if (sentenceNode) {
    sentenceNode.classList.add("loading");
  }
  try {
    const response = await fetch("/api/sentence-translation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id || "",
        work_id: researchData.work_id || "",
        variant_id: researchData.variant_id || "",
        segment_id: selectedSentence.segmentId,
        sentence_id: selectedSentence.sentenceId,
        regenerate
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (requestId !== activeTranslationRequest) return;
    if (!response.ok || !payload.ok) {
      setTranslationStatus(payload.error || "Gemma runtime is not running.", true);
      return;
    }
    renderTranslationRecord(payload.record, payload.cached);
    setTranslationStatus(payload.cached ? "Loaded cached translation." : "Generated translation saved locally.");
  } finally {
    if (requestId === activeTranslationRequest) {
      updateSentenceControls();
    }
    if (sentenceNode) {
      sentenceNode.classList.remove("loading");
    }
  }
}

async function updateTranslationReview(reviewState) {
  if (!selectedTranslationRecord || !selectedTranslationRecord.id) {
    setTranslationStatus("No generated translation is selected.", true);
    return;
  }
  setTranslationStatus(reviewState === "reviewed" ? "Marking reviewed..." : "Updating review state...", true);
  const response = await fetch(`/api/sentence-translations/${encodeURIComponent(selectedTranslationRecord.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpus_id: researchData.corpus_id || researchData.author_id || "",
      review_state: reviewState
    })
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    setTranslationStatus(payload.error || "Could not update translation review.", true);
    return;
  }
  renderTranslationRecord(payload.record, true);
  setTranslationStatus(reviewState === "reviewed" ? "Translation marked reviewed." : "Translation rejected.");
}

function draftNoteFromTranslation() {
  if (!selectedTranslationRecord) return;
  const translation = cleanText(selectedTranslationRecord.translation || "");
  const commentary = cleanText(selectedTranslationRecord.commentary || selectedTranslationRecord.interpretation || "");
  const parts = [];
  if (translation) {
    parts.push(`Translation:\n${translation}`);
  }
  if (commentary) {
    parts.push(`Commentary:\n${commentary}`);
  }
  noteText.value = parts.join("\n\n");
  const existingTags = noteTags.value.split(",").map((item) => item.trim()).filter(Boolean);
  const mergedTags = Array.from(new Set([...existingTags, "ai-translation"]));
  noteTags.value = mergedTags.join(", ");
  setStudyPanel("notes");
  noteText.focus();
  setTranslationStatus("Translation drafted into Notes.");
}

function updateCitationPreview() {
  citationPreview.textContent = citationText();
}

async function copyText(value) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const area = document.createElement("textarea");
  area.value = value;
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

async function loadNotes() {
  const corpusId = researchData.corpus_id || researchData.author_id || "";
  const workId = researchData.work_id || "";
  const params = new URLSearchParams({ corpus_id: corpusId, work_id: workId });
  const filter = noteFilter ? noteFilter.value.trim() : "";
  if (filter.startsWith("#") && filter.length > 1) {
    params.set("tag", filter.slice(1));
  } else if (filter) {
    params.set("q", filter);
  }
  const response = await fetch(`/api/notes?${params}`);
  if (!response.ok) return;
  const payload = await response.json();
  notesList.innerHTML = payload.notes.length
    ? payload.notes.map((note) => {
      const tags = (note.tags || []).join(", ");
      const updated = note.updated_at ? ` / edited ${cleanText(note.updated_at)}` : "";
      return `<div class="note-item" data-note-id="${escapeHtml(note.id)}" data-note-tags="${escapeHtml(tags)}">
        <strong>${escapeHtml(cleanText(note.target_label))}</strong><br>
        <div class="note-text">${escapeHtml(cleanText(note.note))}</div>
        <small>${escapeHtml(cleanText(tags))}${escapeHtml(updated)}</small>
        <div class="note-actions">
          <button type="button" data-action="edit-note" data-note-id="${escapeHtml(note.id)}">Edit</button>
          <button type="button" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">Delete</button>
        </div>
      </div>`;
    }).join("")
    : "";
}

async function updateNote(noteId, note, tags) {
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpus_id: researchData.corpus_id || researchData.author_id,
      note,
      tags
    })
  });
  return response.ok;
}

async function deleteNote(noteId) {
  const corpusId = encodeURIComponent(researchData.corpus_id || researchData.author_id || "");
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}?corpus_id=${corpusId}`, {
    method: "DELETE"
  });
  return response.ok;
}

document.getElementById("copyCitation").addEventListener("click", async () => {
  await copyText(citationText());
  noteStatus.textContent = "Citation copied.";
});

document.getElementById("copyUrl").addEventListener("click", async () => {
  await copyText(currentTarget().url);
  noteStatus.textContent = "URL copied.";
});

copySourceBundleButton.addEventListener("click", async () => {
  const bundleUrl = sourceBundleUrl();
  if (!bundleUrl) {
    noteStatus.textContent = "Source bundle requires a section, paragraph, or verse target.";
    return;
  }
  await copyText(bundleUrl);
  noteStatus.textContent = "Source bundle URL copied.";
});

regenerateSentenceButton.addEventListener("click", () => requestSentenceTranslation(true));
previousSentenceButton.addEventListener("click", () => navigateSentence(-1));
nextSentenceButton.addEventListener("click", () => navigateSentence(1));
markTranslationReviewedButton.addEventListener("click", () => updateTranslationReview("reviewed"));
rejectTranslationButton.addEventListener("click", () => updateTranslationReview("rejected"));
draftTranslationNoteButton.addEventListener("click", draftNoteFromTranslation);
readingModeButton.addEventListener("click", () => setTranslationMode("reading"));
studyModeButton.addEventListener("click", () => setTranslationMode("study"));

studyTabs.forEach((tab) => {
  tab.addEventListener("click", () => setStudyPanel(tab.dataset.studyTab || "translation"));
});

document.querySelector(".reading-body").addEventListener("click", (event) => {
  const sentence = event.target.closest(".reader-sentence");
  if (sentence) {
    selectSentence(sentence);
    setStudyPanel("translation");
    requestSentenceTranslation(false);
  }
});

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const isTyping = target && (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
  if (isTyping || event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === "ArrowDown" || event.key === "j") {
    event.preventDefault();
    navigateSentence(1);
  }
  if (event.key === "ArrowUp" || event.key === "k") {
    event.preventDefault();
    navigateSentence(-1);
  }
});

noteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = currentTarget();
  const note = document.getElementById("noteText").value.trim();
  const tags = document.getElementById("noteTags").value.split(",").map((item) => item.trim()).filter(Boolean);
  const selection = window.getSelection ? window.getSelection().toString().trim() : "";
  const response = await fetch("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      corpus_id: researchData.corpus_id || researchData.author_id,
      work_id: researchData.work_id,
      variant_id: researchData.variant_id || "",
      target_id: target.id,
      target_type: target.type,
      target_label: target.label,
      quote: selection,
      note,
      tags
    })
  });
  if (response.ok) {
    noteForm.reset();
    noteStatus.textContent = "Note saved.";
    await loadNotes();
  } else {
    noteStatus.textContent = "Could not save note.";
  }
});

if (noteFilter) {
  noteFilter.addEventListener("input", () => {
    window.clearTimeout(noteFilter._timer);
    noteFilter._timer = window.setTimeout(loadNotes, 180);
  });
}

notesList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const noteId = button.dataset.noteId;
  const item = button.closest(".note-item");
  const currentText = item ? cleanText(item.querySelector(".note-text")?.textContent || "") : "";
  const currentTags = item ? cleanText(item.dataset.noteTags || "") : "";
  if (button.dataset.action === "edit-note") {
    const nextNote = window.prompt("Edit note", currentText);
    if (nextNote === null) return;
    const nextTags = window.prompt("Tags", currentTags) || "";
    const ok = await updateNote(noteId, nextNote.trim(), nextTags.split(",").map((value) => value.trim()).filter(Boolean));
    noteStatus.textContent = ok ? "Note updated." : "Could not update note.";
    await loadNotes();
  }
  if (button.dataset.action === "delete-note") {
    if (!window.confirm("Delete this note?")) return;
    const ok = await deleteNote(noteId);
    noteStatus.textContent = ok ? "Note deleted." : "Could not delete note.";
    await loadNotes();
  }
});

window.addEventListener("hashchange", () => {
  updateCitationPreview();
  selectSentenceFromHash();
  updateSentenceControls();
});

function initializeStudyCompanion() {
  setTranslationMode("reading");
  setStudyPanel("translation");
  const exportParams = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    review_state: "reviewed",
    format: "markdown"
  });
  exportReviewedTranslations.href = `/api/sentence-translations/export?${exportParams}`;
  const conceptsPanel = document.querySelector('[data-study-panel="concepts"]');
  if (conceptsPanel && !conceptsPanel.textContent.trim()) {
    conceptsPanel.innerHTML = '<section class="research-card"><h2>Concepts</h2><p class="source-notes">No concept notes for this work.</p></section>';
  }
  selectSentenceFromHash();
  if (selectedSentence) {
    requestSentenceTranslation(false);
  }
  updateSentenceControls();
}

updateCitationPreview();
initializeStudyCompanion();
loadNotes();
