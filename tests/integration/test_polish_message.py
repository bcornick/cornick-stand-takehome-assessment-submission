# ABOUTME: Integration test of the request rewrite against Stand's running leadgen and mailbox containers: after a seed-42 run, lead 008's request in the mailbox is the question block as rendered inside an opening and a closing, and lead 001's, whose recorded rewrite failed the model check, is the rendered request.
# ABOUTME: A start resets the mailbox, which the app container shares; the mailbox is read back through its own listing, as a producer's inbox. The two calls of each request are served from the committed recordings.
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.settings import Settings
from uwh.skills.render_message.skill import OPENING

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

# What render_message gives lead 008: the question block, without its fixed opening.
QUESTION_BLOCK_008 = (
    "Property\n1. When was the property purchased?\n\n"
    "Construction\n2. What brand is the electrical panel?"
)
# The request of lead 001 begins with this fixed opening paragraph, then its question block.
LEAD_001_FIRST_QUESTION = "Location\n1. What is the property address?"


@pytest.fixture
def mail(host_urls: dict[str, str], tmp_path: Path) -> Iterator[dict[str, str]]:
    """The body of each seed-42 lead's request in the producer's mailbox after a run."""
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
    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        sent = MailboxClient(http)
        yield {
            lead_id: m["body"]
            for (lead_id,) in db.execute("SELECT lead_id FROM leads").fetchall()
            for m in sent.list_for_lead(lead_id)
            if m["metadata"]["kind"] == "routine_request"
        }
    db.close()


def test_question_block_unchanged_inside_the_rewritten_request(mail: dict[str, str]) -> None:
    body = mail["LEAD-00000042-008"]

    opening, closing = body.split(QUESTION_BLOCK_008)
    assert opening.strip() and closing.strip()
    assert OPENING not in body


def test_rejected_rewrite_sends_the_rendered_request(mail: dict[str, str]) -> None:
    body = mail["LEAD-00000042-001"]

    assert body.startswith(f"{OPENING}\n\n{LEAD_001_FIRST_QUESTION}")
