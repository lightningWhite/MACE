"""A running game, and the log that is its own save file.

The engine is a function: state and an action in, state and events out. A
*session* is what holds that function's hand — it keeps the state between
calls, remembers every action in order, and hands a front-end the events. That
is the whole of what sits between `mace.engine` and a terminal, a browser tab,
or an HTTP request.

The log is written the way a person would write it. `Choose` addresses an
option by index because that is what a `choices` event's ordering means, but an
index is a terrible thing to write down: insert a menu entry above the one a
log meant and the log still replays, down a different road, saying nothing. So
a choice is recorded by its **prompt**, resolved back against the menu that was
actually on offer, and a save that no longer fits its content fails loudly with
that menu in the message.

The consequence is worth stating plainly: a save file is a golden recording
without the expected events. The same triple — packs and versions, seed,
ordered actions — is what `tests/golden/` compares against, which means a
player's save of the fight they could not win is already a bug report that
replays.

See docs/02-architecture.md § Determinism and randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mace.content import ContentError, Library
from mace.engine.actions import Action, Choose, decode
from mace.engine.creation import Character
from mace.engine.events import Event
from mace.engine.state import GameState, Outcome
from mace.engine.step import StepResult, begin, step
from mace.session.view import View, view

__all__ = ["Session", "choose_game"]


@dataclass(slots=True)
class Session:
    """One playthrough, held open.

    Attributes
    ----------
    library : Library
        The loaded content. Shared and immutable; the state beside it is
        neither (architecture boundary 1).
    pack : str
        The game pack being played.
    seed : str
        The session seed.
    state : GameState
        Where the playthrough has got to.
    events : tuple of Event
        What the last action produced. A front-end that missed them has to be
        given them again rather than reading the state to work out what
        happened, so they are kept.
    log : list of dict
        Every action taken, in order, in recorded form.
    combat_mode : str or None
        The player's choice of combat presentation, if they made one.
    time_pressure : float
        How hard the clock presses in `reflex` combat.
    character : Character or None
        What they answered at character creation.
    start_at : str or None
        Where the session opened, when that was not the game's own start.
    start_tick : int or None
        The tick it opened on, when that was not zero.
    """

    library: Library
    pack: str
    seed: str
    state: GameState
    events: tuple[Event, ...] = ()
    log: list[dict[str, Any]] = field(default_factory=list)
    combat_mode: str | None = None
    time_pressure: float = 1.0
    character: Character | None = None
    start_at: str | None = None
    start_tick: int | None = None

    @classmethod
    def begin(
        cls,
        library: Library,
        pack_id: str | None = None,
        *,
        seed: str = "mace",
        combat_mode: str | None = None,
        time_pressure: float = 1.0,
        character: Character | None = None,
        start_at: str | None = None,
        start_tick: int | None = None,
    ) -> Session:
        """Open a new playthrough.

        Parameters
        ----------
        library : Library
            The loaded content.
        pack_id : str or None
            Which game to play. None picks the only one loaded.
        seed : str
            The session seed. The same seed and the same actions replay
            identically.
        combat_mode : str or None
            Override the game's default combat presentation.
        time_pressure : float
            How hard the clock presses in `reflex` combat. 1.0 is the fight
            as authored; below it gives more of the window.
        character : Character or None
            Who the player is. None takes the protagonist as written.
        start_at : str or None
            Open somewhere other than the game's start location.
        start_tick : int or None
            Open at some other tick.

        Returns
        -------
        Session
            The session, with the opening events already in `events`.

        Raises
        ------
        ContentError
            If there is no game to play, or more than one and none was named.
        """
        chosen = choose_game(library, pack_id)
        opened = begin(
            library,
            chosen,
            seed=seed,
            combat_mode=combat_mode,
            time_pressure=time_pressure,
            character=character,
            start_at=start_at,
            start_tick=start_tick,
        )
        return cls(
            library=library,
            pack=chosen,
            seed=seed,
            state=opened.state,
            events=opened.events,
            combat_mode=combat_mode,
            time_pressure=time_pressure,
            character=character,
            start_at=start_at,
            start_tick=start_tick,
        )

    @property
    def playing(self) -> bool:
        """Whether the game is still running.

        Returns
        -------
        bool
            False once it has been won or lost.
        """
        return self.state.outcome is Outcome.PLAYING

    @property
    def offered(self) -> tuple[str, ...]:
        """The prompts currently on offer, in order.

        What a choice recorded by prompt is resolved against, and what a
        front-end's menu is made of.

        Returns
        -------
        tuple of str
            The option prompts, empty when nothing is pending.
        """
        pending = self.state.pending
        if pending is None:
            return ()
        return tuple(option.prompt for option in pending.options)

    def view(self) -> View:
        """Project everything a front-end draws that the events do not carry.

        The pack, the character sheet, the journal, the map. A projection, so
        asking for it changes nothing and a session with a map open replays
        identically to one without.

        Returns
        -------
        View
            The standing facts.
        """
        return view(self.library, self.state)

    def perform(self, action: Action) -> StepResult:
        """Apply one action and remember it.

        Parameters
        ----------
        action : Action
            What the player did.

        Returns
        -------
        StepResult
            The state and everything that happened.
        """
        record = self.record_of(action)
        result = step(self.state, action, self.library)
        self.state = result.state
        self.events = result.events
        self.log.append(record)
        return result

    def replay(self, record: dict[str, Any]) -> StepResult:
        """Apply one action written down, resolving it against what is offered.

        Parameters
        ----------
        record : dict
            An entry from a save's action log.

        Returns
        -------
        StepResult
            The state and everything that happened.

        Raises
        ------
        ValueError
            If the record names no known action, or an option that is not on
            offer — which is what content changing under a save looks like.
        """
        return self.perform(decode(record, offered=self.offered))

    def record_of(self, action: Action) -> dict[str, Any]:
        """Write an action down the way a save file wants it.

        A choice becomes its prompt where one can be found; everything else is
        already readable, and records as itself.

        Parameters
        ----------
        action : Action
            The action about to be taken, against the options standing now.

        Returns
        -------
        dict
            A JSON-safe record.
        """
        if isinstance(action, Choose):
            offered = self.offered
            if 0 <= action.option < len(offered):
                return {"kind": Choose.kind, "prompt": offered[action.option]}
        return action.record()


def choose_game(library: Library, pack_id: str | None = None) -> str:
    """Decide which loaded pack is the one being played.

    Every front-end asks this and none of them should answer it differently,
    so it lives here rather than in the terminal that happened to need it
    first.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack_id : str or None
        The pack that was named, if one was.

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
        library.pack(pack_id)
        return pack_id

    games = library.games
    if not games:
        raise ContentError("no game packs found — a game pack has `kind: game`")
    if len(games) > 1:
        names = ", ".join(pack.id for pack in games)
        raise ContentError(f"several games found; name the one to play: {names}")
    return games[0].id
