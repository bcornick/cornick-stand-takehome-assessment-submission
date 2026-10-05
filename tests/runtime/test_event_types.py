# ABOUTME: Tests that the event-type enum holds the 28 names of A.2 and that each type has a payload model named after it.
# ABOUTME: The names and each payload's field set are written out here; every payload forbids unknown fields and round-trips through JSON.
from datetime import date
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from uwh.providers.models import ProviderResult
from uwh.rules.models import ActionPlan, FieldTriage, StrictModel
from uwh.runtime import event_types
from uwh.runtime.event_types import (
    PAYLOAD_MODELS,
    AbstentionReason,
    Actor,
    ApprovalItemKind,
    AutonomyLevel,
    BlockerDetail,
    BlockerKind,
    BlockerOwner,
    EventType,
    LocatedCandidate,
    MessageKind,
    ObservationSource,
    ReplyClassification,
    RequestKind,
    ReviewCause,
    RulingRecorded,
    Status,
)

# A.2, in order.
A2_NAMES = [
    "run_started",
    "replay_miss",
    "draft_edited",
    "proposal_created",
    "lead_received",
    "fact_observed",
    "fact_selected",
    "conflict_opened",
    "conflict_closed",
    "triage_completed",
    "provider_called",
    "plan_built",
    "blocker_opened",
    "blocker_closed",
    "intent_created",
    "message_sent",
    "delivery_unknown",
    "reply_received",
    "reply_read",
    "approval_recorded",
    "ruling_recorded",
    "command_refused",
    "setting_changed",
    "class_demoted",
    "rule_change_applied",
    "skill_fallback_used",
    "model_called",
    "fault_injected",
]

# The fields each payload holds; the event row's own columns are not repeated here.
# This is the freeze of the contract shapes reviewed at the stage 2 gate: a change detector,
# not a behaviour test. A payload change updates this table in the same commit.
EXPECTED_BLOCKER_DETAIL_FIELDS = {
    "item_kind",
    "cause",
    "cause_persists",
    "resume_trigger",
    "intent_id",
    "observation_id",
    "choice_ids",
    "text",
}

EXPECTED_FIELDS: dict[str, set[str]] = {
    "run_started": {"seed", "lead_count"},
    "replay_miss": {"skill", "prompt_version", "input_hash"},
    "draft_edited": {
        "intent_id",
        "kind",
        "subject",
        "body",
        "payload_hash",
        "reason",
        "lead_revision",
    },
    "proposal_created": {"proposal_id", "kind", "diff_hash"},
    "lead_received": {"source", "received_at"},
    "fact_observed": {"observation_id", "key", "value", "source", "evidence", "status"},
    "fact_selected": {"key", "observation_id", "value", "source", "confirmed"},
    "conflict_opened": {"validator", "fields", "values", "question"},
    "conflict_closed": {"validator", "fields", "values", "observation_id"},
    "triage_completed": {"fields"},
    "provider_called": {"key", "result"},
    "plan_built": {"plan", "plan_hash"},
    "blocker_opened": {"blocker_id", "kind", "owner", "detail"},
    "blocker_closed": {"blocker_id", "kind"},
    "intent_created": {
        "intent_id",
        "round",
        "kind",
        "recipient",
        "subject",
        "body",
        "ask_ids",
        "payload_hash",
    },
    "message_sent": {"intent_id", "mailbox_id"},
    "delivery_unknown": {"intent_id"},
    "reply_received": {"intent_id", "body", "body_hash"},
    "reply_read": {
        "intent_id",
        "body_hash",
        "classification",
        "abstention",
        "candidates",
        "dropped",
    },
    "approval_recorded": {
        "item_id",
        "item_kind",
        "intent_id",
        "lead_revision",
        "plan_hash",
        "ruleset_hash",
        "recipient",
        "payload_hash",
        "decision",
        "reason",
    },
    "ruling_recorded": {
        "kind",
        "choice_id",
        "option",
        "reason",
        "lead_revision",
        "plan_hash",
        "suppressed_rule_ids",
        "refers_to_event_id",
    },
    "command_refused": {"command_type", "command_payload", "reason"},
    "setting_changed": {"key", "value"},
    "class_demoted": {"command_class", "reason"},
    "rule_change_applied": {"proposal_id", "diff_hash", "applied_ruleset_hash"},
    "skill_fallback_used": {"skill", "status", "fallback"},
    "model_called": {
        "skill",
        "prompt_version",
        "input_hash",
        "tokens_in",
        "tokens_out",
        "stop_reason",
    },
    "fault_injected": {"fault"},
}

H = "a" * 64

# One valid payload per type, with values that make a lossy round trip visible.
SAMPLES: dict[str, dict[str, object]] = {
    "run_started": {"seed": 42, "lead_count": 10},
    "replay_miss": {"skill": "read_reply", "prompt_version": H, "input_hash": H},
    "draft_edited": {
        "intent_id": "i1",
        "kind": "sensitive_request",
        "subject": "Re: café",
        "body": "Line one\nLine two",
        "payload_hash": H,
        "reason": "tone",
        "lead_revision": 2,
    },
    "proposal_created": {"proposal_id": 3, "kind": "rule_change", "diff_hash": H},
    "lead_received": {"source": "broker_email", "received_at": "2026-06-29T08:00:00+00:00"},
    "fact_observed": {
        "observation_id": 7,
        "key": "p_f",
        "value": 0.5,
        "source": "fetched",
        "evidence": {"provider": "fire model", "spans": [1, 2]},
        "status": "accepted",
    },
    "fact_selected": {
        "key": "year_built",
        "observation_id": 8,
        "value": 1950,
        "source": "reply",
        "confirmed": True,
    },
    "conflict_opened": {
        "validator": "roof_before_build",
        "fields": ["roof_replacement_year", "year_built"],
        "values": {"roof_replacement_year": 1990, "year_built": 2000},
        "question": "Can you confirm the roof year?",
    },
    "conflict_closed": {
        "validator": "roof_before_build",
        "fields": ["roof_replacement_year", "year_built"],
        "values": {"roof_replacement_year": 1990, "year_built": 2000},
        "observation_id": 9,
    },
    "triage_completed": {
        "fields": {
            "year_built": {
                "value_status": "present",
                "requirement": "required",
                "resolution": "none",
                "depends_on": [],
            }
        }
    },
    "provider_called": {
        "key": "protection_class",
        "result": {
            "status": "blocked",
            "value": None,
            "source": "stand-in",
            "fetched_at": "2026-06-29T08:01:00+00:00",
            "is_stub": True,
            "missing_inputs": ["zip"],
        },
    },
    "plan_built": {
        "plan": ActionPlan.model_validate(
            {
                "effects": [
                    {
                        "effect": {"type": "no_action", "rule": "R-01-1"},
                        "trace": {"board_path": ["01:START", "01:OK"]},
                        "committed": True,
                    }
                ],
                "catalogue_questions": ["kt_extent"],
            }
        ).model_dump(mode="json"),
        "plan_hash": H,
    },
    "blocker_opened": {
        "blocker_id": 1,
        "kind": "data",
        "owner": "data_team",
        "detail": {
            "item_kind": None,
            "cause": None,
            "cause_persists": False,
            "resume_trigger": "provider_available",
            "intent_id": None,
            "observation_id": None,
            "choice_ids": [],
            "text": "lookup down",
        },
    },
    "blocker_closed": {"blocker_id": 1, "kind": "data"},
    "intent_created": {
        "intent_id": "i1",
        "round": 1,
        "kind": "routine_request",
        "recipient": "a@example.com",
        "subject": "s",
        "body": "b",
        "ask_ids": ["year_built", "q:contact_email"],
        "payload_hash": H,
    },
    "message_sent": {"intent_id": "i1", "mailbox_id": 12},
    "delivery_unknown": {"intent_id": "i1"},
    "reply_received": {"intent_id": "i1", "body": "It is 1950.", "body_hash": H},
    "reply_read": {
        "intent_id": "i1",
        "body_hash": H,
        "classification": "answers_some",
        "abstention": None,
        "candidates": [
            {
                "ask_id": "year_built",
                "field": "year_built",
                "value": 1950,
                "quote": "1950",
                "span_start": 6,
                "span_end": 10,
            }
        ],
        "dropped": [
            {"ask_id": "pool_type", "field": "pool_type", "value": "Inground", "quote": "pool"}
        ],
    },
    "approval_recorded": {
        "item_id": 4,
        "item_kind": "draft",
        "intent_id": "i1",
        "lead_revision": 2,
        "plan_hash": H,
        "ruleset_hash": H,
        "recipient": "a@example.com",
        "payload_hash": H,
        "decision": "approved",
        "reason": "ok",
    },
    "ruling_recorded": {
        "kind": "choice",
        "choice_id": "I07.two_months",
        "option": "under_60_days",
        "reason": "r",
        "lead_revision": 3,
        "plan_hash": H,
        "suppressed_rule_ids": [],
        "refers_to_event_id": None,
    },
    "command_refused": {
        "command_type": "approve",
        "command_payload": {"item_id": 4, "plan_hash": H},
        "reason": "stale hash",
    },
    "setting_changed": {"key": "autonomy.fetch_data", "value": "review"},
    "class_demoted": {"command_class": "send_routine_request", "reason": "duplicate"},
    "rule_change_applied": {"proposal_id": 3, "diff_hash": H, "applied_ruleset_hash": H},
    "skill_fallback_used": {"skill": "read_reply", "status": "failing", "fallback": "unread"},
    "model_called": {
        "skill": "read_reply",
        "prompt_version": H,
        "input_hash": H,
        "tokens_in": 100,
        "tokens_out": 20,
        "stop_reason": "tool_use",
    },
    "fault_injected": {"fault": "provider_unavailable"},
}

# The event row's columns. `ruleset_hash` is a row column too but is left out on purpose:
# `ApprovalRecorded.ruleset_hash` is the ruleset the approval is bound to (section 7.4), not the
# ruleset in force at the event.
ROW_COLUMNS = {
    "run_id",
    "mode",
    "lead_id",
    "type",
    "actor",
    "prompt_versions_json",
    "model_id",
    "request_id",
    "real_ts",
    "sim_ts",
}


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def test_event_type_enum_equals_the_28_names_of_a2() -> None:
    assert len(A2_NAMES) == 28
    assert [t.value for t in EventType] == A2_NAMES
    assert {t.name for t in EventType} == set(A2_NAMES)


def test_each_type_has_a_payload_model_named_after_it() -> None:
    assert set(PAYLOAD_MODELS) == set(EventType)
    for name in A2_NAMES:
        model = PAYLOAD_MODELS[EventType(name)]
        assert model.__name__ == pascal(name)
        assert getattr(event_types, pascal(name)) is model
        assert issubclass(model, StrictModel)


def test_the_test_tables_cover_every_type() -> None:
    assert set(EXPECTED_FIELDS) == set(A2_NAMES)
    assert set(SAMPLES) == set(A2_NAMES)


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_fields(name: str) -> None:
    fields = set(PAYLOAD_MODELS[EventType(name)].model_fields)
    assert fields == EXPECTED_FIELDS[name]
    assert "confidence" not in fields
    assert not fields & ROW_COLUMNS


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_forbids_unknown_fields(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    with pytest.raises(ValidationError):
        model.model_validate({**SAMPLES[name], "surprise": 1})


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_requires_every_field(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    for field in SAMPLES[name]:
        partial = {k: v for k, v in SAMPLES[name].items() if k != field}
        with pytest.raises(ValidationError):
            model.model_validate(partial)


@pytest.mark.parametrize("name", A2_NAMES)
def test_payload_round_trips_through_json(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    payload = model.model_validate(SAMPLES[name])
    assert model.model_validate_json(payload.model_dump_json()) == payload


def test_round_trip_keeps_value_types() -> None:
    model = PAYLOAD_MODELS[EventType.fact_selected]
    for value in (True, 1, 1.0, "1", None, ["a"], {"k": 1.5}):
        payload = model.model_validate({**SAMPLES["fact_selected"], "value": value})
        back = model.model_validate_json(payload.model_dump_json())
        assert back == payload
        assert type(back.value) is type(value)  # type: ignore[attr-defined]


def test_reply_read_candidates_carry_the_a9_fields() -> None:
    model = PAYLOAD_MODELS[EventType.reply_read]
    located = model.model_fields["candidates"].annotation
    dropped = model.model_fields["dropped"].annotation
    assert located is not None and dropped is not None
    assert set(located.__args__[0].model_fields) == {  # type: ignore[attr-defined]
        "ask_id",
        "field",
        "value",
        "quote",
        "span_start",
        "span_end",
    }
    assert set(dropped.__args__[0].model_fields) == {  # type: ignore[attr-defined]
        "ask_id",
        "field",
        "value",
        "quote",
    }


LOCATED_CANDIDATE = {
    "ask_id": "year_built",
    "field": "year_built",
    "value": 1950,
    "quote": "1950",
    "span_start": 6,
    "span_end": 10,
}


def test_a_located_candidate_span_is_as_long_as_its_quote() -> None:
    located = LocatedCandidate.model_validate(LOCATED_CANDIDATE)
    assert located.span_end - located.span_start == len(located.quote)
    with pytest.raises(ValidationError):
        LocatedCandidate.model_validate({**LOCATED_CANDIDATE, "span_end": 11})
    with pytest.raises(ValidationError):
        LocatedCandidate.model_validate({**LOCATED_CANDIDATE, "span_end": 9})


def test_a_located_candidate_span_starts_inside_the_body() -> None:
    at_start = {**LOCATED_CANDIDATE, "span_start": 0, "span_end": 4}
    assert LocatedCandidate.model_validate(at_start).span_start == 0
    with pytest.raises(ValidationError):
        LocatedCandidate.model_validate({**LOCATED_CANDIDATE, "span_start": -2, "span_end": 2})


def provider_called(**result_changes: object) -> dict[str, object]:
    result = SAMPLES["provider_called"]["result"]
    assert isinstance(result, dict)
    return {**SAMPLES["provider_called"], "result": {**result, **result_changes}}


def test_provider_called_holds_the_provider_result_whole() -> None:
    called = PAYLOAD_MODELS[EventType.provider_called].model_validate(SAMPLES["provider_called"])
    assert isinstance(called.result, ProviderResult)  # type: ignore[attr-defined]
    assert called.result.missing_inputs == ["zip"]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "result_changes",
    [
        {"status": "maybe"},
        # the provider result's own rules: a blocked result names its missing inputs, and only a
        # found result has a value
        {"missing_inputs": []},
        {"status": "found", "missing_inputs": []},
        {"value": 3},
    ],
)
def test_provider_called_refuses_a_result_the_provider_models_refuse(
    result_changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[EventType.provider_called].model_validate(provider_called(**result_changes))


def test_observation_status_is_a_closed_set() -> None:
    observed = PAYLOAD_MODELS[EventType.fact_observed]
    with pytest.raises(ValidationError):
        observed.model_validate({**SAMPLES["fact_observed"], "status": "maybe"})


# The value sets written out from the architecture: 7.1 statuses and blocker kinds, A.1 owners,
# intent kinds and item kinds, 7.3 sources, 7.4 actors, autonomy levels (7.4), A.11 review causes.
EXPECTED_VALUE_SETS = [
    (Status, ["received", "triaged", "in_progress", "quote_sent", "declined"]),
    (
        BlockerKind,
        [
            "delivery_unknown",
            "underwriter_question",
            "underwriter_review",
            "data",
            "producer_reply",
        ],
    ),
    (BlockerOwner, ["underwriter", "producer", "data_team"]),
    (RequestKind, ["routine_request", "sensitive_request"]),
    (MessageKind, ["routine_request", "sensitive_request", "quote_packet", "decline_notice"]),
    (
        ApprovalItemKind,
        ["draft", "observation", "delivery_unknown", "no_contact_route", "review"],
    ),
    (ObservationSource, ["submitted", "fetched", "derived", "assumed", "reply", "underwriter"]),
    (Actor, ["workflow", "underwriter", "assistant", "mcp_client", "inbound"]),
    (AutonomyLevel, ["auto", "review", "off"]),
    (
        ReviewCause,
        [
            "late_reply",
            "unread_reply",
            "off_topic_reply",
            "declining_reply",
            "reply_after_terminal_status",
            "draft_held_by_stop",
            "draft_held_class_off",
            "round_limit",
            "identity_score_missing",
            "identity_score_unsupported",
        ],
    ),
]


@pytest.mark.parametrize(("literal", "expected"), EXPECTED_VALUE_SETS)
def test_each_value_set_holds_the_architectures_values(literal: Any, expected: list[str]) -> None:
    assert sorted(get_args(literal)) == sorted(expected)


@pytest.mark.parametrize(
    ("name", "field", "good"),
    [
        ("fact_observed", "source", "fetched"),
        ("fact_selected", "source", "reply"),
        ("blocker_opened", "kind", "data"),
        ("blocker_opened", "owner", "data_team"),
        ("blocker_closed", "kind", "producer_reply"),
        ("intent_created", "kind", "quote_packet"),
        ("draft_edited", "kind", "decline_notice"),
        ("approval_recorded", "item_kind", "no_contact_route"),
    ],
)
def test_a_payload_field_takes_its_value_set_and_refuses_another(
    name: str, field: str, good: str
) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    assert getattr(model.model_validate({**SAMPLES[name], field: good}), field) == good
    with pytest.raises(ValidationError):
        model.model_validate({**SAMPLES[name], field: "any_name"})


def test_a_blocker_detail_takes_an_item_kind_and_a_review_cause_of_their_sets() -> None:
    detail = {"resume_trigger": "x", "text": "y"}
    assert BlockerDetail.model_validate({**detail, "item_kind": "review"}).item_kind == "review"
    assert BlockerDetail.model_validate({**detail, "cause": "late_reply"}).cause == "late_reply"
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate({**detail, "item_kind": "any"})
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate({**detail, "cause": "any"})


RULING = SAMPLES["ruling_recorded"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "choice"},
        {"kind": "suppression", "choice_id": None, "option": None, "suppressed_rule_ids": ["PP-3"]},
        {"kind": "decline", "choice_id": None, "option": None},
        {"kind": "withdrawal", "choice_id": None, "option": None, "refers_to_event_id": 5},
        {"kind": "reopened_choice", "option": None, "refers_to_event_id": 5},
    ],
)
def test_a_ruling_with_its_required_parts_is_valid(overrides: dict[str, object]) -> None:
    assert RulingRecorded.model_validate({**RULING, **overrides}).kind == overrides["kind"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "choice", "choice_id": None},
        {"kind": "choice", "option": None},
        {"kind": "suppression", "suppressed_rule_ids": []},
        {"kind": "withdrawal", "refers_to_event_id": None},
        {"kind": "reopened_choice", "option": None, "refers_to_event_id": None},
        {"kind": "reopened_choice", "choice_id": None, "option": None, "refers_to_event_id": 5},
        {"kind": "reopened_choice", "option": "under_60_days", "refers_to_event_id": 5},
        {"kind": "approved"},
    ],
)
def test_a_ruling_missing_a_required_part_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RulingRecorded.model_validate({**RULING, **overrides})


def test_a_blocker_detail_names_no_missing_inputs() -> None:
    # Section 9.4: a blocked lookup does not raise a data blocker, so no blocker carries inputs.
    assert set(BlockerDetail.model_fields) == EXPECTED_BLOCKER_DETAIL_FIELDS
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate(
            {"resume_trigger": "x", "text": "y", "missing_inputs": ["zip"]}
        )


def test_the_plan_and_triage_samples_follow_the_rules_models() -> None:
    plan = SAMPLES["plan_built"]["plan"]
    assert ActionPlan.model_validate(plan).model_dump(mode="json") == plan
    fields = SAMPLES["triage_completed"]["fields"]
    assert isinstance(fields, dict) and fields
    for triage in fields.values():
        assert FieldTriage.model_validate(triage).model_dump(mode="json") == triage


@pytest.mark.parametrize(
    "overrides",
    [
        # suppressed_rule_ids belongs to a suppression only
        {"kind": "choice", "suppressed_rule_ids": ["PP-3"]},
        {"kind": "decline", "choice_id": None, "option": None, "suppressed_rule_ids": ["PP-3"]},
        {
            "kind": "withdrawal",
            "choice_id": None,
            "option": None,
            "refers_to_event_id": 5,
            "suppressed_rule_ids": ["PP-3"],
        },
        {
            "kind": "reopened_choice",
            "refers_to_event_id": 5,
            "suppressed_rule_ids": ["PP-3"],
        },
        # choice_id and option do not belong to a suppression, a decline or a withdrawal
        {"kind": "suppression", "suppressed_rule_ids": ["PP-3"], "choice_id": "c", "option": None},
        {"kind": "suppression", "suppressed_rule_ids": ["PP-3"], "choice_id": None, "option": "o"},
        {"kind": "decline", "choice_id": "c", "option": None},
        {"kind": "decline", "choice_id": None, "option": "o"},
        {"kind": "withdrawal", "refers_to_event_id": 5, "choice_id": "c", "option": None},
        {"kind": "withdrawal", "refers_to_event_id": 5, "choice_id": None, "option": "o"},
        # refers_to_event_id does not belong to a choice, a suppression or a decline
        {"kind": "choice", "refers_to_event_id": 5},
        {
            "kind": "suppression",
            "choice_id": None,
            "option": None,
            "suppressed_rule_ids": ["PP-3"],
            "refers_to_event_id": 5,
        },
        {"kind": "decline", "choice_id": None, "option": None, "refers_to_event_id": 5},
    ],
)
def test_a_ruling_carrying_a_part_its_kind_does_not_use_is_refused(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RulingRecorded.model_validate({**RULING, **overrides})


def test_blocker_detail_needs_a_resume_trigger_and_text_and_defaults_the_rest() -> None:
    detail = BlockerDetail.model_validate({"resume_trigger": "reply_received", "text": "waiting"})
    assert detail.item_kind is None and detail.cause is None and detail.cause_persists is False
    assert detail.intent_id is None and detail.observation_id is None
    assert detail.choice_ids == []
    for missing in ("resume_trigger", "text"):
        full = {"resume_trigger": "x", "text": "y"}
        del full[missing]
        with pytest.raises(ValidationError):
            BlockerDetail.model_validate(full)
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate({"resume_trigger": "x", "text": "y", "surprise": 1})


@pytest.mark.parametrize(
    ("name", "field"),
    [("fact_observed", "evidence"), ("triage_completed", "fields"), ("plan_built", "plan")],
)
def test_json_object_fields_refuse_a_value_that_does_not_survive_json(
    name: str, field: str
) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    with pytest.raises(ValidationError):
        model.model_validate({**SAMPLES[name], field: {"when": date(2026, 6, 29)}})


def test_reply_classification_is_the_four_a9_values() -> None:
    assert set(get_args(ReplyClassification)) == {
        "answers_all",
        "answers_some",
        "declines_to_answer",
        "off_topic",
    }
    model = PAYLOAD_MODELS[EventType.reply_read]
    with pytest.raises(ValidationError):
        model.model_validate({**SAMPLES["reply_read"], "classification": "maybe"})


def test_a_draft_edit_records_the_kind_the_intent_has_after_the_edit() -> None:
    # 7.5: an edited routine request becomes a sensitive request; the event carries the result.
    model = PAYLOAD_MODELS[EventType.draft_edited]
    assert model.model_validate(SAMPLES["draft_edited"]).kind == "sensitive_request"  # type: ignore[attr-defined]
    without_kind = {k: v for k, v in SAMPLES["draft_edited"].items() if k != "kind"}
    with pytest.raises(ValidationError):
        model.model_validate(without_kind)


def test_the_abstention_codes_are_the_two_of_a10() -> None:
    assert set(get_args(AbstentionReason)) == {"invalid_tool_input", "refusal"}


ABSTAINED = {
    **SAMPLES["reply_read"],
    "classification": None,
    "abstention": "refusal",
    "candidates": [],
    "dropped": [],
}


@pytest.mark.parametrize("code", ["invalid_tool_input", "refusal"])
def test_a_reply_read_may_record_an_abstention_in_place_of_a_reading(code: str) -> None:
    # 10.4: when read_reply abstains, the event records the abstention in place of a reading.
    model = PAYLOAD_MODELS[EventType.reply_read]
    event = model.model_validate({**ABSTAINED, "abstention": code})
    assert event.abstention == code  # type: ignore[attr-defined]
    assert event.classification is None  # type: ignore[attr-defined]
    assert model.model_validate(SAMPLES["reply_read"]).abstention is None  # type: ignore[attr-defined]


READ = SAMPLES["reply_read"]
REFUSED_REPLY_READS = [
    {**ABSTAINED, "abstention": None},  # neither a reading nor an abstention
    {**READ, "abstention": "refusal"},  # both
    {**ABSTAINED, "abstention": "timeout"},  # a code outside the two
    {**ABSTAINED, "candidates": READ["candidates"]},  # an abstention with candidates
    {**ABSTAINED, "dropped": READ["dropped"]},  # an abstention with dropped candidates
]


@pytest.mark.parametrize("payload", REFUSED_REPLY_READS)
def test_a_reply_read_holds_a_reading_or_an_abstention_never_both_or_neither(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[EventType.reply_read].model_validate(payload)
