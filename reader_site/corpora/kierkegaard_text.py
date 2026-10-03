from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path


EXTRACT_FIELDS = ("prose_extract_tesim", "verse_extract_tesim", "performance_extract_tesim", "text_tesim")


def has_readable_text(texts: list[str]) -> bool:
    return any(text.strip() and not re.fullmatch(r"[A-Z0-9_-]+:\d+(?::\d+)*", text.strip()) for text in texts)


def json_extracts(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8")).get("response", {}).get("document", {})
    for key in EXTRACT_FIELDS:
        value = document.get(key)
        values = value if isinstance(value, list) else [value] if value else []
        texts = [str(item).strip() for item in values if item and str(item).strip()]
        if texts:
            return texts
    return []


def reading_source_path(path: Path) -> Path:
    """Retain existing JSON targets; use the corresponding HTML when no extracts exist."""
    if path.suffix.lower() != ".json" or json_extracts(path):
        return path
    sibling = path.with_suffix(".html")
    if sibling.is_file() and sibling.resolve().parent == path.resolve().parent:
        return sibling
    return path


class SKSTextParser(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote", "br", "hr"}
    SKIP_TAGS = {"script", "style", "noscript", "button", "form", "nav", "footer", "header", "sup", "small", "svg"}
    SKIP_CLASSES = {"modal", "textToolbar", "debug", "symbol", "pagination", "comment-stuff", "info-stuff", "apparatus-criticus", "hidden"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.parts: list[str] = []
        self.blocks: list[str] = []

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        if text:
            self.blocks.append(text)
        self.parts.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        ident = attributes.get("id") or ""
        active = (self.stack[-1][1] if self.stack else False) or "collection-sks" in classes or (tag == "article" and "ocr" in classes)
        skipped = (self.stack[-1][2] if self.stack else False) or tag in self.SKIP_TAGS or bool(classes & self.SKIP_CLASSES)
        skipped = skipped or ident.startswith("expose_link_") or bool(re.fullmatch(r"s{1,2}[0-9ivxlcdmIVXLCDM]+", ident))
        if active and not skipped and tag in self.BLOCK_TAGS:
            self.flush()
        if tag not in self.VOID_TAGS:
            self.stack.append((tag, active, skipped))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                _, active, skipped = self.stack[index]
                if active and not skipped and tag in self.BLOCK_TAGS:
                    self.flush()
                del self.stack[index:]
                break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(data)


def extract_texts(path: Path) -> list[str]:
    source = reading_source_path(path)
    if source.suffix.lower() == ".json":
        return json_extracts(source)
    parser = SKSTextParser()
    parser.feed(source.read_text(encoding="utf-8"))
    parser.close()
    parser.flush()
    return parser.blocks
