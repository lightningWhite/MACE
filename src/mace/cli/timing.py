"""Reading one keypress against a deadline, in a plain terminal.

The CLI is not a fallback. It is the client that keeps the project honest:
anything the terminal can render is provably engine data rather than UI logic,
and the timing window is the hardest thing to render honestly. A laggy or
unfair window makes tempo combat feel arbitrary, which is the exact failure the
whole system exists to avoid.

So this measures against `time.monotonic` — never the wall clock, which can
jump — and it returns the elapsed milliseconds for the *front-end* to put in
the action log. The engine is handed a recorded number and quantizes it. It
never measures anything itself (ADR-0004).

Where there is no terminal to put in raw mode — a pipe, a recorded session, a
Windows console — `read_key` says so rather than pretending, and the caller
falls back to an untimed prompt. Losing the reflex half of combat is a
disappointment; a window that is secretly unfair is a bug.

`read_key` also takes movement: a character in `move_keys` nudges a running
total and keeps the window open, rather than ending it the way any other key
does. Real time keeps passing while they're tapped, so footwork is spent out
of the same countdown the answer is, not a separate allowance — the CLI's
version of "moving is part of the answer, not a separate turn"
(docs/07-combat.md § Range).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["Keypress", "raw_terminal_available", "read_key"]

try:  # pragma: no cover — platform probe, exercised by whichever branch runs
    import select
    import termios
    import tty

    _POSIX_TTY = True
except ImportError:  # pragma: no cover — Windows and friends
    _POSIX_TTY = False


@dataclass(frozen=True, slots=True)
class Keypress:
    """One key that ended the window, how long it took, and any footwork.

    Attributes
    ----------
    key : str or None
        The character that ended the window, lowercased. None when the
        deadline passed with nothing pressed — or with only movement keys
        pressed, since those don't end it.
    elapsed_ms : int
        Milliseconds from the moment the window opened. Capped at the window
        when nothing arrived, which is what "too late" means.
    move_by : float
        Feet accumulated from any `move_keys` tapped before the window
        ended, signed the same way `Respond.move_by` is.
    """

    key: str | None
    elapsed_ms: int
    move_by: float = 0.0


def raw_terminal_available() -> bool:
    """Whether a timed keypress can be read at all here.

    Returns
    -------
    bool
        True when stdin is a terminal this platform can put in raw mode.
    """
    if not _POSIX_TTY:  # pragma: no cover — platform-dependent
        return False
    try:
        return sys.stdin.isatty()
    except ValueError:  # pragma: no cover — a closed stdin
        return False


def read_key(
    window_ms: int, *, move_keys: Mapping[str, float] | None = None
) -> Keypress:
    """Wait up to `window_ms` for a keypress that ends the window.

    A key in `move_keys` nudges the running `move_by` total and keeps
    reading — it does not end the window, and does not stop the clock either.
    Any other key ends it immediately, same as before.

    Parameters
    ----------
    window_ms : int
        How long the window is open.
    move_keys : dict or None
        Character to feet, signed. None or empty means no key is treated as
        movement, and the first keypress always ends the window.

    Returns
    -------
    Keypress
        What ended the window and when, plus any feet accumulated first.
    """
    started = time.monotonic()
    deadline = started + window_ms / 1000.0
    settings = termios.tcgetattr(sys.stdin)
    move_by = 0.0
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Keypress(None, window_ms, move_by)
            ready, _write, _error = select.select([sys.stdin], [], [], remaining)
            if not ready:
                return Keypress(None, window_ms, move_by)
            typed = sys.stdin.read(1).lower()
            if move_keys and typed in move_keys:
                move_by += move_keys[typed]
                continue
            elapsed = int(round((time.monotonic() - started) * 1000))
            return Keypress(typed, elapsed, move_by)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
