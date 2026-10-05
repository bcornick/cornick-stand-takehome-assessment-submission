# ABOUTME: Tests what the app holds while it runs: the ruleset hash read at startup.
# ABOUTME: Each test opens the runtime against a temporary database, Stand's leadgen and mailbox apps in process, and a temporary directory in place of the image's rules data.
from pathlib import Path


from uwh.api.runtime import open_runtime
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings


def test_a_ruleset_file_changes_the_hash_the_runtime_reads(
    settings: Settings, leadgen: LeadgenClient, mailbox: MailboxClient, rules_data: Path
) -> None:
    with open_runtime(settings, leadgen, mailbox) as runtime:
        before = runtime.env.ruleset_hash
    (rules_data / "interpretation.yaml").write_text("rows: [a]\n", encoding="utf-8")

    with open_runtime(settings, leadgen, mailbox) as runtime:
        assert runtime.env.ruleset_hash != before
