// Reader notes, citation, clipboard, and draft behavior.
function translationNoteDraftText(record) {
  if (!record) return "";
  const translation = cleanText(record.human_translation || record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  const lines = [];
  if (translation) {
    lines.push("번역", translation);
  }
  if (commentary) {
    if (lines.length) lines.push("");
    lines.push("해설", commentary);
  }
  return lines.join("\n");
}

function focusNoteComposer() {
  const focus = () => {
    if (isMobileStudyLayout() && noteForm && typeof noteForm.scrollIntoView === "function") {
      noteForm.scrollIntoView({
        block: "start",
        inline: "nearest",
        behavior: prefersReducedMotion() ? "auto" : "smooth"
      });
    }
    try {
      noteText.focus({ preventScroll: isMobileStudyLayout() });
    } catch (error) {
      noteText.focus();
    }
    if (noteText.setSelectionRange) {
      const noteEnd = noteText.value.length;
      noteText.setSelectionRange(noteEnd, noteEnd);
    }
  };
  window.requestAnimationFrame(focus);
}

function noteAlreadyIncludesDraft(draftText) {
  const normalize = (value) => String(value || "").replace(/\r\n?/g, "\n").trim();
  const draft = normalize(draftText);
  return Boolean(draft && normalize(noteText.value).includes(draft));
}

function draftNoteFromTranslation() {
  if (!selectedTranslationRecord) return;
  const draftText = translationNoteDraftText(selectedTranslationRecord);
  if (!draftText) return;
  const existingNote = noteText.value.trim();
  const alreadyDrafted = noteAlreadyIncludesDraft(draftText);
  if (!alreadyDrafted) {
    noteText.value = existingNote ? `${existingNote}\n\n---\n\n${draftText}` : draftText;
  }
  const existingTags = noteTags.value.split(",").map((item) => item.trim()).filter(Boolean);
  const mergedTags = Array.from(new Set([...existingTags, "ai-translation"]));
  noteTags.value = mergedTags.join(", ");
  lockedNoteTarget = selectedSentenceTargetSnapshot();
  updateNoteTargetPreview();
  saveNoteDraft();
  setStudyPanel("notes");
  setStudyPanelExpanded(true);
  focusNoteComposer();
  if (alreadyDrafted) {
    noteStatus.textContent = "이미 이 노트에 있습니다.";
    setTranslationStatus("이미 노트에 있습니다.");
    return;
  }
  noteStatus.textContent = existingNote ? "노트 초안에 추가했습니다." : "노트 초안을 만들었습니다.";
  setTranslationStatus(existingNote ? "노트 초안에 추가했습니다." : "노트 초안으로 옮겼습니다.");
}

function translationStudyCardText(record) {
  if (!record) return "";
  const lines = [];
  const source = cleanText(record.source_text_excerpt || selectedSentence?.text || "");
  const translation = cleanText(record.human_translation || record.translation || "");
  const commentary = cleanText(record.commentary || record.interpretation || "");
  if (source) {
    lines.push("원문", source);
  }
  if (translation) {
    lines.push("번역", translation);
  }
  if (commentary) {
    lines.push("해설", commentary);
  }
  return lines.join("\n");
}

function noteDraftPayload() {
  return {
    note: noteText.value,
    tags: noteTags.value,
    locked_target: lockedNoteTarget ? targetSnapshot(lockedNoteTarget) : null,
    updated_at: new Date().toISOString()
  };
}

function hasNoteDraftValue(payload) {
  return Boolean(cleanText(payload.note || "") || cleanText(payload.tags || ""));
}

function saveNoteDraft(autoLockTarget = true) {
  if (autoLockTarget && !lockedNoteTarget && hasNoteDraftValue({ note: noteText.value, tags: noteTags.value })) {
    lockedNoteTarget = targetSnapshot();
    updateNoteTargetPreview();
  }
  const payload = noteDraftPayload();
  readerWorkStorage.storeNoteDraft(
    NOTE_DRAFT_STORAGE_KEY,
    hasNoteDraftValue(payload) ? payload : null
  );
}

function scheduleNoteDraftSave() {
  if (!lockedNoteTarget && hasNoteDraftValue({ note: noteText.value, tags: noteTags.value })) {
    lockedNoteTarget = targetSnapshot();
    updateNoteTargetPreview();
  }
  window.clearTimeout(noteDraftSaveTimer);
  noteDraftSaveTimer = window.setTimeout(saveNoteDraft, 180);
}

function restoreNoteDraft() {
  const draft = readerWorkStorage.readNoteDraft(NOTE_DRAFT_STORAGE_KEY);
  if (!draft || !hasNoteDraftValue(draft)) return;
  try {
    if (draft.locked_target) {
      lockedNoteTarget = targetSnapshot(draft.locked_target);
      updateNoteTargetPreview();
    }
    if (!noteText.value) {
      noteText.value = draft.note || "";
    }
    if (!noteTags.value) {
      noteTags.value = draft.tags || "";
    }
    if (hasNoteDraftValue(noteDraftPayload())) {
      noteStatus.textContent = "노트 초안을 복원했습니다.";
    }
  } catch (error) {
    return;
  }
}

function clearNoteDraft() {
  window.clearTimeout(noteDraftSaveTimer);
  readerWorkStorage.clearNoteDraft(NOTE_DRAFT_STORAGE_KEY);
}

async function copyStudyCard() {
  if (!selectedTranslationRecord) {
    setTranslationStatus("번역을 먼저 선택하세요.", true);
    return;
  }
  setActionButtonBusy(copyStudyCardButton, true);
  try {
    await copyText(translationStudyCardText(selectedTranslationRecord));
    setTranslationStatus("학습 노트를 복사했습니다.");
  } catch (error) {
    setTranslationStatus("학습 노트를 복사하지 못했습니다.", true);
  } finally {
    setActionButtonBusy(copyStudyCardButton, false);
    updateSentenceControls();
  }
}

function updateCitationPreview() {
  const preview = citationPreviewText();
  citationPreview.textContent = preview;
  citationPreview.title = "인용 미리보기";
  citationPreview.setAttribute("aria-label", preview);
}

async function copyText(value) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (error) {
      // Fall through to the legacy copy path when browser permissions are strict.
    }
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-9999px";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.focus();
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) {
    throw new Error("클립보드 복사에 실패했습니다");
  }
}

function noteTimestamp(note) {
  const value = note.updated_at || note.created_at || "";
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

function sortedNotes(notes) {
  const items = Array.isArray(notes) ? [...notes] : [];
  const sortMode = noteSort ? noteSort.value : "recent";
  if (sortMode === "target") {
    return items.sort((a, b) => {
      const labelCompare = cleanText(a.target_label || "").localeCompare(cleanText(b.target_label || ""));
      return labelCompare || noteTimestamp(b) - noteTimestamp(a);
    });
  }
  return items.sort((a, b) => noteTimestamp(b) - noteTimestamp(a));
}

function updateNoteFilterClearState() {
  if (!noteFilterClear || !noteFilter) return;
  noteFilterClear.disabled = !noteFilter.value.trim();
}

function clearNoteFilter() {
  if (!noteFilter) return;
  noteFilter.value = "";
  updateNoteFilterClearState();
  if (noteStatus) {
    noteStatus.textContent = "노트 필터를 지웠습니다.";
  }
  loadNotes();
  noteFilter.focus();
}

function normalizedNoteReviewState(note) {
  return note && note.review_state === "reviewed" ? "reviewed" : "raw";
}

function noteReviewLabel(reviewState) {
  return reviewState === "reviewed" ? "저장됨" : "작성 중";
}

function noteReviewAction(reviewState) {
  return reviewState === "reviewed" ? "mark-raw-note" : "mark-reviewed-note";
}

function noteReviewActionLabel(reviewState) {
  return reviewState === "reviewed" ? "작성 중으로" : "저장";
}

function noteReviewActionTitle(reviewState) {
  return reviewState === "reviewed" ? "작성 중인 노트로 옮기기" : "저장한 노트로 표시";
}

function noteTargetHref(note) {
  const url = cleanText(note.url || "");
  if (url.startsWith("/work/") || url.startsWith("/read?") || url.startsWith("/source?")) {
    return url;
  }
  const targetId = cleanText(note.target_id || "");
  if (targetId && targetId !== "work") {
    return `${location.pathname}${location.search}#${encodeURIComponent(targetId)}`;
  }
  return location.pathname + location.search;
}

function renderNotesPending() {
  notesList.setAttribute("aria-busy", "true");
  if (noteListSummary) {
    noteListSummary.textContent = "노트 불러오는 중...";
  }
  notesList.innerHTML = `
    <div class="notes-list-pending" aria-hidden="true">
      <span class="notes-list-skeleton wide"></span>
      <span class="notes-list-skeleton"></span>
      <span class="notes-list-skeleton short"></span>
    </div>`;
}

function noteListSummaryText(items, filter = "") {
  if (!items.length) return "";
  return cleanText(filter) ? `필터 결과 ${items.length.toLocaleString()}개` : "";
}

function renderNotesUnavailable() {
  notesList.setAttribute("aria-busy", "false");
  syncNotesFilterToolsVisibility(0, "");
  if (noteListSummary) {
    noteListSummary.textContent = "";
  }
  notesList.innerHTML = '<div class="notes-empty">노트를 사용할 수 없습니다.</div>';
}

function syncNotesFilterToolsVisibility(itemCount, filter) {
  if (!notesFilterTools) return;
  const showTools = itemCount > 0 || Boolean(cleanText(filter || ""));
  notesFilterTools.hidden = !showTools;
  if (!showTools) {
    notesFilterTools.open = false;
  }
}

function renderNotesList(notes) {
  const items = sortedNotes(notes);
  const filter = noteFilter ? noteFilter.value.trim() : "";
  notesList.setAttribute("aria-busy", "false");
  syncNotesFilterToolsVisibility(items.length, filter);
  if (noteListSummary) {
    noteListSummary.textContent = noteListSummaryText(items, filter);
  }
  if (!items.length) {
    notesList.innerHTML = filter
      ? `<div class="notes-empty">
          <span>이 필터에 맞는 노트가 없습니다.</span>
          <div class="notes-empty-actions">
            <button type="button" data-notes-empty-action="clear-filter">필터 지우기</button>
          </div>
        </div>`
      : '<div class="notes-empty">아직 노트가 없습니다.</div>';
    return;
  }
  notesList.innerHTML = items.map((note) => {
    const tags = (note.tags || []).join(", ");
    const updated = note.updated_at ? ` / 수정 ${cleanText(note.updated_at)}` : "";
    const isRecent = note.id === recentlyChangedNoteId;
    const recentClass = isRecent ? " is-recent" : "";
    const recentAttrs = isRecent ? ' tabindex="-1" aria-label="최근 변경된 노트"' : "";
    const targetHref = noteTargetHref(note);
    const reviewState = normalizedNoteReviewState(note);
    const targetLabel = cleanText(note.target_label || "노트 대상");
    const sourceLinkLabel = `원문 읽기: ${targetLabel}`;
    const reviewActionTitle = noteReviewActionTitle(reviewState);
    return `<div class="note-item${recentClass}" data-note-id="${escapeHtml(note.id)}" data-note-tags="${escapeHtml(tags)}" data-review-state="${escapeHtml(reviewState)}"${recentAttrs}>
      <div class="note-item-title">
        <strong>${escapeHtml(targetLabel)}</strong>
        <span class="review-badge ${escapeHtml(reviewState)}">${escapeHtml(noteReviewLabel(reviewState))}</span>
      </div>
      <div class="note-text">${escapeHtml(cleanText(note.note))}</div>
      <small>${escapeHtml(cleanText(tags))}${escapeHtml(updated)}</small>
      <div class="note-actions">
        <a class="note-target-link" href="${escapeHtml(targetHref)}" aria-label="${escapeHtml(sourceLinkLabel)}" title="${escapeHtml(sourceLinkLabel)}">원문 읽기</a>
        <button type="button" data-action="${escapeHtml(noteReviewAction(reviewState))}" data-note-id="${escapeHtml(note.id)}" title="${escapeHtml(reviewActionTitle)}" aria-label="${escapeHtml(reviewActionTitle)}">${escapeHtml(noteReviewActionLabel(reviewState))}</button>
        <button type="button" data-action="edit-note" data-note-id="${escapeHtml(note.id)}">노트 수정</button>
        <details class="note-danger-actions">
          <summary>삭제</summary>
          <button type="button" data-action="delete-note" data-note-id="${escapeHtml(note.id)}">삭제</button>
        </details>
      </div>
    </div>`;
  }).join("");
}

function revealRecentNote(recentNote) {
  if (!recentNote) return;
  if (typeof recentNote.scrollIntoView === "function") {
    recentNote.scrollIntoView({
      block: isMobileStudyLayout() ? "center" : "nearest",
      inline: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth"
    });
  }
  if (typeof recentNote.focus === "function") {
    try {
      recentNote.focus({ preventScroll: true });
    } catch (error) {
      recentNote.focus();
    }
  }
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
  renderNotesPending();
  try {
    const response = await fetch(`/api/notes?${params}`);
    if (!response.ok) {
      renderNotesUnavailable();
      noteStatus.textContent = "노트를 불러오지 못했습니다.";
      return;
    }
    const payload = await response.json();
    renderNotesList(payload.notes || []);
    if (recentlyChangedNoteId) {
      const recentNote = Array.from(notesList.querySelectorAll(".note-item"))
        .find((item) => item.dataset.noteId === recentlyChangedNoteId);
      if (recentNote) {
        revealRecentNote(recentNote);
      } else if (filter && noteStatus) {
        noteStatus.textContent = "최근 변경한 노트가 현재 필터에 가려져 있습니다. 필터를 지우면 볼 수 있습니다.";
      }
    }
  } catch (error) {
    renderNotesUnavailable();
    noteStatus.textContent = "노트를 불러오지 못했습니다.";
  }
}

async function updateNote(noteId, note, tags) {
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id,
        note,
        tags
      })
    });
    if (!response.ok) return null;
    const payload = await response.json().catch(() => ({}));
    return payload.note || null;
  } catch (error) {
    return null;
  }
}

async function updateNoteReview(noteId, reviewState) {
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: researchData.corpus_id || researchData.author_id,
        review_state: reviewState
      })
    });
    if (!response.ok) return null;
    const payload = await response.json().catch(() => ({}));
    return payload.note || null;
  } catch (error) {
    return null;
  }
}

async function deleteNote(noteId) {
  const corpusId = encodeURIComponent(researchData.corpus_id || researchData.author_id || "");
  try {
    const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}?corpus_id=${corpusId}`, {
      method: "DELETE"
    });
    return response.ok;
  } catch (error) {
    return false;
  }
}
