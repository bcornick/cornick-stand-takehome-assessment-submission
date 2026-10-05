# ABOUTME: Tests of the app skeleton: GET /api/run reports the mode, the seed and no run id before a run starts.
# ABOUTME: The app is built in process, from explicit settings or from the environment.
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.settings import Settings


def test_run_endpoint_reports_mode_seed_and_null_run_id() -> None:
    settings = Settings.load({"UWH_DB": "unused.db", "RUN_MODE": "replay", "SEED": "7"})
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/run")
    assert response.status_code == 200
    assert response.json() == {"mode": "replay", "seed": 7, "run_id": None}


def test_app_without_settings_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUN_MODE", "record")
    monkeypatch.setenv("SEED", "11")
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))
    with TestClient(create_app()) as client:
        response = client.get("/api/run")
    assert response.json() == {"mode": "record", "seed": 11, "run_id": None}
