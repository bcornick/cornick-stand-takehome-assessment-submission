# ABOUTME: Tests what the app holds while it runs: the mode and ruleset hash read at startup, a database connection per request, the background first pass, and the restart recovery that the app runs before it serves.
# ABOUTME: Each test opens the runtime against a temporary database, Stand's leadgen and mailbox apps in process, and a temporary directory in place of the image's rules data.
import sqlite3
from pathlib import Path

import pytest

from uwh.api.runtime import open_runtime
from uwh.runtime.hashing import ruleset_hash
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import current_run
from uwh.runtime.store import open_store
from uwh.settings import Settings


def test_the_runtime_reads_the_mode_and_the_ruleset_hash_of_the_image_rules_data(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, rules_data: Path
) -> None:
    with open_runtime(settings, leadgen, mailbox) as runtime:
        assert runtime.env.mode == "replay"
        assert runtime.env.ruleset_hash == ruleset_hash(rules_data)
        assert runtime.env.steps == ()
        assert runtime.env.mailbox is mailbox
        assert runtime.env.leadgen is leadgen


def test_a_ruleset_file_changes_the_hash_the_runtime_reads(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, rules_data: Path
) -> None:
    with open_runtime(settings, leadgen, mailbox) as runtime:
        before = runtime.env.ruleset_hash
    (rules_data / "interpretation.yaml").write_text("rows: [a]\n", encoding="utf-8")

    with open_runtime(settings, leadgen, mailbox) as runtime:
        assert runtime.env.ruleset_hash != before


def test_a_database_connection_is_a_store_and_is_closed_after_use(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    with open_runtime(settings, leadgen, mailbox) as runtime:
        with runtime.database() as db:
            assert db.execute("SELECT count(*) FROM runs").fetchone() == (0,)
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_resuming_with_no_run_starts_none(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient
) -> None:
    with open_runtime(settings, leadgen, mailbox) as runtime:
        runtime.resume()

    assert current_run(open_store(settings.db_path)) is None
