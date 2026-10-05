# ABOUTME: Tests the mailbox client's public surface and its behaviour against Stand's mailbox app in process.
# ABOUTME: A message sent with metadata must read back by lead with equal metadata and raise no warning.
import uuid

import httpx2
import pytest

from uwh.runtime.mailbox_client import MailboxClient


def test_public_methods_are_exactly_the_five_endpoints() -> None:
    client = MailboxClient(httpx2.Client(base_url="http://mailbox"))
    public = {n for n in dir(client) if not n.startswith("_") and callable(getattr(client, n))}
    assert public == {"send", "list_for_lead", "get", "reset", "healthz"}


@pytest.mark.filterwarnings("error")
def test_metadata_round_trips_by_lead_and_by_id(stand_mailbox_client: httpx2.Client) -> None:
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
    assert client.get(sent["id"])["metadata"] == metadata
    assert client.list_for_lead("TEST-nobody") == []


def test_non_success_raises(stand_mailbox_client: httpx2.Client) -> None:
    with pytest.raises(httpx2.HTTPStatusError):
        MailboxClient(stand_mailbox_client).get(10**9)


@pytest.mark.filterwarnings("error")
def test_reset_clears_messages(stand_mailbox_client: httpx2.Client) -> None:
    client = MailboxClient(stand_mailbox_client)
    lead_id = f"TEST-{uuid.uuid4().hex[:8]}"
    client.send(lead_id=lead_id, to="a@b.c", from_="d@e.f", subject="s", body="b")
    client.reset()
    assert client.list_for_lead(lead_id) == []
