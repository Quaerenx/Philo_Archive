// Display preferences are local to this browser, independent of saved translations.
const READER_VIEW_DEFAULTS = Object.freeze({ size: "standard", spacing: "relaxed", width: "standard", panel: "balanced" });
const READER_VIEW_OPTIONS = Object.freeze({
  size: { small: "16px", standard: "18px", large: "21px" },
  spacing: { standard: "1.75", relaxed: "2", wide: "2.25" },
  width: { narrow: "48ch", standard: "64ch", wide: "76ch" },
  panel: { source: "360px", balanced: "440px", translation: "520px" }
});
const READER_VIEW_PRESETS = Object.freeze({
  balanced: READER_VIEW_DEFAULTS,
  reading: { size: "large", spacing: "relaxed", width: "narrow", panel: "source" },
  comparison: { size: "standard", spacing: "standard", width: "wide", panel: "translation" }
});

function normalizeReaderPreferences(value) {
  const result = { ...READER_VIEW_DEFAULTS };
  Object.keys(result).forEach((key) => {
    if (value && Object.hasOwn(READER_VIEW_OPTIONS[key], value[key])) result[key] = value[key];
  });
  return result;
}

function applyReaderPreferences(value) {
  const preferences = normalizeReaderPreferences(value);
  const root = document.documentElement;
  root.style.setProperty("--reading-font-size", READER_VIEW_OPTIONS.size[preferences.size]);
  root.style.setProperty("--reading-line-height", READER_VIEW_OPTIONS.spacing[preferences.spacing]);
  root.style.setProperty("--reading-measure", READER_VIEW_OPTIONS.width[preferences.width]);
  root.style.setProperty("--study-panel-width", READER_VIEW_OPTIONS.panel[preferences.panel]);
  document.querySelectorAll("[data-reading-preference]").forEach((field) => {
    field.value = preferences[field.dataset.readingPreference];
  });
  document.querySelectorAll("[data-reading-preset]").forEach((button) => {
    const preset = READER_VIEW_PRESETS[button.dataset.readingPreset];
    const active = Object.keys(preferences).every((key) => preset[key] === preferences[key]);
    button.setAttribute("aria-pressed", String(active));
  });
  scheduleReadingPositionRefresh();
  return preferences;
}

function initializeReaderPreferences() {
  const tools = document.getElementById("readerPreferences");
  if (!tools) return;
  let preferences = applyReaderPreferences(readerWorkStorage.readReadingPreferences());
  const update = (value) => {
    preferences = applyReaderPreferences(value);
    const saved = readerWorkStorage.storeReadingPreferences(preferences);
    document.getElementById("readingPreferencesStatus").textContent = saved
      ? "이 브라우저에 읽기 설정을 저장했습니다." : "설정을 적용했습니다. 브라우저 저장소를 사용할 수 없어 이번 화면에만 적용됩니다.";
  };
  tools.addEventListener("change", (event) => {
    const key = event.target.dataset.readingPreference;
    if (key) update({ ...preferences, [key]: event.target.value });
  });
  tools.addEventListener("click", (event) => {
    const preset = event.target.closest("[data-reading-preset]");
    if (preset) update(READER_VIEW_PRESETS[preset.dataset.readingPreset]);
  });
}
