# ABOUTME: Tests of tools/capture_world.py: the wrapper leaves Stand's output unchanged, the guarantee-pass check fires, and the fixture entries hold the section 9.4 values.
# ABOUTME: The generator runs in process for seed 42, the one seed the app reads.
import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from leadgen import archetypes, generator  # Stand's module; tests/conftest.py puts it on sys.path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import capture_world  # noqa: E402


SEED = 42


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return capture_world.load_config()


@pytest.fixture(scope="module")
def world(config: dict[str, Any]) -> dict[str, Any]:
    return capture_world.build_world(SEED, config)


def test_wrapped_output_equals_unwrapped_output_field_for_field(config: dict[str, Any]) -> None:
    unwrapped = generator.generate_queue(SEED, 10, "mixed", copy.deepcopy(config))
    with capture_world.recording() as records:
        wrapped = generator.generate_queue(SEED, 10, "mixed", copy.deepcopy(config))
    assert len(wrapped) == len(unwrapped) == 10
    for got, want in zip(wrapped, unwrapped, strict=True):
        assert got.keys() == want.keys()
        for key in want:
            assert got[key] == want[key], (want["lead_id"], key)
    assert len(records) == 10


def test_seed_42_recording_holds_the_named_archetypes(config: dict[str, Any]) -> None:
    _, records = capture_world.capture_queue(42, config)
    names = sorted(e.archetype for r in records for e in r.effects)
    assert names == sorted(
        ["occupancy_conflict"] * 2
        + ["post_and_pier"]
        + ["profile_kyc"] * 3
        + ["wildfire_severe"] * 2
    )


def test_guarantee_pass_assertion_raises_when_the_guarantee_exceeds_the_natural_count(
    config: dict[str, Any],
) -> None:
    raised = copy.deepcopy(config)
    raised["queue"]["guarantee_hard_archetypes"] = 10
    base_lead = generator._base_lead
    generate_lead = generator.generate_lead
    archetype_table = dict(archetypes.ARCHETYPES)
    with pytest.raises(capture_world.GuaranteePassFired, match="guarantee pass"):
        capture_world.capture_queue(42, raised)
    # the generator is restored after the error
    assert generator._base_lead is base_lead
    assert generator.generate_lead is generate_lead
    assert archetypes.ARCHETYPES.keys() == archetype_table.keys()
    for name, original in archetype_table.items():
        assert archetypes.ARCHETYPES[name] is original


def test_wildfire_archetype_value_stays_on_the_lead_and_the_base_value_is_kept_apart(
    world: dict[str, Any],
) -> None:
    entry = world["leads"]["LEAD-00000042-003"]
    assert entry["fields"]["p_f"] >= 0.55
    assert entry["provider_values"]["p_f"]["value"] <= 0.2


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(capture_world, "DATA_DIR", tmp_path)
    return tmp_path


def test_check_fails_and_leaves_the_file_when_one_value_differs(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert capture_world.main(["--seed", "42"]) == 0
    path = data_dir / "world-42.json"
    world = json.loads(path.read_text(encoding="utf-8"))
    world["leads"]["LEAD-00000042-001"]["provider_values"]["p_f"]["value"] = 0.99
    edited = capture_world.render(world)
    path.write_text(edited, encoding="utf-8")
    assert capture_world.main(["--seed", "42", "--check"]) == 1
    assert "differs" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == edited


def test_committed_fixture_equals_a_fresh_capture() -> None:
    assert capture_world.main(["--seed", str(SEED), "--check"]) == 0
