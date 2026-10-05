# ABOUTME: The helpers the API tests share: waiting for a condition, reading whether the first pass of the run is complete and the app after the first pass of the seed-42 run.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings

WAIT_SECONDS = 10.0
ROOT = Path(__file__).resolve().parents[2]
# Stand's registry, which the app reads at startup.
REGISTRY = ROOT / "docs" / "brief" / "field_registry.json"
# The committed model recordings and reply fixtures.
RECORDINGS = ROOT / "recordings"
FIXTURE_REPLIES = ROOT / "fixtures" / "replies"
LEAD_008 = "LEAD-00000042-008"


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition did not hold in time"
        time.sleep(0.01)


def first_pass_complete(client: TestClient) -> bool:
    complete = client.get("/api/run").json()["first_pass_complete"]
    assert isinstance(complete, bool)
    return complete


@contextmanager
def first_pass(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> Iterator[TestClient]:
    """The app after the first pass of the seed-42 run."""
    with TestClient(
        create_app(replace(settings, seed=42), leadgen=leadgen, mailbox=mailbox)
    ) as client:
        assert client.post("/api/run/start?wait=true").status_code == 200
        yield client
