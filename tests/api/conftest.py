# ABOUTME: Fixtures for the API tests: settings that point at a temporary database, Stand's leadgen and mailbox apps in process, and a factory for apps whose lifespan has run.
# ABOUTME: The image's rules data is replaced by a temporary directory, and the workflow steps are the ones a test passes.
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import REGISTRY
from uwh.api import runtime
from uwh.api.app import create_app
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.workflow import Step
from uwh.settings import Settings

OpenClient = Callable[..., AbstractContextManager[TestClient]]


@pytest.fixture(autouse=True)
def rules_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "rules-data"
    data.mkdir()
    (data / "interpretation.yaml").write_text("rows: []\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "IMAGE_RULES_DATA", data)
    return data


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.load(
        {
            "UWH_DB": str(tmp_path / "app.db"),
            "RUN_MODE": "replay",
            "SEED": "7",
            "UWH_REGISTRY": str(REGISTRY),
        }
    )


@pytest.fixture
def mailbox(stand_mailbox_client: httpx2.Client) -> MailboxClient:
    client = MailboxClient(stand_mailbox_client)
    client.reset()
    return client


@pytest.fixture
def open_client(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    monkeypatch: pytest.MonkeyPatch,
) -> OpenClient:
    """`open_client(steps)` is a context manager that yields a client of an app whose lifespan has run
    and ends it on exit, after the first pass has finished."""

    @contextmanager
    def open_(steps: Sequence[Step] = ()) -> Iterator[TestClient]:
        monkeypatch.setattr(runtime, "build_steps", lambda registry, providers, rules: tuple(steps))
        with TestClient(create_app(settings, leadgen=leadgen, mailbox=mailbox)) as client:
            yield client

    return open_


@pytest.fixture
def client(open_client: OpenClient) -> Iterator[TestClient]:
    with open_client() as opened:
        yield opened
