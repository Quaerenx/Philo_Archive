from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE / "scripts"))

from check_visual_smoke import (  # noqa: E402
    find_browser,
    find_node,
    find_playwright_node_path,
    free_port,
    playwright_is_available,
    seed_visual_translations,
    wait_for_health,
)


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


def dump_reader_and_home_with_playwright(
    node: str,
    node_path: str,
    browser: str,
    work_url: str,
    home_url: str,
    width: int,
    height: int,
) -> tuple[str, str]:
    script = r"""
require('module').Module._initPaths();
const { chromium } = require('playwright-core');
const [workUrl, homeUrl, widthText, heightText, executablePath] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: [
      '--disable-background-networking',
      '--disable-breakpad',
      '--disable-crash-reporter',
      '--disable-features=DawnGraphite,Vulkan,UseSkiaRenderer,CanvasOopRasterization',
      '--no-default-browser-check',
      '--no-first-run',
      '--use-angle=swiftshader'
    ]
  });
  try {
    const page = await browser.newPage({
      viewport: { width: Number(widthText), height: Number(heightText) },
      deviceScaleFactor: 1
    });
    await page.goto(workUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('.reader-sentence.selected', { timeout: 10000 });
    await page.waitForSelector('#translationOutput:not([hidden])', { timeout: 10000 });
    await page.waitForFunction(
      () => ['선택한 문장', '번역 완료'].includes(
        document.querySelector('.study-panel-toggle-summary')?.textContent.trim() || ''
      ),
      null,
      { timeout: 10000 }
    );
    const workHtml = await page.content();
    await page.goto(homeUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('.recent-work .recent-work-link', { timeout: 10000 });
    const homeHtml = await page.content();
    process.stdout.write(JSON.stringify({ work_html: workHtml, home_html: homeHtml }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""
    env = os.environ.copy()
    env["NODE_PATH"] = node_path
    script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            suffix=".cjs",
            prefix="reader-interaction-",
            delete=False,
            encoding="utf-8",
        ) as script_file:
            script_file.write(script)
            script_path = Path(script_file.name)
        result = subprocess.run(
            [
                node,
                str(script_path),
                work_url,
                home_url,
                str(width),
                str(height),
                browser,
            ],
            cwd=SITE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    finally:
        if script_path:
            script_path.unlink(missing_ok=True)
    stderr = (result.stderr or "").strip()
    require(result.returncode == 0, f"Playwright interaction capture failed for {work_url}: {stderr}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f"Playwright interaction capture returned invalid JSON: {error}") from error
    work_html = payload.get("work_html")
    home_html = payload.get("home_html")
    require(isinstance(work_html, str) and "<html" in work_html.lower(), "Playwright work capture did not return HTML")
    require(isinstance(home_html, str) and "<html" in home_html.lower(), "Playwright home capture did not return HTML")
    return work_html, home_html


def check_selected_sentence_dom(html: str, viewport_label: str) -> None:
    context = f"reader interaction {viewport_label}"
    require(TARGET_SENTENCE_ID in html, f"{context} missing target sentence id")
    require(
        re.search(r'class="[^"]*\breader-sentence\b[^"]*\bselected\b[^"]*"', html) is not None,
        f"{context} did not mark a source sentence selected",
    )
    require(
        '<span class="translation-target-label">원문</span>' in html,
        f"{context} did not render human-readable source target label",
    )
    require(
        re.search(r'<strong class="translation-target-id">문장 \d+ / \d+</strong>', html) is not None,
        f"{context} did not render selected sentence position in the study panel",
    )
    require("translation-target-excerpt" in html, f"{context} missing selected sentence excerpt")
    require("study-panel-toggle-action\">본문 보기" in html, f"{context} did not expand study panel after selection")
    require(
        "study-panel-toggle-summary\">선택한 문장" in html or "study-panel-toggle-summary\">번역 완료" in html,
        f"{context} missing selected sentence summary",
    )
    require('data-translation-section="translation"' in html, f"{context} missing translation section")
    require('data-translation-section="commentary"' in html, f"{context} missing commentary section")
    require("<h3>번역</h3>" in html, f"{context} missing translation heading")
    require("<h3>해설</h3>" in html, f"{context} missing commentary heading")
    require("translation-primary" in html, f"{context} missing readable translation body")
    require("translation-commentary" in html, f"{context} missing readable commentary body")
    require("Select a sentence to study." not in html, f"{context} still shows empty translation state")
    for noisy_text in ("source_text_sha256", "sentence_text_sha256", "prompt_sha256", "Literal gloss", "Key terms", "Cached result", "New result"):
        require(noisy_text not in html, f"{context} exposes noisy translation metadata: {noisy_text}")


def check_recent_work_dom(html: str, viewport_label: str) -> None:
    context = f"home recent work {viewport_label}"
    require("이어 읽기" in html, f"{context} missing continue reading entry")
    require("Continue reading" not in html, f"{context} should keep recent work text in the reader language")
    require("recent-work" in html, f"{context} missing recent work markup")
    require("/work/nietzsche/GM#p-0023.s001" in html, f"{context} missing recent sentence link")
    require("Zur Genealogie der Moral" in html, f"{context} missing recent work title")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate reader sentence selection interaction in a headless browser.", allow_abbrev=False)
    parser.add_argument("--browser", default="", help="Path to Edge/Chrome/Chromium. Defaults to common local installs.")
    args = parser.parse_args()

    browser = find_browser(args.browser)
    node = find_node()
    node_path = find_playwright_node_path()
    use_playwright = playwright_is_available(node, node_path)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    ai_temp_dir = tempfile.TemporaryDirectory(prefix="philo_reader_interaction_ai_")
    server_env = os.environ.copy()
    server_env["PHILO_AI_DIR"] = str(Path(ai_temp_dir.name))
    seed_visual_translations(Path(ai_temp_dir.name))
    server = subprocess.Popen(
        [sys.executable, str(SITE / "server.py"), "--host", "127.0.0.1", "--port", str(port)],
        cwd=SITE,
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_health(base_url, server)
        url = f"{base_url}{TARGET_ROUTE}"
        for viewport_label, width, height in VIEWPORTS:
            if use_playwright:
                html, home_html = dump_reader_and_home_with_playwright(
                    node,
                    node_path,
                    browser,
                    url,
                    f"{base_url}/",
                    width,
                    height,
                )
            else:
                profile_dir = Path(tempfile.mkdtemp(prefix="philo-reader-interaction-"))
                try:
                    html = dump_dom_with_profile(browser, url, width, height, profile_dir)
                    home_html = dump_dom_with_profile(browser, f"{base_url}/", width, height, profile_dir)
                finally:
                    shutil.rmtree(profile_dir, ignore_errors=True)
            check_selected_sentence_dom(html, viewport_label)
            check_recent_work_dom(home_html, viewport_label)
        print("reader interaction smoke ok")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        ai_temp_dir.cleanup()


if __name__ == "__main__":
    main()
