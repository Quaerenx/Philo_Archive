// Reader controller core state and shared helpers.
const researchData = JSON.parse(document.getElementById("researchData").textContent);
const readerWorkStorage = window.ReaderWorkStorage;
if (!readerWorkStorage) {
  throw new Error("Reader work storage module is required.");
}
const readerWorkVirtual = window.ReaderWorkVirtual;
if (!readerWorkVirtual) {
  throw new Error("Reader virtual work module is required.");
}
const citationPreview = document.getElementById("citationPreview");
const noteForm = document.getElementById("noteForm");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");
const noteFilter = document.getElementById("noteFilter");
const noteFilterClear = document.getElementById("noteFilterClear");
const noteSort = document.getElementById("noteSort");
const noteListSummary = document.getElementById("noteListSummary");
const notesFilterTools = document.querySelector(".notes-filter-tools");
const noteTargetPreview = document.getElementById("noteTargetPreview");
const lockNoteTargetButton = document.getElementById("lockNoteTarget");
const copySourceBundleButton = document.getElementById("copySourceBundle");
const translationTarget = document.getElementById("translationTarget");
const readingPosition = document.getElementById("readingPosition");
const sentenceContextTools = document.querySelector(".sentence-context-tools");
const sentenceContext = document.getElementById("sentenceContext");
const previousSentenceButton = document.getElementById("previousSentence");
const nextSentenceButton = document.getElementById("nextSentence");
const nextUnstudiedSentenceButton = document.getElementById("nextUnstudiedSentence");
const nextReviewSentenceButton = document.getElementById("nextReviewSentence");
const regenerateSentenceButton = document.getElementById("regenerateSentence");
const markTranslationReviewedButton = document.getElementById("markTranslationReviewed");
const rejectTranslationButton = document.getElementById("rejectTranslation");
const copyStudyCardButton = document.getElementById("copyStudyCard");
const draftTranslationNoteButton = document.getElementById("draftTranslationNote");
const readingModeButton = document.getElementById("readingMode");
const studyModeButton = document.getElementById("studyMode");
const translationStatus = document.getElementById("translationStatus");
const gemmaRuntimeStatus = document.getElementById("gemmaRuntimeStatus");
const gemmaRuntimeStatusText = document.getElementById("gemmaRuntimeStatusText");
const gemmaRuntimeCheckButton = document.getElementById("gemmaRuntimeCheck");
const translationOutput = document.getElementById("translationOutput");
const translationUtility = document.querySelector(".translation-utility");
const translationCard = document.querySelector(".translation-card");
const studyPage = document.querySelector(".study-page");
const studyPanelToggle = document.getElementById("studyPanelToggle");
const studyPanelScrim = document.getElementById("studyPanelScrim");
const translationRecordsSummary = document.getElementById("translationRecordsSummary");
const studyProgress = document.getElementById("studyProgress");
const studyProgressText = document.getElementById("studyProgressText");
const continueStudyButton = document.getElementById("continueStudy");
const exportReviewedTranslations = document.getElementById("exportReviewedTranslations");
const exportAllTranslations = document.getElementById("exportAllTranslations");
const exportStudySession = document.getElementById("exportStudySession");
const studySessionSummary = document.getElementById("studySessionSummary");
const noteTags = document.getElementById("noteTags");
const noteText = document.getElementById("noteText");
const noteSaveButton = noteForm.querySelector("button[type='submit']");
const studyTabsContainer = document.querySelector(".study-tabs");
const studyTabs = Array.from(document.querySelectorAll(".study-tab"));
const studyPanels = Array.from(document.querySelectorAll(".study-panel"));
const readingBody = document.querySelector(".reading-body");
let sentenceNodes = [];
const sentenceNodeById = new Map();
const sentenceIndexById = new Map();
const sentenceNodeByPosition = new Map();
const sourceBundleTargetTypes = new Set(["segment", "section", "paragraph", "verse"]);
let selectedSentence = null;
let selectedTranslationRecord = null;
let activeTranslationRequest = 0;
let activeTranslationController = null;
let activeTranslationTargetKey = "";
let pendingTranslationRegenerate = false;
let translationMode = "reading";
let translationStatusTimer = null;
let translationRevealTimer = 0;
let sentenceRevealTimer = 0;
let sourceFocusTimer = 0;
let translationReviewFlashTimer = 0;
let sentenceReviewFlashTimer = 0;
let translationSentenceStates = new Map();
let translationSentenceStatesLoaded = false;
let gemmaRuntimeCheckController = null;
let gemmaRuntimePollTimer = 0;
let gemmaRuntimeState = "checking";
let recentlyChangedNoteId = "";
let activeReadingCueNode = null;
let readingPositionRefreshHandle = 0;
let noteDraftSaveTimer = 0;
let lockedNoteTarget = null;
let studyPanelDragState = null;
let ignoreNextStudyPanelToggleClick = false;
let pendingActionConfirmation = "";
let actionConfirmationTimer = 0;
const visibleSentenceNodes = new Set();
const STUDY_PANEL_DRAG_THRESHOLD = 36;
const ACTION_CONFIRM_MS = 4500;
const GEMMA_RUNTIME_POLL_MS = 2000;
const GEMMA_RUNTIME_COMMAND = ".\\run_reader_with_gemma.ps1";
const TRANSLATION_STATE_LABELS = {
  generated: "검토할 번역",
  reviewed: "저장한 번역",
  rejected: "제외한 번역"
};
const TRANSLATION_REVIEW_CHIP_LABELS = {
  generated: "검토",
  reviewed: "저장됨",
  rejected: "제외됨"
};
const TRANSLATION_QUALITY_LABELS = {
  critic_pass: "자동 검증 통과",
  critic_pass_after_revision: "자동 수정 후 통과",
  needs_human_review: "자동 검증: 확인 필요",
  critic_error: "자동 검증 실패"
};
const TRANSLATION_REVIEW_CHIP_HINTS = {
  generated: "검토할 번역",
  reviewed: "저장된 번역",
  rejected: "제외된 번역"
};
const TRANSLATION_STATE_SHORT = {
  generated: "AI",
  reviewed: "저장",
  rejected: "제외"
};
let virtualWork = null;
let virtualDocument = null;
let virtualChunkDescriptors = [];

function initializeVirtualWork() {
  virtualWork = readerWorkVirtual.create({
    researchData,
    readingBody,
    getReadingCueTargetLine: readingCueTargetLine,
    getSelectedSentenceNode: selectedSentenceNode,
    onContentChanged: () => {
      refreshSentenceNodeIndex();
      if (selectedSentence) {
        sentenceNodeById.get(selectedSentence.sentenceId)?.classList.add("selected");
      }
    },
    onViewportChanged: scheduleReadingPositionRefresh,
  });
  virtualDocument = virtualWork.document;
  virtualChunkDescriptors = virtualWork.descriptors;
}
const NOTE_DRAFT_STORAGE_KEY = readerWorkStorage.noteDraftStorageKey(researchData);

function cleanText(value) {
  return String(value || "").replace(/[#¶]/g, "").replace(/\s+/g, " ").trim();
}

function totalSentenceCount() {
  return virtualDocument
    ? Number(virtualDocument.total_sentences || 0)
    : sentenceNodes.length;
}

function sentencePosition(node) {
  if (!node) return 0;
  const explicitPosition = Number(node.dataset.sentencePosition || 0);
  if (explicitPosition > 0) return explicitPosition;
  const sentenceId = node.dataset.sentenceId || node.id || "";
  const index = sentenceIndexById.get(sentenceId);
  return Number.isInteger(index) ? index + 1 : 0;
}

function refreshSentenceNodeIndex() {
  sentenceNodes = Array.from(readingBody?.querySelectorAll(".reader-sentence") || []);
  if (virtualDocument) {
    sentenceNodes.sort((left, right) => sentencePosition(left) - sentencePosition(right));
  }
  sentenceNodeById.clear();
  sentenceIndexById.clear();
  sentenceNodeByPosition.clear();
  sentenceNodes.forEach((node, localIndex) => {
    const sentenceId = node.dataset.sentenceId || node.id || "";
    const position = virtualDocument
      ? Number(node.dataset.sentencePosition || 0)
      : localIndex + 1;
    if (!sentenceId || position <= 0) return;
    sentenceNodeById.set(sentenceId, node);
    sentenceIndexById.set(sentenceId, position - 1);
    sentenceNodeByPosition.set(position, node);
    const storedState = translationSentenceStates.get(sentenceId);
    if (storedState) {
      applySentenceTranslationVisualState(node, storedState, false);
    }
  });
}

function currentWorkHref() {
  return `${location.pathname}${location.search}${location.hash || ""}`;
}

function syncConceptReturnLinks() {
  const returnHref = currentWorkHref();
  const returnLabel = cleanText(researchData.title || document.title || researchData.work_id || "읽던 문서");
  document.querySelectorAll(".concept-link").forEach((link) => {
    try {
      const url = new URL(link.getAttribute("href") || "", location.origin);
      if (url.pathname !== "/search") return;
      url.searchParams.set("from", returnHref);
      url.searchParams.set("from_label", returnLabel);
      link.setAttribute("href", `${url.pathname}${url.search}`);
    } catch (error) {
      return;
    }
  });
}

function rememberRecentWork() {
  readerWorkStorage.storeRecentWork({
    href: currentWorkHref(),
    title: cleanText(researchData.title || document.title || researchData.work_id || "현재 문서"),
    corpus_id: cleanText(researchData.corpus_id || researchData.author_id || ""),
    corpus_title: cleanText(researchData.corpus_title || ""),
    work_id: cleanText(researchData.work_id || ""),
    updated_at: new Date().toISOString()
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
