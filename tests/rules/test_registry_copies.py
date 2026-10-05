# ABOUTME: Guards the copy of the field registry that the app image reads.
# ABOUTME: The brief copy and Stand's harness copy must be byte-identical.
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_field_registry_copies_are_byte_identical() -> None:
    brief = (ROOT / "docs/brief/field_registry.json").read_bytes()
    harness = (ROOT / "sim-harness/shared/field_registry.json").read_bytes()
    assert brief == harness
