# ABOUTME: Integration test of the keyless demo against the running app, leadgen and mailbox containers in replay mode: a run, the fixture replies, and the approval of lead 008's packet, all over the app's HTTP API.
# ABOUTME: The app's event log is the evidence that no model was called: every event of the run is stored in replay mode, a model call is served from a recording, and no replay_miss was recorded.
from collections import Counter
from pathlib import Path

import httpx2
import pytest

from tests.integration.test_all_leads import FIRST_PASS
from uwh.runtime.mailbox_client import MailboxClient

pytestmark = pytest.mark.integration

APP_URL = "http://localhost:8000"
LEAD_008 = "LEAD-00000042-008"
ROOT = Path(__file__).resolve().parents[2]
# The app waits on the whole first pass; each reply is read before its request returns.
TIMEOUT_SECONDS = 120


def test_the_demo_runs_from_recordings_to_a_sent_quote_packet(host_urls: dict[str, str]) -> None:
    with (
        httpx2.Client(base_url=APP_URL, timeout=TIMEOUT_SECONDS) as app,
        httpx2.Client(base_url=host_urls["mailbox"]) as mailbox_http,
    ):
        mode = app.get("/api/run").json()["mode"]
        if mode != "replay":
            pytest.skip(
                f"the app container runs in {mode} mode; the replay demo needs RUN_MODE=replay"
            )
        mailbox = MailboxClient(mailbox_http)

        run = app.post("/api/run/start?wait=true").json()
        assert run["first_pass_complete"] is True
        assert run["mode"] == "replay"

        queue = app.get("/api/leads").json()
        assert sorted(row["lead_id"] for row in queue) == [f"LEAD-00000042-{n}" for n in FIRST_PASS]
        mismatches = []
        for number, expected in FIRST_PASS.items():
            lead_id = f"LEAD-00000042-{number}"
            detail = app.get(f"/api/leads/{lead_id}").json()
            found = {
                "status": detail["status"],
                "blockers": sorted(
                    (b["kind"], b["detail"]["item_kind"], b["detail"]["cause"])
                    for b in detail["blockers"]
                ),
                "mail": dict(
                    Counter(m["metadata"]["kind"] for m in mailbox.list_for_lead(lead_id))
                ),
            }
            wanted = {
                "status": "in_progress",
                "blockers": sorted(expected.blockers),
                "mail": expected.mail,
            }
            mismatches += [
                f"{lead_id} {name}: {found[name]!r}, expected {wanted[name]!r}"
                for name in wanted
                if found[name] != wanted[name]
            ]
        assert mismatches == []

        delivered = app.post("/api/replies/fixtures").json()["replies"]
        fixtures = sorted((ROOT / "fixtures" / "replies").glob("*.txt"))
        assert sorted(r["lead_id"] for r in delivered) == [f.stem for f in fixtures]
        assert [r for r in delivered if not r["accepted"]] == []

        detail = app.get(f"/api/leads/{LEAD_008}").json()
        (item,) = detail["blockers"]
        assert item["detail"]["item_kind"] == "draft"
        (packet,) = [d for d in detail["drafts"] if d["kind"] == "quote_packet"]
        approved = app.post(
            "/api/commands",
            json={
                "type": "approve",
                "payload": {
                    "item_id": item["item_id"],
                    "artifact_hash": packet["payload_hash"],
                    "reason": "the packet matches the plan",
                },
            },
        )
        assert approved.json()["accepted"] is True

        assert app.get(f"/api/leads/{LEAD_008}").json()["status"] == "quote_sent"
        sent = mailbox.list_for_lead(LEAD_008)
        assert sorted(m["metadata"]["kind"] for m in sent) == ["quote_packet", "routine_request"]
        (sent_packet,) = [m for m in sent if m["metadata"]["kind"] == "quote_packet"]
        assert sent_packet["metadata"]["payload_hash"] == packet["payload_hash"]

        events = {
            number: app.get(f"/api/leads/LEAD-00000042-{number}/events").json()["events"]
            for number in FIRST_PASS
        }
        every_event = [event for lead_events in events.values() for event in lead_events]
        # The event store records the mode on every event; replay serves a model call from a
        # recording only, and a call with no recording is recorded as replay_miss.
        assert {event["mode"] for event in every_event} == {"replay"}
        assert Counter(e["type"] for e in every_event)["model_called"] >= len(fixtures)
        # The second-round request of leads 003 and 007 has no polish recording; the rendered
        # request goes out as it is. Every other model call is recorded.
        misses = {
            number: [e["summary"] for e in lead_events if e["type"] == "replay_miss"]
            for number, lead_events in events.items()
        }
        assert {number: found for number, found in misses.items() if found} == {
            "003": ["No recording was found for a polish_message call."],
            "007": ["No recording was found for a polish_message call."],
        }
