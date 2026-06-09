from __future__ import annotations

from pathlib import Path

from corpora.work_models import (
    build_bible_work_model,
    build_kierkegaard_work_model,
    build_nietzsche_work_model,
    build_wittgenstein_work_model,
)
from rendering.work_markup import render_work_page_html


SITE = Path(__file__).resolve().parents[1]
TEMPLATES = SITE / "templates"


def build_work_page_model(corpus_id: str, work_id: str, variant_id: str = "") -> dict:
    if corpus_id == "bible":
        return build_bible_work_model(work_id)
    if corpus_id == "kierkegaard":
        return build_kierkegaard_work_model(work_id, variant_id)
    if corpus_id == "wittgenstein":
        return build_wittgenstein_work_model(work_id, variant_id)
    if corpus_id == "nietzsche":
        return build_nietzsche_work_model(work_id)
    raise FileNotFoundError("unknown corpus")


def build_work_page_html(corpus_id: str, work_id: str, variant_id: str = "") -> str:
    template = (TEMPLATES / "work.html").read_text(encoding="utf-8")
    return render_work_page_html(template, build_work_page_model(corpus_id, work_id, variant_id))
