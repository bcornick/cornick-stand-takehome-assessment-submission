# ABOUTME: Tests what a queue row says apart from its group: the decision an underwriter-waiting lead asks for, and the round and send time of a producer-waiting lead's open request.
# ABOUTME: Rows are built from stored state over constructed leads; a row's decision follows its highest-priority underwriter blocker.
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.api.helpers import REGISTRY
from uwh.api.leads import lead_detail, queue_rows
from uwh.api.waiting import ask_label
from uwh.rules.registry import fact_fields, load_registry
from uwh.runtime.event_types import (
    BlockerDetail,
    BlockerKind,
    EventType,
    MessageSent,
)
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker

NOW = datetime(2026, 6, 30, 7, 0, tzinfo=UTC)
SENT_AT = datetime(2026, 6, 29, 9, 30, tzinfo=UTC)
CONTEXT = EventContext("run-1", "replay", "workflow", "r" * 64, NOW, SENT_AT)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    return open_store(str(tmp_path / "app.db"))


def add_lead(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO leads (lead_id, run_id, source, received_at, status, revision)"
        " VALUES ('L-1', 'run-1', 'web', '2026-06-29T07:00:00Z', 'in_progress', 0)"
    )


def add_intent(db: sqlite3.Connection, intent_id: str, kind: str, round: int, state: str) -> None:
    db.execute(
        "INSERT INTO intents (id, lead_id, round, kind, recipient, subject, body, payload_hash,"
        " ask_ids_json, state) VALUES (?, 'L-1', ?, ?, 'p@example.com', 's', 'b', 'h',"
        ' \'["coverage_a", "q:contact_email"]\', ?)',
        (intent_id, round, kind, state),
    )


DRAFT = {"item_kind": "draft", "intent_id": "I-draft"}
DECISIONS: list[tuple[BlockerKind, dict[str, object], str | None, str]] = [
    ("underwriter_review", DRAFT, "decline_notice", "Review decline notice"),
    ("underwriter_review", DRAFT, "quote_packet", "Review quote"),
    ("underwriter_review", DRAFT, "routine_request", "Review request"),
    ("underwriter_review", {"item_kind": "observation"}, None, "Review a reply's value"),
    ("underwriter_review", {"item_kind": "no_contact_route"}, None, "Find a contact route"),
    ("underwriter_review", {"item_kind": "review", "cause": "late_reply"}, None, "Review a reply"),
    (
        "underwriter_review",
        {"item_kind": "review", "cause": "round_limit", "cause_persists": True},
        None,
        "Review the round limit",
    ),
    (
        "underwriter_review",
        {"item_kind": "review", "cause": "identity_score_missing", "cause_persists": True},
        None,
        "Review the identity score",
    ),
    ("delivery_unknown", {"item_kind": "delivery_unknown"}, None, "Check a delivery"),
    ("underwriter_question", {"choice_ids": ["I13.fire_fail"]}, None, "Fire simulation choice"),
    ("underwriter_question", {"choice_ids": ["I14.road_access"]}, None, "Road access choice"),
]


@pytest.mark.parametrize(("kind", "detail", "draft_kind", "decision"), DECISIONS)
def test_an_underwriter_row_names_the_decision_it_asks_for(
    db: sqlite3.Connection,
    kind: BlockerKind,
    detail: dict[str, object],
    draft_kind: str | None,
    decision: str,
) -> None:
    add_lead(db)
    if draft_kind is not None:
        add_intent(db, "I-draft", draft_kind, 1, "draft")
    if detail.get("item_kind") == "observation":
        cursor = db.execute(
            "INSERT INTO observations (lead_id, key, value_json, source, evidence_json, status)"
            " VALUES ('L-1', 'coverage_a', '1', 'reply', '{}', 'pending_review')"
        )
        detail = {**detail, "observation_id": cursor.lastrowid}
    open_blocker(
        db,
        CONTEXT,
        "L-1",
        kind,
        "underwriter",
        BlockerDetail.model_validate({"resume_trigger": "r", "text": "t", **detail}),
    )
    db.commit()

    (row,) = queue_rows(db, NOW)

    assert row.decision == decision


def test_the_highest_priority_underwriter_blocker_names_the_decision(
    db: sqlite3.Connection,
) -> None:
    add_lead(db)
    add_intent(db, "I-draft", "quote_packet", 1, "draft")
    review = BlockerDetail(item_kind="draft", intent_id="I-draft", resume_trigger="r", text="t")
    question = BlockerDetail(choice_ids=["I13.fire_fail"], resume_trigger="r", text="t")
    open_blocker(db, CONTEXT, "L-1", "underwriter_review", "underwriter", review)
    open_blocker(db, CONTEXT, "L-1", "underwriter_question", "underwriter", question)
    db.commit()

    (row,) = queue_rows(db, NOW)

    assert row.decision == "Fire simulation choice"


def test_a_row_waiting_on_the_producer_carries_the_round_and_time_of_its_open_request(
    db: sqlite3.Connection,
) -> None:
    add_lead(db)
    add_intent(db, "I-1", "routine_request", 1, "closed_unsent")
    add_intent(db, "I-2", "sensitive_request", 2, "sent")
    for intent_id in ("I-1", "I-2"):
        append_event(
            db,
            CONTEXT,
            EventType.message_sent,
            MessageSent(intent_id=intent_id, mailbox_id=1),
            lead_id="L-1",
        )
    open_blocker(
        db,
        CONTEXT,
        "L-1",
        "producer_reply",
        "producer",
        BlockerDetail(intent_id="I-2", resume_trigger="r", text="t"),
    )
    db.commit()

    (row,) = queue_rows(db, NOW)
    detail = lead_detail(db, "L-1", load_registry(str(REGISTRY)))
    assert detail is not None
    second = detail.drafts[1]

    assert (row.decision, row.request_round) == (None, 2)
    assert row.asked_at is not None and row.asked_at.startswith("2026-06-29T09:30")
    assert second.sent_at == row.asked_at
    assert second.asks == ["Coverage A (Dwelling)", "Contact email"]


@pytest.mark.parametrize(
    ("ask_id", "label"),
    [
        ("year_built", "Year Built"),
        ("willing_to_mitigate", "Would the applicant be willing to mitigate greater distance?"),
        ("months_unoccupied_in_primary_home", "Confirm Consecutive Months Unoccupied"),
        (
            "dwelling_use_conflict",
            "Confirm Dwelling Use, Occupancy Type and Rental Exposure",
        ),
    ],
    ids=["field", "catalogue question", "confirmation", "combined confirmation"],
)
def test_an_ask_reads_as_the_field_or_question_it_puts_to_the_producer(
    ask_id: str, label: str
) -> None:
    assert ask_label(ask_id, fact_fields(load_registry(str(REGISTRY)))) == label
