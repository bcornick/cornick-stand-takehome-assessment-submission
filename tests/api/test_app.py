# ABOUTME: Tests of the app skeleton: GET /api/run reports the mode, the seed and no run id before a run starts, the static frontend is served, and a restart settles a run that was left processing.
# ABOUTME: The app is built in process from explicit settings, against Stand's leadgen and mailbox apps in process.
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.api.runtime import open_runtime
from uwh.runtime.commands import submit_command
from uwh.runtime.events import EventContext
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.workflow import Step
from uwh.settings import Settings

# Section 11: the summary's seven counts are zero before a run starts.
NO_RUN_SUMMARY = {
    "quotes_sent": 0,
    "follow_ups_sent": 0,
    "declines_approved": 0,
    "waiting_on_underwriter": 0,
    "waiting_on_producer": 0,
    "waiting_on_data": 0,
    "delivery_unknown": 0,
}


def test_run_endpoint_reports_mode_seed_and_null_run_id(client: TestClient) -> None:
    response = client.get("/api/run")
    assert response.status_code == 200
    assert response.json() == {
        "run_id": None,
        "mode": "replay",
        "seed": 7,
        "sim_now": None,
        "first_pass_complete": False,
        "summary": NO_RUN_SUMMARY,
    }


def test_the_app_settles_a_run_left_processing_before_it_serves(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    open_client: Callable[..., AbstractContextManager[TestClient]],
) -> None:
    # The process stopped after the start and before the first pass.
    with open_runtime(settings, leadgen, mailbox) as runtime, runtime.database() as db:
        assert submit_command(db, runtime.env, "underwriter", "start_run", {"seed": 7}).accepted
    ran: list[str] = []

    def record(db: sqlite3.Connection, context: EventContext, lead_id: str) -> None:
        ran.append(lead_id)

    with open_client((Step("record", record),)) as client:
        view = client.get("/api/run").json()
        restarted = client.post("/api/run/start?wait=true")

    assert view["first_pass_complete"] is True
    assert len(ran) == 10 + 10  # the recovered pass, then the pass of the run started after it
    assert restarted.status_code == 200


def static_client(tmp_path: Path) -> TestClient:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (static / "assets/app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings.load({"UWH_DB": str(tmp_path / "app.db"), "UWH_STATIC_DIR": str(static)})
    return TestClient(create_app(settings))


def test_static_directory_is_served_at_the_root(tmp_path: Path) -> None:
    with static_client(tmp_path) as client:
        root = client.get("/")
        asset = client.get("/assets/app.js")
    assert root.status_code == 200
    assert 'id="root"' in root.text
    assert asset.status_code == 200
    assert asset.text == "console.log(1)"


def test_api_routes_keep_precedence_over_the_static_mount(tmp_path: Path) -> None:
    with static_client(tmp_path) as client:
        run = client.get("/api/run")
        declared = client.get("/api/leads")
        unknown = client.get("/api/no-such-route")
    assert run.status_code == 200
    assert run.json()["mode"] == "live"
    assert declared.status_code == 501
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
