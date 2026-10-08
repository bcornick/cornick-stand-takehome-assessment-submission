# ABOUTME: What the playbook makes of the lead's values, read from the pages' decision graphs: each value shown with an open choice (fails, declines, passes, the underwriter's call, depends on the client) and why a decline was reached.
# ABOUTME: A reading follows the node a value leads to in the graph; it is computed for the view and is no part of the stored plan.
from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from uwh.api.views import ChoiceReading
from uwh.rules.graphs import (
    AllOf,
    Choice,
    FieldTest,
    Graph,
    Ladder,
    Outcome,
    input_value,
    matching_case,
)
from uwh.rules.models import ActionPlan, DeclineEffect, OpenChoice
from uwh.rules.registry import FactField

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
    nothing from, or that is missing, has no entry."""
    graph = next(
        g
        for g in graphs
        if any(isinstance(n, Choice) and n.choice == choice.choice_id for n in g.nodes.values())
    )
    readings: dict[str, ChoiceReading] = {}
    for key in choice.show:
        value = facts.get(key)
        reading = None if value is None else _reading(graph, key, value)
        if reading is not None:
            readings[key] = reading
    return readings


def _said(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _listed(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _path(graph: Graph, name: str, target: str, facts: Mapping[str, JsonValue]) -> list[str] | None:
    """The node names from `name` to `target` along the cases the facts take; a choice may take
    any option, since the ruling that took it is not a fact."""
    if name == target:
        return [name]
    node = graph.nodes[name]
    match node:
        case FieldTest():
            value = input_value(node.field, facts)
            case = None if value is None else matching_case(node, value)
            following = [] if case is None else [case.then]
        case Choice():
            following = list(node.options.values())
        case AllOf():
            following = node.children
        case Ladder():
            following = node.rungs
        case _:
            following = []
    for then in following:
        rest = _path(graph, then, target, facts)
        if rest is not None:
            return [name, *rest]
    return None


def _why(
    graph: Graph,
    path: list[str],
    facts: Mapping[str, JsonValue],
    fields: Mapping[str, FactField],
    choice_reasons: Mapping[str, str],
) -> list[str]:
    """What led along the path: the value the page applies on, each value tested, each choice taken
    with the underwriter's reason for it."""

    def value_of(key: str) -> str:
        label = fields[key].label if key in fields else key.replace("_", " ")
        value = _said(input_value(key, facts))
        if key.startswith("q:"):
            return f"the producer answered {value} to “{label}”"
        return f"{label} is {value}"

    applies_on = graph.applies_when.get("field")
    reasons = [value_of(applies_on)] if isinstance(applies_on, str) and applies_on in facts else []
    for name, then in zip(path, path[1:]):
        node = graph.nodes[name]
        if isinstance(node, FieldTest):
            reasons.append(value_of(node.field))
        elif isinstance(node, Choice):
            option = next(o for o, target in node.options.items() if target == then)
            given = choice_reasons.get(node.choice)
            said = f" (“{given}”)" if given else ""
            reasons.append(f"you chose {option.replace('_', ' ')}{said}")
    return reasons


def decline_reason(
    plan: ActionPlan,
    graphs: Sequence[Graph],
    facts: Mapping[str, JsonValue],
    fields: Mapping[str, FactField],
    choice_reasons: Mapping[str, str],
) -> str:
    """Why the lead is declined: the underwriter's own reason, or for each committed decline the
    values on its path through the page's graph, the page and the rule; `choice_reasons` holds the
    underwriter's reason for each choice ruled, by choice id."""
    if plan.underwriter_decline is not None:
        return plan.underwriter_decline
    reasons = []
    for planned in plan.effects:
        if not (planned.committed and isinstance(planned.effect, DeclineEffect)):
            continue
        rule, board_path = planned.effect.rule, planned.trace.board_path
        for graph in graphs:
            outcome = next(
                (
                    name
                    for name, node in graph.nodes.items()
                    if isinstance(node, Outcome)
                    and any(getattr(e, "rule", None) == rule for e in node.effects)
                    and board_path[-len(node.board_path) :] == node.board_path
                ),
                None,
            )
            path = None if outcome is None else _path(graph, graph.root, outcome, facts)
            if path is not None:
                page = graph.id.replace("_", " ")
                why = _why(graph, path, facts, fields, choice_reasons)
                led = f"{_listed(why)}, so " if why else ""
                reasons.append(f"{led}the {page} page declines it ({rule})")
                break
    return "; ".join(reasons) if reasons else "the playbook declines it"
