# ABOUTME: Integration test of lead 008 against Stand's running leadgen and mailbox containers: the app starts the seed-42 run, the first pass sends one routine request, the fixture reply is read from its recording, and the underwriter's approval sends the quote packet.
# ABOUTME: A start resets the mailbox, which the app container shares; the mailbox is read back through its own listing, as a producer's inbox.
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blockers
from uwh.settings import Settings

pytestmark = pytest.mark.integration

LEAD_008 = "LEAD-00000042-008"
ROOT = Path(__file__).resolve().parents[2]


def test_lead_008_goes_from_the_queue_to_a_sent_quote_packet(
    host_urls: dict[str, str], tmp_path: Path
) -> None:
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

    with TestClient(create_app(settings)) as app:
        assert app.post("/api/run/start?wait=true").status_code == 200
        db = open_store(settings.db_path)
        assert [b.kind for b in open_blockers(db, LEAD_008)] == ["producer_reply"]

        delivered = app.post("/api/replies/fixtures").json()["replies"]
        assert [(r["lead_id"], r["accepted"]) for r in delivered] == [(LEAD_008, True)]

        (item,) = open_blockers(db, LEAD_008)
        assert item.detail.item_kind == "draft"
        (packet_hash,) = db.execute(
            "SELECT payload_hash FROM intents WHERE lead_id = ? AND kind = 'quote_packet'",
            (LEAD_008,),
        ).fetchone()
        approved = app.post(
            "/api/commands",
            json={
                "type": "approve",
                "payload": {
                    "item_id": item.id,
                    "artifact_hash": packet_hash,
                    "reason": "the packet matches the plan",
                },
            },
        )
        assert approved.json()["accepted"] is True

    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        sent = MailboxClient(http).list_for_lead(LEAD_008)
    assert sorted(m["metadata"]["kind"] for m in sent) == ["quote_packet", "routine_request"]
    (packet,) = [m for m in sent if m["metadata"]["kind"] == "quote_packet"]
    assert packet["metadata"]["payload_hash"] == packet_hash
    assert "The Electrical page is not evaluated." in packet["body"]
    assert db.execute("SELECT status FROM leads WHERE lead_id = ?", (LEAD_008,)).fetchone() == (
        "quote_sent",
    )
    assert open_blockers(db, LEAD_008) == []
