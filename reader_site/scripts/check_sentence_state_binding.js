#!/usr/bin/env node
"use strict";

// Standalone behavior checks: node reader_site/scripts/check_sentence_state_binding.js
// No server, browser, model, source corpus, or external packages are required.
// Production functions run in a fresh VM per case; only DOM/IO/rendering edges
// are faked. These checks do not measure translation quality or browser layout.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ASSETS = path.resolve(__dirname, "../assets");
const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const SCOPE = { corpus_id: "fixture", work_id: "synthetic-work", variant_id: "edition-a" };

function sourcePart(filename, first, next) {
  const source = fs.readFileSync(path.join(ASSETS, filename), "utf8");
  const start = source.indexOf(first);
  const end = source.indexOf(next, start + first.length);
  assert.ok(start >= 0 && end > start, `Cannot locate production functions in ${filename}`);
  return new vm.Script(source.slice(start, end), { filename });
}

const scripts = [
  sourcePart("reader-work.js", "function cleanText(", "\nfunction currentWorkHref("),
  ...["reader-work-runtime.js", "reader-work-sentences.js"].map((filename) =>
    new vm.Script(fs.readFileSync(path.join(ASSETS, filename), "utf8"), { filename })
  ),
  sourcePart("reader-work-translation.js", "function renderTranslationRecord(", "\nfunction revealFreshTranslationResult("),
];

function element(id = "", initialClasses = []) {
  const classes = new Set(initialClasses);
  const attributes = new Map();
  const node = {
    id, dataset: {}, hidden: false, disabled: false, textContent: "", innerHTML: "",
    classList: {
      add: (...values) => values.forEach((value) => classes.add(value)),
      remove: (...values) => values.forEach((value) => classes.delete(value)),
      contains: (value) => classes.has(value),
      toggle(value, force) {
        const enabled = force === undefined ? !classes.has(value) : Boolean(force);
        if (enabled) classes.add(value); else classes.delete(value);
        return enabled;
      },
    },
    getAttribute: (name) => attributes.has(name) ? attributes.get(name) : null,
    setAttribute(name, value) {
      attributes.set(name, String(value));
      if (name.startsWith("data-")) node.dataset[dataKey(name)] = String(value);
    },
    removeAttribute(name) {
      attributes.delete(name);
      if (name.startsWith("data-")) delete node.dataset[dataKey(name)];
    },
  };
  Object.defineProperty(node, "title", {
    get: () => node.getAttribute("title") || "",
    set: (value) => node.setAttribute("title", value),
  });
  return node;
}

function dataKey(attribute) {
  return attribute.slice(5).replace(/-([a-z])/g, (_, character) => character.toUpperCase());
}

function sentence(id = "p-fixture.s001", hash = HASH_A, position = 1) {
  const node = element(id, ["reader-sentence"]);
  node.dataset.sentenceId = id;
  node.dataset.sentencePosition = String(position);
  if (hash !== undefined) node.dataset.sentenceSha256 = hash;
  node.textContent = "Synthetic sentence.";
  node.title = "Original source title";
  return node;
}

function record(overrides = {}) {
  return {
    ...SCOPE, id: "fixture-record", sentence_id: "p-fixture.s001",
    sentence_text_sha256: HASH_A, review_state: "generated",
    translation: "Synthetic translation.", updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function harness({ virtual = false, total = 4, variant = SCOPE.variant_id } = {}) {
  let mounted = [];
  const effects = [];
  const context = {
    researchData: { ...SCOPE, variant_id: variant },
    sentenceNodes: [], sentenceNodeById: new Map(), sentenceIndexById: new Map(),
    sentenceNodeByPosition: new Map(), translationSentenceStates: new Map(),
    translationSentenceCandidates: new Map(),
    translationSentenceStatesLoaded: true, selectedSentence: null,
    selectedTranslationRecord: null, pendingTranslationRegenerate: false,
    virtualDocument: virtual ? { total_sentences: total } : null,
    virtualChunkDescriptors: virtual ? [{ index: 0 }, { index: 1 }, { index: 2 }] : [],
    virtualWork: { activeChunkIndex: 0, chunkForNode: () => -1 },
    TRANSLATION_STATE_LABELS: { generated: "검토할 번역", reviewed: "저장한 번역", rejected: "제외한 번역" },
    TRANSLATION_STATE_SHORT: { generated: "AI", reviewed: "저장", rejected: "제외" },
    translationMode: "reading", URLSearchParams, URL,
    document: { getElementById: (id) => mounted.find((node) => node.id === id) || null },
    readingBody: { querySelectorAll: (selector) => {
      assert.equal(selector, ".reader-sentence");
      return mounted;
    } },
    fetch: async () => { throw new Error("Unexpected network request in behavior check"); },
    escapeHtml: (value) => String(value),
    window: { setTimeout, clearTimeout },
  };
  for (const name of [
    "previousSentenceButton", "nextSentenceButton", "nextUnstudiedSentenceButton",
    "nextReviewSentenceButton", "regenerateSentenceButton", "markTranslationReviewedButton",
    "rejectTranslationButton", "copyStudyCardButton", "draftTranslationNoteButton",
    "studyProgress", "studyProgressText", "continueStudyButton", "translationRecordsSummary",
    "exportReviewedTranslations", "exportAllTranslations", "translationOutput",
    "translationUtility", "translationCard",
  ]) context[name] = element(name);
  // Rendering-only collaborators are observed; binding/count/navigation remain real.
  for (const name of [
    "setTranslationBusy", "setTranslationReviewVisualState", "resetTranslationOutputScroll",
    "flashSentenceReviewState", "flashTranslationReviewState", "revealFreshTranslationResult",
    "updateStudyPanelToggleLabel",
  ]) context[name] = (...args) => effects.push({ name, args });
  for (const name of [
    "renderTranslationQuality", "renderCommentary", "translationQuickActions",
    "optionalCautions", "translationResultToolbar",
  ]) context[name] = () => "";
  vm.createContext(context);
  scripts.forEach((script) => script.runInContext(context));
  return {
    context, effects,
    setMounted(nodes) {
      mounted = [...nodes];
      context.refreshSentenceNodeIndex();
    },
  };
}

const cases = [];
function check(name, run) { cases.push({ name, run }); }

check("matching source and scope bind badges, navigation, and progress", () => {
  const h = harness(); const c = h.context; const node = sentence();
  h.setMounted([node]);
  assert.equal(c.applySentenceTranslationState(record({ review_state: "reviewed" })), true);
  c.updateSentenceControls();
  assert.equal(c.sentenceHasTranslationState(node), true);
  assert.equal(c.sentenceTranslationState(node), "reviewed");
  assert.equal(c.boundSentenceTranslationState(node).validated, true);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  assert.equal(node.classList.contains("has-translation-state"), true);
  assert.equal(node.dataset.translationState, "reviewed");
  assert.match(node.title, /Original source title/);
  assert.equal(c.firstUnstudiedSentenceIndex(), -1);
  assert.equal(c.studyProgress.dataset.progressState, "complete");
  assert.match(c.studyProgress.title, /1개 문장 중 1개 번역됨/);
});

check("missing, malformed, mismatched hashes and wrong scope are refused", () => {
  const invalid = [
    { sentence_text_sha256: undefined }, { sentence_text_sha256: "" },
    { sentence_text_sha256: "a".repeat(63) }, { sentence_text_sha256: "a".repeat(65) },
    { sentence_text_sha256: "g".repeat(64) }, { sentence_text_sha256: HASH_B },
    { sentence_text_sha256: 123 }, { sentence_text_sha256: [HASH_A] },
    { sentence_text_sha256: `#${HASH_A}` }, { sentence_text_sha256: `${HASH_A}¶` },
    { sentence_text_sha256: `${"a".repeat(32)} ${"a".repeat(32)}` },
    { corpus_id: "other-corpus" }, { work_id: "other-work" }, { variant_id: "edition-b" },
    { corpus_id: `#${SCOPE.corpus_id}` }, { work_id: `${SCOPE.work_id}¶` },
    { variant_id: `${SCOPE.variant_id}#` }, { sentence_id: "#p-fixture.s001" },
    { corpus_id: "" }, { work_id: "" }, { sentence_id: "p-fixture.s999" },
  ];
  for (const overrides of invalid) {
    const h = harness(); const c = h.context; const node = sentence();
    h.setMounted([node]);
    assert.equal(c.applySentenceTranslationState(record(overrides)), false, JSON.stringify(overrides));
    assert.equal(c.translationSentenceStates.size, 0);
    assert.equal(c.sentenceHasTranslationState(node), false);
    assert.equal(node.classList.contains("has-translation-state"), false);
    assert.equal(c.verifiedSentenceTranslationCount(), 0);
  }
  assert.equal(harness().context.applySentenceTranslationState(null), false);
});

check("missing or malformed DOM hashes fail closed", () => {
  for (const hash of ["", "not-a-hash", `#${HASH_A}`, `${HASH_A}¶`]) {
    const h = harness(); const node = sentence(undefined, hash);
    h.setMounted([node]);
    assert.equal(h.context.applySentenceTranslationState(record()), false, hash);
  }
  const h = harness(); const node = sentence(); delete node.dataset.sentenceSha256;
  h.setMounted([node]);
  assert.equal(h.context.applySentenceTranslationState(record()), false);
});

check("invalid direct records preserve an already valid binding", () => {
  const h = harness(); const c = h.context; const node = sentence();
  h.setMounted([node]);
  c.applySentenceTranslationState(record({ review_state: "reviewed" }));
  const previous = c.boundSentenceTranslationState(node); const title = node.title;
  for (const overrides of [
    { sentence_text_sha256: HASH_B }, { sentence_text_sha256: "" },
    { variant_id: "edition-b" }, { corpus_id: "other" }, { work_id: "other" },
  ]) {
    assert.equal(c.applySentenceTranslationState(record(overrides)), false);
    assert.equal(c.boundSentenceTranslationState(node), previous);
    assert.equal(node.title, title);
    assert.equal(node.dataset.translationState, "reviewed");
    assert.equal(c.verifiedSentenceTranslationCount(), 1);
  }
});

check("unmounted nonvirtual records do not count as existing sentences", () => {
  const c = harness().context;
  assert.equal(c.applySentenceTranslationState(record()), false);
  assert.equal(c.translationSentenceStates.size, 0);
});

check("pending virtual candidates are searchable but not counted or skipped", () => {
  const h = harness({ virtual: true }); const c = h.context;
  h.setMounted([]);
  assert.equal(c.applySentenceTranslationState(record()), true);
  c.updateSentenceControls();
  assert.equal(c.translationSentenceStates.get("p-fixture.s001").validated, false);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
  assert.equal(c.translationStateCountsFromSentences().generated, 0);
  assert.equal(c.sentenceHasTranslationState(null), false);
  assert.equal(c.nextGeneratedSentenceId(), "");
  assert.deepEqual([...c.generatedSentenceCandidateIds()], ["p-fixture.s001"]);
  assert.equal(c.nextReviewSentenceButton.disabled, false);
  assert.equal(c.nextUnstudiedSentenceButton.disabled, false);
  assert.match(c.studyProgress.title, /0개 번역됨/);
});

check("mount validates matching pending source and refreshes controls", () => {
  const h = harness({ virtual: true }); const c = h.context; const node = sentence();
  c.applySentenceTranslationState(record());
  h.setMounted([node]);
  assert.equal(c.translationSentenceStates.get(node.id).validated, true);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  assert.equal(c.nextGeneratedSentenceId(), node.id);
  assert.equal(node.dataset.translationState, "generated");
  assert.match(c.studyProgress.title, /1개 번역됨/);
});

check("mount discards stale pending source instead of marking it studied", () => {
  const h = harness({ virtual: true }); const c = h.context; const node = sentence(undefined, HASH_B);
  c.applySentenceTranslationState(record({ review_state: "reviewed" }));
  h.setMounted([node]);
  assert.equal(c.translationSentenceStates.has(node.id), false);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
  assert.equal(node.classList.contains("has-translation-state"), false);
  assert.equal(c.firstUnstudiedSentenceIndex(), 0);
  assert.match(c.studyProgress.title, /0개 번역됨/);
});

check("validated unmount persists and changed-source remount removes badge and count", () => {
  const h = harness({ virtual: true }); const c = h.context; const node = sentence();
  h.setMounted([node]); c.applySentenceTranslationState(record({ review_state: "reviewed" }));
  h.setMounted([]);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  node.dataset.sentenceSha256 = HASH_B;
  h.setMounted([node]);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
  assert.equal(c.translationSentenceStates.has(node.id), false);
  assert.equal(node.classList.contains("has-translation-state"), false);
  assert.equal(node.dataset.translationState, undefined);
  assert.equal(node.title, "Original source title");
});

check("unmounted direct updates reuse verification only for the exact source binding", () => {
  const h = harness({ virtual: true }); const c = h.context; const node = sentence();
  h.setMounted([node]); c.applySentenceTranslationState(record()); h.setMounted([]);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  assert.equal(c.applySentenceTranslationState(record({ review_state: "reviewed", id: "updated-record" })), true);
  const updated = c.translationSentenceStates.get(node.id);
  assert.equal(updated.validated, true);
  assert.equal(updated.reviewState, "reviewed");
  assert.equal(updated.recordId, "updated-record");
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  assert.equal(c.applySentenceTranslationState(record({ sentence_text_sha256: HASH_B })), true);
  assert.equal(c.translationSentenceStates.get(node.id).validated, false);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
});

check("summary refresh retains unmounted verification without granting it to new hashes", () => {
  const h = harness({ virtual: true }); const c = h.context; const node = sentence();
  h.setMounted([node]); c.applySentenceTranslationState(record()); h.setMounted([]);
  c.applySentenceTranslationStates([
    record({ review_state: "reviewed" }),
    record({ sentence_id: "p-fixture.s002" }),
  ]);
  assert.equal(c.translationSentenceStates.get(node.id).validated, true);
  assert.equal(c.translationSentenceStates.get("p-fixture.s002").validated, false);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
  assert.equal(c.translationStateCountsFromSentences().reviewed, 1);
  assert.equal(c.translationStateCountsFromSentences().generated, 0);
  assert.match(c.studyProgress.title, /1개 번역됨/);
  c.applySentenceTranslationStates([record({ sentence_text_sha256: HASH_B })]);
  assert.equal(c.translationSentenceStates.get(node.id).validated, false);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
  h.setMounted([node]);
  assert.equal(c.translationSentenceStates.has(node.id), false);
});

check("binding reads recheck a mounted source even before index refresh", () => {
  const h = harness(); const c = h.context; const node = sentence();
  h.setMounted([node]); c.applySentenceTranslationState(record());
  node.dataset.sentenceSha256 = HASH_B;
  assert.equal(c.boundSentenceTranslationState(node), null);
  assert.equal(c.translationSentenceStates.has(node.id), false);
  assert.equal(c.verifiedSentenceTranslationCount(), 0);
  assert.equal(node.title, "Original source title");
});

check("same sentence and hash cannot carry state into a different page scope", () => {
  for (const key of ["corpus_id", "work_id", "variant_id"]) {
    const h = harness({ virtual: true }); const c = h.context; const node = sentence();
    h.setMounted([node]); c.applySentenceTranslationState(record());
    h.setMounted([]); c.researchData[key] = "other";
    assert.equal(c.verifiedSentenceTranslationCount(), 0);
    assert.deepEqual([...c.generatedSentenceCandidateIds()], []);
    h.setMounted([node]);
    assert.equal(c.translationSentenceStates.has(node.id), false);
    assert.equal(node.classList.contains("has-translation-state"), false);
  }
});

check("virtual review skips null, request failure, and stale hash before valid candidate", async () => {
  const h = harness({ virtual: true }); const c = h.context; const calls = [];
  const ids = [1, 2, 3, 4].map((number) => `p-fixture.s00${number}`);
  ids.forEach((sentence_id) => c.applySentenceTranslationState(record({ sentence_id })));
  const valid = sentence(ids[3], HASH_A, 4);
  c.virtualWork.ensureTarget = async (id) => {
    calls.push(id);
    if (id === ids[0]) return null;
    if (id === ids[1]) throw new Error("Synthetic request failure");
    const node = id === ids[2] ? sentence(id, HASH_B, 3) : valid;
    h.setMounted([node]);
    return node;
  };
  assert.equal(await c.nextVirtualReviewSentenceNode(), valid);
  assert.deepEqual(calls, ids);
  assert.equal(c.translationSentenceStates.has(ids[0]), false);
  assert.equal(c.translationSentenceStates.has(ids[2]), false);
  assert.equal(c.sentenceTranslationState(valid), "generated");
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
});

check("virtual review exhausts removed and stale candidates without selecting either", async () => {
  const h = harness({ virtual: true }); const c = h.context;
  c.applySentenceTranslationState(record());
  c.applySentenceTranslationState(record({ sentence_id: "p-fixture.s002" }));
  c.virtualWork.ensureTarget = async (id) => {
    if (id.endsWith("s001")) return null;
    const stale = sentence(id, HASH_B, 2); h.setMounted([stale]); return stale;
  };
  assert.equal(await c.nextVirtualReviewSentenceNode(), null);
  assert.equal(c.translationSentenceStates.size, 0);
  assert.equal(c.nextReviewSentenceButton.disabled, true);
});

check("virtual untranslated search skips only source-validated records", async () => {
  const h = harness({ virtual: true }); const c = h.context;
  const valid = sentence(); const stale = sentence("p-fixture.s002", HASH_B, 2);
  c.applySentenceTranslationState(record({ review_state: "reviewed" }));
  c.applySentenceTranslationState(record({ sentence_id: stale.id, review_state: "reviewed" }));
  const calls = [];
  c.virtualWork.ensureChunk = async (index) => {
    calls.push(index); h.setMounted([valid, stale]);
    return { querySelectorAll: () => [valid, stale] };
  };
  assert.equal(await c.nextVirtualUnstudiedSentenceNode(), stale);
  assert.deepEqual(calls, [1]);
  assert.equal(c.sentenceHasTranslationState(valid), true);
  assert.equal(c.sentenceHasTranslationState(stale), false);
  assert.equal(c.verifiedSentenceTranslationCount(), 1);
});

check("summary requests include exact variant even when blank and validate returned states", async () => {
  for (const variant of ["", "edition-a"]) {
    const h = harness({ variant }); const c = h.context; const node = sentence();
    h.setMounted([node]); let requestedUrl;
    c.fetch = async (url) => {
      requestedUrl = new URL(url, "https://example.invalid");
      return { ok: true, json: async () => ({
        ok: true, count: 3, sentence_state_count: 99,
        review_state_counts: { generated: 2, reviewed: 1, rejected: 0 },
        sentence_states: [
          record({ variant_id: variant, sentence_text_sha256: HASH_B }),
          record({ variant_id: variant, review_state: "reviewed" }),
          record({ variant_id: "wrong-variant" }),
        ],
      }) };
    };
    await c.loadTranslationRecordsSummary();
    assert.equal(requestedUrl.pathname, "/api/sentence-translations/summary");
    assert.equal(requestedUrl.searchParams.has("variant_id"), true);
    assert.equal(requestedUrl.searchParams.get("variant_id"), variant);
    assert.equal(requestedUrl.searchParams.get("corpus_id"), SCOPE.corpus_id);
    assert.equal(requestedUrl.searchParams.get("work_id"), SCOPE.work_id);
    assert.equal(c.translationSentenceStatesLoaded, true);
    assert.equal(c.verifiedSentenceTranslationCount(), 1);
    assert.equal(node.dataset.translationState, "reviewed");
    assert.match(c.translationRecordsSummary.title, /1개 문장 학습됨/);
    assert.doesNotMatch(c.translationRecordsSummary.title, /99개 문장/);
  }
});

check("mounted source hash wins over newer records for another source in either summary order", () => {
  const oldSource = record({
    id: "old-source-newer-update", sentence_text_sha256: HASH_A,
    review_state: "generated", updated_at: "2026-01-03T00:00:00Z",
  });
  const currentSource = record({
    id: "current-source-reviewed", sentence_text_sha256: HASH_B,
    review_state: "reviewed", updated_at: "2026-01-02T00:00:00Z",
  });
  const earlierCurrentSource = record({
    id: "current-source-earlier", sentence_text_sha256: HASH_B,
    review_state: "generated", updated_at: "2026-01-01T00:00:00Z",
  });
  const orders = [
    [oldSource, currentSource], [currentSource, oldSource],
    [earlierCurrentSource, currentSource, oldSource],
    [oldSource, currentSource, earlierCurrentSource],
  ];
  for (const summary of orders) {
    const h = harness(); const c = h.context; const node = sentence(undefined, HASH_B);
    h.setMounted([node]); c.selectedSentence = { sentenceId: node.id };
    assert.equal(c.renderTranslationRecord(currentSource, true), true);
    const selectedHtml = c.translationOutput.innerHTML;
    c.applySentenceTranslationStates(summary);
    const state = c.boundSentenceTranslationState(node);
    assert.equal(state.sentenceHash, HASH_B);
    assert.equal(state.recordId, currentSource.id);
    assert.equal(state.reviewState, "reviewed");
    assert.equal(node.dataset.translationState, "reviewed");
    assert.equal(node.classList.contains("has-translation-state"), true);
    assert.equal(c.verifiedSentenceTranslationCount(), 1);
    assert.equal(c.translationStateCountsFromSentences().reviewed, 1);
    assert.equal(c.translationStateCountsFromSentences().generated, 0);
    assert.equal(c.selectedTranslationRecord, currentSource);
    assert.equal(c.translationOutput.innerHTML, selectedHtml);
  }
});

check("virtual summaries retain both source candidates and validate the mounted hash regardless of order", () => {
  const oldSource = record({
    id: "virtual-old-source", sentence_text_sha256: HASH_A,
    review_state: "generated", updated_at: "2026-01-03T00:00:00Z",
  });
  const currentSource = record({
    id: "virtual-current-source", sentence_text_sha256: HASH_B,
    review_state: "reviewed", updated_at: "2026-01-02T00:00:00Z",
  });
  const orders = [[oldSource, currentSource], [currentSource, oldSource]];
  for (const summary of orders) {
    const h = harness({ virtual: true }); const c = h.context;
    const node = sentence(undefined, HASH_B);
    h.setMounted([]); c.applySentenceTranslationStates(summary);
    const candidates = c.translationSentenceCandidates.get(node.id);
    assert.equal(candidates.size, 2);
    assert.equal(candidates.get(HASH_A).recordId, oldSource.id);
    assert.equal(candidates.get(HASH_B).recordId, currentSource.id);
    assert.equal(candidates.get(HASH_A).validated, false);
    assert.equal(candidates.get(HASH_B).validated, false);
    assert.equal(c.verifiedSentenceTranslationCount(), 0);
    assert.equal(c.nextGeneratedSentenceId(), "");
    h.setMounted([node]);
    assert.equal(c.boundSentenceTranslationState(node).recordId, currentSource.id);
    assert.equal(c.boundSentenceTranslationState(node).sentenceHash, HASH_B);
    assert.equal(node.dataset.translationState, "reviewed");
    assert.equal(c.verifiedSentenceTranslationCount(), 1);
    assert.equal(c.translationStateCountsFromSentences().generated, 0);
    h.setMounted([]);
    for (const repeatedSummary of orders) {
      c.applySentenceTranslationStates(repeatedSummary);
      assert.equal(c.translationSentenceCandidates.get(node.id).get(HASH_B).validated, true);
      assert.equal(c.verifiedSentenceTranslationCount(), 1);
      assert.equal(c.translationStateCountsFromSentences().reviewed, 1);
      assert.equal(c.translationStateCountsFromSentences().generated, 0);
    }
    h.setMounted([node]);
    assert.equal(c.boundSentenceTranslationState(node).recordId, currentSource.id);
    assert.equal(node.dataset.translationState, "reviewed");
  }
});

check("translation card accepts current binding and rejects stale records without side effects", () => {
  const h = harness(); const c = h.context; const node = sentence();
  const other = sentence("p-fixture.s002", HASH_A, 2);
  h.setMounted([node, other]); c.selectedSentence = { sentenceId: node.id };
  const accepted = record({ review_state: "reviewed" });
  assert.equal(c.renderTranslationRecord(accepted, true), true);
  assert.equal(c.selectedTranslationRecord, accepted);
  assert.match(c.translationOutput.innerHTML, /Synthetic translation/);
  assert.ok(h.effects.some((effect) => effect.name === "setTranslationReviewVisualState" && effect.args[0] === "reviewed"));
  const html = c.translationOutput.innerHTML; const effectCount = h.effects.length;
  const previousState = c.boundSentenceTranslationState(node);
  const assertUnchanged = (candidate) => {
    assert.equal(c.renderTranslationRecord(candidate, false, "generated"), false);
    assert.equal(c.selectedTranslationRecord, accepted);
    assert.equal(c.translationOutput.innerHTML, html);
    assert.equal(h.effects.length, effectCount);
    assert.equal(c.translationSentenceStates.get(node.id), previousState);
  };
  for (const overrides of [
    { sentence_id: other.id }, { sentence_text_sha256: HASH_B },
    { sentence_text_sha256: "" }, { sentence_text_sha256: `#${HASH_A}` },
    { corpus_id: "other" }, { work_id: "other" }, { variant_id: "edition-b" },
  ]) assertUnchanged(record(overrides));
  assertUnchanged(null);
  c.selectedSentence = null; assertUnchanged(accepted);
  c.selectedSentence = { sentenceId: node.id }; h.setMounted([]); assertUnchanged(accepted);
});

(async () => {
  let failed = 0;
  for (const { name, run } of cases) {
    try { await run(); process.stdout.write(`PASS ${name}\n`); }
    catch (error) {
      failed += 1;
      process.stderr.write(`FAIL ${name}\n${error.stack || error}\n`);
    }
  }
  process.stdout.write(`Sentence state binding: ${cases.length - failed}/${cases.length} checks passed.\n`);
  if (failed) process.exitCode = 1;
})().catch((error) => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
