# ABOUTME: Checks the rules data files against the architecture, the field registry and Stand's generator.
# ABOUTME: Every expectation is parsed from those sources or written out here, never read back from the file under test.
import json
import re
import string
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


# ---------------------------------------------------------------------------
# Expectations parsed from docs/architecture.md and docs/brief/field_registry.json.
# ---------------------------------------------------------------------------

ARCHITECTURE = (ROOT / "docs/architecture.md").read_text()
REGISTRY = json.loads((ROOT / "docs/brief/field_registry.json").read_text())["fields"]


def squash(text: str) -> str:
    return " ".join(text.split())


def between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def table_cells(block: str) -> list[list[str]]:
    """The cells of every table row in the block, header and separator rows included."""
    return [
        [squash(cell) for cell in line.strip().strip("|").split(" | ")]
        for line in block.splitlines()
        if line.startswith("|")
    ]


SECTION_97 = between(ARCHITECTURE, "### 9.7 Interpretation table", "## 10. Messages")
ARCHITECTURE_ROWS = [
    cells
    for cells in table_cells(between(SECTION_97, "| Id |", "**Underwriter choices.**"))
    if re.fullmatch(r"I\d\d", cells[0])
]
ARCHITECTURE_CHOICES = {
    cells[0].strip("`"): re.findall(r"`([^`]+)`", cells[1])
    for cells in table_cells(between(SECTION_97, "| Choice id |", "**Fan-outs"))
    if cells[0].startswith("`I")
}
SECTION_95 = between(ARCHITECTURE, "### 9.5 Conflict validators", "### 9.6 Decision graphs")
VALIDATOR_ROWS = [cells for cells in table_cells(SECTION_95) if cells[0].startswith("`")]

ALL_IDS = [f"I{n:02d}" for n in range(1, 58)]
LENIENT = {"I03", "I19", "I20", "I21", "I24", "I25", "I29", "I30", "I32", "I42"}
QUESTION_FOR_STAND = {"I12", "I28", "I52"}
PRODUCER_EDITABLE = {name for name, entry in REGISTRY.items() if entry["editableByProducer"]}
REQUIRED_WHEN = {entry["requiredWhen"] for entry in REGISTRY.values() if "requiredWhen" in entry}
INTERNAL_TERMS = ("validator", "graph", "interpretation")
CONSEQUENCE_WORDS = (
    "decline",
    "price",
    "pricing",
    "premium",
    "surcharge",
    "ineligible",
    "exclu",
    "refus",
    "reject",
)


def interpretation_rows() -> list[dict[str, Any]]:
    return load("interpretation.yaml")["rows"]


def row_by_id() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in interpretation_rows()}


def test_the_architecture_table_parses_to_fifty_seven_rows_of_five_cells() -> None:
    assert len(ARCHITECTURE_ROWS) == 57
    assert all(len(cells) == 5 for cells in ARCHITECTURE_ROWS)
    assert sorted(cells[0] for cells in ARCHITECTURE_ROWS) == ALL_IDS
    assert len(ARCHITECTURE_CHOICES) == 12


def test_rows_run_from_i01_to_i57_in_order() -> None:
    assert [row["id"] for row in interpretation_rows()] == ALL_IDS


def test_each_row_carries_the_table_cells_exactly() -> None:
    rows = row_by_id()
    for id_, page, gap, ruling, kind in ARCHITECTURE_ROWS:
        row = rows[id_]
        assert row["page"] == page, id_
        assert squash(row["gap"]) == gap, id_
        assert squash(row["ruling"]) == ruling, id_
        assert row["kind"] == [letter.strip() for letter in kind.split(",")], id_
        assert set(row["kind"]) <= {"A", "P", "U", "N"}, id_


def test_each_row_states_a_rationale() -> None:
    for row in interpretation_rows():
        assert isinstance(row["rationale"], str) and row["rationale"].strip(), row["id"]


def test_the_two_lists_after_the_table_are_carried_as_flags() -> None:
    lenient_text = between(
        SECTION_97, "**Rows that read more leniently", "**Rows that are questions"
    )
    stand_text = SECTION_97[SECTION_97.index("**Rows that are questions") :]
    assert set(re.findall(r"I\d\d", lenient_text)) == LENIENT
    assert set(re.findall(r"I\d\d", stand_text)) == QUESTION_FOR_STAND
    rows = interpretation_rows()
    assert {row["id"] for row in rows if row.get("lenient")} == LENIENT
    assert {row["id"] for row in rows if row.get("question_for_stand")} == QUESTION_FOR_STAND
    assert all(row.get("lenient", True) is True for row in rows)
    assert all(row.get("question_for_stand", True) is True for row in rows)


def test_i03_names_its_trace_boxes() -> None:
    ruling = row_by_id()["I03"]["ruling"]
    assert "`02:SPOT`, `02:SPOT1` for KYC 6 to 7" in ruling
    assert "`02:HIGH`, `02:HIGH1` for KYC 8 to 10" in ruling


def test_choices_sit_on_the_underwriter_rows_and_equal_the_choices_table() -> None:
    rows = interpretation_rows()
    underwriter_rows = {row["id"] for row in rows if "U" in row["kind"]}
    assert underwriter_rows == {
        "I07",
        "I09",
        "I13",
        "I14",
        "I15",
        "I16",
        "I26",
        "I38",
        "I44",
        "I49",
    }
    assert {row["id"] for row in rows if "choices" in row} == underwriter_rows
    held = {choice["id"]: choice["options"] for row in rows for choice in row.get("choices", [])}
    assert held == ARCHITECTURE_CHOICES
    assert sum(len(row.get("choices", [])) for row in rows) == 12
    for row in rows:
        for choice in row.get("choices", []):
            assert set(choice) == {"id", "options"}
            assert choice["id"].startswith(row["id"] + "."), choice["id"]


def test_fan_outs_equal_the_fire_simulation_paragraph() -> None:
    paragraph = between(SECTION_97, "**Fan-outs on Fire Simulation.**", "**Rows that read")
    expected = {}
    for sentence in paragraph.split(". "):
        semantics = re.search(r"are `(all_of|one_of)`", sentence)
        assert semantics, sentence
        for box in re.findall(r"`(\d\d:[A-Z0-9]+)`", sentence):
            expected[box] = semantics.group(1)
    assert len(expected) == 7
    assert load("interpretation.yaml")["fan_outs"] == expected
    assert expected == {
        "04:LEGACY": "all_of",
        "04:MAP": "all_of",
        "04:ACCESS": "all_of",
        "04:VEG": "one_of",
        "04:INGRESS": "one_of",
        "04:MIND": "one_of",
        "04:SLOPE": "one_of",
    }


def test_only_i35_carries_params_and_the_tolerance_is_ten_percent() -> None:
    rows = interpretation_rows()
    assert {row["id"] for row in rows if "params" in row} == {"I35"}
    assert row_by_id()["I35"]["params"] == {"tolerance": 0.10}


def test_rows_not_evaluated_are_the_kind_n_rows() -> None:
    rows = interpretation_rows()
    assert {row["id"] for row in rows if row.get("not_evaluated")} == {
        row["id"] for row in rows if "N" in row["kind"]
    }
    assert {row["id"] for row in rows if "N" in row["kind"]} == {"I04", "I11", "I36", "I46", "I54"}


APPLIED_IN_CITES = {
    "I01": "kyc_score_out_of_range",
    "I06": "months_unoccupied_in_primary_home",
    "I20": "derivation",
    "I31": "section 9.1",
    "I45": "typed deadlines",
    "I47": "links",
    "I51": "section 9.3",
    "I53": "tenant_use_without_rental",
    "I56": "duration_of_non_occupancy",
    "I57": "collection rule",
}


def test_rows_applied_outside_the_graphs_name_what_applies_them() -> None:
    rows = row_by_id()
    for id_, cited in APPLIED_IN_CITES.items():
        assert cited in rows[id_]["applied_in"], id_
    assert {id_ for id_, row in rows.items() if "applied_in" in row} == set(APPLIED_IN_CITES)


# ---------------------------------------------------------------------------
# catalogue.yaml
# ---------------------------------------------------------------------------

CATALOGUE_ROWS = {
    "kt_extent": "I27",
    "kt_areas": "I27",
    "kt_present_and_where": "I51",
    "tankers_bring_water": "I41",
    "water_source_within_1000ft": "I41",
    "water_source_year_round": "I41",
    "dry_hydrant": "I41",
    "county_and_calfire_fittings": "I41",
    "paved_roads_year_round": "I41",
    "willing_to_mitigate": "I17",
    "rce_documentation": "I37",
}
ANSWER_TYPES = {"yes_no", "choice", "text", "document"}


def test_catalogue_holds_exactly_the_eleven_a7_ids() -> None:
    questions = load("catalogue.yaml")["questions"]
    assert {id_ for id_ in questions} == set(CATALOGUE_ROWS)
    for id_, entry in questions.items():
        assert entry["row"] == CATALOGUE_ROWS[id_], id_
        assert entry["answer_type"] in ANSWER_TYPES, id_
        assert entry["wording"].strip(), id_
        assert ("options" in entry) == (entry["answer_type"] == "choice"), id_
    assert questions["rce_documentation"]["answer_type"] == "document"


def test_catalogue_rows_exist_and_the_producer_rows_are_kind_p() -> None:
    rows = row_by_id()
    for id_, row in CATALOGUE_ROWS.items():
        assert row in rows, id_
        if id_ != "kt_present_and_where":
            assert "P" in rows[row]["kind"], id_


# ---------------------------------------------------------------------------
# wording.yaml
# ---------------------------------------------------------------------------

VALIDATOR_FIELDS = {
    "roof_year_in_future": ["roof_replacement_year"],
    "roof_year_before_year_built": ["roof_replacement_year", "year_built"],
    "effective_date_in_past": ["effective_date"],
    "panel_size_below_60": ["electrical_panel_size_amps"],
    "no_residents_in_primary_home": ["number_of_residents", "dwelling_use_type", "dwelling_type"],
    "acreage_zero": ["acreage"],
    "months_unoccupied_in_primary_home": [
        "months_unoccupied",
        "dwelling_use_type",
        "dwelling_type",
    ],
    "primary_use_with_rental": ["dwelling_use_type", "is_rental"],
    "owner_occupied_with_other_use": ["dwelling_type", "dwelling_use_type"],
    "tenant_use_without_rental": ["dwelling_use_type", "is_rental"],
    "tankless_with_tank_fields": [
        "water_heater_type",
        "water_heater_age_years",
        "water_heater_location",
    ],
    "kyc_score_out_of_range": ["kyc_score"],
}


def all_wording() -> list[str]:
    wording = load("wording.yaml")
    return (
        list(wording["fields"].values())
        + list(wording["preambles"].values())
        + [entry["question"] for entry in wording["confirmations"].values()]
        + [entry["wording"] for entry in load("catalogue.yaml")["questions"].values()]
    )


def test_every_producer_editable_field_has_a_question_and_no_other_field_does() -> None:
    fields = load("wording.yaml")["fields"]
    assert set(fields) == PRODUCER_EDITABLE
    assert len(PRODUCER_EDITABLE) == 61
    assert all(
        isinstance(question, str) and question.strip().endswith("?") for question in fields.values()
    )


def test_the_registry_has_six_distinct_required_when_forms_and_each_has_a_preamble() -> None:
    assert len(REQUIRED_WHEN) == 6
    preambles = load("wording.yaml")["preambles"]
    assert set(preambles) == REQUIRED_WHEN
    assert all(isinstance(text, str) and text.startswith("If ") for text in preambles.values())


def test_there_is_one_confirmation_per_section_95_row_and_each_lists_its_fields() -> None:
    assert len(VALIDATOR_ROWS) == 12
    confirmations = load("wording.yaml")["confirmations"]
    assert len(confirmations) == len(VALIDATOR_ROWS)
    assert {id_: entry["fields"] for id_, entry in confirmations.items()} == VALIDATOR_FIELDS
    for entry in confirmations.values():
        assert set(entry["fields"]) <= set(REGISTRY)


def test_confirmations_state_reported_values_by_field_placeholder() -> None:
    for id_, entry in load("wording.yaml")["confirmations"].items():
        placeholders = {
            name for _, name, _, _ in string.Formatter().parse(entry["question"]) if name
        }
        assert placeholders, id_
        assert placeholders <= set(entry["fields"]), id_
        assert entry["question"].strip().endswith("?"), id_


def test_wording_is_plain_and_states_no_consequence() -> None:
    for text in all_wording():
        lowered = text.lower()
        for word in INTERNAL_TERMS + CONSEQUENCE_WORDS:
            assert word not in lowered, (word, text)
