# ABOUTME: Tests that the vertical tables hold the architecture's terminal statuses, blocker priority, transitions, command classes and persistent review causes and the rules for the blockers that can be served.
# ABOUTME: Every expected value is written out here from the architecture tables, not read back from the module under test.
from datetime import UTC, datetime
from typing import Any, get_args

import pytest

from uwh.runtime.event_types import Actor, AutonomyLevel, BlockerDetail, BlockerKind
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
        ("received", "declined"),
        ("triaged", "declined"),
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


# ---- the blocker rules -----------------------------------------------------------------------


def blocker_detail(**changes: Any) -> BlockerDetail:
    fields: dict[str, Any] = {"resume_trigger": "a reply arrives", "text": "waiting"}
    return BlockerDetail(**{**fields, **changes})


ACCEPTED_BLOCKERS: dict[str, tuple[BlockerKind, dict[str, Any]]] = {
    "producer reply": ("producer_reply", {"intent_id": "I-1"}),
    "data": ("data", {}),
    "question": ("underwriter_question", {"choice_ids": ["c1"]}),
    "delivery unknown": ("delivery_unknown", {"item_kind": "delivery_unknown"}),
    "draft review": ("underwriter_review", {"item_kind": "draft", "intent_id": "I-1"}),
    "no contact route": ("underwriter_review", {"item_kind": "no_contact_route"}),
    "late reply review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "late_reply"},
    ),
    "persistent review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit", "cause_persists": True},
    ),
    "held draft review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "draft_held_by_stop", "intent_id": "I-1"},
    ),
    "pending observation": (
        "underwriter_review",
        {"item_kind": "observation", "observation_id": 1},
    ),
}

REFUSED_BLOCKERS: dict[str, tuple[BlockerKind, dict[str, Any]]] = {
    "a cause on a blocker that is not a review": (
        "underwriter_review",
        {"item_kind": "draft", "intent_id": "I-1", "cause": "late_reply"},
    ),
    "a cause on a data blocker": ("data", {"cause": "late_reply"}),
    "an item kind on a producer reply": ("producer_reply", {"item_kind": "draft"}),
    "an item kind on a question": (
        "underwriter_question",
        {"item_kind": "review", "choice_ids": ["c1"]},
    ),
    "delivery_unknown without its item kind": ("delivery_unknown", {}),
    "delivery_unknown with the wrong item kind": ("delivery_unknown", {"item_kind": "draft"}),
    "a review without an item kind": ("underwriter_review", {}),
    "a review with the item kind delivery_unknown": (
        "underwriter_review",
        {"item_kind": "delivery_unknown"},
    ),
    "a draft review without its draft": ("underwriter_review", {"item_kind": "draft"}),
    "a review without a cause": ("underwriter_review", {"item_kind": "review"}),
    "a persistent cause not marked persistent": (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit"},
    ),
    "a non-persistent cause marked persistent": (
        "underwriter_review",
        {"item_kind": "review", "cause": "late_reply", "cause_persists": True},
    ),
    "cause_persists outside a review": (
        "underwriter_review",
        {"item_kind": "draft", "intent_id": "I-1", "cause_persists": True},
    ),
    "a held draft's review without its draft": (
        "underwriter_review",
        {"item_kind": "review", "cause": "draft_held_class_off"},
    ),
    "an observation item without observation_id": (
        "underwriter_review",
        {"item_kind": "observation"},
    ),
    "a question without choices": ("underwriter_question", {}),
    "choice_ids on a data blocker": ("data", {"choice_ids": ["c1"]}),
    "choice_ids on a review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "late_reply", "choice_ids": ["c1"]},
    ),
    "choice_ids on a producer reply": ("producer_reply", {"choice_ids": ["c1"]}),
}


@pytest.mark.parametrize("name", ACCEPTED_BLOCKERS)
def test_a_servable_blocker_is_accepted(name: str) -> None:
    kind, fields = ACCEPTED_BLOCKERS[name]
    vertical.refuse_unservable_blocker(kind, blocker_detail(**fields))


@pytest.mark.parametrize("name", REFUSED_BLOCKERS)
def test_an_unservable_blocker_is_refused(name: str) -> None:
    kind, fields = REFUSED_BLOCKERS[name]
    with pytest.raises(ValueError):
        vertical.refuse_unservable_blocker(kind, blocker_detail(**fields))
