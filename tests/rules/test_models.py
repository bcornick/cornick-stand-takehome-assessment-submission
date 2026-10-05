# ABOUTME: Tests the rules-core domain models: triage enums, the eight effects, deadlines, node results, rule traces, the action plan and asks.
# ABOUTME: Every expected value list is written out here from section 9.2, 9.6, 9.7 and 10.2; every model forbids unknown fields and round-trips through JSON.
import hashlib
import json
from enum import StrEnum
from typing import Any, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from uwh.rules import models
from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    Ask,
    AskKind,
    Assumption,
    CoverageAdjustmentEffect,
    Deadline,
    Decided,
    DeclineEffect,
    DeclinesOnEveryBranch,
    Effect,
    ExclusionOrEndorsementEffect,
    FieldTriage,
    NodeResult,
    NoActionEffect,
    NotEvaluatedNote,
    ObligationEffect,
    OpenChoice,
    PlannedEffect,
    Requirement,
    RequirementEffect,
    Resolution,
    RuleTrace,
    SurchargeEffect,
    TraceBranch,
    Undecided,
    UndecidedPage,
    ValueStatus,
)
from uwh.runtime.hashing import plan_hash

NODE_RESULT = TypeAdapter(NodeResult)
EFFECT = TypeAdapter(Effect)


def values(enum: Any) -> list[str]:
    return [member.value for member in enum]


def test_triage_enums_hold_the_section_9_2_values() -> None:
    assert values(ValueStatus) == ["present", "missing", "conflicting", "unsupported"]
    assert values(Requirement) == [
        "required",
        "conditional_active",
        "conditional_inactive",
        "conditional_unknown",
        "bind_only",
        "optional",
    ]
    assert values(Resolution) == [
        "none",
        "derive",
        "fetch",
        "assume",
        "ask",
        "ask_follow_on",
        "defer",
        "verify",
        "not_required",
        "blocked",
    ]


def test_blocked_is_a_resolution() -> None:
    triage = FieldTriage(
        value_status="missing",
        requirement="conditional_active",
        resolution="blocked",
        depends_on=["protection_class"],
    )
    assert triage.resolution == Resolution.blocked
    assert triage.depends_on == ["protection_class"]


def test_triage_rejects_a_value_outside_the_enums() -> None:
    with pytest.raises(ValidationError):
        FieldTriage(
            value_status="missing", requirement="required", resolution="guess", depends_on=[]
        )


def test_deadlines_are_the_five_section_9_6_values() -> None:
    assert values(Deadline) == [
        "within_60_days",
        "first_term",
        "underwriting_period",
        "within_30_days_of_bind",
        "duration_of_non_occupancy",
    ]


class _NoMembers(StrEnum):
    """A StrEnum with no members and no helpers: its class dict is the machinery every StrEnum has."""


def test_deadlines_are_never_converted_to_one_another() -> None:
    # No member equals another, the enum adds no function, classmethod, staticmethod or property,
    # and no `_missing_` hook turns another spelling into a member.
    members = list(Deadline)
    assert all(a != b for a in members for b in members if a is not b)
    assert extra_callables(Deadline) == set()
    assert "_missing_" not in vars(Deadline)
    with pytest.raises(ValueError):
        Deadline("60_days")


def extra_callables(enum: type[StrEnum]) -> set[str]:
    machinery = set(vars(_NoMembers))
    members = {m.name for m in enum}
    kinds = (classmethod, staticmethod, property, type(lambda: None))
    return {
        name
        for name, value in vars(enum).items()
        if name not in machinery and name not in members and isinstance(value, kinds)
    }


def test_a_helper_on_a_deadline_enum_is_seen() -> None:
    class WithHelper(StrEnum):
        first_term = "first_term"

        def to_days(self) -> int:
            return 365

    class WithHook(StrEnum):
        first_term = "first_term"

        @classmethod
        def _missing_(cls, value: object) -> "WithHook":
            return cls.first_term

    assert extra_callables(WithHelper) == {"to_days"}
    assert "_missing_" in vars(WithHook)


EFFECT_SAMPLES: dict[str, dict[str, Any]] = {
    "decline": {"type": "decline", "rule": "PP-1"},
    "requirement": {
        "type": "requirement",
        "rule": "RF-2",
        "text": "Replace the roof",
        "deadline": "within_60_days",
    },
    "surcharge": {"type": "surcharge", "rule": "PP-3", "percent": 15},
    "exclusion_or_endorsement": {
        "type": "exclusion_or_endorsement",
        "rule": "PR-1",
        "text": "Exclude liability",
    },
    "coverage_adjustment": {
        "type": "coverage_adjustment",
        "rule": "RC-1",
        "field": "coverage_a",
        "proposed_value": 500000,
    },
    "advisory": {"type": "advisory", "rule": "PR-2", "text": "Later rungs: ..."},
    "obligation": {
        "type": "obligation",
        "rule": "TR-1",
        "text": "Return the trust questionnaire",
        "owner": "producer",
        "trigger": "post_bind",
    },
    "no_action": {"type": "no_action", "rule": "PL-4"},
}

EFFECT_CLASSES = {
    "decline": DeclineEffect,
    "requirement": RequirementEffect,
    "surcharge": SurchargeEffect,
    "exclusion_or_endorsement": ExclusionOrEndorsementEffect,
    "coverage_adjustment": CoverageAdjustmentEffect,
    "advisory": AdvisoryEffect,
    "obligation": ObligationEffect,
    "no_action": NoActionEffect,
}


def effect_type_names() -> list[str]:
    union = get_args(Effect)[0]
    return [get_args(member.model_fields["type"].annotation)[0] for member in get_args(union)]


def test_effect_union_holds_the_eight_effects() -> None:
    assert effect_type_names() == [
        "decline",
        "requirement",
        "surcharge",
        "exclusion_or_endorsement",
        "coverage_adjustment",
        "advisory",
        "obligation",
        "no_action",
    ]
    assert list(EFFECT_SAMPLES) == effect_type_names()


@pytest.mark.parametrize("name", list(EFFECT_SAMPLES))
def test_effect_union_picks_the_class_from_type(name: str) -> None:
    effect = EFFECT.validate_python(EFFECT_SAMPLES[name])
    assert type(effect) is EFFECT_CLASSES[name]
    assert EFFECT.dump_python(effect, mode="json") == EFFECT_SAMPLES[name]


def test_effect_union_rejects_an_unknown_type() -> None:
    with pytest.raises(ValidationError):
        EFFECT.validate_python({"type": "refund", "rule": "X-1"})


def test_the_a6_effect_spellings_validate() -> None:
    assert EFFECT.validate_python({"type": "decline", "rule": "PP-1"}) == DeclineEffect(
        type="decline", rule="PP-1"
    )
    surcharge = EFFECT.validate_python({"type": "surcharge", "percent": 15, "rule": "PP-3"})
    assert isinstance(surcharge, SurchargeEffect) and surcharge.percent == 15


def test_a_requirement_deadline_must_be_a_deadline() -> None:
    with pytest.raises(ValidationError):
        EFFECT.validate_python(
            {"type": "requirement", "rule": "RF-2", "text": "x", "deadline": "in two weeks"}
        )


def test_a_coverage_adjustment_has_no_field_for_the_submitted_value() -> None:
    assert "submitted_value" not in CoverageAdjustmentEffect.model_fields


TRACE = RuleTrace(board_path=["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"])

# Post & Pier with a deck above 12 feet: whatever `post_pier_supports_living_area` is, the lead declines.
PP_ALTERNATIVES = RuleTrace(
    board_path=[],
    alternatives=[
        TraceBranch(
            assumed=[
                Assumption(field="post_pier_supports_living_area", when={"equals": True}),
            ],
            board_path=["07:ROOT", "07:LIVING", "07:D1"],
            rule="PP-1",
        ),
        TraceBranch(
            assumed=[
                Assumption(field="post_pier_supports_living_area", when={"equals": False}),
                Assumption(field="year_built", when={"lt": 2000}),
            ],
            board_path=["07:ROOT", "07:DECK", "07:PRE2000", "07:D1"],
            rule="PP-2",
        ),
        TraceBranch(
            assumed=[
                Assumption(field="post_pier_supports_living_area", when={"equals": False}),
                Assumption(field="year_built", when={"gte": 2000}),
            ],
            board_path=["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"],
            rule="PP-5",
        ),
    ],
)


def test_a_trace_is_the_concatenated_board_path_and_has_no_alternatives_by_default() -> None:
    assert TRACE.board_path == ["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"]
    assert TRACE.alternatives == []
    assert TRACE.choice_ids == []


def test_a_trace_is_a_path_or_a_set_of_alternatives_never_both_and_never_neither() -> None:
    with pytest.raises(ValidationError):
        RuleTrace(board_path=["07:ROOT"], alternatives=PP_ALTERNATIVES.alternatives)
    with pytest.raises(ValidationError):
        RuleTrace(board_path=[])


def test_a_trace_names_the_underwriter_choices_it_followed() -> None:
    trace = RuleTrace(board_path=["04:ROOT", "04:LEGACY", "04:D1"], choice_ids=["I13.fire_fail"])
    assert trace.choice_ids == ["I13.fire_fail"]
    alternatives = PP_ALTERNATIVES.model_copy(update={"choice_ids": ["I44.road_access"]})
    assert alternatives.choice_ids == ["I44.road_access"]


def test_a_decline_on_every_branch_carries_one_trace_per_branch_with_its_assumptions() -> None:
    result = NODE_RESULT.validate_python(
        {"result": "declines_on_every_branch", "trace": PP_ALTERNATIVES.model_dump()}
    )
    assert isinstance(result, DeclinesOnEveryBranch)
    alternatives = result.trace.alternatives
    assert [a.rule for a in alternatives] == ["PP-1", "PP-2", "PP-5"]
    assert [a.board_path[-1] for a in alternatives] == ["07:D1", "07:D1", "07:D2"]


def test_one_alternative_rests_on_several_unknown_inputs_ordered_root_to_leaf() -> None:
    branch = PP_ALTERNATIVES.alternatives[2]
    assert [(a.field, a.when) for a in branch.assumed] == [
        ("post_pier_supports_living_area", {"equals": False}),
        ("year_built", {"gte": 2000}),
    ]
    band = Assumption(field="deck_height_ft", when={"gt": 8, "lte": 12})
    assert band.when == {"gt": 8, "lte": 12}


def test_a_decline_on_every_branch_without_alternatives_is_refused() -> None:
    with pytest.raises(ValidationError):
        DeclinesOnEveryBranch(result="declines_on_every_branch", trace=TRACE)


def test_a_branch_must_state_at_least_one_assumption() -> None:
    with pytest.raises(ValidationError):
        TraceBranch(assumed=[], board_path=["07:ROOT"], rule="PP-1")
    with pytest.raises(ValidationError):
        TraceBranch.model_validate({"board_path": ["07:ROOT"], "rule": "PP-1"})


NODE_RESULT_SAMPLES: dict[str, dict[str, Any]] = {
    "decided": {"result": "decided", "effects": [EFFECT_SAMPLES["surcharge"]]},
    "undecided": {
        "result": "undecided",
        "waits_on": ["I13.fire_fail"],
        "effects": [],
        "possible_effects": [EFFECT_SAMPLES["decline"]],
    },
    "declines_on_every_branch": {
        "result": "declines_on_every_branch",
        "trace": PP_ALTERNATIVES.model_dump(),
    },
}


@pytest.mark.parametrize(
    ("name", "cls"),
    [
        ("decided", Decided),
        ("undecided", Undecided),
        ("declines_on_every_branch", DeclinesOnEveryBranch),
    ],
)
def test_node_results_are_the_three_section_9_6_results(name: str, cls: type[BaseModel]) -> None:
    result = NODE_RESULT.validate_python(NODE_RESULT_SAMPLES[name])
    assert type(result) is cls


def test_an_unknown_node_result_is_refused() -> None:
    with pytest.raises(ValidationError):
        NODE_RESULT.validate_python({"result": "maybe"})


def test_an_undecided_result_names_what_it_waits_on() -> None:
    with pytest.raises(ValidationError):
        Undecided(result="undecided", waits_on=[])


def test_ask_kinds_are_the_five_section_10_2_kinds() -> None:
    assert values(AskKind) == [
        "field_request",
        "follow_on_question",
        "catalogue_question",
        "confirmation",
        "document_request",
    ]


ASK = Ask(
    ask_id="pool_security",
    kind="follow_on_question",
    fields=["pool_security"],
    reason="conditional_unknown",
    wording="If there is a pool: is it fenced?",
)


def test_an_ask_carries_its_ids_reason_and_stored_wording() -> None:
    assert ASK.fields == ["pool_security"]
    assert ASK.reason == "conditional_unknown"
    assert ASK.wording == "If there is a pool: is it fenced?"
    with pytest.raises(ValidationError):
        Ask(ask_id="x", kind="reminder", fields=["x"], reason="r", wording="w")  # type: ignore[arg-type]


FIRE_FAIL_TRACE = RuleTrace(
    board_path=["04:ROOT", "04:LEGACY", "04:D1"], choice_ids=["I13.fire_fail"]
)
ROOF_TRACE = RuleTrace(board_path=["05:ROOT", "05:CLASSB", "05:R1"])
PROFILE_TRACE = RuleTrace(board_path=["02:ROOT", "02:SPOT", "02:SPOT1"])

# One coherent plan: no decline is committed, so the plan is a proposed decline only through
# Post & Pier's decline on every branch; the possible decline sits beneath the open fire choice.
PLAN = ActionPlan(
    effects=[
        PlannedEffect(
            effect=DeclineEffect(type="decline", rule="FS-4"),
            trace=FIRE_FAIL_TRACE,
            committed=False,
        ),
        PlannedEffect(
            effect=ExclusionOrEndorsementEffect(
                type="exclusion_or_endorsement", rule="PR-1", text="Exclude liability"
            ),
            trace=PROFILE_TRACE,
            committed=True,
        ),
        PlannedEffect(
            effect=RequirementEffect(
                type="requirement", rule="RF-2", text="Replace the roof", deadline="first_term"
            ),
            trace=ROOF_TRACE,
            committed=True,
        ),
    ],
    declines_on_every_branch=[PP_ALTERNATIVES],
    proposed_decline=True,
    undecided=[UndecidedPage(graph="fire_simulation", waits_on=["p_f"])],
    open_choices=[
        OpenChoice(
            choice_id="I13.fire_fail",
            options=["decline", "legacy_underwriting"],
            prompt="Decline or legacy underwriting after a fire simulation fail?",
            show=["p_f"],
        )
    ],
    catalogue_questions=["willing_to_mitigate"],
    not_evaluated=[
        NotEvaluatedNote(ref="I46", text="Animals and other attractive nuisances are not evaluated")
    ],
)

DECLINE_LEAD_PLAN = ActionPlan(
    effects=[
        PlannedEffect(
            effect=RequirementEffect(
                type="requirement", rule="RF-2", text="Replace the roof", deadline="first_term"
            ),
            trace=ROOF_TRACE,
            committed=True,
        )
    ],
    proposed_decline=True,
    underwriter_decline="Reputational damage to Stand (I04)",
)


def test_the_action_plan_holds_committed_and_possible_effects() -> None:
    assert [(p.effect.rule, p.committed) for p in PLAN.effects] == [
        ("FS-4", False),
        ("PR-1", True),
        ("RF-2", True),
    ]


def test_the_action_plan_holds_decline_status_undecided_pages_choices_questions_and_notes() -> None:
    assert PLAN.proposed_decline is True
    assert PLAN.declines_on_every_branch[0].alternatives[2].rule == "PP-5"
    assert PLAN.undecided[0].waits_on == ["p_f"]
    assert PLAN.open_choices[0].options == ["decline", "legacy_underwriting"]
    assert PLAN.open_choices[0].show == ["p_f"]
    assert PLAN.catalogue_questions == ["willing_to_mitigate"]
    assert PLAN.not_evaluated[0].ref == "I46"
    assert PLAN.underwriter_decline is None


def test_an_empty_action_plan_is_not_a_proposed_decline() -> None:
    assert ActionPlan().proposed_decline is False


def committed_decline() -> PlannedEffect:
    return PlannedEffect(
        effect=DeclineEffect(type="decline", rule="PP-1"),
        trace=RuleTrace(board_path=["07:ROOT", "07:LIVING", "07:D1"]),
        committed=True,
    )


def possible_decline() -> PlannedEffect:
    return committed_decline().model_copy(update={"committed": False})


def test_a_proposed_decline_stands_on_a_committed_decline_effect() -> None:
    assert ActionPlan(effects=[committed_decline()], proposed_decline=True).proposed_decline
    with pytest.raises(ValidationError):
        ActionPlan(effects=[committed_decline()], proposed_decline=False)


def test_a_proposed_decline_stands_on_a_decline_on_every_branch() -> None:
    assert ActionPlan(declines_on_every_branch=[PP_ALTERNATIVES], proposed_decline=True)
    with pytest.raises(ValidationError):
        ActionPlan(declines_on_every_branch=[PP_ALTERNATIVES], proposed_decline=False)


def test_a_proposed_decline_stands_on_the_underwriters_own_decline() -> None:
    plan = ActionPlan(proposed_decline=True, underwriter_decline="Reputational damage")
    assert plan.underwriter_decline == "Reputational damage"
    with pytest.raises(ValidationError):
        ActionPlan(proposed_decline=False, underwriter_decline="Reputational damage")


def test_a_plan_with_no_decline_is_refused_as_a_proposed_decline() -> None:
    with pytest.raises(ValidationError):
        ActionPlan(proposed_decline=True)
    # A decline beneath an unanswered choice is possible, not committed: no proposed decline.
    with pytest.raises(ValidationError):
        ActionPlan(effects=[possible_decline()], proposed_decline=True)
    assert not ActionPlan(effects=[possible_decline()]).proposed_decline


def test_a_decline_on_every_branch_in_a_plan_carries_its_alternatives() -> None:
    with pytest.raises(ValidationError):
        ActionPlan(declines_on_every_branch=[TRACE], proposed_decline=True)


def test_the_plan_dump_is_the_json_the_plan_hash_is_taken_over() -> None:
    dump = DECLINE_LEAD_PLAN.model_dump(mode="json")
    assert dump["proposed_decline"] is True
    assert dump["underwriter_decline"] == "Reputational damage to Stand (I04)"
    assert plan_hash(dump) == plan_hash(DECLINE_LEAD_PLAN.model_dump(mode="json"))


def surcharge(rule: str, committed: bool = True) -> PlannedEffect:
    return PlannedEffect(
        effect=SurchargeEffect(type="surcharge", rule=rule, percent=15),
        trace=ROOF_TRACE,
        committed=committed,
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
                surcharge("RF-2"),
                surcharge("PR-1"),
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
            [NotEvaluatedNote(ref="I46", text="a"), NotEvaluatedNote(ref="04:ACCESS", text="b")]
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
    assert [(p.effect.rule, p.committed) for p in plan.effects] == [
        ("PR-1", True),
        ("RF-1", True),
        ("RF-2", False),
        ("RF-2", True),
    ]
    assert [t.alternatives[0].rule for t in plan.declines_on_every_branch] == ["PC-2", "PP-1"]
    assert [u.graph for u in plan.undecided] == ["fire_simulation", "roof"]
    assert plan.undecided[1].waits_on == ["p_f", "roof_material"]
    assert [c.choice_id for c in plan.open_choices] == ["I13.fire_fail", "I16.slope"]
    assert plan.catalogue_questions == ["kt_extent", "willing_to_mitigate"]
    assert [n.ref for n in plan.not_evaluated] == ["04:ACCESS", "I46"]


def test_an_open_choice_keeps_the_option_and_show_order_it_was_given() -> None:
    choice = OpenChoice(choice_id="c", options=["z", "a", "m"], prompt="p", show=["y", "b"])
    plan = ActionPlan(open_choices=[choice])
    assert plan.open_choices[0].options == ["z", "a", "m"]
    assert plan.open_choices[0].show == ["y", "b"]


def test_a_surcharge_percent_is_a_whole_number() -> None:
    assert SurchargeEffect(type="surcharge", rule="PP-3", percent=15).percent == 15
    for percent in (12.5, 15.0):
        with pytest.raises(ValidationError):
            SurchargeEffect(type="surcharge", rule="PP-3", percent=percent)  # type: ignore[arg-type]


def test_identical_plans_dump_identically() -> None:
    again = ActionPlan.model_validate(PLAN.model_dump(mode="json"))
    assert json.dumps(again.model_dump(mode="json"), sort_keys=True) == json.dumps(
        PLAN.model_dump(mode="json"), sort_keys=True
    )


def test_no_model_carries_a_confidence_or_a_timestamp() -> None:
    for cls in classes():
        names = set(cls.model_fields)
        assert not {
            n
            for n in names
            if "confidence" in n or n.endswith("_at") or n.endswith("_ts") or n == "id"
        }, cls


def classes() -> list[type[BaseModel]]:
    return [
        c
        for c in vars(models).values()
        if isinstance(c, type) and issubclass(c, BaseModel) and c.__module__ == models.__name__
    ]


def samples() -> list[BaseModel]:
    return [
        FieldTriage(
            value_status="present", requirement="required", resolution="none", depends_on=[]
        ),
        *[EFFECT.validate_python(e) for e in EFFECT_SAMPLES.values()],
        TRACE,
        PP_ALTERNATIVES.alternatives[0],
        PP_ALTERNATIVES.alternatives[0].assumed[0],
        *[NODE_RESULT.validate_python(r) for r in NODE_RESULT_SAMPLES.values()],
        ASK,
        PLAN.effects[0],
        PLAN.undecided[0],
        PLAN.open_choices[0],
        PLAN.not_evaluated[0],
        PLAN,
        DECLINE_LEAD_PLAN,
    ]


def test_every_model_has_a_sample_so_none_escapes_the_checks_below() -> None:
    sampled = {type(s) for s in samples()}
    unsampled = {c for c in classes() if c not in sampled and c is not models.StrictModel}
    assert unsampled == set()


def test_every_model_round_trips_through_json() -> None:
    for sample in samples():
        text = sample.model_dump_json()
        assert type(sample).model_validate_json(text) == sample


def test_every_model_forbids_unknown_fields() -> None:
    for sample in samples():
        with pytest.raises(ValidationError):
            type(sample).model_validate({**sample.model_dump(mode="json"), "surprise": 1})


def test_every_model_config_forbids_extra() -> None:
    for cls in classes():
        assert cls.model_config.get("extra") == "forbid", cls
