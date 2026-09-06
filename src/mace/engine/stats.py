"""Working out what a stat is actually worth right now.

The pipeline's order is fixed, because a player who is told their speed is 33
deserves to be able to reconstruct why, and because a reordering would change
every golden file:

    stored value                     (base, plus permanent progression)
      → + equipment bonuses          (phase 3)
      → + environmental responses    (phase 2 — blizzard: speed -8)
      → + status effects             (phase 3)
      → + scene and consumable modifiers
      → clamp to [min, max]
    = effective

Only the stages that exist are applied. The rest are named here so that adding
one is a visible change to a documented order rather than a line slipped into
the middle of a function. See docs/03-content-model.md § Stats.
"""

from __future__ import annotations

from mace.engine.state import EntityState, Modifier
from mace.model import Entity, Stat

__all__ = ["DEFAULT_ABILITY_MAX", "effective", "pool_bounds", "starting_pools"]

#: The cap an ability gets when the author does not set one.
DEFAULT_ABILITY_MAX = 100.0


def effective(definition: Entity, state: EntityState, stat: str) -> float:
    """Compute a stat's current effective value.

    Parameters
    ----------
    definition : Entity
        The content the entity was instantiated from.
    state : EntityState
        The entity's session state.
    stat : str
        Which stat to compute.

    Returns
    -------
    float
        The effective value, clamped to the stat's bounds. A stat the entity
        does not have is 0 — asking is not an error, because content commonly
        asks about stats only some entities carry.
    """
    stats = definition.stats or {}
    declared = stats.get(stat)
    if declared is None:
        return 0.0

    # The stored value is the base plus whatever play has permanently done to
    # it: a pool that has been depleted, an ability that has been trained. It
    # starts at `base`, which is why an untouched entity reads as authored.
    value = float(state.pools.get(stat, declared.base))
    for modifier in _modifiers_for(state, stat):
        value += modifier.add
    for modifier in _modifiers_for(state, stat):
        value *= modifier.mult

    low, high = _bounds(declared)
    return min(max(value, low), high)


def pool_bounds(definition: Entity, stat: str) -> tuple[float, float]:
    """The floor and ceiling of a pool.

    Parameters
    ----------
    definition : Entity
        The content definition.
    stat : str
        Which pool.

    Returns
    -------
    tuple of (float, float)
        Minimum and maximum.
    """
    declared = (definition.stats or {}).get(stat)
    if declared is None:
        return 0.0, 0.0
    return _bounds(declared)


def starting_pools(definition: Entity) -> dict[str, float]:
    """The pool values an entity begins a playthrough with.

    An author may set `pools` explicitly; otherwise a pool starts full at its
    `base`, which is what "a troll with 80 hitpoints" is understood to mean.

    Parameters
    ----------
    definition : Entity
        The content definition.

    Returns
    -------
    dict
        Stat name to starting value.
    """
    declared = definition.stats or {}
    overrides = definition.pools or {}
    return {
        name: float(overrides.get(name, stat.base)) for name, stat in declared.items()
    }


def _bounds(stat: Stat) -> tuple[float, float]:
    """Read a stat's clamp range.

    Parameters
    ----------
    stat : Stat
        The declared stat.

    Returns
    -------
    tuple of (float, float)
        Minimum and maximum.
    """
    high = DEFAULT_ABILITY_MAX if stat.max is None else float(stat.max)
    return float(stat.min), high


def _modifiers_for(state: EntityState, stat: str) -> list[Modifier]:
    """Every active modifier touching one stat.

    Parameters
    ----------
    state : EntityState
        The entity's state.
    stat : str
        The stat in question.

    Returns
    -------
    list of Modifier
        Modifiers in the order they were applied, which is the order they
        compose in.
    """
    return [modifier for modifier in state.modifiers if modifier.stat == stat]
