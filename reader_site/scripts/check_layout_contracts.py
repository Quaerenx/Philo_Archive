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


def css_rule_block(css: str, selector: str, label: str) -> str:
    start = css.find(selector)
    require(start >= 0, f"{label} missing selector {selector!r}")
    open_brace = css.find("{", start)
    close_brace = css.find("}", open_brace)
    require(open_brace >= 0 and close_brace >= 0, f"{label} malformed selector block {selector!r}")
    return css[open_brace + 1:close_brace]


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
        "/assets/search.css?v=phase11",
        "/assets/search.js?v=phase11",
        'id="searchSubmit"',
        'id="searchClear"',
        'id="searchActiveFilters"',
        'class="form-actions"',
        'role="status"',
        'aria-busy="false"',
    ]:
        require_contains(html, needle, "search.html")
    for needle in [
        "activeSearchController",
        "activeSearchRequest",
        "setSearchBusy",
        "renderSearchPending",
        "function renderEmptySearch",
        "function clearSearchFilters",
        "function updateSearchClearState",
        "function updateSearchFilterSummary",
        "function removeSearchFilter",
        "function resultGroupHeader",
        "function resultKind",
        "result-group-count",
        "result-kind",
        "searchClear.addEventListener",
        "activeFiltersEl.addEventListener",
        "filter-chip",
        "data-empty-action=\"clear-search\"",
        "search-skeleton",
        "activeSearchController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/search.js")
    for needle in [
        ".search-form.is-searching",
        ".form-actions",
        ".secondary-action",
        ".active-filters",
        ".active-filters.has-filters",
        ".filter-chip",
        ".result-group-header",
        ".result-group-count",
        ".result-kind",
        ".result-kind.work",
        ".result-kind.segment",
        ".result-kind.note",
        ".search-form.is-searching #searchSubmit",
        ".empty-state",
        ".empty-actions",
        ".empty-actions a",
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
        "/assets/notes.css?v=notes7",
        "/assets/notes.js?v=notes8",
        'id="notesSubmit"',
        'id="notesClear"',
        'id="notesActiveFilters"',
        'class="form-actions"',
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
        "function renderEmptyNotes",
        "function clearNotesFilters",
        "function updateNotesClearState",
        "function updateNotesFilterSummary",
        "function removeNotesFilter",
        "notesClear.addEventListener",
        "activeFiltersEl.addEventListener",
        "filter-chip",
        "data-empty-action=\"clear-filters\"",
        "notes-skeleton",
        "activeNotesController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/notes.js")
    for needle in [
        ".notes-form.is-loading",
        ".form-actions",
        ".secondary-action",
        ".active-filters",
        ".active-filters.has-filters",
        ".filter-chip",
        ".notes-form.is-loading #notesSubmit",
        ".empty-state",
        ".empty-actions",
        ".empty-actions a",
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
        "/assets/study.css?v=study8",
        "/assets/study.js?v=study8",
        'id="studySubmit"',
        'id="studyClear"',
        'id="studyActiveFilters"',
        'class="form-actions"',
        'role="status"',
        'aria-busy="false"',
    ]:
        require_contains(html, needle, "study.html")
    for needle in [
        "activeStudyController",
        "activeStudyRequest",
        "setStudyBusy",
        "renderStudyPending",
        "function renderEmptyStudy",
        "function clearStudyFilters",
        "function updateStudyClearState",
        "function updateStudyFilterSummary",
        "function removeStudyFilter",
        "studyClear.addEventListener",
        "activeFiltersEl.addEventListener",
        "filter-chip",
        "data-empty-action=\"clear-filters\"",
        "study-skeleton",
        "activeStudyController.abort()",
        "signal: controller.signal",
        'error.name === "AbortError"',
    ]:
        require_contains(script, needle, "assets/study.js")
    for needle in [
        ".study-form.is-loading",
        ".form-actions",
        ".secondary-action",
        ".active-filters",
        ".active-filters.has-filters",
        ".filter-chip",
        ".study-form.is-loading #studySubmit",
        ".empty-state",
        ".empty-actions",
        ".empty-actions a",
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
        "function targetSnapshot",
        "function selectedSentenceTargetSnapshot",
        "function noteTargetForSave",
        "function updateNoteTargetPreview",
        "function lockCurrentNoteTarget",
        "function unlockNoteTarget",
        "function syncTargetDependentViews",
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
        "setCommentaryExpanded",
        "syncTranslationModeDensity",
        "translationJumpNav",
        "scrollTranslationSectionIntoView",
        "data-translation-jump",
        "data-translation-section=\"translation\"",
        "data-translation-section=\"commentary\"",
        "translation-result",
        "translation-section-primary",
        "Show full commentary",
        "Collapse commentary",
        "recentlyChangedNoteId",
        "Note saved and highlighted.",
        "setStudyPanelExpanded",
        "updateStudyPanelScrim",
        "studyPanelScrim",
        "beginStudyPanelDrag",
        "updateStudyPanelDrag",
        "finishStudyPanelDrag",
        "cancelStudyPanelDrag",
        "STUDY_PANEL_DRAG_THRESHOLD",
        "ignoreNextStudyPanelToggleClick",
        "pointerdown",
        "pointermove",
        "pointerup",
        "pointercancel",
        'event.key === "Escape"',
        "selectedSentencePositionLabel",
        "sentencePositionText",
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
        "REGENERATE_CONFIRM_MS",
        "clearRegenerateConfirmation",
        "armRegenerateConfirmation",
        "handleRegenerateClick",
        "Confirm regenerate",
        "Click Confirm regenerate to replace this translation.",
        "requestSentenceTranslation(true)",
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
        "readingPosition",
        "initializeReadingPositionTracker",
        "IntersectionObserver",
        "visibleSentenceNodes",
        "requestAnimationFrame(refreshReadingPosition)",
        "readingCueTargetLine",
        "updateReadingPosition(node)",
        "reading-position-main",
        "reading-position-excerpt",
        "is-selectable-cue",
        "Current reading position: ${label}. ${excerpt}",
        "function studyReadingCueSentence",
        "data-reading-cue-select",
        "readingPosition.addEventListener",
        "function renderTranslationTarget",
        "function selectedSentenceIsVisible",
        "function updateTranslationTargetViewState",
        "translation-target-excerpt",
        "data-selected-source-jump",
        "Source off screen",
        "NOTE_DRAFT_STORAGE_KEY",
        "noteDraftPayload",
        "readerSessionStorage",
        "saveNoteDraft",
        "locked_target",
        "restoreNoteDraft",
        "clearNoteDraft",
        "sessionStorage",
        "Note draft restored.",
        "Note target locked.",
        "Note target follows selection.",
        "const target = noteTargetForSave()",
        "noteSort",
        "noteListSummary",
        "function sortedNotes",
        "function renderNotesPending",
        "function renderNotesList",
        "function noteTargetHref",
        "Open target",
        "notes-list-skeleton",
        "No notes found for this work.",
        "copyStudyCard",
        "function translationNoteDraftText",
        "Generated translation & commentary",
        "Original source",
        "Korean translation",
        "Translation appended to Notes.",
        "noteText.setSelectionRange",
        "translationStudyCardText",
        "Clipboard copy failed",
        'target?.closest?.(".study-page")',
        "activateStudyTabByIndex",
        "ensureActiveStudyTabVisible",
        "scrollIntoView({",
        "inline: \"nearest\"",
        "aria-selected",
        "panel.hidden = !active",
        'event.key === "ArrowRight"',
        'event.key === "Home"',
    ]:
        require_contains(script, needle, "assets/reader-work.js")
    require_contains(template, "/assets/reader-work.js?v=common39", "templates/work.html")
    require_contains(template, "/assets/reader-work.css?v=common36", "templates/work.html")
    for needle in [
        "reading-desk",
        "source-page",
        "study-page",
        "studyCompanionPanel",
        "studyPanelToggle",
        "studyPanelScrim",
        "Close study panel",
        "study-panel-toggle-action",
        "study-panel-toggle-summary",
        "aria-label=\"Full study panel. Select a sentence\"",
        'aria-controls="studyCompanionPanel"',
        "readingPosition",
        "Current reading position",
        "Reading position",
        "noteTargetPreview",
        "lockNoteTarget",
        "Lock target",
        'aria-pressed="false"',
        "notes-list-tools",
        "noteListSummary",
        "noteSort",
        "aria-busy=\"false\"",
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
    mobile_css = css.split("@media (max-width: 860px)", maxsplit=1)[1]
    mobile_page_before = css_rule_block(mobile_css, ".page::before", "assets/reader-work.css mobile block")
    for needle in [
        "width: 100%;",
        "background-size: auto var(--header-portrait-height, 128px);",
    ]:
        require_contains(mobile_page_before, needle, ".page::before mobile overflow guard")

    for needle in [
        ".reading-desk",
        "grid-template-columns: minmax(0, 1fr) 340px",
        "gap: 20px",
        ".source-page",
        "padding-right: 20px",
        ".study-page",
        ".page::before",
        "background-size: auto var(--header-portrait-height, 128px)",
        ".study-panel-scrim",
        ".study-panel-scrim[hidden]",
        "background: rgba(238, 238, 238, 0.42)",
        "position: sticky;",
        "position: fixed;",
        "top: auto;",
        ".reader-sentence.loading",
        ".study-tabs",
        ".study-tab:focus-visible",
        ".study-tab.active::after",
        ".sentence-controls button.needs-confirm",
        "min-height: 38px",
        "grid-template-columns: repeat(4, minmax(72px, 1fr))",
        "overscroll-behavior-x: contain",
        "scrollbar-width: thin",
        "@keyframes archive-panel-in",
        ".study-panel.active",
        "animation: archive-panel-in 140ms ease-out both",
        ".translation-output.reading-mode .translation-extra",
        ".translation-target-main",
        ".translation-target-status",
        ".translation-target-excerpt",
        ".translation-target.is-source-away",
        ".translation-target button",
        ".translation-result",
        ".translation-jump-nav",
        ".translation-section.is-jump-target",
        ".translation-section",
        ".translation-section-primary",
        "border-left: 3px solid #b00000",
        "max-height: clamp(220px, 42vh, 520px)",
        "line-height: 1.62",
        "line-height: 1.72",
        ".translation-loading",
        ".translation-study-skeleton",
        ".translation-skeleton-block",
        ".translation-skeleton-heading",
        ".translation-skeleton-line",
        ".translation-card.is-loading::before",
        "@keyframes archive-loading-rail",
        ".research-card button.is-working",
        ".translation-commentary.is-collapsed",
        ".translation-commentary.is-expanded p::after",
        ".commentary-toggle",
        ".note-item.is-recent",
        "@keyframes archive-note-highlight",
        ".study-panel-toggle",
        ".study-panel-toggle::before",
        ".study-panel-toggle-action",
        ".study-panel-toggle-summary",
        "text-overflow: ellipsis",
        ".study-page.is-expanded",
        ".study-page.is-dragging",
        ".study-page:not(.is-expanded) .study-tabs",
        "env(safe-area-inset-bottom, 0px)",
        "scroll-padding-top: 62px",
        "scroll-padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px))",
        ".study-page.is-expanded .study-panel.active",
        "padding-bottom: calc(28px + env(safe-area-inset-bottom, 0px))",
        "overscroll-behavior: contain",
        "touch-action: pan-y",
        "touch-action: none",
        "user-select: none",
        "max(10px, env(safe-area-inset-right, 0px))",
        "max-height: min(72vh, calc(100dvh - 32px))",
        "scroll-margin-block",
        ".sentence-context",
        ".reading-position",
        ".reading-position.is-selectable-cue",
        ".reading-position-main",
        ".reading-position-excerpt",
        ".reading-position button",
        ".reading-position-current",
        ".reader-sentence.reading-cue",
        ".note-target-tools",
        ".note-target-preview",
        ".note-target-preview.is-locked",
        ".note-target-lock",
        ".notes-list-tools",
        ".note-list-summary",
        ".notes-list-skeleton",
        ".notes-empty",
        ".note-target-link",
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
