from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
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
VISUAL_NOTE_SEED = {
    "id": "visual-study-note-1",
    "created_at": "2026-06-17T09:00:00",
    "updated_at": "2026-06-17T09:05:00",
    "reviewed_at": "2026-06-17T09:05:00",
    "corpus_id": "nietzsche",
    "work_id": "GM",
    "variant_id": "",
    "target_id": "p-0023.s001",
    "target_type": "sentence",
    "target_label": "Zur Genealogie der Moral §10",
    "quote": "Der Sklavenaufstand in der Moral beginnt damit...",
    "note": "원문을 읽으며 저장한 시각 검증용 노트입니다.",
    "tags": ["시각검증", "계보학"],
    "review_state": "reviewed",
    "url": "/work/nietzsche/GM#p-0023.s001",
}
ROUTES = [
    ("home", "/", True),
    ("nietzsche-category", "/category/nietzsche", True),
    ("bible-category", "/category/bible", True),
    ("kierkegaard-category", "/category/kierkegaard", True),
    ("wittgenstein-category", "/category/wittgenstein", True),
    ("nietzsche-work", "/work/nietzsche/GM", True),
    ("runtime-offline", "/work/nietzsche/GM", True),
    ("nietzsche-work-selected", "/work/nietzsche/GM#p-0023.s001", True),
    ("concept-tab", "/work/nietzsche/GM#p-0023.s001", True),
    ("search", "/search", True),
    ("search-results", "/search?q=ressentiment&corpus_id=nietzsche", True),
    ("concept-search", "/search?q=Genealogie&corpus_id=nietzsche&from=/work/nietzsche/GM%23p-0023.s001&from_label=Zur%20Genealogie%20der%20Moral", True),
    ("search-empty", "/search?q=unlikelyarchivequery0000", True),
    ("notes", "/notes", True),
    ("study", "/study", True),
    ("translations", "/translations", True),
    ("translations-review", "/translations?review_state=generated", True),
]
EMPTY_STATE_ROUTES = [
    ("notes-empty", "/notes", True),
    ("study-empty", "/study", True),
    ("translations-empty", "/translations", True),
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


def seed_visual_notes(notes_dir: Path) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / "nietzsche_notes.jsonl"
    path.write_text(json.dumps(VISUAL_NOTE_SEED, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


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
    if route.startswith("/read?"):
        for needle in [
            "파일 정보</summary>",
            'aria-label="읽기 화면 이동"',
            'href="/">아카이브</a>',
            ">원문</a>",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
        for noisy_text in ["Path</summary>", ">Source</a>", "Reader navigation"]:
            require(noisy_text not in html, f"{route} should avoid static-reader header text {noisy_text!r}")
        for noisy_text in ["javascript:;", 'data-label="Paragraph ', 'aria-label="Paragraph ', 'data-label="Sentence ', 'aria-label="Section link"']:
            require(noisy_text not in html, f"{route} should avoid raw markdown or English paragraph labels {noisy_text!r}")
    if route.startswith("/source?"):
        for needle in [
            "파일 정보</summary>",
            'href="/">아카이브</a>',
            ">본문 보기</a>",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
        for noisy_text in ["Path</summary>", "Reading mode", "Personal Archive of Literature</a>"]:
            require(noisy_text not in html, f"{route} should avoid static source header text {noisy_text!r}")
        require("javascript:;" not in html, f"{route} should avoid inert markdown javascript links")
    if route == "/":
        for needle in [
            "검색",
            "노트",
            "학습",
            "번역",
            "app.js?v=home15",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route == "/study":
        for needle in [
            "studySubmit",
            "studyClear",
            "studyActiveFilters",
            "studyOverview",
            "studyExportTranslations",
            "저장한 번역</a>",
            "studyStatus",
            "aria-busy=\"false\"",
            "study.css?v=study30",
            "study.js?v=study53",
            'href="/study" aria-current="page">학습</a>',
            "studyListTools",
            "저장한 노트 찾기</summary>",
            "filter-panel",
            "조건</summary>",
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
            "notes.css?v=notes28",
            "notes.js?v=notes40",
            'href="/notes" aria-current="page">노트</a>',
            "filter-panel",
            "노트 찾기</summary>",
            "export-tools",
            "내보내기</summary>",
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
            "notes.css?v=notes28",
            "translations.css?v=trans35",
            "translations.js?v=trans86",
            'href="/translations" aria-current="page">번역</a>',
            "번역 찾기",
            "translationsListTools",
            "번역 찾기</summary>",
            "translations-filter-fields",
            "export-tools",
            "내보내기</summary>",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
        require("Filters</summary>" not in html, f"{route} should avoid nested filter disclosures")
    if route.startswith("/search"):
        for needle in [
            "searchSubmit",
            "searchClear",
            "searchActiveFilters",
            "searchStatus",
            "aria-busy=\"false\"",
            "search.css?v=phase32",
            "search.js?v=phase43",
            'href="/search" aria-current="page">검색</a>',
            "번역",
            "filter-panel",
            "검색 범위</summary>",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
    if route.startswith("/work/"):
        for needle in [
            "reading-desk",
            "toolbar-more",
            "읽기 메뉴</summary>",
            'href="#toc">목차</a>',
            "/notes?corpus_id=",
            "/study?corpus_id=",
            "/translations?corpus_id=",
            "원본</a>",
            "study-tabs",
            "study-tab-secondary",
            "citation-copy-options",
            "복사 방식</summary>",
            "studyPanelToggle",
            "studyPanelScrim",
            "study-panel-toggle-action",
            "study-panel-toggle-summary",
            "readingPosition",
            "sentence-context-tools",
            "주변 문장",
            "문맥</summary>",
            "sentenceContext",
            "sentence-more-controls",
            "추가 문장 동작",
            "더보기</summary>",
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
            "태그</summary>",
            "notes-filter-tools",
            "저장한 노트</summary>",
            "noteSort",
            "gemmaRuntimeStatus",
            "번역기 상태",
            "문장을 선택하세요.",
            "translationRecordsSummary",
            'id="translationRecordsSummary" class="translation-records-summary" data-records-state="empty" role="status" aria-live="polite" aria-atomic="true" hidden></div>',
            "studyProgress",
            "진행 확인 중",
            "이어 읽기",
            "translation-export-tools",
            "학습 자료 내보내기",
            "내보내기</summary>",
            "다운로드 링크",
            "exportAllTranslations",
            "전체 번역",
            "exportStudySession",
            "학습 기록",
            "studySessionSummary",
            'id="studySessionSummary" class="study-session-summary" data-session-state="empty" role="status" aria-live="polite" aria-atomic="true" hidden></div>',
            'id="toc"',
            "목차</summary>",
            "translation-output",
            "reader-sentence",
            "reader-work.css?v=common140",
            "reader-work.js?v=common186",
        ]:
            require(needle in html, f"{route} missing visual smoke marker {needle!r}")
        require("Contents (" not in html, f"{route} should not expose TOC inventory counts")
        require("Reader navigation" not in html, f"{route} should use reader-language navigation labels")


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
    require(dark_ratio >= 0.0008, f"screenshot appears to be missing readable text: {path}")


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
const [url, outputPath, widthText, heightText, executablePath] = process.argv.slice(2);
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
  if (parsed.pathname === '/') {
    await page.waitForSelector('#archiveLinks .root-link', { timeout: 5000 }).catch(() => {});
    const homeState = await page.evaluate(() => {
      const section = document.querySelector('#archiveLinks .root-links');
      const heading = section?.querySelector('h2');
      const links = Array.from(section?.querySelectorAll('.root-link') || []);
      const grid = section?.querySelector('.root-link-list');
      const navColumn = document.querySelector('.nav-column');
      const gridStyle = grid ? window.getComputedStyle(grid) : null;
      const firstLinkBox = links[0]?.getBoundingClientRect();
      const navColumnBox = navColumn?.getBoundingClientRect();
      return {
        heading: heading?.textContent.trim() || '',
        label: section?.getAttribute('aria-label') || '',
        linkCount: links.length,
        gridColumns: (gridStyle?.gridTemplateColumns || '').trim().split(/\s+/).filter(Boolean).length,
        navColumnTop: navColumnBox?.top || 0,
        firstLinkHeight: firstLinkBox?.height || 0
      };
    });
    if (homeState.heading !== '읽기 시작' || homeState.label !== '자료 선택') {
      throw new Error(`home should frame root categories as a reading start area: ${JSON.stringify(homeState)}`);
    }
    if (homeState.linkCount !== 4) {
      throw new Error(`home should expose the four root categories: ${JSON.stringify(homeState)}`);
    }
    if (Number(widthText) <= 420 && homeState.firstLinkHeight < 40) {
      throw new Error(`mobile home root links should be easy to tap: ${JSON.stringify(homeState)}`);
    }
    if (Number(widthText) <= 420 && homeState.navColumnTop > 110) {
      throw new Error(`mobile home should not spend the first screen on empty masthead space: ${JSON.stringify(homeState)}`);
    }
    if (Number(widthText) > 420 && homeState.gridColumns < 2) {
      throw new Error(`desktop home root links should scan as a compact grid: ${JSON.stringify(homeState)}`);
    }
    await page.evaluate(() => {
      window.localStorage.setItem('philo.reader.recentWork', JSON.stringify({
        href: '/work/nietzsche/M',
        title: 'Morgenröthe / 아침놀',
        corpus_title: '니체'
      }));
    });
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('.recent-work .recent-work-link', { timeout: 5000 }).catch(() => {});
    const recentWorkState = await page.evaluate(() => {
      const recent = document.querySelector('.recent-work');
      const link = recent?.querySelector('.recent-work-link');
      const label = recent?.querySelector('.recent-work-label');
      const title = recent?.querySelector('.recent-work-title');
      const meta = recent?.querySelector('.recent-work-meta');
      const box = recent?.getBoundingClientRect();
      const linkStyle = link ? window.getComputedStyle(link) : null;
      return {
        exists: Boolean(recent),
        text: recent?.textContent.trim().replace(/\s+/g, ' ') || '',
        linkLabel: link?.getAttribute('aria-label') || '',
        linkColor: linkStyle?.color || '',
        labelText: label?.textContent.trim() || '',
        titleText: title?.textContent.trim() || '',
        metaText: meta?.textContent.trim() || '',
        height: box?.height || 0,
        hasStrong: Boolean(recent?.querySelector('strong'))
      };
    });
    const maxRecentWorkHeight = Number(widthText) <= 420 ? 52 : 44;
    if (!recentWorkState.exists || recentWorkState.hasStrong || recentWorkState.height > maxRecentWorkHeight) {
      throw new Error(`home recent work should stay compact, not card-like: ${JSON.stringify(recentWorkState)}`);
    }
    if (recentWorkState.labelText !== '이어 읽기' || recentWorkState.titleText !== 'Morgenröthe / 아침놀' || recentWorkState.metaText !== '니체') {
      throw new Error(`home recent work should preserve useful reading context: ${JSON.stringify(recentWorkState)}`);
    }
    if (recentWorkState.linkLabel !== '이어 읽기: Morgenröthe / 아침놀') {
      throw new Error(`home recent work should have a clear accessible label: ${JSON.stringify(recentWorkState)}`);
    }
    if (recentWorkState.linkColor === 'rgb(255, 0, 0)' || recentWorkState.linkColor === 'rgb(176, 0, 0)') {
      throw new Error(`home recent work should stay visually secondary to the reading-start choices: ${JSON.stringify(recentWorkState)}`);
    }
  }
  if (parsed.pathname.startsWith('/category/')) {
    await page.waitForSelector('#categoryFilter', { timeout: 5000 }).catch(() => {});
    const initialCategoryToolsState = await page.evaluate(() => {
      const categoryId = decodeURIComponent(window.location.pathname.split('/').filter(Boolean)[1] || '');
      const browseTools = document.querySelector('.category-browse-tools');
      const primary = document.querySelector('.reading-path-link.primary');
      const secondaryRead = document.querySelector('.reading-path-link:not(.primary)');
      const firstWork = document.querySelector('.work-link');
      const primaryStyle = primary ? window.getComputedStyle(primary) : null;
      const secondaryReadStyle = secondaryRead ? window.getComputedStyle(secondaryRead) : null;
      const firstWorkStyle = firstWork ? window.getComputedStyle(firstWork) : null;
      const pageHeaderStyle = window.getComputedStyle(document.querySelector('.page'), '::before');
      const visibleInventoryMeta = Array.from(document.querySelectorAll('.section-meta, .work-meta'))
        .map((node) => node.textContent.trim())
        .filter((text) => /\d[\d,]*\s+(verses?|segments?|files?|works?|tokens?|chapters?)\b/i.test(text));
      return {
        categoryId,
        bodyClass: document.body.className,
        headerPortraitImage: pageHeaderStyle?.backgroundImage || '',
        hasCategoryFilter: Boolean(document.querySelector('#categoryFilter')),
        browseToolsOpen: Boolean(browseTools?.open),
        browseToolsSummary: browseTools?.querySelector('summary')?.textContent.trim() || '',
        primaryReadLink: primary?.textContent.trim() || '',
        primaryReadLabel: primary?.getAttribute('aria-label') || '',
        primaryReadLinkHeight: primary?.getBoundingClientRect().height || 0,
        primaryReadBorderLeftColor: primaryStyle?.borderLeftColor || '',
        secondaryReadText: secondaryRead?.textContent.trim() || '',
        secondaryReadColor: secondaryReadStyle?.color || '',
        firstWorkLinkText: firstWork?.textContent.trim() || '',
        firstWorkLinkHeight: firstWork?.getBoundingClientRect().height || 0,
        firstWorkLinkColor: firstWorkStyle?.color || '',
        visibleInventoryMeta
      };
    });
    if (!initialCategoryToolsState.bodyClass.split(/\s+/).includes(`category-${initialCategoryToolsState.categoryId}`)) {
      throw new Error(`category page should expose its category in the body class for corpus-specific visuals: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.categoryId === 'nietzsche') {
      if (!initialCategoryToolsState.headerPortraitImage.includes('nietzsche-header-left')) {
        throw new Error(`nietzsche category should keep the author portrait: ${JSON.stringify(initialCategoryToolsState)}`);
      }
    } else if (initialCategoryToolsState.headerPortraitImage !== 'none') {
      throw new Error(`non-nietzsche categories should not show the Nietzsche portrait: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.hasCategoryFilter && (initialCategoryToolsState.browseToolsOpen || initialCategoryToolsState.browseToolsSummary !== '작품 찾기')) {
      throw new Error(`category page should keep browse filters collapsed behind a concise label: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    const minimumPrimaryReadHeight = Number(widthText) <= 420 ? 40 : 34;
    if (initialCategoryToolsState.hasCategoryFilter && (!initialCategoryToolsState.primaryReadLink || initialCategoryToolsState.primaryReadLinkHeight < minimumPrimaryReadHeight)) {
      throw new Error(`category page should make the first reading action clear before filters: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.hasCategoryFilter && !initialCategoryToolsState.primaryReadLabel.startsWith('추천 읽기 시작: ')) {
      throw new Error(`category page primary reading action should have a clear accessible label: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (Number(widthText) <= 420 && initialCategoryToolsState.firstWorkLinkText && initialCategoryToolsState.firstWorkLinkHeight < 34) {
      throw new Error(`mobile category work links should remain touch-friendly without becoming card-heavy: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.visibleInventoryMeta.length > 0) {
      throw new Error(`category page should hide inventory-style counts from the reading list: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.hasCategoryFilter && initialCategoryToolsState.primaryReadBorderLeftColor !== 'rgb(176, 0, 0)') {
      throw new Error(`category page should keep the first reading action visually distinct: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.secondaryReadText && (initialCategoryToolsState.secondaryReadColor === 'rgb(255, 0, 0)' || initialCategoryToolsState.secondaryReadColor === 'rgb(176, 0, 0)')) {
      throw new Error(`category secondary reading starts should stay quieter than the primary reading action: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    if (initialCategoryToolsState.firstWorkLinkText && (initialCategoryToolsState.firstWorkLinkColor === 'rgb(255, 0, 0)' || initialCategoryToolsState.firstWorkLinkColor === 'rgb(176, 0, 0)')) {
      throw new Error(`category work lists should scan as reading lists rather than red action lists: ${JSON.stringify(initialCategoryToolsState)}`);
    }
    const hasCategoryFilter = initialCategoryToolsState.hasCategoryFilter;
    if (hasCategoryFilter) {
      await page.evaluate(() => {
        const browseTools = document.querySelector('.category-browse-tools');
        if (browseTools) browseTools.open = true;
      });
      await page.fill('#categoryFilter', 'unlikelyarchivequery0000');
      await page.waitForSelector('[data-category-action="clear-filters"]', { timeout: 5000 }).catch(() => {});
      const emptyCategoryState = await page.evaluate(() => {
        const clear = document.querySelector('[data-category-action="clear-filters"]');
        const browseTools = document.querySelector('.category-browse-tools');
        return {
          emptyText: document.querySelector('.category-empty')?.textContent.trim() || '',
          clearText: clear?.textContent.trim() || '',
          filterValue: document.querySelector('#categoryFilter')?.value || '',
          workLinkCount: document.querySelectorAll('.work-link').length,
          browseToolsOpen: Boolean(browseTools?.open)
        };
      });
      if (emptyCategoryState.clearText !== '필터 지우기' || emptyCategoryState.workLinkCount !== 0 || !emptyCategoryState.browseToolsOpen) {
        throw new Error(`category empty search should offer a clear recovery action: ${JSON.stringify(emptyCategoryState)}`);
      }
      await page.click('[data-category-action="clear-filters"]');
      await page.waitForSelector('.work-link', { timeout: 5000 }).catch(() => {});
      const restoredCategoryState = await page.evaluate(() => {
        return {
          filterValue: document.querySelector('#categoryFilter')?.value || '',
          activeFilterText: document.querySelector('.section-filter.active')?.textContent.trim() || '',
          workLinkCount: document.querySelectorAll('.work-link').length,
          emptyVisible: Boolean(document.querySelector('.category-empty'))
        };
      });
      if (restoredCategoryState.filterValue || restoredCategoryState.activeFilterText !== '전체' || restoredCategoryState.workLinkCount <= 0 || restoredCategoryState.emptyVisible) {
        throw new Error(`category clear recovery should restore the readable work list: ${JSON.stringify(restoredCategoryState)}`);
      }
      await page.evaluate(() => {
        if (document.activeElement && typeof document.activeElement.blur === 'function') {
          document.activeElement.blur();
        }
      });
    }
  }
  if (parsed.pathname.startsWith('/work/')) {
    const readerToolsState = await page.evaluate(() => {
      const details = document.querySelector('.toolbar-more');
      if (details) {
        details.open = true;
      }
      const links = Array.from(details?.querySelectorAll('.toolbar-more-links a') || []);
      const linksContainer = details?.querySelector('.toolbar-more-links');
      const toolbar = document.querySelector('.toolbar');
      const toolbarLinks = Array.from(toolbar?.querySelectorAll(':scope > a') || []);
      const toolbarLinkStyle = toolbarLinks[0] ? window.getComputedStyle(toolbarLinks[0]) : null;
      const summaryNode = details?.querySelector('summary');
      const summaryStyle = summaryNode ? window.getComputedStyle(summaryNode) : null;
      const linksContainerStyle = linksContainer ? window.getComputedStyle(linksContainer) : null;
      const firstLinkStyle = links[0] ? window.getComputedStyle(links[0]) : null;
      const firstLinkBox = links[0]?.getBoundingClientRect();
      const state = {
        summary: summaryNode?.textContent.trim() || '',
        toolbarLinkColor: toolbarLinkStyle?.color || '',
        summaryColor: summaryStyle?.color || '',
        linkText: links.map((node) => node.textContent.trim()).join(' / '),
        linkCount: links.length,
        linksDisplay: linksContainerStyle?.display || '',
        firstLinkDisplay: firstLinkStyle?.display || '',
        firstLinkHeight: firstLinkBox?.height || 0
      };
      if (details) {
        details.open = false;
      }
      return state;
    });
    if (readerToolsState.summary !== '읽기 메뉴') {
      throw new Error(`reader tools menu should use reader-facing wording: ${JSON.stringify(readerToolsState)}`);
    }
    if (readerToolsState.linkText !== '목차 / 원본 / 노트 / 학습 / 번역') {
      throw new Error(`reader tools should prioritize document navigation before study actions: ${JSON.stringify(readerToolsState)}`);
    }
    if (readerToolsState.toolbarLinkColor === 'rgb(255, 0, 0)' || readerToolsState.summaryColor === 'rgb(176, 0, 0)') {
      throw new Error(`reader header navigation should stay visually secondary, not red like source emphasis: ${JSON.stringify(readerToolsState)}`);
    }
    if (readerToolsState.linkCount !== 5 || !['flex', 'inline-flex'].includes(readerToolsState.firstLinkDisplay)) {
      throw new Error(`reader tools menu should expose five readable link targets: ${JSON.stringify(readerToolsState)}`);
    }
    if (Number(widthText) <= 420) {
      if (readerToolsState.linksDisplay !== 'grid' || readerToolsState.firstLinkHeight < 32) {
        throw new Error(`mobile reader tools menu should use touch-friendly grid targets: ${JSON.stringify(readerToolsState)}`);
      }
    } else if (readerToolsState.linksDisplay !== 'flex' || readerToolsState.firstLinkHeight < 24) {
      throw new Error(`desktop reader tools menu should keep readable open targets: ${JSON.stringify(readerToolsState)}`);
    }
    if (!parsed.hash) {
      await page.waitForSelector('#translationOutput:not([hidden])', { timeout: 5000 }).catch(() => {});
      const emptyTranslationState = await page.evaluate(() => {
        const output = document.querySelector('#translationOutput');
        const utility = document.querySelector('.translation-utility');
        const utilityStyle = utility ? window.getComputedStyle(utility) : null;
        return {
          outputHidden: Boolean(output?.hidden),
          emptyCopy: output?.querySelector('.translation-empty-copy')?.textContent.trim() || '',
          utilityHidden: Boolean(utility?.hidden),
          utilityDisplay: utilityStyle?.display || ''
        };
      });
      if (emptyTranslationState.outputHidden || emptyTranslationState.emptyCopy !== '문장을 누르면 번역됩니다.') {
        throw new Error(`empty translation panel should explain the direct click workflow: ${JSON.stringify(emptyTranslationState)}`);
      }
      if (!emptyTranslationState.utilityHidden || emptyTranslationState.utilityDisplay !== 'none') {
        throw new Error(`empty translation panel should hide advanced options until a sentence is selected: ${JSON.stringify(emptyTranslationState)}`);
      }
    }
    if (outputPath.includes('runtime-offline')) {
      const runtimeOfflineState = await page.evaluate(() => {
        const firstSentence = document.querySelector('.reader-sentence');
        if (typeof window.selectSentence === 'function' && firstSentence) {
          window.selectSentence(firstSentence, false);
        }
        if (typeof window.setStudyPanel === 'function') {
          window.setStudyPanel('translation');
        }
        if (typeof window.setStudyPanelExpanded === 'function') {
          window.setStudyPanelExpanded(true);
        }
        if (typeof window.renderTranslationError === 'function') {
          window.renderTranslationError('Gemma runtime is not running');
        }
        const output = document.querySelector('#translationOutput');
        const help = output?.querySelector('.translation-runtime-help');
        const runtimeDetails = help?.querySelector('.translation-runtime-details');
        const runtimeSummary = help?.querySelector(':scope > summary');
        const runtimeCommand = runtimeDetails?.querySelector('.translation-runtime-command');
        const copyButton = output?.querySelector('[data-translation-copy-runtime]');
        const retryButton = output?.querySelector('[data-translation-retry]');
        const checkButton = output?.querySelector('[data-translation-check-runtime]');
        const copyButtonBox = copyButton?.getBoundingClientRect();
        const runtimeCommandBox = runtimeCommand?.getBoundingClientRect();
        const retryButtonBox = retryButton?.getBoundingClientRect();
        const checkButtonBox = checkButton?.getBoundingClientRect();
        const recoveryActions = Array.from(output?.querySelectorAll('.translation-recovery-panel > *') || []).map((node) => node.className || node.tagName.toLowerCase());
        return {
          selectedSentence: Boolean(document.querySelector('.reader-sentence.selected')),
          outputHidden: Boolean(output?.hidden),
          outputText: output?.innerText || '',
          translationHeading: output?.querySelector('.translation-section-primary h3')?.textContent.trim() || '',
          commentaryHeading: output?.querySelector('.translation-commentary h3')?.textContent.trim() || '',
          primaryCopy: output?.querySelector('.translation-section-primary p')?.textContent.trim() || '',
          commentaryCopy: output?.querySelector('.translation-commentary p')?.textContent.trim() || '',
          hasRuntimeHelp: Boolean(help),
          runtimeNote: help?.querySelector('.translation-runtime-note')?.textContent.trim() || '',
          copyButtonText: copyButton?.textContent.trim() || '',
          runtimeSummaryText: runtimeSummary?.textContent.trim() || '',
          runtimeHelpOpen: Boolean(help?.open),
          runtimeCommandText: runtimeCommand?.textContent.trim() || '',
          retryText: retryButton?.textContent.trim() || '',
          retryMode: retryButton?.dataset.translationRetry || '',
          checkText: checkButton?.textContent.trim() || '',
          recoveryActions,
          copyButtonHeight: copyButtonBox?.height || 0,
          runtimeCommandHeight: runtimeCommandBox?.height || 0,
          retryButtonHeight: retryButtonBox?.height || 0,
          checkButtonHeight: checkButtonBox?.height || 0
        };
      });
      if (!runtimeOfflineState.selectedSentence || runtimeOfflineState.outputHidden) {
        throw new Error(`runtime offline fixture should keep a selected source and visible translation panel: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (runtimeOfflineState.translationHeading !== '번역' || runtimeOfflineState.commentaryHeading !== '해설') {
        throw new Error(`runtime offline fixture should keep the reader-facing translation/commentary structure: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (runtimeOfflineState.primaryCopy !== '번역을 사용할 수 없습니다.' || runtimeOfflineState.commentaryCopy !== '번역기를 시작한 뒤 다시 시도하세요.') {
        throw new Error(`runtime offline fixture should explain the recovery in reader language: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (!runtimeOfflineState.hasRuntimeHelp || runtimeOfflineState.runtimeNote !== '시작 명령을 복사해 PowerShell에서 실행하세요.') {
        throw new Error(`runtime offline fixture should keep startup instructions available when expanded: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (runtimeOfflineState.copyButtonText !== '명령 복사' || runtimeOfflineState.runtimeSummaryText !== '번역기 시작' || runtimeOfflineState.runtimeHelpOpen) {
        throw new Error(`runtime offline fixture should keep startup commands collapsed behind a concise label: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (!runtimeOfflineState.runtimeCommandText.includes('run_reader_with_gemma.ps1') || runtimeOfflineState.retryText !== '번역 다시 시도' || runtimeOfflineState.retryMode !== 'translate' || runtimeOfflineState.checkText !== '번역기 확인') {
        throw new Error(`runtime offline fixture should keep copy, retry, and status-check actions available: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (runtimeOfflineState.recoveryActions[0] !== 'translation-error-actions' || runtimeOfflineState.recoveryActions[1] !== 'translation-runtime-help') {
        throw new Error(`runtime offline fixture should prioritize retry and status-check before startup command help: ${JSON.stringify(runtimeOfflineState)}`);
      }
      if (runtimeOfflineState.copyButtonHeight !== 0 || runtimeOfflineState.runtimeCommandHeight !== 0) {
        throw new Error(`runtime offline fixture should keep command-copy controls hidden until startup help is expanded: ${JSON.stringify(runtimeOfflineState)}`);
      }
      for (const noisyText of ['Gemma runtime is not running', '시작 도움말', '복사한 명령을 PowerShell에 붙여넣고 Enter', 'PowerShell에 붙여넣고 Enter', 'source_text_sha256', 'prompt_sha256']) {
        if (runtimeOfflineState.outputText.includes(noisyText)) {
          throw new Error(`runtime offline fixture should hide technical noise ${noisyText}: ${JSON.stringify(runtimeOfflineState)}`);
        }
      }
      if (Number(widthText) <= 420 && [runtimeOfflineState.retryButtonHeight, runtimeOfflineState.checkButtonHeight].some((height) => height < 30)) {
        throw new Error(`runtime offline fixture should keep recovery actions touch-friendly: ${JSON.stringify(runtimeOfflineState)}`);
      }
    }
  }
  if (Number(widthText) <= 420) {
    const mobileAnchorState = await page.evaluate(() => {
      const anchor = document.querySelector('.reading-body .segment-anchor');
      if (!anchor) {
        return null;
      }
      const style = window.getComputedStyle(anchor);
      return {
        text: anchor.textContent.trim(),
        position: style.position,
        opacity: style.opacity,
        marginLeft: style.marginLeft,
        parentTag: anchor.parentElement?.tagName || ''
      };
    });
    if (mobileAnchorState && (mobileAnchorState.position !== 'absolute' || Number.parseFloat(mobileAnchorState.opacity) > 0.05)) {
      throw new Error(`mobile reading anchors should stay out of the default reading flow: ${JSON.stringify(mobileAnchorState)}`);
    }
  }
  if (['/search', '/notes', '/study', '/translations'].includes(parsed.pathname)) {
    const secondaryToolbarTone = await page.evaluate(() => {
      const toolbar = document.querySelector('.toolbar');
      const links = Array.from(toolbar?.querySelectorAll('a') || []);
      return {
        text: links.map((node) => node.textContent.trim()).join(' / '),
        colors: links.map((node) => window.getComputedStyle(node).color)
      };
    });
    if (secondaryToolbarTone.colors.some((color) => color === 'rgb(255, 0, 0)')) {
      throw new Error(`secondary workflow toolbar should stay quiet instead of red: ${JSON.stringify(secondaryToolbarTone)}`);
    }
  }
  if (Number(widthText) <= 420 && ['/search', '/notes', '/study', '/translations'].includes(parsed.pathname)) {
    const toolbarState = await page.evaluate(() => {
      const toolbar = document.querySelector('.toolbar');
      const links = Array.from(toolbar?.querySelectorAll('a') || []);
      const toolbarBox = toolbar?.getBoundingClientRect();
      const firstLinkBox = links[0]?.getBoundingClientRect();
      return {
        text: links.map((node) => node.textContent.trim()).join(' / '),
        linkCount: links.length,
        toolbarHeight: toolbarBox?.height || 0,
        firstLinkHeight: firstLinkBox?.height || 0
      };
    });
    if (toolbarState.linkCount !== 5) {
      throw new Error(`mobile toolbar should keep the five primary destinations: ${JSON.stringify(toolbarState)}`);
    }
    if (toolbarState.firstLinkHeight < 22) {
      throw new Error(`mobile toolbar links should keep a stable tap height: ${JSON.stringify(toolbarState)}`);
    }
    if (toolbarState.toolbarHeight > 56) {
      throw new Error(`mobile toolbar should stay compact above the main workflow: ${JSON.stringify(toolbarState)}`);
    }
  }
  if (Number(widthText) <= 420 && parsed.pathname.startsWith('/work/')) {
    const readerToolbarState = await page.evaluate(() => {
      const toolbar = document.querySelector('.toolbar');
      const firstLink = toolbar?.querySelector('a');
      const workspace = toolbar?.querySelector('.toolbar-more summary');
      const toolbarBox = toolbar?.getBoundingClientRect();
      const firstLinkBox = firstLink?.getBoundingClientRect();
      const workspaceBox = workspace?.getBoundingClientRect();
      return {
        text: toolbar?.textContent.trim().replace(/\s+/g, ' ') || '',
        toolbarHeight: toolbarBox?.height || 0,
        firstLinkHeight: firstLinkBox?.height || 0,
        workspaceHeight: workspaceBox?.height || 0,
        workspaceRowOffset: Math.abs((workspaceBox?.top || 0) - (firstLinkBox?.top || 0))
      };
    });
    if (readerToolbarState.workspaceHeight < 22 || readerToolbarState.firstLinkHeight < 22) {
      throw new Error(`mobile reader toolbar links should keep stable tap height: ${JSON.stringify(readerToolbarState)}`);
    }
    if (readerToolbarState.workspaceRowOffset > 4) {
      throw new Error(`closed Workspace should stay on the primary mobile toolbar row: ${JSON.stringify(readerToolbarState)}`);
    }
    if (readerToolbarState.toolbarHeight > 32) {
      throw new Error(`mobile reader toolbar should stay compact above the text: ${JSON.stringify(readerToolbarState)}`);
    }
  }
  if (parsed.pathname === '/search' && parsed.searchParams.get('q')) {
    await page.waitForSelector('.result:not(.search-skeleton), .empty-state', { timeout: 5000 }).catch(() => {});
    const searchPageState = await page.evaluate(() => {
      const empty = document.querySelector('#results .empty-state');
      const firstNoteSourceRead = document.querySelector('#results .note-result .result-action-read');
      const searchReturn = document.querySelector('#searchReturn');
      const searchReturnLink = searchReturn?.querySelector('a');
      return {
        statusText: document.querySelector('#searchStatus')?.textContent.trim() || '',
        hasResults: document.querySelectorAll('#results .result:not(.search-skeleton)').length > 0,
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyBodyText: Array.from(empty?.querySelectorAll('p') || []).map((node) => node.textContent.trim()).join(' '),
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim()),
        emptyActionHrefs: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.getAttribute('href') || ''),
        emptyButtonActions: Array.from(empty?.querySelectorAll('.empty-actions button') || []).map((node) => node.textContent.trim()),
        emptyBorderLeftColor: empty ? window.getComputedStyle(empty).borderLeftColor : '',
        emptyArchiveLinkColor: empty?.querySelector('.empty-actions a') ? window.getComputedStyle(empty.querySelector('.empty-actions a')).color : '',
        actionText: Array.from(document.querySelectorAll('#results .result-actions')).map((node) => node.textContent.trim()).join(' '),
        activeFilterText: document.querySelector('#searchActiveFilters')?.textContent.trim() || '',
        activeFilterLabel: document.querySelector('#searchActiveFilters')?.getAttribute('aria-label') || '',
        returnHidden: Boolean(searchReturn?.hidden),
        returnText: searchReturn?.textContent.trim().replace(/\s+/g, ' ') || '',
        returnHref: searchReturnLink?.getAttribute('href') || '',
        returnLabel: searchReturnLink?.getAttribute('aria-label') || '',
        filterChipHeights: Array.from(document.querySelectorAll('#searchActiveFilters .filter-chip')).map((node) => Math.round(node.getBoundingClientRect().height)),
        filterChipCloseText: Array.from(document.querySelectorAll('#searchActiveFilters .filter-chip span[aria-hidden="true"]')).map((node) => node.textContent.trim()).join(''),
        summaryLinkTexts: Array.from(document.querySelectorAll('#results .result-summary-link')).map((node) => node.textContent.trim()),
        summaryLinkLabels: Array.from(document.querySelectorAll('#results .result-summary-link')).map((node) => node.getAttribute('aria-label') || ''),
        markBackgroundColor: document.querySelector('#results mark') ? window.getComputedStyle(document.querySelector('#results mark')).backgroundColor : '',
        markBoxShadow: document.querySelector('#results mark') ? window.getComputedStyle(document.querySelector('#results mark')).boxShadow : '',
        resultMetaText: Array.from(document.querySelectorAll('#results .result-meta')).map((node) => node.textContent.trim()).join(' '),
        moreActionCount: document.querySelectorAll('#results .result-more-actions').length,
        inlineActionCount: document.querySelectorAll('#results .result-actions-inline').length,
        workSegmentReadActionCount: document.querySelectorAll('#results .work-result .result-action-read, #results .segment-result .result-action-read').length,
        readableTitleCount: document.querySelectorAll('#results .work-result .result-title > a[aria-label^="읽기:"], #results .segment-result .result-title > a[aria-label^="읽기:"]').length,
        readableSnippetCount: document.querySelectorAll('#results .work-result .snippet-link[aria-label^="읽기:"], #results .segment-result .snippet-link[aria-label^="읽기:"]').length,
        noteSourceReadCount: document.querySelectorAll('#results .note-result .result-action-read').length,
        firstNoteSourceReadText: firstNoteSourceRead?.textContent.trim() || '',
        firstNoteSourceReadLabel: firstNoteSourceRead?.getAttribute('aria-label') || '',
        firstNoteSourceReadBorderColor: window.getComputedStyle(firstNoteSourceRead || document.body).borderColor,
        resultKindCount: document.querySelectorAll('#results .result-kind').length,
        groupCountText: Array.from(document.querySelectorAll('#results .result-group-count')).map((node) => node.textContent.trim()).join(' ')
      };
    });
    if (searchPageState.statusText) {
      throw new Error(`search status should not duplicate rendered results: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.activeFilterText && !searchPageState.activeFilterText.startsWith('조건')) {
      throw new Error(`search active filters should read as applied conditions: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.activeFilterText && searchPageState.activeFilterLabel !== '활성 검색 조건') {
      throw new Error(`search active filters should expose condition wording accessibly: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.activeFilterText && (searchPageState.filterChipHeights.some((height) => height < 28) || !searchPageState.filterChipCloseText.includes('×'))) {
      throw new Error(`search filter chips should be easy to remove on touch screens: ${JSON.stringify(searchPageState)}`);
    }
    if (outputPath.includes('concept-search')) {
      if (searchPageState.returnHidden || searchPageState.returnHref !== '/work/nietzsche/GM#p-0023.s001' || !searchPageState.returnText.includes('읽던 문서로 돌아가기') || !searchPageState.returnLabel.startsWith('읽던 문서로 돌아가기:')) {
        throw new Error(`concept search should offer a quiet return to the source text: ${JSON.stringify(searchPageState)}`);
      }
    } else if (!searchPageState.returnHidden || searchPageState.returnText) {
      throw new Error(`ordinary search should not show a return-to-source link: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && searchPageState.emptyTitle !== '검색 결과가 없습니다.') {
      throw new Error(`empty search should use a concise title: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && /notes|saved notes/i.test(searchPageState.emptyBodyText)) {
      throw new Error(`empty search should not send users to a duplicate notes search: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && (searchPageState.emptyActions.length !== 1 || searchPageState.emptyActions[0] !== '읽기 시작')) {
      throw new Error(`empty search should keep only the reading-start recovery action: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && searchPageState.emptyActionHrefs[0] !== '/') {
      throw new Error(`empty search reading-start action should return to the archive home: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && !searchPageState.emptyButtonActions.includes('검색 지우기')) {
      throw new Error(`empty search should keep the clear action available: ${JSON.stringify(searchPageState)}`);
    }
    if (!searchPageState.hasResults && (searchPageState.emptyBorderLeftColor === 'rgb(176, 0, 0)' || searchPageState.emptyArchiveLinkColor === 'rgb(176, 0, 0)')) {
      throw new Error(`empty search should keep secondary empty-state cues visually quiet: ${JSON.stringify(searchPageState)}`);
    }
    if (/Open work|Open source|Open target|Manage note/.test(searchPageState.actionText)) {
      throw new Error(`search result actions should not repeat title-link navigation: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.moreActionCount > 0) {
      throw new Error(`single search result actions should be visible without More: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.workSegmentReadActionCount > 0) {
      throw new Error(`work and segment search cards should not repeat title-link navigation with footer Read actions: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.readableTitleCount === 0 && searchPageState.noteSourceReadCount === 0) {
      throw new Error(`search results should expose readable destinations through links or note source actions: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.readableTitleCount > 0 && searchPageState.readableSnippetCount === 0) {
      throw new Error(`work and segment snippets should carry the same reading destination label as titles: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && (searchPageState.markBackgroundColor === 'rgb(255, 243, 163)' || !searchPageState.markBoxShadow.includes('rgb(216, 197, 109)'))) {
      throw new Error(`search highlights should stay visible without feeling like heavy highlighter blocks: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && /노트/.test(searchPageState.actionText)) {
      throw new Error(`search result actions should keep repeated Notes links out of the result list: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.noteSourceReadCount > 0 && searchPageState.firstNoteSourceReadText !== '원문 읽기') {
      throw new Error(`note search result source action should be labeled 원문 읽기: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.noteSourceReadCount > 0 && !searchPageState.firstNoteSourceReadLabel.startsWith('읽기:')) {
      throw new Error(`note search result source action should expose its reading target accessibly: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.noteSourceReadCount > 0 && searchPageState.firstNoteSourceReadBorderColor !== 'rgb(176, 0, 0)') {
      throw new Error(`note source Read action should use the archive primary color: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.groupCountText) {
      throw new Error(`search result group headers should not repeat count summaries: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.summaryLinkTexts.some((text) => /\d/.test(text))) {
      throw new Error(`search result summary should hide visible counts from the reading flow: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.summaryLinkLabels.some((label) => label && !/\d/.test(label))) {
      throw new Error(`search result summary should keep counts in accessible labels: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.resultKindCount > 0) {
      throw new Error(`search result cards should avoid repeated group labels inside each card: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && /\b(Paragraph|Section|Verse|Quote|Line)\s+\d+/i.test(searchPageState.resultMetaText)) {
      throw new Error(`search result metadata should use reader-language position labels: ${JSON.stringify(searchPageState)}`);
    }
    if (searchPageState.hasResults && searchPageState.activeFilterText.includes('자료: 니체') && /\b니체\b/.test(searchPageState.resultMetaText)) {
      throw new Error(`search results should not repeat corpus metadata already shown in filters: ${JSON.stringify(searchPageState)}`);
    }
  }
  if (parsed.pathname === '/search' && !parsed.search) {
    await page.waitForSelector('#results .search-start', { timeout: 5000 }).catch(() => {});
    const searchStartState = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('#results .search-start-links a'));
      const section = document.querySelector('#results .search-start');
      const heading = section?.querySelector('h2');
      const grid = document.querySelector('#results .search-start-links');
      const reader = document.querySelector('.reader');
      const gridStyle = grid ? window.getComputedStyle(grid) : null;
      const firstLinkBox = links[0]?.getBoundingClientRect();
      const readerBox = reader?.getBoundingClientRect();
      return {
        heading: heading?.textContent.trim() || '',
        label: section?.getAttribute('aria-label') || '',
        linkText: links.map((node) => node.textContent.trim()).join(' / '),
        linkCount: links.length,
        gridColumns: (gridStyle?.gridTemplateColumns || '').trim().split(/\s+/).filter(Boolean).length,
        readerTop: readerBox?.top || 0,
        firstLinkHeight: firstLinkBox?.height || 0
      };
    });
    if (searchStartState.heading !== '읽기 시작' || searchStartState.label !== '자료 선택') {
      throw new Error(`search start should invite users into reading, not generic browsing: ${JSON.stringify(searchStartState)}`);
    }
    if (searchStartState.linkCount !== 4) {
      throw new Error(`search start should expose the four root categories: ${JSON.stringify(searchStartState)}`);
    }
    if (Number(widthText) <= 420 && searchStartState.gridColumns !== 2) {
      throw new Error(`mobile search start should use a two-column browse grid: ${JSON.stringify(searchStartState)}`);
    }
    if (Number(widthText) <= 420 && searchStartState.firstLinkHeight < 40) {
      throw new Error(`mobile search start category links should be easy to tap: ${JSON.stringify(searchStartState)}`);
    }
    if (Number(widthText) <= 420 && searchStartState.readerTop > 110) {
      throw new Error(`mobile search should not spend the first screen on empty masthead space: ${JSON.stringify(searchStartState)}`);
    }
  }
  if (parsed.pathname === '/notes' && !parsed.search) {
    await page.waitForSelector('#notesResults .note-card:not(.notes-skeleton), #notesResults .empty-state', { timeout: 7000 }).catch(() => {});
    const notesPageState = await page.evaluate(() => {
      const empty = document.querySelector('#notesResults .empty-state');
      const emptyStyle = empty ? window.getComputedStyle(empty) : null;
      const results = document.querySelector('#notesResults');
      const exportTools = document.querySelector('#notesExportTools');
      return {
        hasNotes: document.querySelectorAll('#notesResults .note-card:not(.notes-skeleton)').length > 0,
        formHidden: Boolean(document.querySelector('#notesForm')?.hidden),
        exportAfterResults: Boolean(results && exportTools && (results.compareDocumentPosition(exportTools) & Node.DOCUMENT_POSITION_FOLLOWING)),
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyBorderLeftColor: emptyStyle?.borderLeftColor || '',
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim()),
        emptyActionHrefs: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.getAttribute('href') || ''),
        exportLabels: Array.from(document.querySelectorAll('#notesExportTools .export-row a:not([hidden])')).map((node) => node.textContent.trim()),
        jsonlHidden: Boolean(document.querySelector('#exportJsonl')?.hidden),
        reviewOptions: Array.from(document.querySelectorAll('#notesReview option')).map((node) => node.textContent.trim()),
        summaryButtons: Array.from(document.querySelectorAll('#notesResults .notes-summary-filter')).map((node) => node.textContent.trim()),
        summaryLabels: Array.from(document.querySelectorAll('#notesResults .notes-summary-filter')).map((node) => node.getAttribute('aria-label') || ''),
        actionText: Array.from(document.querySelectorAll('#notesResults .note-actions')).map((node) => node.textContent.trim()).join(' '),
        immediateActionText: Array.from(document.querySelectorAll('#notesResults .note-actions > a, #notesResults .note-actions > button, #notesResults .note-actions > details > summary')).map((node) => node.textContent.trim()).join(' '),
        moreActionSummaries: Array.from(document.querySelectorAll('#notesResults .note-more-actions > summary')).map((node) => node.textContent.trim()),
        openMoreActions: document.querySelectorAll('#notesResults .note-more-actions[open]').length,
        sourceActionLabels: Array.from(document.querySelectorAll('#notesResults .note-actions a')).map((node) => node.getAttribute('aria-label') || ''),
      };
    });
    if (!notesPageState.exportAfterResults) {
      throw new Error(`notes export tools should stay after the note results: ${JSON.stringify(notesPageState)}`);
    }
    for (const expectedNoteState of ['작성 중인 노트', '저장한 노트']) {
      if (!notesPageState.reviewOptions.includes(expectedNoteState)) {
        throw new Error(`notes status filter should use learner-facing labels: ${JSON.stringify(notesPageState)}`);
      }
    }
    if (notesPageState.exportLabels.join(' / ') !== '읽기용 / 데이터' || !notesPageState.jsonlHidden) {
      throw new Error(`notes export controls should expose reader-purpose labels and hide JSONL by default: ${JSON.stringify(notesPageState)}`);
    }
    if (!notesPageState.hasNotes) {
      if (!notesPageState.formHidden) throw new Error(`empty notes page should hide filter form: ${JSON.stringify(notesPageState)}`);
      if (notesPageState.emptyTitle !== '아직 노트가 없습니다.' || notesPageState.emptyBodyCount !== 0) {
        throw new Error(`empty notes page should stay quiet: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.emptyBorderLeftColor === 'rgb(176, 0, 0)') {
        throw new Error(`empty notes page should not look like a warning state: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.emptyActions.length !== 1 || notesPageState.emptyActions[0] !== '읽기 시작') {
        throw new Error(`empty notes page should keep only the find action: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.emptyActionHrefs[0] !== '/') {
        throw new Error(`empty notes page reading-start action should return to the archive home: ${JSON.stringify(notesPageState)}`);
      }
    } else {
      if (/Open target|Open work|Manage note|Edit note|다시 열기|저장 완료/.test(notesPageState.actionText)) {
        throw new Error(`notes page actions should stay concise and unambiguous: ${notesPageState.actionText}`);
      }
      if (!notesPageState.actionText.includes('원문 읽기')) {
        throw new Error(`notes page should expose a clear source navigation action: ${JSON.stringify(notesPageState)}`);
      }
      if (!notesPageState.immediateActionText.includes('원문 읽기') || !notesPageState.immediateActionText.includes('수정') || !notesPageState.immediateActionText.includes('더보기')) {
        throw new Error(`notes page should keep source, edit, and more as the immediate actions: ${JSON.stringify(notesPageState)}`);
      }
      if (/작성 중으로|삭제|삭제 확인|저장($|\s)/.test(notesPageState.immediateActionText)) {
        throw new Error(`notes page should move state changes and deletion behind More: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.openMoreActions !== 0 || notesPageState.moreActionSummaries.some((text) => text !== '더보기')) {
        throw new Error(`notes page should keep low-frequency actions collapsed behind 더보기: ${JSON.stringify(notesPageState)}`);
      }
      const notesMoreState = await page.evaluate(() => {
        const details = document.querySelector('#notesResults .note-more-actions');
        const summary = details?.querySelector(':scope > summary');
        if (!details || !summary) return { exists: false };
        summary.click();
        const state = {
          exists: true,
          open: Boolean(details.open),
          summaryText: summary.textContent.trim(),
          reviewActionText: details.querySelector('button[data-action="mark-raw"], button[data-action="mark-reviewed"]')?.textContent.trim() || '',
          dangerSummaryText: details.querySelector('.note-danger-actions > summary')?.textContent.trim() || '',
          deleteActionText: details.querySelector('button[data-action="delete"]')?.textContent.trim() || '',
        };
        details.open = false;
        return state;
      });
      if (!notesMoreState.exists || !notesMoreState.open || notesMoreState.summaryText !== '더보기') {
        throw new Error(`notes page should open low-frequency note actions from 더보기: ${JSON.stringify(notesMoreState)}`);
      }
      if (!/^(저장|작성 중으로)$/.test(notesMoreState.reviewActionText) || notesMoreState.dangerSummaryText !== '삭제' || notesMoreState.deleteActionText !== '삭제 확인') {
        throw new Error(`notes page More disclosure should contain review state and deletion actions: ${JSON.stringify(notesMoreState)}`);
      }
      if (notesPageState.sourceActionLabels.some((label) => label && !label.startsWith('원문 읽기: '))) {
        throw new Error(`notes source links should include their target in accessible labels: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.summaryButtons.some((text) => text.includes('저장됨') || text === '작성 중')) {
        throw new Error(`notes status summary should use learner-facing labels: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.summaryButtons.some((text) => /\d/.test(text))) {
        throw new Error(`notes status summary should hide visible counts from the reading flow: ${JSON.stringify(notesPageState)}`);
      }
      if (notesPageState.summaryLabels.some((label) => label && !/\d/.test(label))) {
        throw new Error(`notes status summary should keep counts in accessible labels: ${JSON.stringify(notesPageState)}`);
      }
      const notesDangerText = await page.evaluate(() => Array.from(document.querySelectorAll('#notesResults .note-danger-actions summary')).map((node) => node.textContent.trim()).join(' '));
      if (notesDangerText.includes('More')) {
        throw new Error(`notes danger action should be explicit, not hidden behind More: ${notesDangerText}`);
      }
    }
  }
  if (parsed.pathname === '/study' && !parsed.search) {
    await page.waitForSelector('#studyResults .study-group:not(.study-skeleton), #studyResults .empty-state', { timeout: 7000 }).catch(() => {});
    const studyPageState = await page.evaluate(() => {
      const empty = document.querySelector('#studyResults .empty-state');
      const overviewPrimary = document.querySelector('#studyOverview .study-overview-primary');
      const listTools = document.querySelector('#studyListTools');
      const results = document.querySelector('#studyResults');
      const exportTools = document.querySelector('#studyExportTools');
      return {
        hasGroups: document.querySelectorAll('#studyResults .study-group:not(.study-skeleton)').length > 0,
        formHidden: Boolean(document.querySelector('#studyForm')?.hidden),
        listToolsHidden: Boolean(listTools?.hidden),
        listToolsOpen: Boolean(listTools?.open),
        listToolsSummary: listTools?.querySelector('summary')?.textContent.trim() || '',
        exportAfterResults: Boolean(results && exportTools && (results.compareDocumentPosition(exportTools) & Node.DOCUMENT_POSITION_FOLLOWING)),
        overviewHidden: Boolean(document.querySelector('#studyOverview')?.hidden),
        overviewText: document.querySelector('#studyOverview')?.textContent.trim() || '',
        overviewPrimaryText: overviewPrimary?.textContent.trim() || '',
        overviewPrimaryLabel: overviewPrimary?.getAttribute('aria-label') || '',
        overviewPrimaryBorderColor: overviewPrimary ? window.getComputedStyle(overviewPrimary).borderColor : '',
        overviewLinkTexts: Array.from(document.querySelectorAll('#studyOverview .study-overview-translations a')).map((node) => node.textContent.trim()),
        overviewLinkLabels: Array.from(document.querySelectorAll('#studyOverview .study-overview-translations a')).map((node) => node.getAttribute('aria-label') || ''),
        firstGroupMeta: document.querySelector('#studyResults .study-group:first-of-type .group-meta')?.textContent.trim() || '',
        firstGroupActions: Array.from(document.querySelectorAll('#studyResults .study-group:first-of-type .group-actions a')).map((node) => node.textContent.trim()),
        firstGroupActionLabels: Array.from(document.querySelectorAll('#studyResults .study-group:first-of-type .group-actions a')).map((node) => node.getAttribute('aria-label') || ''),
        firstNoteActions: Array.from(document.querySelectorAll('#studyResults .study-group:first-of-type .study-note:first-of-type .note-actions a')).map((node) => node.textContent.trim()),
        firstNoteActionLabels: Array.from(document.querySelectorAll('#studyResults .study-group:first-of-type .study-note:first-of-type .note-actions a')).map((node) => node.getAttribute('aria-label') || ''),
        emptyTitle: empty?.querySelector('h2')?.textContent.trim() || '',
        emptyBodyCount: empty ? empty.querySelectorAll('p').length : 0,
        emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim()),
        emptyActionHrefs: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.getAttribute('href') || ''),
        primaryAction: empty?.querySelector('.empty-primary-action')?.textContent.trim() || '',
        primaryActionLabel: empty?.querySelector('.empty-primary-action')?.getAttribute('aria-label') || '',
        primaryActionTitle: empty?.querySelector('.empty-primary-action')?.getAttribute('title') || '',
        emptyBorderLeftColor: empty ? window.getComputedStyle(empty).borderLeftColor : '',
        findActionColor: empty?.querySelector('.empty-actions a:not(.empty-primary-action)') ? window.getComputedStyle(empty.querySelector('.empty-actions a:not(.empty-primary-action)')).color : ''
      };
    });
    if (!studyPageState.exportAfterResults) {
      throw new Error(`study export tools should stay after the learning results: ${JSON.stringify(studyPageState)}`);
    }
    if (!studyPageState.hasGroups) {
      if (!studyPageState.formHidden) throw new Error(`empty study page should hide filter form: ${JSON.stringify(studyPageState)}`);
      if (!studyPageState.listToolsHidden) throw new Error(`empty study page should hide saved-note filter tools: ${JSON.stringify(studyPageState)}`);
      const hasReviewAction = studyPageState.primaryAction === '검토하기';
      const hasSavedTranslationAction = studyPageState.primaryAction === '번역 보기';
      const expectedTitle = hasReviewAction
        ? '검토할 번역이 있습니다.'
        : (hasSavedTranslationAction ? '저장한 번역이 있습니다.' : '아직 저장한 노트가 없습니다.');
      if (studyPageState.emptyTitle !== expectedTitle || studyPageState.emptyBodyCount !== 0) {
        throw new Error(`empty study page should stay quiet: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.emptyActions.includes('노트')) {
        throw new Error(`empty study page should not send users to an empty notes list: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.emptyActions.includes('읽기 시작')) {
        throw new Error(`empty study page should keep a clear find action: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.emptyActionHrefs.includes('/')) {
        throw new Error(`empty study page reading-start action should return to the archive home: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.emptyBorderLeftColor === 'rgb(176, 0, 0)' || studyPageState.findActionColor === 'rgb(176, 0, 0)') {
        throw new Error(`empty study page should keep secondary empty-state cues visually quiet: ${JSON.stringify(studyPageState)}`);
      }
      if (!hasReviewAction && !hasSavedTranslationAction && studyPageState.emptyActions.length !== 1) {
        throw new Error(`empty study page should keep only the find action when there is nothing to review: ${JSON.stringify(studyPageState)}`);
      }
      if ((hasReviewAction || hasSavedTranslationAction) && !studyPageState.primaryAction) {
        throw new Error(`empty study page should make translation study the primary empty action: ${JSON.stringify(studyPageState)}`);
      }
      if (hasReviewAction && !/^검토할 번역 .*개로 이동$/.test(studyPageState.primaryActionLabel)) {
        throw new Error(`empty study page should keep review counts in the accessible label: ${JSON.stringify(studyPageState)}`);
      }
      if (hasSavedTranslationAction && !/^저장한 번역 .*개 보기$/.test(studyPageState.primaryActionLabel)) {
        throw new Error(`empty study page should keep saved translation counts in the accessible label: ${JSON.stringify(studyPageState)}`);
      }
      if (hasReviewAction && studyPageState.primaryActionTitle !== studyPageState.primaryActionLabel) {
        throw new Error(`empty study page should expose the same review count in the title: ${JSON.stringify(studyPageState)}`);
      }
      if ((hasReviewAction || hasSavedTranslationAction) && !studyPageState.overviewHidden) {
        throw new Error(`empty study page should keep translation status inside the empty card, not a separate overview: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.overviewText.includes('저장한 노트 0개')) {
        throw new Error(`empty study page overview should not repeat zero notes: ${JSON.stringify(studyPageState)}`);
      }
    } else {
      if (studyPageState.overviewHidden || studyPageState.overviewPrimaryText !== '이어 읽기') {
        throw new Error(`study page should expose a clear continue-reading action above saved notes: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.listToolsHidden || studyPageState.listToolsOpen || studyPageState.listToolsSummary !== '저장한 노트 찾기') {
        throw new Error(`study page should keep saved-note filters collapsed behind a concise summary when records exist: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.overviewPrimaryLabel.startsWith('이어 읽기: ')) {
        throw new Error(`study continue action should keep the target title in its accessible label: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.overviewPrimaryBorderColor !== 'rgb(176, 0, 0)') {
        throw new Error(`study continue action should use the same red primary action style: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.firstGroupActions.includes('이어 읽기')) {
        throw new Error(`study note groups should offer a clear continue-reading action: ${JSON.stringify(studyPageState)}`);
      }
      if (/\d+개\s+저장/.test(`${studyPageState.overviewText} ${studyPageState.firstGroupMeta}`) || !`${studyPageState.overviewText} ${studyPageState.firstGroupMeta}`.includes('저장한 노트')) {
        throw new Error(`study note counts should read naturally in Korean: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.firstGroupActions.includes('노트 보기') || studyPageState.firstGroupActions.includes('노트')) {
        throw new Error(`study note groups should make note-list navigation explicit: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.firstGroupActionLabels.some((label) => label && !/^(이어 읽기|노트 보기):\s+/.test(label))) {
        throw new Error(`study group actions should include readable targets in accessible labels: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.firstNoteActions.includes('원문 읽기')) {
        throw new Error(`study note actions should expose a clear source navigation action: ${JSON.stringify(studyPageState)}`);
      }
      if (!studyPageState.firstNoteActions.includes('노트 수정') || studyPageState.firstNoteActions.includes('수정')) {
        throw new Error(`study note actions should name note editing explicitly: ${JSON.stringify(studyPageState)}`);
      }
      if (studyPageState.firstNoteActionLabels.some((label) => label && !/^(원문 읽기|노트 수정):\s+/.test(label))) {
        throw new Error(`study note links should include their target in accessible labels: ${JSON.stringify(studyPageState)}`);
      }
    }
    if (studyPageState.overviewText.includes('제외')) {
      throw new Error(`study overview should keep discarded translations out of the learning entry point: ${JSON.stringify(studyPageState)}`);
    }
    if (!studyPageState.overviewHidden && studyPageState.overviewLinkTexts.some((text) => /\d/.test(text) || text === '번역 검토')) {
      throw new Error(`study overview translation links should show action labels without visible counts: ${JSON.stringify(studyPageState)}`);
    }
    if (!studyPageState.overviewHidden && studyPageState.overviewLinkLabels.some((label) => label && !/\d/.test(label))) {
      throw new Error(`study overview translation link labels should retain count details accessibly: ${JSON.stringify(studyPageState)}`);
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
          emptyActions: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.textContent.trim()),
          emptyActionHrefs: Array.from(empty?.querySelectorAll('.empty-actions a') || []).map((node) => node.getAttribute('href') || ''),
          reviewBadgeCount: document.querySelectorAll('#translationsResults .review-badge').length,
          summaryButtons: Array.from(document.querySelectorAll('#translationsResults .translation-record-summary [data-translation-summary-filter]')).map((node) => node.textContent.trim()),
          summaryLabels: Array.from(document.querySelectorAll('#translationsResults .translation-record-summary [data-translation-summary-filter]')).map((node) => node.getAttribute('aria-label') || ''),
          sourceDisclosureCount: document.querySelectorAll('#translationsResults .translation-source').length,
          commentaryDetailsCount: document.querySelectorAll('#translationsResults .translation-commentary').length,
          openCommentaryCount: document.querySelectorAll('#translationsResults .translation-commentary[open]').length,
          commentarySummaryTexts: Array.from(document.querySelectorAll('#translationsResults .translation-commentary summary')).map((node) => node.textContent.trim()),
          groupTitleCount: document.querySelectorAll('#translationsResults .translation-record-group-title').length,
          firstGroupTitle: document.querySelector('#translationsResults .translation-record-group-title')?.textContent.trim() || '',
          reviewQueueBorderColor: window.getComputedStyle(document.querySelector('#translationsReviewQueue')).borderColor,
          reviewQueueColor: window.getComputedStyle(document.querySelector('#translationsReviewQueue')).color,
          reviewQueueBackgroundColor: window.getComputedStyle(document.querySelector('#translationsReviewQueue')).backgroundColor,
          firstRecordTitle: document.querySelector('#translationsResults .translation-record-card .translation-record-title')?.textContent.trim() || '',
          firstGroupActions: Array.from(document.querySelectorAll('#translationsResults .translation-record-group:first-of-type .translation-record-group-actions a')).map((node) => node.textContent.trim()),
          firstGroupActionLabels: Array.from(document.querySelectorAll('#translationsResults .translation-record-group:first-of-type .translation-record-group-actions a')).map((node) => node.getAttribute('aria-label') || ''),
          headingText: document.querySelector('#translationsPageTitle')?.textContent.trim() || '',
          documentTitle: document.title,
          reviewQueueText: document.querySelector('#translationsReviewQueue')?.textContent.trim() || '',
          reviewQueueLabel: document.querySelector('#translationsReviewQueue')?.getAttribute('aria-label') || '',
          exportLabels: Array.from(document.querySelectorAll('#translationsExportTools .export-row a')).map((node) => node.textContent.trim()),
          corpusOptions: Array.from(document.querySelectorAll('#translationsCorpus option')).map((node) => node.textContent.trim())
        };
    });
    for (const expectedCorpusLabel of ['니체', '성경', '키르케고르', '비트겐슈타인']) {
      if (!translationsPageState.corpusOptions.includes(expectedCorpusLabel)) {
        throw new Error(`translations corpus filter should use consistent Korean archive labels: ${JSON.stringify(translationsPageState)}`);
      }
    }
    if (translationsPageState.exportLabels.join(' / ') !== '읽기용 / 데이터') {
      throw new Error(`translations export controls should expose reader-purpose labels: ${JSON.stringify(translationsPageState)}`);
    }
    if (!translationsPageState.hasRecords) {
      if (!translationsPageState.formHidden) throw new Error(`empty translations page should hide filter form: ${JSON.stringify(translationsPageState)}`);
      if (translationsPageState.emptyTitle !== '아직 번역이 없습니다.' || translationsPageState.emptyBodyCount !== 0) {
        throw new Error(`empty translations page should stay quiet: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.emptyActions.length !== 1 || translationsPageState.emptyActions[0] !== '읽기 시작') {
        throw new Error(`empty translations page should keep only the find action: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.emptyActionHrefs[0] !== '/') {
        throw new Error(`empty translations page reading-start action should return to the archive home: ${JSON.stringify(translationsPageState)}`);
      }
    } else {
      if (translationsPageState.reviewBadgeCount !== 0) {
        throw new Error(`default translations list should hide review-state badges: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.sourceDisclosureCount !== 0) {
        throw new Error(`default translations list should hide repeated source disclosures: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.openCommentaryCount !== 0 || translationsPageState.commentarySummaryTexts.some((text) => text !== '해설')) {
        throw new Error(`default translations list should keep commentary collapsed behind a concise label: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.headingText !== '번역 목록' || !translationsPageState.documentTitle.startsWith('번역 목록 /')) {
        throw new Error(`default translations page should read as a list, not a review task: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.reviewQueueText && translationsPageState.reviewQueueText !== '검토할 번역') {
        throw new Error(`translations review entry should clearly name the review queue: ${JSON.stringify(translationsPageState)}`);
      }
      if (/\d/.test(translationsPageState.reviewQueueText)) {
        throw new Error(`translations review entry should keep counts out of the primary action text: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.reviewQueueText && !/^검토할 번역 .*개로 이동$/.test(translationsPageState.reviewQueueLabel)) {
        throw new Error(`translations review entry should keep count details in the accessible label: ${JSON.stringify(translationsPageState)}`);
      }
      if (
        translationsPageState.reviewQueueText &&
        (
          translationsPageState.reviewQueueBorderColor === 'rgb(176, 0, 0)' ||
          translationsPageState.reviewQueueColor === 'rgb(154, 0, 0)' ||
          translationsPageState.reviewQueueBackgroundColor === 'rgb(255, 250, 250)'
        )
      ) {
        throw new Error(`translations review entry should stay visually secondary in the default reading list: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.summaryButtons.length && !translationsPageState.summaryButtons.some((text) => text.startsWith('전체'))) {
        throw new Error(`default translations list should expose a compact status overview: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.summaryButtons.some((text) => /\d/.test(text))) {
        throw new Error(`translations status summary should hide visible counts from the reading flow: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.summaryLabels.some((label) => label && !/\d/.test(label))) {
        throw new Error(`translations status summary should keep counts in accessible labels: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.groupTitleCount === 0 || !translationsPageState.firstGroupTitle) {
        throw new Error(`default translations list should group records by work context: ${JSON.stringify(translationsPageState)}`);
      }
      if (/\d[\d,]*\s+(verses|segments|files|works|translations?)\b/i.test(translationsPageState.firstGroupTitle)) {
        throw new Error(`default translations group title should hide inventory-style counts: ${JSON.stringify(translationsPageState)}`);
      }
      if (/\.[0-9]+\.s[0-9]+/i.test(translationsPageState.firstRecordTitle)) {
        throw new Error(`default translations record title should use readable references, not internal sentence IDs: ${JSON.stringify(translationsPageState)}`);
      }
      if (!translationsPageState.firstGroupActions.includes('원문 읽기')) {
        throw new Error(`translation work groups should expose a concise source-reading action: ${JSON.stringify(translationsPageState)}`);
      }
      if (translationsPageState.firstGroupActionLabels.some((label) => label && !label.startsWith('원문 읽기: '))) {
        throw new Error(`translation work group source links should name their target accessibly: ${JSON.stringify(translationsPageState)}`);
      }
    }
  }
  if (parsed.pathname.startsWith('/work/') && parsed.hash) {
    await page.waitForSelector('.reader-sentence.selected', { timeout: 7000 }).catch(() => {});
    await page.waitForSelector('#translationOutput:not([hidden])', { timeout: 7000 }).catch(() => {});
    const state = await page.evaluate(() => {
      const output = document.querySelector('#translationOutput');
      const card = document.querySelector('.translation-card');
      const studyPage = document.querySelector('.study-page');
      const studyPanelToggle = document.querySelector('#studyPanelToggle');
      const studyPanelToggleBox = studyPanelToggle?.getBoundingClientRect();
      const studyPanelToggleStyle = studyPanelToggle ? window.getComputedStyle(studyPanelToggle) : null;
      const studyTools = document.querySelector('.translation-utility');
      const studyToolsStyle = studyTools ? window.getComputedStyle(studyTools) : null;
      const studyToolsSummaryNode = studyTools?.querySelector('summary');
      const studyToolsSummaryStyle = studyToolsSummaryNode ? window.getComputedStyle(studyToolsSummaryNode) : null;
      const studyToolsSummaryBox = studyToolsSummaryNode?.getBoundingClientRect();
      const activeTab = document.querySelector('.study-tab.active');
      const primaryStudyTabs = Array.from(document.querySelectorAll('#study-tab-translation, #study-tab-notes')).map((node) => {
        const box = node.getBoundingClientRect();
        return {
          text: node.textContent.trim(),
          width: box.width,
          height: box.height
        };
      });
      const inactiveSecondaryTabs = Array.from(document.querySelectorAll('.study-tab-secondary:not(.active)')).map((node) => {
        const style = window.getComputedStyle(node);
        const box = node.getBoundingClientRect();
        return {
          text: node.textContent.trim(),
          background: style.backgroundColor,
          border: style.borderTopColor,
          width: box.width,
          height: box.height
        };
      });
      const readingNext = document.querySelector('[data-translation-quick-action="next-sentence"]');
      const readingSave = document.querySelector('[data-translation-quick-action="mark-reviewed"], .translation-quick-state[data-review-state="reviewed"]');
      const readingNote = document.querySelector('[data-translation-quick-action="draft-note"]');
      const readingActionsNode = document.querySelector('.translation-reading-actions');
      const readingActionsStyle = readingActionsNode ? window.getComputedStyle(readingActionsNode) : null;
      const secondaryActions = document.querySelector('.translation-secondary-actions');
      const secondaryActionsStyle = secondaryActions ? window.getComputedStyle(secondaryActions) : null;
      const secondaryActionsBox = secondaryActions?.getBoundingClientRect();
      const secondarySummary = secondaryActions?.querySelector('summary');
      const secondarySummaryStyle = secondarySummary ? window.getComputedStyle(secondarySummary) : null;
      const secondarySummaryBox = secondarySummary?.getBoundingClientRect();
      const outputVisibleText = output ? output.innerText : '';
      const translationHeading = document.querySelector('.translation-section-primary h3');
      const translationHeadingBox = translationHeading?.getBoundingClientRect();
      const commentaryHeading = document.querySelector('#translationOutput .translation-commentary h3');
      const commentaryHeadingBox = commentaryHeading?.getBoundingClientRect();
      const commentaryBody = document.querySelector('#translationOutput .translation-commentary p');
      const commentaryBodyStyle = commentaryBody ? window.getComputedStyle(commentaryBody) : null;
      const readingActions = Array.from(document.querySelectorAll('.translation-reading-actions > button, .translation-reading-actions > details > summary'))
        .filter((node) => {
          const box = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
        })
        .map((node) => node.textContent.trim());
      const readingNextBox = readingNext?.getBoundingClientRect();
      const readingNoteBox = readingNote?.getBoundingClientRect();
      const readingSaveBox = readingSave?.getBoundingClientRect();
      const visibleExtras = Array.from(document.querySelectorAll('#translationOutput .translation-extra'))
        .filter((node) => window.getComputedStyle(node).display !== 'none');
      const sectionOrder = Array.from(document.querySelectorAll('#translationOutput .translation-result > [data-translation-section]'))
        .filter((node) => window.getComputedStyle(node).display !== 'none')
        .map((node) => node.dataset.translationSection || '');
      const studyPageBox = studyPage?.getBoundingClientRect();
      const selectedSentenceNode = document.querySelector('.reader-sentence.selected');
      const selectedSentenceStyle = selectedSentenceNode ? window.getComputedStyle(selectedSentenceNode) : null;
      const quietMarkedSentence = Array.from(document.querySelectorAll('.reader-sentence.has-translation-state'))
        .find((node) => node !== selectedSentenceNode) || null;
      const quietMarkerStyle = quietMarkedSentence ? window.getComputedStyle(quietMarkedSentence, '::after') : null;
      const selectedMarkerStyle = selectedSentenceNode?.classList.contains('has-translation-state')
        ? window.getComputedStyle(selectedSentenceNode, '::after')
        : null;
      return {
        isMobile: window.innerWidth <= 860,
        viewportHeight: window.innerHeight,
        studyPageHeight: studyPageBox?.height || 0,
        selectedSentence: Boolean(selectedSentenceNode),
        outputVisible: Boolean(output && !output.hidden),
        readingMode: Boolean(output && output.classList.contains('reading-mode')),
        cardReadingMode: Boolean(card && card.classList.contains('reading-mode')),
        cardReviewState: card ? card.dataset.reviewState || '' : '',
        cardBoxShadow: card ? window.getComputedStyle(card).boxShadow : '',
        readingNextVisible: Boolean(readingNext && window.getComputedStyle(readingNext).display !== 'none'),
        readingNextText: readingNext ? readingNext.textContent.trim() : '',
        readingNextLabel: readingNext ? readingNext.getAttribute('aria-label') || '' : '',
        readingNextBorderColor: readingNext ? window.getComputedStyle(readingNext).borderColor : '',
        readingNextWidth: readingNextBox?.width || 0,
        readingNoteWidth: readingNoteBox?.width || 0,
        readingSaveWidth: readingSaveBox?.width || 0,
        readingNoteVisible: /메모 추가/.test(outputVisibleText),
        readingSaveVisible: /(^|\n)(저장|저장됨)(\n|$)/.test(outputVisibleText),
        secondaryActionsOpen: Boolean(secondaryActions?.open),
        secondaryActionsDisplay: secondaryActionsStyle?.display || '',
        secondaryActionsWidth: secondaryActionsBox?.width || 0,
        secondaryActionsHeight: secondaryActionsBox?.height || 0,
        secondaryActionsSummary: secondarySummary?.textContent.trim() || '',
        secondaryActionsJustifySelf: secondaryActionsStyle?.justifySelf || '',
        secondarySummaryBackground: secondarySummaryStyle?.backgroundColor || '',
        secondarySummaryBorderColor: secondarySummaryStyle?.borderTopColor || '',
        secondarySummaryHeight: secondarySummaryBox?.height || 0,
        readingActionsPosition: readingActionsStyle?.position || '',
        readingActionsBottom: readingActionsStyle?.bottom || '',
        readingActionsBoxShadow: readingActionsStyle?.boxShadow || '',
        translationHeadingWidth: translationHeadingBox?.width || 0,
        translationHeadingHeight: translationHeadingBox?.height || 0,
        translationHeadingText: translationHeading?.textContent.trim() || '',
        commentaryHeadingWidth: commentaryHeadingBox?.width || 0,
        commentaryHeadingHeight: commentaryHeadingBox?.height || 0,
        commentaryHeadingText: commentaryHeading?.textContent.trim() || '',
        commentaryLineHeight: commentaryBodyStyle?.lineHeight || '',
        readingSaveLabel: readingSave ? readingSave.getAttribute('aria-label') || '' : '',
        readingNoteLabel: readingNote ? readingNote.getAttribute('aria-label') || '' : '',
        readingActions,
        sectionOrder,
        visibleOutputText: outputVisibleText,
        visibleExtraCount: visibleExtras.length,
        activeTab: activeTab ? activeTab.textContent.trim() : '',
        primaryStudyTabs,
        inactiveSecondaryTabs,
        studyToolsOpen: Boolean(studyTools?.open),
        studyToolsBorderTopColor: studyToolsStyle?.borderTopColor || '',
        studyToolsSummary: studyToolsSummaryNode?.textContent.trim() || '',
        studyToolsSummaryHeight: studyToolsSummaryBox?.height || 0,
        studyToolsSummaryWidth: studyToolsSummaryBox?.width || 0,
        studyToolsSummaryFontSize: studyToolsSummaryStyle?.fontSize || '',
        studyPanelToggleAction: studyPanelToggle?.querySelector('.study-panel-toggle-action')?.textContent.trim() || '',
        studyPanelToggleSummary: studyPanelToggle?.querySelector('.study-panel-toggle-summary')?.textContent.trim() || '',
        studyPanelToggleLabel: studyPanelToggle?.getAttribute('aria-label') || '',
        studyPanelToggleHeight: studyPanelToggleBox?.height || 0,
        studyPanelToggleDisplay: studyPanelToggleStyle?.display || '',
        markerSampleFound: Boolean(quietMarkedSentence),
        quietMarkerOpacity: quietMarkerStyle?.opacity || '',
        selectedSentenceBackground: selectedSentenceStyle?.backgroundColor || '',
        selectedSentenceBoxShadow: selectedSentenceStyle?.boxShadow || '',
        selectedMarkerFound: Boolean(selectedMarkerStyle),
        selectedMarkerOpacity: selectedMarkerStyle?.opacity || '',
        selectedMarkerWidth: selectedMarkerStyle?.width || ''
      };
    });
    if (!state.selectedSentence) throw new Error(`selected work route did not select a sentence: ${JSON.stringify(state)}`);
    if (!state.outputVisible) throw new Error(`selected work route did not show translation output: ${JSON.stringify(state)}`);
    if (!state.readingMode) throw new Error(`translation output did not default to reading mode: ${JSON.stringify(state)}`);
    if (!state.cardReadingMode) throw new Error(`translation card did not default to reading mode: ${JSON.stringify(state)}`);
    if (state.cardReviewState && state.cardBoxShadow !== 'none') {
      throw new Error(`reading mode should suppress review-state card decoration: ${JSON.stringify(state)}`);
    }
    if (!state.readingNextVisible || state.readingNextText !== '다음 문장 번역') {
      throw new Error(`reading mode should expose the next sentence action: ${JSON.stringify(state)}`);
    }
    if (state.readingNextLabel !== '다음 문장을 선택하고 번역') {
      throw new Error(`reading mode next action should keep a clear accessible label: ${JSON.stringify(state)}`);
    }
    if (state.readingNextBorderColor !== 'rgb(176, 0, 0)') {
      throw new Error(`reading mode next action should be visually primary: ${JSON.stringify(state)}`);
    }
    if (state.readingNextWidth <= 0 || state.readingNoteVisible || state.readingSaveVisible) {
      throw new Error(`reading mode should keep only Next sentence translation as the immediate visible action: ${JSON.stringify(state)}`);
    }
    if (state.markerSampleFound && Number.parseFloat(state.quietMarkerOpacity || '1') > 0.4) {
      throw new Error(`translation state markers should stay quiet in the source text: ${JSON.stringify(state)}`);
    }
    if (state.selectedSentenceBackground === 'rgb(255, 241, 184)' || / 3px 0px 0px/.test(state.selectedSentenceBoxShadow)) {
      throw new Error(`selected sentence should stay legible without a highlighter-heavy mark: ${JSON.stringify(state)}`);
    }
    if (state.selectedMarkerFound && Number.parseFloat(state.selectedMarkerOpacity || '0') < 0.75) {
      throw new Error(`selected translation state marker should remain legible: ${JSON.stringify(state)}`);
    }
    if (state.readingActionsPosition !== 'sticky' || state.readingActionsBottom !== '8px') {
      throw new Error(`reading mode should keep study actions reachable during long commentary: ${JSON.stringify(state)}`);
    }
    if (state.readingActionsBoxShadow === 'none') {
      throw new Error(`reading mode should visually separate the sticky next action from long commentary: ${JSON.stringify(state)}`);
    }
    if (state.translationHeadingWidth <= 2 || state.translationHeadingHeight <= 2 || state.translationHeadingText !== '번역') {
      throw new Error(`reading mode should keep the translation heading visible before commentary: ${JSON.stringify(state)}`);
    }
    if (state.commentaryHeadingWidth <= 2 || state.commentaryHeadingHeight <= 2) {
      throw new Error(`reading mode should keep the commentary heading visible: ${JSON.stringify(state)}`);
    }
    if (state.commentaryHeadingText !== '해설') {
      throw new Error(`reading mode should label commentary in the reader language: ${JSON.stringify(state)}`);
    }
    if (state.commentaryLineHeight && parseFloat(state.commentaryLineHeight) > 24) {
      throw new Error(`reading mode commentary should stay compact enough for the study panel: ${JSON.stringify(state)}`);
    }
    if (state.sectionOrder[0] !== 'translation' || state.sectionOrder[1] !== 'commentary') {
      throw new Error(`reading mode should keep translation and commentary as the first visible result sections: ${JSON.stringify(state)}`);
    }
    for (const noisyText of ['Literal gloss', 'Key terms', 'source_text_sha256', 'prompt_sha256']) {
      if (state.visibleOutputText.includes(noisyText)) {
        throw new Error(`reading mode should hide noisy translation metadata ${noisyText}: ${JSON.stringify(state)}`);
      }
    }
    if (!['번역 저장', '저장된 번역'].includes(state.readingSaveLabel) || state.readingNoteLabel !== '번역으로 메모 추가') {
      throw new Error(`reading mode quick actions should keep clear accessible labels: ${JSON.stringify(state)}`);
    }
    if (state.secondaryActionsDisplay !== 'none' || state.secondaryActionsWidth > 0 || state.secondaryActionsHeight > 0) {
      throw new Error(`reading mode should move note/save actions out of the immediate reading card: ${JSON.stringify(state)}`);
    }
    const firstAction = state.readingActions[0] || '';
    if (firstAction !== '다음 문장 번역' || state.readingActions.length !== 1) {
      throw new Error(`reading mode should show only Next sentence translation as the immediate action: ${JSON.stringify(state)}`);
    }
    if (state.visibleExtraCount !== 0) throw new Error(`reading mode exposed study-only translation extras: ${JSON.stringify(state)}`);
    if (state.activeTab !== '번역') throw new Error(`selected work route did not keep Translation tab active: ${JSON.stringify(state)}`);
    if (state.inactiveSecondaryTabs.length !== 2 || state.inactiveSecondaryTabs.some((tab) => tab.background !== 'rgba(0, 0, 0, 0)' || tab.border !== 'rgba(0, 0, 0, 0)')) {
      throw new Error(`secondary study tabs should stay visually quieter than translation and notes: ${JSON.stringify(state)}`);
    }
    if (state.isMobile) {
      const primaryMinWidth = Math.min(...state.primaryStudyTabs.map((tab) => tab.width).filter(Boolean));
      const secondaryMaxWidth = Math.max(...state.inactiveSecondaryTabs.map((tab) => tab.width).filter(Boolean));
      const secondaryMaxHeight = Math.max(...state.inactiveSecondaryTabs.map((tab) => tab.height).filter(Boolean));
      if (!primaryMinWidth || !secondaryMaxWidth || secondaryMaxWidth >= primaryMinWidth * 0.72 || secondaryMaxHeight > 34) {
        throw new Error(`mobile secondary study tabs should stay compact beside primary reading tabs: ${JSON.stringify(state)}`);
      }
    }
    if (state.studyToolsOpen) throw new Error(`study tools should stay collapsed in default reading mode: ${JSON.stringify(state)}`);
    if (state.studyToolsSummary !== '저장 · 노트 · 이동') throw new Error(`study tools summary should name the hidden save, note, and navigation tools: ${JSON.stringify(state)}`);
    if (state.studyToolsSummaryHeight > 24 || state.studyToolsSummaryWidth > 112 || parseFloat(state.studyToolsSummaryFontSize || '99') > 10) {
      throw new Error(`reading mode study tools summary should stay visually secondary: ${JSON.stringify(state)}`);
    }
    if (!['rgba(0, 0, 0, 0)', 'transparent'].includes(state.studyToolsBorderTopColor)) {
      throw new Error(`reading mode study tools should not add another visible divider below the reading actions: ${JSON.stringify(state)}`);
    }
    if (state.isMobile && state.studyPanelToggleAction !== '본문 보기') {
      throw new Error(`expanded mobile study handle should describe returning to source text: ${JSON.stringify(state)}`);
    }
    if (!['선택한 문장', '번역 완료'].includes(state.studyPanelToggleSummary)) {
      throw new Error(`mobile study toggle should describe reading state without numeric metadata: ${JSON.stringify(state)}`);
    }
    if (/Sentence\s+\d+\s+of\s+\d+/i.test(`${state.studyPanelToggleSummary} ${state.studyPanelToggleLabel}`)) {
      throw new Error(`mobile study toggle should hide sentence count metadata from the primary reading handle: ${JSON.stringify(state)}`);
    }
    if (state.isMobile && state.studyPageHeight > Math.ceil(state.viewportHeight * 0.66)) {
      throw new Error(`mobile study panel should leave source text visible above it: ${JSON.stringify(state)}`);
    }
    if (state.isMobile && (state.studyPanelToggleDisplay !== 'grid' || state.studyPanelToggleHeight > 42)) {
      throw new Error(`mobile study toggle should stay compact as a handle: ${JSON.stringify(state)}`);
    }
    const utilityState = await page.evaluate(() => {
      const utility = document.querySelector('.translation-utility');
      if (!utility) return { exists: false, labels: [] };
      utility.open = true;
      const manage = utility.querySelector('.translation-review-tools');
      if (manage) manage.open = true;
      const labels = Array.from(utility.querySelectorAll('.translation-utility-group-label')).map((node) => {
        const box = node.getBoundingClientRect();
        return {
          text: node.textContent.trim(),
          width: box.width,
          height: box.height
        };
      });
      const reviewActions = Array.from(utility.querySelectorAll('.translation-review-actions button')).map((node) => ({
        id: node.id,
        text: node.textContent.trim(),
        display: window.getComputedStyle(node).display
      }));
      const manageSummary = manage?.querySelector('summary')?.textContent.trim() || '';
      const sourceStatus = utility.querySelector('[data-selected-source-status]');
      const sourceStatusBox = sourceStatus?.getBoundingClientRect();
      utility.open = false;
      return {
        exists: true,
        labels,
        manageSummary,
        reviewActions,
        sourceStatusText: sourceStatus?.textContent.trim() || '',
        sourceStatusLabel: sourceStatus?.getAttribute('aria-label') || '',
        sourceStatusClass: sourceStatus?.className || '',
        sourceStatusWidth: sourceStatusBox?.width || 0,
        sourceStatusHeight: sourceStatusBox?.height || 0
      };
    });
    if (!utilityState.exists || utilityState.labels.length < 3) {
      throw new Error(`study tools should keep accessible utility labels: ${JSON.stringify(utilityState)}`);
    }
    if (utilityState.labels.some((label) => label.width > 2 || label.height > 2)) {
      throw new Error(`study tools utility labels should stay visually quiet: ${JSON.stringify(utilityState)}`);
    }
    if (utilityState.manageSummary !== '저장 · 내보내기') {
      throw new Error(`study action tools should have a concise summary: ${JSON.stringify(utilityState)}`);
    }
    if (!utilityState.sourceStatusClass.includes('visually-hidden') || utilityState.sourceStatusWidth > 2 || utilityState.sourceStatusHeight > 2) {
      throw new Error(`selected source visibility status should stay accessible but visually quiet: ${JSON.stringify(utilityState)}`);
    }
    if (!['원문이 화면에 있음', '원문이 화면 밖에 있음'].includes(utilityState.sourceStatusText) || utilityState.sourceStatusText !== utilityState.sourceStatusLabel) {
      throw new Error(`selected source visibility status should avoid visible shorthand labels: ${JSON.stringify(utilityState)}`);
    }
    const visibleManagementActions = utilityState.reviewActions
      .filter((action) => action.display !== 'none')
      .map((action) => action.text);
    for (const expectedAction of ['저장', '제외', '노트 복사', '메모 추가']) {
      if (!visibleManagementActions.includes(expectedAction)) {
        throw new Error(`study action tools should keep ${expectedAction} available behind the tools menu: ${JSON.stringify(utilityState)}`);
      }
    }
    if (state.isMobile) {
      await page.click('#studyPanelToggle');
      await page.waitForFunction(() => !document.querySelector('.study-page')?.classList.contains('is-expanded'), null, { timeout: 3000 });
      await page.waitForTimeout(350);
      const collapsedStudyState = await page.evaluate(() => {
        const studyPage = document.querySelector('.study-page');
        const scrim = document.querySelector('#studyPanelScrim');
        const selected = document.querySelector('.reader-sentence.selected');
        const toggle = document.querySelector('#studyPanelToggle');
        const studyPageBox = studyPage?.getBoundingClientRect();
        const selectedBox = selected?.getBoundingClientRect();
        return {
          expanded: Boolean(studyPage?.classList.contains('is-expanded')),
          scrimHidden: Boolean(scrim?.hidden),
          selectedVisible: Boolean(selectedBox && selectedBox.bottom > 0 && selectedBox.top < (studyPageBox?.top || window.innerHeight) - 8),
          selectedBottom: selectedBox?.bottom || 0,
          panelTop: studyPageBox?.top || 0,
          toggleAction: toggle?.querySelector('.study-panel-toggle-action')?.textContent.trim() || '',
          toggleSummary: toggle?.querySelector('.study-panel-toggle-summary')?.textContent.trim() || ''
        };
      });
      if (collapsedStudyState.expanded || !collapsedStudyState.scrimHidden || !collapsedStudyState.selectedVisible) {
        throw new Error(`mobile body toggle should collapse the study panel and return to the selected source: ${JSON.stringify(collapsedStudyState)}`);
      }
      if (collapsedStudyState.toggleAction !== '해설 보기') {
        throw new Error(`collapsed mobile study handle should name the active study panel: ${JSON.stringify(collapsedStudyState)}`);
      }
      await page.click('#studyPanelToggle');
      await page.waitForFunction(() => document.querySelector('.study-page')?.classList.contains('is-expanded'), null, { timeout: 3000 });
    }
    const nextFocusState = await page.evaluate(async () => {
      const ok = typeof window.focusNextSentenceAction === 'function'
        ? window.focusNextSentenceAction()
        : false;
      await new Promise((resolve) => requestAnimationFrame(resolve));
      await new Promise((resolve) => requestAnimationFrame(resolve));
      return {
        ok,
        activeAction: document.activeElement?.dataset?.translationQuickAction || '',
        activeText: document.activeElement?.textContent.trim() || ''
      };
    });
    if (!nextFocusState.ok || nextFocusState.activeAction !== 'next-sentence') {
      throw new Error(`saved review flow should focus the next sentence action: ${JSON.stringify(nextFocusState)}`);
    }
    await page.evaluate(() => {
      const utility = document.querySelector('.translation-utility');
      const manage = document.querySelector('.translation-review-tools');
      if (utility) utility.open = true;
      if (manage) manage.open = true;
    });
    await page.click('#draftTranslationNote');
    await page.waitForSelector('#study-panel-notes:not([hidden])', { timeout: 5000 });
    await page.waitForFunction(() => document.activeElement?.id === 'noteText', null, { timeout: 3000 }).catch(() => {});
    const draftState = await page.evaluate(() => {
      const note = document.querySelector('#noteText')?.value || '';
      return {
        activeTab: document.querySelector('.study-tab.active')?.textContent.trim() || '',
        note,
        tags: document.querySelector('#noteTags')?.value || '',
        noteStatus: document.querySelector('#noteStatus')?.textContent.trim() || '',
        translationStatus: document.querySelector('#translationStatus')?.textContent.trim() || '',
        activeElementId: document.activeElement?.id || ''
      };
    });
    if (draftState.activeTab !== '노트') {
      throw new Error(`Add note should switch to Notes tab: ${JSON.stringify(draftState)}`);
    }
    for (const expectedText of ['번역', '해설']) {
      if (!draftState.note.includes(expectedText)) {
        throw new Error(`Add note should draft concise ${expectedText} content: ${JSON.stringify(draftState)}`);
      }
    }
    for (const noisyText of ['Target:', 'Original source', 'Korean translation']) {
      if (draftState.note.includes(noisyText)) {
        throw new Error(`Add note should avoid noisy draft label ${noisyText}: ${JSON.stringify(draftState)}`);
      }
    }
    if (!draftState.tags.includes('ai-translation')) {
      throw new Error(`Add note should keep the translation tag: ${JSON.stringify(draftState)}`);
    }
    if (!/노트 초안을 만들었습니다|노트 초안에 추가했습니다/.test(draftState.noteStatus)) {
      throw new Error(`Add note should confirm the draft state without noisy instruction text: ${JSON.stringify(draftState)}`);
    }
    if (!/노트 초안으로 옮겼습니다|노트 초안에 추가했습니다/.test(draftState.translationStatus)) {
      throw new Error(`Add note should keep translation status aligned with the note draft state: ${JSON.stringify(draftState)}`);
    }
    if (draftState.activeElementId !== 'noteText') {
      throw new Error(`Add note should focus the note editor: ${JSON.stringify(draftState)}`);
    }
    const notesState = await page.evaluate(() => ({
      notePlaceholder: document.querySelector('#noteText')?.getAttribute('placeholder') || '',
      noteLabelHidden: Boolean(document.querySelector('#noteText')?.closest('label')?.querySelector('.visually-hidden')),
      saveText: document.querySelector('#noteForm button[type="submit"]')?.textContent.trim() || '',
      saveLabel: document.querySelector('#noteForm button[type="submit"]')?.getAttribute('aria-label') || '',
      tagsSummary: document.querySelector('.note-options summary')?.textContent.trim() || '',
      savedSummary: document.querySelector('.notes-filter-tools summary')?.textContent.trim() || '',
      savedToolsHidden: Boolean(document.querySelector('.notes-filter-tools')?.hidden),
      noteListSummary: document.querySelector('#noteListSummary')?.textContent.trim() || '',
      notesEmptyText: document.querySelector('#notesList .notes-empty')?.textContent.trim() || '',
      noteItemActions: Array.from(document.querySelectorAll('#notesList .note-item:first-of-type .note-actions a, #notesList .note-item:first-of-type .note-actions button, #notesList .note-item:first-of-type .note-actions summary')).map((node) => node.textContent.trim()),
      noteItemActionLabels: Array.from(document.querySelectorAll('#notesList .note-item:first-of-type .note-actions a')).map((node) => node.getAttribute('aria-label') || ''),
      noteItemReviewAction: document.querySelector('#notesList .note-item:first-of-type .note-actions button[data-action="mark-reviewed-note"], #notesList .note-item:first-of-type .note-actions button[data-action="mark-raw-note"]')?.textContent.trim() || '',
      noteItemReviewActionLabel: document.querySelector('#notesList .note-item:first-of-type .note-actions button[data-action="mark-reviewed-note"], #notesList .note-item:first-of-type .note-actions button[data-action="mark-raw-note"]')?.getAttribute('aria-label') || '',
      noteItemReviewActionTitle: document.querySelector('#notesList .note-item:first-of-type .note-actions button[data-action="mark-reviewed-note"], #notesList .note-item:first-of-type .note-actions button[data-action="mark-raw-note"]')?.getAttribute('title') || '',
      noteTargetText: document.querySelector('#noteTargetPreview')?.textContent.trim() || '',
      noteTargetLabel: document.querySelector('#noteTargetPreview')?.getAttribute('aria-label') || '',
      lockTargetText: document.querySelector('#lockNoteTarget')?.textContent.trim() || ''
    }));
    if (notesState.notePlaceholder !== '메모 작성...' || !notesState.noteLabelHidden) {
      throw new Error(`notes tab should keep the editor quiet but accessible: ${JSON.stringify(notesState)}`);
    }
    if (notesState.saveText !== '저장' || notesState.saveLabel !== '노트 저장') {
      throw new Error(`notes tab save control should stay concise: ${JSON.stringify(notesState)}`);
    }
    if (notesState.tagsSummary !== '태그') {
      throw new Error(`notes tab details labels should stay concise: ${JSON.stringify(notesState)}`);
    }
    if (notesState.notesEmptyText === '아직 노트가 없습니다.' && !notesState.savedToolsHidden) {
      throw new Error(`notes tab should hide saved filters when there are no notes: ${JSON.stringify(notesState)}`);
    }
    if (notesState.notesEmptyText !== '아직 노트가 없습니다.' && notesState.savedSummary !== '저장한 노트') {
      throw new Error(`notes tab saved filter label should stay concise when notes or filters exist: ${JSON.stringify(notesState)}`);
    }
    if (/최신순|대상순|\d+개 노트/.test(notesState.noteListSummary)) {
      throw new Error(`notes tab list summary should avoid default count and sort status text: ${JSON.stringify(notesState)}`);
    }
    if (/\b(Work|Paragraph|Section|Verse|Quote|Line)\b|p-\d+\.s\d+/i.test(`${notesState.noteTargetText} ${notesState.noteTargetLabel}`)) {
      throw new Error(`notes target preview should use reader-language labels without internal ids: ${JSON.stringify(notesState)}`);
    }
    if (notesState.noteItemActions.length > 0) {
      if (!notesState.noteItemActions.includes('원문 읽기') || !notesState.noteItemActions.includes('노트 수정') || notesState.noteItemActions.includes('원문 열기') || notesState.noteItemActions.includes('수정') || notesState.noteItemActions.includes('다시 열기')) {
        throw new Error(`notes tab saved-note actions should use explicit reader-language labels: ${JSON.stringify(notesState)}`);
      }
      if (notesState.noteItemActionLabels.some((label) => label && !label.startsWith('원문 읽기: '))) {
        throw new Error(`notes tab source action should name the source target accessibly: ${JSON.stringify(notesState)}`);
      }
      if (!['저장', '작성 중으로'].includes(notesState.noteItemReviewAction)) {
        throw new Error(`notes tab review action should name the destination state clearly: ${JSON.stringify(notesState)}`);
      }
      if (!['저장한 노트로 표시', '작성 중인 노트로 옮기기'].includes(notesState.noteItemReviewActionLabel) || notesState.noteItemReviewActionTitle !== notesState.noteItemReviewActionLabel) {
        throw new Error(`notes tab review action should expose the destination in labels and titles: ${JSON.stringify(notesState)}`);
      }
    }
    if (!['대상 고정', '고정 해제'].includes(notesState.lockTargetText)) {
      throw new Error(`notes target lock control should stay reader-language concise: ${JSON.stringify(notesState)}`);
    }
    await page.click('#study-tab-citation');
    await page.waitForSelector('#study-panel-citation:not([hidden])', { timeout: 5000 });
    await page.click('.citation-copy-options summary');
    await page.waitForSelector('.citation-copy-options[open]', { timeout: 3000 });
    const citationState = await page.evaluate(() => {
      const preview = document.querySelector('#citationPreview');
      const copied = window.citationText ? window.citationText() : '';
      const copiedLabelText = copied.replace(/https?:\/\/\S+/g, '');
      return {
        copyText: document.querySelector('#copyCitation')?.textContent.trim() || '',
        copyLabel: document.querySelector('#copyCitation')?.getAttribute('aria-label') || '',
        copyOptionsText: document.querySelector('.citation-copy-options summary')?.textContent.trim() || '',
        previewText: preview?.textContent || '',
        copiedText: copied,
        copiedLabelText,
        previewHasUrl: /https?:\/\//.test(preview?.textContent || ''),
        copiedHasUrl: /https?:\/\//.test(copied),
        urlText: document.querySelector('#copyUrl')?.textContent.trim() || '',
        urlLabel: document.querySelector('#copyUrl')?.getAttribute('aria-label') || '',
        bundleText: document.querySelector('#copySourceBundle')?.textContent.trim() || '',
        bundleLabel: document.querySelector('#copySourceBundle')?.getAttribute('aria-label') || ''
      };
    });
    if (citationState.copyText !== '복사' || citationState.copyLabel !== '인용 복사') {
      throw new Error(`citation tab primary copy control should stay concise: ${JSON.stringify(citationState)}`);
    }
    if (citationState.copyOptionsText !== '복사 방식') {
      throw new Error(`citation tab secondary copy summary should stay distinct from the primary copy action: ${JSON.stringify(citationState)}`);
    }
    if (citationState.previewHasUrl || !citationState.copiedHasUrl) {
      throw new Error(`citation preview should hide URL while copied citation keeps it: ${JSON.stringify(citationState)}`);
    }
    if (/\b(Work|Paragraph|Section|Verse|Quote|Line)\b|p-\d+\.s\d+/i.test(`${citationState.previewText} ${citationState.copiedLabelText}`)) {
      throw new Error(`citation text should use reader-language position labels without internal ids: ${JSON.stringify(citationState)}`);
    }
    if (citationState.urlText !== 'URL' || citationState.urlLabel !== 'URL 복사' || citationState.bundleText !== '원문 묶음' || citationState.bundleLabel !== '원문 묶음 복사') {
      throw new Error(`citation secondary copy controls should stay concise: ${JSON.stringify(citationState)}`);
    }
    if (outputPath.includes('concept-tab')) {
      await page.click('#study-tab-concepts');
      await page.waitForSelector('#study-panel-concepts:not([hidden])', { timeout: 5000 });
      const conceptsState = await page.evaluate(() => {
        const panel = document.querySelector('#study-panel-concepts');
        const list = panel?.querySelector('.concept-list');
        const firstItem = list?.querySelector('li');
        const firstLink = firstItem?.querySelector('.concept-link');
        const firstItemBox = firstItem?.getBoundingClientRect();
        return {
          activeTab: document.querySelector('.study-tab.active')?.textContent.trim() || '',
          heading: panel?.querySelector('h2')?.textContent.trim() || '',
          text: panel?.textContent.trim().replace(/\s+/g, ' ') || '',
          itemCount: panel?.querySelectorAll('.concept-list li').length || 0,
          linkCount: panel?.querySelectorAll('.concept-link[href^="/search?"]').length || 0,
          firstLinkText: firstLink?.textContent.trim() || '',
          firstLinkHref: firstLink?.getAttribute('href') || '',
          firstLinkLabel: firstLink?.getAttribute('aria-label') || '',
          firstTerm: panel?.querySelector('.concept-term')?.textContent.trim() || '',
          firstItemHeight: firstItemBox?.height || 0,
          listStyle: list ? window.getComputedStyle(list).listStyleType : ''
        };
      });
      if (conceptsState.activeTab !== '개념' || conceptsState.heading !== '개념') {
        throw new Error(`concept tab should use Korean reader-facing labels: ${JSON.stringify(conceptsState)}`);
      }
      if (conceptsState.itemCount < 2 || conceptsState.listStyle !== 'none') {
        throw new Error(`concept tab should present a compact scannable concept list: ${JSON.stringify(conceptsState)}`);
      }
      if (conceptsState.linkCount !== conceptsState.itemCount || !conceptsState.firstLinkHref.includes('corpus_id=nietzsche') || !conceptsState.firstLinkHref.includes('from=') || !conceptsState.firstLinkLabel.startsWith('관련 본문 찾기:')) {
        throw new Error(`concept tab labels should link to scoped source search: ${JSON.stringify(conceptsState)}`);
      }
      if (!conceptsState.text.includes('계보학') || !conceptsState.text.includes('원한 감정') || !conceptsState.text.includes('도덕 개념')) {
        throw new Error(`concept tab should expose localized Nietzsche concept helpers: ${JSON.stringify(conceptsState)}`);
      }
      if (/Concepts|Historical diagnosis|Reactive valuation/.test(conceptsState.text)) {
        throw new Error(`concept tab should not expose English helper copy in the Korean reader UI: ${JSON.stringify(conceptsState)}`);
      }
      if (conceptsState.firstItemHeight > 95) {
        throw new Error(`concept tab entries should remain compact enough to scan: ${JSON.stringify(conceptsState)}`);
      }
    } else {
      await page.click('#study-tab-translation');
      await page.waitForSelector('#study-panel-translation:not([hidden])', { timeout: 5000 });
      const restoredReadingState = await page.evaluate(() => {
        const utility = document.querySelector('.translation-utility');
        const manage = document.querySelector('.translation-review-tools');
        const secondaryActions = document.querySelector('.translation-secondary-actions');
        if (utility) utility.open = false;
        if (manage) manage.open = false;
        if (secondaryActions) secondaryActions.open = false;
        const outputText = document.querySelector('#translationOutput')?.innerText || '';
        return {
          utilityOpen: Boolean(utility?.open),
          manageOpen: Boolean(manage?.open),
          secondaryActionsOpen: Boolean(secondaryActions?.open),
          outputText
        };
      });
      if (restoredReadingState.utilityOpen || restoredReadingState.manageOpen || restoredReadingState.secondaryActionsOpen || /메모 추가/.test(restoredReadingState.outputText) || /(^|\n)(저장|저장됨)(\n|$)/.test(restoredReadingState.outputText)) {
        throw new Error(`selected work screenshot should return to the quiet reading action state: ${JSON.stringify(restoredReadingState)}`);
      }
    }
  }
  if (parsed.pathname === '/translations' && parsed.searchParams.get('review_state') === 'generated') {
    await page.waitForSelector('#translationsResults .translation-record-card, #translationsResults .empty-state', { timeout: 7000 }).catch(() => {});
    const state = await page.evaluate(() => {
      const activeFilters = document.querySelector('#translationsActiveFilters');
      const cards = document.querySelectorAll('#translationsResults .translation-record-card:not(.notes-skeleton)').length;
      return {
        cards,
        toolsHidden: Boolean(document.querySelector('#translationsListTools')?.hidden),
        toolsOpen: Boolean(document.querySelector('#translationsListTools')?.open),
        activeFiltersHidden: Boolean(activeFilters?.hidden),
        activeFiltersText: activeFilters ? activeFilters.textContent.trim() : '',
        reviewQueueHidden: Boolean(document.querySelector('#translationsReviewQueue')?.hidden),
        groupActionText: Array.from(document.querySelectorAll('#translationsResults .translation-record-group-actions')).map((node) => node.textContent.trim()).join(' '),
        headingText: document.querySelector('#translationsPageTitle')?.textContent.trim() || '',
        documentTitle: document.title
      };
    });
    if (state.cards > 0 && !state.toolsHidden) throw new Error(`review queue should hide filter tools while reviewing: ${JSON.stringify(state)}`);
    if (state.cards > 0 && state.toolsOpen) throw new Error(`review queue should keep list tools collapsed: ${JSON.stringify(state)}`);
    if (state.cards > 0 && (!state.activeFiltersHidden || state.activeFiltersText)) {
      throw new Error(`review queue should not repeat the status filter chip: ${JSON.stringify(state)}`);
    }
    if (state.cards > 0 && !state.reviewQueueHidden) {
      throw new Error(`review queue should not repeat the translation review entry action while already reviewing: ${JSON.stringify(state)}`);
    }
    if (state.cards > 0 && state.groupActionText) {
      throw new Error(`review queue should keep repeated group actions out of the review flow: ${JSON.stringify(state)}`);
    }
    if (state.cards > 0 && (state.headingText !== '검토할 번역' || !state.documentTitle.startsWith('검토할 번역 /'))) {
      throw new Error(`review queue should clearly identify the review task: ${JSON.stringify(state)}`);
    }
    if (state.cards > 0) {
      await page.keyboard.press('q');
      await page.waitForSelector('#translationsResults .translation-record-card.is-review-target', { timeout: 3000 }).catch(() => {});
      const reviewTargetState = await page.evaluate(() => {
        const card = document.querySelector('#translationsResults .translation-record-card.is-review-target');
        const cardStyle = card ? window.getComputedStyle(card) : null;
        const more = card?.querySelector('.translation-more-actions');
        const moreSummary = more?.querySelector(':scope > summary');
        const moreSummaryStyle = moreSummary ? window.getComputedStyle(moreSummary) : null;
        const moreSummaryBox = moreSummary?.getBoundingClientRect();
        const wasMoreOpen = Boolean(more?.open);
        if (more) more.open = true;
        const reject = more?.querySelector('.translation-danger-actions');
        const wasRejectOpen = Boolean(reject?.open);
        const rejectSummary = reject?.querySelector(':scope > summary');
        const rejectButton = reject?.querySelector('button[data-review-state="rejected"]');
        const rejectSummaryStyle = rejectSummary ? window.getComputedStyle(rejectSummary) : null;
        const save = card?.querySelector('.primary-review-action');
        const sourceAction = card?.querySelector('.translation-actions [data-open-source]');
        const saveBox = save?.getBoundingClientRect();
        const sourceActionBox = sourceAction?.getBoundingClientRect();
        const footer = card?.querySelector('.translation-record-footer');
        const footerBox = footer?.getBoundingClientRect();
        const footerStyle = footer ? window.getComputedStyle(footer) : null;
        const rejectSummaryBox = rejectSummary?.getBoundingClientRect();
        const immediateActionText = Array.from(card?.querySelectorAll('.translation-actions > button, .translation-actions > a, .translation-actions > details > summary') || [])
          .map((node) => node.textContent.trim())
          .join(' ');
        const nonTargetFooter = Array.from(document.querySelectorAll('#translationsResults .translation-record-card[data-review-state="generated"]:not(.is-review-target) .translation-record-footer'))
          .find((node) => node.querySelector('.primary-review-action'));
        const source = card?.querySelector('.translation-source');
        const sourceSummary = source?.querySelector('summary');
        const commentary = card?.querySelector('.translation-commentary');
        const commentarySummary = commentary?.querySelector('summary');
        const commentarySummaryBox = commentarySummary?.getBoundingClientRect();
        const openCommentaries = document.querySelectorAll('#translationsResults .translation-commentary[open]').length;
        const state = {
          hasReviewTarget: Boolean(card),
          immediateActionText,
          moreText: more?.textContent.trim() || '',
          moreSummaryText: moreSummary?.textContent.trim() || '',
          moreDisplay: more ? window.getComputedStyle(more).display : '',
          moreOpen: Boolean(more?.open),
          moreSummaryBorderColor: moreSummaryStyle?.borderColor || '',
          moreSummaryBackground: moreSummaryStyle?.backgroundColor || '',
          moreSummaryWidth: moreSummaryBox?.width || 0,
          moreSummaryHeight: moreSummaryBox?.height || 0,
          rejectText: reject?.textContent.trim() || '',
          rejectSummaryText: rejectSummary?.textContent.trim() || '',
          rejectButtonText: rejectButton?.textContent.trim() || '',
          rejectButtonLabel: rejectButton?.getAttribute('aria-label') || '',
          rejectDisplay: reject ? window.getComputedStyle(reject).display : '',
          rejectSummaryBorderColor: rejectSummaryStyle?.borderColor || '',
          rejectSummaryBackground: rejectSummaryStyle?.backgroundColor || '',
          saveText: save?.textContent.trim() || '',
          saveLabel: save?.getAttribute('aria-label') || '',
          saveBorderColor: save ? window.getComputedStyle(save).borderColor : '',
          saveWidth: saveBox?.width || 0,
          saveHeight: saveBox?.height || 0,
          sourceActionText: sourceAction?.textContent.trim() || '',
          sourceActionLabel: sourceAction?.getAttribute('aria-label') || '',
          sourceActionHref: sourceAction?.getAttribute('href') || '',
          sourceActionWidth: sourceActionBox?.width || 0,
          sourceActionHeight: sourceActionBox?.height || 0,
          rejectSummaryWidth: rejectSummaryBox?.width || 0,
          rejectSummaryHeight: rejectSummaryBox?.height || 0,
          footerWidth: footerBox?.width || 0,
          reviewFooterPosition: footerStyle?.position || '',
          reviewFooterDisplay: footerStyle?.display || '',
          reviewFooterBottom: footerStyle?.bottom || '',
          nonTargetFooterDisplay: nonTargetFooter ? window.getComputedStyle(nonTargetFooter).display : '',
          isDesktopLayout: window.innerWidth > 860,
          sourceOpen: Boolean(source?.open),
          sourceSummaryText: sourceSummary?.textContent.trim() || '',
          sourceText: source?.textContent.trim() || '',
          reviewTargetBackground: cardStyle?.backgroundColor || '',
          reviewTargetBorderLeftColor: cardStyle?.borderLeftColor || '',
          reviewTargetOutlineColor: cardStyle?.outlineColor || '',
          reviewTargetOutlineStyle: cardStyle?.outlineStyle || '',
          commentaryOpen: Boolean(commentary?.open),
          commentarySummaryText: commentarySummary?.textContent.trim() || '',
          commentarySummaryWidth: commentarySummaryBox?.width || 0,
          commentarySummaryHeight: commentarySummaryBox?.height || 0,
          openCommentaries,
          statusText: document.querySelector('#translationsStatus')?.textContent.trim() || ''
        };
        if (reject) reject.open = wasRejectOpen;
        if (more) more.open = wasMoreOpen;
        return state;
      });
      if (!reviewTargetState.hasReviewTarget || !reviewTargetState.immediateActionText.includes('저장') || !reviewTargetState.immediateActionText.includes('원문 읽기') || !reviewTargetState.immediateActionText.includes('더보기')) {
        throw new Error(`review queue should expose save, source, and more as immediate actions: ${JSON.stringify(reviewTargetState)}`);
      }
      if (/제외하기|삭제|검토로 되돌리기/.test(reviewTargetState.immediateActionText)) {
        throw new Error(`review queue should keep secondary review actions behind 더보기: ${JSON.stringify(reviewTargetState)}`);
      }
      if (!reviewTargetState.moreOpen || reviewTargetState.moreSummaryText !== '더보기' || reviewTargetState.moreDisplay === 'none') {
        throw new Error(`review queue should open secondary actions from 더보기 on the active card: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.moreSummaryBorderColor !== 'rgba(0, 0, 0, 0)' || reviewTargetState.moreSummaryBackground !== 'rgba(0, 0, 0, 0)') {
        throw new Error(`review queue More action should stay visually secondary: ${JSON.stringify(reviewTargetState)}`);
      }
      if (!reviewTargetState.rejectText.includes('제외') || reviewTargetState.rejectDisplay === 'none') {
        throw new Error(`review queue should expose the discard action inside More on the active review card: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.rejectSummaryText !== '제외') {
        throw new Error(`review queue discard action should stay concise inside More: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.saveText !== '저장' || reviewTargetState.saveLabel !== '저장한 번역으로 표시' || reviewTargetState.saveBorderColor !== 'rgb(176, 0, 0)') {
        throw new Error(`review queue save should use the same red primary action style: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.sourceActionText !== '원문 읽기' || !reviewTargetState.sourceActionLabel.startsWith('원문 읽기: ') || !reviewTargetState.sourceActionHref.startsWith('/work/')) {
        throw new Error(`review queue should expose a clear source navigation action on the active review card: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.rejectButtonText !== '제외하기' || reviewTargetState.rejectButtonLabel !== '이 번역 제외하기') {
        throw new Error(`review queue discard confirmation should name the result of the action: ${JSON.stringify(reviewTargetState)}`);
      }
      if (!reviewTargetState.isDesktopLayout) {
        if (reviewTargetState.reviewFooterDisplay !== 'block') {
          throw new Error(`mobile review queue footer should let actions use the full card width: ${JSON.stringify(reviewTargetState)}`);
        }
        if (reviewTargetState.saveHeight < 34 || reviewTargetState.sourceActionHeight < 34 || reviewTargetState.moreSummaryHeight < 34 || reviewTargetState.rejectSummaryHeight < 34) {
          throw new Error(`mobile review queue actions should be touch-friendly: ${JSON.stringify(reviewTargetState)}`);
        }
        if (reviewTargetState.footerWidth > 0 && (reviewTargetState.saveWidth < reviewTargetState.footerWidth * 0.42 || reviewTargetState.sourceActionWidth < reviewTargetState.footerWidth * 0.42 || reviewTargetState.moreSummaryWidth < reviewTargetState.footerWidth * 0.42 || reviewTargetState.rejectSummaryWidth < reviewTargetState.footerWidth * 0.42)) {
          throw new Error(`mobile review queue actions should occupy the card action row: ${JSON.stringify(reviewTargetState)}`);
        }
      }
      if (reviewTargetState.isDesktopLayout && (reviewTargetState.reviewFooterPosition !== 'sticky' || reviewTargetState.reviewFooterBottom !== '8px')) {
        throw new Error(`review queue should keep active review actions reachable on desktop: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.nonTargetFooterDisplay && reviewTargetState.nonTargetFooterDisplay !== 'none') {
        throw new Error(`review queue should keep inactive review actions visually quiet on desktop: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.sourceOpen || reviewTargetState.sourceSummaryText !== '선택 문장' || !reviewTargetState.sourceText.includes('선택 문장')) {
        throw new Error(`review queue should keep original source available but collapsed by default: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.reviewTargetBackground !== 'rgb(255, 255, 255)') {
        throw new Error(`review queue target should stay visually quiet on a white reading surface: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.reviewTargetBorderLeftColor !== 'rgb(176, 0, 0)') {
        throw new Error(`review queue target should use only a slim archive accent line: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.reviewTargetOutlineStyle !== 'none' && reviewTargetState.reviewTargetOutlineColor === 'rgb(176, 0, 0)') {
        throw new Error(`review queue focus should not look like a red error outline: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.statusText.includes('translations /')) {
        throw new Error(`review queue should avoid duplicate count status text: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.statusText.includes('Next item')) {
        throw new Error(`review queue should avoid redundant next-item status text: ${JSON.stringify(reviewTargetState)}`);
      }
      if (!reviewTargetState.commentaryOpen || reviewTargetState.openCommentaries !== 1 || reviewTargetState.commentarySummaryText !== '해설') {
        throw new Error(`review queue should open commentary only for the active review target: ${JSON.stringify(reviewTargetState)}`);
      }
      if (reviewTargetState.commentarySummaryHeight < 22 || reviewTargetState.commentarySummaryWidth <= 0) {
        throw new Error(`review queue commentary disclosure should remain touch-readable: ${JSON.stringify(reviewTargetState)}`);
      }
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
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            suffix=".cjs",
            prefix="visual-smoke-",
            dir=output_path.parent,
            delete=False,
            encoding="utf-8",
        ) as script_file:
            script_file.write(script)
            script_path = Path(script_file.name)
        result = subprocess.run(
            [node, str(script_path), url, str(output_path), str(width), str(height), browser],
            cwd=SITE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    finally:
        if script_path:
            script_path.unlink(missing_ok=True)
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


def clear_previous_screenshots(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.png"):
        path.unlink()


def capture_smoke_routes(
    *,
    base_url: str,
    routes: list[tuple[str, str, bool]],
    output_dir: Path,
    html_only: bool,
    allow_screenshot_failures: bool,
    browser: str,
    playwright_node: str,
    playwright_node_path: str,
) -> tuple[int, int, list[str]]:
    html_count = 0
    screenshot_count = 0
    screenshot_failures: list[str] = []
    for route_label, route, should_capture in routes:
        url = f"{base_url}{route}"
        html = fetch_html(url)
        require("<html" in html.lower(), f"{route} response does not look like a page")
        require(
            "Personal Archive of Literature" in html or "아카이브" in html,
            f"{route} is missing archive identity text",
        )
        check_route_markup(route, html)
        html_count += 1
        if html_only or not should_capture:
            continue
        for viewport_label, width, height in VIEWPORTS:
            output_path = output_dir / f"{route_label}-{viewport_label}.png"
            try:
                capture(browser, playwright_node, playwright_node_path, url, output_path, width, height)
                screenshot_count += 1
            except AssertionError as exc:
                message = f"{route_label}/{viewport_label}: {exc}"
                if not allow_screenshot_failures:
                    raise AssertionError(message) from exc
                screenshot_failures.append(message)
    return html_count, screenshot_count, screenshot_failures


def start_visual_server(port: int, server_env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SITE / "server.py"), "--host", "127.0.0.1", "--port", str(port)],
        cwd=SITE,
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


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
        clear_previous_screenshots(args.output)
    html_count = 0
    screenshot_count = 0
    screenshot_failures: list[str] = []

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="philo_visual_notes_") as notes_temp_dir:
        server_env = os.environ.copy()
        server_env["PHILO_NOTES_DIR"] = str(Path(notes_temp_dir))
        seed_visual_notes(Path(notes_temp_dir))
        server = start_visual_server(port, server_env)
        try:
            wait_for_health(base_url, server)
            routes = [*ROUTES, *discover_source_routes()]
            route_html_count, route_screenshot_count, route_failures = capture_smoke_routes(
                base_url=base_url,
                routes=routes,
                output_dir=args.output,
                html_only=args.html_only,
                allow_screenshot_failures=args.allow_screenshot_failures,
                browser=browser,
                playwright_node=playwright_node,
                playwright_node_path=playwright_node_path,
            )
            html_count += route_html_count
            screenshot_count += route_screenshot_count
            screenshot_failures.extend(route_failures)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    empty_port = free_port()
    empty_base_url = f"http://127.0.0.1:{empty_port}"
    with (
        tempfile.TemporaryDirectory(prefix="philo_visual_empty_notes_") as empty_notes_dir,
        tempfile.TemporaryDirectory(prefix="philo_visual_empty_ai_") as empty_ai_dir,
    ):
        empty_env = os.environ.copy()
        empty_env["PHILO_NOTES_DIR"] = str(Path(empty_notes_dir))
        empty_env["PHILO_AI_DIR"] = str(Path(empty_ai_dir))
        empty_server = start_visual_server(empty_port, empty_env)
        try:
            wait_for_health(empty_base_url, empty_server)
            empty_html_count, empty_screenshot_count, empty_failures = capture_smoke_routes(
                base_url=empty_base_url,
                routes=EMPTY_STATE_ROUTES,
                output_dir=args.output,
                html_only=args.html_only,
                allow_screenshot_failures=args.allow_screenshot_failures,
                browser=browser,
                playwright_node=playwright_node,
                playwright_node_path=playwright_node_path,
            )
            html_count += empty_html_count
            screenshot_count += empty_screenshot_count
            screenshot_failures.extend(empty_failures)
        finally:
            empty_server.terminate()
            try:
                empty_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                empty_server.kill()

    if args.html_only:
        print(f"visual smoke html ok ({html_count} routes)")
    elif screenshot_failures:
        print(f"visual smoke html ok ({html_count} routes); screenshot failures allowed ({len(screenshot_failures)})")
        for failure in screenshot_failures:
            print(f"- {failure}")
    else:
        print(f"visual smoke ok ({screenshot_count} screenshots in {args.output})")


if __name__ == "__main__":
    main()
