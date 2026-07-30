(function (global) {
  "use strict";

  const RECENT_WORK_STORAGE_KEY = "philo.reader.recentWork";
  const STUDY_PANEL_STORAGE_KEY = "philo.reader.studyPanelExpanded";
  const NOTE_DRAFT_STORAGE_PREFIX = "philo.reader.noteDraft";

  function storageFor(name) {
    try {
      return global[name] || null;
    } catch (error) {
      return null;
    }
  }

  function readValue(storageName, key) {
    const storage = storageFor(storageName);
    if (!storage) return null;
    try {
      return storage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeValue(storageName, key, value) {
    const storage = storageFor(storageName);
    if (!storage) return false;
    try {
      storage.setItem(key, value);
      return true;
    } catch (error) {
      return false;
    }
  }

  function removeValue(storageName, key) {
    const storage = storageFor(storageName);
    if (!storage) return false;
    try {
      storage.removeItem(key);
      return true;
    } catch (error) {
      return false;
    }
  }

  function readJson(storageName, key) {
    const value = readValue(storageName, key);
    if (!value) return null;
    try {
      return JSON.parse(value);
    } catch (error) {
      return null;
    }
  }

  function writeJson(storageName, key, value) {
    try {
      const serialized = JSON.stringify(value);
      if (typeof serialized !== "string") return false;
      return writeValue(storageName, key, serialized);
    } catch (error) {
      return false;
    }
  }

  function noteDraftStorageKey(context = {}) {
    return [
      NOTE_DRAFT_STORAGE_PREFIX,
      context.corpus_id || context.author_id || "",
      context.work_id || "",
      context.variant_id || ""
    ].join(":");
  }

  function storeRecentWork(record) {
    return writeJson("localStorage", RECENT_WORK_STORAGE_KEY, record);
  }

  function readStudyPanelExpanded() {
    return readValue("localStorage", STUDY_PANEL_STORAGE_KEY) === "true";
  }

  function storeStudyPanelExpanded(expanded) {
    return writeValue("localStorage", STUDY_PANEL_STORAGE_KEY, expanded ? "true" : "false");
  }

  function readNoteDraft(key) {
    return readJson("sessionStorage", key);
  }

  function storeNoteDraft(key, payload) {
    if (!payload) {
      return removeValue("sessionStorage", key);
    }
    return writeJson("sessionStorage", key, payload);
  }

  function clearNoteDraft(key) {
    return removeValue("sessionStorage", key);
  }

  global.ReaderWorkStorage = Object.freeze({
    noteDraftStorageKey,
    storeRecentWork,
    readStudyPanelExpanded,
    storeStudyPanelExpanded,
    readNoteDraft,
    storeNoteDraft,
    clearNoteDraft
  });
})(window);
