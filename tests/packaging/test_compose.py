# ABOUTME: Checks that compose.yaml defines the default-profile services of architecture section 14.
# ABOUTME: Parses compose.yaml and .dockerignore as files; no Docker calls.
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def services() -> dict[str, dict[str, Any]]:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return compose["services"]


@pytest.fixture(scope="module")
def volumes() -> dict[str, Any]:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return compose["volumes"] or {}


def named_volume_mounts(service: dict[str, Any], target: str) -> list[str]:
    """Named volumes (not bind mounts) mounted at target, by volume name."""
    found = []
    for entry in service.get("volumes", []):
        source, _, rest = entry.partition(":")
        if rest.split(":")[0] == target and not source.startswith((".", "/")):
            found.append(source)
    return found


def test_default_profile_has_exactly_the_three_services(services):
    default_profile = {name for name, service in services.items() if "profiles" not in service}
    assert default_profile == {"leadgen", "mailbox", "app"}


@pytest.mark.parametrize(
    ("name", "host_port", "dockerfile", "db_var", "db_path"),
    [
        ("leadgen", "8081:8080", "leadgen/Dockerfile", "LEADGEN_DB", "/data/leadgen.db"),
        ("mailbox", "8025:8080", "mailbox/Dockerfile", "MAILBOX_DB", "/data/mailbox.db"),
    ],
)
def test_stand_services(services, volumes, name, host_port, dockerfile, db_var, db_path):
    service = services[name]
    assert service["build"]["context"] == "./sim-harness"
    assert service["build"]["dockerfile"] == dockerfile
    assert service["ports"] == [host_port]
    assert service["environment"][db_var] == db_path
    mounts = named_volume_mounts(service, "/data")
    assert len(mounts) == 1
    assert mounts[0] in volumes


def test_leadgen_passes_debug_through(services):
    assert services["leadgen"]["environment"]["DEBUG"] == "${DEBUG:-false}"


def test_stand_services_have_separate_volumes(services):
    leadgen = named_volume_mounts(services["leadgen"], "/data")
    mailbox = named_volume_mounts(services["mailbox"], "/data")
    app = named_volume_mounts(services["app"], "/data")
    assert len({leadgen[0], mailbox[0], app[0]}) == 3


def test_app_build(services):
    build = services["app"]["build"]
    assert build["context"] == "."
    assert build["dockerfile"] == "Dockerfile"
    assert build["target"] == "app"
    assert build["args"]["GIT_COMMIT"] == "${GIT_COMMIT:-unknown}"


def test_app_ports_volume_and_env_file(services, volumes):
    app = services["app"]
    assert app["ports"] == ["8000:8000"]
    mounts = named_volume_mounts(app, "/data")
    assert len(mounts) == 1
    assert mounts[0] in volumes
    assert app["env_file"] in (".env", [".env"])


def test_app_environment(services):
    env = services["app"]["environment"]
    assert env["RUN_MODE"] == "${RUN_MODE:-live}"
    assert env["SEED"] == "${SEED:-42}"
    assert env["MODEL_ID"] == "${MODEL_ID:-deepseek-flash}"
    assert env["MODEL_BASE_URL"] == "${MODEL_BASE_URL:-https://api.deepseek.com/anthropic}"
    assert env["LEADGEN_URL"] == "http://leadgen:8080"
    assert env["MAILBOX_URL"] == "http://mailbox:8080"
    assert env["UWH_DB"] == "/data/app-${RUN_MODE:-live}.db"


def test_app_waits_for_healthy_stand_services(services):
    depends_on = services["app"]["depends_on"]
    assert set(depends_on) == {"leadgen", "mailbox"}
    for condition in depends_on.values():
        assert condition == {"condition": "service_healthy"}


def test_every_service_has_a_healthcheck(services):
    for name, service in services.items():
        assert service["healthcheck"]["test"], name


def test_stand_healthchecks_call_healthz(services):
    for name in ("leadgen", "mailbox"):
        assert services[name]["healthcheck"]["test"] == [
            "CMD",
            "curl",
            "-f",
            "http://localhost:8080/healthz",
        ]


def test_app_healthcheck_calls_api_run(services):
    assert services["app"]["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/run', timeout=3)",
    ]


def test_dockerignore_lists_the_excluded_paths():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for entry in (".env", ".git", ".venv", "web/node_modules", "web/dist"):
        assert entry in lines
