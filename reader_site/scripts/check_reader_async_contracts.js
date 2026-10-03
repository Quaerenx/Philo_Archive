const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../assets/reader-work-translation.js"), "utf8");
function functionSource(name) {
  const start = source.indexOf("async function " + name + "(");
  assert.ok(start >= 0, name + " missing");
  const tail = source.slice(start + 1);
  const next = /\n(?:async )?function /.exec(tail);
  return source.slice(start, next ? start + 1 + next.index : source.length);
}
async function reviewRace(moveSelection) {
  let resolveResponse;
  const rendered = [];
  const statuses = [];
  const context = {
    selectedTranslationRecord: { id: "record-A" },
    translationReviewSequence: 0,
    targetKey: "sentence-A", researchData: { corpus_id: "nietzsche" },
    markTranslationReviewedButton: {}, rejectTranslationButton: {},
    selectedTranslationTargetKey: () => context.targetKey,
    clearActionConfirmations() {}, setActionButtonBusy() {},
    setTranslationStatus: (message) => statuses.push(message),
    loadTranslationRecordsSummary() {}, loadStudySessionSummary() {},
    focusNextSentenceAction() {}, updateSentenceControls() {},
    renderTranslationRecord: (record) => rendered.push(record.id),
    fetch: () => new Promise((resolve) => { resolveResponse = resolve; })
  };
  vm.createContext(context);
  vm.runInContext(functionSource("updateTranslationReview"), context);
  const pending = context.updateTranslationReview("reviewed");
  if (moveSelection) {
    context.targetKey = "sentence-B";
    context.selectedTranslationRecord = { id: "record-B" };
  }
  resolveResponse({ ok: true, json: async () => ({ ok: true, record: { id: "record-A" } }) });
  await pending;
  assert.deepEqual(rendered, moveSelection ? [] : ["record-A"]);
  assert.equal(statuses.includes("저장했습니다."), !moveSelection);
}
async function cancellation(completed) {
  const statuses = [];
  let aborted = false;
  const context = {
    activeTranslationController: { translationJobId: "request-A", abort() { aborted = true; } },
    activeTranslationRequest: 1, activeTranslationTargetKey: "A",
    selectedSentenceNode: () => null, updateSentenceControls() {},
    setTranslationStatus: (message) => statuses.push(message),
    renderTranslationCancelled() {}, loadTranslationRecordsSummary() {},
    fetch: async (_url, options) => {
      assert.equal(JSON.parse(options.body).request_id, "request-A");
      return { ok: true, json: async () => ({ ok: true, cancelled: !completed }) };
    }
  };
  vm.createContext(context);
  vm.runInContext(functionSource("cancelTranslationRequest"), context);
  await context.cancelTranslationRequest();
  assert.equal(aborted, true);
  assert.equal(statuses.at(-1), completed ? "번역이 이미 저장되었습니다." : "번역 요청을 취소했습니다.");
}

function namedFunction(file, name) {
  const value = fs.readFileSync(path.join(__dirname, "../assets", file), "utf8");
  const match = new RegExp("(?:async )?function " + name + "\\(").exec(value);
  assert.ok(match, name + " missing");
  const tail = value.slice(match.index + 1);
  const next = /\n(?:async )?function /.exec(tail);
  return value.slice(match.index, next ? match.index + 1 + next.index : value.length);
}

async function summaryRace(staleFailure) {
  const pending = [], applied = [];
  let cleared = 0;
  const context = {
    translationRecordsSummary: {}, translationSummaryRequest: 0,
    researchData: {corpus_id: "nietzsche", work_id: "GM"}, URLSearchParams,
    fetch: () => new Promise(resolve => pending.push(resolve)),
    applySentenceTranslationStates: states => applied.push(states[0].review_state),
    setTranslationRecordsSummary() {}, updateTranslationExportLinks() {},
    clearSentenceTranslationStates: () => { cleared += 1; },
  };
  vm.createContext(context);
  vm.runInContext(namedFunction("reader-work-runtime.js", "loadTranslationRecordsSummary"), context);
  const older = context.loadTranslationRecordsSummary();
  const newer = context.loadTranslationRecordsSummary();
  const response = state => ({ok: true, json: async () => ({ok: true, count: 1, review_state_counts: {[state]: 1}, sentence_state_count: 1, sentence_states: [{review_state: state}]})});
  pending[1](response("reviewed"));
  await newer;
  pending[0](staleFailure ? {ok: false, json: async () => ({ok: false})} : response("generated"));
  await older;
  assert.deepEqual(applied, ["reviewed"]);
  assert.equal(cleared, 0);
}

async function notesFilterRace() {
  const pending = [], shown = [];
  const context = {
    researchData: {corpus_id: "nietzsche", work_id: "GM"}, URLSearchParams,
    notesRequestSequence: 0, noteFilter: {value: "first"}, noteStatus: {}, recentlyChangedNoteId: "",
    renderNotesPending() {}, renderNotesUnavailable() { throw new Error("stale error displayed"); },
    renderNotesList: notes => shown.push(notes[0].id),
    fetch: () => new Promise(resolve => pending.push(resolve)),
  };
  vm.createContext(context);
  vm.runInContext(namedFunction("reader-work-notes.js", "loadNotes"), context);
  const older = context.loadNotes();
  context.noteFilter.value = "second";
  const newer = context.loadNotes();
  pending[1]({ok: true, json: async () => ({notes: [{id: "second"}]})});
  await newer;
  pending[0]({ok: true, json: async () => ({notes: [{id: "first"}]})});
  await older;
  assert.deepEqual(shown, ["second"]);
}

async function sessionVariantNavigation() {
  const navigated = [];
  const context = {
    URL, cleanText: value => String(value || "").trim(),
    researchData: {corpus_id: "kierkegaard", work_id: "aa", variant_id: "text"},
    location: {origin: "http://127.0.0.1:8793", pathname: "/work/kierkegaard/aa", assign: href => navigated.push(href)},
    document: {getElementById() { throw new Error("wrong variant searched in current document"); }},
  };
  vm.createContext(context);
  vm.runInContext(namedFunction("reader-work.js", "cleanText"), context);
  for (const name of ["sessionPreviewTargetId", "sessionPreviewTargetUrl", "openSessionPreviewTarget"]) {
    vm.runInContext(namedFunction("reader-work-translation.js", name), context);
  }
  const record = {corpus_id: "kierkegaard", work_id: "aa", variant_id: "commentary", sentence_id: "sks-0001.s001", target_url: "/work/kierkegaard/aa?variant=commentary#sks-0001.s001"};
  assert.equal(context.sessionPreviewTargetId({target_url: record.target_url}), record.sentence_id);
  await context.openSessionPreviewTarget(record.sentence_id, context.sessionPreviewTargetUrl(record));
  assert.deepEqual(navigated, ["http://127.0.0.1:8793/work/kierkegaard/aa?variant=commentary#sks-0001.s001"]);
  assert.equal(context.sessionPreviewTargetUrl({...record, target_url: "https://untrusted.invalid/work/kierkegaard/aa"}), "");
}
(async () => {
  const frames = [];
  let stored = "[]";
  let now = 0;
  const metricsContext = {
    localStorage: {getItem: () => stored, setItem: (_,value) => {stored=value;}},
    requestAnimationFrame: callback => frames.push(callback), performance: {now: () => now},
    document: {visibilityState:"visible"}, translationOutput: {getClientRects: () => [{}]}
  };
  vm.createContext(metricsContext);
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../assets/reader-translation-metrics.js"),"utf8"),metricsContext);
  metricsContext.recordTranslationRender(0,{cached:false,record:{revision_count:1},metrics:{model_calls:4,model_usage:[{prompt_tokens:3000,completion_tokens:100,available_context:5192}],context_truncated:true}},() => false);
  while (frames.length) frames.shift()();
  assert.equal(JSON.parse(stored).length,0,"a stale result must not enter latency metrics");
  for (let index=1;index<=20;index++) {
    now=index*100;
    metricsContext.recordTranslationRender(0,{cached:false,record:{revision_count:0},metrics:{model_calls:2,model_usage:[{prompt_tokens:3000}],context_truncated:false}},() => true);
    while (frames.length) frames.shift()();
  }
  const measured = metricsContext.readerTranslationMetrics();
  assert.equal(measured.generation.p50_ms,1000);
  assert.equal(measured.generation.p95_ms,1900);
  assert.equal(measured.mean_model_calls,2);
  assert.equal(measured.prompt_tokens.max,3000);
  assert.ok(!stored.includes("translation") && !stored.includes("prompt_text"));
  now=10;
  metricsContext.markReaderTranslationAction({type:"click",target:{closest:()=>({})}});
  now=5010;
  assert.equal(metricsContext.consumeReaderTranslationAction(),10,"source-chunk loading time must remain inside click latency");
  assert.equal(metricsContext.consumeReaderTranslationAction(),null,"automatic requests must not reuse an old activation");
  await reviewRace(true);
  await reviewRace(false);
  await cancellation(false);
  await cancellation(true);
  await summaryRace(false);
  await summaryRace(true);
  await notesFilterRace();
  await sessionVariantNavigation();
  process.stdout.write("reader async contracts ok: reviews, cancellation, summary/filter races, and variant navigation\n");
})().catch((error) => { process.stderr.write(String(error.stack) + "\n"); process.exitCode = 1; });
