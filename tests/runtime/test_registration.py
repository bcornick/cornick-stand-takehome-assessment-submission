# ABOUTME: Tests that a Registration accepts a consistent set of names and refuses a role name outside its set, a repeated name or an unknown status.
# ABOUTME: A second registration with entirely different names is accepted, so the dataclass holds no underwriting name.
from dataclasses import replace

import pytest

from uwh.runtime.registration import Registration

VALID = Registration(
    statuses=("new", "open", "closed"),
    terminal_statuses=("closed",),
    transitions=(("new", "open"), ("open", "closed")),
    blocker_kinds_by_priority=("lost", "inspect", "lookup", "wait"),
    blocker_owners=("reviewer", "clerk", "outsider"),
    message_kinds=("note", "letter"),
    item_kinds=("note_item", "fact_item", "lost_item", "inspect_item", "extra_item"),
    observation_sources=("given", "found", "worked_out", "guessed", "answer", "ruling"),
    delivery_unknown_kind="lost",
    human_review_kind="inspect",
    data_kind="lookup",
    human_owner="reviewer",
    data_owner="clerk",
    draft_item_kind="note_item",
    observation_item_kind="fact_item",
    delivery_unknown_item_kind="lost_item",
    review_item_kind="inspect_item",
    human_source="ruling",
)


def test_a_consistent_registration_is_accepted() -> None:
    assert VALID.human_review_kind == "inspect"
    assert VALID.human_source == "ruling"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("delivery_unknown_kind", "other"),
        ("human_review_kind", "other"),
        ("data_kind", "other"),
        ("human_owner", "other"),
        ("data_owner", "other"),
        ("draft_item_kind", "other"),
        ("observation_item_kind", "other"),
        ("delivery_unknown_item_kind", "other"),
        ("review_item_kind", "other"),
        ("human_source", "other"),
    ],
)
def test_a_role_name_outside_its_set_is_refused(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=field):
        replace(VALID, **{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "statuses",
        "blocker_kinds_by_priority",
        "blocker_owners",
        "message_kinds",
        "item_kinds",
        "observation_sources",
    ],
)
def test_a_repeated_name_is_refused(field: str) -> None:
    names = getattr(VALID, field)
    with pytest.raises(ValueError, match=f"{field}.*repeated"):
        replace(VALID, **{field: (*names, names[0])})


def test_a_terminal_status_outside_the_statuses_is_refused() -> None:
    with pytest.raises(ValueError, match="terminal_statuses"):
        replace(VALID, terminal_statuses=("closed", "vanished"))


@pytest.mark.parametrize("pair", [("vanished", "open"), ("new", "vanished")])
def test_a_transition_naming_an_unknown_status_is_refused(pair: tuple[str, str]) -> None:
    with pytest.raises(ValueError, match="transitions"):
        replace(VALID, transitions=(*VALID.transitions, pair))
