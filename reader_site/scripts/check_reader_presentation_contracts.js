const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const asset = (name) => fs.readFileSync(path.join(__dirname, "../assets", name), "utf8");
const context = { window: {}, researchData: {}, cleanText: (text) => String(text || "").replace(/\s+/g, " ").trim(),
  document: { querySelectorAll: () => [] } };
vm.createContext(context);
vm.runInContext(asset("translation-comparison.js"), context);
vm.runInContext(asset("reader-work-preferences.js"), context);
vm.runInContext(asset("reader-work-terms.js"), context);
const { difference, render } = context.window.TranslationComparison;
let checks = 0;
function check(name, task) { task(); checks++; console.log(`ok: ${name}`); }

check("comparison retains Korean and marks changed words", () => {
  const diff = difference("가능성을 위한 가능성", "가능성의 가능성");
  assert.equal(diff.model.replace(/<[^>]+>/g, ""), "가능성을 위한 가능성");
  assert.equal(diff.confirmed.replace(/<[^>]+>/g, ""), "가능성의 가능성");
  assert.match(diff.model, /comparison-removed/);
  assert.match(diff.confirmed, /comparison-added/);
});
check("unchanged text and punctuation remain intact", () => {
  const text = "그는 말했다.\n‘같다’: a & b — 😀";
  const diff = difference(text, text);
  assert.equal(diff.model, diff.confirmed);
  assert.ok(!diff.model.includes("<mark"));
  assert.match(render({ translation: text, human_translation: text }), /번역이 같습니다/);
});
check("source and both versions escape HTML", () => {
  const html = render({ source_text_excerpt: '<script>"&', translation: '<img src=x onerror="alert(1)">', human_translation: "<b>확정</b>" });
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img "));
  assert.ok(!html.includes("<b>"));
  assert.match(html, /&lt;script&gt;&quot;&amp;/);
});
check("missing human approval remains explicitly missing", () => {
  const html = render({ translation: "모델" });
  assert.match(html, /확정 번역이 아직 없습니다/);
  assert.ok(!html.includes("확정본 있음"));
});
check("long text limits diff computation without truncation", () => {
  const left = "긴 문장 ".repeat(500);
  const right = "다른 문장 ".repeat(500);
  const diff = difference(left, right);
  assert.equal(diff.limited, true);
  assert.equal(diff.model, left);
  assert.equal(diff.confirmed, right);
});
check("invalid preferences fall back to allowed choices", () => {
  const normalized = context.normalizeReaderPreferences({ size: "garbage", panel: "source", width: "__proto__", spacing: null });
  assert.equal(normalized.size, "standard");
  assert.equal(normalized.panel, "source");
  assert.equal(normalized.width, "standard");
  assert.equal(normalized.spacing, "relaxed");
});
check("preference application updates both layout and controls", () => {
  const properties = {};
  const field = { dataset: { readingPreference: "size" } };
  context.document.documentElement = { style: { setProperty: (key, value) => { properties[key] = value; } } };
  context.document.querySelectorAll = (selector) => selector === "[data-reading-preference]" ? [field] : [];
  context.scheduleReadingPositionRefresh = () => {};
  context.applyReaderPreferences({ size: "large", spacing: "wide", width: "narrow", panel: "source" });
  assert.equal(properties["--reading-font-size"], "21px");
  assert.equal(properties["--reading-line-height"], "2.25");
  assert.equal(properties["--reading-measure"], "48ch");
  assert.equal(properties["--study-panel-width"], "360px");
  assert.equal(field.value, "large");
});
check("preference storage handles unavailable and corrupted storage", () => {
  const stored = new Map();
  const localStorage = { getItem: (key) => stored.get(key) || null, setItem: (key, value) => stored.set(key, value) };
  const storeContext = { window: { localStorage } };
  vm.runInNewContext(asset("reader-work-storage.js"), storeContext);
  const storage = storeContext.window.ReaderWorkStorage;
  assert.equal(storage.storeReadingPreferences({ size: "large" }), true);
  assert.equal(storage.readReadingPreferences().size, "large");
  stored.set("philo.reader.readingPreferences.v1", "broken JSON");
  assert.equal(storage.readReadingPreferences(), null);
  Object.defineProperty(storeContext.window, "localStorage", { get() { throw new Error("unavailable"); } });
  assert.equal(storage.readReadingPreferences(), null);
  assert.equal(storage.storeReadingPreferences({}), false);
});
check("terms match complete source words and preserve case", () => {
  assert.equal(context.termOccurrences("Frygt og Angest; Angesten.", "Angest").length, 1);
  assert.equal(context.termOccurrences("frihed", "Frihed").length, 0);
  assert.equal(context.termOccurrences("「Mulighed for Muligheden」", "Mulighed for Muligheden").length, 1);
  assert.equal(context.termOccurrences("unbekannt", "bekannt").length, 0);
});
check("only current source-bound notes are explained", () => {
  context.document.querySelectorAll = () => [];
  const text = "Angest og Frygt";
  const record = { commentary_status: "current", note_source_text: text, translation_notes: [{ source_span: "Angest", note: "불안" }] };
  assert.equal(context.termsForSentence(text, record).length, 1);
  assert.equal(context.termsForSentence(text, { ...record, commentary_status: "translation_changed" }).length, 0);
  assert.equal(context.termsForSentence(text, { ...record, note_source_text: "other source" }).length, 0);
  assert.equal(context.termsForSentence(text, { ...record, current_note_issues: [{}] }).length, 0);
  assert.equal(context.termsForSentence(text, { ...record, translation_notes: [{ source_span: "other", note: "absent" }] }).length, 0);
});
check("note provenance distinguishes human approval from automatic review", () => {
  const record = { commentary_status: "current", note_source_text: "Angest", translation_notes: [{ source_span: "Angest", note: "불안" }] };
  assert.equal(context.termsForSentence("Angest", record)[0].kind, "model-note");
  assert.equal(context.termsForSentence("Angest", { ...record, human_translation: "불안" })[0].kind, "confirmed-note");
});
console.log(`reader presentation contracts ok (${checks} checks)`);
