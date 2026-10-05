# ABOUTME: Tests the autonomy level of a command class (7.4) and the approval binding check: defaults, locked classes, a stored `off`, and each of the five bound values breaking an approval alone.
# ABOUTME: Levels are read from a real settings table through open_store at a tmp_path file; the binding tests compare plain values.
import json
import sqlite3
from dataclasses import fields, replace
from pathlib import Path

import pytest

from uwh.runtime.policy import ApprovalBinding, autonomy_level, binding_changes
from uwh.runtime.store import open_store
from uwh.skills.vertical import COMMAND_CLASSES, CommandClass

SEND_CLASSES = [c for c in COMMAND_CLASSES if c.default_level is not None]
HUMAN_ONLY = [c for c in COMMAND_CLASSES if c.default_level is None]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "app.db"))


def store_level(db: sqlite3.Connection, name: str, level: str) -> None:
    db.execute(
        "INSERT INTO settings (key, value_json) VALUES (?, ?)",
        (f"autonomy.{name}", json.dumps(level)),
    )


def test_the_defaults_are_those_of_the_7_4_table(db: sqlite3.Connection) -> None:
    levels = {c.name: autonomy_level(db, c.name) for c in SEND_CLASSES}

    assert levels == {
        "fetch_data": "auto",
        "send_routine_request": "auto",
        "send_sensitive_request": "review",
        "send_quote_packet": "review",
        "send_decline_notice": "review",
        "deliver_reply": "auto",
        "propose_command": "auto",
    }


def test_a_stored_level_replaces_the_default(db: sqlite3.Connection) -> None:
    store_level(db, "send_routine_request", "review")
    store_level(db, "send_sensitive_request", "auto")

    assert autonomy_level(db, "send_routine_request") == "review"
    assert autonomy_level(db, "send_sensitive_request") == "auto"


def test_a_stored_off_is_off(db: sqlite3.Connection) -> None:
    store_level(db, "fetch_data", "off")

    assert autonomy_level(db, "fetch_data") == "off"


@pytest.mark.parametrize(
    "command_class", [c for c in SEND_CLASSES if c.locked], ids=lambda c: c.name
)
def test_a_locked_class_never_runs_at_auto(
    db: sqlite3.Connection, command_class: CommandClass
) -> None:
    store_level(db, command_class.name, "auto")

    assert autonomy_level(db, command_class.name) == "review"


def test_a_locked_class_stored_as_off_stays_off(db: sqlite3.Connection) -> None:
    store_level(db, "send_quote_packet", "off")

    assert autonomy_level(db, "send_quote_packet") == "off"


@pytest.mark.parametrize("command_class", HUMAN_ONLY, ids=lambda c: c.name)
def test_a_human_only_class_has_no_level(
    db: sqlite3.Connection, command_class: CommandClass
) -> None:
    with pytest.raises(ValueError, match="has no autonomy level"):
        autonomy_level(db, command_class.name)


def test_an_unknown_class_has_no_level(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="unknown command class"):
        autonomy_level(db, "send_postcard")


def test_a_stored_value_outside_the_levels_is_refused(db: sqlite3.Connection) -> None:
    store_level(db, "fetch_data", "sometimes")

    with pytest.raises(ValueError, match="not an autonomy level"):
        autonomy_level(db, "fetch_data")


APPROVED = ApprovalBinding(
    lead_revision=3,
    plan_hash="p" * 64,
    ruleset_hash="r" * 64,
    recipient="producer@example.com",
    payload_hash="h" * 64,
)
CHANGED_VALUES: dict[str, object] = {
    "lead_revision": 4,
    "plan_hash": "q" * 64,
    "ruleset_hash": "s" * 64,
    "recipient": "other@example.com",
    "payload_hash": "i" * 64,
}


def test_the_binding_names_the_five_bound_values() -> None:
    assert [f.name for f in fields(ApprovalBinding)] == list(CHANGED_VALUES)


def test_an_unchanged_binding_holds() -> None:
    assert binding_changes(APPROVED, replace(APPROVED)) == ()


@pytest.mark.parametrize("name", CHANGED_VALUES)
def test_each_bound_value_changing_alone_breaks_the_approval(name: str) -> None:
    current = replace(APPROVED, **{name: CHANGED_VALUES[name]})

    assert binding_changes(APPROVED, current) == (name,)


def test_several_changes_are_all_named() -> None:
    current = replace(APPROVED, lead_revision=9, recipient="other@example.com")

    assert binding_changes(APPROVED, current) == ("lead_revision", "recipient")
