# ABOUTME: Tests that refuse_unservable_blocker accepts each blocker the lead detail can serve and refuses each combination of item kind, cause, intent and choices it cannot.
# ABOUTME: Every blocker is written out here from the architecture's A.11 rules, not read back from the module under test.
from typing import Any

import pytest

from uwh.runtime.event_types import BlockerDetail, BlockerKind
from uwh.skills import vertical


def blocker_detail(**changes: Any) -> BlockerDetail:
    fields: dict[str, Any] = {"resume_trigger": "a reply arrives", "text": "waiting"}
    return BlockerDetail(**{**fields, **changes})


ACCEPTED_BLOCKERS: dict[str, tuple[BlockerKind, dict[str, Any]]] = {
    "producer reply": ("producer_reply", {"intent_id": "I-1"}),
    "data": ("data", {}),
    "question": ("underwriter_question", {"choice_ids": ["c1"]}),
    "delivery unknown": ("delivery_unknown", {"item_kind": "delivery_unknown"}),
    "draft review": ("underwriter_review", {"item_kind": "draft", "intent_id": "I-1"}),
    "persistent review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit", "cause_persists": True},
    ),
}

REFUSED_BLOCKERS: dict[str, tuple[BlockerKind, dict[str, Any]]] = {
    "a cause on a blocker that is not a review": (
        "underwriter_review",
        {"item_kind": "draft", "intent_id": "I-1", "cause": "late_reply"},
    ),
    "delivery_unknown without its item kind": ("delivery_unknown", {}),
    "a review without an item kind": ("underwriter_review", {}),
    "a persistent cause not marked persistent": (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit"},
    ),
    "a non-persistent cause marked persistent": (
        "underwriter_review",
        {"item_kind": "review", "cause": "late_reply", "cause_persists": True},
    ),
    "a question without choices": ("underwriter_question", {}),
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
