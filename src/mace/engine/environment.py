"""What the world does to the people standing in it.

Weather that only reads nicely is scenery. Three things here turn it into
something a player has to plan around.

**Blanket effects.** A condition's `modify` reaches everyone exposed to it,
scaled by how hard it is doing whatever it is doing.

**Individual responses.** An entity's `env` block answers the weather in its
own way — an orc that fights better in the dark, a horse that will not go in
deep snow. Responses match on *tags* rather than on named conditions, so a snow
type invented three packs later affects everything that reacts to `cold`
without anyone touching it.

**Exposure.** The pool that makes a blizzard genuinely dangerous rather than
slow. It accumulates while the player is outdoors in cold, wet or severe
weather, is held off by endurance and by shelter, and past a threshold starts
taking the vital pool with it. Rest is its counterpart, and the cost of rest is
hours — which run down quest deadlines, move fronts, and let event pressure
keep rising. That is the whole point: "shelter here until it passes, or push on
cold" has to be a real decision with real stakes on both sides.

Everything is recomputed from scratch each tick and written into the ordinary
modifier list, rather than being a special case inside `stats.effective`. That
keeps the stat pipeline one readable order, and it means a debug overlay can
show *why* a troll's strength is 85 today by listing modifiers.

See docs/05-world-simulation.md § Layer 4.
"""

from __future__ import annotations

from mace.engine.conditions import all_hold
from mace.engine.context import RuleContext
from mace.engine.events import Event, StatChanged
from mace.engine.state import EntityState, Modifier
from mace.engine.world import Observation

__all__ = [
    "ENVIRONMENT",
    "EXPOSURE_TAGS",
    "EXPOSURE_THRESHOLD",
    "apply",
]

#: The `source` every environmental modifier carries, so the whole set can be
#: dropped and rebuilt without disturbing a potion or a scene's own modifier.
ENVIRONMENT = "environment"

#: The weather tags that cost you something to stand out in.
EXPOSURE_TAGS = frozenset({"cold", "wet", "severe"})

#: Exposure runs 0 to 1. Past this, it starts taking the vital pool.
EXPOSURE_THRESHOLD = 0.6

#: How much exposure a tick of the worst possible weather adds, before
#: endurance and shelter. A little over three hours of a full-intensity
#: blizzard to reach the threshold, at thirty minutes a tick.
EXPOSURE_PER_TICK = 0.09

#: How much of a tick's exposure a point of endurance holds off. At the
#: hundred-point scale stats use, a hardy character takes about half.
ENDURANCE_RELIEF = 0.006

#: How fast exposure clears under a roof, per tick.
SHELTER_RECOVERY = 0.12

#: Damage to the vital pool per tick, per unit of exposure past the threshold.
EXPOSURE_DAMAGE = 12.0


def apply(context: RuleContext, events: list[Event], *, ticks: int = 0) -> None:
    """Recompute what the weather is doing to everyone the player can see.

    Only the player and whoever is standing with them: those are the entities
    whose stats anything is about to read, and an orc three regions away whose
    stealth is not adjusted is not an observable difference. When combat
    arrives every combatant is in the room anyway.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    ticks : int
        How many ticks of world have just gone by. Zero rebuilds the modifiers
        without charging anybody another hour of standing out in it, which is
        what a caller wants when it is only making sure things are current.
    """
    observed = context.weather()
    for entity in [context.state.protagonist, *context.state.here()]:
        _reset(entity)
        _blanket(entity, observed)
        _responses(entity, context)

    if ticks and "exposure" in context.game.rules.survival:
        _exposure(context, observed, events, ticks)


def _reset(entity: EntityState) -> None:
    """Drop the modifiers the environment put on an entity last tick.

    Parameters
    ----------
    entity : EntityState
        The instance.
    """
    entity.modifiers = [
        modifier for modifier in entity.modifiers if modifier.source != ENVIRONMENT
    ]


def _blanket(entity: EntityState, observed: Observation) -> None:
    """Apply the weather's own `modify` to someone standing out in it.

    Parameters
    ----------
    entity : EntityState
        The instance.
    observed : Observation
        The weather. Indoors, it has nothing to say about anybody's stats.
    """
    condition = observed.condition
    if condition is None or observed.sheltered:
        return
    for change in condition.modify:
        entity.modifiers.append(
            Modifier(
                stat=change.stat,
                add=(change.add or 0.0) * observed.intensity,
                mult=_scaled(change.mult, observed.intensity),
                label=condition.label,
                source=ENVIRONMENT,
            )
        )


def _responses(entity: EntityState, context: RuleContext) -> None:
    """Apply an entity's own answers to the conditions it finds itself in.

    Parameters
    ----------
    entity : EntityState
        The instance.
    context : RuleContext
        The playthrough, for evaluating each response's conditions.
    """
    definition = context.definition(entity)
    for response in definition.env:
        if not all_hold(response.when, context):
            continue
        for change in response.modify:
            entity.modifiers.append(
                Modifier(
                    stat=change.stat,
                    add=change.add or 0.0,
                    mult=change.mult if change.mult is not None else 1.0,
                    label=definition.name,
                    source=ENVIRONMENT,
                )
            )


def _exposure(
    context: RuleContext,
    observed: Observation,
    events: list[Event],
    ticks: int,
) -> None:
    """Accumulate or shed exposure, and bite once there is enough of it.

    The player only. Exposure is a mechanic about the decision *the player*
    makes — push on or shelter — and giving every wandering NPC a cold-weather
    death spiral would be simulation for its own sake.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    observed : Observation
        The weather.
    events : list of Event
        Accumulator.
    ticks : int
        How many ticks of it the player just stood through.
    """
    from mace.engine.stats import effective  # noqa: PLC0415

    player = context.state.protagonist
    biting = set(observed.tags) & EXPOSURE_TAGS

    if not biting or observed.sheltered:
        player.exposure = max(0.0, player.exposure - SHELTER_RECOVERY * ticks)
        return

    endurance = effective(context.definition(player), player, "endurance")
    relief = max(0.15, 1.0 - endurance * ENDURANCE_RELIEF)
    severity = observed.intensity * (1.0 + 0.5 * (len(biting) - 1))
    player.exposure = min(
        1.0, player.exposure + EXPOSURE_PER_TICK * severity * relief * ticks
    )

    over = player.exposure - EXPOSURE_THRESHOLD
    if over <= 0:
        return

    pool = context.game.rules.vital_pool
    before = player.pools.get(pool)
    if before is None:
        return
    after = max(0.0, before - EXPOSURE_DAMAGE * over * ticks)
    if after == before:
        return
    player.pools[pool] = after
    events.append(
        StatChanged(
            actor=player.instance_id,
            stat=pool,
            delta=round(after - before, 3),
            value=round(after, 3),
            reason=observed.label or "the cold",
        )
    )


def _scaled(mult: float | None, intensity: float) -> float:
    """Scale a multiplier toward 1 by how hard the weather is trying.

    Parameters
    ----------
    mult : float or None
        The authored multiplier.
    intensity : float
        0 to 1.

    Returns
    -------
    float
        The multiplier as it applies at this intensity.
    """
    if mult is None:
        return 1.0
    return 1.0 + (mult - 1.0) * intensity
