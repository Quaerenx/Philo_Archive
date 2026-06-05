from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from runtime_status import build_artifact_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a local manifest for generated reader-site artifacts.")
    parser.add_argument(
        "--output",
        type=Path,
        default=SITE / "data" / "artifact_manifest.local.json",
        help="Output JSON path. Defaults to data/artifact_manifest.local.json.",
    )
    parser.add_argument(
        "--checksums",
        action="store_true",
        help="Include SHA-256 checksums. This reads large local search and segment artifacts.",
    )
    args = parser.parse_args()

    manifest = build_artifact_manifest(include_checksums=args.checksums)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
