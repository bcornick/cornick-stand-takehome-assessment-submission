# ABOUTME: What the playbook makes of each value shown with an open choice, read from the page's decision graph: it fails the page, declines, passes, is the underwriter's call or depends on the client.
# ABOUTME: A reading follows the node a value leads to in the graph; it is computed for the view and is no part of the stored plan.
from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from uwh.api.views import ChoiceReading
from uwh.rules.graphs import (
    AllOf,
    Choice,
    FieldTest,
    Graph,
    Outcome,
    matching_case,
)
from uwh.rules.models import DeclineEffect, OpenChoice

NOT_PROVIDED = ChoiceReading(text="Not provided", problem=False)
# Interpretation row I16 is where the board sets no threshold.
_NO_THRESHOLD = "I16"


def _your_call(choice: Choice) -> ChoiceReading:
    why = (
        "the playbook sets no threshold"
        if choice.interpretation == _NO_THRESHOLD
        else "the playbook does not settle it"
    )
    return ChoiceReading(text=f"Your call: {why}", problem=False)


def _leads_to(graph: Graph, name: str) -> ChoiceReading | None:
    """The reading of the node a value leads to; None for a node no reading is defined for."""
    node = graph.nodes[name]
    match node:
        case Outcome():
            if any(isinstance(effect, DeclineEffect) for effect in node.effects):
                return ChoiceReading(text="Declines", problem=True)
            return ChoiceReading(text="Passes", problem=False)
        case Choice():
            return _your_call(node)
        case AllOf(children=[only]):
            return _leads_to(graph, only)
        case FieldTest(kind="producer_question"):
            return ChoiceReading(text="Passes only if the client will mitigate", problem=False)
        case _:
            return None


def _reading(graph: Graph, key: str, value: JsonValue) -> ChoiceReading | None:
    if graph.applies_when.get("field") == key:
        return ChoiceReading(text=f"Fails: above {graph.applies_when['gt']:.2f}", problem=True)
    nodes = graph.nodes.values()
    tests = [n for n in nodes if isinstance(n, FieldTest) and n.field == key]
    if tests:
        case = matching_case(tests[0], value)
        if case is None:
            return None
        then = graph.nodes[case.then]
        # A value that leads on to another field's choice passes its own check; that choice's
        # value carries its own reading.
        if isinstance(then, Choice) and key not in then.show:
            return ChoiceReading(text="Passes", problem=False)
        return _leads_to(graph, case.then)
    # The root choice shows every value of the page; a value no test reads is another choice's.
    own = [
        n
        for name, n in graph.nodes.items()
        if isinstance(n, Choice) and name != graph.root and key in n.show
    ]
    return _your_call(own[0]) if own else None


def choice_readings(
    choice: OpenChoice, graphs: Sequence[Graph], facts: Mapping[str, JsonValue]
) -> dict[str, ChoiceReading]:
    """The reading of each value the choice shows, keyed by field; a value the graph reads
    nothing from has no entry. A missing value reads as not provided."""
    graph = next(
        g
        for g in graphs
        if any(isinstance(n, Choice) and n.choice == choice.choice_id for n in g.nodes.values())
    )
    readings: dict[str, ChoiceReading] = {}
    for key in choice.show:
        value = facts.get(key)
        reading = NOT_PROVIDED if value is None else _reading(graph, key, value)
        if reading is not None:
            readings[key] = reading
    return readings
