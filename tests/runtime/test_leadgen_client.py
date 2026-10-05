# ABOUTME: Tests that the leadgen client has no route to Stand's answer key.
# ABOUTME: Behaviour against the running container is covered in tests/integration/test_harness_clients.py.
import httpx2

from uwh.runtime.leadgen_client import LeadgenClient


def test_no_attribute_name_contains_debug() -> None:
    with httpx2.Client(base_url="http://leadgen") as http:
        client = LeadgenClient(http)
        assert [n for n in dir(client) if "debug" in n.lower()] == []
    assert [n for n in dir(LeadgenClient) if "debug" in n.lower()] == []
