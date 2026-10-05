# ABOUTME: Synchronous client for Stand's mailbox service: send, read, list by lead, reset and health.
# ABOUTME: It returns parsed JSON and raises on any non-success response.
from typing import Any

import httpx2


class MailboxClient:
    def __init__(self, http: httpx2.Client) -> None:
        self._http = http

    def send(
        self,
        lead_id: str,
        to: str,
        from_: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "lead_id": lead_id,
            "to": to,
            "from": from_,
            "subject": subject,
            "body": body,
            "metadata": metadata,
        }
        response = self._http.post("/emails", json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def list_for_lead(self, lead_id: str) -> list[dict[str, Any]]:
        response = self._http.get(f"/leads/{lead_id}/emails")
        response.raise_for_status()
        result: list[dict[str, Any]] = response.json()
        return result

    def get(self, email_id: int) -> dict[str, Any]:
        response = self._http.get(f"/emails/{email_id}")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def reset(self) -> None:
        self._http.post("/reset").raise_for_status()

    def healthz(self) -> dict[str, Any]:
        response = self._http.get("/healthz")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
