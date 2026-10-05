# ABOUTME: The facts of a seed-42 lead as the playbook tests start from them: the captured fields, the facts the first pass adds, and the changes a test names.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
import json
from pathlib import Path

from pydantic import JsonValue

WORLD = Path(__file__).resolve().parents[2] / "src/uwh/providers/data/world-42.json"


def lead_008(**changes: JsonValue) -> dict[str, JsonValue]:
    fields = json.loads(WORLD.read_text(encoding="utf-8"))["leads"]["LEAD-00000042-008"]["fields"]
    facts = {name: value for name, value in fields.items() if value is not None}
    # What the first pass adds: the derived siding class and the fetched replacement cost. A change
    # to None makes the fact unknown.
    merged = {**facts, "siding_classification": "B", "replacement_cost": 928992, **changes}
    return {name: value for name, value in merged.items() if value is not None}
