# ABOUTME: Tests that the vertical tables hold the architecture's terminal statuses, blocker priority, transitions, command classes and review causes.
# ABOUTME: Every expected value is written out here from the architecture tables, not read back from the module under test.
from datetime import UTC, datetime
from typing import get_args

from uwh.runtime.event_types import Actor, BlockerKind, ReviewCause
from uwh.skills import vertical

# Section 7.4 table: class -> (default level, locked, human only, who may submit).
EXPECTED_COMMAND_CLASSES = {
    "fetch_data": ("auto", False, False, ("workflow",)),
    "send_routine_request": ("auto", False, False, ("workflow",)),
    "send_sensitive_request": ("review", False, False, ("workflow",)),
    "send_quote_packet": ("review", True, False, ("workflow",)),
    "send_decline_notice": ("review", True, False, ("workflow",)),
    "deliver_reply": ("auto", False, False, ("inbound", "underwriter")),
    "approve": (None, False, True, ("underwriter",)),
    "reject": (None, False, True, ("underwriter",)),
    "edit_draft": (None, False, True, ("underwriter",)),
    "resolve_fact": (None, False, True, ("underwriter",)),
    "decline_lead": (None, False, True, ("underwriter",)),
    "record_ruling": (None, False, True, ("underwriter",)),
    "propose_rule_change": (None, False, True, ("underwriter",)),
    "apply_rule_change": (None, False, True, ("underwriter",)),
    "change_setting": (None, False, True, ("underwriter",)),
    "emergency_stop": (None, False, True, ("underwriter",)),
    "start_run": (None, False, True, ("underwriter",)),
    "propose_command": ("auto", False, False, ("assistant", "mcp_client")),
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


def test_autonomy_levels() -> None:
    assert get_args(vertical.AutonomyLevel) == ("auto", "review", "off")


def test_the_priority_order_names_each_blocker_kind_once() -> None:
    assert sorted(vertical.BLOCKER_KINDS_BY_PRIORITY) == sorted(get_args(BlockerKind))


def test_command_classes() -> None:
    actual = {
        c.name: (c.default_level, c.locked, c.human_only, c.actors)
        for c in vertical.COMMAND_CLASSES
    }
    assert actual == EXPECTED_COMMAND_CLASSES
    assert len(vertical.COMMAND_CLASSES) == len(EXPECTED_COMMAND_CLASSES)


def test_each_command_class_is_submitted_by_actors_and_has_a_level_of_their_sets() -> None:
    for command_class in vertical.COMMAND_CLASSES:
        assert set(command_class.actors) <= set(get_args(Actor))
        assert command_class.default_level in (*get_args(vertical.AutonomyLevel), None)


# A.11's two review rows, A.3 and sections 7.1, 7.3 rule 9, 7.4 and 10.4: (cause, persists).
# A cause an event raised closes on `approve`; a persistent cause closes when it is removed.
EXPECTED_REVIEW_CAUSES = (
    ("late_reply", False),  # 7.3 rule 9: a reply to a closed round
    ("unread_reply", False),  # 7.1: a reply recorded unread
    ("off_topic_reply", False),  # A.11
    ("declining_reply", False),  # 10.4 step 5
    ("reply_after_terminal_status", False),  # A.3
    ("draft_held_by_stop", False),  # 7.4: a dispatch refused by the stop
    ("draft_held_class_off", False),  # 7.4: a dispatch refused by a class set to off
    ("round_limit", True),  # A.11
    ("identity_score_missing", True),  # A.11
    ("identity_score_unsupported", True),  # A.11
)


def test_review_causes_are_the_ten_of_a11_with_whether_each_persists() -> None:
    assert vertical.REVIEW_CAUSES == EXPECTED_REVIEW_CAUSES


def test_the_review_causes_cover_each_cause_once() -> None:
    assert sorted(cause for cause, _ in vertical.REVIEW_CAUSES) == sorted(get_args(ReviewCause))


def test_confirmation_only_class_is_routine_request() -> None:
    # 10.1: the class takes one of the two request kinds, and is set to routine_request.
    assert vertical.CONFIRMATION_ONLY_CLASS in ("routine_request", "sensitive_request")
    assert vertical.CONFIRMATION_ONLY_CLASS == "routine_request"


def test_reference_morning() -> None:
    assert vertical.REFERENCE_MORNING == datetime(2026, 6, 29, 8, 0, tzinfo=UTC)
    assert vertical.REFERENCE_MORNING.utcoffset() is not None
    assert vertical.REFERENCE_MORNING.strftime("%A") == "Monday"
