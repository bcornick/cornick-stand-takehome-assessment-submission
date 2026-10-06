# ABOUTME: The eval runner (section 13): `python -m evals.run --suite seed42|replies|chat [--control NAME] [--hypothesis TEXT]`; the seed42 suite runs seed 42's first pass in replay mode, grades it at the settle point, plays each label's underwriter actions and grades the state after them, runs the fault runs, and appends one `run` row to the results log.
# ABOUTME: Every run opens its own empty database; the leadgen and mailbox services are the eval ones named by LEADGEN_URL and MAILBOX_URL, and a failed health or bootstrap check writes an `invalid` row, never a score.
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import yaml
from pydantic import JsonValue

import uwh
from evals.cases import (
    CHAT_DIR,
    SKILLS_DIR,
    ChatCase,
    ReplyCase,
    SkillResult,
    load_chat_cases,
    load_reply_cases,
    run_skill_cases,
)
from evals.controls import Control, applied, mailbox_client
from evals.graders import answer_key
from evals.graders.chat import TurnEvidence, chat
from evals.graders.delivery import asks, coverage, forbidden_asks, one_open_request, packet_fidelity
from evals.graders.evidence import Evidence, Expectations, Result
from evals.graders.plan import rule_trace
from evals.graders.reply import reply_facts, reply_reading
from evals.graders.safety import FaultRun, critical_errors, send_safety
from uwh.api.runtime import Runtime, open_runtime
from uwh.chat.skill import run_turn
from uwh.runtime.bootstrap import TIMEOUT_SECONDS, EnvironmentInvalid, check_services
from uwh.runtime.commands import CommandResult, submit_command
from uwh.runtime.event_types import REQUEST_KINDS, EventType, FaultInjected, ModelCalled
from uwh.runtime.events import read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.hashing import file_entries, hash_json, source_files
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.modes import RecordingMiss
from uwh.runtime.runs import current_run, pass_context, run_passes
from uwh.settings import Settings
from uwh.skills import SKILLS
from uwh.skills.digest import chat_digest, skill_digest
from uwh.skills.manifest import load_manifest

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
RESULTS_PATH = EVALS_DIR / "results.jsonl"
SEED = 42
LABELS_DIR = EVALS_DIR / "labels" / f"seed{SEED}"
REPLY_LABELS_DIR = EVALS_DIR / "labels" / "replies"
# The lead the fault runs and nothing else use (13.1): it reaches a sent request with one ask round.
FAULT_LEAD = "LEAD-00000042-008"
# The faults of each fault run, in the order the send primitive records them.
FAULT_RUNS = (("fail_after_acceptance",), ("fail_after_acceptance", "empty_while_in_flight"))

Phase = str
FIRST_PASS, AFTER_ACTIONS = "first_pass", "after_actions"
Grader = Callable[[Evidence, Expectations], Result]


def _stands_key(ev: Evidence, expected: Expectations) -> Result:
    return answer_key.stands_key(ev.db, ev.registry, SEED)


# Each grader of section 13.3 that runs on the state of a phase, with the phases it runs in. Stand's key
# judges the first pass: the key's records are of the first pass.
GRADERS: tuple[tuple[str, Grader, tuple[Phase, ...]], ...] = (
    ("Coverage", coverage, (FIRST_PASS, AFTER_ACTIONS)),
    ("One open request", one_open_request, (FIRST_PASS, AFTER_ACTIONS)),
    ("Asks", asks, (FIRST_PASS, AFTER_ACTIONS)),
    ("Forbidden asks", forbidden_asks, (FIRST_PASS, AFTER_ACTIONS)),
    ("Rule trace", rule_trace, (FIRST_PASS, AFTER_ACTIONS)),
    ("Packet fidelity", packet_fidelity, (FIRST_PASS, AFTER_ACTIONS)),
    ("Reply facts", reply_facts, (AFTER_ACTIONS,)),
    ("Stand's key", _stands_key, (FIRST_PASS,)),
)


@dataclass
class Score:
    """A grader's result over the phases: it passed when no phase failed, and `phase` names the first that did."""

    passed: bool = True
    phase: Phase | None = None
    failures: list[str] = field(default_factory=list)
    measures: dict[str, JsonValue] = field(default_factory=dict)

    def add(self, phase: Phase, result: Result) -> None:
        if result.failures and self.passed:
            self.passed, self.phase = False, phase
        self.failures += [f"{phase}: {message}" for message in result.failures]
        self.measures |= {k: v for k, v in result.measures.items() if k not in self.measures}

    def row(self) -> dict[str, JsonValue]:
        return {
            "passed": self.passed,
            "phase": self.phase,
            "failures": [*self.failures],
            "measures": self.measures,
        }


def load_labels() -> dict[str, dict[str, Any]]:
    """The seed-42 labels by lead id."""
    return {
        path.stem: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(LABELS_DIR.glob("LEAD-*.yaml"))
    }


def _evidence(
    runtime: Runtime, db_conn: sqlite3.Connection, earlier: frozenset[str] = frozenset()
) -> Evidence:
    """What the graders read of the run now: the database and each lead's messages in the mailbox."""
    mail = {
        lead_id: runtime.env.mailbox.list_for_lead(lead_id)
        for (lead_id,) in db_conn.execute("SELECT lead_id FROM leads ORDER BY lead_id")
    }
    return Evidence(db_conn, runtime.env.registry, mail, earlier)


def _draft_item(db: sqlite3.Connection, lead_id: str, kind: str) -> tuple[int, str, str] | None:
    """The open item that reviews the lead's draft of `kind`, its draft's id and its payload hash."""
    for item_id, intent_id, payload_hash in db.execute(
        "SELECT b.id, i.id, i.payload_hash FROM blockers b"
        " JOIN intents i ON i.id = json_extract(b.detail_json, '$.intent_id')"
        " WHERE b.lead_id = ? AND b.closed_event_id IS NULL AND i.kind = ? AND i.state = 'draft'",
        (lead_id, kind),
    ):
        return int(item_id), str(intent_id), str(payload_hash)
    return None


def _deliver(
    runtime: Runtime, db: sqlite3.Connection, lead_id: str, round_: int, body: str
) -> CommandResult | None:
    """Deliver `body` as the producer's reply to the lead's sent request of the round; None when the
    lead has no such request."""
    row = db.execute(
        "SELECT id FROM intents WHERE lead_id = ? AND round = ? AND state = 'sent'"
        f" AND kind IN ({', '.join('?' for _ in REQUEST_KINDS)})",
        (lead_id, round_, *REQUEST_KINDS),
    ).fetchone()
    if row is None:
        return None
    return runtime.submit_as_inbound(
        db, "deliver_reply", {"lead_id": lead_id, "intent_id": row[0], "body": body}
    )


def _play(
    runtime: Runtime, db: sqlite3.Connection, lead_id: str, actions: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Submit the label's underwriter actions for the lead through the app's commands; each action
    that cannot be played or is refused is a failure."""
    failures: list[str] = []
    for action in actions:
        name = action["action"]
        if name == "approve":
            found = _draft_item(db, lead_id, action["item"])
            if found is None:
                failures.append(f"{lead_id}: no {action['item']} waits for approval")
                continue
            item_id, _, payload_hash = found
            result, _ = runtime.submit_as_underwriter(
                db,
                "approve",
                {"item_id": item_id, "artifact_hash": payload_hash, "reason": action["reason"]},
            )
        elif name == "record_ruling":
            result, _ = runtime.submit_as_underwriter(
                db,
                "record_ruling",
                {
                    "lead_id": lead_id,
                    "choice_id": action["choice_id"],
                    "option": action["option"],
                    "reason": action["reason"],
                },
            )
        else:  # deliver_reply
            (round_,) = re.findall(r"round (\d+) request", action["intent"])
            body = (ROOT / action["fixture"]).read_text(encoding="utf-8")
            delivered = _deliver(runtime, db, lead_id, int(round_), body)
            if delivered is None:
                failures.append(f"{lead_id}: no sent {action['intent']}")
                continue
            result = delivered
        if not result.accepted:
            failures.append(f"{lead_id}: {name} was refused: {result.reason}")
    return failures


def _expectations(labels: Mapping[str, Any], phase: Phase) -> Expectations:
    """The labels' expectations for a phase, by lead: the lead's `first_pass`, or its `after_actions`
    where the label has one."""
    return {lead: label[phase] for lead, label in labels.items() if label[phase] is not None}


def _measurements(db: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """Tokens and wall time per lead, from the events of the lead so far."""
    per_lead: dict[str, dict[str, float]] = {}
    for (lead_id,) in db.execute("SELECT lead_id FROM leads ORDER BY lead_id"):
        events = read_events(db, lead_id=lead_id)
        called = [e.payload for e in events if isinstance(e.payload, ModelCalled)]
        per_lead[lead_id] = {
            "tokens_in": sum(c.tokens_in for c in called),
            "tokens_out": sum(c.tokens_out for c in called),
            "wall_seconds": round((events[-1].real_ts - events[0].real_ts).total_seconds(), 3),
        }
    return per_lead


def _reference_run(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox: MailboxClient,
    labels: Mapping[str, Any],
    scores: dict[str, Score],
) -> tuple[list[str], dict[str, dict[str, float]]]:
    """Run seed 42, grade the settle point, play the actions, grade again. Returns the critical
    errors and the per-lead measurements."""
    critical: list[str] = []
    with open_runtime(settings, leadgen, mailbox) as runtime, runtime.database() as db:
        result, first_pass = runtime.submit_as_underwriter(db, "start_run", {"seed": SEED})
        assert result.accepted and first_pass is not None, result.reason
        first_pass.future.result()

        def grade(phase: Phase, ev: Evidence, extra: Mapping[str, list[str]] | None = None) -> None:
            for name, grader, phases in GRADERS:
                if phase in phases:
                    outcome = grader(ev, _expectations(labels, phase))
                    outcome.failures += (extra or {}).get(name, [])
                    scores.setdefault(name, Score()).add(phase, outcome)
            critical.extend(critical_errors(ev))

        settled = _evidence(runtime, db)
        grade(FIRST_PASS, settled)

        earlier = frozenset(
            m["metadata"]["intent_id"] for held in settled.mail.values() for m in held
        )
        played = [
            failure
            for lead_id, label in labels.items()
            for failure in _play(runtime, db, lead_id, label["underwriter_actions"])
        ]
        grade(AFTER_ACTIONS, _evidence(runtime, db, earlier), {"Coverage": played})
        return critical, _measurements(db)


def _fault_run(
    settings: Settings,
    leadgen: LeadgenClient,
    mailbox_http: httpx2.Client,
    control: Control | None,
    faults: tuple[str, ...],
) -> tuple[FaultRun, list[str]]:
    """One lead's first pass with faults injected into the mailbox client (13.1), apart from the
    reference run. Returns what the run left and its critical errors."""
    plan = FaultPlan(
        fail_after_acceptance="fail_after_acceptance" in faults,
        empty_while_in_flight="empty_while_in_flight" in faults,
    )
    with open_runtime(settings, leadgen, mailbox_client(control, mailbox_http, plan)) as runtime:
        with runtime.database() as db:
            submit_command(db, runtime.env, "underwriter", "start_run", {"seed": SEED})
            run = current_run(db)
            assert run is not None
            run_passes(
                settings.db_path,
                pass_context(run, runtime.env),
                [FAULT_LEAD],
                runtime.env.steps,
                runtime.env.mailbox,
            )
            injected = [
                e.payload.fault
                for e in read_events(db)
                if e.type == EventType.fault_injected and isinstance(e.payload, FaultInjected)
            ]
            held = MailboxClient(mailbox_http).list_for_lead(FAULT_LEAD)
            ev = Evidence(db, runtime.env.registry, {FAULT_LEAD: held})
            return FaultRun(faults, injected, held), critical_errors(ev)


def _evaluator_hash() -> str:
    return hash_json(
        file_entries(EVALS_DIR, [p for p in source_files(EVALS_DIR) if p.name != RESULTS_PATH.name])
    )


def _case_set_id(labels_dir: Path | None, case_folders: Iterable[Path]) -> str:
    """The hash of the labels, when the suite has them, and of the case folders."""
    return hash_json(
        {
            "labels": None
            if labels_dir is None
            else file_entries(labels_dir, source_files(labels_dir)),
            "cases": {
                folder.parent.name: file_entries(folder, source_files(folder))
                for folder in case_folders
            },
        }
    )


def _skill_result(folder: Path, outcome: SkillResult) -> dict[str, JsonValue]:
    """The cases of the skill in `folder` against its manifest threshold, as `skill_results` of the
    run row holds them."""
    threshold = load_manifest(folder).pass_threshold
    assert threshold is not None, f"{folder.name} has cases and no pass_threshold"
    for failure in outcome.failures:
        print(f"case failed: {failure}", file=sys.stderr)
    return {
        "cases_passed": outcome.cases_passed,
        "cases_total": outcome.cases_total,
        "passed": outcome.passed(threshold),
    }


def _skill_results() -> dict[str, JsonValue]:
    """`skill_results` of a seed42 run row: evaluate_playbook's table of cases. read_reply's cases are
    the reply suite's."""
    return {"evaluate_playbook": _skill_result(SKILLS_DIR / "evaluate_playbook", run_skill_cases())}


def _tokens(measurements: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    return {key: sum(m[f"tokens_{key}"] for m in measurements.values()) for key in ("in", "out")}


def _evaluate(
    suite: str,
    case_set_id: str,
    settings: Settings,
    leadgen_http: httpx2.Client,
    mailbox_http: httpx2.Client,
    control: Control | None,
    hypothesis: str | None,
    score: Callable[[Callable[[str], Settings], LeadgenClient], dict[str, Any]],
) -> dict[str, Any]:
    """The `run` row of a suite. The row is `invalid`, with no scores, when a service fails its health
    or bootstrap check; otherwise `score` is given a function that makes the settings of a database of
    its own, and the leadgen client, and returns the scored fields of the row."""
    leadgen = LeadgenClient(leadgen_http)
    row: dict[str, Any] = {
        "kind": "run",
        "run_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(UTC).isoformat(),
        "suite": suite,
        "control": None if control is None else control.value,
        "mode": settings.run_mode,
        "jev": settings.typesafe_api_key is not None,
        "commit": settings.git_commit,
        "evaluator_hash": _evaluator_hash(),
        "case_set_id": case_set_id,
        "skill_digests": {
            skill: skill_digest(
                Path(uwh.__file__).parent,
                skill,
                settings.model_id if load_manifest(SKILLS_DIR / skill).model_skill else None,
            )
            for skill in SKILLS
        },
        "hypothesis": hypothesis,
    }
    try:
        check_services(leadgen, MailboxClient(mailbox_http), SEED)
    except EnvironmentInvalid as error:
        return row | {"status": "invalid", "reason": str(error)}

    with tempfile.TemporaryDirectory(prefix="uwh-eval-") as scratch, applied(control):

        def per_run(name: str) -> Settings:
            return replace(settings, db_path=str(Path(scratch) / f"{name}.db"), seed=SEED)

        return row | {"status": "scored"} | score(per_run, leadgen)


def evaluate_seed42(
    settings: Settings,
    leadgen_http: httpx2.Client,
    mailbox_http: httpx2.Client,
    *,
    control: Control | None,
    hypothesis: str | None,
) -> dict[str, Any]:
    """Run the seed-42 suite against the services behind the two clients and return the `run` row."""
    labels = load_labels()
    scores: dict[str, Score] = {}

    def score(per_run: Callable[[str], Settings], leadgen: LeadgenClient) -> dict[str, Any]:
        critical, measurements = _reference_run(
            per_run("reference"),
            leadgen,
            mailbox_client(control, mailbox_http),
            labels,
            scores,
        )
        fault_runs = []
        for number, faults in enumerate(FAULT_RUNS):
            fault_run, errors = _fault_run(
                per_run(f"fault-{number}"), leadgen, mailbox_http, control, faults
            )
            fault_runs.append(fault_run)
            critical += errors
        scores["Send safety"] = Score()
        scores["Send safety"].add(FIRST_PASS, send_safety(fault_runs))
        return {
            "scores": {name: score.row() for name, score in scores.items()},
            "critical_errors": [*dict.fromkeys(critical)],
            "skill_results": _skill_results(),
            "tokens": _tokens(measurements),
            "cost_usd": 0.0,  # a replay makes no billed call
            "measurements": {"per_lead": measurements},
        }

    return _evaluate(
        "seed42",
        _case_set_id(LABELS_DIR, [SKILLS_DIR / "evaluate_playbook" / "cases"]),
        settings,
        leadgen_http,
        mailbox_http,
        control,
        hypothesis,
        score,
    )


def read_replies(
    runtime: Runtime, db: sqlite3.Connection, cases: Sequence[ReplyCase]
) -> tuple[Evidence, list[str]]:
    """Run seed 42's first pass, deliver each case's reply to its lead's first request and return the
    evidence after, with a message for each delivery that was not accepted."""
    result, first_pass = runtime.submit_as_underwriter(db, "start_run", {"seed": SEED})
    assert result.accepted and first_pass is not None, result.reason
    first_pass.future.result()
    earlier = frozenset(
        m["metadata"]["intent_id"] for held in _evidence(runtime, db).mail.values() for m in held
    )
    refused: list[str] = []
    for case in cases:
        delivery = _deliver(runtime, db, case.lead, 1, case.body)
        if delivery is None:
            refused.append(f"{case.lead}: no sent first request")
        elif not delivery.accepted:
            refused.append(f"{case.lead}: the reply was refused: {delivery.reason}")
    return _evidence(runtime, db, earlier), refused


def evaluate_replies(
    settings: Settings,
    leadgen_http: httpx2.Client,
    mailbox_http: httpx2.Client,
    *,
    control: Control | None,
    hypothesis: str | None,
) -> dict[str, Any]:
    """Run the reply suite (13.2): deliver every fixture reply of read_reply's cases, held ones
    included, to its lead's first request in a seed-42 run, and grade the readings. In replay the
    readings come from the recordings."""
    cases = load_reply_cases()

    def score(per_run: Callable[[str], Settings], leadgen: LeadgenClient) -> dict[str, Any]:
        with (
            open_runtime(
                per_run("replies"), leadgen, mailbox_client(control, mailbox_http)
            ) as runtime,
            runtime.database() as db,
        ):
            ev, refused = read_replies(runtime, db, cases)
            by_case = {
                c.lead: reply_reading(ev, {c.lead: c.label}).failures
                + [r for r in refused if r.startswith(c.lead)]
                for c in cases
            }
            outcome = Score()
            outcome.add(
                FIRST_PASS,
                Result(
                    [f for failures in by_case.values() for f in failures],
                    reply_reading(ev, {}).measures,
                ),
            )
            measurements = _measurements(db)
            critical = critical_errors(ev)
        return {
            "scores": {"Reply reading": outcome.row()},
            "critical_errors": [*dict.fromkeys(critical)],
            "skill_results": {
                "read_reply": _skill_result(
                    SKILLS_DIR / "read_reply",
                    SkillResult(
                        sum(not failures for failures in by_case.values()),
                        len(cases),
                        outcome.failures,
                    ),
                )
            },
            "tokens": _tokens(measurements),
            "cost_usd": 0.0,  # a replay makes no billed call
            "measurements": {"per_lead": measurements},
        }

    return _evaluate(
        "replies",
        _case_set_id(REPLY_LABELS_DIR, [SKILLS_DIR / "read_reply" / "cases"]),
        settings,
        leadgen_http,
        mailbox_http,
        control,
        hypothesis,
        score,
    )


def play_chat_cases(
    runtime: Runtime, db: sqlite3.Connection, cases: Sequence[ChatCase]
) -> tuple[list[TurnEvidence], list[str]]:
    """Start seed 42's run, leave it at its start (no first pass, so the event ids are the same on
    every run) and put each case's messages to the assistant in order. Returns the evidence of each
    turn, and a message for each turn that had no recording."""
    result = submit_command(db, runtime.env, "underwriter", "start_run", {"seed": SEED})
    assert result.accepted, result.reason
    turns: list[TurnEvidence] = []
    misses: list[str] = []
    for case in cases:
        for message, expect in case.turns:
            before = db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
            try:
                turn = run_turn(db, runtime.env, message, case.lead)
            except RecordingMiss as miss:
                misses.append(f"{case.name} / {message!r}: {miss}")
                continue
            turns.append(
                TurnEvidence(
                    case.name,
                    message,
                    expect,
                    turn.cited_event_ids,
                    turn.proposal_id,
                    [e for e in read_events(db) if e.id > before],
                )
            )
    return turns, misses


def evaluate_chat(
    settings: Settings,
    leadgen_http: httpx2.Client,
    mailbox_http: httpx2.Client,
    *,
    control: Control | None,
    hypothesis: str | None,
) -> dict[str, Any]:
    """Run the chat suite (13.3): put the messages of the chat cases to the assistant against seed
    42's run at its start and grade what each turn did. In replay the model's replies come from the
    recordings."""
    cases = load_chat_cases()

    def score(per_run: Callable[[str], Settings], leadgen: LeadgenClient) -> dict[str, Any]:
        with (
            open_runtime(
                per_run("chat"), leadgen, mailbox_client(control, mailbox_http)
            ) as runtime,
            runtime.database() as db,
        ):
            turns, misses = play_chat_cases(runtime, db, cases)
            measurements = _measurements(db)
        by_case = {
            case.name: chat([t for t in turns if t.case == case.name]).failures
            + [m for m in misses if m.startswith(f"{case.name} / ")]
            for case in cases
        }
        outcome = Score()
        outcome.add(FIRST_PASS, Result([f for failures in by_case.values() for f in failures]))
        return {
            "scores": {"Chat": outcome.row()},
            "critical_errors": [],
            "skill_results": {
                "chat": _skill_result(
                    CHAT_DIR,
                    SkillResult(
                        sum(not failures for failures in by_case.values()),
                        len(cases),
                        outcome.failures,
                    ),
                )
            },
            "tokens": _tokens(measurements),
            "cost_usd": 0.0,  # a replay makes no billed call
            "measurements": {"per_lead": measurements},
        }

    row = _evaluate(
        "chat",
        _case_set_id(None, [CHAT_DIR / "cases"]),
        settings,
        leadgen_http,
        mailbox_http,
        control,
        hypothesis,
        score,
    )
    # The chat panel is not one of the SKILLS; its own digest says which prompt and tools the row ran.
    row["skill_digests"]["chat"] = chat_digest(CHAT_DIR.parent, settings.model_id)
    return row


def failed(row: Mapping[str, Any]) -> list[str]:
    """What fails the run: an invalid environment, a grader, a critical error or a skill's cases."""
    if row["status"] != "scored":
        return [f"the run is invalid: {row['reason']}"]
    return (
        [f"grader {name} failed" for name, score in row["scores"].items() if not score["passed"]]
        + [f"critical error: {error}" for error in row["critical_errors"]]
        + [
            f"skill {name} failed its cases"
            for name, result in row["skill_results"].items()
            if not result["passed"]
        ]
    )


SUITES = {"seed42": evaluate_seed42, "replies": evaluate_replies, "chat": evaluate_chat}


@contextmanager
def _clients(settings: Settings) -> Iterator[tuple[httpx2.Client, httpx2.Client]]:
    with (
        httpx2.Client(base_url=settings.leadgen_url, timeout=TIMEOUT_SECONDS) as leadgen,
        httpx2.Client(base_url=settings.mailbox_url, timeout=TIMEOUT_SECONDS) as mailbox,
    ):
        yield leadgen, mailbox


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("--suite", choices=sorted(SUITES), default="seed42")
    parser.add_argument("--control", choices=[c.value for c in Control])
    parser.add_argument("--hypothesis")
    parser.add_argument(
        "--jev",
        action="store_true",
        help="classify replies with Jev first, from recordings/jev; needs TYPESAFE_API_KEY set",
    )
    args = parser.parse_args(argv)
    # Each run opens a database of its own, so the path the settings need is a placeholder.
    settings = Settings.load({**os.environ, "UWH_DB": "per run"})
    if args.jev and settings.typesafe_api_key is None:
        parser.error("--jev needs TYPESAFE_API_KEY set; the replay reads recordings/jev with it")
    if not args.jev:
        settings = replace(settings, typesafe_api_key=None)
    if settings.run_mode != "replay":
        parser.error("the suites replay recordings: set RUN_MODE=replay")
    if settings.git_commit == "unknown":
        parser.error("the build has no commit: run through `make eval`")
    with _clients(settings) as (leadgen_http, mailbox_http):
        row = SUITES[args.suite](
            settings,
            leadgen_http,
            mailbox_http,
            control=None if args.control is None else Control(args.control),
            hypothesis=args.hypothesis,
        )
    with RESULTS_PATH.open("a", encoding="utf-8") as log:
        log.write(json.dumps(row) + "\n")
    problems = failed(row)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
