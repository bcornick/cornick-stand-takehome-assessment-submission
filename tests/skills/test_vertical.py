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
    "no contact route": ("underwriter_review", {"item_kind": "no_contact_route"}),
    "late reply review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "late_reply"},
    ),
    "persistent review": (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit", "cause_persists": True},
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
