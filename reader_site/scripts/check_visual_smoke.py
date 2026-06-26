from __future__ import annotations

import argparse
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import zlib
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
    ("home", "/", True),
    ("nietzsche-category", "/category/nietzsche", True),
    ("nietzsche-work", "/work/nietzsche/GM", True),
    ("nietzsche-work-selected", "/work/nietzsche/GM#p-0023.s001", True),
    ("search", "/search", True),
    ("search-results", "/search?q=ressentiment&corpus_id=nietzsche", True),
    ("notes", "/notes", True),
    ("study", "/study", True),
    ("translations", "/translations", True),
    ("translations-review", "/translations?review_state=generated", True),
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


def find_node(explicit: str = "") -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_value = os.environ.get("NODE")
    if env_value:
        candidates.append(env_value)
    candidates.extend(
        [
            shutil.which("node") or "",
            str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"),
            str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"),
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def find_playwright_node_path() -> str:
    candidates = []
    env_value = os.environ.get("NODE_PATH")
    if env_value:
        candidates.extend(env_value.split(os.pathsep))
    candidates.extend(
        [
            str(SITE / "node_modules"),
            str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules" / ".pnpm" / "node_modules"),
            str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules"),
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and ((path / "playwright-core").exists() or (path / "playwright").exists()):
            return str(path)
    return ""


def playwright_is_available(node: str, node_path: str) -> bool:
    if not node or not node_path:
        return False
    env = os.environ.copy()
    env["NODE_PATH"] = node_path
    script = "require('module').Module._initPaths(); require('playwright-core');"
    result = subprocess.run(
        [node, "-e", script],
        cwd=SITE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    return result.returncode == 0


def discover_source_routes() -> list[tuple[str, str, bool]]:
    for root in CORPUS_ROOTS:
        if not root.exists():
            continue
        sample = next(root.rglob("*.md"), None)
        if sample:
            relative = quote(relative_source_path(sample), safe="")
            return [
                ("reader", f"/read?path={relative}", True),
                ("source", f"/source?path={relative}", True),
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
    if route == "/":
        for needle in [
            "Search",
            "Notes",
            "Study",
            "Translations",
            "app.js?v=home7",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route == "/study":
        for needle in [
            "studySubmit",
            "studyClear",
            "studyActiveFilters",
            "studyStatus",
            "aria-busy=\"false\"",
            "study.css?v=study18",
            "study.js?v=study23",
            "filter-panel",
            "export-tools",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route == "/notes":
        for needle in [
            "notesSubmit",
            "notesClear",
            "notesActiveFilters",
            "notesStatus",
            "aria-busy=\"false\"",
            "notes.css?v=notes19",
            "notes.js?v=notes26",
            "filter-panel",
            "export-tools",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route.startswith("/translations"):
        for needle in [
            "translationsSubmit",
            "translationsClear",
            "translationsActiveFilters",
            "translationsStatus",
            "translationsResults",
            "translationsReviewQueue",
            "aria-busy=\"false\"",
            "translations.css?v=trans16",
            "translations.js?v=trans39",
            "translationsListTools",
            "Search and filters</summary>",
            "filter-panel",
            "export-tools",
            "Export results</summary>",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route.startswith("/search"):
        for needle in [
            "searchSubmit",
            "searchClear",
            "searchActiveFilters",
            "searchStatus",
            "aria-busy=\"false\"",
            "search.css?v=phase19",
            "search.js?v=phase22",
            "Translations",
            "filter-panel",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route.startswith("/work/"):
        for needle in [
            "reading-desk",
            "toolbar-more",
            "More</summary>",
            "Source</a>",
            "study-tabs",
            "study-tab-secondary",
            "citation-copy-options",
            "More</summary>",
            "studyPanelToggle",
            "studyPanelScrim",
            "study-panel-toggle-action",
            "study-panel-toggle-summary",
            "readingPosition",
            "sentence-context-tools",
            "sentenceContext",
            "sentence-more-controls",
            "More navigation</summary>",
            "previousSentence",
            "nextSentence",
            "markTranslationReviewed",
            "role=\"status\"",
            "aria-busy=\"false\"",
            "noteStatus",
            "noteTargetPreview",
            "lockNoteTarget",
            "noteListSummary",
            "note-options",
            "Tags</summary>",
            "notes-filter-tools",
            "Saved</summary>",
            "noteSort",
            "gemmaRuntimeStatus",
            "Translation service status",
            "translationRecordsSummary",
            "Translations</div>",
            "studyProgress",
            "Continue study",
            "translation-export-tools",
            "Export</summary>",
            "exportAllTranslations",
            "All Markdown",
            "exportStudySession",
            "Study pack",
            "studySessionSummary",
            "Study pack</div>",
            "translation-output",
            "reader-sentence",
            "reader-work.css?v=common103",
            "reader-work.js?v=common121",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")


def paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def decode_png_pixels(path: Path) -> tuple[int, int, int, bytes]:
    data = path.read_bytes()
    require(data.startswith(PNG_SIGNATURE), f"screenshot is not a PNG: {path}")
    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = 0
    idat_chunks: list[bytes] = []
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk_data)
            require(interlace == 0, f"screenshot uses unsupported interlacing: {path}")
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break
    require(width > 0 and height > 0, f"screenshot has invalid dimensions: {path}")
    require(bit_depth == 8, f"screenshot uses unsupported bit depth {bit_depth}: {path}")
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    require(color_type in channels_by_type, f"screenshot uses unsupported color type {color_type}: {path}")
    channels = channels_by_type[color_type]
    row_size = width * channels
    raw = zlib.decompress(b"".join(idat_chunks))
    require(len(raw) >= (row_size + 1) * height, f"screenshot pixel data is truncated: {path}")
    pixels = bytearray(row_size * height)
    previous = bytearray(row_size)
    cursor = 0
    for row_index in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + row_size])
        cursor += row_size
        for index, value in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + paeth_predictor(left, up, up_left)) & 0xFF
            else:
                require(filter_type == 0, f"screenshot uses unsupported PNG filter {filter_type}: {path}")
        start = row_index * row_size
        pixels[start : start + row_size] = row
        previous = row
    return width, height, color_type, bytes(pixels)


def check_png_content(path: Path) -> None:
    width, height, color_type, pixels = decode_png_pixels(path)
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    row_size = width * channels
    x_step = max(1, width // 90)
    y_step = max(1, height // 70)
    buckets: set[tuple[int, int, int]] = set()
    min_luminance = 255
    max_luminance = 0
    dark_pixels = 0
    sampled = 0
    for y in range(0, height, y_step):
        row = y * row_size
        for x in range(0, width, x_step):
            index = row + (x * channels)
            if color_type == 0:
                red = green = blue = pixels[index]
            elif color_type == 4:
                red = green = blue = pixels[index]
            else:
                red, green, blue = pixels[index], pixels[index + 1], pixels[index + 2]
            luminance = int((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))
            min_luminance = min(min_luminance, luminance)
            max_luminance = max(max_luminance, luminance)
            dark_pixels += 1 if luminance < 175 else 0
            buckets.add((red // 32, green // 32, blue // 32))
            sampled += 1
    dark_ratio = dark_pixels / max(1, sampled)
    require(max_luminance - min_luminance >= 35, f"screenshot appears blank or low-contrast: {path}")
    require(len(buckets) >= 4, f"screenshot has too little visual variation: {path}")
    require(dark_ratio >= 0.002, f"screenshot appears to be missing readable text: {path}")


def verify_screenshot(path: Path) -> None:
    require(path.exists(), f"screenshot was not written: {path}")
    data = path.read_bytes()
    require(data.startswith(PNG_SIGNATURE), f"screenshot is not a PNG: {path}")
    require(len(data) > 5000, f"screenshot is unexpectedly small: {path}")
    check_png_content(path)


def capture_with_playwright(node: str, node_path: str, browser: str, url: str, output_path: Path, width: int, height: int) -> None:
    env = os.environ.copy()
    env["NODE_PATH"] = node_path
    script = r"""
require('module').Module._initPaths();
const { chromium } = require('playwright-core');
const [url, outputPath, widthText, heightText, executablePath] = process.argv.slice(1);
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
  const page = await browser.newPage({
    viewport: { width: Number(widthText), height: Number(heightText) },
    deviceScaleFactor: 1
  });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  const parsed = new URL(url);
  if (parsed.pathname === '/search' && parsed.searchParams.get('q')) {
    await page.waitForSelector('.result:not(.search-skeleton), .empty-state', { timeout: 5000 }).catch(() => {});
  }
  if (parsed.pathname === '/notes' && !parsed.search) {
    await page.waitForSelector('#notesResults .note-card:not(.notes-skeleton), #notesResults .empty-state', { timeout: 7000 }).catch(() => {});
    const notesPageState = await page.evaluate(() => {
      const empty = document.querySelector('#notesResults .empty-state');
      return {
        hasNotes: document.querySelectorAll('#notesResults .note-card:not(.notes-skeleton)').length > 0,
        formHidden: Boolean(document.querySelector('#notesForm')?.hidden),
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim())
      };
    });
    if (!notesPageState.hasNotes) {
      if (!notesPageState.formHidden) throw new Error(`empty notes page should hide filter form: ${JSON.stringify(notesPageState)}`);
      if (notesPageState.emptyTitle !== 'No notes yet.' || notesPageState.emptyBodyCount !== 0) {
        throw new Error(`empty notes page should stay quiet: ${JSON.stringify(notesPageState)}`);
      }
      if (!notesPageState.emptyActions.includes('Find work')) {
        throw new Error(`empty notes page should keep a concise find action: ${JSON.stringify(notesPageState)}`);
      }
    }
  }
  if (parsed.pathname === '/study' && !parsed.search) {
    await page.waitForSelector('#studyResults .study-group:not(.study-skeleton), #studyResults .empty-state', { timeout: 7000 }).catch(() => {});
    const studyPageState = await page.evaluate(() => {
      const empty = document.querySelector('#studyResults .empty-state');
      return {
        hasGroups: document.querySelectorAll('#studyResults .study-group:not(.study-skeleton)').length > 0,
        formHidden: Boolean(document.querySelector('#studyForm')?.hidden),
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim())
      };
    });
    if (!studyPageState.hasGroups) {
      if (!studyPageState.formHidden) throw new Error(`empty study page should hide filter form: ${JSON.stringify(studyPageState)}`);
      if (studyPageState.emptyTitle !== 'No saved notes yet.' || studyPageState.emptyBodyCount !== 0) {
        throw new Error(`empty study page should stay quiet: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.emptyActions.includes('Working notes') || !studyPageState.emptyActions.includes('Find work')) {
        throw new Error(`empty study page should keep concise actions: ${JSON.stringify(studyPageState)}`);
      }
    }
  }
  if (parsed.pathname === '/translations' && !parsed.search) {
    await page.waitForSelector('#translationsResults .translation-record-card:not(.notes-skeleton), #translationsResults .empty-state', { timeout: 7000 }).catch(() => {});
    const translationsPageState = await page.evaluate(() => {
      const empty = document.querySelector('#translationsResults .empty-state');
      return {
        hasRecords: document.querySelectorAll('#translationsResults .translation-record-card:not(.notes-skeleton)').length > 0,
        formHidden: Boolean(document.querySelector('#translationsForm')?.hidden),
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim())
      };
    });
    if (!translationsPageState.hasRecords) {
      if (!translationsPageState.formHidden) throw new Error(`empty translations page should hide filter form: ${JSON.stringify(translationsPageState)}`);
      if (translationsPageState.emptyTitle !== 'No translations yet.' || translationsPageState.emptyBodyCount !== 0) {
        throw new Error(`empty translations page should stay quiet: ${JSON.stringify(translationsPageState)}`);
      }
      if (!translationsPageState.emptyActions.includes('Find work') || !translationsPageState.emptyActions.includes('Study')) {
        throw new Error(`empty translations page should keep concise actions: ${JSON.stringify(translationsPageState)}`);
      }
    }
  }
  if (parsed.pathname.startsWith('/work/') && parsed.hash) {
    await page.waitForSelector('.reader-sentence.selected', { timeout: 7000 }).catch(() => {});
    await page.waitForSelector('#translationOutput:not([hidden])', { timeout: 7000 }).catch(() => {});
    const state = await page.evaluate(() => {
      const output = document.querySelector('#translationOutput');
      const card = document.querySelector('.translation-card');
      const activeTab = document.querySelector('.study-tab.active');
      const readingNext = document.querySelector('[data-translation-quick-action="next-sentence"]');
      const visibleExtras = Array.from(document.querySelectorAll('#translationOutput .translation-extra'))
        .filter((node) => window.getComputedStyle(node).display !== 'none');
      return {
        selectedSentence: Boolean(document.querySelector('.reader-sentence.selected')),
        outputVisible: Boolean(output && !output.hidden),
        readingMode: Boolean(output && output.classList.contains('reading-mode')),
        cardReadingMode: Boolean(card && card.classList.contains('reading-mode')),
        cardReviewState: card ? card.dataset.reviewState || '' : '',
        cardBoxShadow: card ? window.getComputedStyle(card).boxShadow : '',
        readingNextVisible: Boolean(readingNext && window.getComputedStyle(readingNext).display !== 'none'),
        readingNextText: readingNext ? readingNext.textContent.trim() : '',
        visibleExtraCount: visibleExtras.length,
        activeTab: activeTab ? activeTab.textContent.trim() : '',
        studyToolsOpen: Boolean(document.querySelector('.translation-utility')?.open)
      };
    });
    if (!state.selectedSentence) throw new Error(`selected work route did not select a sentence: ${JSON.stringify(state)}`);
    if (!state.outputVisible) throw new Error(`selected work route did not show translation output: ${JSON.stringify(state)}`);
    if (!state.readingMode) throw new Error(`translation output did not default to reading mode: ${JSON.stringify(state)}`);
    if (!state.cardReadingMode) throw new Error(`translation card did not default to reading mode: ${JSON.stringify(state)}`);
    if (state.cardReviewState && state.cardBoxShadow !== 'none') {
      throw new Error(`reading mode should suppress review-state card decoration: ${JSON.stringify(state)}`);
    }
    if (!state.readingNextVisible || state.readingNextText !== 'Next sentence') {
      throw new Error(`reading mode should expose only the next sentence flow action: ${JSON.stringify(state)}`);
    }
    if (state.visibleExtraCount !== 0) throw new Error(`reading mode exposed study-only translation extras: ${JSON.stringify(state)}`);
    if (state.activeTab !== 'Translation') throw new Error(`selected work route did not keep Translation tab active: ${JSON.stringify(state)}`);
    if (state.studyToolsOpen) throw new Error(`study tools should stay collapsed in default reading mode: ${JSON.stringify(state)}`);
    await page.click('#study-tab-notes');
    await page.waitForSelector('#study-panel-notes:not([hidden])', { timeout: 5000 });
    const notesState = await page.evaluate(() => ({
      notePlaceholder: document.querySelector('#noteText')?.getAttribute('placeholder') || '',
      noteLabelHidden: Boolean(document.querySelector('#noteText')?.closest('label')?.querySelector('.visually-hidden')),
      saveText: document.querySelector('#noteForm button[type="submit"]')?.textContent.trim() || '',
      saveLabel: document.querySelector('#noteForm button[type="submit"]')?.getAttribute('aria-label') || '',
      tagsSummary: document.querySelector('.note-options summary')?.textContent.trim() || '',
      savedSummary: document.querySelector('.notes-filter-tools summary')?.textContent.trim() || '',
      savedToolsHidden: Boolean(document.querySelector('.notes-filter-tools')?.hidden),
      notesEmptyText: document.querySelector('#notesList .notes-empty')?.textContent.trim() || ''
    }));
    if (notesState.notePlaceholder !== 'Write a note...' || !notesState.noteLabelHidden) {
      throw new Error(`notes tab should keep the editor quiet but accessible: ${JSON.stringify(notesState)}`);
    }
    if (notesState.saveText !== 'Save' || notesState.saveLabel !== 'Save note') {
      throw new Error(`notes tab save control should stay concise: ${JSON.stringify(notesState)}`);
    }
    if (notesState.tagsSummary !== 'Tags') {
      throw new Error(`notes tab details labels should stay concise: ${JSON.stringify(notesState)}`);
    }
    if (notesState.notesEmptyText === 'No notes yet.' && !notesState.savedToolsHidden) {
      throw new Error(`notes tab should hide saved filters when there are no notes: ${JSON.stringify(notesState)}`);
    }
    if (notesState.notesEmptyText !== 'No notes yet.' && notesState.savedSummary !== 'Saved') {
      throw new Error(`notes tab saved filter label should stay concise when notes or filters exist: ${JSON.stringify(notesState)}`);
    }
    await page.click('#study-tab-citation');
    await page.waitForSelector('#study-panel-citation:not([hidden])', { timeout: 5000 });
    await page.click('.citation-copy-options summary');
    await page.waitForSelector('.citation-copy-options[open]', { timeout: 3000 });
    const citationState = await page.evaluate(() => {
      const preview = document.querySelector('#citationPreview');
      const copied = window.citationText ? window.citationText() : '';
      return {
        copyText: document.querySelector('#copyCitation')?.textContent.trim() || '',
        copyLabel: document.querySelector('#copyCitation')?.getAttribute('aria-label') || '',
        moreText: document.querySelector('.citation-copy-options summary')?.textContent.trim() || '',
        previewHasUrl: /https?:\/\//.test(preview?.textContent || ''),
        copiedHasUrl: /https?:\/\//.test(copied),
        urlText: document.querySelector('#copyUrl')?.textContent.trim() || '',
        urlLabel: document.querySelector('#copyUrl')?.getAttribute('aria-label') || '',
        bundleText: document.querySelector('#copySourceBundle')?.textContent.trim() || '',
        bundleLabel: document.querySelector('#copySourceBundle')?.getAttribute('aria-label') || ''
      };
    });
    if (citationState.copyText !== 'Copy' || citationState.copyLabel !== 'Copy citation') {
      throw new Error(`citation tab primary copy control should stay concise: ${JSON.stringify(citationState)}`);
    }
    if (citationState.moreText !== 'More') {
      throw new Error(`citation tab secondary copy summary should stay concise: ${JSON.stringify(citationState)}`);
    }
    if (citationState.previewHasUrl || !citationState.copiedHasUrl) {
      throw new Error(`citation preview should hide URL while copied citation keeps it: ${JSON.stringify(citationState)}`);
    }
    if (citationState.urlText !== 'URL' || citationState.urlLabel !== 'Copy URL' || citationState.bundleText !== 'Source bundle' || citationState.bundleLabel !== 'Copy source bundle') {
      throw new Error(`citation secondary copy controls should stay concise: ${JSON.stringify(citationState)}`);
    }
    await page.click('#study-tab-translation');
    await page.waitForSelector('#study-panel-translation:not([hidden])', { timeout: 5000 });
  }
  if (parsed.pathname === '/translations' && parsed.searchParams.get('review_state') === 'generated') {
    await page.waitForSelector('#translationsResults .translation-record-card, #translationsResults .empty-state', { timeout: 7000 }).catch(() => {});
    const state = await page.evaluate(() => {
      const activeFilters = document.querySelector('#translationsActiveFilters');
      const cards = document.querySelectorAll('#translationsResults .translation-record-card:not(.notes-skeleton)').length;
      return {
        cards,
        toolsOpen: Boolean(document.querySelector('#translationsListTools')?.open),
        activeFiltersHidden: Boolean(activeFilters?.hidden),
        activeFiltersText: activeFilters ? activeFilters.textContent.trim() : ''
      };
    });
    if (state.cards > 0 && state.toolsOpen) throw new Error(`review queue should keep list tools collapsed: ${JSON.stringify(state)}`);
    if (state.cards > 0 && (!state.activeFiltersHidden || state.activeFiltersText)) {
      throw new Error(`review queue should not repeat the status filter chip: ${JSON.stringify(state)}`);
    }
  }
  await page.waitForTimeout(700);
  await page.screenshot({ path: outputPath, fullPage: false });
  await browser.close();
})().catch(async (error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""
    result = subprocess.run(
        [node, "-e", script, url, str(output_path), str(width), str(height), browser],
        cwd=SITE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    stderr = (result.stderr or "").strip()
    require(result.returncode == 0, f"playwright screenshot failed for {url}: {stderr}")
    verify_screenshot(output_path)


def capture_with_native_browser(browser: str, url: str, output_path: Path, width: int, height: int) -> None:
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
            "--run-all-compositor-stages-before-draw",
            "--use-angle=swiftshader",
            "--virtual-time-budget=3000",
            f"--user-data-dir={profile_dir.resolve().as_posix()}",
            f"--window-size={width},{height}",
            f"--screenshot={output_path}",
        ]
        command.append(url)
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
        verify_screenshot(output_path)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def capture(browser: str, playwright_node: str, playwright_node_path: str, url: str, output_path: Path, width: int, height: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    if playwright_node and playwright_node_path:
        capture_with_playwright(playwright_node, playwright_node_path, browser, url, output_path, width, height)
        return
    capture_with_native_browser(browser, url, output_path, width, height)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture local browser screenshots for reader-site visual smoke QA.", allow_abbrev=False)
    parser.add_argument("--browser", default="", help="Path to Edge/Chrome/Chromium. Defaults to common local installs.")
    parser.add_argument("--node", default="", help="Path to Node.js for Playwright screenshots. Defaults to bundled/local node.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Screenshot output directory.")
    parser.add_argument("--html-only", action="store_true", help="Validate routed HTML markers without launching a browser.")
    parser.add_argument("--allow-screenshot-failures", action="store_true", help="Report screenshot failures without failing HTML smoke checks.")
    args = parser.parse_args()

    browser = "" if args.html_only else find_browser(args.browser)
    playwright_node = ""
    playwright_node_path = ""
    if not args.html_only:
        node = find_node(args.node)
        node_path = find_playwright_node_path()
        if playwright_is_available(node, node_path):
            playwright_node = node
            playwright_node_path = node_path
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
        for route_label, route, should_capture in routes:
            url = f"{base_url}{route}"
            html = fetch_html(url)
            require("<html" in html.lower(), f"{route} response does not look like a page")
            require("Personal Archive of Literature" in html or "Archive" in html, f"{route} is missing archive identity text")
            check_route_markup(route, html)
            html_count += 1
            if args.html_only or not should_capture:
                continue
            for viewport_label, width, height in VIEWPORTS:
                output_path = args.output / f"{route_label}-{viewport_label}.png"
                try:
                    capture(browser, playwright_node, playwright_node_path, url, output_path, width, height)
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
