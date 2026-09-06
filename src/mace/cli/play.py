"""The terminal front-end: turn events into prose, and typing into actions.

This is the whole of what a front-end does. It never asks the engine what the
state is; it renders the events it is handed and sends back an action. The web
client will do the same thing with the same events and a different set of
pixels, which is the point of the arrangement.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from mace.content import ContentError, Library, load_library
from mace.engine.actions import Action, Choose
from mace.engine.events import Event
from mace.engine.state import Outcome
from mace.engine.step import StepResult, begin, step

__all__ = ["Renderer", "play"]

#: Printed once, at the top.
RULE = "─" * 64

#: How an event of each kind is prefixed. Anything absent is not shown: an
#: event a player has no use for is noise, and the engine emits some that exist
#: for tests and debuggers rather than for readers.
ASIDES = {
    "stat.changed": "  ",
    "inventory.changed": "  ",
    "quest.updated": "  ",
    "location.revealed": "  ",
    "engine.unsupported": "  ! ",
    "engine.rule-failed": "  ! ",
}


@dataclass(slots=True)
class Renderer:
    """Turns events into lines on a terminal.

    Parameters
    ----------
    out : TextIO
        Where to write.
    interactive : bool
        Whether to honour `pause`. A recorded or piped session should not stop
        and wait for a keypress nobody is there to give.
    """

    out: TextIO
    interactive: bool = True

    def show(self, events: Iterable[Event]) -> None:
        """Render a step's events in order.

        Parameters
        ----------
        events : iterable of Event
            What happened.
        """
        for event in events:
            self.show_one(event)

    def show_one(self, event: Event) -> None:
        """Render one event.

        Parameters
        ----------
        event : Event
            What happened.
        """
        payload = event.payload()

        if event.kind == "narrate":
            self.line(str(payload["text"]))
            if payload["pause"] and self.interactive:
                self.wait()
            return

        if event.kind == "choices":
            self.menu(payload["options"])
            return

        if event.kind == "moved" and payload["ticks"]:
            self.line("")
            return

        if event.kind == "travel.leg":
            if payload["text"]:
                self.line(str(payload["text"]))
            return

        if event.kind == "travel.interrupted":
            self.line("")
            return

        if event.kind == "weather.changed":
            if payload["text"]:
                self.line("")
                self.line(str(payload["text"]))
            return

        if event.kind == "world.status":
            self.status(payload)
            return

        if event.kind == "game.over":
            self.line("")
            self.line(RULE)
            self.line("You won." if payload["outcome"] == "won" else "You lost.")
            self.line(RULE)
            return

        aside = ASIDES.get(event.kind)
        if aside is not None:
            self.line(f"{aside}{_describe(event.kind, payload)}")

    def menu(self, options: list[dict[str, Any]]) -> None:
        """Print the options on offer.

        Parameters
        ----------
        options : list of dict
            The option records from a `choices` event.
        """
        self.line("")
        if not options:
            self.line("  There is nothing to do here.")
            return
        for index, option in enumerate(options, start=1):
            if option["available"]:
                self.line(f"  {index}. {option['prompt']}")
            else:
                hint = f"  {option['hint']}" if option["hint"] else ""
                self.line(f"  {index}. {option['prompt']}  (unavailable){hint}")

    def status(self, payload: dict[str, Any]) -> None:
        """Print the standing line: when it is, where you are, what the sky is doing.

        This is the whole visible payoff of the world simulation. A player who
        never sees `Day 3 · dusk · Fenmoor · light rain` has no way to know
        that waiting a day was a decision they could have made.

        Parameters
        ----------
        payload : dict
            The fields of a `world.status` event.
        """
        parts = [f"Day {payload['day']}", str(payload["dayPart"])]
        if payload["place"]:
            parts.append(str(payload["place"]))
        if payload["sky"]:
            sky = str(payload["sky"])
            if payload["indoors"]:
                sky += ", outside"
            parts.append(sky)
        cold = _exposure(float(payload.get("exposure") or 0.0))
        if cold:
            parts.append(cold)
        self.line("")
        self.line(f"  {' · '.join(parts)}")

    def line(self, text: str) -> None:
        """Write one line.

        Parameters
        ----------
        text : str
            What to write.
        """
        print(text, file=self.out)

    def wait(self) -> None:
        """Hold until the player is ready, where there is a player to wait for."""
        try:
            input("")
        except EOFError:  # pragma: no cover — piped input ends
            self.interactive = False


#: How the status line says what standing out in it has cost. The engine
#: reports a number; putting a word to it is a front-end's job, and the player
#: never sees the number.
EXPOSURE_WORDS: tuple[tuple[float, str], ...] = (
    (0.85, "in a bad way"),
    (0.60, "badly chilled"),
    (0.35, "cold through"),
    (0.15, "feeling it"),
)


def _exposure(level: float) -> str:
    """Put a word to how much the weather has taken out of the player.

    Parameters
    ----------
    level : float
        0 to 1, from a `world.status` event.

    Returns
    -------
    str
        The word, or an empty string while it does not matter yet.
    """
    for threshold, word in EXPOSURE_WORDS:
        if level >= threshold:
            return word
    return ""


def _describe(kind: str, payload: dict[str, Any]) -> str:
    """Phrase a side-effect event as a short aside.

    Parameters
    ----------
    kind : str
        The event kind.
    payload : dict
        Its fields.

    Returns
    -------
    str
        A line a player can read.
    """
    if kind == "stat.changed":
        delta = payload["delta"]
        sign = "+" if delta > 0 else ""
        reason = f" ({payload['reason']})" if payload["reason"] else ""
        return f"{sign}{_number(delta)} {payload['stat']}{reason}"
    if kind == "inventory.changed":
        delta = payload["delta"]
        sign = "+" if delta > 0 else ""
        return f"{sign}{delta} {_local(str(payload['item']))}"
    if kind == "quest.updated":
        journal = payload["journal"]
        if journal:
            return f"Journal: {journal}"
        return f"Quest {payload['status']}: {_local(str(payload['quest']))}"
    if kind == "location.revealed":
        return f"You have heard of {_local(str(payload['location']))}."
    if kind == "engine.unsupported":
        return f"{payload['feature']} is not in the engine yet ({payload['arrives']})."
    return str(payload.get("message", payload))


def _number(value: float) -> str:
    """Render a number without a pointless decimal point.

    Parameters
    ----------
    value : float
        The number.

    Returns
    -------
    str
        `8` rather than `8.0`.
    """
    return str(int(value)) if float(value).is_integer() else str(value)


def _local(qualified: str) -> str:
    """Strip the pack from a qualified id for display.

    Parameters
    ----------
    qualified : str
        A qualified content id.

    Returns
    -------
    str
        The local part.
    """
    return qualified.split(":", 1)[-1]


def choose(renderer: Renderer, result: StepResult) -> Action | None:
    """Ask the player what to do next.

    Parameters
    ----------
    renderer : Renderer
        For prompting and complaining.
    result : StepResult
        The last step, whose pending options are what may be chosen.

    Returns
    -------
    Action or None
        The action, or None to stop playing.
    """
    pending = result.state.pending
    count = len(pending.options) if pending else 0

    while True:
        try:
            typed = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None

        if typed in {"q", "quit", "exit"}:
            return None
        if not typed:
            continue
        if not typed.isdigit():
            renderer.line("  Type the number of what you want to do, or `q` to stop.")
            continue

        chosen = int(typed)
        if 1 <= chosen <= count:
            return Choose(chosen - 1)
        renderer.line(f"  Pick a number between 1 and {count}.")


def play(
    paths: list[Path],
    *,
    pack_id: str | None = None,
    seed: str = "mace",
    out: TextIO | None = None,
) -> int:
    """Load some packs and play one of them.

    Parameters
    ----------
    paths : list of Path
        Directories to load packs from.
    pack_id : str or None
        Which game to play. Optional when exactly one game was loaded.
    seed : str
        The session seed. The same seed and the same choices replay identically.
    out : TextIO or None
        Where to write. Defaults to standard output.

    Returns
    -------
    int
        The process exit code.
    """
    stream = out or sys.stdout
    renderer = Renderer(stream, interactive=sys.stdin.isatty())

    try:
        library = load_library(*paths)
        chosen = _pick_game(library, pack_id)
        result = begin(library, chosen, seed=seed)
    except ContentError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    renderer.line(RULE)
    renderer.show(result.events)

    while result.state.outcome is Outcome.PLAYING:
        action = choose(renderer, result)
        if action is None:
            renderer.line("\nUntil next time.")
            return 0
        result = step(result.state, action, library)
        renderer.show(result.events)

    return 0


def _pick_game(library: Library, pack_id: str | None) -> str:
    """Decide which loaded pack to play.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack_id : str or None
        The pack the player named, if they named one.

    Returns
    -------
    str
        The pack id to play.

    Raises
    ------
    ContentError
        If there is no game, or more than one and no choice was made.
    """
    if pack_id is not None:
        return pack_id

    games = library.games
    if not games:
        raise ContentError("no game packs found — a game pack has `kind: game`")
    if len(games) > 1:
        names = ", ".join(pack.id for pack in games)
        raise ContentError(f"several games found; choose one with --pack: {names}")
    return games[0].id
