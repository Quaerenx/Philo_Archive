const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const regenerateSentenceButton = document.getElementById("regenerateSentence");
const translationStatus = document.getElementById("translationStatus");
const translationOutput = document.getElementById("translationOutput");
const sourceBundleTargetTypes = new Set(["segment", "section", "paragraph", "verse"]);
let selectedSentence = null;
let activeTranslationRequest = 0;

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
  translationTarget.textContent = `${sentence.sentenceId} / ${sentence.text}`;
  regenerateSentenceButton.disabled = false;
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

function renderList(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return `<ul>${values.map((value) => `<li>${escapeHtml(cleanText(value))}</li>`).join("")}</ul>`;
}

function optionalCautions(record) {
  const cautions = renderList(record.cautions);
  if (!cautions) return "";
  return `<h3>Cautions</h3>${cautions}`;
}

function renderTranslationRecord(record, cached) {
  translationOutput.hidden = false;
  translationOutput.innerHTML = `
    <h3>Original source</h3>
    <p>${escapeHtml(cleanText(record.source_text_excerpt || selectedSentence?.text || ""))}</p>
    <h3>Translation</h3>
    <p class="translation-primary">${escapeHtml(cleanText(record.translation || ""))}</p>
    <h3>Commentary</h3>
    <p>${escapeHtml(cleanText(record.commentary || record.interpretation || ""))}</p>
    ${optionalCautions(record)}`;
}

async function requestSentenceTranslation(regenerate = false) {
  if (!selectedSentence) {
    translationStatus.textContent = "Select a sentence first.";
    return;
  }
  const requestId = activeTranslationRequest + 1;
  activeTranslationRequest = requestId;
  const sentenceNode = document.getElementById(selectedSentence.sentenceId);
  translationStatus.textContent = regenerate ? "Regenerating with Gemma..." : "Translating with Gemma...";
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
      translationStatus.textContent = payload.error || "Gemma runtime is not running.";
      return;
    }
    renderTranslationRecord(payload.record, payload.cached);
    translationStatus.textContent = payload.cached ? "Loaded cached translation." : "Generated translation saved locally.";
  } finally {
    if (requestId === activeTranslationRequest) {
      regenerateSentenceButton.disabled = false;
    }
    if (sentenceNode) {
      sentenceNode.classList.remove("loading");
    }
  }
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
      const updated = note.updated_at ? ` · edited ${cleanText(note.updated_at)}` : "";
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

document.querySelector(".reading-body").addEventListener("click", (event) => {
  const sentence = event.target.closest(".reader-sentence");
  if (sentence) {
    selectSentence(sentence);
    requestSentenceTranslation(false);
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
});
updateCitationPreview();
selectSentenceFromHash();
loadNotes();
