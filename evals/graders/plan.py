# ABOUTME: The graders of what the system decided for each lead: Rule trace, Field resolution and Escalation (section 13.3), each against the labels' pages, asks and underwriter items.
# ABOUTME: Rule trace reads the stored plan, Field resolution the latest triage, and Escalation the open blockers and drafts of each lead.
from typing import Any

from evals.graders.evidence import Evidence, Expectations, Result, lead_ids, plan_of
from uwh.rules.graphs import Graph, load_graphs
from uwh.rules.models import DeclineEffect, PlannedEffect, RequirementEffect
from uwh.runtime.event_types import TriageCompleted
from uwh.runtime.events import read_events
from uwh.runtime.waits import open_blockers

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
# The most leads that may need the underwriter on the first pass of seed 42 (section 13.3).
ESCALATION_TARGET = 4


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


def _latest_triage(ev: Evidence, lead_id: str) -> dict[str, Any]:
    """The fields of the lead's latest triage; none before the lead has been triaged."""
    triaged = [
        e.payload
        for e in read_events(ev.db, lead_id=lead_id)
        if isinstance(e.payload, TriageCompleted)
    ]
    return triaged[-1].fields if triaged else {}


def _rates(expected: set[Any], found: set[Any]) -> tuple[float, float]:
    """Precision and recall of `found` against `expected`; both 1.0 when both are empty."""
    hits = len(expected & found)
    return (hits / len(found) if found else 1.0, hits / len(expected) if expected else 1.0)


def field_resolution(ev: Evidence, expected: Expectations) -> Result:
    """Precision and recall of the fields the system's triage asks for against the labelled asks
    (a decline's suppressed asks included), over the leads the labels describe. Each must be 1.0."""
    wanted: set[tuple[str, str]] = set()
    found: set[tuple[str, str]] = set()
    for lead_id, expectation in expected.items():
        request = expectation["request"] or expectation.get("suppressed") or {}
        wanted |= {(lead_id, name) for name in request.get("asks", [])}
        found |= {
            (lead_id, name)
            for name, t in _latest_triage(ev, lead_id).items()
            if t["resolution"] in ("ask", "ask_follow_on")
        }
    precision, recall = _rates(wanted, found)
    failures = [
        f"{lead} {name} is asked by the triage and not labelled"
        for lead, name in sorted(found - wanted)
    ]
    failures += [
        f"{lead} {name} is labelled asked and the triage does not"
        for lead, name in sorted(wanted - found)
    ]
    return Result(failures, {"precision": precision, "recall": recall})


def _items(ev: Evidence, lead_id: str) -> set[str]:
    """What the lead waits on the underwriter for: each open choice, each draft awaiting approval by
    its kind, and each other review by its cause or kind."""
    items: set[str] = set()
    for blocker in open_blockers(ev.db, lead_id):
        detail = blocker.detail
        if blocker.kind == "underwriter_question":
            items |= set(detail.choice_ids)
        elif blocker.kind == "delivery_unknown":
            items.add("delivery_unknown")
        elif blocker.kind == "underwriter_review" and detail.item_kind == "draft":
            (kind,) = ev.db.execute(
                "SELECT kind FROM intents WHERE id = ?", (detail.intent_id,)
            ).fetchone()
            items.add(kind)
        elif blocker.kind == "underwriter_review":
            items.add(detail.cause or str(detail.item_kind))
    return items


def escalation(ev: Evidence, expected: Expectations) -> Result:
    """Precision and recall of the items waiting on the underwriter against the labelled ones, each
    1.0, and the share of leads that need the underwriter, at most the target of 4 of 10 in seed 42."""
    wanted = {(lead, item) for lead, e in expected.items() for item in e["underwriter_items"]}
    found = {(lead, item) for lead in expected for item in _items(ev, lead)}
    precision, recall = _rates(wanted, found)
    escalated = sorted({lead for lead, _ in found})
    failures = [f"{lead}: waits on {item}, not labelled" for lead, item in sorted(found - wanted)]
    failures += [f"{lead}: labelled {item} is not waiting" for lead, item in sorted(wanted - found)]
    if len(escalated) > ESCALATION_TARGET:
        failures.append(
            f"{len(escalated)} leads need the underwriter, the target is {ESCALATION_TARGET}"
        )
    return Result(
        failures,
        {
            "precision": precision,
            "recall": recall,
            "escalated_leads": [*escalated],
            "escalation_rate": f"{len(escalated)} of {len(expected)}",
        },
    )
