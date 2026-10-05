# ABOUTME: Tests that the event-type enum holds the 28 names of A.2 and that each type has a payload model named after it.
# ABOUTME: The names and each payload's field set are written out here; every payload forbids unknown fields and round-trips through JSON.
from datetime import date
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from uwh.runtime import event_types
from uwh.runtime.event_types import (
    PAYLOAD_MODELS,
    BlockerDetail,
    EventType,
    LocatedCandidate,
    ReplyClassification,
    RulingRecorded,
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
EXPECTED_FIELDS: dict[str, set[str]] = {
    "run_started": {"seed", "lead_count"},
    "replay_miss": {"skill", "prompt_version", "input_hash"},
    "draft_edited": {"intent_id", "subject", "body", "payload_hash", "reason", "lead_revision"},
    "proposal_created": {"proposal_id", "kind", "diff_hash"},
    "lead_received": {"source", "received_at"},
    "fact_observed": {"observation_id", "key", "value", "source", "evidence", "status"},
    "fact_selected": {"key", "observation_id", "value", "source", "confirmed"},
    "conflict_opened": {"validator", "fields", "values", "question"},
    "conflict_closed": {"validator", "fields", "values", "observation_id"},
    "triage_completed": {"fields"},
    "provider_called": {
        "key",
        "status",
        "value",
        "source",
        "fetched_at",
        "is_stub",
        "missing_inputs",
    },
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
    "reply_read": {"intent_id", "body_hash", "classification", "candidates", "dropped"},
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
    "triage_completed": {"fields": {"year_built": {"value_status": "present", "depends_on": []}}},
    "provider_called": {
        "key": "protection_class",
        "status": "blocked",
        "value": None,
        "source": "stand-in",
        "fetched_at": "2026-06-29T08:01:00+00:00",
        "is_stub": True,
        "missing_inputs": ["zip"],
    },
    "plan_built": {"plan": {"asks": [], "effects": [{"kind": "no_action"}]}, "plan_hash": H},
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
            "missing_inputs": ["zip"],
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
        assert issubclass(model, BaseModel)


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


def test_provider_status_and_observation_values_are_closed_sets() -> None:
    provider = PAYLOAD_MODELS[EventType.provider_called]
    with pytest.raises(ValidationError):
        provider.model_validate({**SAMPLES["provider_called"], "status": "maybe"})
    observed = PAYLOAD_MODELS[EventType.fact_observed]
    with pytest.raises(ValidationError):
        observed.model_validate({**SAMPLES["fact_observed"], "source": "guess"})
    with pytest.raises(ValidationError):
        observed.model_validate({**SAMPLES["fact_observed"], "status": "maybe"})


RULING = SAMPLES["ruling_recorded"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "choice"},
        {"kind": "suppression", "choice_id": None, "option": None, "suppressed_rule_ids": ["PP-3"]},
        {"kind": "decline", "choice_id": None, "option": None},
        {"kind": "withdrawal", "choice_id": None, "option": None, "refers_to_event_id": 5},
        {"kind": "reopened_choice", "refers_to_event_id": 5},
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
        {"kind": "reopened_choice", "refers_to_event_id": None},
        {"kind": "reopened_choice", "choice_id": None, "refers_to_event_id": 5},
        {"kind": "approved"},
    ],
)
def test_a_ruling_missing_a_required_part_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RulingRecorded.model_validate({**RULING, **overrides})


def test_blocker_detail_needs_a_resume_trigger_and_text_and_defaults_the_rest() -> None:
    detail = BlockerDetail.model_validate({"resume_trigger": "reply_received", "text": "waiting"})
    assert detail.item_kind is None and detail.cause is None and detail.cause_persists is False
    assert detail.intent_id is None and detail.observation_id is None
    assert detail.choice_ids == [] and detail.missing_inputs == []
    for missing in ("resume_trigger", "text"):
        full = {"resume_trigger": "x", "text": "y"}
        del full[missing]
        with pytest.raises(ValidationError):
            BlockerDetail.model_validate(full)
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate({"resume_trigger": "x", "text": "y", "surprise": 1})
    with pytest.raises(ValidationError):
        BlockerDetail.model_validate({"resume_trigger": "x", "text": "y", "item_kind": "other"})


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
