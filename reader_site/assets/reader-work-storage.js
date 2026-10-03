(function (global) {
  "use strict";

  const RECENT_WORK_STORAGE_KEY = "philo.reader.recentWork";
  const STUDY_PANEL_STORAGE_KEY = "philo.reader.studyPanelExpanded";
  const NOTE_DRAFT_STORAGE_PREFIX = "philo.reader.noteDraft";
  const READING_PREFERENCES_KEY = "philo.reader.readingPreferences.v1";
  const AUTOMATIC_TRANSLATION_KEY = "philo.reader.automaticTranslation.v1";
  const RECENT_WORKS_KEY = "philo.reader.recentWorks.v2";

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

  function recentRecord(record) {
    if (!record || typeof record !== "object") return null;
    try {
      const href = String(record.href || "");
      if (!href.startsWith("/work/")) return null;
      const url = new URL(href, global.location?.origin || "http://localhost");
      if (url.origin !== (global.location?.origin || "http://localhost") || !/^\/work\/[^/]+\/[^/]+\/?$/.test(url.pathname)) return null;
      const variant = url.searchParams.get("variant") || String(record.variant_id || "");
      const normalizedHref = url.pathname + (variant ? "?" + new URLSearchParams({ variant }) : "") + url.hash;
      return { ...record, href: normalizedHref, key: url.pathname + "?variant=" + variant,
        title: String(record.title || record.work_id || "최근 문서").slice(0, 240),
        position_label: String(record.position_label || "").slice(0, 120) };
    } catch { return null; }
  }

  function readRecentWorks() {
    const value = readJson("localStorage", RECENT_WORKS_KEY);
    const legacy = readJson("localStorage", RECENT_WORK_STORAGE_KEY);
    const records = [...(Array.isArray(value) ? value : []), ...(legacy ? [legacy] : [])];
    const seen = new Set();
    return records.map(recentRecord).filter((record) => {
      if (!record || seen.has(record.key)) return false;
      seen.add(record.key); return true;
    }).slice(0, 5);
  }

  function storeRecentWork(record) {
    const current = recentRecord(record);
    if (!current) return false;
    const recent = readRecentWorks();
    const old = recent.find((item) => item.key === current.key);
    // Opening a work without a selected position must not erase its saved anchor.
    if (!current.href.includes("#") && old?.href.includes("#")) {
      current.href = old.href; current.position_label = old.position_label;
    }
    const saved = writeJson("localStorage", RECENT_WORKS_KEY, [current, ...recent.filter((item) => item.key !== current.key)].slice(0, 5));
    writeJson("localStorage", RECENT_WORK_STORAGE_KEY, current);
    return saved;
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
    readAutomaticTranslation: () => readValue("localStorage", AUTOMATIC_TRANSLATION_KEY) === "true",
    storeAutomaticTranslation: (enabled) => writeValue("localStorage", AUTOMATIC_TRANSLATION_KEY, String(Boolean(enabled))),
    readRecentWorks,
    readReadingPreferences: () => readJson("localStorage", READING_PREFERENCES_KEY),
    storeReadingPreferences: (value) => writeJson("localStorage", READING_PREFERENCES_KEY, value),
    noteDraftStorageKey,
    storeRecentWork,
    readStudyPanelExpanded,
    storeStudyPanelExpanded,
    readNoteDraft,
    storeNoteDraft,
    clearNoteDraft
  });
})(window);
