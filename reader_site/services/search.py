from __future__ import annotations

import heapq
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from services.notes import read_all_notes

SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"
SEARCH_INDEX = DATA / "search_index.jsonl"
SEARCH_DB = DATA / "search_index.sqlite"
BIBLE_METADATA = DATA / "bible_metadata.json"
METADATA_FILES = {
    "nietzsche": DATA / "nietzsche_metadata.json",
    "bible": DATA / "bible_metadata.json",
    "kierkegaard": DATA / "kierkegaard_metadata.json",
    "wittgenstein": DATA / "wittgenstein_metadata.json",
}
CORPUS_TITLES = {
    "nietzsche": "니체",
    "bible": "성경",
    "kierkegaard": "키르케고르",
    "wittgenstein": "비트겐슈타인",
}
BIBLE_ALIAS_CACHE: dict[str, list[dict]] | None = None
WORK_METADATA_CACHE: dict[str, dict] | None = None
BIBLE_KO_ABBREVIATIONS = {
    "창": "Gen",
    "출": "Exod",
    "레": "Lev",
    "민": "Num",
    "신": "Deut",
    "수": "Josh",
    "삿": "Judg",
    "룻": "Ruth",
    "삼상": "1Sam",
    "삼하": "2Sam",
    "왕상": "1Kgs",
    "왕하": "2Kgs",
    "대상": "1Chr",
    "대하": "2Chr",
    "스": "Ezra",
    "느": "Neh",
    "에": "Esth",
    "욥": "Job",
    "시": "Ps",
    "시편": "Ps",
    "잠": "Prov",
    "전": "Eccl",
    "아": "Song",
    "사": "Isa",
    "렘": "Jer",
    "애": "Lam",
    "겔": "Ezek",
    "단": "Dan",
    "호": "Hos",
    "욜": "Joel",
    "암": "Amos",
    "옵": "Obad",
    "욘": "Jonah",
    "미": "Mic",
    "나": "Nah",
    "합": "Hab",
    "습": "Zeph",
    "학": "Hag",
    "슥": "Zech",
    "말": "Mal",
    "마": "Matt",
    "막": "Mark",
    "눅": "Luke",
    "요": "John",
    "행": "Acts",
    "롬": "Rom",
    "고전": "1Cor",
    "고후": "2Cor",
    "갈": "Gal",
    "엡": "Eph",
    "빌": "Phil",
    "골": "Col",
    "살전": "1Thess",
    "살후": "2Thess",
    "딤전": "1Tim",
    "딤후": "2Tim",
    "딛": "Titus",
    "몬": "Phlm",
    "히": "Heb",
    "약": "Jas",
    "벧전": "1Pet",
    "벧후": "2Pet",
    "요일": "1John",
    "요이": "2John",
    "요삼": "3John",
    "요1": "1John",
    "요2": "2John",
    "요3": "3John",
    "유": "Jude",
    "계": "Rev",
}

BIBLE_ALTERNATE_BOOK_ALIASES = {
    "Ps": ["Psalm", "Psalter"],
    "1Esd": ["1 Esd", "First Esdras", "1 Esdras", "3 Ezra", "3 Esdras"],
    "EsdB": ["Esdras B", "Ezra-Nehemiah", "Ezra Nehemiah"],
    "Tob": ["Tob", "Tb", "Tobias", "Book of Tobit"],
    "Jdt": ["Jdt", "Judith", "Book of Judith"],
    "Wis": ["Wis", "Wisdom", "Wisdom of Solomon", "Sapientia"],
    "Sir": ["Sir", "Sirach", "Ecclesiasticus", "Ben Sira", "Wisdom of Sirach"],
    "Bar": ["Bar", "Baruch"],
    "LetJer": ["LetJer", "EpJer", "Epistle of Jeremiah", "Letter of Jeremiah"],
    "1Macc": ["1 Macc", "I Maccabees", "First Maccabees"],
    "2Macc": ["2 Macc", "II Maccabees", "Second Maccabees"],
    "3Macc": ["3 Macc", "III Maccabees", "Third Maccabees"],
    "4Macc": ["4 Macc", "IV Maccabees", "Fourth Maccabees"],
    "PsLXX": ["Psalm", "Psalter", "LXX Psalms", "Psalm 151", "Psalms 151"],
    "PsSol": ["PssSol", "PsSol", "Psalms of Solomon"],
    "Odes": ["Ode", "Odes"],
    "EsthLXX": ["Greek Esther", "LXX Esther", "Additions to Esther", "Esther additions"],
    "DanOG": ["Daniel OG", "Old Greek Daniel", "Greek Daniel", "Additions to Daniel", "Daniel additions"],
    "DanTh": ["Daniel Th", "Daniel Theodotion", "Theodotion Daniel", "Additions to Daniel", "Daniel additions"],
    "SusOG": ["Sus", "Susanna", "Susanna OG", "Old Greek Susanna", "Additions to Daniel"],
    "SusTh": ["Sus", "Susanna", "Susanna Th", "Theodotion Susanna", "Additions to Daniel"],
    "BelOG": ["Bel", "Bel and Dragon", "Bel and the Dragon", "Bel OG", "Old Greek Bel", "Additions to Daniel"],
    "BelTh": ["Bel", "Bel and Dragon", "Bel and the Dragon", "Bel Th", "Theodotion Bel", "Additions to Daniel"],
}


def normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def compact_alias_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", normalize_search_text(value), flags=re.UNICODE)


def bible_source_priority(work: dict, preferred_source: str = "") -> tuple[int, int, str]:
    source_id = str(work.get("source_id", ""))
    if preferred_source and source_id.startswith(preferred_source):
        source_rank = 0
    elif source_id == "sblgnt":
        source_rank = 10
    elif source_id == "oshb_morphhb":
        source_rank = 20
    elif source_id == "lxx_swete":
        source_rank = 30
    else:
        source_rank = 90
    return (source_rank, int(work.get("order") or 9999), str(work.get("work_id", "")))


def load_bible_alias_index() -> dict[str, list[dict]]:
    global BIBLE_ALIAS_CACHE
    if BIBLE_ALIAS_CACHE is not None:
        return BIBLE_ALIAS_CACHE
    if not BIBLE_METADATA.exists():
        BIBLE_ALIAS_CACHE = {}
        return BIBLE_ALIAS_CACHE

    payload = json.loads(BIBLE_METADATA.read_text(encoding="utf-8"))
    aliases: dict[str, list[dict]] = {}
    works_by_book_id: dict[str, list[dict]] = {}
    for work in payload.get("works", {}).values():
        if work.get("book_id"):
            works_by_book_id.setdefault(str(work["book_id"]), []).append(work)
        values = {
            work.get("book_id", ""),
            work.get("title", ""),
            work.get("book_name_en", ""),
            work.get("book_name_ko", ""),
            work.get("display_title", ""),
            work.get("work_id", ""),
        }
        values.update(BIBLE_ALTERNATE_BOOK_ALIASES.get(str(work.get("book_id", "")), []))
        display_title = str(work.get("display_title", ""))
        if "/" in display_title:
            values.update(part.strip() for part in display_title.split("/"))
        for value in values:
            key = compact_alias_key(str(value))
            if not key:
                continue
            aliases.setdefault(key, []).append(work)

    for abbreviation, book_id in BIBLE_KO_ABBREVIATIONS.items():
        key = compact_alias_key(abbreviation)
        if key and book_id in works_by_book_id:
            aliases.setdefault(key, []).extend(works_by_book_id[book_id])

    for key, works in aliases.items():
        deduped = {work.get("work_id"): work for work in works if work.get("work_id")}
        aliases[key] = sorted(deduped.values(), key=bible_source_priority)
    BIBLE_ALIAS_CACHE = aliases
    return BIBLE_ALIAS_CACHE


def parse_bible_reference(query: str) -> dict | None:
    text = normalize_search_text(query)
    if not text:
        return None
    preferred_source = ""
    source_match = re.match(r"^(oshb|sblgnt|lxx|lxx_swete)\s+(.+)$", text)
    if source_match:
        preferred_source = "lxx_swete" if source_match.group(1) == "lxx" else source_match.group(1)
        text = source_match.group(2).strip()
    match = re.match(r"^(.+?)[\s.]+([0-9]+)[\s:.\-]+([0-9]+[a-z]?)$", text)
    if not match:
        return None
    book_key = compact_alias_key(match.group(1))
    chapter = str(int(match.group(2)))
    verse_raw = match.group(3)
    verse = str(int(verse_raw)) if verse_raw.isdigit() else verse_raw.lstrip("0")
    if not book_key or not chapter or not verse:
        return None
    return {
        "book_key": book_key,
        "chapter": chapter,
        "verse": verse,
        "preferred_source": preferred_source,
    }


def search_snippet(text: str, terms: list[str], radius: int = 90) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - radius)
    end = min(len(text), center + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def search_phrase(terms: list[str]) -> str:
    return " ".join(term for term in terms if term)


def score_search_result(text: str, title: str, label: str, terms: list[str]) -> int:
    text_haystack = normalize_search_text(text)
    title_haystack = normalize_search_text(f"{title} {label}")
    full_haystack = normalize_search_text(f"{title_haystack} {text_haystack}")
    phrase = search_phrase(terms)

    score = sum(text_haystack.count(term) for term in terms)
    score += sum(6 * title_haystack.count(term) for term in terms)
    score += sum(3 for term in terms if term in title_haystack)
    if phrase and phrase in text_haystack:
        score += 50
    if phrase and phrase in title_haystack:
        score += 80
    if phrase and normalize_search_text(title) == phrase:
        score += 120
    if phrase and normalize_search_text(label) == phrase:
        score += 100
    if len(terms) > 1 and all(term in text_haystack for term in terms):
        score += 12
    if len(terms) > 1 and all(term in title_haystack for term in terms):
        score += 30
    if phrase and phrase in full_haystack:
        score += 10
    return score


def segment_type_boost(segment_type: str, title: str, label: str, terms: list[str]) -> int:
    phrase = search_phrase(terms)
    title_haystack = normalize_search_text(f"{title} {label}")
    if segment_type in {"paragraph", "verse", "block"}:
        return 5
    if segment_type in {"section", "heading"} and phrase and phrase in title_haystack:
        return 10
    return 0


def load_work_metadata() -> dict[str, dict]:
    global WORK_METADATA_CACHE
    if WORK_METADATA_CACHE is not None:
        return WORK_METADATA_CACHE
    metadata: dict[str, dict] = {}
    for corpus_id, path in METADATA_FILES.items():
        if not path.exists():
            metadata[corpus_id] = {}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        works = payload.get("works", {})
        metadata[corpus_id] = works if isinstance(works, dict) else {}
    WORK_METADATA_CACHE = metadata
    return WORK_METADATA_CACHE


def work_display_title(work: dict, fallback: str = "") -> str:
    return str(
        work.get("display_title")
        or work.get("title")
        or work.get("korean_title")
        or work.get("book_name_ko")
        or work.get("book_name_en")
        or fallback
        or ""
    ).strip()


def note_context_title(corpus_id: str, work_id: str) -> str:
    corpus_id = str(corpus_id or "").strip()
    work_id = str(work_id or "").strip()
    if work_id:
        work = load_work_metadata().get(corpus_id, {}).get(work_id)
        if isinstance(work, dict):
            title = work_display_title(work)
            if title:
                return title
    return CORPUS_TITLES.get(corpus_id, "노트")


def work_alias_values(corpus_id: str, work: dict) -> list[str]:
    values = [
        corpus_id,
        work.get("work_id", ""),
        work.get("title", ""),
        work.get("display_title", ""),
        work.get("korean_title", ""),
        work.get("category_title", ""),
        work.get("book_id", ""),
        work.get("book_name_en", ""),
        work.get("book_name_ko", ""),
        work.get("siglum", ""),
    ]
    display_title = str(work.get("display_title", ""))
    if "/" in display_title:
        values.extend(part.strip() for part in display_title.split("/"))
    if corpus_id == "bible":
        values.extend(BIBLE_ALTERNATE_BOOK_ALIASES.get(str(work.get("book_id", "")), []))
    values.extend(str(item) for item in work.get("variant_ids", []) if item)
    return [str(value).strip() for value in values if str(value).strip()]


def work_matches_variant(work: dict, variant_id: str) -> bool:
    if not variant_id:
        return True
    if work.get("variant_id") == variant_id:
        return True
    return variant_id in {str(item) for item in work.get("variant_ids", [])}


def score_work_match(query: str, terms: list[str], aliases: list[str], work: dict) -> int:
    compact_query = compact_alias_key(query)
    compact_aliases = {compact_alias_key(alias) for alias in aliases if compact_alias_key(alias)}
    haystack = normalize_search_text(" ".join(aliases))
    compact_haystack = compact_alias_key(haystack)
    exact_match = bool(compact_query and compact_query in compact_aliases)
    prefix_match = bool(
        compact_query and len(compact_query) >= 2 and any(alias.startswith(compact_query) for alias in compact_aliases)
    )
    term_matches = [
        term in haystack or (compact_alias_key(term) and compact_alias_key(term) in compact_haystack)
        for term in terms
    ]
    if not exact_match and not prefix_match and not all(term_matches):
        return 0
    if len(compact_query) == 1 and not exact_match:
        return 0
    score = 0
    if exact_match:
        score += 1000
    elif prefix_match:
        score += 250
    if compact_query and compact_query == compact_alias_key(str(work.get("work_id", ""))):
        score += 500
    score += sum(30 for term in terms if term in haystack)
    score += sum(15 for term in terms if compact_alias_key(term) and compact_alias_key(term) in compact_haystack)
    return score


def source_prefix_query(query: str) -> tuple[str, str]:
    text = normalize_search_text(query)
    match = re.match(r"^(oshb|sblgnt|lxx|lxx_swete)\s+(.+)$", text)
    if not match:
        return "", query
    source_id = "lxx_swete" if match.group(1) == "lxx" else match.group(1)
    return source_id, match.group(2).strip()


def bible_work_source_score(work: dict, preferred_source: str = "") -> int:
    source_id = str(work.get("source_id", ""))
    if preferred_source and source_id.startswith(preferred_source):
        return 100
    if source_id == "sblgnt":
        return 80
    if source_id == "oshb_morphhb":
        return 70
    if source_id == "lxx_swete":
        return 40
    return 0


def search_work_records(query: str, corpus_id: str, work_id: str, variant_id: str, limit: int) -> dict:
    preferred_source, work_query = source_prefix_query(query)
    terms = [term for term in normalize_search_text(work_query).split(" ") if term]
    if not terms:
        return {"count": 0, "results": []}
    metadata = load_work_metadata()
    corpora = [corpus_id] if corpus_id else sorted(metadata)
    ranked: list[tuple[int, str, str, dict]] = []
    for current_corpus_id in corpora:
        for current_work_id, work in metadata.get(current_corpus_id, {}).items():
            if work_id and current_work_id != work_id:
                continue
            if not work_matches_variant(work, variant_id):
                continue
            if current_corpus_id == "bible" and preferred_source:
                source_id = str(work.get("source_id", ""))
                if not source_id.startswith(preferred_source):
                    continue
            aliases = work_alias_values(current_corpus_id, work)
            score = score_work_match(work_query, terms, aliases, work)
            if score <= 0:
                continue
            if current_corpus_id == "bible":
                score += bible_work_source_score(work, preferred_source)
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


def note_haystack(note: dict) -> str:
    return normalize_search_text(
        " ".join(
            [
                str(note.get("corpus_id", "")),
                str(note.get("work_id", "")),
                str(note.get("target_label", "")),
                str(note.get("target_id", "")),
                str(note.get("quote", "")),
                str(note.get("note", "")),
                " ".join(str(tag) for tag in note.get("tags", [])),
            ]
        )
    )


def note_manage_url(note: dict) -> str:
    params = []
    for key in ("corpus_id", "work_id"):
        value = str(note.get(key, ""))
        if value:
            params.append(f"{key}={quote(value, safe='')}")
    target_id = str(note.get("target_id", ""))
    if target_id:
        params.append(f"target_id={quote(target_id, safe='')}")
    return "/notes" + ("?" + "&".join(params) if params else "")


def search_note_records(query: str, corpus_id: str, work_id: str, limit: int) -> dict:
    terms = [term for term in normalize_search_text(query).split(" ") if term]
    if not terms:
        return {"count": 0, "results": []}
    corpus_ids = [corpus_id] if corpus_id else None
    notes = read_all_notes(corpus_ids=corpus_ids, work_id=work_id)
    ranked: list[tuple[int, int, dict]] = []
    for index, note in enumerate(notes):
        haystack = note_haystack(note)
        if not all(term in haystack for term in terms):
            continue
        title = note_context_title(str(note.get("corpus_id", "")), str(note.get("work_id", "")))
        label = str(note.get("target_label") or note.get("target_id") or "노트")
        text = " ".join(
            str(item)
            for item in [note.get("quote", ""), note.get("note", ""), " ".join(str(tag) for tag in note.get("tags", []))]
            if item
        )
        score = score_search_result(text, title, label, terms)
        result = {
            "kind": "note",
            "id": note.get("id", ""),
            "corpus_id": note.get("corpus_id", ""),
            "work_id": note.get("work_id", ""),
            "variant_id": note.get("variant_id", ""),
            "target_id": note.get("target_id", ""),
            "target_label": label,
            "title": title,
            "label": label,
            "url": note.get("url", ""),
            "manage_url": note_manage_url(note),
            "snippet": search_snippet(text, terms),
            "review_state": note.get("review_state", "raw"),
            "tags": note.get("tags", []),
            "score": score,
        }
        ranked.append((score, -index, result))
    ranked.sort(reverse=True)
    return {"count": len(ranked), "results": [item[2] for item in ranked[:limit]]}


def attach_related_results(payload: dict, query: str, corpus_id: str, work_id: str, variant_id: str, limit: int) -> dict:
    works = search_work_records(query, corpus_id, work_id, variant_id, min(limit, 20))
    notes = search_note_records(query, corpus_id, work_id, min(limit, 20))
    payload["work_count"] = works["count"]
    payload["work_results"] = works["results"]
    payload["note_count"] = notes["count"]
    payload["note_results"] = notes["results"]
    return payload


def sqlite_search_has_fts(connection: sqlite3.Connection) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'search_segments_fts'"
        ).fetchone()
    )


def fts5_query(terms: list[str]) -> str:
    return " AND ".join(f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms)


def search_result_from_row(row: sqlite3.Row, terms: list[str], score: int) -> dict:
    return {
        "corpus_id": row["corpus_id"],
        "work_id": row["work_id"],
        "variant_id": row["variant_id"],
        "segment_id": row["segment_id"],
        "segment_type": row["segment_type"],
        "title": row["title"],
        "label": row["label"],
        "url": row["url"],
        "snippet": search_snippet(row["snippet"], terms),
        "score": score,
    }


def score_sqlite_segment_row(row: sqlite3.Row, terms: list[str], result_index: int = 0) -> int:
    score = score_search_result(row["search_text"], row["title"], row["label"], terms)
    score += segment_type_boost(row["segment_type"], row["title"], row["label"], terms)
    score += max(0, 20 - result_index)
    return score


def score_jsonl_segment_record(record: dict, text: str, title: str, label: str, terms: list[str]) -> int:
    score = score_search_result(text, title, label, terms)
    score += segment_type_boost(str(record.get("segment_type", "")), title, label, terms)
    return score


def direct_bible_result_from_row(row: sqlite3.Row, score: int) -> dict:
    return {
        "corpus_id": row["corpus_id"],
        "work_id": row["work_id"],
        "variant_id": row["variant_id"],
        "segment_id": row["segment_id"],
        "segment_type": row["segment_type"],
        "title": row["title"],
        "label": row["label"],
        "url": row["url"],
        "snippet": row["snippet"],
        "score": score,
    }


def search_records_sqlite_direct_bible(
    connection: sqlite3.Connection,
    query: str,
    corpus_id: str,
    work_id: str,
    variant_id: str,
    limit: int,
) -> dict | None:
    if corpus_id and corpus_id != "bible":
        return None
    reference = parse_bible_reference(query)
    if not reference:
        return None

    alias_index = load_bible_alias_index()
    candidates = alias_index.get(reference["book_key"], [])
    if reference["preferred_source"]:
        candidates = [
            work
            for work in candidates
            if str(work.get("source_id", "")).startswith(reference["preferred_source"])
        ]
    if work_id:
        candidates = [work for work in candidates if work.get("work_id") == work_id]
    if variant_id:
        candidates = [work for work in candidates if work.get("variant_id") == variant_id]
    if not candidates:
        return None

    rows: list[tuple[int, sqlite3.Row]] = []
    for candidate_index, work in enumerate(sorted(candidates, key=lambda item: bible_source_priority(item, reference["preferred_source"]))):
        book_id = work.get("book_id", "")
        if not book_id:
            continue
        segment_ids = [f"{book_id}.{reference['chapter']}.{reference['verse']}"]
        if reference["chapter"] == "1":
            segment_ids.append(f"{book_id}.0.{reference['verse']}")
        for segment_id in segment_ids:
            found = connection.execute(
                """
                SELECT corpus_id, work_id, variant_id, segment_id, segment_type, label, title, url, snippet, search_text
                FROM search_segments
                WHERE corpus_id = 'bible' AND work_id = ? AND segment_id = ?
                """,
                (work.get("work_id"), segment_id),
            ).fetchall()
            rows.extend((candidate_index, row) for row in found)

    if not rows:
        return None
    rows = sorted(rows, key=lambda item: item[0])[:limit]
    results = [direct_bible_result_from_row(row, 10000 - index) for index, (_, row) in enumerate(rows)]
    first = results[0]
    return {
        "query": query,
        "count": len(rows),
        "results": results,
        "engine": "sqlite-direct-bible",
        "direct": {
            "kind": "bible_reference",
            "book_id": first["segment_id"].split(".", 1)[0],
            "chapter": reference["chapter"],
            "verse": reference["verse"],
        },
    }


def search_records_sqlite_fts(
    connection: sqlite3.Connection,
    terms: list[str],
    corpus_id: str,
    work_id: str,
    variant_id: str,
    limit: int,
) -> dict:
    clauses = ["search_segments_fts MATCH ?"]
    params: list[str] = [fts5_query(terms)]
    if corpus_id:
        clauses.append("s.corpus_id = ?")
        params.append(corpus_id)
    if work_id:
        clauses.append("s.work_id = ?")
        params.append(work_id)
    if variant_id:
        clauses.append("s.variant_id = ?")
        params.append(variant_id)
    where = " AND ".join(clauses)
    scan_limit = max(limit * 5, 100)

    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM search_segments_fts
        JOIN search_segments AS s ON s.id = search_segments_fts.rowid
        WHERE {where}
        """,
        params,
    ).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT
          s.corpus_id, s.work_id, s.variant_id, s.segment_id, s.segment_type,
          s.label, s.title, s.url, s.snippet, s.search_text,
          bm25(search_segments_fts) AS rank
        FROM search_segments_fts
        JOIN search_segments AS s ON s.id = search_segments_fts.rowid
        WHERE {where}
        ORDER BY rank
        LIMIT ?
        """,
        [*params, scan_limit],
    ).fetchall()

    ranked = []
    for index, row in enumerate(rows):
        score = score_sqlite_segment_row(row, terms, index)
        ranked.append((score, -index, search_result_from_row(row, terms, score)))
    results = [item[2] for item in sorted(ranked, reverse=True)[:limit]]
    return {"query": " ".join(terms), "count": total, "results": results, "engine": "sqlite-fts5"}


def search_records_sqlite_like(
    connection: sqlite3.Connection,
    terms: list[str],
    corpus_id: str,
    work_id: str,
    variant_id: str,
    limit: int,
) -> dict:
    clauses = ["search_text LIKE ?"]
    params: list[str] = [f"%{terms[0]}%"]
    for term in terms[1:]:
        clauses.append("search_text LIKE ?")
        params.append(f"%{term}%")
    if corpus_id:
        clauses.append("corpus_id = ?")
        params.append(corpus_id)
    if work_id:
        clauses.append("work_id = ?")
        params.append(work_id)
    if variant_id:
        clauses.append("variant_id = ?")
        params.append(variant_id)
    where = " AND ".join(clauses)
    scan_limit = max(limit * 30, 500)

    total = connection.execute(f"SELECT COUNT(*) FROM search_segments WHERE {where}", params).fetchone()[0]
    rows = connection.execute(
        f"""
        SELECT corpus_id, work_id, variant_id, segment_id, segment_type, label, title, url, snippet, search_text
        FROM search_segments
        WHERE {where}
        LIMIT ?
        """,
        [*params, scan_limit],
    ).fetchall()

    ranked = []
    for index, row in enumerate(rows):
        score = score_sqlite_segment_row(row, terms, index)
        ranked.append((score, -index, search_result_from_row(row, terms, score)))
    results = [item[2] for item in sorted(ranked, reverse=True)[:limit]]
    return {"query": " ".join(terms), "count": total, "results": results, "engine": "sqlite-like"}


def search_records_sqlite(query: str, corpus_id: str, work_id: str, variant_id: str, limit: int) -> dict:
    terms = [term for term in normalize_search_text(query).split(" ") if term]
    if not terms:
        return {"query": normalize_search_text(query), "count": 0, "results": []}
    connection = sqlite3.connect(SEARCH_DB)
    connection.row_factory = sqlite3.Row
    try:
        direct_result = search_records_sqlite_direct_bible(connection, query, corpus_id, work_id, variant_id, limit)
        if direct_result is not None:
            return direct_result
        if sqlite_search_has_fts(connection):
            try:
                return search_records_sqlite_fts(connection, terms, corpus_id, work_id, variant_id, limit)
            except sqlite3.Error:
                return search_records_sqlite_like(connection, terms, corpus_id, work_id, variant_id, limit)
        return search_records_sqlite_like(connection, terms, corpus_id, work_id, variant_id, limit)
    finally:
        connection.close()


def search_records_jsonl(query: str, terms: list[str], corpus_id: str, work_id: str, variant_id: str, limit: int) -> dict:
    total_matches = 0
    heap: list[tuple[int, int, dict]] = []
    order = 0
    with SEARCH_INDEX.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if corpus_id and record.get("corpus_id") != corpus_id:
                continue
            if work_id and record.get("work_id") != work_id:
                continue
            if variant_id and record.get("variant_id") != variant_id:
                continue
            haystack = normalize_search_text(
                " ".join(
                    [
                        str(record.get("title", "")),
                        str(record.get("label", "")),
                        str(record.get("text", "")),
                    ]
                )
            )
            if not all(term in haystack for term in terms):
                continue
            text = str(record.get("text", ""))
            title = str(record.get("title", ""))
            label = str(record.get("label", ""))
            score = score_jsonl_segment_record(record, text, title, label, terms)
            total_matches += 1
            order += 1
            result = {
                "corpus_id": record.get("corpus_id", ""),
                "work_id": record.get("work_id", ""),
                "variant_id": record.get("variant_id", ""),
                "segment_id": record.get("segment_id", ""),
                "segment_type": record.get("segment_type", ""),
                "title": title,
                "label": label,
                "url": record.get("url", ""),
                "snippet": search_snippet(text, terms),
                "score": score,
            }
            item = (score, -order, result)
            if len(heap) < limit:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

    results = [item[2] for item in sorted(heap, reverse=True)]
    return {"query": query, "count": total_matches, "results": results, "engine": "jsonl"}


def first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    value = query.get(key, [default])
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or default)


def safe_search_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "", str(value).strip())


def search_payload_from_query(query: dict[str, list[str]]) -> dict:
    try:
        limit = int(first_query_value(query, "limit", "30"))
    except ValueError:
        limit = 30
    return search_records(
        first_query_value(query, "q"),
        safe_search_slug(first_query_value(query, "corpus_id")),
        first_query_value(query, "work_id"),
        first_query_value(query, "variant_id"),
        limit,
    )


def search_records(query: str, corpus_id: str = "", work_id: str = "", variant_id: str = "", limit: int = 30) -> dict:
    query = normalize_search_text(query)
    terms = [term for term in query.split(" ") if term]
    if not terms:
        return {"query": query, "count": 0, "results": [], "work_count": 0, "work_results": [], "note_count": 0, "note_results": []}
    limit = max(1, min(int(limit), 100))
    if SEARCH_DB.exists():
        return attach_related_results(search_records_sqlite(query, corpus_id, work_id, variant_id, limit), query, corpus_id, work_id, variant_id, limit)
    if not SEARCH_INDEX.exists():
        return {
            "query": query,
            "count": 0,
            "results": [],
            "work_count": 0,
            "work_results": [],
            "note_count": 0,
            "note_results": [],
            "error": "search index not found",
        }
    return attach_related_results(search_records_jsonl(query, terms, corpus_id, work_id, variant_id, limit), query, corpus_id, work_id, variant_id, limit)
