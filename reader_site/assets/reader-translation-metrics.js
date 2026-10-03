// Local, bounded numeric diagnostics. No source, prompt, translation, or target IDs.
const READER_METRICS_KEY = "philo.reader.translation-metrics.v1";
let readerTranslationActionStarted = null;
function markReaderTranslationAction(event) {
  if (event.type === "keydown" && !["Enter", " "].includes(event.key)) return;
  if (event.target.closest?.('.reader-sentence, #translateSentence, #regenerateSentence, #previousSentence, #nextSentence, #nextUnstudiedSentence, #nextReviewSentence, [data-translation-quick-action="next-sentence"], [data-translation-quick-action="previous-sentence"]')) {
    readerTranslationActionStarted = performance.now();
  }
}
document.addEventListener?.("click", markReaderTranslationAction, true);
document.addEventListener?.("keydown", markReaderTranslationAction, true);
function consumeReaderTranslationAction() {
  const started = readerTranslationActionStarted;
  readerTranslationActionStarted = null;
  return started !== null && performance.now() - started <= 30000 ? started : null;
}
function readerMetricSamples() {
  try {
    const rows = JSON.parse(localStorage.getItem(READER_METRICS_KEY) || "[]");
    return Array.isArray(rows) ? rows.filter(row => Number.isFinite(row.milliseconds) && row.milliseconds >= 0).slice(-200).map(row => ({
      milliseconds: row.milliseconds, cached: Boolean(row.cached), revisions: Number(row.revisions || 0),
      modelCalls: Number.isFinite(row.modelCalls) ? row.modelCalls : null, truncated: Boolean(row.truncated),
      promptTokens: (Array.isArray(row.promptTokens) ? row.promptTokens : []).filter(Number.isFinite).slice(0,4),
      completionTokens: (Array.isArray(row.completionTokens) ? row.completionTokens : []).filter(Number.isFinite).slice(0,4),
      availableContext: (Array.isArray(row.availableContext) ? row.availableContext : []).filter(Number.isFinite).slice(0,4)
    })) : [];
  } catch (_) { return []; }
}

function recordTranslationRender(started, payload, stillCurrent) {
  if (!Number.isFinite(started)) return;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (!stillCurrent() || document.visibilityState !== "visible" || !translationOutput.getClientRects().length) return;
    const metrics = payload.metrics || {};
    const row = {
      milliseconds: performance.now() - started,
      cached: Boolean(payload.cached),
      revisions: payload.cached ? 0 : Number(payload.record?.revision_count || 0),
      modelCalls: payload.cached ? 0 : (Number.isFinite(metrics.model_calls) ? metrics.model_calls : null),
      truncated: !payload.cached && Boolean(metrics.context_truncated),
      promptTokens: (metrics.model_usage || []).map(call => call.prompt_tokens).filter(Number.isFinite),
      completionTokens: (metrics.model_usage || []).map(call => call.completion_tokens).filter(Number.isFinite),
      availableContext: (metrics.model_usage || []).map(call => call.available_context).filter(Number.isFinite)
    };
    try { localStorage.setItem(READER_METRICS_KEY, JSON.stringify([...readerMetricSamples(), row].slice(-200))); } catch (_) {}
  }));
}

function readerTranslationMetrics() {
  const rows = readerMetricSamples();
  const percentile = (values, fraction) => values.length ? [...values].sort((a,b) => a-b)[Math.max(0, Math.ceil(values.length*fraction)-1)] : null;
  const summary = samples => ({count: samples.length, p50_ms: percentile(samples.map(row => row.milliseconds), .5), p95_ms: percentile(samples.map(row => row.milliseconds), .95)});
  const generated = rows.filter(row => !row.cached);
  const tokens = generated.flatMap(row => row.promptTokens || []);
  const measuredCalls = generated.filter(row => Number.isFinite(row.modelCalls));
  return {
    scope: "last 200 successful visible renders; click-handler entry to paint; nearest-rank percentiles",
    all: summary(rows), generation: summary(generated), cache: summary(rows.filter(row => row.cached)),
    cache_hit_rate: rows.length ? rows.filter(row => row.cached).length / rows.length : null,
    revision_rate: generated.length ? generated.filter(row => row.revisions > 0).length / generated.length : null,
    mean_model_calls: measuredCalls.length ? measuredCalls.reduce((sum,row) => sum+row.modelCalls,0)/measuredCalls.length : null,
    prompt_tokens: {count: tokens.length, p50: percentile(tokens,.5), p95: percentile(tokens,.95), max: tokens.length ? Math.max(...tokens) : null},
    context_truncations: generated.filter(row => row.truncated).length
  };
}
