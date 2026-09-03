from __future__ import annotations

import gzip
import json
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora.archive import build_archive  # noqa: E402
from server import Handler, LoopbackThreadingHTTPServer  # noqa: E402
from services import sentence_translations as sentence_translation_service  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def nested_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for child in value.values():
            keys.update(nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(nested_keys(child))
    return keys


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


def request_bytes(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> tuple[bytes, object]:
    request = Request(base_url + path, headers=headers or {}, method=method)
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as exc:
        require(exc.code == expected_status, f"{method} {path} returned {exc.code}, expected {expected_status}")
        body = exc.read()
        response_headers = exc.headers
    else:
        with response:
            require(
                response.status == expected_status,
                f"{method} {path} returned {response.status}, expected {expected_status}",
            )
            body = response.read()
            response_headers = response.headers
    return body, response_headers


def check_static_cache_contracts(base_url: str) -> None:
    for path, expected_type in (
        ("/app.js?v=home18", "javascript"),
        ("/assets/reader-work.css?v=common148", "text/css"),
    ):
        identity_body, identity_headers = request_bytes(
            base_url,
            path,
            headers={"Accept-Encoding": "identity"},
        )
        require(identity_body, f"{path} identity response is empty")
        require(expected_type in identity_headers.get("Content-Type", ""), f"{path} Content-Type drift")
        require(
            identity_headers.get("Cache-Control") == "public, max-age=31536000, immutable",
            f"{path} versioned cache policy drift",
        )
        require(identity_headers.get("ETag"), f"{path} missing ETag")
        require(identity_headers.get("Last-Modified"), f"{path} missing Last-Modified")
        require(
            int(identity_headers.get("Content-Length", "-1")) == len(identity_body),
            f"{path} identity Content-Length mismatch",
        )

        gzip_body, gzip_headers = request_bytes(
            base_url,
            path,
            headers={"Accept-Encoding": "gzip"},
        )
        require(gzip_headers.get("Content-Encoding") == "gzip", f"{path} did not negotiate gzip")
        require(gzip_headers.get("Vary") == "Accept-Encoding", f"{path} missing Vary: Accept-Encoding")
        require(int(gzip_headers.get("Content-Length", "-1")) == len(gzip_body), f"{path} gzip length mismatch")
        require(len(gzip_body) < len(identity_body), f"{path} gzip response was not smaller")
        require(gzip.decompress(gzip_body) == identity_body, f"{path} gzip response changed content")
        gzip_etag = gzip_headers.get("ETag", "")
        require(gzip_etag and gzip_etag != identity_headers.get("ETag"), f"{path} ETag must identify encoding")

        conditional_body, conditional_headers = request_bytes(
            base_url,
            path,
            headers={"Accept-Encoding": "gzip", "If-None-Match": gzip_etag},
            expected_status=304,
        )
        require(not conditional_body, f"{path} 304 response included a body")
        require(conditional_headers.get("ETag") == gzip_etag, f"{path} 304 ETag mismatch")
        require(conditional_headers.get("Content-Length") is None, f"{path} 304 included Content-Length")

        modified_body, _ = request_bytes(
            base_url,
            path,
            headers={
                "Accept-Encoding": "identity",
                "If-Modified-Since": identity_headers.get("Last-Modified", ""),
            },
            expected_status=304,
        )
        require(not modified_body, f"{path} If-Modified-Since 304 included a body")

        head_body, head_headers = request_bytes(
            base_url,
            path,
            method="HEAD",
            headers={"Accept-Encoding": "gzip"},
        )
        require(not head_body, f"{path} HEAD returned a body")
        require(
            int(head_headers.get("Content-Length", "-1")) == len(gzip_body),
            f"{path} HEAD Content-Length does not match gzip GET",
        )
        require(head_headers.get("Content-Encoding") == "gzip", f"{path} HEAD lost Content-Encoding")

    _, unversioned_headers = request_bytes(
        base_url,
        "/assets/reader-work.css",
        headers={"Accept-Encoding": "identity"},
    )
    require(unversioned_headers.get("Cache-Control") == "no-cache", "unversioned asset received long cache")
    _, root_headers = request_bytes(base_url, "/", headers={"Accept-Encoding": "identity"})
    require(root_headers.get("Cache-Control") == "no-cache", "HTML should be revalidated")
    _, api_headers = request_bytes(base_url, "/api/health")
    require(api_headers.get("Cache-Control") == "no-store", "API response received static cache policy")


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


def check_translation_delete_route(base_url: str) -> None:
    with TemporaryDirectory(prefix="philo_translation_delete_route_") as temp_dir:
        original_ai_dir = sentence_translation_service.AI_DIR
        sentence_translation_service.AI_DIR = Path(temp_dir)
        try:
            path = sentence_translation_service.ai_record_path("contract")
            sentence_translation_service.write_records(
                path,
                [
                    {
                        "id": "delete-route-record",
                        "record_type": "ai_sentence_translation",
                        "corpus_id": "contract",
                        "work_id": "demo",
                        "translation": "temporary route contract",
                        "review_state": "generated",
                    }
                ],
            )
            request = Request(
                base_url + "/api/sentence-translations/delete-route-record?corpus_id=contract",
                method="DELETE",
            )
            with urlopen(request, timeout=15) as response:
                status = response.status
                payload = json.loads(response.read().decode("utf-8"))
            require(status == 200, "sentence translation DELETE route should return 200")
            require(payload.get("deleted", {}).get("id") == "delete-route-record", "DELETE response record mismatch")
            require(sentence_translation_service.iter_cached_records(path) == [], "DELETE route left the record stored")

            try:
                urlopen(request, timeout=15)
            except HTTPError as exc:
                require(exc.code == 404, "repeated sentence translation DELETE should return 404")
            else:
                raise AssertionError("repeated sentence translation DELETE should fail")

            missing_corpus_request = Request(
                base_url + "/api/sentence-translations/delete-route-record",
                method="DELETE",
            )
            try:
                urlopen(missing_corpus_request, timeout=15)
            except HTTPError as exc:
                require(exc.code == 400, "sentence translation DELETE without corpus_id should return 400")
            else:
                raise AssertionError("sentence translation DELETE without corpus_id should fail")
        finally:
            sentence_translation_service.AI_DIR = original_ai_dir


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
        "/translations": "번역 목록",
    }
    for path, expected in static_cases.items():
        body = fetch_text(base_url, path)
        require(expected in body, f"{path} did not contain {expected!r}")

    tokens = fetch_text(base_url, "/assets/design-tokens.css")
    require("--page-frame-width" in tokens, "design tokens asset did not load")
    require(fetch_status(base_url, "/assets/missing.css") == 404, "missing static asset should return 404")
    require(fetch_status(base_url, "/%2e%2e/server.py") == 403, "path traversal should return 403")
    for private_path in (
        "/server.py",
        "/runtime_status.py",
        "/README.md",
        "/templates/work.html",
        "/data/notes/nietzsche_notes.jsonl",
        "/data/segment_offset_index.sqlite",
        "/data/search_index.sqlite",
    ):
        require(fetch_status(base_url, private_path) == 403, f"private static path should return 403: {private_path}")

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
    require("javascript:;" not in read_body, f"{read_path} should not expose inert markdown javascript links")
    require('data-label="Paragraph ' not in read_body, f"{read_path} should use reader-language paragraph labels")
    require('aria-label="Paragraph ' not in read_body, f"{read_path} should use reader-language paragraph anchor labels")
    require('data-label="Sentence ' not in read_body, f"{read_path} should use reader-language sentence labels")
    require('aria-label="Section link"' not in read_body, f"{read_path} should use reader-language section anchor labels")
    source_body = fetch_text(base_url, source_path)
    require("static-reader" in source_body or "<pre" in source_body, f"{source_path} did not look like a source page")
    require("javascript:;" not in source_body, f"{source_path} should not expose inert markdown javascript links")
    require(fetch_status(base_url, "/read") == 400, "missing read path should return 400")

    health = fetch_json(base_url, "/api/health")
    require(health.get("status") in {"ok", "warning"}, "health status invalid")
    gemma_health = fetch_json(base_url, "/api/health/gemma")
    require(gemma_health.get("status") in {"ok", "warning"}, "Gemma health status invalid")
    require(
        (gemma_health.get("gemma") or {}).get("state") in {"starting", "ready", "failed", "unavailable"},
        "Gemma health state invalid",
    )
    archive_summary = fetch_json(base_url, "/api/archive/summary")
    require(
        archive_summary.get("schema_version") == 1 and len(archive_summary.get("corpora", [])) == 4,
        "archive summary shape invalid",
    )
    morning_titles = fetch_json(base_url, "/api/archive/titles?q=%EC%95%84%EC%B9%A8&limit=8")
    require(morning_titles.get("count") == 1, "archive title route did not resolve the Korean title alias")
    require(
        (morning_titles.get("results") or [{}])[0].get("href") == "/work/nietzsche/M",
        "archive title route resolved the wrong work",
    )
    genesis_titles = fetch_json(base_url, "/api/archive/titles?q=Genesis&limit=8")
    require(
        {result.get("section_title") for result in genesis_titles.get("results", [])}
        == {"Hebrew Bible", "LXX / Deuterocanon"},
        "archive title route did not distinguish duplicate Bible editions",
    )
    require(fetch_status(base_url, "/api/archive/titles?q=a&limit=0") == 400, "invalid title search limit should return 400")
    artifacts = fetch_json(base_url, "/api/artifacts")
    forbidden_diagnostic_keys = {
        "base_url",
        "bytes",
        "corpus_root",
        "error",
        "models",
        "modified_at",
        "notes",
        "path",
        "primary_output",
        "site_root",
        "source_root",
    }
    require(
        not (forbidden_diagnostic_keys & nested_keys(health)),
        "health response exposed private diagnostic fields",
    )
    require(
        not (forbidden_diagnostic_keys & nested_keys(artifacts)),
        "artifact response exposed private diagnostic fields",
    )
    study = fetch_json(base_url, "/api/study")
    require("groups" in study and "count" in study, "study api shape invalid")
    translation_export = fetch_text(base_url, "/api/sentence-translations/export?corpus_id=nietzsche&work_id=GM&format=markdown")
    require("번역 목록" in translation_export, "sentence translation export invalid")
    require("Sentence Translations" not in translation_export, "sentence translation export should avoid English title")
    require("Reviewed Gemma" not in translation_export, "sentence translation export should hide runtime-oriented title")
    translation_summary = fetch_json(base_url, "/api/sentence-translations/summary?corpus_id=nietzsche&work_id=GM")
    require("count" in translation_summary and "review_state_counts" in translation_summary, "sentence translation summary invalid")
    translation_page = fetch_text(base_url, "/translations?corpus_id=nietzsche&work_id=GM")
    require("translationsSubmit" in translation_page and "translationsResults" in translation_page, "translations page invalid")
    session_export = fetch_text(base_url, "/api/study-session/export?corpus_id=nietzsche&work_id=GM&format=markdown")
    require("학습 기록" in session_export, "study session export invalid")
    require("Study Bundle" not in session_export, "study session export should avoid English title")
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
    large_work_path = (
        "/work/wittgenstein/Group_BigTypescriptCorpus"
        "?variant=idp_transcription_linear"
    )
    large_work_body = fetch_text(base_url, large_work_path)
    require(len(large_work_body.encode("utf-8")) < 2 * 1024 * 1024, "large work initial HTML exceeds 2 MiB")
    require("virtual-work" in large_work_body, "large work route should use chunk loading")
    require("p-0001.s001" in large_work_body, "large work route missing initial sentence")
    require("p-3301.s001" not in large_work_body, "large work route eagerly rendered a middle sentence")
    chunk = fetch_json(
        base_url,
        "/api/work-chunks?corpus_id=wittgenstein"
        "&work_id=Group_BigTypescriptCorpus"
        "&variant_id=idp_transcription_linear"
        "&anchor=p-3301.s001",
    )
    require(chunk.get("chunk", {}).get("index") == 158, "work chunk anchor route resolved the wrong chunk")
    require("p-3301.s001" in chunk.get("chunk", {}).get("html", ""), "work chunk route lost the sentence anchor")
    require(fetch_status(base_url, "/api/work-chunks?corpus_id=wittgenstein") == 400, "missing chunk fields should return 400")


def main() -> None:
    httpd = LoopbackThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address
        base_url = f"http://{host}:{port}"
        check_routes(base_url)
        check_static_cache_contracts(base_url)
        check_translation_delete_route(base_url)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
    print("static routes ok")


if __name__ == "__main__":
    main()
