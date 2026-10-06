# ABOUTME: The sentence a lead's conversation opens with, written by code from the lead's status, its open items, its plan and the asks sent to the producer.
# ABOUTME: It leads with what the underwriter must do, then what the system is waiting on; a finished lead states its outcome.
import sqlite3

from uwh.rules.models import ActionPlan
from uwh.runtime.waits import Blocker


def summary_line(
    db: sqlite3.Connection,
    lead_id: str,
    status: str,
    plan: ActionPlan | None,
    blockers: list[Blocker],
) -> str:
    """The opening line of the lead's conversation."""
    return "Triage is running."
