# ABOUTME: The three controls of section 13.4, each a deliberately broken variant of the system under test: do nothing, email every lead with every missing field, and send twice.
# ABOUTME: A control replaces one function or one client of the running system for the length of a run; no production code path carries a switch for it.
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from types import ModuleType
from typing import Any

import httpx2

import uwh.api.runtime
from uwh.rules.models import Ask, AskKind, ValueStatus
from uwh.runtime.faults import FaultPlan
from uwh.runtime.mailbox_client import MailboxClient
from uwh.skills.plan_asks import skill as plan_asks


class Control(StrEnum):
    do_nothing = "do_nothing"
    email_everything = "email_everything"
    send_twice = "send_twice"


class DoubleSendingMailbox(MailboxClient):
    """Posts every message twice. The extra copy is posted without the fault plan, so a fault that
    loses the result of the post that counts still leaves two messages in the mailbox."""

    def send(
        self,
        lead_id: str,
        to: str,
        from_: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        faults, self.faults = self.faults, None
        try:
            super().send(lead_id, to, from_, subject, body, metadata)
        finally:
            self.faults = faults
        return super().send(lead_id, to, from_, subject, body, metadata)


def mailbox_client(
    control: Control | None, http: httpx2.Client, faults: FaultPlan | None = None
) -> MailboxClient:
    """The mailbox client of the system under test."""
    cls = DoubleSendingMailbox if control == Control.send_twice else MailboxClient
    return cls(http, faults)


def _ask_every_missing_field(input: plan_asks.PlanAsksInput) -> plan_asks.PlanAsksOutput:
    """Asks every field the lead has no value for, whoever owns it and whatever its condition."""
    asks = [
        Ask(
            ask_id=name,
            kind=AskKind.field_request,
            fields=[name],
            reason="The lead has no value for it.",
            wording=f"What is the {input.registry[name].label}?",
        )
        for name, triage in input.triage.items()
        if triage.value_status == ValueStatus.missing
    ]
    return plan_asks.PlanAsksOutput(asks=asks, message_class="routine_request")


@contextmanager
def _replaced(module: ModuleType, name: str, value: Callable[..., Any]) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextmanager
def applied(control: Control | None) -> Iterator[None]:
    """Apply the control to the system under test for the length of the block.

    - do nothing: the app builds no workflow steps (`build_steps` of `uwh.api.runtime`), so no step runs;
    - email everything: `plan_asks.run` asks every missing field, and the request goes out as routine;
    - send twice: nothing is replaced here; `mailbox_client` builds the doubling client.
    """
    if control == Control.do_nothing:
        with _replaced(
            uwh.api.runtime, "build_steps", lambda registry, providers, rules, model: ()
        ):
            yield
    elif control == Control.email_everything:
        with _replaced(plan_asks, "run", _ask_every_missing_field):
            yield
    else:
        yield
