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
"""

from __future__ import annotations

import sys
import time
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
    """One key, and how long it took to arrive.

    Attributes
    ----------
    key : str or None
        The character typed, lowercased. None when the deadline passed with
        nothing pressed.
    elapsed_ms : int
        Milliseconds from the moment the window opened. Capped at the window
        when nothing arrived, which is what "too late" means.
    """

    key: str | None
    elapsed_ms: int


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


def read_key(window_ms: int) -> Keypress:
    """Wait up to `window_ms` for a single keypress.

    Parameters
    ----------
    window_ms : int
        How long the window is open.

    Returns
    -------
    Keypress
        What was pressed and when, or None and the full window.
    """
    started = time.monotonic()
    deadline = started + window_ms / 1000.0
    settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Keypress(None, window_ms)
            ready, _write, _error = select.select([sys.stdin], [], [], remaining)
            if not ready:
                return Keypress(None, window_ms)
            typed = sys.stdin.read(1)
            elapsed = int(round((time.monotonic() - started) * 1000))
            return Keypress(typed.lower(), elapsed)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
