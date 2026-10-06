# ABOUTME: Tests the load-time check of a decision graph: a test node whose cases are numeric bands must cover every number once, with no gap and no overlap.
# ABOUTME: Graphs are built in the test from the cases under check; the shipped graph files are loaded to show they pass.
from typing import Any

import pytest
from pydantic import ValidationError

from uwh.rules.graphs import Graph, check_rows_are_applied, load_graphs


def graph_testing(*bands: dict[str, Any], field: str = "p_f") -> dict[str, Any]:
    """A graph whose one test sends each band to its own outcome."""
    outcomes = {
        f"outcome_{i}": {"kind": "outcome", "board_path": [f"X:{i}"], "effects": []}
        for i in range(len(bands))
    }
    return {
        "id": "demo",
        "page": "docs/playbook/demo.md",
        "applies_when": {"always": True},
        "root": "band",
        "nodes": {
            "band": {
                "kind": "test",
                "field": field,
                "board_path": ["X:ROOT"],
                "cases": [{"when": band, "then": f"outcome_{i}"} for i, band in enumerate(bands)],
            },
            **outcomes,
        },
    }


COMPLETE = [{"lte": 0.15}, {"gt": 0.15, "lt": 0.50}, {"gte": 0.50}]


def test_complete_disjoint_bands_load_in_any_order() -> None:
    Graph.model_validate(graph_testing(*COMPLETE))
    Graph.model_validate(graph_testing(*reversed(COMPLETE)))


@pytest.mark.parametrize(
    ("bands", "message"),
    [
        ([{"lte": 0.15}, {"gt": 0.15, "lt": 0.50}], "do not reach both ends"),
        ([{"gt": 0.15}], "do not reach both ends"),
        ([{"lt": 1}, {"gt": 1}], "leave a gap at 1"),
        ([{"lt": 1}, {"gte": 2}], "leave a gap at 2"),
        ([{"lte": 1}, {"gte": 1}], "overlap at 1"),
        ([{"lt": 2}, {"gt": 1}], "overlap at 1"),
    ],
)
def test_bands_with_a_gap_or_an_overlap_are_refused_when_the_graph_loads(
    bands: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Graph.model_validate(graph_testing(*bands))


def test_a_test_on_discrete_values_need_not_cover_every_value() -> None:
    Graph.model_validate(graph_testing({"equals": "Class A"}, {"in": ["Class B", "Class C"]}))


def test_the_shipped_graphs_load() -> None:
    assert {graph.id for graph in load_graphs()} >= {"roof", "siding", "replacement_cost"}


def test_an_interpretation_row_that_nothing_applies_is_refused() -> None:
    graph = Graph.model_validate(graph_testing(*COMPLETE))
    rows = [
        {"id": "I90", "applied_in": "validator"},
        {"id": "I91", "not_evaluated": True},
        {"id": "I92"},
    ]

    with pytest.raises(ValueError, match=r"\['I92'\]"):
        check_rows_are_applied([graph], rows)
