# ABOUTME: Integration test of the underwriter's actions on the seed-42 leads against Stand's running leadgen and mailbox containers: approve, edit and reject a draft, approve and reject a pending value, a ruling, a resolved fact, a decline with its notice, and a pasted reply.
# ABOUTME: The app runs in process in replay mode; each effect is read back from the lead detail the page reads and from the producer's mailbox, which a start resets.
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import httpx2
import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


class Session(NamedTuple):
    app: TestClient
    mailbox: MailboxClient


@pytest.fixture
def session(host_urls: dict[str, str], tmp_path: Path) -> Iterator[Session]:
    """A started seed-42 run with the fixture replies not yet delivered."""
    settings = Settings.load(
        {
            "UWH_DB": str(tmp_path / "app.db"),
            "RUN_MODE": "replay",
            "SEED": "42",
            "UWH_REGISTRY": str(ROOT / "docs" / "brief" / "field_registry.json"),
            "UWH_RECORDINGS": str(ROOT / "recordings"),
            "UWH_FIXTURE_REPLIES": str(ROOT / "fixtures" / "replies"),
            "LEADGEN_URL": host_urls["leadgen"],
            "MAILBOX_URL": host_urls["mailbox"],
        }
    )
    with (
        TestClient(create_app(settings)) as app,
        httpx2.Client(base_url=host_urls["mailbox"]) as http,
    ):
        assert app.post("/api/run/start?wait=true").status_code == 200
        yield Session(app, MailboxClient(http))


@pytest.fixture
def answered(session: Session) -> Session:
    """The same run after the fixture replies have been delivered."""
    assert session.app.post("/api/replies/fixtures").status_code == 200
    return session


def lead_id(number: str) -> str:
    return f"LEAD-00000042-{number}"


def command(app: TestClient, command_type: str, **payload: Any) -> dict[str, Any]:
    response = app.post("/api/commands", json={"type": command_type, "payload": payload})
    assert response.status_code == 200
    answer: dict[str, Any] = response.json()
    return answer


def detail(app: TestClient, number: str) -> dict[str, Any]:
    answer: dict[str, Any] = app.get(f"/api/leads/{lead_id(number)}").json()
    return answer


def item_of(lead: dict[str, Any], item_kind: str) -> dict[str, Any]:
    (item,) = [b for b in lead["blockers"] if b["detail"]["item_kind"] == item_kind]
    return item


def draft_of(lead: dict[str, Any], kind: str) -> dict[str, Any]:
    (draft,) = [d for d in lead["drafts"] if d["kind"] == kind]
    return draft


def mail(session: Session, number: str) -> list[dict[str, Any]]:
    return session.mailbox.list_for_lead(lead_id(number))


def kinds(session: Session, number: str) -> list[str]:
    return sorted(m["metadata"]["kind"] for m in mail(session, number))


def approve_draft(
    app: TestClient, number: str, hash_: str | None = None, kind: str = "quote_packet"
) -> dict[str, Any]:
    lead = detail(app, number)
    return command(
        app,
        "approve",
        item_id=item_of(lead, "draft")["item_id"],
        artifact_hash=hash_ or draft_of(lead, kind)["payload_hash"],
        reason="the draft matches the plan",
    )


def test_approving_a_waiting_packet_sends_it(answered: Session) -> None:
    assert approve_draft(answered.app, "008")["accepted"] is True

    lead = detail(answered.app, "008")
    assert (lead["status"], lead["blockers"]) == ("quote_sent", [])
    assert kinds(answered, "008") == ["quote_packet", "routine_request"]


def test_an_edited_packet_is_sent_with_its_new_text_after_its_new_approval(
    answered: Session,
) -> None:
    app = answered.app
    before = draft_of(detail(app, "009"), "quote_packet")

    edited = command(
        app,
        "edit_draft",
        intent_id=before["intent_id"],
        subject="Your quote, checked",
        body="Checked by the underwriter.",
        reason="the opening was too stiff",
    )

    assert edited["accepted"] is True
    assert approve_draft(app, "009", before["payload_hash"])["accepted"] is False
    assert kinds(answered, "009") == ["routine_request"]
    assert approve_draft(app, "009")["accepted"] is True
    (packet,) = [m for m in mail(answered, "009") if m["metadata"]["kind"] == "quote_packet"]
    assert (packet["subject"], packet["body"]) == (
        "Your quote, checked",
        "Checked by the underwriter.",
    )


def test_rejecting_a_packet_sends_nothing_and_leaves_it_as_a_draft(answered: Session) -> None:
    app = answered.app
    item = item_of(detail(app, "004"), "draft")

    rejected = command(app, "reject", item_id=item["item_id"], reason="the roof is wrong")

    assert rejected["accepted"] is True
    assert draft_of(detail(app, "004"), "quote_packet")["state"] == "draft"
    assert kinds(answered, "004") == ["routine_request"]


@pytest.mark.parametrize(
    ("decision", "effective_value"), [("approve", 5), ("reject", 3)], ids=["approve", "reject"]
)
def test_a_pending_value_becomes_the_fact_when_approved_and_stays_out_when_rejected(
    answered: Session, decision: str, effective_value: int
) -> None:
    app = answered.app
    item = item_of(detail(app, "003"), "observation")

    answer = command(app, decision, item_id=item["item_id"], reason="the reply is clear")

    assert answer["accepted"] is True
    lead = detail(app, "003")
    assert [b for b in lead["blockers"] if b["detail"]["item_kind"] == "observation"] == []
    (fact,) = [f for f in lead["facts"] if f["key"] == "months_unoccupied"]
    assert fact["value"] == effective_value


def test_a_ruling_on_lead_003_needs_a_reason_and_closes_the_choice(session: Session) -> None:
    app = session.app
    ruling = {
        "lead_id": lead_id("003"),
        "choice_id": "I13.fire_fail",
        "option": "legacy_underwriting",
    }
    blank = app.post(
        "/api/commands", json={"type": "record_ruling", "payload": {**ruling, "reason": ""}}
    )
    assert blank.status_code == 422

    accepted = command(app, "record_ruling", **ruling, reason="the checklist is satisfied")

    assert accepted["accepted"] is True
    (card,) = [b for b in detail(app, "003")["blockers"] if b["kind"] == "underwriter_question"]
    assert card["detail"]["choice_ids"] == ["I16.distance"]


def test_a_resolved_fact_is_the_effective_value_from_the_underwriter(session: Session) -> None:
    answer = command(
        session.app,
        "resolve_fact",
        lead_id=lead_id("002"),
        key="coverage_a",
        value=500000,
        reason="the producer said so by phone",
    )

    assert answer["accepted"] is True
    (fact,) = [f for f in detail(session.app, "002")["facts"] if f["key"] == "coverage_a"]
    assert (fact["value"], fact["source"]) == (500000, "underwriter")


def test_a_declined_lead_sends_its_notice_once_the_notice_is_approved(session: Session) -> None:
    app = session.app

    declined = command(app, "decline_lead", lead_id=lead_id("005"), reason="outside our appetite")

    assert declined["accepted"] is True
    assert kinds(session, "005") == ["routine_request"]
    assert approve_draft(app, "005", kind="decline_notice")["accepted"] is True
    assert detail(app, "005")["status"] == "declined"
    assert kinds(session, "005") == ["decline_notice", "routine_request"]


def test_a_pasted_reply_is_read_and_its_values_become_facts(session: Session) -> None:
    app = session.app
    (request,) = [d for d in detail(app, "007")["drafts"] if d["state"] == "sent"]
    body = (ROOT / "fixtures" / "replies" / f"{lead_id('007')}.txt").read_text(encoding="utf-8")

    answer = app.post(
        "/api/replies",
        json={"lead_id": lead_id("007"), "intent_id": request["intent_id"], "body": body},
    ).json()

    assert answer["accepted"] is True
    facts = {f["key"]: f for f in detail(app, "007")["facts"]}
    assert (facts["zip"]["value"], facts["zip"]["source"]) == ("34102", "reply")
