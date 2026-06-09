from __future__ import annotations

import os
from pathlib import Path


SITE = Path(__file__).resolve().parent
REPO = SITE.parent
CORPUS_ROOT_ENV = "PHILOSOPHY_CRAWL_ROOT"
ROOT = Path(os.environ.get(CORPUS_ROOT_ENV, REPO)).resolve()

SOURCE_ROOT_NAMES = (
    "니체_원서수집",
    "비트겐슈타인_원서수집",
    "성경_원서수집",
    "키르케고르_원서수집",
)

NIETZSCHE_SOURCE_ROOT = ROOT / "니체_원서수집"
WITTGENSTEIN_SOURCE_ROOT = ROOT / "비트겐슈타인_원서수집"
BIBLE_SOURCE_ROOT = ROOT / "성경_원서수집"
KIERKEGAARD_SOURCE_ROOT = ROOT / "키르케고르_원서수집"

CORPUS_ROOTS = (
    NIETZSCHE_SOURCE_ROOT,
    WITTGENSTEIN_SOURCE_ROOT,
    BIBLE_SOURCE_ROOT,
    KIERKEGAARD_SOURCE_ROOT,
)

NIETZSCHE_OUTPUT = NIETZSCHE_SOURCE_ROOT / "nietzsche" / "nietzsche" / "output"
WITTGENSTEIN_OUTPUT = WITTGENSTEIN_SOURCE_ROOT / "wittgenstein" / "wittgenstein" / "output"
BIBLE_OUTPUT = BIBLE_SOURCE_ROOT / "bible" / "bible" / "output"
KIERKEGAARD_TEXTS = (
    KIERKEGAARD_SOURCE_ROOT
    / "kierkegaard"
    / "kierkegaard"
    / "data"
    / "kierkegaard"
    / "raw"
    / "texts"
)

PRIMARY_OUTPUTS = {
    "nietzsche": NIETZSCHE_OUTPUT,
    "bible": BIBLE_OUTPUT,
    "kierkegaard": KIERKEGAARD_TEXTS,
    "wittgenstein": WITTGENSTEIN_OUTPUT,
}
