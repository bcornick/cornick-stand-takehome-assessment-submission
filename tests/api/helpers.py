# ABOUTME: The helpers the API tests share: waiting for a condition, reading whether the first pass of the run is complete and the app after the first pass of the seed-42 run.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.rules.registry import load_registry
from uwh.runtime.facts import open_conflicts
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.recordings import Exchange, write_recording
from uwh.settings import Settings
from uwh.skills.read_reply import skill

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


def record_reading(
    db: sqlite3.Connection,
    directory: Path,
    lead_id: str,
    request_intent_id: str,
    body: str,
    candidates: list[dict[str, Any]],
) -> None:
    """Write the recording of a reading of `body` that classifies it `answers_some` with the
    candidates, for the asks of the request. The tests that use it are of what the app does with a
    reading, so no model reads the reply."""
    (ask_ids,) = db.execute(
        "SELECT ask_ids_json FROM intents WHERE id = ?", (request_intent_id,)
    ).fetchone()
    asks = skill.open_asks(
        json.loads(ask_ids),
        load_registry(str(REGISTRY)),
        [c.opened for c in open_conflicts(db, lead_id)],
    )
    call = skill.forced_call(skill.ReadReplyInput(body=body, asks=asks))
    key = call.recording_key
    write_recording(
        directory,
        key,
        Exchange(
            skill=key.skill,
            prompt_version=key.prompt_version,
            input_hash=key.input_hash,
            input=dict(call.shown),
            model_id="deepseek-flash",
            request_id="",
            stop_reason="tool_use",
            tokens_in=1,
            tokens_out=1,
            tool_input={"classification": "answers_some", "candidates": candidates},
        ),
    )
