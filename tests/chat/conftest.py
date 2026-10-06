# ABOUTME: Fixtures for the chat tests: Stand's mailbox in process behind a client, which the command environment holds and a chat turn never calls.
# ABOUTME: The mailbox is emptied before each test, since Stand's in-process mailbox keeps one database for the whole session.
import httpx2
import pytest

from uwh.runtime.mailbox_client import MailboxClient


@pytest.fixture
def mailbox(stand_mailbox_client: httpx2.Client) -> MailboxClient:
    client = MailboxClient(stand_mailbox_client)
    client.reset()
    return client
