# ABOUTME: Tests the leadgen client's public surface and that it has no route to Stand's answer key.
# ABOUTME: Behaviour against the running container is covered in tests/integration/test_harness_clients.py.
import httpx2

from uwh.runtime.leadgen_client import LeadgenClient


def test_public_methods_are_exactly_the_four_endpoints() -> None:
    client = LeadgenClient(httpx2.Client(base_url="http://leadgen"))
    public = {n for n in dir(client) if not n.startswith("_") and callable(getattr(client, n))}
    assert public == {"post_queue", "list_leads", "get_lead", "healthz"}


def test_no_attribute_name_contains_debug() -> None:
    client = LeadgenClient(httpx2.Client(base_url="http://leadgen"))
    assert [n for n in dir(client) if "debug" in n.lower()] == []
    assert [n for n in dir(LeadgenClient) if "debug" in n.lower()] == []
