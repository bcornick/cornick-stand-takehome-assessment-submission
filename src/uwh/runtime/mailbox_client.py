# ABOUTME: Synchronous client for Stand's mailbox service: send, read, list by lead, reset and health.
# ABOUTME: It returns parsed JSON and raises on any non-success response; a FaultPlan, when one is given, injects the mailbox faults of 13.1.
from typing import Any

import httpx2

from uwh.runtime.faults import FaultPlan


class MailboxClient:
    def __init__(self, http: httpx2.Client, faults: FaultPlan | None = None) -> None:
        self._http = http
        self.faults = faults

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
        if self.faults is not None:
            self.faults.after_acceptance()
        result: dict[str, Any] = response.json()
        return result

    def list_for_lead(self, lead_id: str) -> list[dict[str, Any]]:
        if self.faults is not None and self.faults.hides_listing():
            return []
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
