# ABOUTME: Integration test of lead 008 against Stand's running leadgen and mailbox containers: the app starts the seed-42 run and the lead's first pass leaves one sent routine request in the real mailbox.
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
REGISTRY = Path(__file__).resolve().parents[2] / "docs" / "brief" / "field_registry.json"


def test_lead_008_first_pass_sends_one_routine_request(
    host_urls: dict[str, str], tmp_path: Path
) -> None:
    settings = Settings.load(
        {
            "UWH_DB": str(tmp_path / "app.db"),
            "RUN_MODE": "replay",
            "SEED": "42",
            "UWH_REGISTRY": str(REGISTRY),
            "LEADGEN_URL": host_urls["leadgen"],
            "MAILBOX_URL": host_urls["mailbox"],
        }
    )

    with TestClient(create_app(settings)) as app:
        assert app.post("/api/run/start?wait=true").status_code == 200

    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        (message,) = MailboxClient(http).list_for_lead(LEAD_008)
    assert (message["metadata"]["kind"], message["metadata"]["round"]) == ("routine_request", 1)
    assert message["body"].count("?") == 2
    assert "electrical panel" in message["body"] and "property purchased" in message["body"]
    db = open_store(settings.db_path)
    assert db.execute("SELECT status FROM leads WHERE lead_id = ?", (LEAD_008,)).fetchone() == (
        "in_progress",
    )
    assert [b.kind for b in open_blockers(db, LEAD_008)] == ["producer_reply"]
