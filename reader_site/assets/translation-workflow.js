(function (global) {
  "use strict";
  const text = (value) => String(value || "").trim();
  function timestamp(record, human = false) {
    const fields = human ? ["human_translation_updated_at", "reviewed_at", "updated_at", "generated_at", "created_at"]
      : ["generated_at", "created_at", "updated_at"];
    for (const field of fields) { const stamp = Date.parse(record[field] || ""); if (Number.isFinite(stamp)) return stamp; }
    return 0;
  }
  function state(record) {
    const currentIssues = [...(record.current_translation_issues || []), ...(record.current_note_issues || [])];
    const human = Boolean(text(record.human_translation));
    if (record.source_current === false) return { human, label: "이전 번역 기록 · 원문 연결 확인", kind: "attention" };
    if (Object.hasOwn(record, "source_current") && record.source_current === null) return { human, label: "원문 확인 필요", kind: "attention" };
    const label = human ? "사람 확정" : record.review_state === "reviewed" ? "저장한 모델 번역"
      : record.review_state === "rejected" ? "제외한 모델 번역" : "검토 대기";
    return { human, label: currentIssues.length ? `${label} · 재검토 필요` : label,
      kind: currentIssues.length ? "attention" : human ? "confirmed" : record.review_state || "generated" };
  }
  function compareCurrent(left, right) {
    const sourceRank = (record) => record.source_current === true ? 2 : record.source_current === false ? 0 : 1;
    const source = sourceRank(right) - sourceRank(left);
    if (source) return source;
    const human = Number(Boolean(text(right.human_translation))) - Number(Boolean(text(left.human_translation)));
    if (human) return human;
    const reviewed = Number(right.review_state === "reviewed") - Number(left.review_state === "reviewed");
    if (reviewed) return reviewed;
    return timestamp(right, state(right).human) - timestamp(left, state(left).human);
  }
  function sentenceKey(record) {
    return [record.corpus_id, record.work_id, record.variant_id || "", record.segment_id,
      record.sentence_id || record.target_id || record.id].join("\u001f");
  }
  function currentRecords(records) {
    const grouped = new Map();
    records.forEach((record) => {
      const key = sentenceKey(record);
      const current = grouped.get(key);
      if (!current || compareCurrent(record, current) < 0) grouped.set(key, record);
    });
    return Array.from(grouped.values());
  }
  function priority(record) {
    if (record.source_current === false) return { rank: 1, label: "원문 연결 확인", reason: "저장된 번역이 현재 문장과 연결되지 않습니다. 현재 원문에서 번역을 확인하세요." };
    if (Object.hasOwn(record, "source_current") && record.source_current === null) return { rank: 2, label: "원문 확인 필요", reason: "저장된 번역과 현재 원문의 연결을 확인하지 못했습니다." };
    const source = record.current_translation_issues || [];
    const notes = record.current_note_issues || [];
    if (source.length) return { rank: 1, label: "원문 의미 재검토", reason: source.map((item) => item.explanation).filter(Boolean).join(" ") };
    if (notes.length || ["notes_review_required", "translation_review_required"].includes(record.commentary_status)) {
      return { rank: 2, label: "번역 노트 재검토", reason: notes.map((item) => item.explanation).filter(Boolean).join(" ") || "현재 번역에 연결된 노트를 검토하세요." };
    }
    // The old model verdict does not override a human-confirmed translation.
    if (state(record).human || record.review_state === "rejected") return null;
    const issues = record.critic?.final?.issues || record.critic?.initial?.issues || record.critic_issues || record.quality_issues || [];
    if (record.quality_state === "critic_error") return { rank: 3, label: "자동 검토 확인", reason: "자동 검토를 완료하지 못한 모델 번역입니다." };
    if (record.quality_state === "needs_human_review") {
      return { rank: issues.some((item) => item.severity === "major") ? 1 : 3,
        label: issues.some((item) => item.severity === "major") ? "모델 의미 오류 검토" : "모델 번역 검토",
        reason: issues.map((item) => item.explanation).filter(Boolean).join(" ") || "자동 검토에서 해결되지 않은 문제가 있습니다." };
    }
    return record.review_state !== "reviewed" ? { rank: 4, label: "확정 전 검토", reason: "아직 사람이 저장하거나 확정하지 않은 번역입니다." } : null;
  }
  function queue(records) {
    return currentRecords(records).map((record) => ({ record, priority: priority(record) }))
      .filter((item) => item.priority)
      .sort((left, right) => left.priority.rank - right.priority.rank
        || timestamp(left.record) - timestamp(right.record) || text(left.record.id).localeCompare(text(right.record.id)));
  }
  global.TranslationWorkflow = Object.freeze({ state, compareCurrent, currentRecords, priority, queue });
})(window);
