"""One shape for everything a front-end is told.

`{session, playing, events, choices, view}`. The events are what happened, the
view is what stands, and the choices are what may be done next, named the way
a save names them.

It lives here rather than in a front-end because there is now more than one
front-end that sends it — the HTTP service and the engine running inside a
browser tab — and two definitions of the same wire is how the two quietly stop
being the same game. A client cannot tell which one it is talking to, and that
is the point.
"""

from __future__ import annotations

from typing import Any

from mace.session.session import Session

__all__ = ["frame"]


def frame(session_id: str, session: Session) -> dict[str, Any]:
    """Everything a client needs after something happened.

    One shape for every reply, so a client has one renderer rather than one
    per endpoint or per transport.

    Parameters
    ----------
    session_id : str
        Which playthrough.
    session : Session
        The playthrough.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "session": session_id,
        "playing": session.playing,
        "events": [event.record() for event in session.events],
        "choices": list(session.offered),
        "view": session.view().record(),
    }
