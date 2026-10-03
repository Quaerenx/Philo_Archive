from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


ARTIFACT_NAMES = (
    "nietzsche_metadata.json", "bible_metadata.json", "kierkegaard_metadata.json",
    "wittgenstein_metadata.json", "nietzsche_segments.jsonl", "bible_segments.jsonl",
    "kierkegaard_segments.jsonl", "wittgenstein_segments.jsonl", "segment_offset_index.sqlite",
    "archive_catalog.local.json", "search_index.jsonl", "search_index.sqlite",
    "artifact_manifest.local.json",
)


def preflight_registered_sources(data: Path, source_root: Path) -> None:
    """Reject a partial source tree before metadata builders can forget missing works."""
    for corpus in ("nietzsche", "bible", "kierkegaard", "wittgenstein"):
        metadata = data / f"{corpus}_metadata.json"
        if not metadata.is_file():
            continue
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        for work_id, work in payload.get("works", {}).items():
            for variant in work.get("variants") or [work]:
                source = variant.get("source_path")
                if source and not (source_root / source).is_file():
                    raise FileNotFoundError(f"registered source is missing: {corpus}/{work_id}/{variant.get('variant_id', '')}")


def restore_file(source: Path, target: Path) -> None:
    for attempt in range(20):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


@contextmanager
def preserve_artifacts(data: Path) -> Iterator[None]:
    """Restore the previous derived artifacts if a build/check fails or is interrupted."""
    data = data.resolve()
    data.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=".rebuild-backup-", dir=data)).resolve()
    backup.relative_to(data)
    keep_backup = False
    existing: set[str] = set()
    try:
        for name in ARTIFACT_NAMES:
            target = data / name
            if target.is_symlink() or target.resolve().parent != data:
                raise ValueError(f"unsafe generated artifact: {name}")
            if target.exists():
                shutil.copy2(target, backup / name)
                existing.add(name)
        try:
            yield
        except BaseException:
            failures = []
            for name in ARTIFACT_NAMES:
                try:
                    if name in existing:
                        restore_file(backup / name, data / name)
                    else:
                        (data / name).unlink(missing_ok=True)
                except OSError as error:
                    failures.append(f"{name}: {error}")
            if failures:
                keep_backup = True
                raise RuntimeError(f"rebuild rollback incomplete; backup retained at {backup}: {'; '.join(failures)}")
            raise
    finally:
        if not keep_backup:
            backup.relative_to(data)
            shutil.rmtree(backup)
