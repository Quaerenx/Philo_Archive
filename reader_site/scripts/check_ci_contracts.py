from __future__ import annotations

from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
WORKFLOW = REPO / ".github" / "workflows" / "reader-site-source-light.yml"


REQUIRED_SNIPPETS = [
    "name: Reader Site Source-Light Checks",
    "pull_request:",
    "push:",
    "permissions:",
    "contents: read",
    "runs-on: ubuntu-latest",
    "actions/checkout@v6",
    "actions/setup-python@v6",
    'python-version: "3.13"',
    "PHILOSOPHY_CRAWL_ROOT:",
    "python scripts/check_clean_clone_contracts.py --run-source-light-checks",
]

FORBIDDEN_SNIPPETS = [
    "rebuild_all.py",
    "check_corpus_schema.py",
    "check_search_contracts.py",
    "check_static_routes.py",
    "check_visual_smoke.py",
    "git push",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(WORKFLOW.exists(), "missing source-light GitHub Actions workflow")
    text = WORKFLOW.read_text(encoding="utf-8")
    for snippet in REQUIRED_SNIPPETS:
        require(snippet in text, f"workflow missing {snippet!r}")
    for snippet in FORBIDDEN_SNIPPETS:
        require(snippet not in text, f"workflow should not run source-heavy command {snippet!r}")
    print("ci contracts ok")


if __name__ == "__main__":
    main()
