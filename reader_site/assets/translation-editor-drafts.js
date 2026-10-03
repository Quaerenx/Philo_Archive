(function (global) {
  "use strict";
  const PREFIX = "philo.reader.translationDraft.v1:";
  const memory = new Map();
  const forms = new WeakMap();
  const externalChanges = new Set();
  const text = (record) => String(record.human_translation || record.translation || "").trim();
  const key = (record) => PREFIX + encodeURIComponent(record.corpus_id) + ":" + encodeURIComponent(record.id);
  function read(record) {
    const id = key(record);
    if (memory.has(id)) return memory.get(id);
    try {
      const value = JSON.parse(global.localStorage.getItem(id) || "null");
      if (value && value.recordId === record.id && value.corpusId === record.corpus_id
        && typeof value.text === "string" && value.text.length <= 12000 && typeof value.baseTranslation === "string") {
        memory.set(id, value); return value;
      }
    } catch { /* An unavailable store still leaves the active editor protected. */ }
    return null;
  }
  function write(record, value) {
    const id = key(record);
    memory.set(id, { ...value, persisted: false });
    if (externalChanges.has(id)) return false;
    try { const persisted = { ...value, persisted: true }; global.localStorage.setItem(id, JSON.stringify(persisted)); memory.set(id, persisted); return true; }
    catch { return false; }
  }
  function remove(record) {
    memory.set(key(record), null);
    if (externalChanges.has(key(record))) return;
    try { global.localStorage.removeItem(key(record)); } catch { /* The saved server text is authoritative. */ }
  }
  function tools(form) {
    let node = form.querySelector(".translation-draft-tools");
    if (node) return node;
    node = document.createElement("div"); node.className = "translation-draft-tools";
    node.innerHTML = '<p data-draft-status role="status" aria-live="polite"></p><div class="draft-actions">'
      + '<button type="button" data-draft-action="discard" hidden>초안 취소</button>'
      + '<button type="button" data-draft-action="restore" hidden>취소한 초안 복구</button>'
      + '<button type="button" data-draft-action="rebase" hidden>최신 번역을 확인하고 편집 계속</button></div>'
      + '<details data-draft-comparison hidden><summary>저장된 번역과 초안 비교</summary>'
      + '<h4>현재 저장된 번역</h4><p data-draft-server-text></p><h4>복구된 초안</h4><p data-draft-local-text></p></details>';
    form.append(node); return node;
  }
  function show(form, persisted) {
    const state = forms.get(form);
    if (!state) return;
    const draft = read(state.record);
    if (persisted === undefined) persisted = draft?.persisted !== false;
    const node = tools(form);
    const active = Boolean(draft && !draft.discarded);
    const conflict = active && draft.baseTranslation !== state.base;
    node.querySelector('[data-draft-action="discard"]').hidden = !active;
    node.querySelector('[data-draft-action="restore"]').hidden = !draft?.discarded;
    node.querySelector('[data-draft-action="rebase"]').hidden = !conflict;
    node.querySelector('[data-draft-comparison]').hidden = !conflict;
    const status = node.querySelector('[data-draft-status]');
    status.textContent = externalChanges.has(key(state.record)) ? "다른 탭에서 이 문장의 초안을 변경했습니다. 현재 내용을 복사한 뒤 새로고침해 확인하세요."
      : conflict ? "저장된 번역이 편집 시작 이후 바뀌었습니다. 최신 번역과 초안을 비교한 뒤 계속하세요."
      : draft?.discarded ? "초안을 취소했습니다. 취소한 내용은 복구할 수 있습니다."
        : active ? persisted ? "이 브라우저에 초안을 저장했습니다. 확정 번역에는 아직 반영되지 않았습니다."
          : "브라우저 저장소를 사용할 수 없습니다. 초안은 이 화면에만 남아 있으므로 이동 전에 내용을 복사하세요." : "";
    if (conflict) {
      node.querySelector('[data-draft-server-text]').textContent = state.base;
      node.querySelector('[data-draft-local-text]').textContent = draft.text;
    }
    form.querySelector('button[type="submit"]').disabled = conflict || externalChanges.has(key(state.record));
  }
  function attach(form, record) {
    const base = text(record);
    forms.set(form, { record, base });
    const draft = read(record);
    if (draft && !draft.discarded && draft.text.trim() === base) { remove(record); }
    else if (draft && !draft.discarded) {
      form.elements.human_translation.value = draft.text;
      form.closest("details").open = true;
    }
    show(form);
  }
  function capture(form) {
    const state = forms.get(form);
    if (!state) return;
    const value = form.elements.human_translation.value;
    const previous = read(state.record);
    if (value === state.base) { remove(state.record); show(form); return; }
    const draft = { recordId: state.record.id, corpusId: state.record.corpus_id, text: value,
      baseTranslation: previous && !previous.discarded ? previous.baseTranslation : state.base,
      updatedAt: new Date().toISOString(), discarded: false };
    show(form, write(state.record, draft));
  }
  function snapshot(form) {
    capture(form);
    const state = forms.get(form);
    const draft = state && read(state.record);
    return { text: form.elements.human_translation.value.trim(), baseTranslation: draft && !draft.discarded ? draft.baseTranslation : state?.base };
  }
  function saved(record, sentText) {
    const draft = read(record);
    if (!draft || draft.discarded || draft.text.trim() === sentText) { remove(record); return; }
    write(record, { ...draft, baseTranslation: text(record) });
  }
  function action(form, name) {
    const state = forms.get(form);
    const draft = state && read(state.record);
    if (!state || !draft) return;
    if (name === "discard") {
      write(state.record, { ...draft, discarded: true });
      form.elements.human_translation.value = state.base;
    } else if (name === "restore") {
      write(state.record, { ...draft, discarded: false });
      form.elements.human_translation.value = draft.text;
    } else if (name === "rebase") {
      write(state.record, { ...draft, baseTranslation: state.base });
    }
    show(form); form.elements.human_translation.focus();
  }
  function hasPending() {
    return Array.from(memory.values()).some((draft) => draft && !draft.discarded);
  }
  function initialize(root) {
    root.addEventListener("input", (event) => {
      const form = event.target.closest("form[data-human-translation-form]");
      if (form) capture(form);
    });
    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-draft-action]");
      if (button) action(button.closest("form"), button.dataset.draftAction);
    });
    global.addEventListener("beforeunload", (event) => {
      if (!hasPending()) return;
      event.preventDefault(); event.returnValue = "";
    });
    global.addEventListener("storage", (event) => {
      if (!event.key?.startsWith(PREFIX)) return;
      // Preserve the other tab's stored draft; this tab remains protected by the leave guard.
      root.querySelectorAll("form[data-human-translation-form]").forEach((form) => {
        const state = forms.get(form);
        if (state && key(state.record) === event.key) {
          externalChanges.add(event.key); show(form);
        }
      });
    });
  }
  global.TranslationDrafts = Object.freeze({ attach, capture, snapshot, saved, action, hasPending, initialize });
})(window);
