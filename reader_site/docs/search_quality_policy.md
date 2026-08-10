# Search Quality Policy

Search quality is measured against `data/search_eval_queries.json`. The suite combines stable lookup benchmarks with manually curated research questions; it never records or uploads a user's live search history.

## Evaluation Sets

- **Benchmark cases** cover work sigla, title aliases, Bible references, corpus/work/variant filters, and known source phrases.
- **Research-question cases** start from a human-readable scholarly question and pair it with the source-language terms a researcher would enter into this lexical search system.
- Research-question coverage must include Nietzsche, Bible, Kierkegaard, and Wittgenstein.

The initial research set covers 12 questions: three per corpus. It includes German concepts and phrases, Danish terms, Wittgenstein manuscript language, Hebrew morphology text, and Greek New Testament text.

## Change Rule

- Add a case when a real study need is reproducible and its expected source target can be verified.
- Do not log user searches automatically.
- Do not tune a query-specific exception merely to make one case pass.
- Change ranking or normalization only when a failed case exposes a general rule that also preserves existing contracts.
- Keep SQLite FTS5 and JSONL fallback result contracts compatible.

## Metrics

`check_search_relevance.py` reports pass count, mean reciprocal rank, and recall at 1, 3, and 10. Every committed case must pass; metric changes remain visible for review.

Run:

```powershell
python .\scripts\check_search_contracts.py
python .\scripts\check_search_relevance.py
python .\scripts\check_search_artifact_integrity.py
```
