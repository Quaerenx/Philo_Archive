from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE / "scripts"))

from check_visual_smoke import find_browser, free_port, wait_for_health  # noqa: E402


TARGET_ROUTE = "/work/nietzsche/GM#p-0023.s001"
TARGET_SENTENCE_ID = "p-0023.s001"
VIEWPORTS = [
    ("desktop", 1365, 768),
    ("mobile", 390, 844),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def dump_dom_with_profile(browser: str, url: str, width: int, height: int, profile_dir: Path) -> str:
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-gpu-sandbox",
        "--disable-background-networking",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-features=DawnGraphite,Vulkan,UseSkiaRenderer,CanvasOopRasterization",
        "--no-default-browser-check",
        "--no-first-run",
        "--use-angle=swiftshader",
        f"--user-data-dir={profile_dir.resolve().as_posix()}",
        f"--window-size={width},{height}",
        "--virtual-time-budget=4000",
        "--dump-dom",
        url,
    ]
    result = subprocess.run(
        command,
        cwd=SITE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    stderr = (result.stderr or "").strip()
    require(result.returncode == 0, f"browser DOM dump failed for {url}: {stderr}")
    require("<html" in result.stdout.lower(), f"browser DOM dump did not return HTML for {url}")
    return result.stdout


def check_selected_sentence_dom(html: str, viewport_label: str) -> None:
    context = f"reader interaction {viewport_label}"
    require(TARGET_SENTENCE_ID in html, f"{context} missing target sentence id")
    require(
        re.search(r'class="[^"]*\breader-sentence\b[^"]*\bselected\b[^"]*"', html) is not None,
        f"{context} did not mark a source sentence selected",
    )
    require(
        '<span class="translation-target-label">Source</span>' in html,
        f"{context} did not render human-readable source target label",
    )
    require(
        re.search(r'<strong class="translation-target-id">Sentence \d+ of \d+</strong>', html) is not None,
        f"{context} did not render selected sentence position in the study panel",
    )
    require("translation-target-excerpt" in html, f"{context} missing selected sentence excerpt")
    require("study-panel-toggle-action\">Back to text" in html, f"{context} did not expand study panel after selection")
    require("study-panel-toggle-summary\">Sentence " in html, f"{context} missing selected sentence summary")
    require('data-translation-section="translation"' in html, f"{context} missing translation section")
    require('data-translation-section="commentary"' in html, f"{context} missing commentary section")
    require("<h3>Translation</h3>" in html, f"{context} missing translation heading")
    require("<h3>Commentary</h3>" in html, f"{context} missing commentary heading")
    require("translation-primary" in html, f"{context} missing readable translation body")
    require("translation-commentary" in html, f"{context} missing readable commentary body")
    require("Select a sentence to study." not in html, f"{context} still shows empty translation state")
    for noisy_text in ("source_text_sha256", "sentence_text_sha256", "prompt_sha256", "Literal gloss", "Key terms", "Cached result", "New result"):
        require(noisy_text not in html, f"{context} exposes noisy translation metadata: {noisy_text}")


def check_recent_work_dom(html: str, viewport_label: str) -> None:
    context = f"home recent work {viewport_label}"
    require("Continue reading" in html, f"{context} missing continue reading entry")
    require("recent-work" in html, f"{context} missing recent work markup")
    require("/work/nietzsche/GM#p-0023.s001" in html, f"{context} missing recent sentence link")
    require("Zur Genealogie der Moral" in html, f"{context} missing recent work title")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate reader sentence selection interaction in a headless browser.", allow_abbrev=False)
    parser.add_argument("--browser", default="", help="Path to Edge/Chrome/Chromium. Defaults to common local installs.")
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
        url = f"{base_url}{TARGET_ROUTE}"
        for viewport_label, width, height in VIEWPORTS:
            profile_dir = Path(tempfile.mkdtemp(prefix="philo-reader-interaction-"))
            try:
                html = dump_dom_with_profile(browser, url, width, height, profile_dir)
                check_selected_sentence_dom(html, viewport_label)
                home_html = dump_dom_with_profile(browser, f"{base_url}/", width, height, profile_dir)
                check_recent_work_dom(home_html, viewport_label)
            finally:
                shutil.rmtree(profile_dir, ignore_errors=True)
        print("reader interaction smoke ok")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
