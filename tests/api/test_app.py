# ABOUTME: Tests of the app skeleton: GET /api/run reports the mode, the seed and no run id before a run starts.
# ABOUTME: The app is built in process from explicit settings, so no environment is read.
from fastapi.testclient import TestClient

from uwh.api.app import create_app
from uwh.settings import Settings


def test_run_endpoint_reports_mode_seed_and_null_run_id() -> None:
    settings = Settings.load({"UWH_DB": "unused.db", "RUN_MODE": "replay", "SEED": "7"})
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/run")
    assert response.status_code == 200
    assert response.json() == {"mode": "replay", "seed": 7, "run_id": None}
