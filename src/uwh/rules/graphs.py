# ABOUTME: The decision graphs of 9.6 and A.6: the graph files, the three-valued test of when a page applies, and the walk of a graph over a lead's usable facts.
# ABOUTME: Walking supports `test` and `outcome` nodes; a test on an unknown field leaves the page undecided, naming the field, and a graph with no root holds only `applies_when`.
from collections.abc import Mapping
from functools import cache
from typing import Literal

from pydantic import JsonValue

from uwh.rules.data_files import DATA_DIR, read_yaml
from uwh.rules.models import Effect, PlannedEffect, RuleTrace, StrictModel, UndecidedPage


class Case(StrictModel):
    when: dict[str, JsonValue]
    then: str


class Node(StrictModel):
    kind: Literal["test", "outcome"]
    board_path: list[str]
    field: str | None = None  # a registry field or a derived input
    interpretation: str | None = None
    cases: list[Case] = []
    effects: list[Effect] = []


class Graph(StrictModel):
    id: str
    page: str
    applies_when: dict[str, JsonValue]
    root: str | None = None
    nodes: dict[str, Node] = {}


class NotEncodedPage(StrictModel):
    id: str
    title: str
    page: str
    applies_when: dict[str, JsonValue]


@cache
def load_graphs() -> tuple[Graph, ...]:
    """Every graph file, in file name order."""
    paths = sorted(p for p in (DATA_DIR / "graphs").glob("*.yaml") if p.name != "_not_encoded.yaml")
    return tuple(Graph.model_validate(read_yaml(f"graphs/{p.name}")) for p in paths)


@cache
def load_not_encoded_pages() -> tuple[NotEncodedPage, ...]:
    return tuple(
        NotEncodedPage.model_validate(page)
        for page in read_yaml("graphs/_not_encoded.yaml")["pages"]
    )


@cache
def _interpretation_params() -> dict[str, float]:
    """Row parameters by `<row id>.<name>`, which a graph bound names."""
    return {
        f"{row['id']}.{name}": value
        for row in read_yaml("interpretation.yaml")["rows"]
        for name, value in row.get("params", {}).items()
    }


def _bound(bound: JsonValue) -> float:
    """A bound is a number, or one minus or one plus a row parameter (the replacement cost tolerance)."""
    if isinstance(bound, dict):
        ((form, name),) = bound.items()
        parameter = _interpretation_params()[str(name)]
        return 1 - parameter if form == "one_minus" else 1 + parameter
    assert isinstance(bound, int | float)
    return float(bound)


def _holds(clause: str, operand: JsonValue, value: JsonValue) -> bool:
    if clause == "equals":
        return value == operand
    if clause == "in":
        assert isinstance(operand, list)
        return value in operand
    assert isinstance(value, int | float)
    limit = _bound(operand)
    return {
        "lt": value < limit,
        "lte": value <= limit,
        "gt": value > limit,
        "gte": value >= limit,
    }[clause]


def _derived_input(name: str, facts: Mapping[str, JsonValue]) -> JsonValue:
    """A derived input of `derivations.yaml`, or None when an input is unknown or the divisor is zero."""
    spec = read_yaml("derivations.yaml")["derived_inputs"][name]
    if spec["operation"] != "ratio":
        raise ValueError(f"the derived input operation {spec['operation']} is not built")
    numerator, divisor = (facts.get(field) for field in spec["inputs"])
    if (
        not isinstance(numerator, int | float)
        or not isinstance(divisor, int | float)
        or divisor == 0
    ):
        return None
    return numerator / divisor


def _value(field: str, facts: Mapping[str, JsonValue]) -> JsonValue:
    if field in read_yaml("derivations.yaml")["derived_inputs"]:
        return _derived_input(field, facts)
    return facts.get(field)


def applies(condition: Mapping[str, JsonValue], facts: Mapping[str, JsonValue]) -> bool | None:
    """Whether a page's `applies_when` holds: None when it rests on a fact that is unknown, and for
    `any`, true when any member is true, otherwise unknown when any member is unknown (A.6)."""
    if condition.get("always"):
        return True
    if "any" in condition:
        members = condition["any"]
        assert isinstance(members, list)
        results = [applies(member, facts) for member in members if isinstance(member, dict)]
        return True if True in results else None if None in results else False
    field = str(condition["field"])
    if field not in facts:
        return None
    return all(
        _holds(clause, operand, facts[field])
        for clause, operand in condition.items()
        if clause != "field"
    )


def unknown_fields(condition: Mapping[str, JsonValue], facts: Mapping[str, JsonValue]) -> list[str]:
    """The fields an `applies_when` waits on."""
    if "any" in condition:
        members = condition["any"]
        assert isinstance(members, list)
        return [f for m in members if isinstance(m, dict) for f in unknown_fields(m, facts)]
    field = condition.get("field")
    return [str(field)] if field is not None and field not in facts else []


def evaluate_graph(
    graph: Graph, facts: Mapping[str, JsonValue]
) -> list[PlannedEffect] | UndecidedPage:
    """Walk the graph from its root over the usable facts. The effects of the outcome reached are
    committed, each with the board path from the root; a test on an unknown field leaves the page
    undecided. Raises ValueError for a value no case of a test covers."""
    assert graph.root is not None, "a graph with no root is not walked"
    path: list[str] = []
    node = graph.nodes[graph.root]
    while node.kind == "test":
        assert node.field is not None
        path += node.board_path
        value = _value(node.field, facts)
        if value is None:
            return UndecidedPage(graph=graph.id, waits_on=[node.field])
        chosen = next(
            (
                case
                for case in node.cases
                if all(_holds(clause, operand, value) for clause, operand in case.when.items())
            ),
            None,
        )
        if chosen is None:
            raise ValueError(f"the {graph.id} graph has no case for {node.field} = {value}")
        node = graph.nodes[chosen.then]
    trace = RuleTrace(board_path=path + node.board_path)
    return [PlannedEffect(effect=effect, trace=trace, committed=True) for effect in node.effects]
