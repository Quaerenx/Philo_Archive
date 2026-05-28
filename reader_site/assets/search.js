const form = document.getElementById("searchForm");
const queryInput = document.getElementById("queryInput");
const corpusSelect = document.getElementById("corpusSelect");
const statusEl = document.getElementById("searchStatus");
const resultsEl = document.getElementById("results");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function highlight(value, query) {
  let output = escapeHtml(value);
  const terms = String(query || "").trim().split(/\s+/).filter(Boolean);
  for (const term of terms) {
    const safe = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    output = output.replace(new RegExp(`(${safe})`, "gi"), "<mark>$1</mark>");
  }
  return output;
}

function updateUrl(query, corpusId) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (corpusId) params.set("corpus_id", corpusId);
  history.replaceState(null, "", params.toString() ? `/search?${params}` : "/search");
}

function renderResults(payload, query) {
  statusEl.textContent = payload.count
    ? `${payload.count.toLocaleString()} matching segments`
    : query ? "No matching segments." : "";
  resultsEl.innerHTML = (payload.results || [])
    .map((result) => {
      const meta = [
        result.corpus_id,
        result.work_id,
        result.variant_id,
        result.label
      ].filter(Boolean).join(" / ");
      return `<article class="result">
        <div class="result-title">
          <a href="${escapeHtml(result.url)}">${escapeHtml(result.title || result.work_id)}</a>
          <span class="result-meta">${escapeHtml(meta)}</span>
        </div>
        <p class="snippet">${highlight(result.snippet || "", query)}</p>
      </article>`;
    })
    .join("");
}

async function runSearch() {
  const query = queryInput.value.trim();
  const corpusId = corpusSelect.value;
  updateUrl(query, corpusId);
  if (!query) {
    statusEl.textContent = "";
    resultsEl.innerHTML = "";
    return;
  }
  statusEl.textContent = "Searching...";
  resultsEl.innerHTML = "";
  const params = new URLSearchParams({ q: query, limit: "40" });
  if (corpusId) params.set("corpus_id", corpusId);
  const response = await fetch(`/api/search?${params}`);
  if (!response.ok) {
    statusEl.textContent = "Search failed.";
    return;
  }
  renderResults(await response.json(), query);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

const initialParams = new URLSearchParams(location.search);
queryInput.value = initialParams.get("q") || "";
corpusSelect.value = initialParams.get("corpus_id") || "";
if (queryInput.value) {
  runSearch();
}
