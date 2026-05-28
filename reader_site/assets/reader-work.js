const researchData = JSON.parse(document.getElementById("researchData").textContent);
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");

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
  const corpusId = encodeURIComponent(researchData.corpus_id || researchData.author_id || "");
  const workId = encodeURIComponent(researchData.work_id || "");
  const response = await fetch(`/api/notes?corpus_id=${corpusId}&work_id=${workId}`);
  if (!response.ok) return;
  const payload = await response.json();
  notesList.innerHTML = payload.notes.length
    ? payload.notes.map((note) => `<div class="note-item"><strong>${escapeHtml(cleanText(note.target_label))}</strong><br>${escapeHtml(cleanText(note.note))}<br><small>${escapeHtml(cleanText((note.tags || []).join(", ")))}</small></div>`).join("")
    : "";
}

document.getElementById("copyCitation").addEventListener("click", async () => {
  await copyText(citationText());
  noteStatus.textContent = "Citation copied.";
});

document.getElementById("copyUrl").addEventListener("click", async () => {
  await copyText(currentTarget().url);
  noteStatus.textContent = "URL copied.";
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

window.addEventListener("hashchange", updateCitationPreview);
updateCitationPreview();
loadNotes();
