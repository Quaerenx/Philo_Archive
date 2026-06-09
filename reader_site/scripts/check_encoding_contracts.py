from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
REPO = SITE.parent
sys.path.insert(0, str(SITE))

from path_config import SOURCE_ROOT_NAMES  # noqa: E402

KOREAN_SOURCE_ROOTS = list(SOURCE_ROOT_NAMES)

BINARY_SUFFIXES = {
    ".bmp",
    ".db",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".sqlite",
    ".webp",
}

REQUIRED_ROOT_REFERENCES = {
    ".gitignore": [f"{root}/" for root in KOREAN_SOURCE_ROOTS],
    "README.md": [f"{root}/" for root in KOREAN_SOURCE_ROOTS],
    "reader_site/docs/release_handoff.md": [f"`{root}/`" for root in KOREAN_SOURCE_ROOTS],
    "reader_site/docs/encoding_policy.md": [f"`{root}`" for root in KOREAN_SOURCE_ROOTS],
    "reader_site/path_config.py": KOREAN_SOURCE_ROOTS,
}

MOJIBAKE_NEEDLES = [
    "?덉껜",
    "?먯꽌",
    "?섏쭛",
    "?깃꼍",
    "?ㅻⅤ",
    "鍮꾪듃",
    "寃먯뒋",
    "怨좊Ⅴ",
    "李?",
    "異?",
    "?붿씪",
    "?댁쟾",
    "\ufffd",
]

ALLOWED_REPLACEMENT_CHAR_FILES = {
    "reader_site/RESEARCH_UPGRADE_ROADMAP.md",
}
SELF_RELATIVE_PATH = "reader_site/scripts/check_encoding_contracts.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True)


def tracked_paths() -> list[str]:
    raw = run_git("ls-files", "-z").stdout
    return [
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in raw.split(b"\0")
        if item
    ]


def changed_paths() -> list[str]:
    raw = run_git("status", "--porcelain=v1", "-z", "-uall").stdout
    parts = [part for part in raw.split(b"\0") if part]
    paths: list[str] = []
    index = 0
    while index < len(parts):
        entry = parts[index].decode("utf-8", errors="surrogateescape")
        status = entry[:2]
        path = entry[3:].replace("\\", "/")
        if "R" in status or "C" in status:
            index += 1
            if index < len(parts):
                path = parts[index].decode("utf-8", errors="surrogateescape").replace("\\", "/")
        paths.append(path)
        index += 1
    return paths


def is_binary_candidate(relative_path: str, data: bytes) -> bool:
    if Path(relative_path).suffix.lower() in BINARY_SUFFIXES:
        return True
    return b"\0" in data[:4096]


def read_tracked_text_files() -> dict[str, str]:
    texts: dict[str, str] = {}
    for relative_path in sorted(set(tracked_paths()) | set(changed_paths())):
        absolute = REPO / relative_path
        if not absolute.is_file():
            continue
        data = absolute.read_bytes()
        if is_binary_candidate(relative_path, data):
            continue
        try:
            texts[relative_path] = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AssertionError(f"{relative_path} is not valid UTF-8 text") from exc
    return texts


def check_required_root_references(texts: dict[str, str]) -> None:
    for relative_path, required_values in REQUIRED_ROOT_REFERENCES.items():
        require(relative_path in texts, f"missing tracked file for encoding contract: {relative_path}")
        text = texts[relative_path]
        for value in required_values:
            require(value in text, f"{relative_path} missing Korean root reference {value!r}")


def check_no_mojibake_fragments(texts: dict[str, str]) -> None:
    failures: list[str] = []
    for relative_path, text in texts.items():
        if relative_path == SELF_RELATIVE_PATH:
            continue
        for needle in MOJIBAKE_NEEDLES:
            if needle not in text:
                continue
            if needle == "\ufffd" and relative_path in ALLOWED_REPLACEMENT_CHAR_FILES:
                continue
            failures.append(f"{relative_path}: {needle!r}")
    require(not failures, "mojibake fragments found: " + ", ".join(failures))


def check_local_source_root_names() -> None:
    existing = [
        child.name
        for child in REPO.iterdir()
        if child.is_dir() and child.name.endswith("_원서수집")
    ]
    unexpected = sorted(set(existing) - set(KOREAN_SOURCE_ROOTS))
    require(not unexpected, "unexpected Korean source-root directories: " + ", ".join(unexpected))


def main() -> None:
    require((REPO / ".git").exists(), "encoding contracts require a Git checkout")
    texts = read_tracked_text_files()
    check_required_root_references(texts)
    check_no_mojibake_fragments(texts)
    check_local_source_root_names()
    print(f"encoding contracts ok ({len(texts)} tracked text files)")


if __name__ == "__main__":
    main()
