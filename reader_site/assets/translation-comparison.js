(function (global) {
  "use strict";

  function escape(value) {
    return String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  function tokens(text) {
    return String(text || "").match(/[\p{L}\p{M}\p{N}]+|\s+|[^\p{L}\p{M}\p{N}\s]/gu) || [];
  }

  // Bound quadratic work: long passages still show both complete texts.
  function difference(model, confirmed) {
    const left = tokens(model);
    const right = tokens(confirmed);
    if (left.length * right.length > 160000) {
      return { model: escape(model), confirmed: escape(confirmed), limited: true };
    }
    const rows = Array.from({ length: left.length + 1 }, () => new Uint16Array(right.length + 1));
    for (let i = left.length - 1; i >= 0; i--) {
      for (let j = right.length - 1; j >= 0; j--) {
        rows[i][j] = left[i] === right[j] ? rows[i + 1][j + 1] + 1
          : Math.max(rows[i + 1][j], rows[i][j + 1]);
      }
    }
    const removed = new Set();
    const added = new Set();
    let i = 0;
    let j = 0;
    while (i < left.length && j < right.length) {
      if (left[i] === right[j]) { i++; j++; }
      else if (rows[i + 1][j] >= rows[i][j + 1]) { removed.add(i++); }
      else { added.add(j++); }
    }
    while (i < left.length) removed.add(i++);
    while (j < right.length) added.add(j++);
    const markup = (parts, changed, kind) => parts.map((part, index) => changed.has(index) && part.trim()
      ? `<mark class="comparison-${kind}">${escape(part)}</mark>` : escape(part)).join("");
    return { model: markup(left, removed, "removed"), confirmed: markup(right, added, "added"), limited: false };
  }

  function render(record, sourceFallback = "") {
    const source = String(record.note_source_text || sourceFallback || record.source_text_excerpt || "").trim();
    const model = String(record.translation || "").trim();
    const confirmed = String(record.human_translation || "").trim();
    if (!source && !model && !confirmed) return "";
    const diff = confirmed ? difference(model, confirmed) : { model: escape(model), confirmed: "" };
    const same = Boolean(confirmed && confirmed === model);
    const help = !confirmed ? "확정 번역이 아직 없습니다."
      : same ? "모델 원본과 확정 번역이 같습니다."
        : diff.limited ? "긴 문장이므로 차이 강조 없이 전체 내용을 표시합니다."
          : "노란색: 모델 원본에서 바뀐 표현 · 초록색: 확정 번역에 반영한 표현. 색이 다른 부분은 밑줄로도 표시합니다.";
    return `<details class="translation-comparison">
      <summary>번역 비교${confirmed ? " · 확정본 있음" : ""}</summary>
      <div class="comparison-body">
        <section class="comparison-source"><h3>원문</h3><p dir="auto">${escape(source)}</p></section>
        <p class="comparison-help">${help}</p>
        <div class="comparison-columns">
          <section><h3>모델 원본</h3><p>${diff.model || "모델 원본이 없습니다."}</p></section>
          <section><h3>확정 번역</h3><p>${diff.confirmed || "아직 확정하지 않았습니다."}</p></section>
        </div>
      </div>
    </details>`;
  }

  global.TranslationComparison = Object.freeze({ difference, render });
})(window);
