# ABOUTME: The per-skill eval cases (section 8): a skill's `cases/*.yaml` is a table of cases, each an input and the properties its output must hold; this module runs evaluate_playbook on its and reports the failures.
# ABOUTME: Lead values come from the provider fixture's captured seed-42 leads; a case changes the values it names, and a null removes the value. A skill's pass is its share of passing cases against its manifest threshold.
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import JsonValue

import uwh.chat
import uwh.providers
import uwh.skills
from evals.graders.chat import Expect
from uwh.rules.graphs import Outcome, load_graphs
from uwh.rules.models import Rulings
from uwh.skills.evaluate_playbook import skill as evaluate_playbook

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = Path(uwh.skills.__file__).parent
CHAT_DIR = Path(uwh.chat.__file__).parent
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


@dataclass(frozen=True)
class ReplyCase:
    """A fixture reply, the lead whose first request it answers, and the label of its expected reading."""

    lead: str
    body: str
    label: dict[str, Any]


@dataclass(frozen=True)
class ChatCase:
    """A lead of the seed-42 run and the messages put to the assistant about it, each with the
    outcome it must have."""

    name: str
    lead: str
    turns: list[tuple[str, Expect]]  # (message, expected outcome)
    after_replies: bool  # run after the first pass and the fixture replies, not at the run's start


def load_chat_cases() -> list[ChatCase]:
    """The cases of the chat package's `cases/` folder, files in name order."""
    cases: list[ChatCase] = []
    for path in sorted((CHAT_DIR / "cases").glob("*.yaml")):
        table = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases += [
            ChatCase(
                c["name"],
                c["lead"],
                [(t["message"], t["expect"]) for t in c["turns"]],
                c.get("after_replies", False),
            )
            for c in table["cases"]
        ]
    return cases


def load_reply_cases() -> list[ReplyCase]:
    """The cases of read_reply's `cases/` folder, files in name order. Each file names the lead, the
    reply fixture and the label by their paths from the repository root."""
    cases: list[ReplyCase] = []
    for path in sorted((SKILLS_DIR / "read_reply" / "cases").glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        cases.append(
            ReplyCase(
                case["lead"],
                (ROOT / case["fixture"]).read_text(encoding="utf-8"),
                yaml.safe_load((ROOT / case["label"]).read_text(encoding="utf-8")),
            )
        )
    return cases


def lead_facts(lead_id: str, changes: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """The captured fields of the lead that hold a value, with the first pass's additions and
    `changes` applied: a null removes the value."""
    fields = json.loads(WORLD.read_text(encoding="utf-8"))["leads"][lead_id]["fields"]
    merged = {k: v for k, v in fields.items() if v is not None}
    merged |= FIRST_PASS_ADDITIONS
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


def _page_rules(page: str | None) -> set[str]:
    """The rule ids of the outcomes of the page's graph."""
    (graph,) = [g for g in load_graphs() if g.id == page]
    return {
        effect.rule
        for node in graph.nodes.values()
        if isinstance(node, Outcome)
        for effect in node.effects
    }


def observe(case: Case) -> dict[str, Any]:
    facts = lead_facts(case.input["lead"], case.input.get("facts", {}))
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


def mismatches(expected: Any, observed: Any, where: str = "") -> list[str]:
    """What differs between the expected properties and the observed ones. A mapping is compared
    on the keys it names; `includes` and `excludes` name members a list must and must not hold."""
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
            else:
                found += mismatches(value, observed[key], path)
        return found
    if expected != observed:
        return [f"{where}: expected {expected!r}, observed {observed!r}"]
    return []


def run_skill_cases() -> SkillResult:
    """Run every case of evaluate_playbook; read_reply's cases are the reply suite's."""
    failures: list[str] = []
    cases = load_cases("evaluate_playbook")
    failed = 0
    for case in cases:
        found = mismatches(case.expect, observe(case))
        failed += bool(found)
        failures += [f"evaluate_playbook / {case.name}: {message}" for message in found]
    return SkillResult(len(cases) - failed, len(cases), failures)
