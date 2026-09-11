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

from mace.content import Library
from mace.content.ids import split
from mace.engine.state import EntityState, Modifier
from mace.model import Entity, Stat
from mace.model.entity import RelativeStat

__all__ = [
    "DEFAULT_ABILITY_MAX",
    "effective",
    "pool_bounds",
    "resolve_relative",
    "starting_pools",
]

#: The cap an ability gets when the author does not set one.
DEFAULT_ABILITY_MAX = 100.0


def resolve_relative(
    value: float | RelativeStat, library: Library, player: EntityState | None
) -> float:
    """A damage bound or stat value, as an absolute number.

    A `RelativeStat` reads the player's own stat *cap* — not their
    fluctuating current value — so a ratio means the same thing regardless
    of how depleted the player's pool happens to be at the moment something
    else asks for it.

    Parameters
    ----------
    value : float or RelativeStat
        The authored value.
    library : Library
        For resolving the player's own content definition.
    player : EntityState or None
        The player's current state. Only `None` when resolving one of the
        player's own stats before the player exists yet — content can't
        legally reach that case (a `customizable` stat can't be relative,
        and nothing else is resolved before the player), so it is treated
        as an error rather than silently handled.

    Returns
    -------
    float
        The resolved number.

    Raises
    ------
    RuleError
        If `value` is relative and there is no player to resolve it against.
    """
    if isinstance(value, RelativeStat):
        from mace.engine.conditions import RuleError  # noqa: PLC0415

        if player is None:
            raise RuleError("a relative value needs the player to already exist")
        pack_id, local_id = split(player.definition)
        assert pack_id is not None
        definition = library.pack(pack_id).entities[local_id]
        _low, high = pool_bounds(definition, player, value.stat)
        return high * value.factor
    return float(value)


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
    # `state.pools` always holds a resolved number for every declared stat
    # by the time this is called (`starting_pools()` populates it at
    # instantiation) — the fallback here is only ever reached if that
    # invariant is somehow violated, so a relative `base` falls back to 0
    # rather than crashing on a `RelativeStat` it can't resolve without a
    # library/player in scope.
    fallback = 0.0 if isinstance(declared.base, RelativeStat) else float(declared.base)
    value = float(state.pools.get(stat, fallback))
    for modifier in _modifiers_for(state, stat):
        value += modifier.add
    for modifier in _modifiers_for(state, stat):
        value *= modifier.mult

    low, high = _bounds(declared, state, stat)
    return min(max(value, low), high)


def pool_bounds(
    definition: Entity, state: EntityState, stat: str
) -> tuple[float, float]:
    """The floor and ceiling of a pool.

    Parameters
    ----------
    definition : Entity
        The content definition.
    state : EntityState
        The entity's session state, for any permanent growth to its ceiling
        (`state.stat_caps`) on top of what the content declared.
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
    return _bounds(declared, state, stat)


def starting_pools(
    definition: Entity, library: Library, player: EntityState | None
) -> dict[str, float]:
    """The pool values an entity begins a playthrough with.

    An author may set `pools` explicitly; otherwise a pool starts full at its
    `base`, which is what "a troll with 80 hitpoints" is understood to mean —
    resolved once here if `base` is a `RelativeStat`, so the stat pipeline
    downstream never needs to know the difference.

    Parameters
    ----------
    definition : Entity
        The content definition.
    library : Library
        For resolving any `RelativeStat`-valued `base` against the player's
        own stats.
    player : EntityState or None
        The player's current state. `None` only while the player's own
        entity is being instantiated — a `RelativeStat` is unreachable there
        (see `resolve_relative`).

    Returns
    -------
    dict
        Stat name to starting value.
    """
    declared = definition.stats or {}
    overrides = definition.pools or {}
    return {
        name: (
            float(overrides[name])
            if name in overrides
            else resolve_relative(stat.base, library, player)
        )
        for name, stat in declared.items()
    }


def _bounds(stat: Stat, state: EntityState, name: str) -> tuple[float, float]:
    """Read a stat's clamp range, permanent growth included.

    Parameters
    ----------
    stat : Stat
        The declared stat.
    state : EntityState
        The entity's session state.
    name : str
        The stat's name, to look its growth up by.

    Returns
    -------
    tuple of (float, float)
        Minimum and maximum.
    """
    if isinstance(stat.max, RelativeStat):
        high = state.resolved_stats.get(name, DEFAULT_ABILITY_MAX)
    else:
        high = DEFAULT_ABILITY_MAX if stat.max is None else float(stat.max)
    high += state.stat_caps.get(name, 0.0)
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
