# ABOUTME: Tests that settings read the environment on demand, apply the documented defaults and reject bad values.
# ABOUTME: Each test clears the variables it relies on so the developer's shell and .env cannot affect it.
import pytest

from uwh.settings import Settings

VARIABLES = (
    "RUN_MODE",
    "SEED",
    "MODEL_ID",
    "MODEL_BASE_URL",
    "ANTHROPIC_MODEL",
    "LEADGEN_URL",
    "MAILBOX_URL",
    "UWH_REGISTRY",
    "UWH_DB",
    "GIT_COMMIT",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("UWH_DB", "/tmp/uwh-test.db")


@pytest.mark.parametrize("mode", ["live", "replay", "record"])
def test_run_mode_accepts_the_three_modes(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("RUN_MODE", mode)
    assert Settings.load().run_mode == mode


@pytest.mark.parametrize("mode", ["", "Live", "dry", "replay "])
def test_run_mode_refuses_anything_else(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("RUN_MODE", mode)
    with pytest.raises(ValueError, match="RUN_MODE"):
        Settings.load()


def test_defaults() -> None:
    s = Settings.load()
    assert s.run_mode == "live"
    assert s.seed == 42
    assert s.model_id == "deepseek-flash"
    assert s.model_base_url == "https://api.deepseek.com/anthropic"
    assert s.leadgen_url == "http://leadgen:8080"
    assert s.mailbox_url == "http://mailbox:8080"
    assert s.registry_path == "/app/registry/field_registry.json"
    assert s.git_commit == "unknown"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "7")
    monkeypatch.setenv("MODEL_ID", "other-model")
    monkeypatch.setenv("MODEL_BASE_URL", "http://localhost:9000/anthropic")
    monkeypatch.setenv("LEADGEN_URL", "http://localhost:8081")
    monkeypatch.setenv("MAILBOX_URL", "http://localhost:8025")
    monkeypatch.setenv("UWH_REGISTRY", "/tmp/registry.json")
    monkeypatch.setenv("UWH_DB", "/tmp/other.db")
    monkeypatch.setenv("GIT_COMMIT", "abc123")
    s = Settings.load()
    assert s.seed == 7
    assert s.model_id == "other-model"
    assert s.model_base_url == "http://localhost:9000/anthropic"
    assert s.leadgen_url == "http://localhost:8081"
    assert s.mailbox_url == "http://localhost:8025"
    assert s.registry_path == "/tmp/registry.json"
    assert s.db_path == "/tmp/other.db"
    assert s.git_commit == "abc123"


def test_a_variable_from_another_provider_does_not_set_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "other-model")
    assert Settings.load().model_id == "deepseek-flash"


def test_db_path_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UWH_DB")
    with pytest.raises(ValueError, match="UWH_DB"):
        Settings.load()


def test_load_takes_an_explicit_environment() -> None:
    assert Settings.load({"UWH_DB": "/x.db", "SEED": "3"}).seed == 3


def test_non_integer_seed_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "forty-two")
    with pytest.raises(ValueError, match="SEED"):
        Settings.load()
