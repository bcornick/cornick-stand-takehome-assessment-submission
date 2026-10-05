# ABOUTME: Integration tests of the bootstrap against Stand's running leadgen and mailbox containers.
# ABOUTME: A closed port stands in for an unreachable service; the probe is read back independently.
import json
import socket
from pathlib import Path

import httpx2
import pytest

from uwh.runtime import bootstrap
from uwh.runtime.bootstrap import EnvironmentInvalid
from uwh.runtime.mailbox_client import MailboxClient

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UWH_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("SEED", "42")


def closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
    return f"http://localhost:{port}"


def test_run_reads_the_queue_and_round_trips_a_probe(host_urls: dict[str, str]) -> None:
    summary = bootstrap.run()

    expected = [f"LEAD-00000042-{i:03d}" for i in range(10)]
    assert summary["lead_ids"] == expected
    bootstrap_id = summary["bootstrap_id"]
    probe_lead = f"BOOTSTRAP-{bootstrap_id}"
    assert summary["probe"]["lead_id"] == probe_lead
    assert summary["probe"]["metadata_round_trip"] is True

    with httpx2.Client(base_url=host_urls["mailbox"]) as http:
        messages = MailboxClient(http).list_for_lead(probe_lead)
    assert len(messages) == 1
    assert messages[0]["metadata"] == {"probe": True, "run_id": bootstrap_id}


def test_each_run_has_its_own_id(host_urls: dict[str, str]) -> None:
    assert bootstrap.run()["bootstrap_id"] != bootstrap.run()["bootstrap_id"]


def test_closed_mailbox_port_is_an_invalid_environment(
    host_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAILBOX_URL", closed_port_url())
    with pytest.raises(EnvironmentInvalid, match="mailbox"):
        bootstrap.run()


def test_closed_leadgen_port_is_an_invalid_environment(
    host_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADGEN_URL", closed_port_url())
    with pytest.raises(EnvironmentInvalid, match="leadgen"):
        bootstrap.run()


def test_main_prints_only_the_json_summary(
    host_urls: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert bootstrap.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["lead_ids"][0] == "LEAD-00000042-000"
    assert captured.err == ""


def test_main_reports_an_invalid_environment_on_stderr(
    host_urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MAILBOX_URL", closed_port_url())
    assert bootstrap.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "mailbox" in captured.err
