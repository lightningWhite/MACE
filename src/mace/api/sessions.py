"""Playthroughs the server is holding open, and the ids that address them.

An HTTP request is stateless and a playthrough is not, so something has to
keep the sessions between calls. This is that something, and it is
deliberately the least clever version of it: a dictionary in one process.

What that buys, and what it costs, is worth being explicit about because the
next phase changes it. A session here dies with the process, is invisible to a
second worker, and is evicted when the registry fills up. None of that loses a
playthrough — a session *is* its action log, and `GET /sessions/{id}/save`
hands the client the recipe to reopen it anywhere. The client that keeps its
save is the client that survives a restart, which is the same contract the
terminal has.

Phase 5's Pyodide build removes the problem rather than solving it: the engine
runs in the browser tab and there is no server to hold anything. What is here
is the bridge to that, not the destination.
"""

from __future__ import annotations

import secrets
from collections import OrderedDict
from dataclasses import dataclass, field

from mace.session import Session

__all__ = ["DEFAULT_CAPACITY", "Registry", "UnknownSession"]

#: How many playthroughs one process holds before the least recently used one
#: is dropped. Generous for a hobby deployment and bounded so that a crawler
#: opening sessions cannot exhaust memory.
DEFAULT_CAPACITY = 256

#: Bytes of entropy in a session id. A session id is a bearer token — anybody
#: holding one can play that playthrough — so it is not a counter.
ID_BYTES = 16


class UnknownSession(KeyError):
    """No session by that id — never opened, or evicted since."""


@dataclass(slots=True)
class Registry:
    """The playthroughs this process is holding open.

    Attributes
    ----------
    capacity : int
        How many to keep. The least recently used is dropped above it.
    open : OrderedDict
        Session id to session, most recently used last.
    """

    capacity: int = DEFAULT_CAPACITY
    open: OrderedDict[str, Session] = field(default_factory=OrderedDict)

    def add(self, session: Session) -> str:
        """Hold a session open and give it an address.

        Parameters
        ----------
        session : Session
            The playthrough.

        Returns
        -------
        str
            Its id.
        """
        session_id = secrets.token_urlsafe(ID_BYTES)
        self.open[session_id] = session
        while len(self.open) > self.capacity:
            self.open.popitem(last=False)
        return session_id

    def get(self, session_id: str) -> Session:
        """Look a session up, and mark it as the most recently used.

        Parameters
        ----------
        session_id : str
            The id.

        Returns
        -------
        Session
            The playthrough.

        Raises
        ------
        UnknownSession
            If there is no such session.
        """
        if session_id not in self.open:
            raise UnknownSession(session_id)
        self.open.move_to_end(session_id)
        return self.open[session_id]

    def drop(self, session_id: str) -> None:
        """Forget a session.

        Parameters
        ----------
        session_id : str
            The id.

        Raises
        ------
        UnknownSession
            If there is no such session.
        """
        if self.open.pop(session_id, None) is None:
            raise UnknownSession(session_id)
