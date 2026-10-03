let recentWorkPositionTimer = 0;
let pendingRecentWorkPosition = null;
let recentWorkSentenceId = "";
let recentWorkPositionTracking = false;

function clearRecentWorkPositionTimer() {
  window.clearTimeout(recentWorkPositionTimer);
  recentWorkPositionTimer = 0;
  pendingRecentWorkPosition = null;
}

function flushRecentWorkPosition() {
  if (pendingRecentWorkPosition) readerWorkStorage.storeRecentWork(pendingRecentWorkPosition);
  clearRecentWorkPositionTimer();
}

function resetRecentWorkPositionTracking() {
  recentWorkPositionTracking = false;
  recentWorkSentenceId = "";
  clearRecentWorkPositionTimer();
}

function scheduleRecentWorkPosition(node) {
  const id = node?.dataset.sentenceId || node?.id || "";
  if (!recentWorkPositionTracking || !id || id === recentWorkSentenceId) return;
  recentWorkSentenceId = id;
  window.clearTimeout(recentWorkPositionTimer);
  pendingRecentWorkPosition = recentWorkRecord(node);
  recentWorkPositionTimer = window.setTimeout(flushRecentWorkPosition, 650);
}

// Layout and anchor-restoration scrolling must not move a saved bookmark.
window.addEventListener("wheel", () => { recentWorkPositionTracking = true; }, { passive: true });
window.addEventListener("touchmove", () => { recentWorkPositionTracking = true; }, { passive: true });
window.addEventListener("pointerdown", (event) => {
  if (event.clientX >= document.documentElement.clientWidth) recentWorkPositionTracking = true;
}, { passive: true });
window.addEventListener("keydown", (event) => {
  if (["PageDown", "PageUp", "Home", "End", "ArrowDown", "ArrowUp", " "].includes(event.key)
    && !event.target?.closest?.("input,textarea,select,[contenteditable='true']")) recentWorkPositionTracking = true;
});

window.addEventListener("pagehide", flushRecentWorkPosition);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flushRecentWorkPosition(); });
