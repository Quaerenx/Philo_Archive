from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from corpora.archive import ARCHIVE_CATALOG, ARCHIVE_SCHEMA_VERSION, build_archive_catalog  # noqa: E402


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the versioned local archive catalog used for cold Reader startup.",
        allow_abbrev=False,
    )
    parser.add_argument("--output", type=Path, default=ARCHIVE_CATALOG)
    parser.add_argument("--check", action="store_true", help="Build and validate in memory without writing.")
    args = parser.parse_args()

    catalog = build_archive_catalog()
    if catalog.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise SystemExit("archive catalog schema version mismatch")
    if not isinstance(catalog.get("archive", {}).get("corpora"), list):
        raise SystemExit("archive catalog has no corpora")
    if args.check:
        print(f"archive catalog check ok ({len(catalog['archive']['corpora'])} corpora)")
        return
    atomic_write_json(args.output, catalog)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
