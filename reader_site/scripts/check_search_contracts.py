from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"
sys.path.insert(0, str(SITE))

import services.search as search_service  # noqa: E402
from services.search import search_payload_from_query, search_records  # noqa: E402
from services.notes import append_note, note_storage_path  # noqa: E402


NOTE_CORPUS_ID = "contract_search"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_results(payload: dict, context: str) -> list[dict]:
    results = payload.get("results", [])
    require(results, f"{context} returned no results")
    return results


def check_bible_direct_lookup() -> None:
    cases = [
        ("Gen 1:1", "", "oshb.Gen", "Gen.1.1"),
        ("Genesis 1:1", "", "oshb.Gen", "Gen.1.1"),
        ("lxx Gen 1:1", "", "lxx.Gen", "Gen.1.1"),
        ("John 3:16", "", "sblgnt.John", "John.3.16"),
        ("1 John 5:7", "", "sblgnt.1John", "1John.5.7"),
        ("창 1:1", "", "oshb.Gen", "Gen.1.1"),
        ("요 3:16", "", "sblgnt.John", "John.3.16"),
        ("요일 5:7", "", "sblgnt.1John", "1John.5.7"),
        ("시 23:1", "", "oshb.Ps", "Ps.23.1"),
        ("계 1:1", "", "sblgnt.Rev", "Rev.1.1"),
        ("Gen 1:1", "lxx.Gen", "lxx.Gen", "Gen.1.1"),
        ("Tob 1:1", "", "lxx.Tob", "Tob.1.1"),
        ("Wis 1:1", "", "lxx.Wis", "Wis.1.1"),
        ("Sir 1:1", "", "lxx.Sir", "Sir.1.1"),
        ("EpJer 1:1", "", "lxx.LetJer", "LetJer.0.1"),
        ("Psalm 151:1", "", "lxx.PsLXX", "PsLXX.151.1"),
    ]
    for query, work_filter, expected_work, expected_segment in cases:
        payload = search_records(query, work_id=work_filter, limit=5)
        results = require_results(payload, query)
        first = results[0]
        require(payload.get("engine") == "sqlite-direct-bible", f"{query} did not use direct Bible lookup")
        require(first.get("work_id") == expected_work, f"{query} expected {expected_work}, got {first.get('work_id')}")
        require(
            first.get("segment_id") == expected_segment,
            f"{query} expected {expected_segment}, got {first.get('segment_id')}",
        )
        require(first.get("url", "").endswith("#" + expected_segment), f"{query} URL does not target verse anchor")


def check_filters() -> None:
    nietzsche = search_records("ressentiment", corpus_id="nietzsche", limit=5)
    nietzsche_results = require_results(nietzsche, "nietzsche ressentiment")
    require(all(item.get("corpus_id") == "nietzsche" for item in nietzsche_results), "nietzsche filter leaked")

    nietzsche_work = search_records("ressentiment", corpus_id="nietzsche", work_id="GM", limit=5)
    nietzsche_work_results = require_results(nietzsche_work, "nietzsche GM ressentiment")
    require(all(item.get("work_id") == "GM" for item in nietzsche_work_results), "work filter leaked")

    wittgenstein = search_records("language", corpus_id="wittgenstein", limit=5)
    wittgenstein_results = require_results(wittgenstein, "wittgenstein language")
    require(all(item.get("corpus_id") == "wittgenstein" for item in wittgenstein_results), "wittgenstein filter leaked")

    variant = search_records("Gen 1:1", corpus_id="bible", variant_id="lxx_swete", limit=5)
    variant_results = require_results(variant, "lxx variant direct lookup")
    require(variant_results[0].get("work_id") == "lxx.Gen", "variant filter did not prefer LXX Genesis")


def check_query_payload_helper() -> None:
    payload = search_payload_from_query({"q": ["M"], "corpus_id": ["nietzsche!!"], "limit": ["not-a-number"]})
    work_results = payload.get("work_results", [])
    require(work_results and work_results[0].get("work_id") == "M", "search query payload helper failed")

    limited = search_payload_from_query({"q": ["John"], "corpus_id": ["bible"], "limit": ["0"]})
    require(len(limited.get("work_results", [])) <= 1, "search query limit clamp failed")


def check_work_alias_search() -> None:
    single_letter = search_records("M", corpus_id="nietzsche", limit=5)
    single_letter_results = single_letter.get("work_results", [])
    require(single_letter_results and single_letter_results[0].get("work_id") == "M", "nietzsche M alias did not rank M first")
    require(
        all(item.get("work_id") == "M" for item in single_letter_results),
        "single-letter Nietzsche alias should not return partial title matches",
    )

    nietzsche = search_records("GM", corpus_id="nietzsche", limit=5)
    work_results = nietzsche.get("work_results", [])
    require(work_results, "nietzsche work alias returned no work results")
    require(work_results[0].get("work_id") == "GM", "nietzsche GM alias did not rank GM first")
    require(work_results[0].get("url") == "/work/nietzsche/GM", "nietzsche GM alias URL failed")

    bible = search_records("John", corpus_id="bible", limit=5)
    bible_work_results = bible.get("work_results", [])
    require(any(item.get("work_id") == "sblgnt.John" for item in bible_work_results), "Bible John alias missing SBLGNT John")
    require(bible_work_results[0].get("work_id") == "sblgnt.John", "Bible John alias did not rank John first")

    first_john = search_records("1 John", corpus_id="bible", limit=5)
    first_john_results = first_john.get("work_results", [])
    require(first_john_results and first_john_results[0].get("work_id") == "sblgnt.1John", "Bible 1 John alias failed")
    require(all("John" in item.get("work_id", "") for item in first_john_results), "Bible 1 John alias leaked unrelated books")

    genesis = search_records("Genesis", corpus_id="bible", limit=5)
    genesis_results = genesis.get("work_results", [])
    require(genesis_results and genesis_results[0].get("work_id") == "oshb.Gen", "Genesis should prefer OSHB")

    lxx_genesis = search_records("lxx Genesis", corpus_id="bible", limit=5)
    lxx_genesis_results = lxx_genesis.get("work_results", [])
    require(lxx_genesis_results and lxx_genesis_results[0].get("work_id") == "lxx.Gen", "lxx Genesis should prefer LXX")

    tobit = search_records("Tob", corpus_id="bible", limit=5)
    tobit_results = tobit.get("work_results", [])
    require(tobit_results and tobit_results[0].get("work_id") == "lxx.Tob", "Tob alias should find Tobit")

    wisdom = search_records("Wisdom", corpus_id="bible", limit=5)
    wisdom_results = wisdom.get("work_results", [])
    require(wisdom_results and wisdom_results[0].get("work_id") == "lxx.Wis", "Wisdom alias should find Wisdom")

    sirach = search_records("Ecclesiasticus", corpus_id="bible", limit=5)
    sirach_results = sirach.get("work_results", [])
    require(sirach_results and sirach_results[0].get("work_id") == "lxx.Sir", "Ecclesiasticus alias should find Sirach")

    epjer = search_records("EpJer", corpus_id="bible", limit=5)
    epjer_results = epjer.get("work_results", [])
    require(epjer_results and epjer_results[0].get("work_id") == "lxx.LetJer", "EpJer alias should find Letter of Jeremiah")

    psalm_151 = search_records("Psalm 151", corpus_id="bible", limit=5)
    psalm_151_results = psalm_151.get("work_results", [])
    require(psalm_151_results and psalm_151_results[0].get("work_id") == "lxx.PsLXX", "Psalm 151 alias should find LXX Psalms")

    additions_daniel = search_records("Additions to Daniel", corpus_id="bible", limit=10)
    additions_daniel_results = additions_daniel.get("work_results", [])
    require(
        any(
            item.get("work_id") in {"lxx.DanOG", "lxx.DanTh", "lxx.SusOG", "lxx.SusTh", "lxx.BelOG", "lxx.BelTh"}
            for item in additions_daniel_results
        ),
        "Additions to Daniel alias should find LXX Daniel/Susanna/Bel materials",
    )

    ascii_title_cases = [
        ("Morgenrothe", "nietzsche", "M"),
        ("Frohliche Wissenschaft", "nietzsche", "FW"),
        ("Gotzen-Dammerung", "nietzsche", "GD"),
        ("Jenseits von Gut und Bose", "nietzsche", "JGB"),
        ("Frygt og Baeven", "kierkegaard", "fb"),
    ]
    for query, corpus_id, expected_work_id in ascii_title_cases:
        payload = search_records(query, corpus_id=corpus_id, limit=5)
        results = payload.get("work_results", [])
        require(results, f"{query} ASCII title alias returned no work results")
        require(
            results[0].get("work_id") == expected_work_id,
            f"{query} expected {expected_work_id}, got {results[0].get('work_id')}",
        )


def reference_search_work_records(
    query: str,
    corpus_id: str = "",
    work_id: str = "",
    variant_id: str = "",
    limit: int = 20,
) -> dict:
    preferred_source, work_query = search_service.source_prefix_query(query)
    terms = [term for term in search_service.normalize_search_text(work_query).split(" ") if term]
    if not terms:
        return {"count": 0, "results": []}
    metadata = search_service.load_work_metadata()
    corpora = [corpus_id] if corpus_id else sorted(metadata)
    ranked: list[tuple[int, str, str, dict]] = []
    for current_corpus_id in corpora:
        for current_work_id, work in metadata.get(current_corpus_id, {}).items():
            if work_id and current_work_id != work_id:
                continue
            if not search_service.work_matches_variant(work, variant_id):
                continue
            if current_corpus_id == "bible" and preferred_source:
                source_id = str(work.get("source_id", ""))
                if not source_id.startswith(preferred_source):
                    continue
            aliases = search_service.work_alias_values(current_corpus_id, work)
            score = search_service.score_work_match(work_query, terms, aliases, work)
            if score <= 0:
                continue
            if current_corpus_id == "bible":
                score += search_service.bible_work_source_score(work, preferred_source)
            title = str(work.get("display_title") or work.get("title") or current_work_id)
            category = str(work.get("category_title") or work.get("category_id") or "")
            result = {
                "kind": "work",
                "corpus_id": current_corpus_id,
                "work_id": current_work_id,
                "variant_id": variant_id,
                "title": title,
                "label": category,
                "url": work.get("work_url") or f"/work/{current_corpus_id}/{current_work_id}",
                "snippet": " / ".join(alias for alias in aliases[:6] if alias),
                "category_id": work.get("category_id", ""),
                "category_title": category,
                "variant_ids": work.get("variant_ids", []),
                "score": score,
            }
            ranked.append((score, current_corpus_id, current_work_id, result))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return {"count": len(ranked), "results": [item[3] for item in ranked[:limit]]}


def check_work_search_index_equivalence() -> None:
    cases = [
        ("ressentiment", "", "", "", 10),
        ("Gen 1:1", "", "", "", 10),
        ("Morgenrothe", "nietzsche", "", "", 10),
        ("will to power", "nietzsche", "", "", 10),
        ("lxx Genesis", "bible", "", "", 5),
        ("Genesis", "bible", "", "lxx_swete", 5),
    ]
    for query, corpus_id, work_id, variant_id, limit in cases:
        expected = reference_search_work_records(query, corpus_id, work_id, variant_id, limit)
        actual = search_service.search_work_records(query, corpus_id, work_id, variant_id, limit)
        require(actual == expected, f"{query}: indexed work results differ from per-request reference")


def write_test_metadata(paths: dict[str, Path], title: str) -> None:
    for corpus_id, path in paths.items():
        works = {}
        if corpus_id == "nietzsche":
            works = {
                "TEST": {
                    "corpus_id": corpus_id,
                    "work_id": "TEST",
                    "title": title,
                    "display_title": title,
                    "category_id": "test",
                    "category_title": "Test",
                    "variant_ids": ["test.variant"],
                    "work_url": "/work/nietzsche/TEST",
                }
            }
        path.write_text(json.dumps({"works": works}, ensure_ascii=False), encoding="utf-8")


def check_work_search_index_refresh_and_concurrency() -> None:
    with tempfile.TemporaryDirectory(prefix="philo_search_metadata_") as temporary_directory:
        temporary_path = Path(temporary_directory)
        metadata_paths = {
            corpus_id: temporary_path / f"{corpus_id}_metadata.json"
            for corpus_id in search_service.METADATA_FILES
        }
        write_test_metadata(metadata_paths, "Alpha Work")
        with (
            patch.dict(search_service.METADATA_FILES, metadata_paths, clear=True),
            patch.object(search_service, "_WORK_SEARCH_STATE", None),
        ):
            first_index = search_service.load_work_search_index()
            first_signature = first_index.signature
            first_result = search_service.search_work_records("Alpha", "nietzsche", "", "", 5)
            require(first_result["results"][0]["work_id"] == "TEST", "initial metadata index lookup failed")
            alpha_entry = first_index.entries_by_corpus["nietzsche"][0]
            require(alpha_entry.normalized_title == "alpha work", "normalized work title was not precomputed")
            require("alpha work" in alpha_entry.normalized_aliases, "normalized aliases were not precomputed")
            require(isinstance(alpha_entry.aliases, tuple), "work aliases should be stored as an immutable tuple")
            require(isinstance(alpha_entry.compact_aliases, frozenset), "compact aliases should be immutable")
            try:
                first_index.entries_by_corpus["new"] = ()
            except TypeError:
                pass
            else:
                raise AssertionError("corpus work index should be read-only")

            write_test_metadata(metadata_paths, "Omega Expanded Work")
            refreshed_index = search_service.load_work_search_index()
            require(refreshed_index is not first_index, "metadata signature change did not replace the work index")
            require(refreshed_index.signature != first_signature, "metadata signature did not change after rewrite")
            refreshed_result = search_service.search_work_records("Omega Expanded", "nietzsche", "", "", 5)
            require(refreshed_result["results"][0]["work_id"] == "TEST", "refreshed metadata lookup failed")
            require(
                not search_service.search_work_records("Alpha", "nietzsche", "", "", 5)["results"],
                "stale alias remained after metadata index refresh",
            )

            search_service._WORK_SEARCH_STATE = None
            build_count = 0
            build_count_lock = threading.Lock()
            start_barrier = threading.Barrier(8)
            original_builder = search_service.build_work_search_index

            def counted_builder(metadata: dict[str, dict], signature: search_service.WorkMetadataSignature):
                nonlocal build_count
                with build_count_lock:
                    build_count += 1
                time.sleep(0.02)
                return original_builder(metadata, signature)

            def concurrent_load():
                start_barrier.wait()
                return search_service.load_work_search_index()

            with patch.object(search_service, "build_work_search_index", side_effect=counted_builder):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    indexes = list(executor.map(lambda _index: concurrent_load(), range(8)))
            require(build_count == 1, f"concurrent metadata requests built the index {build_count} times")
            require(len({id(index) for index in indexes}) == 1, "concurrent requests observed different index instances")


def check_segment_ranking() -> None:
    ressentiment = search_records("ressentiment", corpus_id="nietzsche", limit=5)
    ressentiment_results = require_results(ressentiment, "Nietzsche ressentiment segment ranking")
    require(ressentiment.get("engine") == "sqlite-fts5", "segment ranking should use sqlite FTS5 when available")
    require("ressentiment" in str(ressentiment_results[0].get("snippet", "")).lower(), "top ressentiment hit should show the term")
    require(
        any(item.get("work_id") == "GM" and item.get("segment_id") == "p-0023" for item in ressentiment_results[:3]),
        "ressentiment should keep GM paragraph 23 near the top",
    )

    gut_bose = search_records("Gut B\u00f6se", corpus_id="nietzsche", limit=5)
    gut_bose_results = require_results(gut_bose, "Nietzsche Gut Boese segment ranking")
    require(
        gut_bose_results[0].get("work_id") in {"JGB", "GM", "EH"},
        "Gut Boese should rank a directly related Nietzsche work first",
    )
    require(
        "gut" in str(gut_bose_results[0].get("snippet", "")).lower()
        or "gut" in str(gut_bose_results[0].get("label", "")).lower(),
        "Gut Boese result should expose the matching phrase",
    )

    language_game = search_records("language game", corpus_id="wittgenstein", limit=5)
    language_game_results = require_results(language_game, "Wittgenstein language game segment ranking")
    first_snippet = str(language_game_results[0].get("snippet", "")).lower()
    require("language game" in first_snippet, "language game should rank an exact phrase hit first")

    gud = search_records("Gud", corpus_id="kierkegaard", limit=5)
    gud_results = require_results(gud, "Kierkegaard Gud segment ranking")
    require(gud_results[0].get("corpus_id") == "kierkegaard", "Gud ranking should stay inside Kierkegaard filter")


def check_nietzsche_concept_search_links() -> None:
    payload = json.loads((DATA / "nietzsche_concepts.json").read_text(encoding="utf-8"))
    concepts = payload.get("concepts", [])
    require(concepts, "Nietzsche concepts should be available for concept tab search links")
    for concept in concepts:
        query = str(concept.get("search_query") or "").strip()
        context = f"Nietzsche concept search {concept.get('id')}"
        require(query, f"{context} missing search_query")
        results = search_records(query, corpus_id="nietzsche", limit=3)
        hits = results.get("results", []) + results.get("work_results", [])
        require(hits, f"{context} returned no scoped Nietzsche results for {query!r}")
        require(
            all(item.get("corpus_id") == "nietzsche" for item in hits),
            f"{context} leaked outside Nietzsche search scope",
        )


def cleanup_notes() -> None:
    path = note_storage_path(NOTE_CORPUS_ID)
    if path.exists():
        path.unlink()


def check_note_search() -> None:
    cleanup_notes()
    try:
        append_note(
            NOTE_CORPUS_ID,
            {
                "id": "search-note-1",
                "created_at": "2026-06-05T12:00:00",
                "corpus_id": NOTE_CORPUS_ID,
                "work_id": "M",
                "variant_id": "",
                "target_id": "sec-1",
                "target_type": "section",
                "target_label": "Section 1",
                "quote": "portable unique note phrase",
                "note": "integrated archive search note",
                "tags": ["search-contract"],
                "review_state": "reviewed",
                "reviewed_at": "2026-06-05T12:01:00",
                "url": "/work/nietzsche/M#sec-1",
            },
        )
        payload = search_records("portable unique note", corpus_id=NOTE_CORPUS_ID, limit=5)
        require(payload.get("note_count") == 1, "note search count failed")
        note_results = payload.get("note_results", [])
        require(note_results and note_results[0].get("id") == "search-note-1", "note search result failed")
        require(note_results[0].get("manage_url", "").startswith("/notes?"), "note search manage url failed")
        append_note(
            NOTE_CORPUS_ID,
            {
                "id": "search-note-fallback",
                "created_at": "2026-06-05T12:10:00",
                "corpus_id": NOTE_CORPUS_ID,
                "work_id": "",
                "variant_id": "",
                "target_id": "",
                "target_type": "",
                "target_label": "",
                "quote": "",
                "note": "fallback label unique note phrase",
                "tags": [],
                "review_state": "reviewed",
                "reviewed_at": "2026-06-05T12:11:00",
                "url": "",
            },
        )
        fallback_payload = search_records("fallback label unique", corpus_id=NOTE_CORPUS_ID, limit=5)
        fallback_results = fallback_payload.get("note_results", [])
        require(fallback_results and fallback_results[0].get("id") == "search-note-fallback", "note fallback search result failed")
        require(fallback_results[0].get("label") == "노트", "empty note target fallback should stay in reader language")
        require(fallback_results[0].get("title") == "노트", "empty note title fallback should stay in reader language")
    finally:
        cleanup_notes()


def main() -> None:
    check_bible_direct_lookup()
    check_filters()
    check_query_payload_helper()
    check_work_alias_search()
    check_work_search_index_equivalence()
    check_work_search_index_refresh_and_concurrency()
    check_segment_ranking()
    check_nietzsche_concept_search_links()
    check_note_search()
    print("search contracts ok")


if __name__ == "__main__":
    main()
