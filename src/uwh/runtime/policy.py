# ABOUTME: The autonomy level of a command class (7.4), from the settings table or the class's default with a locked class never at auto, and the check of an approval's five bound values.
# ABOUTME: Pure checks over the settings table and two bindings; the stop, the send and the decision to dispatch belong to other modules.
import json
import sqlite3
from dataclasses import dataclass, fields
from typing import cast, get_args

from uwh.runtime.event_types import AutonomyLevel
from uwh.skills import vertical


def autonomy_level(db: sqlite3.Connection, command_class: str) -> AutonomyLevel:
    """The level of the class: the setting `autonomy.<class>` when stored, else its default.

    A locked class stored as `auto` runs at `review`. A level of `off` means the class is refused.
    Raises ValueError for an unknown class, a human-only class (no level applies) and a stored value
    that is not a level.
    """
    declared = vertical.command_class(command_class)
    if declared is None:
        raise ValueError(f"unknown command class {command_class}")
    if declared.default_level is None:
        raise ValueError(f"{command_class} has no autonomy level")
    row = db.execute(
        "SELECT value_json FROM settings WHERE key = ?", (f"autonomy.{command_class}",)
    ).fetchone()
    level = declared.default_level
    if row is not None:
        stored = json.loads(row[0])
        if stored not in get_args(AutonomyLevel):
            raise ValueError(f"{stored!r} is not an autonomy level")
        level = cast(AutonomyLevel, stored)
    if level == "auto" and declared.locked:
        return "review"
    return level


@dataclass(frozen=True)
class ApprovalBinding:
    """The five values an approval binds to (7.4): the lead revision, the action-plan hash, the ruleset
    hash, the recipient and the payload hash of the exact message or packet."""

    lead_revision: int
    plan_hash: str
    ruleset_hash: str
    recipient: str
    payload_hash: str


def binding_changes(approved: ApprovalBinding, current: ApprovalBinding) -> tuple[str, ...]:
    """The names of the bound values that differ from those approved; empty when the approval still holds."""
    return tuple(
        field.name
        for field in fields(ApprovalBinding)
        if getattr(approved, field.name) != getattr(current, field.name)
    )
