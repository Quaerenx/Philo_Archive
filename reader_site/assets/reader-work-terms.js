// Explain only registered terms and notes bound to the current translation.
let readerTermEntries = [];
let decoratedTermSentence = null;
let activeReaderTermButton = null;

function registeredReaderTerms() {
  const approved = Array.isArray(researchData.reading_terms) ? researchData.reading_terms : [];
  const concepts = Array.from(document.querySelectorAll(".concept-link[data-term-source]")).map((link) => ({
    source: link.dataset.termSource,
    target: link.textContent,
    note: link.dataset.termNote,
    kind: "registered"
  }));
  return [...approved, ...concepts];
}

function termOccurrences(text, source) {
  const matches = [];
  if (!source || source.length > 500) return matches;
  let start = text.indexOf(source);
  const word = /[\p{L}\p{M}\p{N}]/u;
  while (start >= 0) {
    const end = start + source.length;
    const before = text.slice(0, start).match(/.$/u)?.[0] || "";
    const after = text.slice(end).match(/^./u)?.[0] || "";
    if (!(word.test(source[0]) && word.test(before)) && !(word.test(source.at(-1)) && word.test(after))) {
      matches.push({ start, end });
    }
    start = text.indexOf(source, end);
  }
  return matches;
}

function termsForSentence(text, record = null) {
  const terms = [];
  const seen = new Set();
  const notes = record?.commentary_status === "current" && record.note_source_text
    && cleanText(record.note_source_text) === cleanText(text) && !record.current_note_issues?.length
    && !record.current_translation_issues?.length && Array.isArray(record.translation_notes)
    ? record.translation_notes.map((note) => ({ source: note.source_span, note: note.note,
      kind: record.human_translation ? "confirmed-note" : "model-note" })) : [];
  [...notes, ...registeredReaderTerms()].forEach((term) => {
    const source = String(term.source || "").trim();
    if (!source || seen.has(source) || !termOccurrences(text, source).length) return;
    if (!term.target && !term.note) return;
    seen.add(source);
    terms.push({ ...term, source });
  });
  return terms.slice(0, 12);
}

function clearReaderTermDecoration() {
  decoratedTermSentence?.querySelectorAll("[data-reader-term]").forEach((button) => {
    button.replaceWith(document.createTextNode(button.textContent));
  });
  decoratedTermSentence?.normalize();
  decoratedTermSentence = null;
}

function closeReaderTermCard(returnFocus = false) {
  const card = document.getElementById("readerTermCard");
  if (card) card.hidden = true;
  activeReaderTermButton?.setAttribute("aria-expanded", "false");
  if (returnFocus && activeReaderTermButton?.isConnected) activeReaderTermButton.focus({ preventScroll: true });
  activeReaderTermButton = null;
}

function decorateReaderTermSentence(node) {
  if (!node || !readerTermEntries.length) return;
  decoratedTermSentence = node;
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
    acceptNode: (text) => text.parentElement.closest("a, button, script, style")
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
  });
  const texts = [];
  while (walker.nextNode()) texts.push(walker.currentNode);
  texts.forEach((textNode) => {
    const text = textNode.textContent;
    const matches = readerTermEntries.flatMap((term, index) => termOccurrences(text, term.source)
      .map((match) => ({ ...match, index })));
    matches.sort((left, right) => left.start - right.start || right.end - left.end);
    if (!matches.length) return;
    const fragment = document.createDocumentFragment();
    let end = 0;
    matches.forEach((match) => {
      if (match.start < end) return;
      fragment.append(document.createTextNode(text.slice(end, match.start)));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "reader-term";
      button.dataset.readerTerm = String(match.index);
      button.setAttribute("aria-controls", "readerTermCard");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", `${text.slice(match.start, match.end)} 설명 보기`);
      button.textContent = text.slice(match.start, match.end);
      fragment.append(button);
      end = match.end;
    });
    fragment.append(document.createTextNode(text.slice(end)));
    textNode.replaceWith(fragment);
  });
}

function updateReaderTerms(record = null) {
  closeReaderTermCard();
  clearReaderTermDecoration();
  readerTermEntries = selectedSentence ? termsForSentence(selectedSentence.text, record) : [];
  const strip = document.getElementById("readerTermStrip");
  if (!strip) return;
  strip.hidden = !readerTermEntries.length;
  strip.innerHTML = readerTermEntries.length ? `<span>이 문장의 용어·표현</span>${readerTermEntries.map((term, index) =>
    `<button type="button" data-reader-term="${index}" aria-controls="readerTermCard" aria-expanded="false">${escapeHtml(term.source)}</button>`).join("")}` : "";
  decorateReaderTermSentence(selectedSentenceNode());
}

function openReaderTermCard(button) {
  const term = readerTermEntries[Number(button.dataset.readerTerm)];
  const card = document.getElementById("readerTermCard");
  if (!term || !card) return;
  const wasOpen = activeReaderTermButton === button && !card.hidden;
  closeReaderTermCard();
  if (wasOpen) return;
  const provenance = { approved: "사람 승인 용어", registered: "등록된 작품 개념", "confirmed-note": "확정 번역 노트", "model-note": "자동 검토된 번역 노트" }[term.kind];
  const search = new URLSearchParams({ q: term.source, corpus_id: researchData.corpus_id || researchData.author_id || "",
    work_id: researchData.work_id || "", from: currentWorkHref(), from_label: researchData.title || "읽던 문서" });
  card.innerHTML = `<div class="reader-term-card-heading"><h3>${escapeHtml(term.source)}</h3>
    <button type="button" data-close-reader-term aria-label="용어 설명 닫기">닫기</button></div>
    ${term.target ? `<p class="reader-term-target">${escapeHtml(term.target)}</p>` : ""}
    ${term.note ? `<p>${escapeHtml(term.note)}</p>` : ""}
    <p class="reader-term-provenance">${escapeHtml(provenance || "등록 용어")}</p>
    <a href="/search?${escapeHtml(search)}">이 작품에서 더 찾기</a>`;
  card.hidden = false;
  activeReaderTermButton = button;
  button.setAttribute("aria-expanded", "true");
  setStudyPanel("translation");
  setStudyPanelExpanded(true);
  card.scrollIntoView({ block: "nearest", behavior: "auto" });
  card.querySelector("[data-close-reader-term]").focus({ preventScroll: true });
}

function initializeReaderTerms() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-reader-term]");
    if (button) { event.preventDefault(); openReaderTermCard(button); }
    if (event.target.closest("[data-close-reader-term]")) closeReaderTermCard(true);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeReaderTermButton) {
      event.preventDefault(); event.stopImmediatePropagation(); closeReaderTermCard(true);
    }
  }, true);
}
