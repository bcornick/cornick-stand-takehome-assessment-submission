# ABOUTME: The FaultPlan hook of 13.1 for the mailbox client: a send the mailbox accepted whose result is lost, a listing that is empty while a request is in flight, and a hold a test uses to act while a post is in flight.
# ABOUTME: Each injection is kept in `injected` until the send primitive records it as `fault_injected`; a client with no plan runs none of this.
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx2


@dataclass
class FaultPlan:
    """Faults for the mailbox client; each flag fires once and clears.

    A request is in flight from the moment the mailbox has accepted a post until the client has
    returned its result. A post whose result is lost never returns, so its request stays in flight
    until one listing has been answered.
    """

    fail_after_acceptance: bool = False  # the next post is accepted and then raises
    empty_while_in_flight: bool = False  # the next listing during a request in flight is empty
    hold_in_flight: Callable[[], None] | None = None  # runs while each post is in flight
    injected: list[str] = field(default_factory=list, init=False)
    _request_in_flight: bool = field(default=False, init=False, repr=False)

    def take_injected(self) -> list[str]:
        """The faults injected since the last call, in order."""
        taken, self.injected = self.injected, []
        return taken

    def after_acceptance(self) -> None:
        """Called by the client once the mailbox has accepted a post, before it returns the result."""
        self._request_in_flight = True
        if self.hold_in_flight is not None:
            self.hold_in_flight()
        if self.fail_after_acceptance:
            self.fail_after_acceptance = False
            self.injected.append("fail_after_acceptance")
            raise httpx2.ReadError(
                "injected: the mailbox accepted the post and the result was lost"
            )
        self._request_in_flight = False

    def hides_listing(self) -> bool:
        """Called by the client before it lists; True when the listing must be answered empty."""
        if not (self.empty_while_in_flight and self._request_in_flight):
            return False
        self.empty_while_in_flight = False
        self._request_in_flight = False
        self.injected.append("empty_while_in_flight")
        return True
