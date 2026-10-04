# ABOUTME: Checks repository-wide writing rules that tools like ruff do not cover.
# ABOUTME: Fails on temporal vocabulary, missing ABOUTME headers, and source files without a test file.
"""Run from the repository root: python3 scripts/check_discipline.py"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXEMPT_PREFIXES = (
    "sim-harness/",
    "docs/brief/",
    "docs/playbook/",
    ".agents/",
    ".claude/",
    "web/node_modules/",
    "recordings/",
    "fixtures/replies/",
)
EXEMPT_FILES = {"AGENTS.md", "CLAUDE.md", "scripts/check_discipline.py", "uv.lock", "web/pnpm-lock.yaml"}

TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".ts", ".tsx", ".sh", ".toml", ".css"}
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".sh"}

TEMPORAL = re.compile(
    r"\b(initially|previously|originally|formerly|recently|no longer|used to be|"
    r"refactored|was changed|has been changed|as before|old behaviou?r|backwards? compat\w*)\b",
    re.IGNORECASE,
)


def tracked_and_untracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def exempt(path: str) -> bool:
    return path in EXEMPT_FILES or path.startswith(EXEMPT_PREFIXES)


def main() -> int:
    problems: list[str] = []
    paths = [p for p in tracked_and_untracked() if not exempt(p) and (ROOT / p).is_file()]

    for rel in paths:
        file = ROOT / rel
        if file.suffix not in TEXT_SUFFIXES:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            match = TEMPORAL.search(line)
            if match:
                problems.append(f"{rel}:{number}: temporal language: '{match.group(0)}'")
        if file.suffix in CODE_SUFFIXES and file.name != "__init__.py" and text.strip():
            head = [line for line in text.splitlines()[:6] if "ABOUTME: " in line]
            if len(head) < 2:
                problems.append(f"{rel}:1: missing two-line ABOUTME header")

    test_names = {Path(p).name for p in paths if p.startswith("tests/")}
    for rel in paths:
        path = Path(rel)
        if rel.startswith("src/uwh/") and path.suffix == ".py" and path.name != "__init__.py":
            if f"test_{path.name}" not in test_names:
                problems.append(f"{rel}: no tests/**/test_{path.name}")

    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} discipline problem(s).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
