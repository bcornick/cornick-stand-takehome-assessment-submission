# ABOUTME: Integration tests of the harness clients against Stand's running leadgen and mailbox containers.
# ABOUTME: Mailbox writes use TEST- lead ids and never reset the container.
import uuid

import httpx2
import pytest

from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient

pytestmark = pytest.mark.integration


def test_leadgen_seed_42_returns_ten_leads_with_73_fields(host_urls: dict[str, str]) -> None:
    with httpx2.Client(base_url=host_urls["leadgen"]) as http:
        client = LeadgenClient(http)
        assert client.healthz() == {"status": "ok"}
        queue = client.post_queue(seed=42)
        expected = [f"LEAD-00000042-{i:03d}" for i in range(10)]
        assert queue["lead_ids"] == expected
        assert [s["lead_id"] for s in client.list_leads()] == expected
        for lead_id in expected:
            lead = client.get_lead(lead_id)
            assert lead["lead_id"] == lead_id
            assert len(lead["fields"]) == 73


def test_mailbox_round_trips_metadata(host_urls: dict[str, str]) -> None:
    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        client = MailboxClient(http)
        assert client.healthz() == {"status": "ok"}
        lead_id = f"TEST-{uuid.uuid4().hex[:8]}"
        metadata = {"asked": ["x"], "n": {"k": 1}}
        sent = client.send(
            lead_id=lead_id, to="a@b.c", from_="d@e.f", subject="s", body="b", metadata=metadata
        )
        listed = client.list_for_lead(lead_id)
        assert [m["id"] for m in listed] == [sent["id"]]
        assert listed[0]["metadata"] == metadata
        assert client.get(sent["id"])["metadata"] == metadata
