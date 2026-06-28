from __future__ import annotations

import html

from rendering.work_markup import apply_template


def render_reading_page_html(template: str, title: str, source_path: str, source_href: str, content_html: str) -> str:
    return apply_template(
        template,
        {
            "TITLE": html.escape(title),
            "SOURCE_PATH": html.escape(source_path),
            "SOURCE_HREF": html.escape(source_href, quote=True),
            "CONTENT": content_html,
        },
    )


def source_mode_links(reading_href: str = "") -> str:
    links = '<a href="/">아카이브</a>'
    if reading_href:
        links += f' / <a href="{html.escape(reading_href, quote=True)}">본문 보기</a>'
    return links


def render_source_page_html(
    template: str,
    title: str,
    source_path: str,
    source_text: str,
    reading_href: str = "",
) -> str:
    return apply_template(
        template,
        {
            "TITLE": html.escape(title),
            "MODE_LINKS": source_mode_links(reading_href),
            "SOURCE_PATH": html.escape(source_path),
            "SOURCE_TEXT": html.escape(source_text),
        },
    )
