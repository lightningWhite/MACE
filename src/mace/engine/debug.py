"""The debug overlay: why the world just did that.

An author iterating on a corner of their world needs to see the machinery —
which conditions are being evaluated and how they came out, what the encounter
tables remember, which modifiers are in force and where they came from, and
where every random stream has got to.

This is a **projection**, not an extra event channel. It reads state and
content and returns a description; it never changes anything, and the engine
emits nothing extra when somebody is watching. That matters twice over: the
event stream stays the contract a second implementation has to match, and a
playthrough with the overlay open replays byte-identically to one without it.

Conditions are the one part that does real work. The engine records *whether*
a choice is available, not *why not*, because a player does not need the
because and a save file should not carry it. So the overlay goes back to the
scene the choices came from and evaluates each `when` again through the same
`RuleContext` the engine used — a second look at an unchanged world, which
gives the same answer by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mace.content import ContentError, Library
from mace.engine import economy
from mace.engine.conditions import RuleError, holds
from mace.engine.context import RuleContext
from mace.engine.state import GameState, MarketState
from mace.engine.step import context_for
from mace.engine.world import Observation
from mace.model import Condition, Scene

__all__ = ["Overlay", "Priced", "Tested", "TableMemory", "Modifier", "overlay"]


@dataclass(frozen=True, slots=True)
class Tested:
    """One condition, and how it came out just now.

    Attributes
    ----------
    subject : str
        What the condition gates — a choice's prompt.
    when : tuple of Condition
        The conditions themselves, handed back unrendered. Putting them into
        English is a front-end's job (`mace.wizard.language`), and the engine
        does not import the wizard to do it.
    holds : bool
        Whether it is true.
    error : str or None
        What went wrong evaluating it, for a condition that cannot even be
        asked. A dangling reference in a `when` shows up here rather than as a
        silent false, because those two look identical from the outside and
        need completely different fixes.
    """

    subject: str
    when: tuple[Condition, ...]
    holds: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TableMemory:
    """What one encounter table remembers about this playthrough.

    Attributes
    ----------
    table : str
        Qualified table id.
    pressure : float
        Added to the next roll's chance. Negative after a run of hits.
    ticks_since : int or None
        How long since it last produced something.
    fired : int
        How many times it has, in total.
    """

    table: str
    pressure: float
    ticks_since: int | None
    fired: int


@dataclass(frozen=True, slots=True)
class Modifier:
    """One stat adjustment in force, and where it came from.

    Attributes
    ----------
    stat : str
        Which stat.
    add, mult : float
        The adjustment.
    label : str
        What the player sees it called.
    source : str
        Where it came from — the whole point of showing it.
    expires_in : int or None
        Ticks left, or None for one that does not lapse.
    """

    stat: str
    add: float
    mult: float
    label: str
    source: str
    expires_in: int | None


@dataclass(frozen=True, slots=True)
class Priced:
    """One good on one market's shelf, and what it would cost right now.

    Attributes
    ----------
    good : str
        Qualified good id.
    held : float
        Units on the shelf.
    wanted : float
        Units the market aims to hold. Scarcity is `wanted` against `held`,
        so showing both is showing the price's working.
    price : float
        What one unit costs.
    base : float
        The item's `baseValue`, so the multiple is readable at a glance.
    """

    good: str
    held: float
    wanted: float
    price: float
    base: float


@dataclass(frozen=True, slots=True)
class Overlay:
    """Everything the debug view shows, as data.

    Attributes
    ----------
    tick : int
        The world clock.
    day : int
        Which day it is.
    day_part : str
        Which part of it.
    season : str
        Which season.
    location : str or None
        Where the player is.
    region : str or None
        Which region that is in.
    weather : str
        The condition in force, and its intensity.
    conditions : tuple of Tested
        Every condition currently gating something, evaluated.
    modifiers : tuple of Modifier
        What is acting on the player's stats.
    tables : tuple of TableMemory
        What the encounter tables remember.
    streams : tuple of tuple
        Stream name and how many values it has drawn.
    flags : tuple of str
        The player's flags.
    variables : tuple of tuple
        Game variables and their values.
    market : str or None
        The market where the player is standing, if there is one.
    prices : tuple of Priced
        What that market is charging, and the stock the price came from.
        Projected rather than read: the market is carried forward to now
        without being written to, so opening the overlay cannot move a price.
    """

    tick: int
    day: int
    day_part: str
    season: str
    location: str | None
    region: str | None
    weather: str
    conditions: tuple[Tested, ...] = ()
    modifiers: tuple[Modifier, ...] = ()
    tables: tuple[TableMemory, ...] = ()
    streams: tuple[tuple[str, int], ...] = ()
    flags: tuple[str, ...] = ()
    variables: tuple[tuple[str, object], ...] = field(default_factory=tuple)
    market: str | None = None
    prices: tuple[Priced, ...] = ()


def overlay(library: Library, state: GameState) -> Overlay:
    """Describe what the engine is currently thinking.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough. Read, never written.

    Returns
    -------
    Overlay
        The description.
    """
    context = context_for(library, state)
    clock = context.clock
    player = state.protagonist
    seen = context.weather()
    standing = _market(library, state)

    return Overlay(
        tick=state.tick,
        day=clock.day(state.tick),
        day_part=clock.day_part(state.tick),
        season=clock.season(state.tick).id,
        location=state.location,
        region=seen.region,
        weather=_weather(seen),
        conditions=_conditions(library, state, context),
        modifiers=tuple(
            Modifier(
                stat=one.stat,
                add=one.add,
                mult=one.mult,
                label=one.label,
                source=one.source,
                expires_in=(
                    None
                    if one.expires_at_tick is None
                    else one.expires_at_tick - state.tick
                ),
            )
            for one in player.modifiers
        ),
        tables=tuple(
            TableMemory(
                table=name,
                pressure=memory.pressure,
                ticks_since=(
                    None
                    if memory.last_at_tick is None
                    else state.tick - memory.last_at_tick
                ),
                fired=sum(memory.fired.values()),
            )
            for name, memory in sorted(state.encounters.items())
        ),
        streams=tuple(
            (name, state.rng.stream(name).position) for name in state.rng.names
        ),
        flags=tuple(sorted(player.flags)),
        variables=tuple(sorted(state.variables.items())),
        market=None if standing is None else standing.id,
        prices=() if standing is None else _prices(state, standing),
    )


def _market(library: Library, state: GameState) -> economy.Prepared | None:
    """The market where the player is standing, if there is one.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.

    Returns
    -------
    Prepared or None
        The market, resolved.
    """
    here = state.location
    if here is None:
        return None
    return economy.at(economy.prepare(library), here)


def _prices(state: GameState, standing: economy.Prepared) -> tuple[Priced, ...]:
    """What a market is charging, without moving its shelves.

    The market is projected to now rather than synced, because the overlay is
    a projection: a playthrough with it open has to replay byte-identically to
    one without.

    Parameters
    ----------
    state : GameState
        The playthrough. Read, never written.
    standing : Prepared
        The market.

    Returns
    -------
    tuple of Priced
        One entry per good, in the market's own order.
    """
    held = state.markets.get(standing.id) or MarketState(
        market=standing.id,
        stock={
            good_id: dealt.stock.opening for good_id, dealt in standing.goods.items()
        },
        stepped_to=state.start_tick,
    )
    now = economy.projected(held, standing, state.tick)
    return tuple(
        Priced(
            good=good_id,
            held=round(now.get(good_id, 0.0), 4),
            wanted=dealt.stock.wanted,
            price=round(
                economy.price_of(dealt, now.get(good_id, 0.0), standing.market.wealth),
                4,
            ),
            base=dealt.base_value,
        )
        for good_id, dealt in standing.goods.items()
    )


def _weather(seen: Observation) -> str:
    """What the sky is doing, in one phrase.

    Parameters
    ----------
    seen : Observation
        The weather where the player is.

    Returns
    -------
    str
        `light-rain at 0.40`, or a note that nothing is modelled here.
    """
    if seen.qualified is None:
        return "no weather here"
    indoors = " (indoors)" if seen.sheltered else ""
    return f"{seen.qualified.split(':')[-1]} at {seen.intensity:.2f}{indoors}"


def _conditions(
    library: Library, state: GameState, context: RuleContext
) -> tuple[Tested, ...]:
    """Evaluate every condition currently gating a choice.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    context : RuleContext
        What the engine evaluates against.

    Returns
    -------
    tuple of Tested
        One entry per gated choice, in the order they are offered.
    """
    pending = state.pending
    if pending is None:
        return ()
    scene = _scene(library, state, pending.scene)
    if scene is None:
        return ()

    return tuple(
        _test(choice.prompt, choice.when, context)
        for choice in scene.choices
        if choice.when
    )


def _test(subject: str, when: Sequence[Condition], context: RuleContext) -> Tested:
    """Evaluate one choice's conditions and say how they came out.

    Parameters
    ----------
    subject : str
        What they gate.
    when : sequence of Condition
        The authored conditions.
    context : RuleContext
        What to evaluate against.

    Returns
    -------
    Tested
        The result.
    """
    kept = tuple(when)
    try:
        answer = all(holds(one, context) for one in kept)
    except (RuleError, ContentError) as error:
        return Tested(subject=subject, when=kept, holds=False, error=str(error))
    return Tested(subject=subject, when=kept, holds=answer)


def _scene(library: Library, state: GameState, scene_id: str) -> Scene | None:
    """Look up the scene a set of pending choices came from.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    scene_id : str
        The qualified scene id, or the engine's own between-scenes menu.

    Returns
    -------
    Scene or None
        The scene, or None when the choices are the engine's own rather than
        an author's — the travel menu has no `when` to show.
    """
    if not scene_id:
        return None
    try:
        found = library.find(scene_id, "scenes", within=state.pack)
    except ContentError:
        return None
    return found if isinstance(found, Scene) else None
