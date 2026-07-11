from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from check_visual_smoke import (
    DEFAULT_OUTPUT,
    find_browser,
    find_node,
    find_playwright_node_path,
    playwright_is_available,
    require,
    verify_screenshot,
)


SITE = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8793"
DEFAULT_QA_DIR = DEFAULT_OUTPUT / "live_ui_smoke"
VIEWPORTS = (("desktop", 1365, 768), ("mobile", 390, 844))

RUNNER_SCRIPT = r"""
require('module').Module._initPaths();
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const [baseUrlText, browserPath, outputDir, viewportJson] = process.argv.slice(2);
const baseUrl = new URL(baseUrlText.endsWith('/') ? baseUrlText : `${baseUrlText}/`);
const viewports = JSON.parse(viewportJson);
const screenshots = [];
const consoleErrors = [];
const mutatingRequests = [];
let currentStep = 'startup';

function absoluteUrl(route) {
  return new URL(route.replace(/^\//, ''), baseUrl).toString();
}

function screenshotPath(viewportName, label) {
  return path.join(outputDir, `${viewportName}-${label}.png`);
}

async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(250);
}

async function assertBodyHasContent(page, label) {
  const text = await page.locator('body').innerText({ timeout: 5000 }).catch(() => '');
  if (!text || text.trim().length < 20) {
    throw new Error(`${label} appears blank or missing body text`);
  }
}

async function gotoRoute(page, route, label) {
  currentStep = label;
  const response = await page.goto(absoluteUrl(route), { waitUntil: 'domcontentloaded', timeout: 20000 });
  if (!response) {
    throw new Error(`${label} did not return a navigation response`);
  }
  if (response.status() >= 400) {
    throw new Error(`${label} returned HTTP ${response.status()}`);
  }
  await settle(page);
  await assertBodyHasContent(page, label);
}

async function capture(page, viewportName, label) {
  const file = screenshotPath(viewportName, label);
  await page.screenshot({ path: file, fullPage: false });
  screenshots.push(file);
}

async function expectVisible(page, selector, label) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: 'visible', timeout: 10000 });
  return locator;
}

async function waitForSearchResult(page) {
  await page.waitForFunction(() => {
    const results = document.querySelector('#results');
    if (!results || results.getAttribute('aria-busy') === 'true') return false;
    return Boolean(results.querySelector('a[href^="/work/"], a[href*="/work/"]'));
  }, null, { timeout: 20000 });
}

async function runSearch(page) {
  currentStep = 'search-interaction';
  await expectVisible(page, '#searchForm', 'search form');
  await page.evaluate(() => {
    const panel = document.querySelector('#searchForm .filter-panel');
    if (panel) panel.open = true;
  });
  await page.waitForTimeout(100);
  await page.fill('#queryInput', 'ressentiment');
  await page.selectOption('#corpusSelect', 'nietzsche');
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/search?') && response.request().method() === 'GET',
      { timeout: 20000 }
    ).catch(() => null),
    page.click('#searchSubmit')
  ]);
  await waitForSearchResult(page);
}

async function clickFirstSearchResult(page) {
  currentStep = 'search-result-click';
  const link = page.locator('#results a[href^="/work/"], #results a[href*="/work/"]').first();
  await link.waitFor({ state: 'visible', timeout: 10000 });
  const href = await link.getAttribute('href');
  if (!href) {
    throw new Error('first search result has no href');
  }
  await Promise.all([
    page.waitForURL(/\/work\//, { timeout: 10000 }).catch(() => null),
    link.click()
  ]);
  if (!page.url().includes('/work/')) {
    await gotoRoute(page, href, 'search-result-work-fallback');
  } else {
    await settle(page);
    await assertBodyHasContent(page, 'search-result-work');
  }
  const cleanUrl = new URL(page.url());
  cleanUrl.hash = '';
  return `${cleanUrl.pathname}${cleanUrl.search}`;
}

async function inspectGemmaControls(page) {
  currentStep = 'work-gemma-controls';
  await expectVisible(page, '.reading-body', 'work reading body');
  await page.evaluate(() => {
    const panel = document.getElementById('studyCompanionPanel');
    if (panel) panel.classList.add('is-expanded');
    const toggle = document.getElementById('studyPanelToggle');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    const utility = document.querySelector('.translation-utility');
    if (utility) utility.hidden = false;
    document.querySelectorAll('.translation-utility, .sentence-more-controls, .translation-review-tools').forEach((details) => {
      details.open = true;
    });
  });
  await page.waitForTimeout(300);
  await page.waitForSelector('#gemmaRuntimeStatus', { state: 'attached', timeout: 10000 });
  await page.waitForSelector('#gemmaRuntimeCheck', { state: 'attached', timeout: 10000 });
  await page.waitForFunction(() => {
    const state = document.getElementById('gemmaRuntimeStatus')?.dataset.runtimeState || '';
    return state && state !== 'checking';
  }, null, { timeout: 5000 }).catch(() => {});
  const state = await page.locator('#gemmaRuntimeStatus').first().getAttribute('data-runtime-state');
  if (!['ready', 'offline', 'unavailable', 'checking'].includes(state || '')) {
    throw new Error(`unexpected Gemma runtime state: ${state}`);
  }
  const statusVisible = await page.locator('#gemmaRuntimeStatus').first().isVisible().catch(() => false);
  if (state !== 'ready' && !statusVisible) {
    throw new Error(`Gemma runtime status should be visible for state ${state}`);
  }
  const controls = await page.evaluate(() => {
    const ids = [
      'gemmaRuntimeCheck',
      'regenerateSentence',
      'markTranslationReviewed',
      'rejectTranslation',
      'copyStudyCard',
      'draftTranslationNote'
    ];
    return ids.map((id) => {
      const element = document.getElementById(id);
      if (!element) return { id, exists: false };
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return {
        id,
        exists: true,
        disabled: Boolean(element.disabled),
        ariaBusy: element.getAttribute('aria-busy') || '',
        visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
      };
    });
  });
  const missing = controls.filter((control) => !control.exists).map((control) => control.id);
  if (missing.length) {
    throw new Error(`missing Gemma/study controls: ${missing.join(', ')}`);
  }
  const hidden = controls
    .filter((control) => !control.visible && !(state === 'ready' && control.id === 'gemmaRuntimeCheck'))
    .map((control) => control.id);
  if (hidden.length) {
    throw new Error(`hidden Gemma/study controls: ${hidden.join(', ')}`);
  }
  const regenerate = controls.find((control) => control.id === 'regenerateSentence');
  if (!regenerate || regenerate.disabled !== true) {
    throw new Error('regenerateSentence should be disabled before selecting a sentence');
  }
  return { state, controls };
}

async function smokeViewport(browser, viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ step: currentStep, type: 'console', text: message.text().slice(0, 600) });
    }
  });
  page.on('pageerror', (error) => {
    consoleErrors.push({ step: currentStep, type: 'pageerror', text: String(error && error.message ? error.message : error).slice(0, 600) });
  });
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      mutatingRequests.push({ step: currentStep, method: request.method(), url: request.url() });
    }
  });

  await gotoRoute(page, '/', `${viewport.name}-home`);
  await expectVisible(page, '.reader, body', 'home body');
  await capture(page, viewport.name, 'home');

  await gotoRoute(page, '/search', `${viewport.name}-search`);
  await runSearch(page);
  await capture(page, viewport.name, 'search-results');

  const workRoute = await clickFirstSearchResult(page);
  await gotoRoute(page, workRoute || '/work/nietzsche/GM', `${viewport.name}-work-detail`);
  const gemma = await inspectGemmaControls(page);
  await capture(page, viewport.name, 'work-detail');

  await gotoRoute(page, '/study', `${viewport.name}-study`);
  await page.waitForSelector('#studyForm', { state: 'attached', timeout: 10000 });
  await expectVisible(page, '#studyResults', 'study results');
  await capture(page, viewport.name, 'study');

  await context.close();
  return { viewport: viewport.name, gemma };
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: browserPath,
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
  const viewportResults = [];
  try {
    for (const viewport of viewports) {
      viewportResults.push(await smokeViewport(browser, viewport));
    }
  } finally {
    await browser.close();
  }
  if (mutatingRequests.length) {
    throw new Error(`read-only smoke made mutating requests: ${JSON.stringify(mutatingRequests)}`);
  }
  if (consoleErrors.length) {
    throw new Error(`browser console errors: ${JSON.stringify(consoleErrors)}`);
  }
  console.log(JSON.stringify({ screenshots, viewports: viewportResults }, null, 2));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only live UI smoke test against the fixed Philo Archive Reader port."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Live Reader URL. Defaults to http://127.0.0.1:8793.")
    parser.add_argument("--output", type=Path, default=DEFAULT_QA_DIR, help="QA output directory for screenshots.")
    parser.add_argument("--browser", default="", help="Explicit Chrome/Edge executable path.")
    parser.add_argument("--node", default="", help="Explicit Node.js executable path.")
    return parser.parse_args()


def fetch_json(url: str, timeout: float = 5.0) -> dict[str, object]:
    try:
        with urlopen(url, timeout=timeout) as response:
            require(response.status == 200, f"{url} returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise SystemExit(f"{url} returned HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise SystemExit(
            f"Reader is not reachable at {url}. Start the existing service on 127.0.0.1:8793; "
            "this smoke test does not choose another port."
        ) from error


def check_live_service(base_url: str) -> None:
    root_url = base_url.rstrip("/") + "/"
    health_url = base_url.rstrip("/") + "/api/health"
    try:
        with urlopen(root_url, timeout=5.0) as response:
            require(response.status == 200, f"{root_url} returned HTTP {response.status}")
    except HTTPError as error:
        raise SystemExit(f"{root_url} returned HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise SystemExit(
            f"Reader is not reachable at {root_url}. Start the existing service on 127.0.0.1:8793; "
            "this smoke test does not choose another port."
        ) from error

    health = fetch_json(health_url)
    issues = health.get("issues") or []
    require(isinstance(issues, list), "health issues must be a list")
    require(not issues, f"health issues are not empty: {issues}")


def prepare_output_dir(output: Path) -> Path:
    qa_root = DEFAULT_OUTPUT.resolve()
    target = output.resolve()
    require(target == qa_root or qa_root in target.parents, f"output must stay under {qa_root}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_runner(output: Path) -> Path:
    runner = output / "live_ui_smoke_runner.cjs"
    runner.write_text(RUNNER_SCRIPT, encoding="utf-8")
    return runner


def run_node_check(node: str, runner: Path) -> None:
    result = subprocess.run(
        [node, "--check", str(runner)],
        cwd=SITE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    require(result.returncode == 0, f"node --check failed:\n{result.stderr or result.stdout}")


def run_playwright(node: str, node_path: str, browser: str, runner: Path, base_url: str, output: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["NODE_PATH"] = node_path
    viewport_payload = json.dumps(
        [{"name": name, "width": width, "height": height} for name, width, height in VIEWPORTS],
        separators=(",", ":"),
    )
    result = subprocess.run(
        [node, str(runner), base_url, browser, str(output), viewport_payload],
        cwd=SITE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    require(result.returncode == 0, f"Playwright live UI smoke failed:\n{result.stderr or result.stdout}")
    return json.loads(result.stdout)


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    require(base_url == DEFAULT_BASE_URL, "live UI smoke must use the fixed Reader port http://127.0.0.1:8793")
    check_live_service(base_url)

    output = prepare_output_dir(args.output)
    runner = write_runner(output)
    node = find_node(args.node)
    require(node, "Node.js was not found. Pass --node or set NODE.")
    node_path = find_playwright_node_path()
    require(node_path, "playwright-core was not found. Install dependencies or set NODE_PATH.")
    require(playwright_is_available(node, node_path), "playwright-core is not importable from NODE_PATH.")
    browser = find_browser(args.browser)

    run_node_check(node, runner)
    report = run_playwright(node, node_path, browser, runner, base_url, output)
    screenshot_paths = [Path(path) for path in report.get("screenshots", [])]
    expected_count = len(VIEWPORTS) * 4
    require(len(screenshot_paths) == expected_count, f"expected {expected_count} screenshots, got {len(screenshot_paths)}")
    for screenshot in screenshot_paths:
        verify_screenshot(screenshot)

    summary = {
        "base_url": base_url,
        "output": str(output),
        "screenshots": [str(path) for path in screenshot_paths],
        "viewports": report.get("viewports", []),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
