# ABOUTME: Shared test setup that loads Stand's mailbox app in process and applies the host URLs for integration tests.
# ABOUTME: Stand's package must be imported before the standard-library module of the same name.
import atexit
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

# Stand's modules read these paths at import, so they are set before the import below.
_DB_DIR = Path(tempfile.mkdtemp(prefix="uwh-test-db-"))
atexit.register(shutil.rmtree, _DB_DIR, ignore_errors=True)
os.environ["LEADGEN_DB"] = str(_DB_DIR / "leadgen.db")
os.environ["MAILBOX_DB"] = str(_DB_DIR / "mailbox.db")

sys.path.insert(0, str(ROOT / "sim-harness"))
# A standard-library `mailbox` already imported would shadow Stand's package.
assert "mailbox" not in sys.modules, (
    "Stand's package must be imported before the standard-library module of the same name"
)
import mailbox.main as stand_mailbox  # noqa: E402

assert Path(stand_mailbox.__file__).is_relative_to(ROOT / "sim-harness")

HOST_LEADGEN_URL = "http://localhost:8081"
HOST_MAILBOX_URL = "http://localhost:8025"


@pytest.fixture
def stand_mailbox_client() -> Iterator[httpx2.Client]:
    """Stand's unmodified mailbox app served in process; an httpx2.Client."""
    with TestClient(stand_mailbox.app, base_url="http://mailbox") as client:
        yield client


@pytest.fixture
def host_urls(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Point settings at the containers' host ports for the duration of one test."""
    monkeypatch.setenv("LEADGEN_URL", HOST_LEADGEN_URL)
    monkeypatch.setenv("MAILBOX_URL", HOST_MAILBOX_URL)
    return {"leadgen": HOST_LEADGEN_URL, "mailbox": HOST_MAILBOX_URL}
