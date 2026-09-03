// Reader study-panel navigation and mobile panel behavior.
function setStudyPanel(name, focusTab = false) {
  const targetTab = studyTabs.find((tab) => tab.dataset.studyTab === name);
  if (targetTab?.hidden) {
    name = "translation";
  }
  let activeTab = null;
  studyTabs.forEach((tab) => {
    const active = tab.dataset.studyTab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.tabIndex = active ? 0 : -1;
    if (active) {
      activeTab = tab;
    }
    if (active && focusTab) {
      tab.focus();
    }
  });
  studyPanels.forEach((panel) => {
    const active = panel.dataset.studyPanel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  ensureActiveStudyTabVisible(activeTab);
  updateStudyPanelToggleLabel();
}

function visibleStudyTabs() {
  return studyTabs.filter((tab) => !tab.hidden);
}

function ensureActiveStudyTabVisible(tab) {
  if (!tab || !studyTabsContainer || !isMobileStudyLayout()) return;
  if (typeof tab.scrollIntoView !== "function") return;
  tab.scrollIntoView({
    block: "nearest",
    inline: "nearest",
    behavior: prefersReducedMotion() ? "auto" : "smooth"
  });
}

function activateStudyTabByIndex(index) {
  const tabs = visibleStudyTabs();
  if (!tabs.length) return;
  const nextIndex = (index + tabs.length) % tabs.length;
  const nextTab = tabs[nextIndex];
  setStudyPanel(nextTab.dataset.studyTab || "translation", true);
  setStudyPanelExpanded(true);
}

function storedStudyPanelExpanded() {
  return readerWorkStorage.readStudyPanelExpanded();
}

function rememberStudyPanelExpanded(expanded) {
  readerWorkStorage.storeStudyPanelExpanded(expanded);
}

function selectedSentencePositionLabel() {
  if (!selectedSentence) return "문장 선택";
  const index = sentenceIndex(selectedSentence.sentenceId);
  return index >= 0 ? `문장 ${index + 1} / ${totalSentenceCount()}` : selectedSentence.sentenceId;
}

function studyPanelToggleSummary() {
  if (!selectedSentence) return "문장 선택";
  if (translationCard && translationCard.classList.contains("is-loading")) {
    return "번역 중";
  }
  if (translationOutput && translationOutput.querySelector(".translation-error")) {
    return "다시 시도 필요";
  }
  if (selectedTranslationRecord) {
    return "번역 완료";
  }
  return "선택한 문장";
}

function collapsedStudyPanelAction() {
  const activeTab = studyTabs.find((tab) => tab.classList.contains("active") && !tab.hidden);
  const name = activeTab?.dataset.studyTab || "translation";
  if (name === "notes") return "노트 보기";
  if (name === "citation") return "인용 보기";
  if (name === "concepts") return "개념 보기";
  return "해설 보기";
}

function updateStudyPanelToggleLabel() {
  if (!studyPage || !studyPanelToggle) return;
  const expanded = studyPage.classList.contains("is-expanded");
  const action = expanded ? "본문 보기" : collapsedStudyPanelAction();
  const summary = studyPanelToggleSummary();
  studyPanelToggle.innerHTML = `
    <span class="study-panel-toggle-action">${escapeHtml(action)}</span>
    <span class="study-panel-toggle-summary">${escapeHtml(summary)}</span>`;
  studyPanelToggle.setAttribute("aria-label", `${action}. ${summary}`);
}

function setStudyPanelExpanded(expanded, remember = false) {
  if (!studyPage || !studyPanelToggle) return;
  studyPage.classList.toggle("is-expanded", expanded);
  studyPanelToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  updateStudyPanelToggleLabel();
  updateStudyPanelScrim();
  if (remember) {
    rememberStudyPanelExpanded(expanded);
  }
}

function returnToSelectedSourceAfterPanelCollapse() {
  if (!isMobileStudyLayout()) return;
  const node = selectedSentenceNode();
  if (!node) return;
  window.requestAnimationFrame(() => {
    scrollSentenceIntoView(node);
    updateReadingPosition(node);
    updateTranslationTargetViewState();
    flashSourceFocus(node);
  });
}

function collapseStudyPanelToSource(remember = false) {
  setStudyPanelExpanded(false, remember);
  returnToSelectedSourceAfterPanelCollapse();
}

function returnToReadingAfterNoteChange() {
  if (!isMobileStudyLayout() || !selectedSentenceNode()) return;
  collapseStudyPanelToSource(true);
}

function updateStudyPanelScrim() {
  if (!studyPanelScrim || !studyPage) return;
  const visible = isMobileStudyLayout() && studyPage.classList.contains("is-expanded");
  studyPanelScrim.hidden = !visible;
  studyPanelScrim.setAttribute("aria-hidden", visible ? "false" : "true");
}

function beginStudyPanelDrag(event) {
  if (!isMobileStudyLayout() || !studyPage || !studyPanelToggle) return;
  if (event.button !== undefined && event.button !== 0) return;
  studyPanelDragState = {
    pointerId: event.pointerId,
    startY: event.clientY,
    deltaY: 0,
    moved: false
  };
  studyPage.classList.add("is-dragging");
  if (studyPanelToggle.setPointerCapture) {
    studyPanelToggle.setPointerCapture(event.pointerId);
  }
}

function updateStudyPanelDrag(event) {
  if (!studyPanelDragState || event.pointerId !== studyPanelDragState.pointerId) return;
  studyPanelDragState.deltaY = event.clientY - studyPanelDragState.startY;
  if (Math.abs(studyPanelDragState.deltaY) > 8) {
    studyPanelDragState.moved = true;
    event.preventDefault();
  }
}

function finishStudyPanelDrag(event) {
  if (!studyPanelDragState || event.pointerId !== studyPanelDragState.pointerId) return;
  const { deltaY, moved } = studyPanelDragState;
  studyPanelDragState = null;
  studyPage.classList.remove("is-dragging");
  if (studyPanelToggle.releasePointerCapture) {
    try {
      studyPanelToggle.releasePointerCapture(event.pointerId);
    } catch (error) {
      // Pointer capture may already be released by the browser.
    }
  }
  if (!moved) return;
  ignoreNextStudyPanelToggleClick = true;
  if (deltaY <= -STUDY_PANEL_DRAG_THRESHOLD) {
    setStudyPanelExpanded(true, true);
  }
  if (deltaY >= STUDY_PANEL_DRAG_THRESHOLD) {
    collapseStudyPanelToSource(true);
  }
}

function cancelStudyPanelDrag() {
  studyPanelDragState = null;
  if (studyPage) {
    studyPage.classList.remove("is-dragging");
  }
}
