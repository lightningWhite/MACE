"""Layer 3: storms with a position, a direction, and a life of their own.

The chain in `weather.py` gives each region weather that is coherent in time
and independent in space — it can rain in the valley and be clear on the ridge
next door, forever, for no reason. A front is what ties them together. It sits
over a region and multiplies that region's transition weights toward its own
kind of weather; every few ticks it hops to the next region along its heading;
and the region *ahead* of it gets a share of the same bias, which is what lets
a player read the sky and decide to wait a day.

Everything here draws from one stream, `weather.fronts`, so a chatty front
system does not shift what any individual region's chain was going to do.

See docs/05-world-simulation.md § Layer 3.
"""

from __future__ import annotations

from mace.content import ContentError, Library
from mace.engine.rng import RandomStream
from mace.engine.state import FrontState, GameState
from mace.engine.world.clock import Clock
from mace.model import Climate, Region, WeatherFront

__all__ = [
    "FRONT_STREAM",
    "biases_for",
    "occupying",
    "step",
]

#: The stream fronts are drawn from — their own, so that adding a front system
#: to a game does not change the weather a recorded playthrough experienced.
FRONT_STREAM = "weather.fronts"


def step(
    library: Library,
    state: GameState,
    clock: Clock,
    regions: dict[str, tuple[Region, Climate | None, str]],
) -> tuple[list[FrontState], list[FrontState]]:
    """Advance every front one tick, and decide whether a new one forms.

    Fronts are advanced for the whole map rather than for the player's region
    alone. There are never many of them, and a storm that only exists while
    someone is looking at it is exactly the thing this layer is for.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough. Fronts are moved, added, and removed in place.
    clock : Clock
        World time.
    regions : mapping
        Qualified region id to its region, climate, and the pack the climate
        was written in — built once by the caller, which already needs it.

    Returns
    -------
    tuple
        The fronts that formed this tick, and the ones that died.
    """
    stream = state.rng.stream(FRONT_STREAM)
    tick = state.tick

    faded = [front for front in state.fronts if tick >= front.expires_at_tick]
    if faded:
        state.fronts = [front for front in state.fronts if tick < front.expires_at_tick]

    for front in state.fronts:
        if tick >= front.hops_at_tick:
            definition = _definition(library, front.kind)
            front.position += 1
            front.hops_at_tick = tick + (
                definition.speed_ticks if definition is not None else 1
            )
            if front.position >= len(front.heading):
                front.expires_at_tick = tick

    formed = _maybe_form(library, state, clock, stream, regions)
    return formed, faded


def _maybe_form(
    library: Library,
    state: GameState,
    clock: Clock,
    stream: RandomStream,
    regions: dict[str, tuple[Region, Climate | None, str]],
) -> list[FrontState]:
    """Roll for a new front, once, across the whole map.

    One roll rather than one per region, so adding regions to a map does not
    silently make it stormier. The chance is the largest `frontFrequency` any
    region's climate offers, and the origin is then chosen among the regions
    whose climates can produce the kind that was drawn.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    clock : Clock
        World time.
    stream : RandomStream
        The front stream.
    regions : mapping
        Qualified region id to its region, climate, and the climate's pack.

    Returns
    -------
    list of FrontState
        The front that formed, or nothing.
    """
    season = clock.season(state.tick).id
    candidates: list[tuple[tuple[str, str], float]] = []
    frequency = 0.0

    for region_id, (_region, climate, home) in sorted(regions.items()):
        if climate is None or not climate.fronts:
            continue
        frequency = max(frequency, climate.front_frequency)
        for reference in climate.fronts:
            definition = _resolve(library, reference, home)
            if definition is None:
                continue
            if definition.seasons and season not in definition.seasons:
                continue
            qualified = library.resolve(reference, "weatherFronts", within=home)
            candidates.append(((region_id, qualified), definition.weight))

    if not candidates or frequency <= 0.0 or not stream.chance(frequency):
        return []

    region_id, kind = stream.weighted(candidates)
    definition = _definition(library, kind)
    assert definition is not None

    heading = _plot(library, stream, region_id, definition, regions)
    low, high = definition.intensity_range

    state.fronts_spawned += 1
    front = FrontState(
        id=f"{kind.split(':', 1)[1]}#{state.fronts_spawned}",
        kind=kind,
        heading=heading,
        intensity=low + stream.fraction() * (high - low),
        born_at_tick=state.tick,
        expires_at_tick=state.tick + definition.lifespan_ticks,
        hops_at_tick=state.tick + definition.speed_ticks,
    )
    state.fronts.append(front)
    return [front]


def _plot(
    library: Library,
    stream: RandomStream,
    origin: str,
    definition: WeatherFront,
    regions: dict[str, tuple[Region, Climate | None, str]],
) -> tuple[str, ...]:
    """Walk the neighbour graph to give a front somewhere to go.

    A front that stayed put would be indistinguishable from a run of bad luck
    in one region's chain. Walking neighbours is what makes it a direction.

    Parameters
    ----------
    library : Library
        The loaded content.
    stream : RandomStream
        The front stream.
    origin : str
        Qualified id of the region it forms over.
    definition : WeatherFront
        The kind of front, for how far it may travel.
    regions : mapping
        Qualified region id to its region, climate, and the climate's pack.

    Returns
    -------
    tuple of str
        The regions it crosses, origin first. A region with no neighbours
        gives a one-entry heading, and the front simply sits and dies.
    """
    fewest, most = definition.hops
    wanted = stream.between(fewest, most)

    heading = [origin]
    while len(heading) < wanted:
        region, _climate, _home = regions[heading[-1]]
        pack = heading[-1].split(":", 1)[0]
        onward = []
        for reference in region.neighbors:
            try:
                qualified = library.resolve(reference, "regions", within=pack)
            except ContentError:
                continue
            if qualified in heading or qualified not in regions:
                continue
            onward.append(qualified)
        if not onward:
            break
        heading.append(stream.choice(sorted(onward)))
    return tuple(heading)


# ── What a front does to the sky under it ─────────────────────────────────────


def occupying(state: GameState, region_id: str) -> list[FrontState]:
    """The fronts currently over a region.

    Parameters
    ----------
    state : GameState
        The playthrough.
    region_id : str
        Qualified region id.

    Returns
    -------
    list of FrontState
        In the order they formed, so two fronts over one region compose the
        same way every replay.
    """
    return [front for front in state.fronts if front.at == region_id]


def biases_for(
    library: Library, state: GameState, region_id: str, tick: int
) -> dict[str, float]:
    """The multipliers every front has to offer this region right now.

    A front over the region contributes its full bias; a front whose *next*
    region this is contributes `aheadBias` of it, which is the foreshadowing.
    Both scale with the front's intensity, which decays as it ages — so a
    storm arrives, sits, and eases off rather than switching on and off.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    region_id : str
        Qualified region id.
    tick : int
        The tick being resolved.

    Returns
    -------
    dict
        Qualified condition id to multiplier. Qualified rather than bare,
        because a front in `fantasy.core` and a climate in a game pack name
        the same rain two different ways.
    """
    combined: dict[str, float] = {}
    for front in state.fronts:
        share = 0.0
        if front.at == region_id:
            share = 1.0
        elif front.ahead == region_id:
            definition = _definition(library, front.kind)
            share = definition.ahead_bias if definition is not None else 0.0
        if share <= 0.0:
            continue

        definition = _definition(library, front.kind)
        if definition is None:
            continue
        home = front.kind.split(":", 1)[0]
        strength = share * _strength(front, definition, tick)
        for condition, bias in definition.biases.items():
            scaled = 1.0 + (bias - 1.0) * strength
            try:
                qualified = library.resolve(condition, "weatherConditions", within=home)
            except ContentError:
                continue
            combined[qualified] = combined.get(qualified, 1.0) * max(0.0, scaled)
    return combined


def _strength(front: FrontState, definition: WeatherFront, tick: int) -> float:
    """How much of itself a front still has.

    Parameters
    ----------
    front : FrontState
        The front.
    definition : WeatherFront
        Its kind, for its lifespan.
    tick : int
        Now.

    Returns
    -------
    float
        0 to 1: its birth intensity, decayed linearly toward nothing at the
        end of its life.
    """
    age = max(0, tick - front.born_at_tick)
    remaining = max(0.0, 1.0 - age / definition.lifespan_ticks)
    return front.intensity * remaining


# ── Looking things up ─────────────────────────────────────────────────────────


def _definition(library: Library, qualified: str) -> WeatherFront | None:
    """Find a front definition by qualified id.

    Parameters
    ----------
    library : Library
        The loaded content.
    qualified : str
        The qualified id.

    Returns
    -------
    WeatherFront or None
        The definition, or None when content changed under a save.
    """
    pack_id, local_id = qualified.split(":", 1)
    return library.pack(pack_id).weather_fronts.get(local_id)


def _resolve(library: Library, reference: str, home: str) -> WeatherFront | None:
    """Resolve a front reference written in a climate.

    Parameters
    ----------
    library : Library
        The loaded content.
    reference : str
        As the climate wrote it.
    home : str
        The pack the climate was written in.

    Returns
    -------
    WeatherFront or None
        The definition, or None if it names nothing.
    """
    try:
        found = library.find(reference, "weatherFronts", within=home)
    except ContentError:
        return None
    assert isinstance(found, WeatherFront)
    return found
