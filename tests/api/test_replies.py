# ABOUTME: Tests the reply path of lead 008 through the running app: POST /api/replies and /api/replies/fixtures, the reading from the committed recording, the facts and round it settles, the quote packet draft, and the approval that sends it.
# ABOUTME: The app runs in process with the real steps against Stand's leadgen and mailbox apps in process; replay serves the model's reading from recordings/, and hand-made readings stand in for the abnormal replies.
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import FIXTURE_REPLIES, LEAD_008, RECORDINGS, REGISTRY, first_pass
from uwh.api import runtime
from uwh.rules.registry import load_registry
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.facts import effective_facts
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.recordings import (
    Exchange,
    RecordingKey,
    read_recording,
    write_recording,
)
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings
from uwh.skills.read_reply import skill

FIXTURE_BODY = (FIXTURE_REPLIES / f"{LEAD_008}.txt").read_text(encoding="utf-8")
ASKED = ["property_purchase_date", "electrical_panel_brand"]


@pytest.fixture
def app(settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient) -> Iterator[TestClient]:
    with first_pass(settings, leadgen, mailbox) as client:
        yield client


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    store = open_store(settings.db_path)
    yield store
    store.close()


def request_intent_id(db: sqlite3.Connection) -> str:
    (intent_id,) = db.execute("SELECT id FROM intents WHERE lead_id = ?", (LEAD_008,)).fetchone()
    return str(intent_id)


def deliver(client: TestClient, intent_id: str, body: str = FIXTURE_BODY) -> dict[str, Any]:
    response = client.post(
        "/api/replies", json={"lead_id": LEAD_008, "intent_id": intent_id, "body": body}
    )
    assert response.status_code == 200
    answer: dict[str, Any] = response.json()
    return answer


def producer_reply_open(db: sqlite3.Connection) -> bool:
    return any(b.kind == "producer_reply" for b in open_blockers(db, LEAD_008))


def review_causes(db: sqlite3.Connection) -> list[str | None]:
    return [b.detail.cause for b in open_blockers(db, LEAD_008) if b.kind == "underwriter_review"]


def facts_of(db: sqlite3.Connection) -> dict[str, Any]:
    return {key: fact.value for key, fact in effective_facts(db, LEAD_008).items()}


def test_the_fixture_reply_fills_the_two_fields_closes_the_round_and_drafts_the_quote_packet(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    intent_id = request_intent_id(db)

    answer = deliver(app, intent_id)

    assert answer["accepted"] is True and answer["lead_id"] == LEAD_008
    facts = facts_of(db)
    assert (facts["property_purchase_date"], facts["electrical_panel_brand"]) == (
        "2019-07-12",
        "Square D",
    )
    fact = effective_facts(db, LEAD_008)["electrical_panel_brand"]
    assert fact.source == "reply"
    start, end = fact.evidence["span_start"], fact.evidence["span_end"]
    assert FIXTURE_BODY[start:end] == fact.evidence["quote"]
    assert producer_reply_open(db) is False
    (draft,) = db.execute(
        "SELECT kind, state FROM intents WHERE lead_id = ? AND kind = 'quote_packet'", (LEAD_008,)
    ).fetchall()
    assert draft == ("quote_packet", "draft")
    assert review_causes(db) == [None]  # the packet's own review item, no reading problem
    assert len(mailbox.list_for_lead(LEAD_008)) == 1  # the request; the packet waits for approval
    (model_call,) = [e for e in read_events(db) if e.type is EventType.model_called]
    assert model_call.payload.tokens_in > 0  # type: ignore[attr-defined]


def test_the_same_reply_is_not_delivered_twice(app: TestClient, db: sqlite3.Connection) -> None:
    intent_id = request_intent_id(db)
    deliver(app, intent_id)
    events_before = len(read_events(db))

    answer = deliver(app, intent_id)

    assert answer["accepted"] is False and "already" in answer["reason"]
    assert [e.type for e in read_events(db)[events_before:]] == [EventType.command_refused]


@pytest.mark.parametrize("state", ["draft", "dispatching", "unknown", "closed_unsent"])
def test_a_reply_for_an_intent_that_is_not_sent_is_refused(
    app: TestClient, db: sqlite3.Connection, state: str
) -> None:
    intent_id = request_intent_id(db)
    db.execute("UPDATE intents SET state = ? WHERE id = ?", (state, intent_id))
    db.commit()

    answer = deliver(app, intent_id)

    assert answer["accepted"] is False and state in answer["reason"]
    assert facts_of(db).get("electrical_panel_brand") is None
    assert [e for e in read_events(db) if e.type is EventType.model_called] == []


def test_a_reply_after_the_round_closed_raises_a_review_and_applies_nothing(
    app: TestClient, db: sqlite3.Connection
) -> None:
    intent_id = request_intent_id(db)
    (round_blocker,) = open_blockers(db, LEAD_008)
    db.execute("UPDATE blockers SET closed_event_id = 1 WHERE id = ?", (round_blocker.id,))
    db.commit()

    answer = deliver(app, intent_id)

    assert answer["accepted"] is True
    assert review_causes(db) == ["late_reply"]
    assert facts_of(db).get("electrical_panel_brand") is None
    statuses = db.execute(
        "SELECT status FROM observations WHERE lead_id = ? AND source = 'reply'", (LEAD_008,)
    ).fetchall()
    assert statuses == [("pending_review",), ("pending_review",)]


def test_a_reply_with_no_recording_fails_closed_and_leaves_the_round_open(
    app: TestClient, db: sqlite3.Connection
) -> None:
    answer = deliver(app, request_intent_id(db), "A reply that was never recorded.")

    assert answer["accepted"] is False and "no recording" in answer["reason"]
    assert producer_reply_open(db) is True
    assert [e for e in read_events(db) if e.type is EventType.reply_received] == []
    assert [e.type for e in read_events(db) if e.type is EventType.replay_miss] == [
        EventType.replay_miss
    ]


@pytest.mark.parametrize(
    "unavailable",
    [
        {"model_api_key": None},
        {"model_api_key": "not-used", "model_base_url": "http://127.0.0.1:1"},  # a refused port
    ],
    ids=["no key", "provider unreachable"],
)
def test_a_reply_the_model_cannot_read_is_recorded_unread_for_the_underwriter(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    unavailable: dict[str, str | None],
) -> None:
    live = replace(settings, run_mode="live", **unavailable)  # type: ignore[arg-type]
    with first_pass(live, leadgen, mailbox) as client:
        db = open_store(settings.db_path)
        answer = deliver(client, request_intent_id(db))

        assert answer["accepted"] is True
        types = [e.type for e in read_events(db, lead_id=LEAD_008)]
        assert EventType.reply_received in types and EventType.reply_read not in types
        assert EventType.skill_fallback_used in types
        assert review_causes(db) == ["unread_reply"]
        assert producer_reply_open(db) is True
        assert facts_of(db).get("electrical_panel_brand") is None
        db.close()


def record_reading(directory: Path, body: str, tool_input: dict[str, Any] | None) -> None:
    """A hand-made model output for `body`, stored where replay finds it."""
    asks = skill.open_asks(ASKED, load_registry(str(REGISTRY)))
    call = skill.forced_call(skill.ReadReplyInput(body=body, asks=asks))
    key = call.recording_key
    write_recording(
        directory,
        key,
        Exchange(
            skill=key.skill,
            prompt_version=key.prompt_version,
            input_hash=key.input_hash,
            input=dict(call.shown),
            model_id="deepseek-flash",
            request_id="",
            stop_reason="tool_use" if tool_input is not None else "refusal",
            tokens_in=1,
            tokens_out=1,
            tool_input=tool_input,
        ),
    )


@pytest.mark.parametrize(
    ("tool_input", "cause", "read_event_holds"),
    [
        ({"classification": "off_topic", "candidates": []}, "off_topic_reply", "off_topic"),
        (
            {"classification": "declines_to_answer", "candidates": []},
            "declining_reply",
            "declines_to_answer",
        ),
        ({"classification": "maybe", "candidates": []}, "unread_reply", "invalid_tool_input"),
        (None, "unread_reply", "refusal"),
    ],
)
def test_a_reply_that_is_not_an_answer_raises_its_review_and_leaves_the_round_open(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    tmp_path: Path,
    tool_input: dict[str, Any] | None,
    cause: str,
    read_event_holds: str,
) -> None:
    body = "Please call me."
    record_reading(tmp_path, body, tool_input)
    with first_pass(replace(settings, recordings_dir=str(tmp_path)), leadgen, mailbox) as client:
        db = open_store(settings.db_path)

        answer = deliver(client, request_intent_id(db), body)

        assert answer["accepted"] is True
        assert review_causes(db) == [cause]
        assert producer_reply_open(db) is True
        (read,) = [e.payload for e in read_events(db) if e.type is EventType.reply_read]
        assert read_event_holds in (read.classification, read.abstention)  # type: ignore[attr-defined]
        assert facts_of(db).get("electrical_panel_brand") is None
        db.close()


def test_the_model_is_called_with_no_write_lock_held(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second connection takes the write lock while the model call is in flight."""
    locked: list[bool] = []

    def model_call(call: Any, key: RecordingKey) -> Exchange:
        other = sqlite3.connect(settings.db_path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
            locked.append(False)
        except sqlite3.OperationalError:
            locked.append(True)
        finally:
            other.rollback()
            other.close()
        recorded = read_recording(RECORDINGS, key)
        assert recorded is not None
        return recorded

    monkeypatch.setattr(runtime, "anthropic_call", lambda client, model_id: model_call)
    keyed = replace(settings, run_mode="live", model_api_key="not-used")
    with first_pass(keyed, leadgen, mailbox) as client:
        db = open_store(settings.db_path)

        assert deliver(client, request_intent_id(db))["accepted"] is True

        assert locked == [False]
        db.close()


def test_lead_008_goes_from_its_reply_to_a_sent_quote_packet(
    app: TestClient, db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    delivered = app.post("/api/replies/fixtures").json()
    assert [(r["lead_id"], r["accepted"]) for r in delivered["replies"]] == [(LEAD_008, True)]
    (item,) = [b for b in open_blockers(db, LEAD_008) if b.detail.item_kind == "draft"]
    (packet_id, shown_hash) = db.execute(
        "SELECT id, payload_hash FROM intents WHERE lead_id = ? AND kind = 'quote_packet'",
        (LEAD_008,),
    ).fetchone()
    assert item.detail.intent_id == packet_id

    stale = app.post(
        "/api/commands",
        json={
            "type": "approve",
            "payload": {"item_id": item.id, "artifact_hash": "0" * 64, "reason": "ok"},
        },
    ).json()
    assert stale["accepted"] is False
    assert len(mailbox.list_for_lead(LEAD_008)) == 1

    approved = app.post(
        "/api/commands",
        json={
            "type": "approve",
            "payload": {"item_id": item.id, "artifact_hash": shown_hash, "reason": "ok"},
        },
    ).json()

    assert approved["accepted"] is True, approved
    assert db.execute("SELECT status FROM leads WHERE lead_id = ?", (LEAD_008,)).fetchone() == (
        "quote_sent",
    )
    sent = mailbox.list_for_lead(LEAD_008)
    assert sorted(m["metadata"]["kind"] for m in sent) == ["quote_packet", "routine_request"]
    (packet,) = [m for m in sent if m["metadata"]["kind"] == "quote_packet"]
    assert packet["metadata"]["intent_id"] == packet_id
    assert packet["metadata"]["payload_hash"] == shown_hash
    assert open_blockers(db, LEAD_008) == []
