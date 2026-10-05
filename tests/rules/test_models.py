# ABOUTME: Tests the action plan's computed behaviour: one effect per effect type and rule id, every list in a stable order, and a hash that does not depend on build order.
# ABOUTME: A decline beneath an unanswered choice is possible, not committed, so it does not propose a decline.
import hashlib
import json

import pytest
from pydantic import ValidationError

from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    Assumption,
    DeclineEffect,
    NotEvaluatedNote,
    OpenChoice,
    PlannedEffect,
    RuleTrace,
    SurchargeEffect,
    TraceBranch,
    UndecidedPage,
)
from uwh.runtime.hashing import plan_hash

ROOF_TRACE = RuleTrace(board_path=["05:ROOT", "05:CLASSB", "05:R1"])


def committed_decline() -> PlannedEffect:
    return PlannedEffect(
        effect=DeclineEffect(type="decline", rule="PP-1"),
        trace=RuleTrace(board_path=["07:ROOT", "07:LIVING", "07:D1"]),
        committed=True,
    )


def possible_decline() -> PlannedEffect:
    return committed_decline().model_copy(update={"committed": False})


def test_a_possible_decline_does_not_propose_a_decline() -> None:
    # A decline beneath an unanswered choice is possible, not committed: no proposed decline.
    assert not ActionPlan(effects=[possible_decline()]).proposed_decline


def surcharge(rule: str, committed: bool = True) -> PlannedEffect:
    return PlannedEffect(
        effect=SurchargeEffect(type="surcharge", rule=rule, percent=15),
        trace=ROOF_TRACE,
        committed=committed,
    )


def advisory(rule: str) -> PlannedEffect:
    return PlannedEffect(
        effect=AdvisoryEffect(type="advisory", rule=rule, text="Later rungs"),
        trace=ROOF_TRACE,
        committed=True,
    )


def branch(rule: str, path: list[str]) -> RuleTrace:
    return RuleTrace(
        board_path=[],
        alternatives=[
            TraceBranch(
                assumed=[Assumption(field="year_built", when={"lt": 2000})],
                board_path=path,
                rule=rule,
            )
        ],
    )


def plan_in_order(forward: bool) -> ActionPlan:
    def order[T](items: list[T]) -> list[T]:
        return items if forward else list(reversed(items))

    return ActionPlan(
        effects=order(
            [
                surcharge("RF-1"),
                surcharge("RF-2", committed=False),
                surcharge("RF-3"),
                surcharge("PR-1"),
                advisory("RF-1"),
            ]
        ),
        declines_on_every_branch=order(
            [branch("PP-1", ["07:A", "07:D1"]), branch("PC-2", ["09:A", "09:D1"])]
        ),
        proposed_decline=True,
        undecided=order(
            [
                UndecidedPage(graph="roof", waits_on=order(["roof_material", "p_f", "p_f"])),
                UndecidedPage(graph="fire_simulation", waits_on=["p_f"]),
            ]
        ),
        open_choices=order(
            [
                OpenChoice(choice_id="I16.slope", options=["steep", "gentle"], prompt="p", show=[]),
                OpenChoice(
                    choice_id="I13.fire_fail",
                    options=["decline", "legacy_underwriting"],
                    prompt="p",
                    show=["slope_angle_deg", "p_f"],
                ),
            ]
        ),
        catalogue_questions=order(["willing_to_mitigate", "kt_extent", "kt_extent"]),
        not_evaluated=order(
            [
                NotEvaluatedNote(ref="I46", text="a", producer_text="a"),
                NotEvaluatedNote(ref="04:ACCESS", text="b", producer_text="b"),
            ]
        ),
    )


def test_plans_built_in_different_orders_hash_equally_over_a_pinned_input() -> None:
    forward_dump = plan_in_order(True).model_dump(mode="json")
    backward_dump = plan_in_order(False).model_dump(mode="json")
    assert plan_hash(forward_dump) == plan_hash(backward_dump)
    # The hash input is pinned apart from `plan_hash`: SHA-256 of the sorted-key, compact,
    # non-ASCII-preserving JSON of the dump.
    text = json.dumps(forward_dump, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert plan_hash(forward_dump) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_a_plan_puts_every_list_in_a_stable_order() -> None:
    plan = plan_in_order(False)
    assert [(p.effect.rule, p.effect.type) for p in plan.effects] == [
        ("PR-1", "surcharge"),
        ("RF-1", "advisory"),
        ("RF-1", "surcharge"),
        ("RF-2", "surcharge"),
        ("RF-3", "surcharge"),
    ]
    assert [t.alternatives[0].rule for t in plan.declines_on_every_branch] == ["PC-2", "PP-1"]
    assert [u.graph for u in plan.undecided] == ["fire_simulation", "roof"]
    assert plan.undecided[1].waits_on == ["p_f", "roof_material"]
    assert [c.choice_id for c in plan.open_choices] == ["I13.fire_fail", "I16.slope"]
    assert plan.catalogue_questions == ["kt_extent", "willing_to_mitigate"]
    assert [n.ref for n in plan.not_evaluated] == ["04:ACCESS", "I46"]


def test_a_plan_holds_one_effect_for_each_effect_type_and_rule_id() -> None:
    # 9.6: effects are deduplicated by effect type and rule id.
    with pytest.raises(ValidationError, match="surcharge.*RF-1"):
        ActionPlan(effects=[surcharge("RF-1"), surcharge("RF-1")])
    with pytest.raises(ValidationError, match="surcharge.*RF-1"):
        ActionPlan(effects=[surcharge("RF-1"), surcharge("RF-1", committed=False)])


def test_a_plan_accepts_one_rule_id_under_two_effect_types() -> None:
    plan = ActionPlan(effects=[surcharge("RF-1"), advisory("RF-1")])
    assert {(p.effect.type, p.effect.rule) for p in plan.effects} == {
        ("surcharge", "RF-1"),
        ("advisory", "RF-1"),
    }
