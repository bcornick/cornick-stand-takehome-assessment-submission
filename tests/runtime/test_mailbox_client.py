# ABOUTME: Tests the mailbox client's behaviour against Stand's mailbox app in process.
# ABOUTME: A message sent with metadata must read back by lead with equal metadata and raise no warning.
import uuid

import httpx2
import pytest

from uwh.runtime.mailbox_client import MailboxClient


@pytest.mark.filterwarnings("error")
def test_metadata_round_trips_by_lead(stand_mailbox_client: httpx2.Client) -> None:
    client = MailboxClient(stand_mailbox_client)
    lead_id = f"TEST-{uuid.uuid4().hex[:8]}"
    metadata = {"fields": ["a", "b"], "nested": {"n": 1}, "flag": True}
    assert client.healthz() == {"status": "ok"}

    sent = client.send(
        lead_id=lead_id,
        to="applicant@example.com",
        from_="underwriting@example.com",
        subject="Missing details",
        body="Please send them.",
        metadata=metadata,
    )
    assert sent["lead_id"] == lead_id

    by_lead = client.list_for_lead(lead_id)
    assert len(by_lead) == 1
    assert by_lead[0]["metadata"] == metadata
    assert by_lead[0]["id"] == sent["id"]
    assert by_lead[0]["from"] == "underwriting@example.com"
    assert client.list_for_lead("TEST-nobody") == []


@pytest.mark.filterwarnings("error")
def test_reset_clears_messages(stand_mailbox_client: httpx2.Client) -> None:
    client = MailboxClient(stand_mailbox_client)
    lead_id = f"TEST-{uuid.uuid4().hex[:8]}"
    client.send(lead_id=lead_id, to="a@b.c", from_="d@e.f", subject="s", body="b")
    client.reset()
    assert client.list_for_lead(lead_id) == []
