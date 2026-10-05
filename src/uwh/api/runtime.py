# ABOUTME: What the app holds while it runs: the settings, the command environment read once at startup (mode, ruleset hash, steps, clients), a database connection per request and the single worker that runs a run's first pass.
# ABOUTME: The registry is read at startup; the workflow steps run in order on every lead and the ledger rules govern its facts.
import logging
import sqlite3
from collections.abc import Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx2
from fastapi import Depends, Request
from pydantic import JsonValue

import uwh.rules
import uwh.skills
from uwh.providers.stand_in import StandInProviders
from uwh.rules.derivations import ledger_derivations
from uwh.rules.registry import Registry, load_registry
from uwh.rules.validators import conflict_validators
from uwh.runtime.bootstrap import TIMEOUT_SECONDS
from uwh.runtime.commands import CommandResult, submit_command
from uwh.runtime.facts import LedgerRules
from uwh.runtime.hashing import ruleset_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import RunEnvironment, current_run, pass_context, run_first_pass
from uwh.runtime.store import open_store
from uwh.settings import Settings
from uwh.skills.steps import build_steps

logger = logging.getLogger(__name__)

# The image's rules data: the ruleset every run uses (A.4).
IMAGE_RULES_DATA = Path(uwh.rules.__file__).parent / "data"


def ledger_rules(registry: Registry) -> LedgerRules:
    """The rules of the fact ledger: a reply never sets a system-owned field, the conflict validators
    run on the facts, and the roof and siding classes are derived."""
    return LedgerRules(
        system_owned_keys=frozenset(
            name for name, field in registry.items() if not field.producer_editable
        ),
        validators=conflict_validators(),
        derivations=ledger_derivations(),
    )


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    env: RunEnvironment
    # One worker: a run is not started while another is processing, so at most one pass runs.
    passes: ThreadPoolExecutor

    @contextmanager
    def database(self) -> Iterator[sqlite3.Connection]:
        """A connection of its own, closed on exit; a connection belongs to the thread that opened it."""
        with closing(open_store(self.settings.db_path)) as db:
            yield db

    def submit_as_underwriter(
        self, db: sqlite3.Connection, command_type: str, payload: Mapping[str, JsonValue]
    ) -> tuple[CommandResult, Future[None] | None]:
        """Submit the command as the underwriter, the actor the REST transport binds. An accepted
        `start_run` also launches the first pass of its run on the worker; the future of that pass is
        returned for a caller that waits for it, and is None for every other result."""
        result = submit_command(db, self.env, "underwriter", command_type, payload)
        if result.accepted and command_type == "start_run":
            return result, self._launch_first_pass(db)
        return result, None

    def _launch_first_pass(self, db: sqlite3.Connection) -> Future[None]:
        """Run the first pass of the current run on the worker. A failure is logged with the run id, and
        the pass has settled the run by then."""
        run = current_run(db)
        assert run is not None  # called after a start wrote the run
        env = self.env
        future = self.passes.submit(
            run_first_pass,
            self.settings.db_path,
            run.run_id,
            pass_context(run, env),
            env.steps,
            env.mailbox,
        )
        future.add_done_callback(lambda done: _log_failure(run.run_id, done))
        return future


def _log_failure(run_id: str, future: Future[None]) -> None:
    error = future.exception()
    if error is not None:
        logger.error("the first pass of run %s failed", run_id, exc_info=error)


@contextmanager
def open_runtime(
    settings: Settings, leadgen: LeadgenClient | None = None, mailbox: MailboxClient | None = None
) -> Iterator[Runtime]:
    """Build the runtime from the settings and close what it opened on exit, after the running pass
    has finished. A service client the caller does not pass is built from the service's URL."""
    with ExitStack() as stack:
        if leadgen is None:
            http = httpx2.Client(base_url=settings.leadgen_url, timeout=TIMEOUT_SECONDS)
            leadgen = LeadgenClient(stack.enter_context(http))
        if mailbox is None:
            http = httpx2.Client(base_url=settings.mailbox_url, timeout=TIMEOUT_SECONDS)
            mailbox = MailboxClient(stack.enter_context(http))
        registry = load_registry(settings.registry_path)
        rules = ledger_rules(registry)
        env = RunEnvironment(
            settings.run_mode,
            ruleset_hash(IMAGE_RULES_DATA),
            rules,
            build_steps(registry, StandInProviders.for_seed(settings.seed), rules),
            Path(uwh.skills.__file__).parent,
            lambda: datetime.now(UTC),
            mailbox,
            leadgen,
        )
        passes = stack.enter_context(
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="first-pass")
        )
        yield Runtime(settings, env, passes)


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


RuntimeDependency = Annotated[Runtime, Depends(get_runtime)]
