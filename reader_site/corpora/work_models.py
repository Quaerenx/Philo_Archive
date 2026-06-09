from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from corpora.catalogs import (
    bible_segments_for_work,
    concepts_for_work,
    nietzsche_catalog_record,
    nietzsche_metadata_record,
    resolve_bible_work,
    resolve_metadata_work,
    resolve_nietzsche_work,
)
from path_config import CORPUS_ROOTS, ROOT, SITE
from rendering.documents import (
    kierkegaard_extract_texts,
    readable_markdown_text,
    render_bible_work_document,
    render_reading_document,
    render_segments_from_texts,
    title_from_markdown,
)
from rendering.work_markup import concept_markup, source_notice_markup, toc_markup, variant_tabs_for_work, variant_tabs_markup


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def relative_source_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def source_href(path: Path) -> str:
    return "/source?path=" + quote(relative_source_path(path), safe="")


def selected_variant(work: dict, variant_id: str, preferred: list[str]) -> dict:
    variants = work.get("variants", [])
    if variant_id:
        for variant in variants:
            if variant.get("variant_id") == variant_id:
                return variant
    for preferred_id in preferred:
        for variant in variants:
            current_id = variant.get("variant_id", "")
            if current_id == preferred_id or current_id.startswith(f"{preferred_id}."):
                return variant
    if not variants:
        raise FileNotFoundError("variant not found")
    return variants[0]


def variant_source_path(variant: dict) -> Path:
    source_path = variant.get("source_path", "")
    if not source_path:
        raise FileNotFoundError("variant source not found")
    target = (ROOT / source_path).resolve()
    if not any(is_inside(target, root.resolve()) for root in CORPUS_ROOTS):
        raise PermissionError("source path is outside allowed corpus roots")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("variant source not found")
    return target


def build_nietzsche_work_model(work_id: str) -> dict:
    target = resolve_nietzsche_work(work_id)
    record = nietzsche_catalog_record(work_id)
    metadata = nietzsche_metadata_record(work_id)
    concepts = concepts_for_work(work_id)
    text = target.read_text(encoding="utf-8", errors="replace")
    document = render_reading_document(text)
    rel_path = relative_source_path(target)
    title_raw = metadata.get("title") or record.get("label") or title_from_markdown(target)
    research_payload = {
        "author": "Friedrich Nietzsche",
        "author_id": "nietzsche",
        "work_id": work_id,
        "title": title_raw,
        "meta": record.get("meta") or work_id,
        "section": record.get("section_title") or "Works",
        "source_path": rel_path,
    }
    return {
        "corpus_id": "nietzsche",
        "corpus_title": "Nietzsche",
        "category_href": "/category/nietzsche",
        "title": title_raw,
        "work_id": work_id,
        "section": record.get("section_title") or "Works",
        "meta": record.get("meta") or work_id,
        "source_path": rel_path,
        "source_href": source_href(target),
        "toc": toc_markup(document["toc"]),
        "concepts": concept_markup(concepts),
        "variant_tabs": "",
        "heading_count": str(int(document["heading_count"])),
        "segment_count": str(int(document["paragraph_count"])),
        "content": str(document["html"]),
        "body_class": "nietzsche-work",
        "text_direction": "ltr",
        "research": research_payload,
    }


def build_bible_work_model(work_id: str) -> dict:
    work = resolve_bible_work(work_id)
    segments = bible_segments_for_work(work_id)
    if not segments:
        raise FileNotFoundError("segments not found")
    document = render_bible_work_document(work, segments)
    source_path = work.get("source_path", "")
    research_payload = {
        "author": work.get("source_label") or work.get("source_id") or "Bible",
        "author_id": "bible",
        "corpus_id": "bible",
        "corpus_title": "Bible",
        "work_id": work_id,
        "variant_id": work.get("variant_id") or work.get("source_id") or "",
        "title": work.get("display_title") or work.get("title") or work_id,
        "citation_title": document["title_for_citation"],
        "source_label": work.get("source_label") or work.get("source_id") or "",
        "default_target_type": "verse",
        "source_path": source_path,
    }
    return {
        "corpus_id": "bible",
        "corpus_title": "Bible",
        "category_href": "/category/bible",
        "title": work.get("display_title") or work.get("title") or work_id,
        "work_id": work_id,
        "section": work.get("category_title") or "Bible",
        "meta": work.get("source_label") or work.get("source_id") or work_id,
        "source_path": source_path,
        "source_href": work.get("source_url") or "#",
        "toc": toc_markup(document["toc"]),
        "concepts": "",
        "variant_tabs": variant_tabs_markup(
            [{"id": work.get("variant_id"), "label": work.get("source_label") or work.get("source_id")}]
        ),
        "heading_count": str(int(document["heading_count"])),
        "segment_count": str(int(document["paragraph_count"])),
        "content": str(document["html"]),
        "body_class": "bible-work",
        "text_direction": "ltr",
        "research": research_payload,
    }


def build_kierkegaard_work_model(work_id: str, variant_id: str = "") -> dict:
    work = resolve_metadata_work("kierkegaard", work_id)
    variant = selected_variant(work, variant_id, ["text", "commentary", "textual_account"])
    target = variant_source_path(variant)
    texts = kierkegaard_extract_texts(target)
    document = render_segments_from_texts(texts, "sks")
    active_variant_id = variant.get("variant_id", "")
    source_path = variant.get("source_path", "")
    title = work.get("display_title") or work.get("title") or work_id
    research_payload = {
        "author": work.get("author") or "Søren Kierkegaard",
        "author_id": "kierkegaard",
        "corpus_id": "kierkegaard",
        "corpus_title": "Kierkegaard",
        "work_id": work_id,
        "variant_id": active_variant_id,
        "title": title,
        "source_label": variant.get("label") or active_variant_id,
        "default_target_type": "paragraph",
        "source_path": source_path,
    }
    notice = source_notice_markup(
        "Source",
        [
            work.get("volume", ""),
            variant.get("label", ""),
            work.get("license", ""),
            variant.get("source_xml", ""),
        ],
    )
    return {
        "corpus_id": "kierkegaard",
        "corpus_title": "Kierkegaard",
        "category_href": "/category/kierkegaard",
        "title": title,
        "work_id": work_id,
        "section": work.get("category_title") or "Søren Kierkegaards Skrifter",
        "meta": variant.get("label") or active_variant_id,
        "source_path": source_path,
        "source_href": variant.get("source_url") or source_href(target),
        "toc": toc_markup(document["toc"]),
        "concepts": notice,
        "variant_tabs": variant_tabs_for_work("kierkegaard", work_id, work.get("variants", []), active_variant_id),
        "heading_count": str(int(document["heading_count"])),
        "segment_count": str(int(document["paragraph_count"])),
        "content": str(document["html"]),
        "body_class": "kierkegaard-work",
        "text_direction": "ltr",
        "research": research_payload,
    }


def build_wittgenstein_work_model(work_id: str, variant_id: str = "") -> dict:
    work = resolve_metadata_work("wittgenstein", work_id)
    variant = selected_variant(
        work,
        variant_id,
        [
            "source_transcription_normalized",
            "source_transcription_diplomatic",
            "idp_transcription_linear",
            "idp_transcription_diplomatic",
            "source_metadata",
        ],
    )
    target = variant_source_path(variant)
    text = target.read_text(encoding="utf-8", errors="replace")
    document = render_segments_from_texts([readable_markdown_text(text)], "p")
    active_variant_id = variant.get("variant_id", "")
    source_path = variant.get("source_path", "")
    title = work.get("display_title") or work.get("title") or work_id
    research_payload = {
        "author": work.get("author") or "Ludwig Wittgenstein",
        "author_id": "wittgenstein",
        "corpus_id": "wittgenstein",
        "corpus_title": "Wittgenstein",
        "work_id": work_id,
        "variant_id": active_variant_id,
        "title": title,
        "source_label": variant.get("label") or active_variant_id,
        "default_target_type": "paragraph",
        "source_path": source_path,
    }
    notice = source_notice_markup(
        "Rights",
        [
            variant.get("label", ""),
            variant.get("license", ""),
            variant.get("rights_note", ""),
            variant.get("external_source_url", ""),
        ],
    )
    return {
        "corpus_id": "wittgenstein",
        "corpus_title": "Wittgenstein",
        "category_href": "/category/wittgenstein",
        "title": title,
        "work_id": work_id,
        "section": work.get("category_title") or "Wittgenstein Archive",
        "meta": variant.get("label") or active_variant_id,
        "source_path": source_path,
        "source_href": variant.get("source_url") or source_href(target),
        "toc": toc_markup(document["toc"]),
        "concepts": notice,
        "variant_tabs": variant_tabs_for_work("wittgenstein", work_id, work.get("variants", []), active_variant_id),
        "heading_count": str(int(document["heading_count"])),
        "segment_count": str(int(document["paragraph_count"])),
        "content": str(document["html"]),
        "body_class": "wittgenstein-work",
        "text_direction": "ltr",
        "research": research_payload,
    }
