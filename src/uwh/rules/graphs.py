# ABOUTME: The decision graphs of 9.6 and A.6: the graph files, the three-valued test of when a page applies, and the walk of a graph over a lead's usable facts.
# ABOUTME: Walking supports `test` and `outcome` nodes; a test on an unknown field leaves the page undecided, naming the field, and a graph with no root holds only `applies_when`.
import math
from collections.abc import Mapping
from functools import cache
from typing import Literal, Self

from pydantic import JsonValue, model_validator

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

    @model_validator(mode="after")
    def _bands_are_complete_and_disjoint(self) -> Self:
        """A test whose cases are numeric bands covers every number exactly once (9.6). A test on
        discrete values is not checked: the values a field can take are not known here."""
        for name, node in self.nodes.items():
            bands = [_band(case.when) for case in node.cases]
            if node.kind == "test" and all(band is not None for band in bands):
                _check_bands(f"{self.id}.{name}", [band for band in bands if band is not None])
        return self


class NotEncodedPage(StrictModel):
    id: str
    title: str
    producer_text: str  # the packet's note that the page was not reviewed
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


# A numeric band: its lower and upper bound, each a value and whether the band includes it.
type _Band = tuple[tuple[float, bool], tuple[float, bool]]


def _band(when: Mapping[str, JsonValue]) -> _Band | None:
    """The band a case selects, or None when the case is not made of numeric bounds."""
    lower, upper = (-math.inf, False), (math.inf, False)
    for clause, operand in when.items():
        match clause:
            case "gt" | "gte":
                lower = (_bound(operand), clause == "gte")
            case "lt" | "lte":
                upper = (_bound(operand), clause == "lte")
            case _:
                return None
    return lower, upper


def _check_bands(where: str, bands: list[_Band]) -> None:
    """Raise ValueError unless the bands cover the number line with no gap and no overlap."""
    ordered = sorted(bands)
    if ordered[0][0][0] != -math.inf or ordered[-1][1][0] != math.inf:
        raise ValueError(f"the bands of {where} do not reach both ends of the number line")
    for (_, (high, high_closed)), ((low, low_closed), _) in zip(ordered, ordered[1:], strict=False):
        if high != low or high_closed == low_closed:
            overlap = high > low or (high == low and high_closed and low_closed)
            raise ValueError(
                f"the bands of {where} {'overlap' if overlap else 'leave a gap'} at {low}"
            )


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
