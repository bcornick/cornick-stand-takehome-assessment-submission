# ABOUTME: Tests that the vertical tables hold the architecture's terminal statuses, blocker priority, transitions, command classes and persistent review causes.
# ABOUTME: Every expected value is written out here from the architecture tables, not read back from the module under test.
from datetime import UTC, datetime
from typing import get_args

from uwh.runtime.event_types import Actor, AutonomyLevel
from uwh.skills import vertical

# Section 7.4 table: class -> (default level, locked, who may submit). A class with no default level is human only.
EXPECTED_COMMAND_CLASSES = {
    "fetch_data": ("auto", False, ("workflow",)),
    "send_routine_request": ("auto", False, ("workflow",)),
    "send_sensitive_request": ("review", False, ("workflow",)),
    "send_quote_packet": ("review", True, ("workflow",)),
    "send_decline_notice": ("review", True, ("workflow",)),
    "deliver_reply": ("auto", False, ("inbound", "underwriter")),
    "approve": (None, False, ("underwriter",)),
    "reject": (None, False, ("underwriter",)),
    "edit_draft": (None, False, ("underwriter",)),
    "resolve_fact": (None, False, ("underwriter",)),
    "decline_lead": (None, False, ("underwriter",)),
    "record_ruling": (None, False, ("underwriter",)),
    "propose_rule_change": (None, False, ("underwriter",)),
    "apply_rule_change": (None, False, ("underwriter",)),
    "change_setting": (None, False, ("underwriter",)),
    "emergency_stop": (None, False, ("underwriter",)),
    "start_run": (None, False, ("underwriter",)),
    "propose_command": ("auto", False, ("assistant", "mcp_client")),
}


def test_terminal_statuses() -> None:
    assert vertical.TERMINAL_STATUSES == ("quote_sent", "declined")


def test_blocker_kinds_in_priority_order() -> None:
    assert vertical.BLOCKER_KINDS_BY_PRIORITY == (
        "delivery_unknown",
        "underwriter_question",
        "underwriter_review",
        "data",
        "producer_reply",
    )


def test_transitions() -> None:
    assert set(vertical.TRANSITIONS) == {
        ("received", "triaged"),
        ("triaged", "in_progress"),
        ("in_progress", "in_progress"),
        ("in_progress", "quote_sent"),
        ("in_progress", "declined"),
    }


def test_command_classes() -> None:
    actual = {c.name: (c.default_level, c.locked, c.actors) for c in vertical.COMMAND_CLASSES}
    assert actual == EXPECTED_COMMAND_CLASSES
    assert len(vertical.COMMAND_CLASSES) == len(EXPECTED_COMMAND_CLASSES)


def test_each_command_class_is_submitted_by_actors_and_has_a_level_of_their_sets() -> None:
    for command_class in vertical.COMMAND_CLASSES:
        assert set(command_class.actors) <= set(get_args(Actor))
        assert command_class.default_level in (*get_args(AutonomyLevel), None)


# A.11's two review rows: an event raised the other causes and `approve` closes them; these three
# persist until they are removed.
def test_the_review_causes_that_persist_are_the_three_of_a11() -> None:
    assert vertical.PERSISTING_REVIEW_CAUSES == frozenset(
        {"round_limit", "identity_score_missing", "identity_score_unsupported"}
    )


def test_confirmation_only_class_is_routine_request() -> None:
    # 10.1: the class takes one of the two request kinds, and is set to routine_request.
    assert vertical.CONFIRMATION_ONLY_CLASS == "routine_request"


def test_reference_morning() -> None:
    assert vertical.REFERENCE_MORNING == datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
    assert vertical.REFERENCE_MORNING.utcoffset() is not None
    assert vertical.REFERENCE_MORNING.strftime("%A") == "Monday"
