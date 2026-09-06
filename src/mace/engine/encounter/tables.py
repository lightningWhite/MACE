"""Rolling an encounter table: does anything happen, and if so what.

Two stages, and keeping them apart is what makes a table tunable. Stage one is
one number — `chance` — and it is the road's danger dial. Stage two picks among
the entries that are *currently* eligible, normalising weights among that set,
so an author can add a `when` to an entry without silently changing how
dangerous the road is.

Nothing here narrates. The roll returns an entry and the caller decides what to
do with it, because an encounter on a road and an encounter in a dungeon end up
in the same scene runner by different routes.

See docs/06-travel-and-encounters.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from mace.content import ContentError, Library
from mace.engine.conditions import all_hold
from mace.engine.context import RuleContext
from mace.engine.state import EncounterMemory
from mace.model import EncounterEntry, EncounterTable

__all__ = ["Rolled", "roll", "table_for"]


@dataclass(frozen=True, slots=True)
class Rolled:
    """An encounter that fired.

    Attributes
    ----------
    table : str
        Qualified table id.
    entry : EncounterEntry
        What happened.
    chance : float
        The effective chance it was rolled against, pity included. Carried for
        the debug overlay: an author balancing a road wants to see the number
        the engine actually used, not the one they wrote.
    """

    table: str
    entry: EncounterEntry
    chance: float


def table_for(
    context: RuleContext, reference: str | None, *, within: str | None = None
) -> tuple[str, EncounterTable] | None:
    """Resolve an encounter-table reference to the table it names.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    reference : str or None
        As the author wrote it. None resolves to nothing, so callers can pass
        an optional field straight through.
    within : str or None
        The pack the reference was written in. Defaults to the game pack.

    Returns
    -------
    tuple or None
        The qualified id and the table, or None.
    """
    if reference is None:
        return None
    home = within or context.state.pack
    try:
        qualified = context.library.resolve(reference, "encounterTables", within=home)
    except ContentError:
        return None
    return qualified, _look_up(context.library, qualified)


def roll(context: RuleContext, table_id: str, table: EncounterTable) -> Rolled | None:
    """Roll one encounter table once.

    Parameters
    ----------
    context : RuleContext
        The playthrough. The table's memory is updated in place.
    table_id : str
        Qualified table id.
    table : EncounterTable
        The table.

    Returns
    -------
    Rolled or None
        What happened, or None for an uneventful stretch of road.
    """
    state = context.state
    memory = state.encounters.setdefault(table_id, EncounterMemory(table=table_id))

    if _too_soon(memory, table, state.tick):
        return None

    effective = min(1.0, max(0.0, table.chance + memory.pressure))
    stream = state.rng.stream(f"encounters.{table_id}")
    if not stream.chance(effective):
        memory.pressure += table.pressure_step
        return None

    eligible = [
        entry
        for entry in table.entries
        if entry.weight > 0
        and _available(entry, memory, state.tick)
        and all_hold(entry.when, context)
    ]
    if not eligible:
        # Nothing was eligible, so nothing happened — but the roll was spent.
        # Leaving the pity counter alone would let a road whose entries are
        # all on cooldown build up a debt it pays off all at once later.
        memory.pressure = 0.0
        return None

    chosen = stream.weighted([(entry, entry.weight) for entry in eligible])
    memory.last_at_tick = state.tick
    memory.fired[chosen.id] = memory.fired.get(chosen.id, 0) + 1
    memory.last_entry_tick[chosen.id] = state.tick
    memory.pressure -= table.pressure_step * (1.0 / max(table.chance, 1e-6) - 1.0)
    return Rolled(table=table_id, entry=chosen, chance=effective)


def _too_soon(memory: EncounterMemory, table: EncounterTable, tick: int) -> bool:
    """Whether this table produced something too recently to produce another.

    Parameters
    ----------
    memory : EncounterMemory
        What the table remembers.
    table : EncounterTable
        The table, for its `minGapTicks`.
    tick : int
        Now.

    Returns
    -------
    bool
        Whether the roll is suppressed.
    """
    if memory.last_at_tick is None or table.min_gap_ticks <= 0:
        return False
    return tick - memory.last_at_tick < table.min_gap_ticks


def _available(entry: EncounterEntry, memory: EncounterMemory, tick: int) -> bool:
    """Whether one entry may fire, ignoring its `when`.

    Parameters
    ----------
    entry : EncounterEntry
        The entry.
    memory : EncounterMemory
        What the table remembers.
    tick : int
        Now.

    Returns
    -------
    bool
        Whether it is on the table this time.
    """
    fired = memory.fired.get(entry.id, 0)
    if entry.once and fired:
        return False
    if entry.max_per_game is not None and fired >= entry.max_per_game:
        return False
    last = memory.last_entry_tick.get(entry.id)
    if last is not None and tick - last < entry.cooldown_ticks:
        return False
    return True


def _look_up(library: Library, qualified: str) -> EncounterTable:
    """Find a table by qualified id.

    Parameters
    ----------
    library : Library
        The loaded content.
    qualified : str
        The qualified id.

    Returns
    -------
    EncounterTable
        The table.
    """
    pack_id, local_id = qualified.split(":", 1)
    return library.pack(pack_id).encounter_tables[local_id]
