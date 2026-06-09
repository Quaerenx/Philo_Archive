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


def capture(browser: str, url: str, output_path: Path, width: int, height: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={output_path}",
        url,
    ]
    result = subprocess.run(command, cwd=SITE, capture_output=True, text=True, timeout=45)
    require(result.returncode == 0, f"browser screenshot failed for {url}: {result.stderr.strip()}")
    require(output_path.exists(), f"screenshot was not written: {output_path}")
    data = output_path.read_bytes()
    require(data.startswith(PNG_SIGNATURE), f"screenshot is not a PNG: {output_path}")
    require(len(data) > 5000, f"screenshot is unexpectedly small: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture local browser screenshots for reader-site visual smoke QA.", allow_abbrev=False)
    parser.add_argument("--browser", default="", help="Path to Edge/Chrome/Chromium. Defaults to common local installs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Screenshot output directory.")
    args = parser.parse_args()

    browser = find_browser(args.browser)
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
        count = 0
        for route_label, route in routes:
            url = f"{base_url}{route}"
            html = fetch_html(url)
            require("<html" in html.lower(), f"{route} response does not look like a page")
            require("Personal Archive of Literature" in html or "Archive" in html, f"{route} is missing archive identity text")
            for viewport_label, width, height in VIEWPORTS:
                output_path = args.output / f"{route_label}-{viewport_label}.png"
                capture(browser, url, output_path, width, height)
                count += 1
        print(f"visual smoke ok ({count} screenshots in {args.output})")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
