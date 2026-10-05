# ABOUTME: Checks the rules data files against the architecture, the field registry and Stand's generator.
# ABOUTME: Every expectation is parsed from those sources or written out here, never read back from the file under test.
from pathlib import Path
from typing import Any

import yaml
from leadgen.generator import ROOF_CLASS, SIDING_CLASS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/uwh/rules/data"


def load(name: str) -> Any:
    return yaml.safe_load((DATA / name).read_text())


def test_derivation_maps_equal_stands_generator_maps_and_cite_them() -> None:
    maps = load("derivations.yaml")["maps"]
    assert maps["roof_classification"]["map"] == ROOF_CLASS
    assert maps["siding_classification"]["map"] == SIDING_CLASS
    for field, symbol, source_field in (
        ("roof_classification", "ROOF_CLASS", "roof_material"),
        ("siding_classification", "SIDING_CLASS", "siding_material"),
    ):
        assert maps[field]["source"] == {
            "file": "sim-harness/leadgen/generator.py",
            "symbol": symbol,
        }
        assert maps[field]["from"] == source_field
    assert (ROOT / "sim-harness/leadgen/generator.py").is_file()


def test_the_two_derived_inputs_declare_their_inputs() -> None:
    derived = load("derivations.yaml")["derived_inputs"]
    assert set(derived) == {"coverage_to_rce_ratio", "roof_age_years"}
    ratio = derived["coverage_to_rce_ratio"]
    assert ratio["operation"] == "ratio"
    assert ratio["inputs"] == ["coverage_a", "replacement_cost"]
    assert ratio["divisor"] == "replacement_cost"
    age = derived["roof_age_years"]
    assert age["operation"] == "years_before_reference"
    assert age["inputs"] == ["roof_replacement_year"]
