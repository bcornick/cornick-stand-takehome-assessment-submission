# ABOUTME: Tests the input and output models of the seven section 8 skills, the shared typed abstention, the A.9 reply models and the section 10.5 quote packet.
# ABOUTME: Skill names, abstention codes and the A.9 field lists are written out here; every model forbids unknown fields and round-trips through JSON.
from typing import Any, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from uwh.rules.models import ActionPlan, Ask
from uwh.runtime import event_types
from uwh.skills import contracts
from uwh.skills.contracts import (
    Abstention,
    BuildQuotePacketInput,
    BuildQuotePacketOutput,
    BuildQuotePacketResult,
    Candidate,
    EvaluatePlaybookInput,
    EvaluatePlaybookOutput,
    LocatedCandidate,
    PlanAsksInput,
    PlanAsksOutput,
    PlanAsksResult,
    QuotePacket,
    ReadReplyInput,
    ReadReplyOutput,
    ReadReplyResult,
    RenderMessageInput,
    RenderMessageOutput,
    RenderMessageResult,
    ReplyReading,
    ResolveDataInput,
    ResolveDataOutput,
    ResolveDataResult,
    TriageFieldsInput,
    TriageFieldsOutput,
    TriageFieldsResult,
)

SKILL_CONTRACTS: dict[str, tuple[type[BaseModel], Any, type[BaseModel]]] = {
    "triage_fields": (TriageFieldsInput, TriageFieldsOutput, TriageFieldsResult),
    "resolve_data": (ResolveDataInput, ResolveDataOutput, ResolveDataResult),
    "evaluate_playbook": (EvaluatePlaybookInput, EvaluatePlaybookOutput, ActionPlan),
    "plan_asks": (PlanAsksInput, PlanAsksOutput, PlanAsksResult),
    "render_message": (RenderMessageInput, RenderMessageOutput, RenderMessageResult),
    "read_reply": (ReadReplyInput, ReadReplyOutput, ReadReplyResult),
    "build_quote_packet": (BuildQuotePacketInput, BuildQuotePacketOutput, BuildQuotePacketResult),
}

ASK = {
    "ask_id": "pool_security",
    "kind": "follow_on_question",
    "fields": ["pool_security"],
    "reason": "conditional_unknown",
    "wording": "If there is a pool: is it fenced?",
}
FIELD_TRIAGE = {
    "value_status": "missing",
    "requirement": "required",
    "resolution": "ask",
    "depends_on": [],
}
FOUND = {
    "status": "found",
    "value": "4",
    "source": "fixture",
    "fetched_at": "2026-06-29T08:00:00+00:00",
    "is_stub": False,
}
CONFLICT = {
    "validator": "roof_before_build",
    "fields": ["roof_replacement_year", "year_built"],
    "values": {"roof_replacement_year": 1990, "year_built": 2001},
    "question": "Please confirm the year built and the year the roof was replaced.",
}
CANDIDATE = {
    "ask_id": "pool_security",
    "field": "pool_security",
    "value": "Fenced",
    "quote": "the pool is fenced",
}
LOCATED = {**CANDIDATE, "span_start": 4, "span_end": 22}
PACKET = {
    "coverages": [{"field": "coverage_a", "value": 500000}],
    "coverage_adjustments": [
        {
            "type": "coverage_adjustment",
            "rule": "RC-1",
            "field": "coverage_a",
            "proposed_value": 450000,
            "submitted_value": 500000,
        }
    ],
    "surcharges": [{"type": "surcharge", "rule": "PP-3", "percent": 15}],
    "requirements": [
        {
            "type": "requirement",
            "rule": "RF-2",
            "text": "Replace the roof",
            "deadline": "first_term",
        }
    ],
    "exclusions_and_endorsements": [
        {"type": "exclusion_or_endorsement", "rule": "PR-1", "text": "Exclude liability"}
    ],
    "advisories": [{"type": "advisory", "rule": "PR-2", "text": "Vinyl siding"}],
}

# One valid input and one valid result per skill; the inputs carry values only.
INPUTS: dict[str, dict[str, Any]] = {
    "triage_fields": {
        "facts": {"pool_type": None, "year_built": 1990},
        "conflicting_fields": ["roof_replacement_year"],
        "unsupported_fields": ["kyc_score"],
        "blocked_fields": ["protection_class"],
    },
    "resolve_data": {
        "facts": {"year_built": None},
        "triage": {"year_built": FIELD_TRIAGE},
        "provider_results": {"protection_class": FOUND},
    },
    "evaluate_playbook": {
        "facts": {"foundation_type": "Piers"},
        "answered_choices": {"I13.fire_fail": "decline"},
        "suppressed_rules": ["PP-1"],
    },
    "plan_asks": {
        "triage": {"year_built": FIELD_TRIAGE},
        "resolved": {
            "observations": [],
            "ask_fields": ["street_address"],
            "catalogue_questions": ["kt_present_and_where"],
            "blockers": [],
        },
        "plan": {},
        "conflicts": [CONFLICT],
    },
    "render_message": {"kind": "request", "lead_label": "LEAD-00000042-001", "asks": [ASK]},
    "read_reply": {"body": "Yes, the pool is fenced.", "open_asks": [ASK]},
    "build_quote_packet": {
        "plan": {},
        "facts": {"coverage_a": 500000},
        "assumed": {"protection_class": "9"},
    },
}
RESULTS: dict[str, dict[str, Any]] = {
    "triage_fields": {"fields": {"year_built": FIELD_TRIAGE}},
    "resolve_data": {
        "observations": [
            {
                "key": "protection_class",
                "value": "9",
                "source": "assumed",
                "evidence": {"rule": "9.3"},
            },
        ],
        "ask_fields": ["zip"],
        "catalogue_questions": [],
        "blockers": [
            {"kind": "data", "owner": "data_team", "detail": {"field": "kyc_score"}},
        ],
    },
    "evaluate_playbook": {"proposed_decline": False},
    "plan_asks": {"asks": [ASK]},
    "render_message": {
        "subject": "Information needed for your quote: LEAD-00000042-001",
        "body": "Thank you for your submission.",
        "ask_ids": ["pool_security"],
    },
    "read_reply": {
        "classification": "answers_some",
        "candidates": [LOCATED],
        "dropped": [CANDIDATE],
    },
    "build_quote_packet": {
        "packet": PACKET,
        "internal": {"assumptions": {"protection_class": "9"}, "rule_traces": [], "approver": None},
    },
}


def test_there_is_one_input_and_one_output_for_each_of_the_seven_skills() -> None:
    assert list(SKILL_CONTRACTS) == [
        "triage_fields",
        "resolve_data",
        "evaluate_playbook",
        "plan_asks",
        "render_message",
        "read_reply",
        "build_quote_packet",
    ]
    assert list(INPUTS) == list(RESULTS) == list(SKILL_CONTRACTS)


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_an_input_validates_and_round_trips(skill: str) -> None:
    input_model = SKILL_CONTRACTS[skill][0]
    value = input_model.model_validate(INPUTS[skill])
    assert input_model.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_an_input_forbids_unknown_fields(skill: str) -> None:
    input_model = SKILL_CONTRACTS[skill][0]
    with pytest.raises(ValidationError):
        input_model.model_validate({**INPUTS[skill], "surprise": 1})


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_an_output_is_the_skills_result_or_the_typed_abstention(skill: str) -> None:
    _, output, result_model = SKILL_CONTRACTS[skill]
    assert set(get_args(output)) == {result_model, Abstention}


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_an_output_picks_the_result_and_round_trips(skill: str) -> None:
    _, output, result_model = SKILL_CONTRACTS[skill]
    adapter = TypeAdapter(output)
    value = adapter.validate_python(RESULTS[skill])
    assert type(value) is result_model
    assert adapter.validate_json(adapter.dump_json(value)) == value


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_an_output_picks_the_abstention(skill: str) -> None:
    adapter = TypeAdapter(SKILL_CONTRACTS[skill][1])
    value = adapter.validate_python(
        {"reason": "invalid_tool_input", "message": "The tool input failed validation twice."}
    )
    assert type(value) is Abstention


@pytest.mark.parametrize("skill", list(SKILL_CONTRACTS))
def test_a_result_forbids_unknown_fields(skill: str) -> None:
    result_model = SKILL_CONTRACTS[skill][2]
    with pytest.raises(ValidationError):
        result_model.model_validate({**RESULTS[skill], "surprise": 1})


def test_the_abstention_holds_a_reason_code_and_a_plain_message() -> None:
    assert list(Abstention.model_fields) == ["reason", "message"]
    for reason in ("refusal", "invalid_tool_input"):  # A.10
        assert Abstention(reason=reason, message="m").reason == reason
    with pytest.raises(ValidationError):
        Abstention.model_validate({"reason": "refusal", "message": "m", "surprise": 1})


def test_inputs_carry_no_handles_or_clients() -> None:
    for input_model, _, _ in SKILL_CONTRACTS.values():
        assert not {
            n
            for n in input_model.model_fields
            if n in {"db", "conn", "connection", "client", "store"}
        }


def test_the_evaluate_playbook_input_holds_usable_facts_answered_choices_and_suppressed_rules() -> (
    None
):
    assert list(EvaluatePlaybookInput.model_fields) == [
        "facts",
        "answered_choices",
        "suppressed_rules",
    ]


def test_the_triage_input_names_conflicting_unsupported_and_blocked_fields() -> None:
    assert list(TriageFieldsInput.model_fields) == [
        "facts",
        "conflicting_fields",
        "unsupported_fields",
        "blocked_fields",
    ]


def test_render_message_kinds_are_the_three_a8_subjects() -> None:
    assert list(get_args(RenderMessageInput.model_fields["kind"].annotation)) == [
        "request",
        "quote_packet",
        "decline_notice",
    ]


def test_a_rendered_message_has_no_recipient_field() -> None:
    assert list(RenderMessageResult.model_fields) == ["subject", "body", "ask_ids"]
    assert "recipient" not in RenderMessageInput.model_fields


# A.9, written out.
def test_candidate_has_the_a9_fields_and_no_offset() -> None:
    assert list(Candidate.model_fields) == ["ask_id", "field", "value", "quote"]
    assert "span_start" not in Candidate.model_fields
    assert "span_end" not in Candidate.model_fields


def test_a_candidate_quote_is_not_empty() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "quote": ""})


@pytest.mark.parametrize("value", ["Fenced", 3, 1.5, True])
def test_a_candidate_value_is_a_string_number_or_boolean_and_keeps_its_type(value: Any) -> None:
    assert type(Candidate.model_validate({**CANDIDATE, "value": value}).value) is type(value)


def test_a_candidate_value_is_not_a_list() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "value": ["Fenced"]})


def test_reply_reading_is_a_classification_and_candidates() -> None:
    assert list(ReplyReading.model_fields) == ["classification", "candidates"]
    assert list(get_args(ReplyReading.model_fields["classification"].annotation)) == [
        "answers_all",
        "answers_some",
        "declines_to_answer",
        "off_topic",
    ]
    reading = ReplyReading.model_validate(
        {"classification": "answers_all", "candidates": [CANDIDATE]}
    )
    assert reading.candidates[0].quote == "the pool is fenced"


def test_the_reply_reading_schema_holds_no_offsets() -> None:
    schema = str(ReplyReading.model_json_schema())
    assert "span_start" not in schema and "span_end" not in schema


def test_reply_reading_refuses_a_located_candidate() -> None:
    with pytest.raises(ValidationError):
        ReplyReading.model_validate({"classification": "answers_all", "candidates": [LOCATED]})


def test_a_located_candidate_is_a_candidate_with_offsets() -> None:
    assert issubclass(LocatedCandidate, Candidate)
    assert list(LocatedCandidate.model_fields) == [
        *Candidate.model_fields,
        "span_start",
        "span_end",
    ]
    located = LocatedCandidate.model_validate(LOCATED)
    assert located.span_start == 4 and located.span_end == 22


def test_the_candidate_contracts_are_the_runtime_classes() -> None:
    assert Candidate is event_types.Candidate
    assert LocatedCandidate is event_types.LocatedCandidate
    assert contracts.ReplyClassification is event_types.ReplyClassification


def test_a_candidate_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate({**CANDIDATE, "surprise": 1})


def test_the_read_reply_result_is_the_classification_with_located_candidates_and_the_dropped() -> (
    None
):
    assert list(ReadReplyResult.model_fields) == ["classification", "candidates", "dropped"]
    with pytest.raises(ValidationError):  # a candidate without offsets is not a located candidate
        ReadReplyResult.model_validate({**RESULTS["read_reply"], "candidates": [CANDIDATE]})


# Section 10.5.
def test_the_quote_packet_holds_the_section_10_5_parts() -> None:
    assert list(QuotePacket.model_fields) == [
        "coverages",
        "coverage_adjustments",
        "surcharges",
        "requirements",
        "exclusions_and_endorsements",
        "advisories",
    ]


def test_the_quote_packet_shows_an_adjustment_beside_the_submitted_value() -> None:
    packet = QuotePacket.model_validate(PACKET)
    assert packet.coverages[0].value == 500000
    adjustment = packet.coverage_adjustments[0]
    assert (adjustment.submitted_value, adjustment.proposed_value) == (500000, 450000)


def test_the_quote_packet_puts_each_surcharge_on_its_own_line_with_its_rule() -> None:
    packet = QuotePacket.model_validate(
        {
            **PACKET,
            "surcharges": [
                PACKET["surcharges"][0],
                {"type": "surcharge", "rule": "PP-4", "percent": 25},
            ],
        }
    )
    assert [(s.percent, s.rule) for s in packet.surcharges] == [(15, "PP-3"), (25, "PP-4")]


def test_the_quote_packet_requirements_carry_deadlines() -> None:
    assert QuotePacket.model_validate(PACKET).requirements[0].deadline == "first_term"


def test_no_field_of_the_packet_is_a_price_or_premium() -> None:
    def names(model: type[BaseModel]) -> set[str]:
        found = set(model.model_fields)
        for info in model.model_fields.values():
            for arg in (info.annotation, *get_args(info.annotation)):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    found |= names(arg)
        return found

    packet_names = names(QuotePacket)
    assert {"percent", "text", "rule"} <= packet_names
    assert not {
        n
        for n in packet_names
        if any(w in n for w in ("price", "premium", "cost", "amount", "total"))
    }


def test_the_internal_copy_lists_assumptions_the_rule_trace_and_the_approver() -> None:
    internal = BuildQuotePacketResult.model_validate(RESULTS["build_quote_packet"]).internal
    assert list(type(internal).model_fields) == ["assumptions", "rule_traces", "approver"]
    assert internal.assumptions == {"protection_class": "9"}
    assert internal.approver is None


def test_no_contract_model_carries_a_confidence() -> None:
    for cls in contract_classes():
        assert not {n for n in cls.model_fields if "confidence" in n}, cls


def contract_classes() -> list[type[BaseModel]]:
    return [
        c
        for c in vars(contracts).values()
        if isinstance(c, type) and issubclass(c, BaseModel) and c.__module__ == contracts.__name__
    ]


def test_every_asks_model_is_the_rules_ask() -> None:
    assert PlanAsksResult.model_fields["asks"].annotation == list[Ask]
    assert ReadReplyInput.model_fields["open_asks"].annotation == list[Ask]


def test_every_contract_model_forbids_unknown_fields() -> None:
    assert contract_classes()
    for cls in contract_classes():
        assert cls.model_config.get("extra") == "forbid", cls
