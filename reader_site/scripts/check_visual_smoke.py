from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from services.sources import CORPUS_ROOTS, relative_source_path  # noqa: E402

DEFAULT_OUTPUT = SITE / "data" / "visual_qa.local"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ROUTES = [
    ("home", "/"),
    ("nietzsche-category", "/category/nietzsche"),
    ("nietzsche-work", "/work/nietzsche/GM"),
    ("search", "/search"),
    ("notes", "/notes"),
    ("study", "/study"),
]
VIEWPORTS = [
    ("desktop", 1365, 768),
    ("mobile", 390, 844),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_browser(explicit: str = "") -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    for env_name in ("MSEDGE", "CHROME", "CHROMIUM"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(value)
    candidates.extend(
        [
            shutil.which("msedge") or "",
            shutil.which("chrome") or "",
            shutil.which("chromium") or "",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("No headless browser found. Set MSEDGE, CHROME, CHROMIUM, or pass --browser.")


def discover_source_routes() -> list[tuple[str, str]]:
    for root in CORPUS_ROOTS:
        if not root.exists():
            continue
        sample = next(root.rglob("*.md"), None)
        if sample:
            relative = quote(relative_source_path(sample), safe="")
            return [
                ("reader", f"/read?path={relative}"),
                ("source", f"/source?path={relative}"),
            ]
    return []


def wait_for_health(base_url: str, process: subprocess.Popen, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit("reader server exited before visual smoke checks could run")
        try:
            with urlopen(f"{base_url}/api/health", timeout=1.0) as response:
                require(response.status == 200, f"health endpoint returned {response.status}")
                return
        except URLError:
            time.sleep(0.25)
    raise SystemExit("reader server did not become ready")


def fetch_html(url: str) -> str:
    with urlopen(url, timeout=5.0) as response:
        require(response.status == 200, f"{url} returned {response.status}")
        content_type = response.headers.get("Content-Type", "")
        require("text/html" in content_type, f"{url} did not return HTML")
        return response.read().decode("utf-8", errors="replace")


def check_route_markup(route: str, html: str) -> None:
    if route == "/study":
        for needle in [
            "studySubmit",
            "studyClear",
            "studyActiveFilters",
            "studyStatus",
            "aria-busy=\"false\"",
            "study.css?v=study8",
            "study.js?v=study8",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route == "/notes":
        for needle in [
            "notesSubmit",
            "notesClear",
            "notesActiveFilters",
            "notesStatus",
            "aria-busy=\"false\"",
            "notes.css?v=notes7",
            "notes.js?v=notes8",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route == "/search":
        for needle in [
            "searchSubmit",
            "searchClear",
            "searchActiveFilters",
            "searchStatus",
            "aria-busy=\"false\"",
            "search.css?v=phase11",
            "search.js?v=phase11",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route.startswith("/work/"):
        for needle in [
            "reading-desk",
            "study-tabs",
            "studyPanelToggle",
            "studyPanelScrim",
            "study-panel-toggle-action",
            "study-panel-toggle-summary",
            "readingPosition",
            "sentenceContext",
            "previousSentence",
            "nextSentence",
            "markTranslationReviewed",
            "role=\"status\"",
            "aria-busy=\"false\"",
            "noteStatus",
            "noteTargetPreview",
            "lockNoteTarget",
            "noteListSummary",
            "noteSort",
            "translation-output",
            "reader-sentence",
            "reader-work.css?v=common39",
            "reader-work.js?v=common45",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")


def capture(browser: str, url: str, output_path: Path, width: int, height: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    profile_dir = output_path.with_suffix(".profile")
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)
    try:
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--disable-background-networking",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--disable-features=DawnGraphite,Vulkan,UseSkiaRenderer,CanvasOopRasterization",
            "--hide-scrollbars",
            "--no-default-browser-check",
            "--no-first-run",
            "--use-angle=swiftshader",
            f"--user-data-dir={profile_dir.resolve().as_posix()}",
            f"--window-size={width},{height}",
            f"--screenshot={output_path}",
            url,
        ]
        try:
            result = subprocess.run(
                command,
                cwd=SITE,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
            raise AssertionError(f"browser screenshot timed out for {url}: {stderr.strip()}") from exc
        stderr = (result.stderr or "").strip()
        require(result.returncode == 0, f"browser screenshot failed for {url}: {stderr}")
        require(output_path.exists(), f"screenshot was not written: {output_path}")
        data = output_path.read_bytes()
        require(data.startswith(PNG_SIGNATURE), f"screenshot is not a PNG: {output_path}")
        require(len(data) > 5000, f"screenshot is unexpectedly small: {output_path}")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture local browser screenshots for reader-site visual smoke QA.", allow_abbrev=False)
    parser.add_argument("--browser", default="", help="Path to Edge/Chrome/Chromium. Defaults to common local installs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Screenshot output directory.")
    parser.add_argument("--html-only", action="store_true", help="Validate routed HTML markers without launching a browser.")
    parser.add_argument("--allow-screenshot-failures", action="store_true", help="Report screenshot failures without failing HTML smoke checks.")
    args = parser.parse_args()

    browser = "" if args.html_only else find_browser(args.browser)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, str(SITE / "server.py"), "--host", "127.0.0.1", "--port", str(port)],
        cwd=SITE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_health(base_url, server)
        routes = [*ROUTES, *discover_source_routes()]
        html_count = 0
        screenshot_count = 0
        screenshot_failures = []
        for route_label, route in routes:
            url = f"{base_url}{route}"
            html = fetch_html(url)
            require("<html" in html.lower(), f"{route} response does not look like a page")
            require("Personal Archive of Literature" in html or "Archive" in html, f"{route} is missing archive identity text")
            check_route_markup(route, html)
            html_count += 1
            if args.html_only:
                continue
            for viewport_label, width, height in VIEWPORTS:
                output_path = args.output / f"{route_label}-{viewport_label}.png"
                try:
                    capture(browser, url, output_path, width, height)
                    screenshot_count += 1
                except AssertionError as exc:
                    message = f"{route_label}/{viewport_label}: {exc}"
                    if not args.allow_screenshot_failures:
                        raise AssertionError(message) from exc
                    screenshot_failures.append(message)
        if args.html_only:
            print(f"visual smoke html ok ({html_count} routes)")
        elif screenshot_failures:
            print(f"visual smoke html ok ({html_count} routes); screenshot failures allowed ({len(screenshot_failures)})")
            for failure in screenshot_failures:
                print(f"- {failure}")
        else:
            print(f"visual smoke ok ({screenshot_count} screenshots in {args.output})")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
