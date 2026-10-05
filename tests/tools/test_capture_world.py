# ABOUTME: Tests of tools/capture_world.py: the wrapper leaves Stand's output unchanged, the guarantee-pass check fires, and the fixture entries hold the section 9.4 values.
# ABOUTME: The generator runs in process; the two not_found leads are checked against the lead's own fields.
import copy
import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest
from leadgen import archetypes, generator  # Stand's module; tests/conftest.py puts it on sys.path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import capture_world  # noqa: E402

from uwh.runtime.hashing import hash_json  # noqa: E402

SEEDS = (42, 11, 15)


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return capture_world.load_config()


@pytest.fixture(scope="module")
def worlds(config: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {seed: capture_world.build_world(seed, config) for seed in SEEDS}


@pytest.mark.parametrize("seed", SEEDS)
def test_wrapped_output_equals_unwrapped_output_field_for_field(
    seed: int, config: dict[str, Any]
) -> None:
    unwrapped = generator.generate_queue(seed, 10, "mixed", copy.deepcopy(config))
    with capture_world.recording() as records:
        wrapped = generator.generate_queue(seed, 10, "mixed", copy.deepcopy(config))
    assert len(wrapped) == len(unwrapped) == 10
    for got, want in zip(wrapped, unwrapped, strict=True):
        assert got.keys() == want.keys()
        for key in want:
            assert got[key] == want[key], (want["lead_id"], key)
    assert len(records) == 10


def test_wrapper_restores_the_generator_after_a_generation() -> None:
    before = (generator._base_lead, generator.generate_lead, dict(generator.archetypes.ARCHETYPES))
    with capture_world.recording():
        assert generator._base_lead is not before[0]
    assert generator._base_lead is before[0]
    assert generator.generate_lead is before[1]
    assert dict(generator.archetypes.ARCHETYPES) == before[2]


@pytest.mark.parametrize("seed", SEEDS)
def test_recording_is_non_empty_and_consistent_with_the_final_lead(
    seed: int, config: dict[str, Any]
) -> None:
    leads, records = capture_world.capture_queue(seed, config)
    assert sum(len(r.effects) for r in records) > 0
    for lead, record in zip(leads, records, strict=True):
        assert record.lead_id == lead["lead_id"]
        assert len(record.base) == 73
        for effect in record.effects:
            assert effect.set_values or effect.nulled
            for name, value in effect.set_values.items():
                assert lead["fields"][name] == value
            for name in effect.nulled:
                assert lead["fields"][name] is None


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


@pytest.mark.parametrize("seed", SEEDS)
def test_guarantee_pass_is_silent_under_the_supplied_config(
    seed: int, config: dict[str, Any]
) -> None:
    assert config["queue"]["guarantee_hard_archetypes"] == 4
    capture_world.capture_queue(seed, config)


@pytest.mark.parametrize("seed", SEEDS)
def test_each_entry_holds_every_provider_field_and_a_fingerprint_of_the_final_lead(
    seed: int, worlds: dict[int, dict[str, Any]], config: dict[str, Any]
) -> None:
    world = worlds[seed]
    leads, records = capture_world.capture_queue(seed, config)
    assert list(world["leads"]) == [ld["lead_id"] for ld in leads]
    for lead, record in zip(leads, records, strict=True):
        entry = world["leads"][lead["lead_id"]]
        assert entry["fingerprint"] == hash_json(lead["fields"])
        assert entry["fields"] == lead["fields"]
        assert list(entry["provider_values"]) == list(capture_world.PROVIDER_FIELDS)
        assert "roof_classification" not in entry["provider_values"]
        assert "siding_classification" not in entry["provider_values"]
        for name, result in entry["provider_values"].items():
            if result["status"] == "found":
                assert result["value"] == record.base[name]
                assert record.base[name] is not None
            else:
                assert result == {"status": "not_found", "value": None}
        for name, value in entry["archetype_set"].items():
            assert name in capture_world.PROVIDER_FIELDS
            assert lead["fields"][name] == value


def test_replacement_cost_holds_the_base_value_that_predates_the_archetype_nulling_it(
    worlds: dict[int, dict[str, Any]], config: dict[str, Any]
) -> None:
    # Lead 0 of seed 11 is drawn the way generate_queue draws it: the tier shuffle first, then
    # the lead's own _base_lead on the same stream.
    rng = random.Random(11)
    tier_mix = config["queue"]["tier_mix"]
    generator._tier_sequence(rng, capture_world.COUNT, capture_world.DIFFICULTY, tier_mix)
    base = generator._base_lead(rng)
    first = worlds[11]["leads"]["LEAD-00000011-000"]
    for name in capture_world.PROVIDER_FIELDS:
        assert first["provider_values"][name] == {"status": "found", "value": base[name]}

    # LEAD-00000011-001: replacement_cost_gap nulled replacement_cost and moved coverage_a. The
    # provider keeps the base value, which sits outside the ratio band of the final coverage_a.
    gap = worlds[11]["leads"]["LEAD-00000011-001"]
    assert gap["fields"]["replacement_cost"] is None
    result = gap["provider_values"]["replacement_cost"]
    assert result["status"] == "found"
    final_coverage = gap["fields"]["coverage_a"]
    assert not int(final_coverage * 0.95) <= result["value"] <= int(final_coverage * 1.1)


def test_wildfire_archetype_values_are_recorded_as_set_and_the_base_value_is_kept_apart(
    worlds: dict[int, dict[str, Any]],
) -> None:
    entry = worlds[42]["leads"]["LEAD-00000042-003"]
    assert entry["archetype_set"]["p_f"] == entry["fields"]["p_f"]
    assert entry["archetype_set"]["p_f"] >= 0.55
    assert entry["provider_values"]["p_f"]["value"] <= 0.2


def test_kyc_score_is_not_found_on_lead_11_008_which_holds_every_lookup_input(
    worlds: dict[int, dict[str, Any]],
) -> None:
    entry = worlds[11]["leads"]["LEAD-00000011-008"]
    assert entry["provider_values"]["kyc_score"] == {"status": "not_found", "value": None}
    assert entry["fields"]["kyc_score"] is None
    for name in ("first_name", "last_name", "insured_dob"):
        assert entry["fields"][name]


def test_protection_class_is_not_found_on_lead_15_003_which_holds_the_full_address(
    worlds: dict[int, dict[str, Any]],
) -> None:
    entry = worlds[15]["leads"]["LEAD-00000015-003"]
    assert entry["provider_values"]["protection_class"] == {"status": "not_found", "value": None}
    assert entry["fields"]["protection_class"] is None
    for name in ("street_address", "city", "state", "zip"):
        assert entry["fields"][name]


def test_not_found_entries_are_exactly_the_four_nulled_by_the_rural_and_profile_archetypes(
    worlds: dict[int, dict[str, Any]],
) -> None:
    not_found = {
        (lead_id, name)
        for world in worlds.values()
        for lead_id, entry in world["leads"].items()
        for name, result in entry["provider_values"].items()
        if result["status"] == "not_found"
    }
    assert not_found == {
        ("LEAD-00000011-008", "kyc_score"),
        ("LEAD-00000015-003", "protection_class"),
        ("LEAD-00000015-004", "protection_class"),
        ("LEAD-00000015-007", "protection_class"),
    }
    assert not any(
        result["status"] == "not_found"
        for entry in worlds[42]["leads"].values()
        for result in entry["provider_values"].values()
    )


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(capture_world, "DATA_DIR", tmp_path)
    return tmp_path


def test_writing_is_byte_identical_on_every_run_and_check_passes(data_dir: Path) -> None:
    assert capture_world.main(["--seed", "42"]) == 0
    first = (data_dir / "world-42.json").read_bytes()
    assert capture_world.main(["--seed", "42"]) == 0
    assert (data_dir / "world-42.json").read_bytes() == first
    assert first.endswith(b"}\n") and b"\r" not in first
    assert capture_world.main(["--seed", "42", "--check"]) == 0
    assert json.loads(first)["seed"] == 42


def test_check_fails_and_writes_nothing_when_the_file_is_absent(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert capture_world.main(["--seed", "42", "--check"]) == 1
    assert "missing" in capsys.readouterr().err
    assert list(data_dir.iterdir()) == []


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


@pytest.mark.parametrize("seed", SEEDS)
def test_committed_fixture_equals_a_fresh_capture(seed: int) -> None:
    assert capture_world.main(["--seed", str(seed), "--check"]) == 0
