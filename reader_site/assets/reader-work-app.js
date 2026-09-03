// Reader event bindings and application bootstrap.

document.getElementById("copyCitation").addEventListener("click", async () => {
  await copyText(citationText());
  noteStatus.textContent = "인용을 복사했습니다.";
});

document.getElementById("copyUrl").addEventListener("click", async () => {
  await copyText(currentTarget().url);
  noteStatus.textContent = "URL을 복사했습니다.";
});

copySourceBundleButton.addEventListener("click", async () => {
  const bundleUrl = sourceBundleUrl();
  if (!bundleUrl) {
    noteStatus.textContent = "원문 묶음은 섹션, 문단, 절 대상에서 사용할 수 있습니다.";
    return;
  }
  await copyText(bundleUrl);
  noteStatus.textContent = "원문 묶음 URL을 복사했습니다.";
});

regenerateSentenceButton.addEventListener("click", () => handleConfirmedAction("regenerate"));
previousSentenceButton.addEventListener("click", () => navigateSentence(-1));
nextSentenceButton.addEventListener("click", () => navigateSentence(1));
if (nextUnstudiedSentenceButton) {
  nextUnstudiedSentenceButton.addEventListener("click", navigateToNextUnstudiedSentence);
}
if (nextReviewSentenceButton) {
  nextReviewSentenceButton.addEventListener("click", navigateToNextReviewSentence);
}
if (continueStudyButton) {
  continueStudyButton.addEventListener("click", continueStudy);
}
markTranslationReviewedButton.addEventListener("click", () => updateTranslationReview("reviewed"));
rejectTranslationButton.addEventListener("click", () => handleConfirmedAction("reject"));
copyStudyCardButton.addEventListener("click", copyStudyCard);
draftTranslationNoteButton.addEventListener("click", draftNoteFromTranslation);
readingModeButton.addEventListener("click", () => setTranslationMode("reading"));
studyModeButton.addEventListener("click", () => setTranslationMode("study"));
if (gemmaRuntimeCheckButton) {
  gemmaRuntimeCheckButton.addEventListener("click", () => checkGemmaRuntimeStatus(true));
}
lockNoteTargetButton.addEventListener("click", () => {
  if (lockedNoteTarget) {
    unlockNoteTarget();
  } else {
    lockCurrentNoteTarget();
  }
});
if (studyPanelToggle && studyPage) {
  studyPanelToggle.addEventListener("click", () => {
    if (ignoreNextStudyPanelToggleClick) {
      ignoreNextStudyPanelToggleClick = false;
      return;
    }
    const wasExpanded = studyPage.classList.contains("is-expanded");
    if (wasExpanded) {
      collapseStudyPanelToSource(true);
    } else {
      setStudyPanelExpanded(true, true);
    }
  });
  studyPanelToggle.addEventListener("pointerdown", beginStudyPanelDrag);
  studyPanelToggle.addEventListener("pointermove", updateStudyPanelDrag);
  studyPanelToggle.addEventListener("pointerup", finishStudyPanelDrag);
  studyPanelToggle.addEventListener("pointercancel", cancelStudyPanelDrag);
}

if (studyPanelScrim) {
  studyPanelScrim.addEventListener("click", () => {
    collapseStudyPanelToSource(true);
  });
}

if (sentenceContext) {
  sentenceContext.addEventListener("click", (event) => {
    const item = event.target.closest("[data-sentence-id]");
    if (!item) return;
    const sentenceId = item.dataset.sentenceId || "";
    const node = document.getElementById(sentenceId);
    if (!node || !node.classList.contains("reader-sentence")) return;
    const wasSelected = selectedSentence && selectedSentence.sentenceId === sentenceId;
    selectSentence(node);
    scrollSentenceIntoView(node);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    keepSentenceAboveStudyPanel(node);
    if (!wasSelected || !selectedTranslationRecord) {
      requestSentenceTranslation(false);
    }
  });
}

if (translationTarget) {
  translationTarget.addEventListener("click", (event) => {
    const jumpButton = event.target.closest("[data-selected-source-jump]");
    if (!jumpButton || !selectedSentence) return;
    focusSelectedSourceSentence();
  });
}

if (readingPosition) {
  readingPosition.addEventListener("click", (event) => {
    const button = event.target.closest("[data-reading-cue-select]");
    if (!button) return;
    studyReadingCueSentence();
  });
}

translationOutput.addEventListener("click", (event) => {
  const quickAction = event.target.closest("[data-translation-quick-action]");
  if (quickAction) {
    const action = quickAction.dataset.translationQuickAction || "";
    if (action === "next-sentence") {
      navigateSentence(1);
      return;
    }
    if (action === "mark-reviewed") {
      updateTranslationReview("reviewed", quickAction);
      return;
    }
    if (action === "draft-note") {
      draftNoteFromTranslation();
      return;
    }
    if (action === "continue") {
      continueStudy();
      return;
    }
  }
  const sourceJump = event.target.closest("[data-selected-source-jump]");
  if (sourceJump) {
    focusSelectedSourceSentence();
    return;
  }
  const cancel = event.target.closest("[data-translation-cancel]");
  if (cancel) {
    cancelTranslationRequest();
    return;
  }
  const retry = event.target.closest("[data-translation-retry]");
  if (retry) {
    requestSentenceTranslation(retry.dataset.translationRetry === "regenerate");
    return;
  }
  const copyRuntime = event.target.closest("[data-translation-copy-runtime]");
  if (copyRuntime) {
    copyText(GEMMA_RUNTIME_COMMAND)
      .then(() => setTranslationStatus("시작 명령을 복사했습니다."))
      .catch(() => setTranslationStatus("시작 명령을 복사하지 못했습니다.", true));
    return;
  }
  const checkRuntime = event.target.closest("[data-translation-check-runtime]");
  if (checkRuntime) {
    checkGemmaRuntimeStatus(true);
    return;
  }
  const jump = event.target.closest("[data-translation-jump]");
  if (jump) {
    scrollTranslationSectionIntoView(jump.dataset.translationJump || "");
    return;
  }
  const sessionTarget = event.target.closest("[data-session-preview-target]");
  if (sessionTarget) {
    openSessionPreviewTarget(sessionTarget.dataset.sessionPreviewTarget || "");
    return;
  }
  const sessionToggle = event.target.closest("[data-session-preview-toggle]");
  if (sessionToggle) {
    toggleSessionPreviewGroup(sessionToggle);
    return;
  }
  const sessionCopy = event.target.closest("[data-session-preview-copy]");
  if (sessionCopy) {
    copyStudySessionMarkdown(sessionCopy);
  }
});

studyTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setStudyPanel(tab.dataset.studyTab || "translation");
    setStudyPanelExpanded(true);
  });
});

if (studyTabsContainer) {
  studyTabsContainer.addEventListener("keydown", (event) => {
    const tabs = visibleStudyTabs();
    const currentIndex = tabs.indexOf(event.target);
    if (currentIndex < 0) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      activateStudyTabByIndex(currentIndex + 1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      activateStudyTabByIndex(currentIndex - 1);
    }
    if (event.key === "Home") {
      event.preventDefault();
      activateStudyTabByIndex(0);
    }
    if (event.key === "End") {
      event.preventDefault();
      activateStudyTabByIndex(tabs.length - 1);
    }
  });
}

readingBody.addEventListener("click", (event) => {
  const retryChunk = event.target.closest("[data-load-work-chunk]");
  if (retryChunk) {
    const chunkIndex = Number(retryChunk.dataset.loadWorkChunk);
    virtualWork.ensureChunk(chunkIndex).catch(() => {});
    return;
  }
  const sentence = event.target.closest(".reader-sentence");
  if (sentence) {
    const sentenceId = sentence.dataset.sentenceId || sentence.id || "";
    const wasSelected = selectedSentence && selectedSentence.sentenceId === sentenceId;
    selectSentence(sentence);
    setStudyPanel("translation");
    setStudyPanelExpanded(true);
    keepSentenceAboveStudyPanel(sentence);
    if (!wasSelected || !selectedTranslationRecord) {
      requestSentenceTranslation(false);
    }
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
  if (event.key === "Escape" && hasPendingActionConfirmation()) {
    event.preventDefault();
    clearActionConfirmations();
    setTranslationStatus("동작을 취소했습니다.");
    return;
  }
  if (event.key === "Escape" && isMobileStudyLayout() && studyPage?.classList.contains("is-expanded")) {
    event.preventDefault();
    collapseStudyPanelToSource(true);
    return;
  }
  if (event.key.toLowerCase() === "s") {
    event.preventDefault();
    focusSelectedSourceSentence();
    return;
  }
  if (
    (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "j" || event.key === "k") &&
    target?.closest?.(".study-page")
  ) {
    return;
  }
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
  setActionButtonBusy(noteSaveButton, true);
  const target = noteTargetForSave();
  const note = document.getElementById("noteText").value.trim();
  const tags = document.getElementById("noteTags").value.split(",").map((item) => item.trim()).filter(Boolean);
  const selection = window.getSelection ? window.getSelection().toString().trim() : "";
  noteStatus.textContent = "노트 저장 중...";
  try {
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
      const payload = await response.json().catch(() => ({}));
      recentlyChangedNoteId = payload.note?.id || "";
      clearNoteDraft();
      noteForm.reset();
      unlockNoteTarget(false);
      noteStatus.textContent = "노트를 저장하고 표시했습니다.";
      await loadNotes();
      await loadStudySessionSummary();
      returnToReadingAfterNoteChange();
    } else {
      noteStatus.textContent = "노트를 저장하지 못했습니다.";
    }
  } catch (error) {
    noteStatus.textContent = "노트를 저장하지 못했습니다.";
  } finally {
    setActionButtonBusy(noteSaveButton, false);
  }
});

if (noteFilter) {
  noteFilter.addEventListener("input", () => {
    window.clearTimeout(noteFilter._timer);
    updateNoteFilterClearState();
    noteFilter._timer = window.setTimeout(loadNotes, 180);
  });
  updateNoteFilterClearState();
}

if (noteFilterClear && noteFilter) {
  noteFilterClear.addEventListener("click", () => {
    clearNoteFilter();
  });
}

if (noteSort) {
  noteSort.addEventListener("change", loadNotes);
}

[noteText, noteTags].forEach((field) => {
  if (!field) return;
  field.addEventListener("input", scheduleNoteDraftSave);
});

notesList.addEventListener("click", async (event) => {
  const emptyAction = event.target.closest("button[data-notes-empty-action]");
  if (emptyAction) {
    if (emptyAction.dataset.notesEmptyAction === "clear-filter") {
      clearNoteFilter();
    }
    return;
  }
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const noteId = button.dataset.noteId;
  const item = button.closest(".note-item");
  const currentText = item ? cleanText(item.querySelector(".note-text")?.textContent || "") : "";
  const currentTags = item ? cleanText(item.dataset.noteTags || "") : "";
  if (button.dataset.action === "mark-reviewed-note" || button.dataset.action === "mark-raw-note") {
    const nextState = button.dataset.action === "mark-reviewed-note" ? "reviewed" : "raw";
    setActionButtonBusy(button, true);
    const updatedNote = await updateNoteReview(noteId, nextState);
    noteStatus.textContent = updatedNote
      ? (nextState === "reviewed" ? "노트를 저장했습니다." : "작성 중으로 옮겼습니다.")
      : "노트를 업데이트하지 못했습니다.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
      returnToReadingAfterNoteChange();
    }
    setActionButtonBusy(button, false);
    return;
  }
  if (button.dataset.action === "edit-note") {
    const nextNote = window.prompt("노트 수정", currentText);
    if (nextNote === null) return;
    const nextTags = window.prompt("태그 수정", currentTags) || "";
    setActionButtonBusy(button, true);
    const updatedNote = await updateNote(noteId, nextNote.trim(), nextTags.split(",").map((value) => value.trim()).filter(Boolean));
    noteStatus.textContent = updatedNote ? "노트를 수정하고 표시했습니다." : "노트를 업데이트하지 못했습니다.";
    if (updatedNote) {
      recentlyChangedNoteId = updatedNote.id || noteId;
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
  }
  if (button.dataset.action === "delete-note") {
    if (!window.confirm("이 노트를 삭제할까요?")) return;
    setActionButtonBusy(button, true);
    const ok = await deleteNote(noteId);
    noteStatus.textContent = ok ? "노트를 삭제했습니다." : "노트를 삭제하지 못했습니다.";
    if (ok) {
      if (recentlyChangedNoteId === noteId) {
        recentlyChangedNoteId = "";
      }
      await loadNotes();
      await loadStudySessionSummary();
    }
    setActionButtonBusy(button, false);
  }
});

window.addEventListener("hashchange", async () => {
  await selectSentenceFromHash();
  syncTargetDependentViews();
  updateSentenceControls();
  syncConceptReturnLinks();
});

async function initializeStudyCompanion() {
  rememberRecentWork();
  setTranslationMode("reading");
  restoreNoteDraft();
  setStudyPanelExpanded(storedStudyPanelExpanded());
  setStudyPanel("translation");
  renderTranslationEmptyState();
  syncConceptReturnLinks();
  const exportParams = new URLSearchParams({
    corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "",
    review_state: "reviewed",
    format: "markdown"
  });
  exportReviewedTranslations.href = `/api/sentence-translations/export?${exportParams}`;
  const exportAllParams = new URLSearchParams(exportParams);
  exportAllParams.set("review_state", "all");
  if (exportAllTranslations) {
    exportAllTranslations.href = `/api/sentence-translations/export?${exportAllParams}`;
  }
  if (exportStudySession) {
    exportStudySession.href = studySessionExportUrl("markdown");
    exportStudySession.title = "이 문서의 학습 기록 다운로드";
  }
  syncConceptsPanelAvailability();
  await selectSentenceFromHash();
  if (selectedSentence) {
    requestSentenceTranslation(false);
  }
  updateSentenceControls();
  syncTargetDependentViews();
  updateStudyPanelScrim();
  checkGemmaRuntimeStatus(false);
  loadTranslationRecordsSummary();
  loadStudySessionSummary();
}

function syncConceptsPanelAvailability() {
  const conceptsPanel = document.querySelector('[data-study-panel="concepts"]');
  const conceptsTab = document.querySelector('[data-study-tab="concepts"]');
  if (!conceptsPanel || !conceptsTab) return;
  const hasConcepts = Boolean(conceptsPanel.textContent.trim());
  if (hasConcepts) return;
  conceptsTab.hidden = true;
  conceptsTab.classList.remove("active");
  conceptsTab.setAttribute("aria-selected", "false");
  conceptsTab.tabIndex = -1;
  conceptsPanel.hidden = true;
  conceptsPanel.classList.remove("active");
}

if (!researchData.print_view) {
  initializeVirtualWork();
  virtualWork.initialize();
  initializeStudyCompanion();
  initializeReadingPositionTracker();
  loadNotes();
}
