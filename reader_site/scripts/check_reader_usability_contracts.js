const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = (name) => fs.readFileSync(path.join(__dirname, "../assets", name), "utf8");
let count = 0;
function check(name, task) { task(); count++; console.log(`ok: ${name}`); }
const workflowContext = { window: {} };
vm.runInNewContext(source("translation-workflow.js"), workflowContext);
const workflow = workflowContext.window.TranslationWorkflow;
const record = { id: "record-1", corpus_id: "nietzsche", work_id: "JGB", segment_id: "p-0004", sentence_id: "p-0004.s002",
  translation: "모델 번역", review_state: "generated", generated_at: "2026-10-01T00:00:00Z", source_current: true };
check("human confirmation takes precedence over a newer model and its old warning", () => {
  const human = { ...record, human_translation: "확정 번역", review_state: "reviewed", quality_state: "needs_human_review" };
  const fresh = { ...record, id: "record-2", generated_at: "2026-10-04T00:00:00Z" };
  assert.equal(workflow.currentRecords([fresh, human])[0].id, human.id);
  assert.equal(workflow.queue([fresh, human]).length, 0);
});
check("a human-confirmed current issue remains in the review queue", () => {
  const human = { ...record, human_translation: "확정 번역", review_state: "reviewed", current_translation_issues: [{ severity: "major", explanation: "현재 의미 오류" }] };
  assert.equal(workflow.queue([human])[0].priority.rank, 1);
  assert.match(workflow.state(human).label, /재검토/);
});
check("source changes cannot be hidden by an old human approval", () => {
  const old = { ...record, human_translation: "이전 원문 확정", source_current: false };
  assert.equal(workflow.currentRecords([old, record])[0].human_translation, undefined);
  assert.match(workflow.state(old).label, /원문 연결 확인/);
});
check("the actual critic audit determines global priority", () => {
  const critical = { ...record, id: "critical", sentence_id: "p-0004.s003", quality_state: "needs_human_review", critic: { final: { issues: [{ severity: "major", explanation: "중대 오류" }] } } };
  const error = { ...record, id: "error", sentence_id: "p-0004.s004", quality_state: "critic_error" };
  assert.equal(workflow.queue([record, error, critical]).map((item) => item.record.id).join(","), "critical,error,record-1");
});
check("duplicates count once and rejected translations are excluded", () => {
  assert.equal(workflow.queue([record, { ...record, id: "older" }]).length, 1);
  assert.equal(workflow.queue([{ ...record, review_state: "rejected" }]).length, 0);
});
check("source unavailable is not represented as confirmed current", () => {
  const unknown = { ...record, human_translation: "확정", source_current: null };
  assert.match(workflow.state(unknown).label, /원문 확인/);
  assert.equal(workflow.queue([unknown]).length, 1);
});

function storageContext(map = new Map()) {
  const storage = { getItem: (key) => map.get(key) || null, setItem: (key, value) => map.set(key, value), removeItem: (key) => map.delete(key) };
  const context = { URL, URLSearchParams, window: { localStorage: storage, location: { origin: "http://127.0.0.1:8793" } } };
  vm.runInNewContext(source("reader-work-storage.js"), context);
  return { storage, map, api: context.window.ReaderWorkStorage };
}
check("recent history retains five documents, deduplicates and restores anchors", () => {
  const { api } = storageContext();
  for (let index = 1; index <= 6; index++) api.storeRecentWork({ href: `/work/nietzsche/work-${index}#p-000${index}.s001`, title: `작품 ${index}`, position_label: `문장 ${index}` });
  assert.equal(api.readRecentWorks().length, 5);
  api.storeRecentWork({ href: "/work/nietzsche/work-3", title: "작품 3" });
  assert.equal(api.readRecentWorks().length, 5);
  assert.equal(api.readRecentWorks()[0].href, "/work/nietzsche/work-3#p-0003.s001");
});
check("recent history preserves variants and accepts the old single-work storage", () => {
  const map = new Map([["philo.reader.recentWork", JSON.stringify({ href: "/work/kierkegaard/ba?variant=text#sks-0017.s001", title: "기존 문서" })]]);
  const { api } = storageContext(map);
  assert.equal(api.readRecentWorks().length, 1);
  api.storeRecentWork({ href: "/work/kierkegaard/ba?variant=commentary#sks-0017.s001", title: "다른 판본" });
  assert.equal(api.readRecentWorks().length, 2);
});
check("recent navigation rejects foreign origins and malformed entries", () => {
  const { api } = storageContext();
  assert.equal(api.storeRecentWork({ href: "https://untrusted.invalid/work/nietzsche/JGB" }), false);
  assert.equal(api.storeRecentWork({ href: "/work/../../outside" }), false);
  assert.equal(api.readRecentWorks().length, 0);
});
check("automatic generation defaults off and changes only through its stored choice", () => {
  const { api } = storageContext();
  assert.equal(api.readAutomaticTranslation(), false);
  api.storeAutomaticTranslation(true); assert.equal(api.readAutomaticTranslation(), true);
  api.storeAutomaticTranslation(false); assert.equal(api.readAutomaticTranslation(), false);
});
check("restoring an anchor preserves its bookmark until the user scrolls", () => {
  const listeners = {}, saved = [], timers = new Map(); let timerId = 0;
  const context = {
    window: { addEventListener: (name, callback) => { listeners[name] = callback; },
      clearTimeout: (id) => timers.delete(id), setTimeout: (callback) => { timers.set(++timerId, callback); return timerId; } },
    document: { documentElement: { clientWidth: 1280 }, addEventListener() {} },
    recentWorkRecord: (node) => ({ href: `/work/nietzsche/JGB#${node.id}` }),
    readerWorkStorage: { storeRecentWork: (entry) => saved.push(entry) }
  };
  vm.createContext(context); vm.runInContext(source("reader-work-recent.js"), context);
  const node = { id: "p-0004.s003", dataset: {} };
  context.scheduleRecentWorkPosition(node); assert.equal(timers.size, 0);
  listeners.wheel(); context.scheduleRecentWorkPosition(node); assert.equal(timers.size, 1);
  listeners.pagehide(); assert.equal(saved[0].href, "/work/nietzsche/JGB#p-0004.s003");
  context.resetRecentWorkPositionTracking(); context.scheduleRecentWorkPosition({ ...node, id: "p-0004.s004" });
  assert.equal(timers.size, 0);
  listeners.keydown({ key: "PageDown", target: { closest: () => ({}) } });
  context.scheduleRecentWorkPosition(node); assert.equal(timers.size, 0);
  listeners.keydown({ key: "PageDown", target: { closest: () => null } });
  context.scheduleRecentWorkPosition(node); assert.equal(timers.size, 1);
});

function draftContext(map = new Map(), blocked = false) {
  const listeners = {};
  const mountedForms = [];
  const storage = { getItem: (key) => map.get(key) || null, setItem: (key, value) => { if (blocked) throw new Error("blocked"); map.set(key, value); }, removeItem: (key) => map.delete(key) };
  const context = { window: { localStorage: storage, addEventListener: (name, callback) => { listeners[name] = callback; } } };
  vm.runInNewContext(source("translation-editor-drafts.js"), context);
  context.window.TranslationDrafts.initialize({ addEventListener() {}, querySelectorAll: () => mountedForms });
  return { api: context.window.TranslationDrafts, map, listeners, mountedForms };
}
function editor(value = record.translation) {
  const nodes = new Map();
  const selectors = ['[data-draft-action="discard"]','[data-draft-action="restore"]','[data-draft-action="rebase"]',
    '[data-draft-comparison]','[data-draft-status]','[data-draft-server-text]','[data-draft-local-text]'];
  selectors.forEach((selector) => nodes.set(selector, {}));
  const button = {};
  const details = { open: false };
  const tools = { querySelector: (selector) => nodes.get(selector) };
  const form = { elements: { human_translation: { value, focus() {} } },
    querySelector: (selector) => selector === ".translation-draft-tools" ? tools : button,
    closest: () => details };
  return { form, nodes, button, details };
}
check("draft survives rerender and reload, isolated by record and corpus", () => {
  const { api, map } = draftContext();
  const first = editor(); api.attach(first.form, record);
  first.form.elements.human_translation.value = "편집 중\n초안"; api.capture(first.form);
  const remounted = editor(); api.attach(remounted.form, record);
  assert.equal(remounted.form.elements.human_translation.value, "편집 중\n초안");
  assert.equal(remounted.details.open, true);
  const reload = draftContext(map).api;
  const restored = editor(); reload.attach(restored.form, record);
  assert.equal(restored.form.elements.human_translation.value, "편집 중\n초안");
  const other = editor(); reload.attach(other.form, { ...record, corpus_id: "bible" });
  assert.equal(other.form.elements.human_translation.value, record.translation);
});
check("pending drafts activate the leave guard", () => {
  const { api, listeners } = draftContext();
  const { form } = editor(); api.attach(form, record); form.elements.human_translation.value = "초안"; api.capture(form);
  let prevented = false; const event = { preventDefault: () => { prevented = true; } };
  listeners.beforeunload(event); assert.equal(prevented, true); assert.equal(event.returnValue, "");
});
check("a stale tab cannot remove or overwrite the other tab's newer draft", () => {
  const { api, map, listeners, mountedForms } = draftContext();
  const first = editor(); api.attach(first.form, record); mountedForms.push(first.form);
  first.form.elements.human_translation.value = "먼저 편집한 초안"; api.capture(first.form);
  const key = [...map.keys()][0];
  const newer = JSON.stringify({ ...JSON.parse(map.get(key)), text: "다른 탭의 최신 초안" });
  map.set(key, newer); listeners.storage({ key });
  assert.equal(first.button.disabled, true);
  first.form.elements.human_translation.value = record.translation; api.capture(first.form);
  assert.equal(map.get(key), newer);
  first.form.elements.human_translation.value = "오래된 탭에서 계속 편집"; api.capture(first.form);
  assert.equal(map.get(key), newer);
});
check("server edit conflict preserves draft and requires an explicit rebase", () => {
  const { api } = draftContext();
  const first = editor(); api.attach(first.form, record); first.form.elements.human_translation.value = "내 초안"; api.capture(first.form);
  const next = editor("다른 확정 번역"); api.attach(next.form, { ...record, human_translation: "다른 확정 번역" });
  assert.equal(next.button.disabled, true); assert.equal(next.form.elements.human_translation.value, "내 초안");
  api.action(next.form, "rebase"); assert.equal(next.button.disabled, false);
  assert.equal(api.snapshot(next.form).baseTranslation, "다른 확정 번역");
});
check("editing during save keeps the newer local text", () => {
  const { api } = draftContext();
  const first = editor(); api.attach(first.form, record); first.form.elements.human_translation.value = "보낸 초안"; api.capture(first.form);
  first.form.elements.human_translation.value = "저장 중 계속 편집한 내용"; api.capture(first.form);
  api.saved({ ...record, human_translation: "보낸 초안" }, "보낸 초안");
  const next = editor(); api.attach(next.form, { ...record, human_translation: "보낸 초안" });
  assert.equal(next.form.elements.human_translation.value, "저장 중 계속 편집한 내용");
  assert.equal(next.button.disabled, false);
});
check("draft discard is recoverable after reload", () => {
  const { api, map } = draftContext();
  const first = editor(); api.attach(first.form, record); first.form.elements.human_translation.value = "복구할 초안"; api.capture(first.form);
  api.action(first.form, "discard"); assert.equal(first.form.elements.human_translation.value, record.translation); assert.equal(api.hasPending(), false);
  const reload = draftContext(map).api; const next = editor(); reload.attach(next.form, record); reload.action(next.form, "restore");
  assert.equal(next.form.elements.human_translation.value, "복구할 초안");
});
check("unavailable storage preserves in-memory draft and warns on rerender", () => {
  const { api } = draftContext(new Map(), true); const first = editor(); api.attach(first.form, record);
  first.form.elements.human_translation.value = "보호할 초안"; api.capture(first.form);
  const next = editor(); api.attach(next.form, record);
  assert.equal(next.form.elements.human_translation.value, "보호할 초안");
  assert.match(next.nodes.get('[data-draft-status]').textContent, /저장소/);
});
check("cache browsing preference is applied to every selected sentence", () => {
  const calls = []; const context = { requestSentenceTranslation: (...args) => calls.push(args) };
  vm.createContext(context); vm.runInContext(source("reader-work-navigation.js"), context);
  context.requestSelectedTranslation(); assert.deepEqual(calls[0], [false, true]);
  vm.runInContext("automaticSentenceTranslation = true", context); context.requestSelectedTranslation(); assert.deepEqual(calls[1], [false, false]);
});
check("restored automatic preference has matching status and storage failures are explicit", () => {
  let onChange;
  const field = { checked: false, addEventListener: (name, callback) => { onChange = callback; } };
  const status = { textContent: "" };
  const context = {
    document: { getElementById: (id) => id === "automaticSentenceTranslation" ? field : status },
    readerWorkStorage: { readAutomaticTranslation: () => true, storeAutomaticTranslation: () => false }
  };
  vm.createContext(context); vm.runInContext(source("reader-work-navigation.js"), context);
  context.initializeSentenceTranslationPreference();
  assert.equal(field.checked, true); assert.match(status.textContent, /자동으로 생성/);
  field.checked = false; onChange();
  assert.match(status.textContent, /저장된 번역만/); assert.match(status.textContent, /이번 화면에만/);
});
console.log(`reader usability contracts ok (${count} checks)`);
