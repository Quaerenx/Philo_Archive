from __future__ import annotations

from pathlib import Path


SITE = Path(__file__).resolve().parents[1]

TOKEN_FILE = "assets/design-tokens.css"
HTML_ENTRYPOINTS = [
    "index.html",
    "search.html",
    "notes.html",
    "study.html",
    "templates/work.html",
    "templates/reading.html",
    "templates/source.html",
]
READER_CSS_FILES = [
    "assets/reader-work.css",
    "assets/static-reader.css",
    "assets/notes.css",
    "assets/study.css",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_site_file(relative_path: str) -> str:
    return (SITE / relative_path).read_text(encoding="utf-8")


def require_contains(text: str, needle: str, label: str) -> None:
    require(needle in text, f"{label} missing {needle!r}")


def check_tokens() -> None:
    tokens = read_site_file(TOKEN_FILE)
    expected_tokens = {
        "--page-background": "#d9d9d9",
        "--page-frame-background": "#eeeeee",
        "--page-frame-width": "1000px",
        "--reader-column-width": "764px",
        "--reader-background": "#ffffff",
    }
    for name, value in expected_tokens.items():
        require_contains(tokens, f"{name}: {value};", TOKEN_FILE)


def check_html_entrypoints() -> None:
    for relative_path in HTML_ENTRYPOINTS:
        html = read_site_file(relative_path)
        require_contains(html, "/assets/design-tokens.css", relative_path)
        require_contains(html, 'class="page"', relative_path)


def check_page_frame_css(relative_path: str, css: str) -> None:
    for needle in [
        ".page {",
        "max-width: var(--page-frame-width",
        "background-color: var(--page-frame-background",
        "border: 1px solid var(--page-frame-border",
        "box-shadow: var(--page-frame-shadow",
    ]:
        require_contains(css, needle, relative_path)


def check_reader_css(relative_path: str, css: str) -> None:
    common_needles = [
        ".reader {",
        "background: var(--reader-background",
        "border: 1px solid var(--reader-border",
        "@media (max-width: 860px)",
        "width: auto;",
        "margin: 0 10px 24px;",
    ]
    for needle in common_needles:
        require_contains(css, needle, relative_path)
    if relative_path == "assets/reader-work.css":
        require_contains(css, "width: calc(100% - 64px);", relative_path)
        require_contains(css, "grid-template-columns: minmax(0, 1fr) 340px;", relative_path)
    else:
        require_contains(css, "width: var(--reader-column-width", relative_path)


def check_home_css() -> None:
    relative_path = "styles.css"
    css = read_site_file(relative_path)
    check_page_frame_css(relative_path, css)
    for needle in [
        ".nav-column {",
        "flex: 0 0 var(--reader-column-width",
        "background: var(--reader-background",
        "border: 1px solid var(--reader-border",
        "@media (max-width: 860px)",
    ]:
        require_contains(css, needle, relative_path)

    responsive = css.split("@media (max-width: 860px)", maxsplit=1)[1]
    for needle in [
        ".nav-column {",
        "flex: 0 1 auto;",
        "width: 100%;",
        "padding: 0 10px 24px;",
    ]:
        require_contains(responsive, needle, f"{relative_path} responsive block")


def check_reader_pages_css() -> None:
    for relative_path in READER_CSS_FILES:
        css = read_site_file(relative_path)
        check_page_frame_css(relative_path, css)
        check_reader_css(relative_path, css)


def check_study_target_ui() -> None:
    script = read_site_file("assets/study.js")
    for needle in [
        "function noteTargetMeta",
        "variant / ${variantId}",
        "Target URL missing",
        "Open target",
        "Manage note",
    ]:
        require_contains(script, needle, "assets/study.js")

    css = read_site_file("assets/study.css")
    for needle in [
        ".target-meta",
        "overflow-wrap: anywhere;",
        ".target-warning",
        ".note-actions",
    ]:
        require_contains(css, needle, "assets/study.css")


def check_search_ui() -> None:
    html = read_site_file("search.html")
    script = read_site_file("assets/search.js")
    css = read_site_file("assets/search.css")
    for needle in [
        "/assets/search.css?v=phase7",
        "/assets/search.js?v=phase7",
        'id="searchSubmit"',
        'role="status"',
        'aria-busy="false"',
    ]:
        require_contains(html, needle, "search.html")
    for needle in [
        "activeSearchController",
        "activeSearchRequest",
        "setSearchBusy",
        "renderSearchPending",
        "search-skeleton",
        "activeSearchController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/search.js")
    for needle in [
        ".search-form.is-searching",
        ".search-skeleton-line",
        "@keyframes archive-spin",
        "@keyframes archive-skeleton",
        "@media (prefers-reduced-motion: reduce)",
    ]:
        require_contains(css, needle, "assets/search.css")


def check_notes_ui() -> None:
    html = read_site_file("notes.html")
    script = read_site_file("assets/notes.js")
    css = read_site_file("assets/notes.css")
    for needle in [
        "/assets/notes.css?v=notes4",
        "/assets/notes.js?v=notes5",
        'id="notesSubmit"',
        'role="status"',
        'aria-busy="false"',
    ]:
        require_contains(html, needle, "notes.html")
    for needle in [
        "activeNotesController",
        "activeNotesRequest",
        "setNotesBusy",
        "setActionButtonBusy",
        "renderNotesPending",
        "notes-skeleton",
        "activeNotesController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/notes.js")
    for needle in [
        ".notes-form.is-loading",
        ".notes-skeleton-line",
        ".note-actions button.is-working",
        "@keyframes archive-spin",
        "@keyframes archive-skeleton",
        "@media (prefers-reduced-motion: reduce)",
    ]:
        require_contains(css, needle, "assets/notes.css")


def check_study_ui() -> None:
    html = read_site_file("study.html")
    script = read_site_file("assets/study.js")
    css = read_site_file("assets/study.css")
    for needle in [
        "/assets/study.css?v=study5",
        "/assets/study.js?v=study5",
        'id="studySubmit"',
        'role="status"',
        'aria-busy="false"',
    ]:
        require_contains(html, needle, "study.html")
    for needle in [
        "activeStudyController",
        "activeStudyRequest",
        "setStudyBusy",
        "renderStudyPending",
        "study-skeleton",
        "activeStudyController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/study.js")
    for needle in [
        ".study-form.is-loading",
        ".study-skeleton-line",
        "@keyframes archive-spin",
        "@keyframes archive-skeleton",
        "@media (prefers-reduced-motion: reduce)",
    ]:
        require_contains(css, needle, "assets/study.css")


def check_work_source_bundle_ui() -> None:
    template = read_site_file("templates/work.html")
    for needle in [
        'id="copySourceBundle"',
        "Copy source bundle",
    ]:
        require_contains(template, needle, "templates/work.html")

    script = read_site_file("assets/reader-work.js")
    for needle in [
        "function sourceBundleUrl",
        'new Set(["segment", "section", "paragraph", "verse"])',
        "/api/source-target",
        "/api/sentence-translation",
        "requestSentenceTranslation(false)",
        "Source bundle requires a section, paragraph, or verse target.",
        "Source bundle URL copied.",
        "navigateSentence(1)",
        "updateTranslationReview(\"reviewed\")",
        "setTranslationMode(\"reading\")",
        "renderTranslationPending",
        "renderTranslationError",
        "resetTranslationOutputScroll",
        "translationOutput.scrollTop = 0",
        "setActionButtonBusy",
        "Could not save note.",
        "renderCommentary",
        "translation-result",
        "translation-section-primary",
        "Show full commentary",
        "recentlyChangedNoteId",
        "Note saved and highlighted.",
        "setStudyPanelExpanded",
        "selectedSentencePositionLabel",
        "studyPanelToggleSummary",
        "updateStudyPanelToggleLabel",
        "translation ready",
        "Full study panel",
        "prefersReducedMotion",
        "sentenceScrollBlock",
        "activeTranslationController",
        "activeTranslationTargetKey",
        "selectedTranslationTargetKey",
        "Translation is already running...",
        "activeTranslationController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
        "isMobileStudyLayout",
        "studyPanelViewportHeight",
        "mobileSentenceSafeBottom",
        "adjustSentenceAboveStudyPanel",
        "keepSentenceAboveStudyPanel",
        "window.scrollBy",
        "window.setTimeout(() => adjustSentenceAboveStudyPanel(node)",
        "behavior: prefersReducedMotion() ? \"auto\" : \"smooth\"",
        "STUDY_PANEL_STORAGE_KEY",
        "storedStudyPanelExpanded",
        "rememberStudyPanelExpanded",
        "updateSentenceContext",
        "sentence-context-item",
        "copyStudyCard",
        "translationStudyCardText",
        "Clipboard copy failed",
        'target?.closest?.(".study-page")',
        "activateStudyTabByIndex",
        "aria-selected",
        "panel.hidden = !active",
        'event.key === "ArrowRight"',
        'event.key === "Home"',
    ]:
        require_contains(script, needle, "assets/reader-work.js")
    require_contains(template, "/assets/reader-work.js?v=common22", "templates/work.html")
    require_contains(template, "/assets/reader-work.css?v=common19", "templates/work.html")
    for needle in [
        "reading-desk",
        "source-page",
        "study-page",
        "studyCompanionPanel",
        "studyPanelToggle",
        "study-panel-toggle-action",
        "study-panel-toggle-summary",
        "aria-label=\"Full study panel. Select a sentence\"",
        'aria-controls="studyCompanionPanel"',
        "sentenceContext",
        'role="tablist"',
        'role="tab"',
        'role="tabpanel"',
        'aria-controls="study-panel-translation"',
        'aria-labelledby="study-tab-translation"',
        'aria-selected="true"',
        'tabindex="-1"',
        "aria-label=\"Translation result\"",
        "tabindex=\"0\"",
        "aria-keyshortcuts=\"ArrowUp K\"",
        "aria-keyshortcuts=\"ArrowDown J\"",
        "copyStudyCard",
        "translation-card",
        "study-tabs",
        "previousSentence",
        "markTranslationReviewed",
    ]:
        require_contains(template, needle, "templates/work.html")

    css = read_site_file("assets/reader-work.css")
    for needle in [
        ".reading-desk",
        "grid-template-columns: minmax(0, 1fr) 340px",
        "gap: 20px",
        ".source-page",
        "padding-right: 20px",
        ".study-page",
        "position: sticky;",
        "position: fixed;",
        "top: auto;",
        ".reader-sentence.loading",
        ".study-tabs",
        ".study-tab:focus-visible",
        "@keyframes archive-panel-in",
        ".study-panel.active",
        "animation: archive-panel-in 140ms ease-out both",
        ".translation-output.reading-mode .translation-extra",
        ".translation-result",
        ".translation-section",
        ".translation-section-primary",
        "border-left: 3px solid #b00000",
        "max-height: clamp(220px, 42vh, 520px)",
        "line-height: 1.62",
        "line-height: 1.72",
        ".translation-loading",
        ".translation-skeleton-line",
        ".research-card button.is-working",
        ".translation-commentary.is-collapsed",
        ".commentary-toggle",
        ".note-item.is-recent",
        "@keyframes archive-note-highlight",
        ".study-panel-toggle",
        ".study-panel-toggle::before",
        ".study-panel-toggle-action",
        ".study-panel-toggle-summary",
        "text-overflow: ellipsis",
        ".study-page.is-expanded",
        ".study-page:not(.is-expanded) .study-tabs",
        "env(safe-area-inset-bottom, 0px)",
        "overscroll-behavior: contain",
        "touch-action: pan-y",
        "max(10px, env(safe-area-inset-right, 0px))",
        "max-height: min(72vh, calc(100dvh - 32px))",
        "scroll-margin-block",
        ".sentence-context",
        ".research-card .sentence-context-item",
        "overscroll-behavior: contain",
        "scrollbar-gutter: stable",
        ".translation-output:focus-visible",
        "@media (prefers-reduced-motion: reduce)",
    ]:
        require_contains(css, needle, "assets/reader-work.css")


def main() -> None:
    check_tokens()
    check_html_entrypoints()
    check_home_css()
    check_reader_pages_css()
    check_study_target_ui()
    check_search_ui()
    check_notes_ui()
    check_study_ui()
    check_work_source_bundle_ui()
    print("layout contracts ok")


if __name__ == "__main__":
    main()
