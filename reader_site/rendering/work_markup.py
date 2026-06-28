from __future__ import annotations

import html
import json
from urllib.parse import quote, urlencode


def work_href(corpus_id: str, work_id: str) -> str:
    return f"/work/{quote(corpus_id, safe='')}/{quote(work_id, safe='')}"


def toc_markup(toc: list[dict[str, int | str]]) -> str:
    if not toc:
        return ""
    links = []
    for item in toc:
        level = int(item["level"])
        anchor = html.escape(str(item["id"]), quote=True)
        label = html.escape(str(item["label"]))
        links.append(f'<a class="toc-link level-{level}" href="#{anchor}">{label}</a>')
    return (
        '<details id="toc" class="toc"><summary>목차</summary>'
        f'<div class="toc-links">{"".join(links)}</div></details>'
    )


def concept_search_href(query: str, corpus_id: str = "") -> str:
    params = {"q": query}
    if corpus_id:
        params["corpus_id"] = corpus_id
    return f"/search?{urlencode(params)}"


def concept_markup(concepts: list[dict], corpus_id: str = "") -> str:
    if not concepts:
        return ""
    items = []
    for concept in concepts:
        label_text = str(concept.get("label_ko") or concept.get("label") or concept.get("id", ""))
        term_text = str(concept.get("german") or (concept.get("label") if concept.get("label_ko") else "") or "")
        search_query = str(concept.get("search_query") or term_text or label_text).strip()
        label = html.escape(label_text)
        term = html.escape(term_text)
        description = html.escape(concept.get("description_ko") or concept.get("description", ""))
        if search_query:
            href = html.escape(concept_search_href(search_query, corpus_id), quote=True)
            text = f'<strong><a class="concept-link" href="{href}" aria-label="관련 본문 찾기: {label}">{label}</a></strong>'
        else:
            text = f"<strong>{label}</strong>"
        if term and term_text != label_text:
            text += f'<span class="concept-term">{term}</span>'
        if description:
            text += f"<small>{description}</small>"
        items.append(f"<li>{text}</li>")
    return f'<section class="research-card"><h2>개념</h2><ul class="concept-list">{"".join(items)}</ul></section>'


def variant_tabs_markup(variants: list[dict] | list[str]) -> str:
    if not variants:
        return ""
    items = []
    for variant in variants:
        if isinstance(variant, dict):
            label = html.escape(str(variant.get("label") or variant.get("id") or "Variant"))
            active = " active" if variant.get("active", True) else ""
            href = variant.get("href", "")
        else:
            label = html.escape(str(variant))
            active = " active"
            href = ""
        if href:
            items.append(f'<a class="variant-tab{active}" href="{html.escape(str(href), quote=True)}">{label}</a>')
        else:
            items.append(f'<span class="variant-tab{active}">{label}</span>')
    return f'<nav class="variant-tabs" aria-label="Text variants">{"".join(items)}</nav>'


def source_notice_markup(title: str, lines: list[str]) -> str:
    clean_lines = [line for line in lines if line]
    if not clean_lines:
        return ""
    items = "".join(f"<li>{html.escape(line)}</li>" for line in clean_lines)
    return f'<section class="research-card"><h2>{html.escape(title)}</h2><ul class="source-notes">{items}</ul></section>'


def variant_tabs_for_work(corpus_id: str, work_id: str, variants: list[dict], active_variant_id: str) -> str:
    tabs = []
    for variant in variants:
        variant_id = variant.get("variant_id", "")
        href = work_href(corpus_id, work_id)
        if variant_id:
            href += "?variant=" + quote(variant_id, safe="")
        tabs.append(
            {
                "label": variant.get("label") or variant_id,
                "href": href,
                "active": variant_id == active_variant_id,
            }
        )
    return variant_tabs_markup(tabs)


def apply_template(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def render_work_page_html(template: str, model: dict) -> str:
    research_json = json.dumps(model["research"], ensure_ascii=False).replace("</", "<\\/")
    toc_link = '<a href="#toc">목차</a>' if model.get("toc") else ""
    return apply_template(
        template,
        {
            "TITLE": html.escape(str(model.get("title", ""))),
            "CORPUS_TITLE": html.escape(str(model.get("corpus_title", ""))),
            "CORPUS_ID": html.escape(str(model.get("corpus_id", ""))),
            "WORK_ID": html.escape(str(model.get("work_id", ""))),
            "HEADER_META": html.escape(str(model.get("header_meta", ""))),
            "SECTION": html.escape(str(model.get("section", ""))),
            "META": html.escape(str(model.get("meta", ""))),
            "SOURCE_PATH": html.escape(str(model.get("source_path", ""))),
            "SOURCE_HREF": html.escape(str(model.get("source_href", "#")), quote=True),
            "CATEGORY_HREF": html.escape(str(model.get("category_href", "/")), quote=True),
            "TOC_LINK": toc_link,
            "TOC": str(model.get("toc", "")),
            "CONCEPTS": str(model.get("concepts", "")),
            "VARIANT_TABS": str(model.get("variant_tabs", "")),
            "HEADING_COUNT": str(model.get("heading_count", "0")),
            "SEGMENT_COUNT": str(model.get("segment_count", "0")),
            "CONTENT": str(model.get("content", "")),
            "BODY_CLASS": html.escape(str(model.get("body_class", ""))),
            "TEXT_DIRECTION": html.escape(str(model.get("text_direction", "ltr"))),
            "RESEARCH_JSON": html.escape(research_json, quote=False),
        },
    )
