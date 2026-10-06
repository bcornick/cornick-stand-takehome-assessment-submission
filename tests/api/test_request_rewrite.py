# ABOUTME: Tests the rewrite of the first pass's requests through the running app (10.2): the rewritten body of lead 008 keeps the question block and is hashed and sent as it is, a rejected rewrite sends the rendered request and the log names the check, the approval of a sensitive request binds to the rewritten body, and a decline notice is never rewritten.
# ABOUTME: The app runs in process in replay against Stand's leadgen and mailbox apps in process; the two calls per request are served from the committed recordings of the seed-42 record run.
import shutil
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.api.helpers import LEAD_008, RECORDINGS, first_pass
from uwh.runtime.event_types import EventType
from uwh.runtime.events import read_events
from uwh.runtime.hashing import payload_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings
from uwh.skills.plan_asks import skill as plan_asks
from uwh.skills.polish_message.skill import PolishInput, rewrite_call
from uwh.skills.render_message import skill as render_message

# The seed-42 request whose rewrite failed the model check in the record run.
LEAD_001 = "LEAD-00000042-001"
LEAD_000 = "LEAD-00000042-000"


@pytest.fixture
def db(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> Iterator[sqlite3.Connection]:
    with first_pass(settings, leadgen, mailbox):
        store = open_store(settings.db_path)
        yield store
        store.close()


def request_of(db: sqlite3.Connection, lead_id: str) -> tuple[str, str, str, str]:
    """The id, recipient, subject and body of the lead's first request."""
    (row,) = db.execute(
        "SELECT id, recipient, subject, body FROM intents WHERE lead_id = ? AND kind LIKE '%_request'",
        (lead_id,),
    ).fetchall()
    return row  # type: ignore[no-any-return]


def events_of(db: sqlite3.Connection, lead_id: str, type: EventType) -> list[Any]:
    return [e.payload for e in read_events(db, lead_id=lead_id) if e.type is type]


QUESTION_BLOCK_008 = (
    "Property\n1. When was the property purchased?\n\n"
    "Construction\n2. What brand is the electrical panel?"
)


def test_lead_008s_request_is_the_rewrite_with_its_question_block_unchanged(
    db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    _, _, _, body = request_of(db, LEAD_008)

    opening, closing = body.split(QUESTION_BLOCK_008)
    assert opening.strip() and closing.strip()
    assert render_message.OPENING not in body
    (sent,) = mailbox.list_for_lead(LEAD_008)
    assert sent["body"] == body


def test_the_body_the_draft_is_hashed_over_is_the_body_that_is_sent(
    db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    intent_id, recipient, subject, body = request_of(db, LEAD_008)

    (stored,) = db.execute("SELECT payload_hash FROM intents WHERE id = ?", (intent_id,)).fetchone()
    (sent,) = mailbox.list_for_lead(LEAD_008)
    assert stored == payload_hash(recipient, subject, body)
    assert sent["metadata"]["payload_hash"] == stored


def test_a_rewrite_that_failed_a_check_sends_the_rendered_request_and_the_log_names_the_check(
    db: sqlite3.Connection, mailbox: MailboxClient
) -> None:
    _, _, _, body = request_of(db, LEAD_001)

    assert body.startswith(render_message.OPENING)
    (fallback,) = events_of(db, LEAD_001, EventType.skill_fallback_used)
    assert fallback.skill == "polish_message" and fallback.status == "failing"
    assert "the model check rejected the rewrite" in fallback.fallback
    assert "the rendered request is sent as it is" in fallback.fallback
    (sent,) = mailbox.list_for_lead(LEAD_001)
    assert sent["body"] == body
    assert (
        sent["metadata"]["kind"] == "routine_request"
    )  # the class stays; it still sends automatically


def test_a_decline_notice_is_never_rewritten(
    db: sqlite3.Connection,
) -> None:
    (notice,) = db.execute("SELECT body FROM intents WHERE lead_id = ?", (LEAD_000,)).fetchone()

    assert notice == render_message.DECLINE_NOTICE
    assert events_of(db, LEAD_000, EventType.model_called) == []
    assert events_of(db, LEAD_000, EventType.skill_fallback_used) == []


def test_the_approval_of_a_sensitive_request_binds_to_the_rewritten_body_shown(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_asks, "_message_class", lambda asks: "sensitive_request")
    with first_pass(settings, leadgen, mailbox) as app:
        db = open_store(settings.db_path)
        intent_id, recipient, subject, body = request_of(db, LEAD_008)
        (item,) = [b for b in open_blockers(db, LEAD_008) if b.detail.intent_id == intent_id]
        assert mailbox.list_for_lead(LEAD_008) == []  # the draft waits for the underwriter
        (shown_hash,) = db.execute(
            "SELECT payload_hash FROM intents WHERE id = ?", (intent_id,)
        ).fetchone()
        assert shown_hash == payload_hash(recipient, subject, body)
        assert not body.startswith(render_message.OPENING)

        approved = app.post(
            "/api/commands",
            json={
                "type": "approve",
                "payload": {
                    "item_id": item.id,
                    "artifact_hash": shown_hash,
                    "reason": "the request reads as shown",
                },
            },
        )

        assert approved.json()["accepted"] is True
        (sent,) = mailbox.list_for_lead(LEAD_008)
        assert (sent["body"], sent["metadata"]["payload_hash"]) == (body, shown_hash)
        db.close()


def test_a_request_with_nothing_recorded_is_sent_rendered_and_the_miss_is_logged(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, tmp_path: Path
) -> None:
    empty = replace(settings, recordings_dir=str(tmp_path / "none"))
    with first_pass(empty, leadgen, mailbox):
        db = open_store(empty.db_path)
        _, _, _, body = request_of(db, LEAD_008)

        assert body.startswith(render_message.OPENING)
        assert len(events_of(db, LEAD_008, EventType.replay_miss)) == 1
        (fallback,) = events_of(db, LEAD_008, EventType.skill_fallback_used)
        assert fallback.status == "unavailable"
        assert "no recording answers the call" in fallback.fallback
        db.close()


def test_a_check_call_with_nothing_recorded_leaves_the_rewrite_call_logged(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, tmp_path: Path
) -> None:
    rewrite_version = rewrite_call(
        PolishInput(
            rendered=render_message.RenderMessageOutput(
                subject="", body="", ask_ids=[], question_block=""
            ),
            recipient_kind="producer",
            round=1,
        )
    ).recording_key.prompt_version
    only_rewrites = tmp_path / "recordings"
    shutil.copytree(
        RECORDINGS / "polish_message" / rewrite_version,
        only_rewrites / "polish_message" / rewrite_version,
    )
    partial = replace(settings, recordings_dir=str(only_rewrites))
    with first_pass(partial, leadgen, mailbox):
        db = open_store(partial.db_path)

        assert len(events_of(db, LEAD_008, EventType.model_called)) == 1
        assert len(events_of(db, LEAD_008, EventType.replay_miss)) == 1
        db.close()
