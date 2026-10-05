# ABOUTME: Tests POST /api/run/start and GET /api/run (A.5): the start submits start_run as the underwriter, returns at once or after the run has settled, and the run view reports the run, its clock, its summary counts and whether the first pass is complete.
# ABOUTME: Each test runs the app in process against Stand's leadgen and mailbox apps and reads the application database back through open_store.
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import WAIT_SECONDS, first_pass_complete, wait_for
from uwh.api.runtime import FirstPass, Runtime
from uwh.api.views import RunView
from pydantic import JsonValue
from uwh.runtime.commands import CommandResult
from uwh.runtime.event_types import BlockerDetail, EventType
from uwh.runtime.events import EventContext, read_events
from uwh.runtime.runs import command_context
from uwh.runtime.store import open_store
from uwh.runtime.waits import open_blocker
from uwh.runtime.workflow import Step
from uwh.settings import Settings

OpenClient = Callable[..., AbstractContextManager[TestClient]]


class HeldStep:
    """A step that blocks inside the unit of work of its lead until `release`, so that a test acts while
    a first pass is running. A released step does not block, so the other leads pass through."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.finished: list[str] = []
        self.step = Step("hold", self._run)

    def _run(self, db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        self.entered.set()
        if not self.released.wait(WAIT_SECONDS):
            raise TimeoutError("the held step was not released")
        self.finished.append(lead_id)

    def release(self) -> None:
        self.released.set()


@contextmanager
def held_pass(open_client: OpenClient) -> Iterator[tuple[TestClient, HeldStep]]:
    """A client whose first pass blocks in its first step; the pass is released on exit, so a failing
    test does not leave the app waiting."""
    held = HeldStep()
    with open_client((held.step,)) as client:
        try:
            yield client, held
        finally:
            held.release()


def test_a_waited_start_ingests_ten_leads_and_reports_the_first_pass_complete(
    client: TestClient, settings: Settings
) -> None:
    response = client.post("/api/run/start?wait=true")

    assert response.status_code == 200
    view = RunView.model_validate(response.json())
    assert view.run_id is not None
    assert (view.mode, view.seed, view.first_pass_complete) == ("replay", 7, True)
    assert client.get("/api/run").json()["first_pass_complete"] is True
    db = open_store(settings.db_path)
    assert db.execute("SELECT run_id, seed, status FROM runs").fetchall() == [
        (view.run_id, 7, "settled")
    ]
    leads = [row[0] for row in db.execute("SELECT lead_id FROM leads ORDER BY rowid")]
    assert [lead_id[:14] for lead_id in leads] == ["LEAD-00000007-"] * 10
    events = read_events(db)
    assert [e.type for e in events].count(EventType.lead_received) == 10
    (started,) = [e for e in events if e.type is EventType.run_started]
    assert (started.actor, started.run_id) == ("underwriter", view.run_id)
    assert {e.run_id for e in events} == {view.run_id}
    db.close()


def test_a_start_returns_at_once_with_the_run_id_while_the_pass_runs(
    open_client: OpenClient, settings: Settings
) -> None:
    with held_pass(open_client) as (client, held):
        response = client.post("/api/run/start")

        assert response.status_code == 200
        view = RunView.model_validate(response.json())
        assert view.run_id is not None
        assert view.first_pass_complete is False
        assert held.entered.wait(WAIT_SECONDS)
        assert held.finished == []
        assert first_pass_complete(client) is False
        assert client.get("/api/run").json()["run_id"] == view.run_id

        held.release()
        wait_for(lambda: first_pass_complete(client))
        assert len(held.finished) == 10
    db = open_store(settings.db_path)
    assert {status for (status,) in db.execute("SELECT status FROM leads")} == {"in_progress"}
    db.close()


def test_a_waited_start_that_a_later_start_replaced_reports_its_own_run_and_not_the_later_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Runtime.submit_as_underwriter
    later_runs: list[str] = []

    def start_then_replace(
        self: Runtime, db: sqlite3.Connection, command_type: str, payload: Mapping[str, JsonValue]
    ) -> tuple[CommandResult, FirstPass | None]:
        result, first = original(self, db, command_type, payload)
        if not later_runs:
            # The first pass settles, and a later start lands before the response is built.
            assert first is not None
            first.future.result()
            with self.database() as other:
                _, later = original(self, other, "start_run", {"seed": 7})
            assert later is not None
            later_runs.append(later.run.run_id)
        return result, first

    monkeypatch.setattr(Runtime, "submit_as_underwriter", start_then_replace)

    response = client.post("/api/run/start?wait=true")

    (later_run,) = later_runs
    assert response.status_code == 409
    assert "was replaced by a later start" in response.json()["detail"]
    assert later_run not in response.text
    assert client.get("/api/run").json()["run_id"] == later_run


def test_a_start_while_the_run_is_processing_is_refused(
    client: TestClient, settings: Settings
) -> None:
    # The only worker is busy, so the first start's pass waits in its queue and the run stays processing.
    release = threading.Event()
    client.app.state.runtime.passes.submit(release.wait, WAIT_SECONDS)  # type: ignore[attr-defined]
    try:
        first = RunView.model_validate(client.post("/api/run/start").json())

        second = client.post("/api/run/start")

        assert second.status_code == 409
        assert "processing" in second.json()["detail"]
        assert client.get("/api/run").json()["run_id"] == first.run_id
    finally:
        release.set()
    wait_for(lambda: first_pass_complete(client))
    db = open_store(settings.db_path)
    refusals = [e for e in read_events(db) if e.type is EventType.command_refused]
    assert [(e.actor, e.run_id) for e in refusals] == [("underwriter", first.run_id)]
    db.close()


def test_a_failed_pass_is_logged_the_run_still_settles_and_a_waited_start_answers_500(
    open_client: OpenClient, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    class PassAbort(BaseException):
        """An exception no step handler catches, so it escapes the pass."""

    def abort(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        raise PassAbort

    caplog.set_level(logging.ERROR, logger="uwh.api.runtime")
    with open_client((Step("abort", abort),)) as client:
        response = client.post("/api/run/start?wait=true")

        assert response.status_code == 500
        assert first_pass_complete(client) is True
    db = open_store(settings.db_path)
    (run_id,) = db.execute("SELECT run_id FROM runs").fetchone()
    db.close()
    (record,) = [r for r in caplog.records if r.name == "uwh.api.runtime"]
    assert run_id in record.getMessage()
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], BaseExceptionGroup)
    assert record.exc_info[1].exceptions[0].__class__ is PassAbort


def test_the_summary_counts_come_from_the_stored_state(
    client: TestClient, settings: Settings
) -> None:
    client.post("/api/run/start?wait=true")
    db = open_store(settings.db_path)
    context = command_context(db, "workflow", "replay", "r" * 64, datetime.now().astimezone())
    ids = [row[0] for row in db.execute("SELECT lead_id FROM leads ORDER BY rowid")]

    def intent(lead_id: str, kind: str, round_: int, state: str = "sent") -> None:
        db.execute(
            "INSERT INTO intents (id, run_id, lead_id, round, kind, recipient, subject, body,"
            " ask_ids_json, payload_hash, state) VALUES (?, ?, ?, ?, ?, 'a@b.c', 's', 'b', '[]', 'h', ?)",
            (f"{lead_id}-{kind}-{round_}", context.run_id, lead_id, round_, kind, state),
        )

    def block(lead_id: str, kind: str, **detail: object) -> None:
        owner = {"data": "data_team", "producer_reply": "producer"}.get(kind, "underwriter")
        open_blocker(
            db,
            context,
            lead_id,
            kind,  # type: ignore[arg-type]
            owner,  # type: ignore[arg-type]
            BlockerDetail(resume_trigger="a person acts", text="held", **detail),  # type: ignore[arg-type]
        )

    db.execute("UPDATE leads SET status = 'quote_sent' WHERE lead_id = ?", (ids[0],))
    intent(ids[0], "quote_packet", 0)
    block(ids[0], "data")  # a terminal lead waits on nothing
    intent(ids[1], "routine_request", 1)
    intent(ids[1], "sensitive_request", 2)
    intent(ids[1], "routine_request", 3, state="draft")  # not sent
    block(ids[1], "producer_reply")
    db.execute("UPDATE leads SET status = 'declined' WHERE lead_id = ?", (ids[2],))
    intent(ids[2], "decline_notice", 0)
    block(ids[3], "underwriter_review", item_kind="review", cause="unread_reply")
    block(ids[3], "producer_reply")  # the lead counts once, under the underwriter
    block(ids[4], "data")
    block(ids[5], "delivery_unknown", item_kind="delivery_unknown")
    block(ids[5], "data")  # the lead counts once, under delivery_unknown
    block(ids[6], "underwriter_question", choice_ids=["c1"])
    db.commit()
    db.close()

    summary = client.get("/api/run").json()["summary"]

    assert summary == {
        "quotes_sent": 1,
        "follow_ups_sent": 2,
        "declines_approved": 1,
        "waiting_on_underwriter": 2,
        "waiting_on_producer": 1,
        "waiting_on_data": 1,
        "delivery_unknown": 1,
    }
