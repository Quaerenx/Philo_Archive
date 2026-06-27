from __future__ import annotations

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora.archive import build_archive  # noqa: E402
from server import Handler  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fetch_json(base_url: str, path: str) -> dict:
    with urlopen(base_url + path, timeout=15) as response:
        require(response.status == 200, f"{path} returned {response.status}")
        return json.loads(response.read().decode("utf-8"))


def fetch_text(base_url: str, path: str) -> str:
    with urlopen(base_url + path, timeout=15) as response:
        require(response.status == 200, f"{path} returned {response.status}")
        return response.read().decode("utf-8", errors="replace")


def fetch_status(base_url: str, path: str) -> int:
    try:
        with urlopen(base_url + path, timeout=15) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def first_work_route() -> str:
    archive = build_archive()
    for corpus in archive.get("corpora", []):
        for section in corpus.get("sections", []):
            for link in section.get("links", []):
                href = str(link.get("href", ""))
                if href.startswith("/work/"):
                    return href
    raise AssertionError("no /work route found in archive")


def first_source_routes() -> tuple[str, str]:
    archive = build_archive()
    for corpus in archive.get("corpora", []):
        for section in corpus.get("sections", []):
            for link in section.get("links", []):
                href = str(link.get("href", ""))
                source_href = str(link.get("source_href", ""))
                if href.startswith("/read?") and source_href.startswith("/source?"):
                    return href, source_href
    raise AssertionError("no read/source route pair found in archive")


def check_routes(base_url: str) -> None:
    static_cases = {
        "/": "Personal Archive",
        "/category/nietzsche": "Personal Archive",
        "/category/bible": "Personal Archive",
        "/category/kierkegaard": "Personal Archive",
        "/category/wittgenstein": "Personal Archive",
        "/search": "검색",
        "/notes": "노트",
        "/study": "학습 기록",
        "/translations": "번역 검토",
    }
    for path, expected in static_cases.items():
        body = fetch_text(base_url, path)
        require(expected in body, f"{path} did not contain {expected!r}")

    tokens = fetch_text(base_url, "/assets/design-tokens.css")
    require("--page-frame-width" in tokens, "design tokens asset did not load")
    require(fetch_status(base_url, "/assets/missing.css") == 404, "missing static asset should return 404")
    require(fetch_status(base_url, "/%2e%2e/server.py") == 403, "path traversal should return 403")

    work_path = first_work_route()
    work_body = fetch_text(base_url, work_path)
    require("reader-work" in work_body or "work-page" in work_body, f"{work_path} did not look like a work page")
    require("reading-desk" in work_body, f"{work_path} missing reading desk layout")
    require("copySourceBundle" in work_body, f"{work_path} missing source bundle action")
    require("translation-card" in work_body, f"{work_path} missing sentence translation panel")
    require("previousSentence" in work_body and "nextSentence" in work_body, f"{work_path} missing sentence navigation")
    require("markTranslationReviewed" in work_body, f"{work_path} missing translation review action")
    require("study-tabs" in work_body, f"{work_path} missing study tabs")
    require("reader-sentence" in work_body, f"{work_path} missing sentence spans")
    work_cases = [
        "/work/nietzsche/M",
        "/work/bible/oshb.Gen",
        "/work/kierkegaard/aas",
        "/work/wittgenstein/Ms-101",
    ]
    for path in work_cases:
        body = fetch_text(base_url, path)
        require("reader-work" in body or "work-page" in body, f"{path} did not look like a work page")

    read_path, source_path = first_source_routes()
    read_body = fetch_text(base_url, read_path)
    require("static-reader" in read_body or "reader-column" in read_body, f"{read_path} did not look like a reading page")
    source_body = fetch_text(base_url, source_path)
    require("static-reader" in source_body or "<pre" in source_body, f"{source_path} did not look like a source page")
    require(fetch_status(base_url, "/read") == 400, "missing read path should return 400")

    health = fetch_json(base_url, "/api/health")
    require(health.get("status") in {"ok", "warning"}, "health status invalid")
    study = fetch_json(base_url, "/api/study")
    require("groups" in study and "count" in study, "study api shape invalid")
    translation_export = fetch_text(base_url, "/api/sentence-translations/export?corpus_id=nietzsche&work_id=GM&format=markdown")
    require("Sentence Translations" in translation_export, "sentence translation export invalid")
    require("Reviewed Gemma" not in translation_export, "sentence translation export should hide runtime-oriented title")
    translation_summary = fetch_json(base_url, "/api/sentence-translations/summary?corpus_id=nietzsche&work_id=GM")
    require("count" in translation_summary and "review_state_counts" in translation_summary, "sentence translation summary invalid")
    translation_page = fetch_text(base_url, "/translations?corpus_id=nietzsche&work_id=GM")
    require("translationsSubmit" in translation_page and "translationsResults" in translation_page, "translations page invalid")
    session_export = fetch_text(base_url, "/api/study-session/export?corpus_id=nietzsche&work_id=GM&format=markdown")
    require("Study Bundle" in session_export, "study session export invalid")
    target = fetch_json(base_url, "/api/source-target?corpus_id=nietzsche&work_id=GM&target_id=p-0023")
    target_record = target.get("target") or {}
    require(target_record.get("record_type") == "source_target_bundle", "source target api record_type invalid")
    require(target_record.get("target_url", "").startswith("/work/nietzsche/GM"), "source target api URL invalid")
    require(len(target_record.get("source_text_sha256", "")) == 64, "source target api checksum invalid")
    require(fetch_status(base_url, "/api/source-target?corpus_id=nietzsche&work_id=GM") == 400, "missing source target fields should return 400")
    require(
        fetch_status(base_url, "/api/source-target?corpus_id=nietzsche&work_id=GM&target_id=missing") == 404,
        "missing source target should return 404",
    )


def main() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address
        check_routes(f"http://{host}:{port}")
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
    print("static routes ok")


if __name__ == "__main__":
    main()
