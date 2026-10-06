# ABOUTME: The per-skill eval cases (section 8): each skill's `cases/*.yaml` is a table of cases, each an input and the properties its output must hold; this module runs a skill on each and reports the failures.
# ABOUTME: Lead values come from the provider fixture's captured seed-42 leads; a case changes the values it names, and a null removes the value. A skill's pass is its share of passing cases against its manifest threshold.
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import JsonValue

import uwh.providers
import uwh.skills
from uwh.rules.graphs import Outcome, load_graphs
from uwh.rules.models import Rulings
from uwh.rules.registry import Registry
from uwh.skills.build_quote_packet import skill as build_quote_packet
from uwh.skills.evaluate_playbook import skill as evaluate_playbook
from uwh.skills.plan_asks import skill as plan_asks
from uwh.skills.render_message import skill as render_message
from uwh.skills.resolve_data import skill as resolve_data
from uwh.skills.triage_fields import skill as triage_fields

SKILLS_DIR = Path(uwh.skills.__file__).parent
WORLD = Path(uwh.providers.__file__).parent / "data" / "world-42.json"
# What the first pass adds to lead 008's captured fields: the derived siding class and the fetched replacement cost.
FIRST_PASS_ADDITIONS: dict[str, JsonValue] = {
    "siding_classification": "B",
    "replacement_cost": 928992,
}


@dataclass(frozen=True)
class Case:
    name: str
    input: dict[str, Any]
    expect: dict[str, Any]
    page: str | None  # the playbook page of the file, for the evaluate_playbook cases


@dataclass(frozen=True)
class SkillResult:
    """The share of a skill's cases that pass, and each failure's message."""

    cases_passed: int
    cases_total: int
    failures: list[str]

    def passed(self, threshold: float) -> bool:
        return self.cases_total > 0 and self.cases_passed / self.cases_total >= threshold


def lead_facts(
    lead_id: str, changes: Mapping[str, JsonValue], *, first_pass: bool = False
) -> dict[str, JsonValue]:
    """The captured fields of the lead that hold a value, with the first pass's additions when asked,
    and `changes` applied: a null removes the value."""
    fields = json.loads(WORLD.read_text(encoding="utf-8"))["leads"][lead_id]["fields"]
    merged = {k: v for k, v in fields.items() if v is not None}
    merged |= FIRST_PASS_ADDITIONS if first_pass else {}
    merged |= changes
    return {name: value for name, value in merged.items() if value is not None}


def load_cases(skill: str) -> list[Case]:
    """Every case of the skill's `cases/` folder, files in name order."""
    cases: list[Case] = []
    for path in sorted((SKILLS_DIR / skill / "cases").glob("*.yaml")):
        table = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases += [
            Case(c["name"], c["input"], c["expect"], table.get("page")) for c in table["cases"]
        ]
    return cases


def _raised(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """The properties `call` observes; a ValueError it raises is observed as `raises`."""
    try:
        return call()
    except ValueError as error:
        return {"raises": str(error)}


def _triage(case: Case, registry: Registry) -> dict[str, Any]:
    facts = lead_facts(case.input["lead"], case.input.get("facts", {}))
    output = triage_fields.run(
        triage_fields.TriageFieldsInput(
            registry=registry,
            facts=facts,
            conflicting_fields=case.input.get("conflicting_fields", []),
        )
    )
    observed: dict[str, Any] = {
        attribute: {name: getattr(t, attribute) for name, t in output.fields.items()}
        for attribute in ("value_status", "requirement", "resolution", "depends_on")
    }
    observed["asked"] = sorted(n for n, t in output.fields.items() if t.resolution == "ask")
    return observed


def _resolve(case: Case, registry: Registry) -> dict[str, Any]:
    def observe() -> dict[str, Any]:
        output = resolve_data.run(resolve_data.ResolveDataInput.model_validate(case.input))
        return {"facts": [[f.key, f.value, f.source] for f in output.facts]}

    return _raised(observe)


def _page_rules(page: str | None) -> set[str]:
    """The rule ids of the outcomes of the page's graph."""
    (graph,) = [g for g in load_graphs() if g.id == page]
    return {
        effect.rule
        for node in graph.nodes.values()
        if isinstance(node, Outcome)
        for effect in node.effects
    }


def _evaluate(case: Case, registry: Registry) -> dict[str, Any]:
    facts = lead_facts(case.input["lead"], case.input.get("facts", {}), first_pass=True)
    plan = evaluate_playbook.run(
        evaluate_playbook.EvaluatePlaybookInput(
            facts=facts, rulings=Rulings.model_validate(case.input.get("rulings", {}))
        )
    )
    rules = _page_rules(case.page)

    def listed(committed: bool) -> list[str]:
        return sorted(
            f"{p.effect.type} {p.effect.rule}"
            for p in plan.effects
            if p.effect.rule in rules and p.committed == committed
        )

    return {
        "committed": listed(True),
        "possible": listed(False),
        "choices": sorted(c.choice_id for c in plan.open_choices),
        "catalogue_questions": plan.catalogue_questions,
        "proposed_decline": plan.proposed_decline,
        "undecided": [w for u in plan.undecided if u.graph == case.page for w in u.waits_on],
        "decline_alternatives": [
            [b.rule, b.board_path] for t in plan.declines_on_every_branch for b in t.alternatives
        ],
        "paths": {p.effect.rule: p.trace.board_path for p in plan.effects},
        "deadlines": {
            p.effect.rule: p.effect.deadline for p in plan.effects if hasattr(p.effect, "deadline")
        },
        "not_evaluated": [n.ref for n in plan.not_evaluated],
    }


def _plan_asks(case: Case, registry: Registry) -> dict[str, Any]:
    facts = lead_facts(case.input["lead"], case.input.get("facts", {}))
    triage = triage_fields.run(
        triage_fields.TriageFieldsInput(registry=registry, facts=facts, conflicting_fields=[])
    ).fields
    planned = plan_asks.run(
        plan_asks.PlanAsksInput.model_validate(
            {
                "registry": registry,
                "triage": triage,
                "conflicts": case.input.get("conflicts", []),
                "catalogue_questions": case.input.get("catalogue_questions", []),
            }
        )
    )
    return {
        "ask_ids": [ask.ask_id for ask in planned.asks],
        "kinds": {ask.ask_id: ask.kind for ask in planned.asks},
        "message_class": planned.message_class,
    }


def _render(case: Case, registry: Registry) -> dict[str, Any]:
    output = render_message.run(
        render_message.RenderMessageInput.model_validate({**case.input, "registry": registry})
    )
    return {"subject": output.subject, "body": output.body, "ask_ids": output.ask_ids}


def _packet(case: Case, registry: Registry) -> dict[str, Any]:
    def observe() -> dict[str, Any]:
        output = build_quote_packet.run(
            build_quote_packet.BuildQuotePacketInput.model_validate(case.input)
        )
        return {"subject": output.subject, "body": output.body}

    return _raised(observe)


OBSERVERS: dict[str, Callable[[Case, Registry], dict[str, Any]]] = {
    "triage_fields": _triage,
    "resolve_data": _resolve,
    "evaluate_playbook": _evaluate,
    "plan_asks": _plan_asks,
    "render_message": _render,
    "build_quote_packet": _packet,
}


def mismatches(expected: Any, observed: Any, where: str = "") -> list[str]:
    """What differs between the expected properties and the observed ones. A mapping is compared
    on the keys it names; `includes` and `excludes` name members a list must and must not hold; a
    `raises` property is a pattern the error message must match."""
    if isinstance(expected, dict) and expected.keys() <= {"includes", "excludes"}:
        return [
            f"{where}: expected {'in' if key == 'includes' else 'not in'} {observed!r}: {item!r}"
            for key, items in expected.items()
            for item in items
            if (item in observed) != (key == "includes")
        ]
    if isinstance(expected, dict):
        found: list[str] = []
        for key, value in expected.items():
            path = f"{where}.{key}" if where else key
            if key not in observed:
                found.append(f"{path}: not observed")
            elif key == "raises":
                if not re.search(value, observed[key]):
                    found.append(f"{path}: {observed[key]!r} does not match {value!r}")
            else:
                found += mismatches(value, observed[key], path)
        return found
    if expected != observed:
        return [f"{where}: expected {expected!r}, observed {observed!r}"]
    return []


def run_skill_cases(skill: str, registry: Registry) -> SkillResult:
    """Run every case of the skill on `registry`."""
    failures: list[str] = []
    cases = load_cases(skill)
    failed = 0
    for case in cases:
        found = mismatches(case.expect, OBSERVERS[skill](case, registry))
        failed += bool(found)
        failures += [f"{skill} / {case.name}: {message}" for message in found]
    return SkillResult(len(cases) - failed, len(cases), failures)
