# ABOUTME: Tests the rules-core domain models: triage enums, the eight effects, deadlines, node results, rule traces, the action plan and asks.
# ABOUTME: Every expected value list is written out here from section 9.2, 9.6, 9.7 and 10.2; every model forbids unknown fields and round-trips through JSON.
import json
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from uwh.rules import models
from uwh.rules.models import (
    ActionPlan,
    AdvisoryEffect,
    Ask,
    AskKind,
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


def test_deadlines_are_never_converted_to_one_another() -> None:
    # No member equals another, no member is built from another's text, and the enum adds no helper.
    members = list(Deadline)
    assert all(a != b for a in members for b in members if a is not b)
    helpers = (
        {n for n in dir(Deadline) if not n.startswith("_")}
        - {m.name for m in Deadline}
        - set(dir(str))
    )
    assert helpers == set()
    with pytest.raises(ValueError):
        Deadline("60_days")


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


def test_effect_union_holds_the_eight_effects() -> None:
    assert list(EFFECT_SAMPLES) == [
        "decline",
        "requirement",
        "surcharge",
        "exclusion_or_endorsement",
        "coverage_adjustment",
        "advisory",
        "obligation",
        "no_action",
    ]


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

PP_ALTERNATIVES = RuleTrace(
    board_path=["07:ROOT"],
    alternatives=[
        TraceBranch(
            field="post_pier_supports_living_area",
            assumed_value=True,
            board_path=["07:ROOT", "07:LIVING", "07:D1"],
            rule="PP-1",
        ),
        TraceBranch(
            field="post_pier_supports_living_area",
            assumed_value=False,
            board_path=["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"],
            rule="PP-5",
        ),
    ],
)


def test_a_trace_is_the_concatenated_board_path_and_has_no_alternatives_by_default() -> None:
    assert TRACE.board_path == ["07:ROOT", "07:DECK", "07:POST2000", "07:HIGH", "07:D2"]
    assert TRACE.alternatives == []


def test_a_decline_on_every_branch_carries_one_trace_per_branch_with_its_assumed_value() -> None:
    result = NODE_RESULT.validate_python(
        {"result": "declines_on_every_branch", "trace": PP_ALTERNATIVES.model_dump()}
    )
    assert isinstance(result, DeclinesOnEveryBranch)
    alternatives = result.trace.alternatives
    assert [(a.assumed_value, a.rule) for a in alternatives] == [(True, "PP-1"), (False, "PP-5")]
    assert [a.board_path[-1] for a in alternatives] == ["07:D1", "07:D2"]


def test_a_decline_on_every_branch_without_alternatives_is_refused() -> None:
    with pytest.raises(ValidationError):
        DeclinesOnEveryBranch(result="declines_on_every_branch", trace=TRACE)


def test_a_branch_must_state_its_assumed_value() -> None:
    with pytest.raises(ValidationError):
        TraceBranch.model_validate({"field": "f", "board_path": ["07:ROOT"], "rule": "PP-1"})


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


PLAN = ActionPlan(
    effects=[
        PlannedEffect(
            effect=DeclineEffect(type="decline", rule="PP-1"), trace=TRACE, committed=False
        ),
        PlannedEffect(
            effect=SurchargeEffect(type="surcharge", rule="PP-3", percent=15),
            trace=TRACE,
            committed=True,
        ),
        PlannedEffect(
            effect=AdvisoryEffect(type="advisory", rule="PP-1", text="Overridden rule PP-1"),
            trace=RuleTrace(board_path=[]),
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


def test_the_action_plan_holds_committed_and_possible_effects() -> None:
    assert [(p.effect.rule, p.committed) for p in PLAN.effects] == [
        ("PP-1", False),
        ("PP-3", True),
        ("PP-1", True),
    ]


def test_the_action_plan_holds_decline_status_undecided_pages_choices_questions_and_notes() -> None:
    assert PLAN.proposed_decline is True
    assert PLAN.declines_on_every_branch[0].alternatives[1].rule == "PP-5"
    assert PLAN.undecided[0].waits_on == ["p_f"]
    assert PLAN.open_choices[0].options == ["decline", "legacy_underwriting"]
    assert PLAN.open_choices[0].show == ["p_f"]
    assert PLAN.catalogue_questions == ["willing_to_mitigate"]
    assert PLAN.not_evaluated[0].ref == "I46"


def test_an_empty_action_plan_is_not_a_proposed_decline() -> None:
    assert ActionPlan().proposed_decline is False


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
        *[NODE_RESULT.validate_python(r) for r in NODE_RESULT_SAMPLES.values()],
        ASK,
        PLAN.effects[0],
        PLAN.undecided[0],
        PLAN.open_choices[0],
        PLAN.not_evaluated[0],
        PLAN,
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
