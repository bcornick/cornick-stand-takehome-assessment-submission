# ABOUTME: Integration test that each captured world's final leads equal what the running leadgen container serves for the same seed.
# ABOUTME: Seed 42 is posted last so the container's queue ends on the app's seed.
import json
from pathlib import Path

import httpx2
import pytest

from uwh.runtime.hashing import hash_json
from uwh.runtime.leadgen_client import LeadgenClient

pytestmark = pytest.mark.integration

DATA = Path(__file__).resolve().parents[2] / "src" / "uwh" / "providers" / "data"


@pytest.mark.parametrize("seed", [11, 15, 42])
def test_fixture_final_leads_equal_the_containers_leads(
    seed: int, host_urls: dict[str, str]
) -> None:
    world = json.loads((DATA / f"world-{seed}.json").read_text(encoding="utf-8"))
    with httpx2.Client(base_url=host_urls["leadgen"]) as http:
        client = LeadgenClient(http)
        queue = client.post_queue(seed=seed, count=world["count"])
        assert queue["lead_ids"] == list(world["leads"])
        for lead_id, entry in world["leads"].items():
            served = client.get_lead(lead_id)["fields"]
            assert entry["fields"] == served
            assert entry["fingerprint"] == hash_json(served)
