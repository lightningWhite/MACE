"""The session layer: owns a running game.

Applies actions, emits events, snapshots and restores saves, and projects a
read-only view-model for front-ends. The boundary between the pure engine and
the impure outside world. See docs/02-architecture.md.

Everything above this line — a terminal, a browser tab, an HTTP request —
drives a `Session` and renders its events. Nothing above this line calls
`mace.engine.step` directly, and nothing below it knows a user exists.
"""

from mace.session.frames import frame
from mace.session.saves import FORMAT, Save, SaveError, load, read, resume, write
from mace.session.session import Session, choose_game
from mace.session.view import (
    Atlas,
    Carried,
    Entry,
    Gauge,
    Place,
    Road,
    Sheet,
    Underway,
    View,
    view,
)

__all__ = [
    "FORMAT",
    "Atlas",
    "Carried",
    "Entry",
    "Gauge",
    "Place",
    "Road",
    "Save",
    "SaveError",
    "Session",
    "Sheet",
    "Underway",
    "View",
    "choose_game",
    "frame",
    "load",
    "read",
    "resume",
    "view",
    "write",
]
