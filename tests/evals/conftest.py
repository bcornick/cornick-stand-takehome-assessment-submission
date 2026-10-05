# ABOUTME: Fixture for the eval tests: the database of the app after the first pass of the seed-42 run, with Stand's leadgen and mailbox apps in process.
# ABOUTME: The image's rules data is replaced by a temporary directory holding an empty interpretation table, as the API tests do.
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import FIXTURE_REPLIES, RECORDINGS, REGISTRY
from uwh.api import runtime
from uwh.api.app import create_app
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.settings import Settings


@pytest.fixture
def first_pass_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    leadgen: LeadgenClient,
    stand_mailbox_client: httpx2.Client,
) -> Iterator[sqlite3.Connection]:
    """The database of the app after the first pass of the seed-42 run."""
    data = tmp_path / "rules-data"
    data.mkdir()
    (data / "interpretation.yaml").write_text("rows: []\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "IMAGE_RULES_DATA", data)
    settings = Settings.load(
        {
            "UWH_DB": str(tmp_path / "app.db"),
            "RUN_MODE": "replay",
            "SEED": "42",
            "UWH_REGISTRY": str(REGISTRY),
            "UWH_RECORDINGS": str(RECORDINGS),
            "UWH_FIXTURE_REPLIES": str(FIXTURE_REPLIES),
        }
    )
    mailbox = MailboxClient(stand_mailbox_client)
    mailbox.reset()
    with TestClient(create_app(settings, leadgen=leadgen, mailbox=mailbox)) as client:
        assert client.post("/api/run/start?wait=true").status_code == 200
    db = open_store(settings.db_path)
    yield db
    db.close()
