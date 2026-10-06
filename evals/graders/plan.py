# ABOUTME: The Rule trace grader (section 13.3): the stored plan of each lead against the labels' pages, board paths and the effects a producer sees.
# ABOUTME: It reads the plan stored for each lead and the playbook graphs.
from typing import Any

from evals.graders.evidence import Evidence, Expectations, Result, lead_ids, plan_of
from uwh.rules.graphs import Graph, load_graphs
from uwh.rules.models import DeclineEffect, PlannedEffect, RequirementEffect

# The effect type of the plan for each outcome a label names.
LABELLED_TYPES = {
    "decline": "decline",
    "requirement": "requirement",
    "surcharge": "surcharge",
    "exclusion": "exclusion_or_endorsement",
    "no_action": "no_action",
}
# The effect types a label's `effects` list, the ones a producer sees in the packet or the plan.
PRODUCER_EFFECT_TYPES = frozenset(
    {
        "decline",
        "requirement",
        "surcharge",
        "exclusion_or_endorsement",
        "coverage_adjustment",
        "obligation",
    }
)


def _page_number(graph: Graph) -> str:
    """The playbook page number of the graph, as board boxes name it: `05` for `05-roof-class`."""
    return graph.page.split("/")[2].split("-")[0]


def _page_state(
    effects: list[PlannedEffect], undecided: bool, label: dict[str, Any], page: str
) -> list[str]:
    """What differs between the system's result on one page and the label's."""
    # YAML reads an unquoted yes and no as booleans.
    applies = {True: "yes", False: "no"}.get(label["applies"], label["applies"])
    if applies != "yes":
        problems = [f"{page}: has effects, expected the page not to apply"] if effects else []
        if undecided != (applies == "unknown"):
            problems.append(f"{page}: expected applies {applies}")
        return problems
    outcome, trace = label["outcome"], label.get("trace")
    if outcome in ("undecided", "choice_open"):
        problems = [] if undecided else [f"{page}: not undecided, expected {outcome}"]
        if trace and not any(e.trace.board_path[: len(trace)] == trace for e in effects):
            problems.append(f"{page}: no outcome beneath {trace}")
        return problems
    wanted = LABELLED_TYPES[outcome]
    if not any(
        e.effect.type == wanted and e.committed and (not trace or e.trace.board_path == trace)
        for e in effects
    ):
        return [f"{page}: no committed {wanted} at {trace}"]
    return []


def _deadline(planned: PlannedEffect) -> str | None:
    deadline = getattr(planned.effect, "deadline", None)
    return None if deadline is None else str(deadline)


def rule_trace(ev: Evidence, expected: Expectations) -> Result:
    """Every committed decline and requirement has a rule trace, each labelled page reaches the
    labelled outcome by the labelled board path, and the effects a producer sees are the labelled ones."""
    graphs = {g.id: _page_number(g) for g in load_graphs()}
    failures: list[str] = []
    for lead_id in lead_ids(ev):
        plan = plan_of(ev, lead_id)
        failures += [
            f"{lead_id}: {p.effect.type} {p.effect.rule} has no trace"
            for p in (plan.effects if plan else [])
            if isinstance(p.effect, DeclineEffect | RequirementEffect)
            and not (p.trace.board_path or p.trace.alternatives)
        ]
    for lead_id, expectation in expected.items():
        plan = plan_of(ev, lead_id)
        if plan is None:
            failures.append(f"{lead_id}: has no plan")
            continue
        undecided = {u.graph for u in plan.undecided}
        for page, label in expectation.get("pages", {}).items():
            effects = [
                p
                for p in plan.effects
                if p.trace.board_path[:1] and p.trace.board_path[0].startswith(f"{graphs[page]}:")
            ]
            failures += [
                f"{lead_id}: {m}" for m in _page_state(effects, page in undecided, label, page)
            ]
        if "effects" in expectation:
            wanted = sorted(
                (e["type"], e["from"], e.get("deadline"))
                for e in expectation["effects"]
                if e["type"] in PRODUCER_EFFECT_TYPES
            )
            found = sorted(
                (p.effect.type, p.trace.board_path[-1], _deadline(p))
                for p in plan.effects
                if p.committed and p.effect.type in PRODUCER_EFFECT_TYPES and p.trace.board_path
            )
            failures += [f"{lead_id}: effect {e} is missing" for e in wanted if e not in found]
            failures += [f"{lead_id}: effect {e} is extra" for e in found if e not in wanted]
    return Result(failures)
