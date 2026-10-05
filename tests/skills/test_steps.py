# ABOUTME: Tests the one command-class check of the workflow steps: the resolve step writes provider results only when the manifest of resolve_data declares `fetch_data` (7.4).
# ABOUTME: The manifest is read from a temporary skills folder; the database and the registry are real.
from pathlib import Path

import pytest
import yaml

from tests.api.helpers import REGISTRY
from tests.runtime.helpers import insert_run, ticking_context
from uwh.providers.stand_in import StandInProviders
from uwh.rules.registry import load_registry
from uwh.runtime.facts import LedgerRules
from uwh.runtime.store import open_store
from uwh.skills import steps


def test_the_resolve_step_is_refused_when_its_manifest_does_not_declare_fetch_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = yaml.safe_load((steps._SKILLS_ROOT / "resolve_data" / "manifest.yaml").read_text())
    manifest["command_classes"] = ["send_routine_request"]
    folder = tmp_path / "skills" / "resolve_data"
    folder.mkdir(parents=True)
    (folder / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    monkeypatch.setattr(steps, "_SKILLS_ROOT", tmp_path / "skills")
    db = open_store(str(tmp_path / "app.db"))
    insert_run(db)
    db.commit()
    registry = load_registry(str(REGISTRY))

    with pytest.raises(ValueError, match="does not declare fetch_data"):
        steps._resolve_step(
            registry, StandInProviders({}), LedgerRules(), db, ticking_context()(), "L-1"
        )
