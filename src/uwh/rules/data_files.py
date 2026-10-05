# ABOUTME: Reads the YAML files of `src/uwh/rules/data/`, the rules the interpreter runs on.
# ABOUTME: Each file is read once per process; the ruleset hash (A.4) covers the same directory.
from functools import cache
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).parent / "data"


@cache
def read_yaml(relative_path: str) -> Any:
    """The parsed content of `relative_path` under the rules data directory."""
    return yaml.safe_load((DATA_DIR / relative_path).read_text(encoding="utf-8"))
