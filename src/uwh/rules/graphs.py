# ABOUTME: The decision graphs of 9.6 and A.6: the graph files, the three-valued test of when a page applies, and the walk of a graph over a lead's usable facts and the underwriter's rulings.
# ABOUTME: A walk is decided, undecided or a decline on every branch; it carries the effects, the open choices and the catalogue questions the walk collects, each effect with the board path from the root.
import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from uwh.rules.data_files import DATA_DIR, read_yaml
from uwh.skills.vertical import REFERENCE_MORNING
from uwh.rules.models import (
    AdvisoryEffect,
    Assumption,
    DeclineEffect,
    Effect,
    ExclusionOrEndorsementEffect,
    OpenChoice,
    PlannedEffect,
    RuleTrace,
    Rulings,
    StrictModel,
    TraceBranch,
)


class Case(StrictModel):
    when: dict[str, JsonValue]
    then: str


class _NodeBase(StrictModel):
    board_path: list[str]  # the board boxes this node stands for, in order
    interpretation: str | None = None


class FieldTest(_NodeBase):
    """A comparison of a field, a derived input or a catalogue answer (`producer_question`, whose
    field is `q:<catalogue id>`) to values or bands. Its cases are one_of: exactly one applies."""

    kind: Literal["test", "producer_question"]
    field: str
    cases: list[Case]


class Choice(_NodeBase):
    """An underwriter choice: the options are listed with no default and each leads to a node."""

    kind: Literal["underwriter_choice"]
    choice: str  # section 9.7
    prompt: str
    show: list[str]  # the fields shown with the choice
    options: dict[str, str]  # option id -> the node it leads to


class AllOf(_NodeBase):
    """Every child is evaluated and the effects combine."""

    kind: Literal["all_of"]
    children: list[str]


class Ladder(_NodeBase):
    """Ordered fallbacks for negotiation after a quote (I05): the first rung is the effect, the
    endorsements of the later rungs are an advisory, and a later decline is the underwriter's
    decision in the negotiation, not an effect."""

    kind: Literal["ladder"]
    rungs: list[str]


class Outcome(_NodeBase):
    kind: Literal["outcome"]
    effects: list[Effect]


Node = Annotated[
    FieldTest | Choice | AllOf | Ladder | Outcome,
    Field(discriminator="kind"),
]


def _targets(node: Node) -> list[str]:
    """The nodes a node leads to."""
    match node:
        case FieldTest():
            return [case.then for case in node.cases]
        case Choice():
            return list(node.options.values())
        case AllOf():
            return node.children
        case Ladder():
            return node.rungs
        case Outcome():
            return []


@cache
def _interpretation_choices() -> dict[str, list[str]]:
    """The options of each underwriter choice of the interpretation table (9.7)."""
    return {
        choice["id"]: choice["options"]
        for row in read_yaml("interpretation.yaml")["rows"]
        for choice in row.get("choices", [])
    }


class Graph(StrictModel):
    id: str
    page: str
    applies_when: dict[str, JsonValue]
    root: str
    nodes: dict[str, Node]

    @model_validator(mode="after")
    def _bands_are_complete_and_disjoint(self) -> Self:
        """A test whose cases are numeric bands covers every number exactly once (9.6). A test on
        discrete values is not checked: the values a field can take are not known here."""
        for name, node in self.nodes.items():
            if isinstance(node, FieldTest) and node.kind == "test":
                bands = [_band(case.when) for case in node.cases]
                if all(band is not None for band in bands):
                    _check_bands(f"{self.id}.{name}", [band for band in bands if band is not None])
        return self

    @model_validator(mode="after")
    def _every_node_is_reachable_from_the_root(self) -> Self:
        reached: set[str] = set()
        pending = [self.root]
        while pending:
            name = pending.pop()
            if name not in self.nodes:
                raise ValueError(f"the {self.id} graph leads to {name}, which is not a node")
            if name not in reached:
                reached.add(name)
                pending += _targets(self.nodes[name])
        if unreached := set(self.nodes) - reached:
            raise ValueError(f"the {self.id} graph has nodes no path reaches: {sorted(unreached)}")
        return self

    @model_validator(mode="after")
    def _choices_are_those_of_the_interpretation_table(self) -> Self:
        for node in self.nodes.values():
            if isinstance(node, Choice) and _interpretation_choices().get(node.choice) != list(
                node.options
            ):
                raise ValueError(
                    f"the {self.id} graph's choice {node.choice} is not one of the table's, "
                    "with the table's options"
                )
        return self

    @model_validator(mode="after")
    def _an_outcome_holds_one_effect_of_a_type_for_each_rule(self) -> Self:
        for name, node in self.nodes.items():
            if isinstance(node, Outcome):
                keys = [(effect.type, effect.rule) for effect in node.effects]
                if len(keys) != len(set(keys)):
                    raise ValueError(
                        f"the {self.id}.{name} outcome holds two effects of one type for one rule"
                    )
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
    values = [facts.get(field) for field in spec["inputs"]]
    if not all(isinstance(value, int | float) for value in values):
        return None
    match spec["operation"]:
        case "ratio":
            numerator, divisor = values
            return None if divisor == 0 else numerator / divisor  # type: ignore[operator]
        case "years_before_reference":
            return REFERENCE_MORNING.year - values[0]  # type: ignore[operator]
        case operation:
            raise ValueError(f"the derived input operation {operation} is unknown")


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


@dataclass(frozen=True)
class Walk:
    """What a walk of a graph found. It is decided when nothing is awaited, undecided when `waits_on`
    names a field, a catalogue answer or a choice, and a decline on every branch when `every_branch`
    holds the traces of the alternatives."""

    effects: tuple[PlannedEffect, ...] = ()  # committed, a decline among them
    possible: tuple[PlannedEffect, ...] = ()  # beneath an unanswered choice, not committed
    waits_on: tuple[str, ...] = ()
    choices: tuple[OpenChoice, ...] = ()  # the choices the underwriter can answer now
    questions: tuple[str, ...] = ()  # the catalogue ids to ask the producer
    every_branch: tuple[RuleTrace, ...] = ()

    def __add__(self, other: "Walk") -> "Walk":
        return Walk(
            self.effects + other.effects,
            self.possible + other.possible,
            self.waits_on + other.waits_on,
            self.choices + other.choices,
            self.questions + other.questions,
            self.every_branch + other.every_branch,
        )

    def declined_branches(self, assumed: tuple[Assumption, ...]) -> list[TraceBranch]:
        """The branches of this walk that decline, each resting on the cases `assumed`."""
        branches = [
            TraceBranch(
                assumed=list(assumed), board_path=planned.trace.board_path, rule=planned.effect.rule
            )
            for planned in self.effects
            if isinstance(planned.effect, DeclineEffect)
        ]
        for trace in self.every_branch:
            branches += trace.alternatives
        return branches


@dataclass(frozen=True)
class _Walker:
    graph: Graph
    facts: Mapping[str, JsonValue]
    rulings: Rulings

    def walk(
        self,
        name: str,
        path: tuple[str, ...],
        assumed: tuple[Assumption, ...],
        answered: tuple[str, ...],
    ) -> Walk:
        """Walk from the node. `path` holds the board boxes visited above it, `assumed` the cases
        taken for unknown fields above it and `answered` the choices answered above it."""
        node = self.graph.nodes[name]
        path += tuple(node.board_path)
        match node:
            case Outcome() if not node.effects:
                return Walk()
            case Outcome():
                trace = RuleTrace(board_path=list(path), choice_ids=list(answered))
                return Walk(effects=tuple(self._committed(e, trace) for e in node.effects))
            case AllOf():
                return sum(
                    (self.walk(child, path, assumed, answered) for child in node.children), Walk()
                )
            case Ladder():
                first, *later = node.rungs
                fallbacks = tuple(
                    PlannedEffect(
                        effect=AdvisoryEffect(
                            type="advisory", rule=planned.effect.rule, text=planned.effect.text
                        ),
                        trace=planned.trace,
                        committed=True,
                    )
                    for rung in later
                    for planned in self.walk(rung, path, assumed, answered).effects
                    if isinstance(planned.effect, ExclusionOrEndorsementEffect)
                )
                return self.walk(first, path, assumed, answered) + Walk(effects=fallbacks)
            case Choice():
                return self._choice(node, path, assumed, answered)
            case FieldTest():
                return self._test(node, path, assumed, answered)

    def _committed(self, effect: Effect, trace: RuleTrace) -> PlannedEffect:
        """A suppressed decline is decided with an advisory naming the overridden rule (9.6)."""
        if isinstance(effect, DeclineEffect) and effect.rule in self.rulings.suppressed_rules:
            effect = AdvisoryEffect(
                type="advisory",
                rule=effect.rule,
                text=f"The decline under rule {effect.rule} was overridden by the underwriter.",
                internal=True,
            )
        return PlannedEffect(effect=effect, trace=trace, committed=True)

    def _choice(
        self,
        node: Choice,
        path: tuple[str, ...],
        assumed: tuple[Assumption, ...],
        answered: tuple[str, ...],
    ) -> Walk:
        option = self.rulings.choices.get(node.choice)
        if option in node.options:
            return self.walk(node.options[option], path, assumed, answered + (node.choice,))
        possible: list[PlannedEffect] = []
        for target in node.options.values():
            found = self.walk(target, path, assumed, answered + (node.choice,))
            possible += [p.model_copy(update={"committed": False}) for p in found.effects]
            possible += found.possible
        return Walk(
            possible=tuple(possible),
            waits_on=(node.choice,),
            choices=(
                OpenChoice(
                    choice_id=node.choice,
                    options=list(node.options),
                    prompt=node.prompt,
                    show=node.show,
                ),
            ),
        )

    def _test(
        self,
        node: FieldTest,
        path: tuple[str, ...],
        assumed: tuple[Assumption, ...],
        answered: tuple[str, ...],
    ) -> Walk:
        value = _value(node.field, self.facts)
        if value is not None:
            chosen = next(
                (
                    case
                    for case in node.cases
                    if all(_holds(clause, operand, value) for clause, operand in case.when.items())
                ),
                None,
            )
            if chosen is None:
                raise ValueError(
                    f"the {self.graph.id} graph has no case for {node.field} = {value}"
                )
            return self.walk(chosen.then, path, assumed, answered)
        # The field is unknown: the page declines when every case it could take declines.
        branches: list[TraceBranch] = []
        for case in node.cases:
            taken = assumed + (Assumption(field=node.field, when=case.when),)
            declined = self.walk(case.then, path, taken, answered).declined_branches(taken)
            if not declined:
                question = (
                    (node.field.removeprefix("q:"),) if node.kind == "producer_question" else ()
                )
                return Walk(waits_on=(node.field,), questions=question)
            branches += declined
        trace = RuleTrace(board_path=[], alternatives=branches, choice_ids=list(answered))
        return Walk(every_branch=(trace,))


def evaluate_graph(graph: Graph, facts: Mapping[str, JsonValue], rulings: Rulings) -> Walk:
    """Walk the graph from its root over the usable facts and the underwriter's rulings. Raises
    ValueError for a value no case of a test covers."""
    return _Walker(graph, facts, rulings).walk(graph.root, (), (), ())
