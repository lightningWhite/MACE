"""The terminal front-end: turn events into prose, and typing into actions.

This is the whole of what a front-end does. It never asks the engine what the
state is; it renders the events it is handed and sends back an action. The web
client will do the same thing with the same events and a different set of
pixels, which is the point of the arrangement.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from mace.cli.create import ask
from mace.cli.map import draw
from mace.cli.timing import Keypress, raw_terminal_available, read_key
from mace.content import ContentError, load_best_effort
from mace.engine.actions import Action, Choose, Respond
from mace.engine.creation import Character
from mace.engine.creation import offer as creation_offer
from mace.engine.events import Event
from mace.session import SaveError, Session, choose_game
from mace.session import load as load_save
from mace.session import write as write_save

__all__ = ["Renderer", "keys_for", "play"]

#: Printed once, at the top.
RULE = "─" * 64

#: What each outcome of an exchange is called, and why it went that way.
#: Naming the *reason* is what turns an outcome into learning — "-8 hp" teaches
#: nobody anything, and learning is the entire point of tempo combat.
RESULTS: dict[str, str] = {
    "counter": "Clean counter",
    "absorbed": "Taken on the guard",
    "glancing": "Glancing",
    "clean": "Caught square",
}

#: How the timing half of an exchange is described, by precision.
TIMING: tuple[tuple[float, str], ...] = (
    (0.9, "perfectly timed"),
    (0.6, "well timed"),
    (0.3, "a shade early"),
    (0.0, "mistimed"),
)

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
    units : str
        `"celsius"` or `"fahrenheit"` — the scale the status line reads
        temperature in, converting from whatever a `world.status` event's own
        `temperatureUnit` says the number was written in.
    """

    out: TextIO
    interactive: bool = True
    fighting: bool = False
    units: str = "fahrenheit"

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

        if event.kind == "trade.haggled":
            self.line("")
            self.line(f"  {_haggling(payload)}")
            return

        if event.kind == "trade.stall":
            # The prices are in the menu; what the menu cannot say is why a
            # merchant has stopped buying, and that is their purse.
            if payload["purse"] is not None:
                self.line("")
                self.line(f"  {payload['name']} has {payload['purse']} to spend.")
            return

        if event.kind == "world.status" and not self.fighting:
            self.status(payload)
            return

        if event.kind == "combat.begin":
            self.fighting = True
            self.line("")
            self.line(RULE)
            against = ", ".join(
                c["name"] for c in payload["combatants"] if c["side"] == "enemy"
            )
            self.line(f"  Fighting: {against}")
            for entry in payload["matrix"]:
                answers = " or ".join(entry["beatenBy"]) or "nothing you have"
                self.line(f"    {entry['type']:<10} beaten by {answers}")
            self.line(RULE)
            return

        if event.kind == "combat.tell":
            self.line("")
            self.line(f"  {payload['text']}")
            if payload["type"]:
                self.line(f"  ({payload['type']})")
            return

        if event.kind == "combat.resolve":
            self.exchange(payload)
            return

        if event.kind == "combat.end":
            self.fighting = False
            self.finish(payload)
            return

        if self.fighting and event.kind in {"stat.changed", "world.status"}:
            # `combat.resolve` already says what an exchange cost and why, and
            # the standing line has nothing new to say inside a fight. Both
            # are still emitted; a fight is simply not where they belong.
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

    def exchange(self, payload: dict[str, Any]) -> None:
        """Say how one exchange went, and why.

        Attribution is what turns an outcome into learning: "Clean counter —
        you read the overhead" tells a player what to do again, and "-8 hp"
        does not.

        Parameters
        ----------
        payload : dict
            The fields of a `combat.resolve` event.
        """
        result = RESULTS.get(str(payload["result"]), str(payload["result"]))
        read = "read" if payload["read"] == "correct" else "misread"
        timing = _timing(float(payload["precision"]))
        parts = [f"  {result} — you {read} it, {timing}."]
        if payload["damageTaken"]:
            parts.append(f"You take {_number(payload['damageTaken'])}.")
        if payload["damageDealt"]:
            hit = "Critical opening" if payload["critical"] else "Your opening lands"
            parts.append(f"{hit} for {_number(payload['damageDealt'])}.")
        if payload["feint"] and payload["read"] != "correct":
            parts.append("It was a feint.")
        self.line(" ".join(parts))

    def finish(self, payload: dict[str, Any]) -> None:
        """Say how a fight ended.

        Parameters
        ----------
        payload : dict
            The fields of a `combat.end` event.
        """
        told = {
            "won": "You are still standing.",
            "lost": "You are not.",
            "fled": "You are away, and it is behind you.",
        }
        self.line("")
        self.line(f"  {told.get(str(payload['outcome']), str(payload['outcome']))}")
        for taken in payload["spoils"]:
            self.line(f"    +{taken['qty']} {_local(str(taken['item']))}")

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
        temperature = _temperature(
            payload.get("temperature"),
            str(payload.get("temperatureUnit", "celsius")),
            self.units,
        )
        if temperature is not None:
            parts.append(temperature)
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


def _temperature(value: float | None, source: str, target: str) -> str | None:
    """Convert and format a temperature reading for the status line.

    Parameters
    ----------
    value : float or None
        A `world.status` or `weather.changed` event's `temperature`. None
        where the region has no climate.
    source : str
        The scale it was written in — the same event's `temperatureUnit`.
    target : str
        The scale the player asked to read it in.

    Returns
    -------
    str or None
        `"46°F"`, or None where there is nothing to show.
    """
    if value is None:
        return None
    if source == target:
        converted = value
    elif target == "fahrenheit":
        converted = value * 9 / 5 + 32
    else:
        converted = (value - 32) * 5 / 9
    suffix = "°F" if target == "fahrenheit" else "°C"
    return f"{round(converted)}{suffix}"


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


def _haggling(payload: dict[str, Any]) -> str:
    """Say how a push went, without printing a spread at the player.

    Parameters
    ----------
    payload : dict
        A `trade.haggled` event's fields.

    Returns
    -------
    str
        A line a player can read.
    """
    who = payload["name"]
    said = " You mention what it costs elsewhere." if payload["leverage"] else ""
    if payload["result"] == "gave":
        return f"{who} comes down a little.{said}"
    if payload["result"] == "soured":
        return f"{who} has heard enough, and it will cost you.{said}"
    return f"{who} does not move.{said}"


def _timing(precision: float) -> str:
    """Put a word to how well an answer was timed.

    Parameters
    ----------
    precision : float
        0 to 1, from a `combat.resolve` event.

    Returns
    -------
    str
        The word.
    """
    for threshold, word in TIMING:
        if precision >= threshold:
            return word
    return TIMING[-1][1]  # pragma: no cover — the last threshold is zero


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


def keys_for(options: Sequence[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Bind a key to each response, without content having to name one.

    A move's `key` would be presentation leaking into content — a browser
    binds a button, a screen reader binds nothing. So the terminal picks:
    first free letter of the *label*, and failing that a digit.

    Parameters
    ----------
    options : sequence of tuple
        Response and label, in presentation order.

    Returns
    -------
    dict
        Key to the response and label it stands for, in offer order.
    """
    bound: dict[str, tuple[str, str]] = {}
    for index, (response, label) in enumerate(options, start=1):
        letter = next(
            (c for c in label.lower() if c.isalnum() and c not in bound),
            str(index)[-1],
        )
        bound[letter] = (response, label)
    return bound


def _marked(key: str, label: str) -> str:
    """Show a response with its key marked, wherever in the word it fell.

    Parameters
    ----------
    key : str
        The bound character.
    label : str
        What the response is called.

    Returns
    -------
    str
        `[d]odge`, or `s[t]rike` when the obvious letter was taken.
    """
    at = label.lower().index(key)
    return f"{label[:at]}[{key}]{label[at + 1 :]}"


def fight(renderer: Renderer, session: Session, timed: bool) -> Action | None:
    """Collect the player's answer to a telegraphed move.

    Two presentations of one window. Timed, a key is read against a monotonic
    deadline and the elapsed milliseconds go into the action; untimed, a line
    is read and the engine fixes precision. Both send the same
    `combat.input` action, so the engine never learns which terminal it was
    talking to.

    Parameters
    ----------
    renderer : Renderer
        For prompting.
    session : Session
        The playthrough, whose pending tell is what needs answering.
    timed : bool
        Whether to run the clock.

    Returns
    -------
    Action or None
        The response, or None to stop playing.
    """
    combat = session.state.combat
    assert combat is not None and combat.tell is not None
    offered = next(
        (
            event.payload()
            for event in reversed(session.events)
            if event.kind == "combat.responses"
        ),
        None,
    )
    if offered is None:  # pragma: no cover — a live fight always offers them
        return None

    options = [
        (str(option["response"]), str(option["label"])) for option in offered["options"]
    ]
    bound = keys_for(options)
    renderer.line("")
    renderer.line(
        "  " + "   ".join(_marked(key, label) for key, (_r, label) in bound.items())
    )
    renderer.line(
        f"  stamina {_number(offered['stamina'])}"
        f"   momentum ×{offered['momentum']}"
        + (f"   streak {offered['streak']}" if offered["streak"] else "")
    )

    if not timed:
        return _untimed(renderer, bound)
    return _timed(renderer, bound, combat.tell.window_ms)


def _untimed(renderer: Renderer, bound: dict[str, tuple[str, str]]) -> Action | None:
    """Read an answer with no clock running.

    Parameters
    ----------
    renderer : Renderer
        For complaining.
    bound : dict
        Key to response and label.

    Returns
    -------
    Action or None
        The response, or None to stop playing.
    """
    while True:
        try:
            typed = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if typed in {"q", "quit", "exit"}:
            return None
        chosen = bound.get(typed[:1]) or next(
            (pair for pair in bound.values() if typed in {pair[0], pair[1].lower()}),
            None,
        )
        if chosen is not None:
            return Respond(chosen[0])
        names = ", ".join(label for _r, label in bound.values())
        renderer.line(f"  One of: {names}, or `q` to stop.")


def _timed(
    renderer: Renderer, bound: dict[str, tuple[str, str]], window_ms: int
) -> Action | None:
    """Read an answer against a monotonic deadline.

    A key that is not one of the answers still spends the window — hesitating
    over the keyboard is hesitating, and a terminal that quietly gave the time
    back would be a kinder window than the browser's, which is the one thing a
    second front-end must never be.

    Parameters
    ----------
    renderer : Renderer
        For prompting.
    bound : dict
        Key to response and label.
    window_ms : int
        How long the window is open.

    Returns
    -------
    Action or None
        The response, or None to stop playing.
    """
    renderer.out.write("\n> ")
    renderer.out.flush()
    try:
        pressed: Keypress = read_key(window_ms)
    except (EOFError, KeyboardInterrupt):  # pragma: no cover — a real terminal
        return None
    renderer.line("")

    if pressed.key in {"q", "\x03", "\x04"}:
        return None
    chosen = bound.get(pressed.key or "")
    if chosen is None:
        # Nothing, or the wrong key. Either way the window is spent, and the
        # engine is told exactly how much of it went by.
        renderer.line("  (too slow)" if pressed.key is None else "  (fumbled)")
        return Respond("recover", pressed.elapsed_ms)
    return Respond(chosen[0], pressed.elapsed_ms)


def choose(renderer: Renderer, session: Session) -> Action | None:
    """Ask the player what to do next.

    Parameters
    ----------
    renderer : Renderer
        For prompting and complaining.
    session : Session
        The playthrough, whose pending options are what may be chosen.

    Returns
    -------
    Action or None
        The action, or None to stop playing.
    """
    count = len(session.offered)

    while True:
        try:
            typed = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None

        if typed in {"q", "quit", "exit"}:
            return None
        if typed in {"m", "map"}:
            renderer.line("")
            for line in draw(session.view().atlas):
                renderer.line(line)
            continue
        if not typed:
            continue
        if not typed.isdigit():
            renderer.line(
                "  Type the number of what you want to do, `m` for the map, "
                "or `q` to stop."
            )
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
    combat_mode: str | None = None,
    time_pressure: float = 1.0,
    character: Character | None = None,
    save: Path | None = None,
    resume: Path | None = None,
    units: str = "fahrenheit",
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
    combat_mode : str or None
        Override the game's default combat presentation.
    time_pressure : float
        How hard the clock presses in reflex combat. 1.0 is the fight as
        written; below it gives more of the window.
    character : Character or None
        Skip character creation and start as this. None asks, for a game that
        has something to ask.
    save : Path or None
        Where to write the playthrough when it ends, however it ends.
    resume : Path or None
        A save to carry on from. Its seed, combat mode and character are the
        session's, so the arguments that would have set those are ignored.
    units : str
        `"celsius"` or `"fahrenheit"` — the scale the status line reads
        temperature in, converting from whatever the climate is written in.
    out : TextIO or None
        Where to write. Defaults to standard output.

    Returns
    -------
    int
        The process exit code.
    """
    stream = out or sys.stdout
    interactive = sys.stdin.isatty()
    renderer = Renderer(stream, interactive=interactive, units=units)

    try:
        loaded = load_best_effort(*paths)
        for problem in loaded.problems:
            # A pack or object elsewhere that will not build should not stop
            # playing this one — same reasoning as `mace dev`. `mace validate`
            # is the strict gate.
            print(f"warning {problem}", file=sys.stderr)
        library = loaded.library
        if resume is not None:
            session, drift = load_save(resume, library)
            for line in drift:
                print(f"warning {line}", file=sys.stderr)
        else:
            chosen = choose_game(library, pack_id)
            if character is None and creation_offer(library, chosen).asks_anything:
                character = ask(library, chosen, stream, interactive=interactive)
            session = Session.begin(
                library,
                chosen,
                seed=seed,
                combat_mode=combat_mode,
                time_pressure=time_pressure,
                character=character,
            )
    except (ContentError, SaveError) as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    # A window that cannot be measured fairly is worse than no window at all,
    # so a piped or unsupported terminal drops to the untimed presentation
    # rather than pretending to run a clock.
    timed = raw_terminal_available()
    if session.state.combat_mode == "reflex" and not timed:
        renderer.line("  (no timed input available here — playing combat untimed)")

    renderer.line(RULE)
    renderer.line("  (`m` for the map, `q` to stop)")
    if resume is not None:
        # The replay already happened, in silence: re-reading a whole
        # playthrough is not resuming it. What the player needs is the world
        # they are standing in, which is the last step's events.
        renderer.fighting = session.state.combat is not None
        renderer.line(f"  Resumed — {len(session.log)} actions replayed.")
    renderer.show(session.events)

    while session.playing:
        combat = session.state.combat
        if combat is not None and combat.tell is not None:
            action = fight(renderer, session, timed and combat.mode == "reflex")
        else:
            action = choose(renderer, session)
        if action is None:
            renderer.line("\nUntil next time.")
            break
        session.perform(action)
        renderer.show(session.events)

    return _keep(session, save, renderer)


def _keep(session: Session, save: Path | None, renderer: Renderer) -> int:
    """Write the playthrough down, if the player asked for that.

    Parameters
    ----------
    session : Session
        The playthrough, ended or abandoned.
    save : Path or None
        Where to write it.
    renderer : Renderer
        For saying where it went.

    Returns
    -------
    int
        The process exit code.
    """
    if save is None:
        return 0
    try:
        written = write_save(session, save)
    except SaveError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1
    renderer.line(f"  Saved to {written}.")
    return 0
