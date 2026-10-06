# ABOUTME: Fixtures for the eval tests: replay settings, the database of the app after the first pass of the seed-42 run, and the state the graders read at the settle point and after lead 008's actions, with Stand's leadgen and mailbox apps in process.
# ABOUTME: The image's rules data is replaced by a temporary directory holding an empty interpretation table, as the API tests do; the graders' state is built once and each test gets a copy it may change.
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest

from evals import run
from evals.graders.evidence import Evidence
from tests.api.helpers import (
    LEAD_008,
    REGISTRY,
    replay_settings,
    restore_first_pass,
    use_empty_rules_data,
)
from uwh.api.runtime import open_runtime
from uwh.rules.registry import load_registry
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.store import open_store
from uwh.settings import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    use_empty_rules_data(tmp_path, monkeypatch)
    return replay_settings(tmp_path, 42, GIT_COMMIT="0123abc")


@pytest.fixture
def first_pass_db(
    settings: Settings, leadgen: LeadgenClient, stand_mailbox_client: httpx2.Client
) -> Iterator[sqlite3.Connection]:
    """The database of the app after the first pass of the seed-42 run."""
    restore_first_pass(settings, leadgen, MailboxClient(stand_mailbox_client))
    db = open_store(settings.db_path)
    yield db
    db.close()


def copy_of(db: sqlite3.Connection) -> sqlite3.Connection:
    copy = sqlite3.connect(":memory:")
    db.backup(copy)
    return copy


@dataclass
class Snapshot:
    """The database and the mailbox at one moment of the seed-42 run."""

    db: sqlite3.Connection
    mail: dict[str, list[dict[str, Any]]]

    def evidence(self, earlier: frozenset[str] = frozenset()) -> Evidence:
        """Evidence over a copy of the snapshot, which a test may change."""
        mail = {lead: [dict(m) for m in held] for lead, held in self.mail.items()}
        return Evidence(copy_of(self.db), load_registry(str(REGISTRY)), mail, earlier)


@dataclass
class RunState:
    settled: Snapshot  # the settle point, before any underwriter action
    acted: Snapshot  # after lead 008's reply and approval


# The state is built by the first test that asks for it and shared with the rest.
_BUILT: list[RunState] = []


@pytest.fixture
def run_state(
    settings: Settings, leadgen: LeadgenClient, stand_mailbox_client: httpx2.Client
) -> RunState:
    if not _BUILT:
        mailbox = MailboxClient(stand_mailbox_client)
        labels = run.load_labels()
        with open_runtime(settings, leadgen, mailbox) as app, app.database() as db:
            result, first_pass = app.submit_as_underwriter(db, "start_run", {"seed": 42})
            assert result.accepted and first_pass is not None
            first_pass.future.result()

            def snapshot() -> Snapshot:
                ev = run._evidence(app, db)
                return Snapshot(copy_of(db), {lead: list(held) for lead, held in ev.mail.items()})

            settled = snapshot()
            assert run._play(app, db, LEAD_008, labels[LEAD_008]["underwriter_actions"]) == []
            _BUILT.append(RunState(settled, snapshot()))
    return _BUILT[0]
