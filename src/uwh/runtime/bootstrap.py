# ABOUTME: Environment bootstrap check: health, queue for the seed, every lead envelope, and a mailbox probe.
# ABOUTME: Any failure raises EnvironmentInvalid; `python -m uwh.runtime.bootstrap` prints a JSON summary.
import json
import sys
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import httpx2

from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.settings import Settings

LEAD_COUNT = 10
TIMEOUT_SECONDS = 10.0
PROBE_ADDRESS = "uw@stand.com"
# Transport failures, a malformed URL, and an answer of the wrong form or shape.
CHECK_FAILURES = (
    httpx2.HTTPError,
    httpx2.InvalidURL,
    ValueError,
    LookupError,
    TypeError,
    AttributeError,
)


class EnvironmentInvalid(Exception):
    """The leadgen or mailbox service is unreachable or answered incorrectly."""


@contextmanager
def environment_check(name: str) -> Iterator[None]:
    """Name the failing check in the EnvironmentInvalid raised for a transport, URL or shape failure."""
    try:
        yield
    except CHECK_FAILURES as error:
        raise EnvironmentInvalid(f"{name} failed: {error!r}") from error


def run() -> dict[str, Any]:
    settings = Settings.load()
    bootstrap_id = uuid.uuid4().hex
    with ExitStack() as stack:
        with environment_check("leadgen client"):
            leadgen_http = stack.enter_context(
                httpx2.Client(base_url=settings.leadgen_url, timeout=TIMEOUT_SECONDS)
            )
        with environment_check("mailbox client"):
            mailbox_http = stack.enter_context(
                httpx2.Client(base_url=settings.mailbox_url, timeout=TIMEOUT_SECONDS)
            )
        leadgen = LeadgenClient(leadgen_http)
        mailbox = MailboxClient(mailbox_http)

        with environment_check("leadgen health check"):
            leadgen.healthz()
        with environment_check("mailbox health check"):
            mailbox.healthz()

        with environment_check("leadgen queue"):
            lead_ids = leadgen.post_queue(settings.seed, count=LEAD_COUNT)["lead_ids"]
            if len(lead_ids) != LEAD_COUNT:
                raise EnvironmentInvalid(
                    f"leadgen queue returned {len(lead_ids)} leads, not {LEAD_COUNT}"
                )
        with environment_check("leadgen lead list"):
            listed = [summary["lead_id"] for summary in leadgen.list_leads()]
            if listed != lead_ids:
                raise EnvironmentInvalid(
                    f"leadgen lead list {listed} differs from the queue {lead_ids}"
                )
        leads_read = 0
        for lead_id in lead_ids:
            with environment_check(f"leadgen lead {lead_id}"):
                envelope = leadgen.get_lead(lead_id)
                if envelope["lead_id"] != lead_id:
                    raise EnvironmentInvalid(
                        f"leadgen lead {lead_id} returned envelope {envelope['lead_id']}"
                    )
                if not isinstance(envelope["fields"], dict):
                    raise EnvironmentInvalid(f"leadgen lead {lead_id} has no fields mapping")
            leads_read += 1

        probe_lead_id = f"BOOTSTRAP-{bootstrap_id}"
        metadata = {"probe": True, "run_id": bootstrap_id}
        with environment_check("mailbox probe send"):
            mailbox.send(
                lead_id=probe_lead_id,
                to=PROBE_ADDRESS,
                from_=PROBE_ADDRESS,
                subject="Bootstrap probe",
                body="This message is a bootstrap probe and asks for nothing.",
                metadata=metadata,
            )
        with environment_check("mailbox probe read"):
            stored = mailbox.list_for_lead(probe_lead_id)
            if len(stored) != 1:
                raise EnvironmentInvalid(f"mailbox returned {len(stored)} probe messages, not 1")
            round_trip = stored[0]["metadata"] == metadata
            if not round_trip:
                raise EnvironmentInvalid(
                    f"mailbox probe metadata {stored[0]['metadata']} differs from sent {metadata}"
                )

    return {
        "bootstrap_id": bootstrap_id,
        "lead_ids": lead_ids,
        "leads_read": leads_read,
        "probe": {"lead_id": probe_lead_id, "metadata_round_trip": round_trip},
    }


def main() -> int:
    try:
        summary = run()
    except EnvironmentInvalid as error:
        print(f"invalid environment: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
