# ABOUTME: Tests the sentence a lead's conversation opens with, over one constructed lead per case: what the underwriter must do comes first, then what the system waits on.
# ABOUTME: State is built with the queue test's lead helper, open blockers, intents, observations and a sent-message event; the sentences are asserted whole.
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.api.helpers import REGISTRY
from tests.api.test_leads import CONTEXT, add_lead
from uwh.api.summary import summary_line
from uwh.rules.models import ActionPlan, OpenChoice
from uwh.rules.registry import fact_fields, load_registry
from uwh.runtime.event_types import BlockerDetail, BlockerKind, BlockerOwner, EventType, MessageSent
from uwh.runtime.events import EventContext, append_event
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker, open_blockers

LEAD = "L-1"
FIRE_CHOICE = OpenChoice(
    choice_id="I13.fire_fail",
    options=["decline", "legacy_underwriting"],
    prompt="The fire simulation failed.",
    show=[],
)
OTHER_CHOICE = OpenChoice(
    choice_id="I14.road_access",
    options=["continue", "decline"],
    prompt="The road access is a single access point.",
    show=[],
)


@dataclass
class Item:
    kind: BlockerKind
    owner: BlockerOwner
    detail: BlockerDetail


def item(kind: BlockerKind, owner: BlockerOwner, **detail: object) -> Item:
    fields = {"resume_trigger": "resumes", "text": "waiting", **detail}
    return Item(kind, owner, BlockerDetail.model_validate(fields))


@dataclass
class Case:
    name: str
    sentence: str
    items: list[Item] = field(default_factory=list)
    plan: ActionPlan | None = None
    status: str = "in_progress"
    intents: dict[str, str] = field(default_factory=dict)  # intent id -> kind
    asks: str = "[]"
    sent: str | None = None  # the intent whose message_sent event is on 2026-07-01


FIRE = item("underwriter_question", "underwriter", choice_ids=["I13.fire_fail"], text="choose")
PACKET_REVIEW = item("underwriter_review", "underwriter", item_kind="draft", intent_id="I-q")
NOTICE_REVIEW = item("underwriter_review", "underwriter", item_kind="draft", intent_id="I-d")
OBSERVATION = item("underwriter_review", "underwriter", item_kind="observation", observation_id=3)
WAIT_REPLY = item("producer_reply", "producer", intent_id="I-L-1")
CASES = [
    Case(
        "fire simulation choice names the fact",
        "This lead failed the fire simulation at 0.79. "
        "I need you to choose between a decline and legacy underwriting.",
        [FIRE],
        ActionPlan(open_choices=[FIRE_CHOICE]),
    ),
    Case(
        "another choice gives the prompt and the options",
        "I need you to choose. The road access is a single access point. "
        "The options are continue or decline.",
        [item("underwriter_question", "underwriter", choice_ids=["I14.road_access"])],
        ActionPlan(open_choices=[OTHER_CHOICE]),
    ),
    Case(
        "quote packet draft",
        "The quote packet is ready. I need you to approve it before it goes to the producer.",
        [PACKET_REVIEW],
        intents={"I-q": "quote_packet"},
    ),
    Case(
        "decline notice draft gives the underwriter's reason",
        "I propose to decline this lead: the roof is beyond repair. "
        "I need you to approve the notice, or withdraw the decline.",
        [NOTICE_REVIEW],
        ActionPlan(underwriter_decline="the roof is beyond repair", proposed_decline=True),
        intents={"I-d": "decline_notice"},
    ),
    Case(
        "pending observation names the field and both values",
        "The producer's reply gives Roof Surface Material as Metal, which differs from the value in use, Tile. "
        "I need you to accept or reject it.",
        [OBSERVATION],
    ),
    Case(
        "unconfirmed delivery",
        "The mailbox did not confirm a message. I need you to check it before anything else goes.",
        [item("delivery_unknown", "underwriter", item_kind="delivery_unknown")],
    ),
    Case(
        "another review gives its text",
        "I need you to review this: the reply came after the lead was closed.",
        [
            item(
                "underwriter_review",
                "underwriter",
                item_kind="review",
                cause="reply_after_terminal_status",
                text="the reply came after the lead was closed",
            )
        ],
    ),
    Case(
        "waiting on the producer counts the distinct asks",
        "I asked the producer for the 2 missing fields and am waiting for the reply.",
        [WAIT_REPLY],
        asks='["a1", "a2", "a1"]',
    ),
    Case(
        "waiting on the producer while an underwriter item is open",
        "The quote packet is ready. I need you to approve it before it goes to the producer. "
        "Meanwhile I asked the producer for the 1 missing field and am waiting for the reply.",
        [WAIT_REPLY, PACKET_REVIEW],
        intents={"I-q": "quote_packet"},
        asks='["a1"]',
    ),
    Case(
        "waiting on data",
        "I am waiting on data: the fire lookup has not answered.",
        [item("data", "data_team", text="the fire lookup has not answered")],
    ),
    Case(
        "several items, underwriter first, one sentence each",
        "This lead failed the fire simulation at 0.79. "
        "I need you to choose between a decline and legacy underwriting. "
        "I am waiting on data: slow.",
        [item("data", "data_team", text="slow"), FIRE],
        ActionPlan(open_choices=[FIRE_CHOICE]),
    ),
    Case(
        "quote packet sent",
        "Quote packet sent on Jul 1.",
        status="quote_sent",
        intents={"I-q": "quote_packet"},
        sent="I-q",
    ),
    Case(
        "declined",
        "Declined on Jul 1: the roof is beyond repair.",
        plan=ActionPlan(underwriter_decline="the roof is beyond repair", proposed_decline=True),
        status="declined",
        intents={"I-d": "decline_notice"},
        sent="I-d",
    ),
    Case("nothing open", "Triage is running."),
]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_the_summary_line_for_each_state_of_a_lead(case: Case, tmp_path: Path) -> None:
    db = open_store(str(tmp_path / "app.db"))
    add_lead(db, LEAD, case.status, None, asks=case.asks)
    _add_fact(db, "p_f", 0.79, "accepted", "submitted")
    _add_fact(db, "roof_material", "Tile", "accepted", "submitted")
    _add_fact(db, "roof_material", "Metal", "pending_review", "reply")
    for intent_id, kind in case.intents.items():
        db.execute(
            "INSERT INTO intents (id, lead_id, round, kind, ask_ids_json, state)"
            " VALUES (?, ?, 2, ?, '[]', 'draft')",
            (intent_id, LEAD, kind),
        )
    for it in case.items:
        open_blocker(db, CONTEXT, LEAD, it.kind, it.owner, it.detail)
    if case.sent is not None:
        sim_ts = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
        context = EventContext("run-1", "replay", "workflow", "r" * 64, sim_ts, sim_ts)
        append_event(
            db,
            context,
            EventType.message_sent,
            MessageSent(intent_id=case.sent, mailbox_id=1),
            lead_id=LEAD,
        )
    db.commit()
    fields = fact_fields(load_registry(str(REGISTRY)))
    line = summary_line(db, LEAD, case.status, case.plan, open_blockers(db, LEAD), fields)
    assert line == case.sentence


def _add_fact(db: sqlite3.Connection, key: str, value: object, status: str, source: str) -> None:
    cursor = db.execute(
        "INSERT INTO observations (lead_id, key, value_json, source, evidence_json, status)"
        " VALUES (?, ?, ?, ?, '{}', ?)",
        (LEAD, key, json.dumps(value), source, status),
    )
    if status == "accepted":
        db.execute(
            "INSERT INTO effective_facts (lead_id, key, observation_id, confirmed)"
            " VALUES (?, ?, ?, 0)",
            (LEAD, key, cursor.lastrowid),
        )
