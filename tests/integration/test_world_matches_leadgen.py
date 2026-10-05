# ABOUTME: Integration test that the captured world's final leads equal what the running leadgen container serves for seed 42.
# ABOUTME: The container's queue ends on the app's seed.
import json
from pathlib import Path

import httpx2
import pytest

from uwh.runtime.hashing import hash_json
from uwh.runtime.leadgen_client import LeadgenClient

pytestmark = pytest.mark.integration

DATA = Path(__file__).resolve().parents[2] / "src" / "uwh" / "providers" / "data"


def test_fixture_final_leads_equal_the_containers_leads(host_urls: dict[str, str]) -> None:
    world = json.loads((DATA / "world-42.json").read_text(encoding="utf-8"))
    with httpx2.Client(base_url=host_urls["leadgen"]) as http:
        client = LeadgenClient(http)
        queue = client.post_queue(seed=42, count=world["count"])
        assert queue["lead_ids"] == list(world["leads"])
        for lead_id, entry in world["leads"].items():
            served = client.get_lead(lead_id)["fields"]
            assert entry["fields"] == served
            assert entry["fingerprint"] == hash_json(served)
