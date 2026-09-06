"""Driving the world forward one tick at a time.

The tick order is fixed and is part of the contract, because every layer above
reads what the one below left:

    1. fronts move, form, and fade
    2. each region's weather chain steps, under whatever bias the fronts leave
    3. the caller narrates what changed where the player can see it

Every region with a climate steps every tick, not only the one the player is
standing in. The design once called for the rest to be fast-forwarded on
demand, and the fast-forward is still here — a region created mid-game begins
at the playthrough's opening tick and catches up — but it cannot be the normal
path once fronts exist, because a front's bias is a fact about *when*, and
replaying a region's chain later with today's fronts would give a different
world. Stepping everything is a handful of weighted draws per tick at any map
size an author will actually build, and it is correct.

See docs/05-world-simulation.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mace.content import Library
from mace.engine.state import FrontState, GameState
from mace.engine.world import fronts
from mace.engine.world.clock import Clock
from mace.engine.world.weather import Prepared, climate_of, sync

__all__ = ["WorldChanges", "advance", "prepare"]


@dataclass(slots=True)
class WorldChanges:
    """What moved in the world while the clock did.

    Attributes
    ----------
    weather : set of str
        Regions whose condition changed. A region that changed twice appears
        once — the player sees where the sky ended up, not the working.
    formed : list of FrontState
        Fronts that came into being.
    faded : list of FrontState
        Fronts that died.
    """

    weather: set[str] = field(default_factory=set)
    formed: list[FrontState] = field(default_factory=list)
    faded: list[FrontState] = field(default_factory=list)


def prepare(library: Library) -> dict[str, Prepared]:
    """Resolve every region, its climate, and that climate's pack, once.

    Parameters
    ----------
    library : Library
        The loaded content.

    Returns
    -------
    dict
        Qualified region id to the resolved triple. Sorted insertion order, so
        anything iterating it does so in the same order every replay.
    """
    prepared: dict[str, Prepared] = {}
    for pack in library.packs:
        for local_id in sorted(pack.regions):
            region_id = f"{pack.id}:{local_id}"
            prepared[region_id] = climate_of(library, region_id)
    return prepared


def advance(
    library: Library,
    state: GameState,
    clock: Clock,
    pack: str,
    prepared: dict[str, Prepared] | None = None,
) -> WorldChanges:
    """Bring the world up to `state.tick`.

    Idempotent: called twice with the clock unmoved, the second call does
    nothing. That matters because arriving somewhere and time passing both
    want the world current, and they happen in either order.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough, advanced in place.
    clock : Clock
        World time.
    pack : str
        The pack references resolve against.
    prepared : mapping or None
        The output of `prepare`, if the caller already has it.

    Returns
    -------
    WorldChanges
        What moved, for the caller to narrate.
    """
    regions = prepare(library) if prepared is None else prepared
    changes = WorldChanges()
    if not regions:
        state.world_tick = state.tick
        return changes

    # The opening tick: every region needs weather before anything reads it.
    if not state.weather:
        for region_id, entry in regions.items():
            if sync(library, state, clock, pack, region_id, entry):
                changes.weather.add(region_id)

    while state.world_tick < state.tick:
        state.world_tick += 1
        standing = state.tick
        state.tick = state.world_tick
        try:
            formed, faded = fronts.step(library, state, clock, regions)
            changes.formed.extend(formed)
            changes.faded.extend(faded)
            for region_id, entry in regions.items():
                if sync(library, state, clock, pack, region_id, entry):
                    changes.weather.add(region_id)
        finally:
            state.tick = standing

    state.world_tick = state.tick
    return changes
