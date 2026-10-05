# ABOUTME: The fact ledger of 7.3: observations and the effective fact per key, selected by the ten source-authority rules, with conflicts opened and closed by validators and derived facts recomputed.
# ABOUTME: Every change writes its events in the caller's transaction and moves the lead revision once when an effective fact changed; the registry, validators and derivations arrive as plain arguments.
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, get_args

from pydantic import JsonValue

from uwh.runtime.event_types import (
    BlockerDetail,
    ConflictClosed,
    ConflictOpened,
    EventType,
    FactObserved,
    FactSelected,
    ObservationSource,
    ObservationStatus,
)
from uwh.runtime.events import EventContext, append_event, read_events
from uwh.runtime.waits import close_blocker, open_blocker, open_blockers


@dataclass(frozen=True)
class Conflict:
    """What a validator (9.5) returns: the fields involved, their reported values and a neutral question."""

    validator: str
    fields: tuple[str, ...]
    values: dict[str, JsonValue]
    question: str

    @property
    def opened(self) -> ConflictOpened:
        """The conflict as its `conflict_opened` event holds it."""
        return ConflictOpened(
            validator=self.validator,
            fields=list(self.fields),
            values=self.values,
            question=self.question,
        )

    @property
    def identity(self) -> tuple[str, tuple[str, ...], str]:
        """The validator on these values: a conflict closed by the reply or underwriter observation that confirmed its values is not opened again on them (9.6)."""
        return (self.validator, self.fields, _canonical(self.values))


# A validator maps the lead's effective values to the conflicts that hold.
Validator = Callable[[Mapping[str, JsonValue]], list[Conflict]]


@dataclass(frozen=True)
class Derivation:
    """A derived fact: `compute` maps the values of `inputs` to the value of `key`."""

    id: str
    key: str
    inputs: tuple[str, ...]
    compute: Callable[[Mapping[str, JsonValue]], JsonValue]


@dataclass(frozen=True)
class LedgerRules:
    """What the ledger is told: the keys a reply never sets (rule 4), the validators to run on facts
    (rule 8) and the derivations, each listed after the derivations it reads (rule 5)."""

    system_owned_keys: frozenset[str] = frozenset()
    validators: tuple[Validator, ...] = ()
    derivations: tuple[Derivation, ...] = ()


@dataclass(frozen=True)
class ReplyValue:
    """One value read from a reply, with its evidence (the quoted span)."""

    key: str
    value: JsonValue
    evidence: dict[str, JsonValue]


@dataclass(frozen=True)
class Fact:
    """An effective fact with the observation it points at."""

    key: str
    value: JsonValue
    source: ObservationSource
    status: ObservationStatus
    confirmed: bool
    evidence: dict[str, JsonValue]
    observation_id: int


@dataclass
class _Pass:
    """One ledger operation on one lead: it records, selects and, at the end, settles derived facts, conflicts and the revision."""

    db: sqlite3.Connection
    context: EventContext
    lead_id: str
    rules: LedgerRules
    moves_revision: bool = field(default=False)

    def record(
        self,
        key: str,
        value: JsonValue,
        source: ObservationSource,
        evidence: dict[str, JsonValue],
        status: ObservationStatus,
    ) -> int:
        cursor = self.db.execute(
            "INSERT INTO observations (lead_id, key, value_json, source, evidence_json, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (self.lead_id, key, json.dumps(value), source, json.dumps(evidence), status),
        )
        observation_id = cursor.lastrowid
        assert observation_id is not None  # an INSERT always sets it
        event_id = append_event(
            self.db,
            self.context,
            EventType.fact_observed,
            FactObserved(
                observation_id=observation_id,
                key=key,
                value=value,
                source=source,
                evidence=evidence,
                status=status,
            ),
            lead_id=self.lead_id,
        )
        self.db.execute(
            "UPDATE observations SET event_id = ? WHERE id = ?", (event_id, observation_id)
        )
        return observation_id

    def select(self, observation_id: int, *, confirmed: bool = False) -> None:
        """Make the observation the effective fact of its key; nothing is written when it already is."""
        key, value_json, source = self.db.execute(
            "SELECT key, value_json, source FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()
        current = effective_facts(self.db, self.lead_id).get(key)
        if (
            current is not None
            and current.observation_id == observation_id
            and current.confirmed == confirmed
        ):
            return
        self.db.execute(
            "INSERT OR REPLACE INTO effective_facts (lead_id, key, observation_id, confirmed)"
            " VALUES (?, ?, ?, ?)",
            (self.lead_id, key, observation_id, int(confirmed)),
        )
        append_event(
            self.db,
            self.context,
            EventType.fact_selected,
            FactSelected(
                key=key,
                observation_id=observation_id,
                value=json.loads(value_json),
                source=source,
                confirmed=confirmed,
            ),
            lead_id=self.lead_id,
        )
        self.moves_revision = True

    def raise_review(self, detail: BlockerDetail) -> None:
        open_blocker(
            self.db, self.context, self.lead_id, "underwriter_review", "underwriter", detail
        )

    def finish(self) -> None:
        """Recompute derived facts and reconcile conflicts with the validators, then move the revision once."""
        self._recompute_derived_facts()
        self._reconcile_conflicts()
        if self.moves_revision:
            self.db.execute(
                "UPDATE leads SET revision = COALESCE(revision, 0) + 1 WHERE lead_id = ?",
                (self.lead_id,),
            )

    def _recompute_derived_facts(self) -> None:
        """9.3 step 2: a derivation with its inputs present selects its value over any source but an underwriter's.

        The only derived facts are the roof and siding classes, both system-owned, which is why a
        derivation may outrank every source but the underwriter.
        """
        for derivation in self.rules.derivations:
            facts = effective_facts(self.db, self.lead_id)
            if any(name not in facts for name in derivation.inputs):
                continue
            current = facts.get(derivation.key)
            if current is not None and current.source == "underwriter":
                continue
            inputs: dict[str, JsonValue] = {
                name: facts[name].observation_id for name in derivation.inputs
            }
            if (
                current is not None
                and current.source == "derived"
                and current.evidence.get("inputs") == inputs
            ):
                continue
            value = derivation.compute({name: facts[name].value for name in derivation.inputs})
            evidence: dict[str, JsonValue] = {"derivation_id": derivation.id, "inputs": inputs}
            self.select(self.record(derivation.key, value, "derived", evidence, "accepted"))

    def _reconcile_conflicts(self) -> None:
        values = {key: fact.value for key, fact in effective_facts(self.db, self.lead_id).items()}
        holding = {c.identity: c for validator in self.rules.validators for c in validator(values)}
        for conflict in open_conflicts(self.db, self.lead_id):
            if conflict.identity not in holding:
                self.close_conflict(conflict, None)
        open_now = {c.identity for c in open_conflicts(self.db, self.lead_id)}
        confirmed = _confirmed_identities(self.db, self.lead_id)
        for identity, conflict in holding.items():
            if identity not in open_now and identity not in confirmed:
                append_event(
                    self.db,
                    self.context,
                    EventType.conflict_opened,
                    conflict.opened,
                    lead_id=self.lead_id,
                )

    def close_conflict(self, conflict: Conflict, observation_id: int | None) -> None:
        append_event(
            self.db,
            self.context,
            EventType.conflict_closed,
            ConflictClosed(
                validator=conflict.validator,
                fields=list(conflict.fields),
                values=conflict.values,
                observation_id=observation_id,
            ),
            lead_id=self.lead_id,
        )


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True)


def _conflict_events(
    db: sqlite3.Connection, lead_id: str
) -> list[tuple[bool, Conflict, int | None]]:
    """The lead's conflict events in order: (opened, conflict, observation id that closed it)."""
    found: list[tuple[bool, Conflict, int | None]] = []
    for event in read_events(db, lead_id=lead_id):
        payload = event.payload
        if isinstance(payload, ConflictOpened):
            opened = Conflict(
                payload.validator, tuple(payload.fields), payload.values, payload.question
            )
            found.append((True, opened, None))
        elif isinstance(payload, ConflictClosed):
            closed = Conflict(payload.validator, tuple(payload.fields), payload.values, "")
            found.append((False, closed, payload.observation_id))
    return found


def open_conflicts(db: sqlite3.Connection, lead_id: str) -> list[Conflict]:
    """The lead's open conflicts, oldest first, from its `conflict_opened` and `conflict_closed` events."""
    open_by_identity: dict[tuple[str, tuple[str, ...], str], Conflict] = {}
    for opened, conflict, _ in _conflict_events(db, lead_id):
        if opened:
            open_by_identity[conflict.identity] = conflict
        else:
            open_by_identity.pop(conflict.identity, None)
    return list(open_by_identity.values())


def _confirmed_identities(
    db: sqlite3.Connection, lead_id: str
) -> set[tuple[str, tuple[str, ...], str]]:
    """The conflicts closed by the reply or underwriter observation that confirmed their values; their validator is not to open them again."""
    return {
        conflict.identity
        for opened, conflict, observation_id in _conflict_events(db, lead_id)
        if not opened and observation_id is not None
    }


def effective_facts(db: sqlite3.Connection, lead_id: str) -> dict[str, Fact]:
    """The lead's effective fact per key."""
    rows = db.execute(
        "SELECT e.key, o.value_json, o.source, o.status, e.confirmed, o.evidence_json, o.id"
        " FROM effective_facts e JOIN observations o ON o.id = e.observation_id"
        " WHERE e.lead_id = ? ORDER BY e.key",
        (lead_id,),
    ).fetchall()
    return {
        row[0]: Fact(
            key=row[0],
            value=json.loads(row[1]),
            source=row[2],
            status=row[3],
            confirmed=bool(row[4]),
            evidence=json.loads(row[5]),
            observation_id=row[6],
        )
        for row in rows
    }


def usable_facts(db: sqlite3.Connection, lead_id: str) -> dict[str, Fact]:
    """The effective facts that are usable (9.6): accepted, and not part of an open conflict;
    a derived fact is usable when the inputs it recorded are."""
    in_conflict = {name for c in open_conflicts(db, lead_id) for name in c.fields}
    facts = effective_facts(db, lead_id)
    usable: dict[str, Fact] = {}

    def is_usable(key: str) -> bool:
        if key in usable:
            return True
        fact = facts[key]
        if fact.status != "accepted" or key in in_conflict:
            return False
        inputs = fact.evidence.get("inputs")
        if fact.source == "derived" and isinstance(inputs, dict):
            return all(name in facts and is_usable(name) for name in inputs)
        return True

    for key in facts:
        if is_usable(key):
            usable[key] = facts[key]
    return usable


def observe(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    key: str,
    value: JsonValue,
    source: Literal["submitted", "fetched", "assumed"],
    evidence: dict[str, JsonValue],
    rules: LedgerRules,
) -> None:
    """Record an accepted observation from the lead, a provider or an assumption.

    It becomes the effective fact when the key has none, or replaces an `assumed` value unless it is
    assumed itself; an underwriter value and any other existing value stay. The caller commits.
    """
    ledger = _Pass(db, context, lead_id, rules)
    observation_id = ledger.record(key, value, source, evidence, "accepted")
    current = effective_facts(db, lead_id).get(key)
    if current is None or (current.source == "assumed" and source != "assumed"):
        ledger.select(observation_id)
    ledger.finish()


def observe_submitted(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    fields: Mapping[str, JsonValue],
    rules: LedgerRules,
) -> None:
    """Record the lead's submitted fields as accepted observations, each the effective fact of its key.
    A null field is missing (9.2) and records nothing. The caller commits."""
    ledger = _Pass(db, context, lead_id, rules)
    for key, value in fields.items():
        if value is not None:
            ledger.select(ledger.record(key, value, "submitted", {}, "accepted"))
    ledger.finish()


def submitted_values(db: sqlite3.Connection, lead_id: str) -> dict[str, JsonValue]:
    """The values the lead was submitted with, by key."""
    rows = db.execute(
        "SELECT key, value_json FROM observations WHERE lead_id = ? AND source = 'submitted'",
        (lead_id,),
    )
    return {key: json.loads(value) for key, value in rows}


LateReplyCause = Literal["late_reply", "reply_after_terminal_status"]

# The reviews a late reply raises (rule 9): acknowledging one rejects that reply's pending values.
LATE_REPLY_CAUSES: tuple[LateReplyCause, ...] = get_args(LateReplyCause)

_LATE_REPLY_TEXT: dict[LateReplyCause, str] = {
    "late_reply": "A reply arrived after its round closed.",
    "reply_after_terminal_status": "A reply arrived after the lead reached its final status.",
}


def observe_reply(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    values: Sequence[ReplyValue],
    rules: LedgerRules,
) -> None:
    """Apply the values read from one reply to an open round by the source-authority rules of 7.3.
    The caller commits."""
    ledger = _Pass(db, context, lead_id, rules)
    changed = _changed_keys(ledger, values)
    for reply_value in values:
        _apply_reply_value(ledger, reply_value, changed)
    ledger.finish()


def observe_late_reply(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    values: Sequence[ReplyValue],
    rules: LedgerRules,
    *,
    intent_id: str,
    cause: LateReplyCause,
) -> None:
    """Rule 9: record the values of a reply that arrived after its round closed, or after the lead's
    final status (A.3), applied to nothing. The caller commits.

    Each value is recorded `pending_review` (a system-owned key's is rejected by rule 4), one review
    of `cause` naming `intent_id`, the request the reply answers, is raised and the revision moves,
    whatever the values.
    """
    ledger = _Pass(db, context, lead_id, rules)
    for reply_value in values:
        status: ObservationStatus = (
            "rejected" if reply_value.key in rules.system_owned_keys else "pending_review"
        )
        ledger.record(reply_value.key, reply_value.value, "reply", reply_value.evidence, status)
    ledger.raise_review(
        BlockerDetail(
            item_kind="review",
            cause=cause,
            resume_trigger="an underwriter acknowledges the late reply",
            intent_id=intent_id,
            text=_LATE_REPLY_TEXT[cause],
        )
    )
    ledger.moves_revision = True
    ledger.finish()


def _changed_keys(ledger: _Pass, values: Sequence[ReplyValue]) -> set[str]:
    """The keys the reply gives a value other than the one in effect; a system-owned field is never changed by a reply."""
    facts = effective_facts(ledger.db, ledger.lead_id)
    return {
        v.key
        for v in values
        if v.key not in ledger.rules.system_owned_keys
        and v.key in facts
        and _canonical(facts[v.key].value) != _canonical(v.value)
    }


def _apply_reply_value(ledger: _Pass, reply_value: ReplyValue, changed: set[str]) -> None:
    key, value, evidence = reply_value.key, reply_value.value, reply_value.evidence
    if key in ledger.rules.system_owned_keys:  # rule 4
        ledger.record(key, value, "reply", evidence, "rejected")
        return
    current = effective_facts(ledger.db, ledger.lead_id).get(key)
    if current is None:  # rule 2
        ledger.select(ledger.record(key, value, "reply", evidence, "accepted"))
    elif current.source == "assumed":  # rule 2
        observation_id = ledger.record(key, value, "reply", evidence, "accepted")
        restates = _canonical(current.value) == _canonical(value)
        ledger.select(
            observation_id,
            confirmed=restates and _close_confirmed_conflicts(ledger, key, observation_id, changed),
        )
    elif _canonical(current.value) == _canonical(value):  # rule 6
        observation_id = ledger.record(key, value, "reply", evidence, "accepted")
        if _close_confirmed_conflicts(ledger, key, observation_id, changed):
            ledger.select(current.observation_id, confirmed=True)
    else:  # rules 1, 3, 6 and 7: the existing value stays until the underwriter decides
        observation_id = ledger.record(key, value, "reply", evidence, "pending_review")
        ledger.raise_review(
            BlockerDetail(
                item_kind="observation",
                observation_id=observation_id,
                resume_trigger="an underwriter approves or rejects the value",
                text=f"A reply gives {key} as {json.dumps(value)}; the effective value is {json.dumps(current.value)}.",
            )
        )


def _close_confirmed_conflicts(
    ledger: _Pass, key: str, observation_id: int, changed: set[str]
) -> bool:
    """Rule 6: close the open conflicts the restated key is part of, unless the same reply changes
    another field of the conflict (that value follows rule 3 and the conflict stays open).
    True when a conflict closed."""
    closing = [
        c
        for c in open_conflicts(ledger.db, ledger.lead_id)
        if key in c.fields and changed.isdisjoint(c.fields)
    ]
    for conflict in closing:
        ledger.close_conflict(conflict, observation_id)
    return bool(closing)


def _observation_blocker_id(
    db: sqlite3.Connection, lead_id: str, observation_id: int
) -> int | None:
    for blocker in open_blockers(db, lead_id):
        if (
            blocker.detail.item_kind == "observation"
            and blocker.detail.observation_id == observation_id
        ):
            return blocker.id
    return None


def _awaiting_blocker_id(db: sqlite3.Connection, lead_id: str, observation_id: int) -> int:
    blocker_id = _observation_blocker_id(db, lead_id, observation_id)
    if blocker_id is None:
        raise ValueError(f"observation {observation_id} is not awaiting an underwriter decision")
    return blocker_id


def _pending_observation_lead(db: sqlite3.Connection, observation_id: int) -> str:
    row = db.execute(
        "SELECT lead_id, status FROM observations WHERE id = ?", (observation_id,)
    ).fetchone()
    if row is None or row[1] != "pending_review":
        raise ValueError(f"observation {observation_id} is not awaiting an underwriter decision")
    return str(row[0])


def approve_observation(
    db: sqlite3.Connection, context: EventContext, observation_id: int, rules: LedgerRules
) -> None:
    """Rule 10: a pending observation becomes the effective fact and its review closes.

    Raises ValueError for an observation that has no open observation review. The caller commits.
    """
    lead_id = _pending_observation_lead(db, observation_id)
    blocker_id = _awaiting_blocker_id(db, lead_id, observation_id)
    db.execute("UPDATE observations SET status = 'accepted' WHERE id = ?", (observation_id,))
    close_blocker(db, context, blocker_id)
    ledger = _Pass(db, context, lead_id, rules)
    ledger.select(observation_id)
    ledger.finish()


def reject_observation(db: sqlite3.Connection, context: EventContext, observation_id: int) -> None:
    """Rule 10: a pending observation is marked rejected, its review closes and the existing value stays.

    Raises ValueError for an observation that has no open observation review. The caller commits.
    """
    lead_id = _pending_observation_lead(db, observation_id)
    blocker_id = _awaiting_blocker_id(db, lead_id, observation_id)
    db.execute("UPDATE observations SET status = 'rejected' WHERE id = ?", (observation_id,))
    close_blocker(db, context, blocker_id)


def resolve_fact(
    db: sqlite3.Connection,
    context: EventContext,
    lead_id: str,
    key: str,
    value: JsonValue,
    reason: str,
    rules: LedgerRules,
) -> int:
    """Rule 10 and rule 1: record an underwriter observation, which becomes the effective fact, and return the id of its `fact_observed` event.

    No conflict on its key stays open, even one the value trips: the ruling closes it, and a validator
    does not open it again on the same values. A later change to the other field of a pair opens one
    again. It rejects the pending observations on its key. The caller commits.
    """
    ledger = _Pass(db, context, lead_id, rules)
    observation_id = ledger.record(key, value, "underwriter", {"reason": reason}, "accepted")
    pending = db.execute(
        "SELECT id FROM observations WHERE lead_id = ? AND key = ? AND status = 'pending_review'",
        (lead_id, key),
    ).fetchall()
    for (pending_id,) in pending:
        db.execute("UPDATE observations SET status = 'rejected' WHERE id = ?", (pending_id,))
        blocker_id = _observation_blocker_id(db, lead_id, pending_id)
        if blocker_id is not None:
            close_blocker(db, context, blocker_id)
    ledger.select(observation_id)
    ledger.finish()
    for conflict in open_conflicts(db, lead_id):
        if key in conflict.fields:
            ledger.close_conflict(conflict, observation_id)
    (event_id,) = db.execute(
        "SELECT event_id FROM observations WHERE id = ?", (observation_id,)
    ).fetchone()
    return int(event_id)


def reject_late_reply_values(db: sqlite3.Connection, blocker_id: int) -> None:
    """Rule 9: acknowledging a late reply's review marks that reply's `pending_review` values rejected.

    A reply records its values and then opens its review, so its values are the observations
    recorded after the lead's previous event of any other type and before the review opened. A value
    already settled, and the values of another reply, stay as they are. Raises ValueError for a
    blocker that is not a late reply's review. The caller commits.
    """
    row = db.execute(
        "SELECT lead_id, kind, detail_json, opened_event_id FROM blockers WHERE id = ?",
        (blocker_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"blocker {blocker_id} is not the review of a late reply")
    lead_id, kind, detail_json, opened_event_id = row
    detail = BlockerDetail.model_validate_json(detail_json)
    if kind != "underwriter_review" or detail.cause not in LATE_REPLY_CAUSES:
        raise ValueError(f"blocker {blocker_id} is not the review of a late reply")
    db.execute(
        "UPDATE observations SET status = 'rejected'"
        " WHERE lead_id = ? AND status = 'pending_review' AND event_id < ? AND event_id >"
        " COALESCE((SELECT MAX(id) FROM events WHERE lead_id = ? AND id < ? AND type != ?), 0)",
        (lead_id, opened_event_id, lead_id, opened_event_id, EventType.fact_observed.value),
    )
