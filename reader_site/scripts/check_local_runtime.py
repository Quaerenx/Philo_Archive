from __future__ import annotations

import argparse
import json
from urllib.error import URLError
from urllib.request import urlopen


def fetch_json(url: str, timeout: float = 5.0) -> tuple[bool, dict]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status == 200, json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return False, {"error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local Philo Archive reader and Gemma runtime.", allow_abbrev=False)
    parser.add_argument("--reader", default="http://127.0.0.1:8793", help="Reader base URL.")
    parser.add_argument("--gemma", default="http://127.0.0.1:8794", help="Gemma llama.cpp base URL.")
    parser.add_argument("--plain", action="store_true", help="Print a short human-readable status instead of JSON.")
    args = parser.parse_args()

    reader_ok, health = fetch_json(f"{args.reader.rstrip('/')}/api/health")
    gemma_ok, models = fetch_json(f"{args.gemma.rstrip('/')}/v1/models")
    summary = {
        "reader": {
            "ok": reader_ok,
            "url": args.reader,
            "status": health.get("status"),
            "issues": health.get("issues", []),
        },
        "gemma": {
            "ok": gemma_ok,
            "url": args.gemma,
            "model_count": len(models.get("data") or models.get("models") or []) if gemma_ok else 0,
            "error": "" if gemma_ok else models.get("error", ""),
        },
    }
    if args.plain:
        reader_label = "OK" if reader_ok else "NOT READY"
        gemma_label = "OK" if gemma_ok else "NOT READY"
        print(f"Reader: {reader_label} ({args.reader})")
        if health.get("issues"):
            print("Reader issues: " + "; ".join(str(item) for item in health.get("issues", [])))
        print(f"Local AI: {gemma_label} ({args.gemma})")
        if gemma_ok:
            print(f"Local AI models: {summary['gemma']['model_count']}")
        elif summary["gemma"].get("error"):
            print(f"Local AI error: {summary['gemma']['error']}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not reader_ok or not gemma_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
