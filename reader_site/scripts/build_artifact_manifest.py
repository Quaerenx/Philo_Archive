from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))

from runtime_status import build_artifact_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write or check a local manifest for generated reader-site artifacts.",
        allow_abbrev=False,
    )
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate manifest generation and any existing output JSON without writing.",
    )
    args = parser.parse_args()

    manifest = build_artifact_manifest(include_checksums=args.checksums)
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if args.output.exists():
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            if existing.get("schema_version") != manifest.get("schema_version"):
                raise SystemExit(f"{args.output} has an unexpected schema_version")
            if not isinstance(existing.get("artifacts"), list):
                raise SystemExit(f"{args.output} does not contain an artifacts list")
        print(f"artifact manifest check ok ({args.output})")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
