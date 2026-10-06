# ABOUTME: The eval runner (section 13): `python -m evals.run --suite seed42 [--control NAME] [--hypothesis TEXT]` runs seed 42's first pass in replay mode, grades it at the settle point, plays each label's underwriter actions and grades the state after them, runs the fault runs, and appends one `run` row to the results log.
# ABOUTME: Every run opens its own empty database; the leadgen and mailbox services are the eval ones named by LEADGEN_URL and MAILBOX_URL, and a failed health or bootstrap check writes an `invalid` row, never a score.
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import yaml
from pydantic import JsonValue

import uwh
from evals.cases import SKILLS_DIR, OBSERVERS, run_skill_cases
from evals.controls import Control, applied, mailbox_client
from evals.graders import answer_key
from evals.graders.delivery import asks, coverage, forbidden_asks, one_open_request, packet_fidelity
from evals.graders.evidence import Evidence, Expectations, Result
from evals.graders.plan import escalation, field_resolution, rule_trace
from evals.graders.safety import (
    FaultRun,
    Probe,
    approval_binding,
    critical_errors,
    key_isolation,
    policy,
    send_safety,
)
from uwh.api.runtime import Runtime, open_runtime
from uwh.rules.registry import Registry, load_registry
from uwh.runtime.bootstrap import TIMEOUT_SECONDS, EnvironmentInvalid, check_services
from uwh.runtime.commands import submit_command
from uwh.runtime.event_types import REQUEST_KINDS, EventType, FaultInjected, ModelCalled
from uwh.runtime.events import read_events
from uwh.runtime.faults import FaultPlan
from uwh.runtime.hashing import file_entries, hash_json, source_files
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import current_run, pass_context, run_passes
from uwh.settings import Settings
from uwh.skills import SKILLS
from uwh.skills.digest import skill_digest
from uwh.skills.manifest import load_manifest

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
RESULTS_PATH = EVALS_DIR / "results.jsonl"
SEED = 42
LABELS_DIR = EVALS_DIR / "labels" / f"seed{SEED}"
# The lead the fault runs and nothing else use (13.1): it reaches a sent request with one ask round.
FAULT_LEAD = "LEAD-00000042-008"
# The faults of each fault run, in the order the send primitive records them.
FAULT_RUNS = (("fail_after_acceptance",), ("fail_after_acceptance", "empty_while_in_flight"))

Phase = str
FIRST_PASS, AFTER_ACTIONS = "first_pass", "after_actions"
Grader = Callable[[Evidence, Expectations], Result]


def _stands_key(ev: Evidence, expected: Expectations) -> Result:
    return answer_key.stands_key(ev.db, ev.registry, SEED)


# Each grader of section 13.3 that runs on the state of a phase, with the phases it runs in. Field
# resolution and Stand's key judge the first pass: the facts the replies add change the triage and the
# key's records are of the first pass.
GRADERS: tuple[tuple[str, Grader, tuple[Phase, ...]], ...] = (
    ("Coverage", coverage, (FIRST_PASS, AFTER_ACTIONS)),
    ("One open request", one_open_request, (FIRST_PASS, AFTER_ACTIONS)),
    ("Asks", asks, (FIRST_PASS, AFTER_ACTIONS)),
    ("Forbidden asks", forbidden_asks, (FIRST_PASS, AFTER_ACTIONS)),
    ("Rule trace", rule_trace, (FIRST_PASS, AFTER_ACTIONS)),
    ("Packet fidelity", packet_fidelity, (FIRST_PASS, AFTER_ACTIONS)),
    ("Field resolution", field_resolution, (FIRST_PASS,)),
    ("Escalation", escalation, (FIRST_PASS, AFTER_ACTIONS)),
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
        for path in sorted(LABELS_DIR.glob("*.yaml"))
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


def _probe(
    runtime: Runtime, db: sqlite3.Connection, labels: Mapping[str, Any]
) -> tuple[Probe | None, Probe | None]:
    """Submit an approval with a stale hash, then one by the assistant, for the first draft a label's
    actions approve; both must be refused. Returns the two probes, or None where no draft waited."""
    for lead_id, label in labels.items():
        for action in label["underwriter_actions"]:
            found = action["action"] == "approve" and _draft_item(db, lead_id, action["item"])
            if not found:
                continue
            item_id, intent_id, payload_hash = found
            before = len(runtime.env.mailbox.list_for_lead(lead_id))
            stale, _ = runtime.submit_as_underwriter(
                db, "approve", {"item_id": item_id, "artifact_hash": "stale", "reason": "probe"}
            )
            assistant = submit_command(
                db,
                runtime.env,
                "assistant",
                "approve",
                {"item_id": item_id, "artifact_hash": payload_hash, "reason": "probe"},
            )
            return (
                Probe(lead_id, intent_id, stale.event_id, before),
                Probe(lead_id, intent_id, assistant.event_id, before),
            )
    return None, None


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
            row = db.execute(
                "SELECT id FROM intents WHERE lead_id = ? AND round = ? AND state = 'sent'"
                f" AND kind IN ({', '.join('?' for _ in REQUEST_KINDS)})",
                (lead_id, int(round_), *REQUEST_KINDS),
            ).fetchone()
            if row is None:
                failures.append(f"{lead_id}: no sent {action['intent']}")
                continue
            body = (ROOT / action["fixture"]).read_text(encoding="utf-8")
            result = runtime.submit_as_inbound(
                db, "deliver_reply", {"lead_id": lead_id, "intent_id": row[0], "body": body}
            )
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
        stale, assistant = _probe(runtime, db, labels)
        probed = _evidence(runtime, db)
        scores.setdefault("Approval binding", Score()).add(
            FIRST_PASS, approval_binding(probed, stale)
        )
        scores.setdefault("Policy", Score()).add(FIRST_PASS, policy(probed, assistant))

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


def _case_set_id() -> str:
    return hash_json(
        {
            "labels": file_entries(LABELS_DIR, source_files(LABELS_DIR)),
            "cases": {
                skill: file_entries(
                    SKILLS_DIR / skill / "cases", source_files(SKILLS_DIR / skill / "cases")
                )
                for skill in SKILLS
            },
        }
    )


def _skill_results(registry: Registry) -> dict[str, JsonValue]:
    """`skill_results` of the run row: each skill's cases against its manifest threshold. A skill with
    no table of cases here (read_reply's are the reply suite's) has no result."""
    results: dict[str, JsonValue] = {}
    for skill in OBSERVERS:
        outcome = run_skill_cases(skill, registry)
        results[skill] = {
            "cases_passed": outcome.cases_passed,
            "cases_total": outcome.cases_total,
            "passed": outcome.passed(load_manifest(SKILLS_DIR / skill).pass_threshold),
        }
        for failure in outcome.failures:
            print(f"case failed: {failure}", file=sys.stderr)
    return results


def evaluate_seed42(
    settings: Settings,
    leadgen_http: httpx2.Client,
    mailbox_http: httpx2.Client,
    *,
    control: Control | None,
    hypothesis: str | None,
) -> dict[str, Any]:
    """Run the seed-42 suite against the services behind the two clients and return the `run` row.

    The row is `invalid`, with no scores, when a service fails its health or bootstrap check.
    """
    requests: list[str] = []
    for http in (leadgen_http, mailbox_http):
        http.event_hooks["request"].append(lambda request: requests.append(request.url.path))
    leadgen = LeadgenClient(leadgen_http)
    row: dict[str, Any] = {
        "kind": "run",
        "run_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(UTC).isoformat(),
        "suite": "seed42",
        "control": None if control is None else control.value,
        "mode": settings.run_mode,
        "commit": settings.git_commit,
        "evaluator_hash": _evaluator_hash(),
        "case_set_id": _case_set_id(),
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

    registry = load_registry(settings.registry_path)
    labels = load_labels()
    scores: dict[str, Score] = {}
    with tempfile.TemporaryDirectory(prefix="uwh-eval-") as scratch, applied(control):

        def per_run(name: str) -> Settings:
            return replace(settings, db_path=str(Path(scratch) / f"{name}.db"), seed=SEED)

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
    scores["Key isolation"] = Score()
    scores["Key isolation"].add(FIRST_PASS, key_isolation(Path(uwh.__file__).parent, requests))

    tokens = {key: sum(m[f"tokens_{key}"] for m in measurements.values()) for key in ("in", "out")}
    return row | {
        "status": "scored",
        "scores": {name: score.row() for name, score in scores.items()},
        "critical_errors": [*dict.fromkeys(critical)],
        "skill_results": _skill_results(registry),
        "tokens": tokens,
        "cost_usd": 0.0,  # a replay makes no billed call
        "measurements": {"per_lead": measurements},
    }


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


SUITES = {"seed42": evaluate_seed42}


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
    args = parser.parse_args(argv)
    # Each run opens a database of its own, so the path the settings need is a placeholder.
    settings = Settings.load({**os.environ, "UWH_DB": "per run"})
    if settings.run_mode != "replay":
        parser.error("the seed42 suite replays recordings: set RUN_MODE=replay")
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
