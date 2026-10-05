# ABOUTME: Tests of tools/export_openapi.py: it writes the app's OpenAPI document deterministically and --check fails when the file differs or is absent.
# ABOUTME: Each test works on a temporary copy; the tracked web/src/api/openapi.json is only read.
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from uwh.api.app import create_app
from uwh.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
TRACKED = ROOT / "web" / "src" / "api" / "openapi.json"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_openapi", ROOT / "tools" / "export_openapi.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_document() -> dict[str, object]:
    return create_app(Settings.load({"UWH_DB": "unused.db"})).openapi()


def test_writing_produces_the_apps_document_in_a_fixed_form(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    assert load_tool().main(["--output", str(target)]) == 0
    raw = target.read_bytes()
    assert json.loads(raw) == app_document()
    text = raw.decode("utf-8")
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert "\r" not in text
    assert text == json.dumps(app_document(), indent=2, sort_keys=True) + "\n"


def test_check_passes_on_a_file_that_matches(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    tool = load_tool()
    tool.main(["--output", str(target)])
    assert tool.main(["--check", "--output", str(target)]) == 0


def test_check_fails_when_the_file_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "openapi.json"
    tool = load_tool()
    tool.main(["--output", str(target)])
    document = json.loads(target.read_text())
    del document["paths"]["/api/items"]
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    before = target.read_bytes()
    assert tool.main(["--check", "--output", str(target)]) == 1
    assert "differs" in capsys.readouterr().err
    assert target.read_bytes() == before, "--check does not rewrite the file"


def test_check_fails_when_the_file_is_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "openapi.json"
    assert load_tool().main(["--check", "--output", str(target)]) == 1
    assert "missing" in capsys.readouterr().err
    assert not target.exists()


def test_the_tracked_file_matches_the_app() -> None:
    assert load_tool().main(["--check"]) == 0
    assert TRACKED.is_file()
