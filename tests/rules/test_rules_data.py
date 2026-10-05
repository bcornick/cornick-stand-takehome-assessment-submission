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
    for field, symbol in (
        ("roof_classification", "ROOF_CLASS"),
        ("siding_classification", "SIDING_CLASS"),
    ):
        assert maps[field]["source"] == {
            "file": "sim-harness/leadgen/generator.py",
            "symbol": symbol,
        }
        assert maps[field]["from"] == REGISTRY[field]["derivedFrom"]
    assert (ROOT / "sim-harness/leadgen/generator.py").is_file()


def test_the_two_derived_inputs_declare_their_inputs() -> None:
    derived = load("derivations.yaml")["derived_inputs"]
    assert set(derived) == {"coverage_to_rce_ratio", "roof_age_years"}
    ratio = derived["coverage_to_rce_ratio"]
    assert ratio["operation"] == "ratio"
    assert ratio["inputs"] == ["coverage_a", "replacement_cost"]
    age = derived["roof_age_years"]
    assert age["operation"] == "years_before_reference"
    assert age["inputs"] == ["roof_replacement_year"]
    assert set(ratio) == set(age) == {"operation", "inputs"}


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
CHOICE_CELLS = [
    cells
    for cells in table_cells(between(SECTION_97, "| Choice id |", "**Fan-outs"))
    if cells[0].startswith("`I")
]
ARCHITECTURE_CHOICES = {
    re.match(r"`([^`]+)`", cells[0]).group(1): re.findall(r"`([^`]+)`", cells[1])  # type: ignore[union-attr]
    for cells in CHOICE_CELLS
}
# The rows that carry a choice: the row the id is named for, or the rows the table says share it.
CHOICE_CARRIERS = {
    re.match(r"`([^`]+)`", cells[0]).group(1): (  # type: ignore[union-attr]
        set(re.findall(r"I\d\d", cells[0].split("(shared by")[1]))
        if "(shared by" in cells[0]
        else {cells[0][1:4]}
    )
    for cells in CHOICE_CELLS
}
SECTION_95 = between(ARCHITECTURE, "### 9.5 Conflict validators", "### 9.6 Decision graphs")
VALIDATOR_ROWS = [cells for cells in table_cells(SECTION_95) if cells[0].startswith("`")]
CATALOGUE_SENTENCE = between(ARCHITECTURE, "`catalogue.yaml` holds id,", "`wording.yaml` holds")

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
    assert len(ARCHITECTURE_CHOICES) == 10
    assert CHOICE_CARRIERS["I14.road_access"] == {"I14", "I44", "I49"}


def test_rows_run_from_i01_to_i57_in_order() -> None:
    assert [row["id"] for row in interpretation_rows()] == ALL_IDS


def test_each_row_carries_the_table_cells_exactly() -> None:
    rows = row_by_id()
    for id_, page, gap, ruling, kind in ARCHITECTURE_ROWS:
        row = rows[id_]
        assert row["source"] == page, id_
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
    held: dict[str, list[str]] = {}
    carriers: dict[str, set[str]] = {}
    for row in rows:
        for choice in row.get("choices", []):
            assert set(choice) == {"id", "options"}
            # a choice carried by several rows has the same options on each
            assert held.setdefault(choice["id"], choice["options"]) == choice["options"], row["id"]
            carriers.setdefault(choice["id"], set()).add(row["id"])
    assert held == ARCHITECTURE_CHOICES
    assert len(held) == 10
    assert carriers == CHOICE_CARRIERS


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


# `applied_in` reads "<category>: <what> (<citation>)". The category is one of the six places a row can be
# applied outside a graph node (section 9.6); the first backticked name after the colon is the thing named.
APPLIED_IN_CATEGORIES = {
    "validator",
    "derivation",
    "resolution rule",
    "rendering step",
    "graph page",
    "effect field",
}
# The section 9.5 validator that goes to the underwriter has an id but no confirmation template.
VALIDATOR_WITHOUT_TEMPLATE = "kyc_score_out_of_range"
APPLIED_IN_CATEGORY = {
    "I01": "validator",
    "I02": "graph page",
    "I06": "graph page",
    "I10": "graph page",
    "I12": "graph page",
    "I19": "graph page",
    "I20": "derivation",
    "I23": "graph page",
    "I25": "graph page",
    "I31": "resolution rule",
    "I34": "graph page",
    "I45": "effect field",
    "I47": "rendering step",
    "I51": "resolution rule",
    "I53": "validator",
    "I55": "graph page",
    "I56": "effect field",
    "I57": "resolution rule",
}


def test_rows_applied_outside_the_graph_nodes_name_what_applies_them() -> None:
    rows = row_by_id()
    assert {id_ for id_, row in rows.items() if "applied_in" in row} == set(APPLIED_IN_CATEGORY)
    confirmations = load("wording.yaml")["confirmations"]
    for id_, category in APPLIED_IN_CATEGORY.items():
        text = rows[id_]["applied_in"]
        assert category in APPLIED_IN_CATEGORIES, id_
        assert text.startswith(category + ": "), id_
        named = re.findall(r"`([^`]+)`", text.split(" (")[0])
        if category == "validator":
            assert len(named) == 1, id_
            assert named[0] in {*confirmations, VALIDATOR_WITHOUT_TEMPLATE}, id_
        if category == "graph page":
            assert len(named) == 1 and (ROOT / "docs/playbook" / named[0]).is_dir(), id_
        if category == "effect field":
            assert named == ["deadline"] and "(text, deadline)" in ARCHITECTURE, id_
        for file in re.findall(r"`([^`]+\.yaml)`", text):
            assert (DATA / file).is_file(), id_
    assert "derivations.yaml" in rows["I20"]["applied_in"]
    # the pairs that share a test: the row a test cites needs no applied_in, the outcome-only row does
    assert not {"I18", "I24", "I39", "I50"} & {
        id_ for id_, row in rows.items() if "applied_in" in row
    }


# ---------------------------------------------------------------------------
# catalogue.yaml
# ---------------------------------------------------------------------------

CATALOGUE_IDS = re.findall(r"`([a-z0-9_]+)`", CATALOGUE_SENTENCE.split("for each:")[1])
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
    assert len(CATALOGUE_IDS) == 11
    assert list(questions) == CATALOGUE_IDS
    assert list(CATALOGUE_ROWS) == CATALOGUE_IDS
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

# The registry fields a section 9.5 row names in its Validator cell, in the order the row gives them.
# The kyc_score range validator goes to the underwriter, so it has no confirmation (A.7).
PRODUCER_VALIDATOR_ROWS = [cells for cells in VALIDATOR_ROWS if "`kyc_score`" not in cells[0]]
VALIDATOR_FIELDS = [
    list(dict.fromkeys(f for f in re.findall(r"`([^`]+)`", cells[0]) if f in REGISTRY))
    for cells in PRODUCER_VALIDATOR_ROWS
]
# A required-when form whose dependents are blocked while protection class is unresolved (section 9.2).
BLOCKED_DEPENDENTS_FORM = "protection_class in (9, 10)"


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


def test_each_required_when_form_a_follow_on_can_take_has_a_preamble() -> None:
    assert len(REQUIRED_WHEN) == 6
    assert BLOCKED_DEPENDENTS_FORM in REQUIRED_WHEN
    preambles = load("wording.yaml")["preambles"]
    assert set(preambles) == REQUIRED_WHEN - {BLOCKED_DEPENDENTS_FORM}
    assert len(preambles) == 5
    assert all(isinstance(text, str) and text.startswith("If ") for text in preambles.values())


def test_there_is_one_confirmation_per_producer_validator_and_each_lists_its_fields() -> None:
    assert len(VALIDATOR_ROWS) == 12
    assert len(PRODUCER_VALIDATOR_ROWS) == 11
    confirmations = load("wording.yaml")["confirmations"]
    assert len(confirmations) == 11
    assert VALIDATOR_WITHOUT_TEMPLATE not in confirmations
    assert [entry["fields"] for entry in confirmations.values()] == VALIDATOR_FIELDS
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


def test_wording_addresses_the_applicant() -> None:
    for text in all_wording():
        lowered = text.lower()
        assert "insured" not in lowered and "client" not in lowered, text


def test_kt_areas_says_any_high_draw_area_is_answered_high_draw() -> None:
    entry = load("catalogue.yaml")["questions"]["kt_areas"]
    assert entry["options"] == ["high_draw", "low_draw"]
    assert "any high draw area" in entry["wording"]
    assert "answer high draw" in entry["wording"]


def test_willing_to_mitigate_uses_the_boards_words_and_names_no_distance() -> None:
    board = (ROOT / "docs/playbook/04-fire-simulation/flowchart.md").read_text()
    phrase = re.search(r"willingness to (mitigate [a-z ]+?)\"", board)
    assert phrase and phrase.group(1) == "mitigate greater distance"
    wording = load("catalogue.yaml")["questions"]["willing_to_mitigate"]["wording"]
    assert wording == "Is the applicant willing to " + phrase.group(1) + "?"
