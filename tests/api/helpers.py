# ABOUTME: The helpers the API tests share: waiting for a condition and reading whether the first pass of the run is complete.
# ABOUTME: A plain module rather than conftest.py, which pytest loads under its own module name and tests do not import.
import time
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

WAIT_SECONDS = 10.0
# Stand's registry, which the app reads at startup.
REGISTRY = Path(__file__).resolve().parents[2] / "docs" / "brief" / "field_registry.json"


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while not condition():
        assert time.monotonic() < deadline, "the condition did not hold in time"
        time.sleep(0.01)


def first_pass_complete(client: TestClient) -> bool:
    complete = client.get("/api/run").json()["first_pass_complete"]
    assert isinstance(complete, bool)
    return complete
