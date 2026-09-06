"""The world as a rule sees it: what content can ask about, and how to find it.

Two jobs. The first is turning a reference an author wrote — `gorm`,
`fantasy.core:gold`, `player` — into the thing it means in this playthrough.
The second is building the mapping an expression reads its dotted paths from.

Both are here rather than spread through the rules so that "what content can
see" is one readable list. Content cannot reach anything not in it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mace.content import ContentError, Library
from mace.content.ids import split
from mace.engine.state import EntityState, GameState
from mace.engine.stats import effective, pool_bounds
from mace.engine.world import Clock, Observation, observe
from mace.model import Entity, Game, Location
from mace.model.base import RESERVED_ACTORS

__all__ = ["RuleContext"]


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a condition or effect is allowed to look at.

    Attributes
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    clock : Clock
        World time.
    game : Game
        The game manifest, for the rules a playthrough is judged by.
    """

    library: Library
    state: GameState
    clock: Clock
    game: Game

    # ── Resolving what an author wrote ────────────────────────────────────

    def qualify(self, reference: str, collection: str) -> str:
        """Turn a reference into a fully qualified content id.

        Parameters
        ----------
        reference : str
            As the author wrote it, bare or qualified.
        collection : str
            Which collection it points into.

        Returns
        -------
        str
            The qualified id.

        Raises
        ------
        ContentError
            If it names nothing. Validation catches these before play, so
            reaching one at runtime means content changed underneath a save.
        """
        return self.library.resolve(reference, collection, within=self.state.pack)

    def definition(self, entity: EntityState) -> Entity:
        """The content an entity instance was made from.

        Parameters
        ----------
        entity : EntityState
            The instance.

        Returns
        -------
        Entity
            Its definition.
        """
        pack_id, local_id = split(entity.definition)
        assert pack_id is not None
        found = self.library.pack(pack_id).entities[local_id]
        return found

    def actor(self, reference: str) -> EntityState | None:
        """Find the entity instance a reference names.

        `player` is the protagonist, whoever that is this playthrough. Anything
        else names a definition; where a definition has several instances the
        one in the player's location wins, because content that says `gorm`
        while standing in front of one means that one.

        Parameters
        ----------
        reference : str
            As the author wrote it.

        Returns
        -------
        EntityState or None
            The instance, or None if nothing matches.
        """
        if reference in RESERVED_ACTORS:
            return self.state.protagonist
        try:
            qualified = self.qualify(reference, "entities")
        except ContentError:
            return None

        matches = [
            entity
            for _key, entity in sorted(self.state.entities.items())
            if entity.definition == qualified
        ]
        if not matches:
            return None
        here = self.state.location
        return next((e for e in matches if e.location == here), matches[0])

    def here(self) -> Location | None:
        """The location definition the player is standing in.

        Returns
        -------
        Location or None
            The definition, or None when the player is nowhere yet.
        """
        where = self.state.location
        if where is None:
            return None
        pack_id, local_id = split(where)
        assert pack_id is not None
        return self.library.pack(pack_id).locations.get(local_id)

    def weather(self) -> Observation:
        """What the sky is doing where the player is standing.

        Reading never advances the chain — `mace.engine.world.sync` does that,
        at the points where time moves — so a condition asked twice in one
        step gives the same answer both times.

        Returns
        -------
        Observation
            The weather, with the location's override, its roof, and any
            active world event's standing changes already taken into account.
        """
        from mace.engine.world import events  # noqa: PLC0415

        observed = observe(
            self.library,
            self.state,
            self.clock,
            self.state.pack,
            self.here(),
            self.game.world.start_region,
        )
        if not self.state.events:
            return observed
        return observed.under(events.standing(self, observed.region))

    def light(self) -> float:
        """How much light there is, all told.

        The day part's own light, cut by what the sky is doing, unless an
        event has put it out entirely — which is what an eclipse is.

        Returns
        -------
        float
            0 to 1.
        """
        observed = self.weather()
        if self.state.light_override is not None:
            return self.state.light_override
        if observed.light_override is not None:
            return observed.light_override
        return self.clock.light(self.state.tick) * observed.visibility

    def item_id(self, reference: str) -> str | None:
        """Qualify an item reference for inventory keys.

        Parameters
        ----------
        reference : str
            As the author wrote it.

        Returns
        -------
        str or None
            The qualified id, or None if it names nothing.
        """
        try:
            return self.qualify(reference, "entities")
        except ContentError:
            return None

    # ── What an expression can read ───────────────────────────────────────

    def expression_context(self) -> dict[str, Any]:
        """Build the mapping expressions read their paths from.

        The roots are `player`, `world`, `vars`, and every entity whose
        definition has exactly one instance in play, under its local id. An
        ambiguous name is left out rather than guessed at: a path that cannot
        be answered is an error, and a wrong answer is worse.

        Returns
        -------
        dict
            Root name to value.
        """
        context: dict[str, Any] = {
            "player": self.entity_view(self.state.protagonist),
            "world": self.world_view(),
            "vars": dict(self.state.variables),
        }

        by_definition: dict[str, list[EntityState]] = {}
        for _key, entity in sorted(self.state.entities.items()):
            by_definition.setdefault(entity.definition, []).append(entity)

        for qualified, instances in by_definition.items():
            _pack, local_id = split(qualified)
            if len(instances) != 1 or local_id in context:
                continue
            context[local_id] = self.entity_view(instances[0])
        return context

    def world_view(self) -> dict[str, Any]:
        """What `world.*` reads.

        Returns
        -------
        dict
            Time now — tick, day, season, day part, light — and the weather
            once there is any to report.
        """
        tick = self.state.tick
        weather = self.weather()
        return {
            "tick": tick,
            "day": self.clock.day(tick),
            "dayPart": self.clock.day_part(tick),
            "time": self.clock.clock_time(tick),
            "minutesPerTick": self.clock.minutes_per_tick,
            "ticksPerDay": self.clock.ticks_per_day,
            "season": self.clock.season(tick).id,
            "dayOfYear": self.clock.day_of_year(tick) + 1,
            "dayName": self.clock.day_name(tick) or "",
            "monthName": self.clock.month_name(tick) or "",
            # The day part's light, cut by what the sky is doing. One number
            # for stealth, ranged accuracy, encounter detection, and which
            # description variant is shown.
            "light": self.light(),
            "skyLight": self.clock.light(tick),
            # A list, so `'rain' in world.weather` reads naturally and a place
            # with no weather answers false rather than erroring.
            "news": sum(1 for item in self.state.news if not item.told),
            "weather": [weather.id] if weather.id else [],
            "weatherTags": list(weather.tags),
            "temperature": weather.temperature,
            "visibility": weather.visibility,
            "region": _local(weather.region),
            "indoors": weather.sheltered,
        }

    def entity_view(self, entity: EntityState) -> dict[str, Any]:
        """What an entity root reads.

        Parameters
        ----------
        entity : EntityState
            The instance to describe.

        Returns
        -------
        dict
            Its readable attributes. Stats are effective values; pools carry
            their current, minimum, and maximum.
        """
        definition = self.definition(entity)
        declared = definition.stats or {}

        pools: dict[str, Mapping[str, float]] = {}
        for name in declared:
            low, high = pool_bounds(definition, name)
            pools[name] = {
                "current": entity.pools.get(name, 0.0),
                "min": low,
                "max": high,
            }

        return {
            "id": definition.id,
            "name": definition.name,
            "kind": definition.kind,
            "tags": list(definition.tags),
            "flags": sorted(entity.flags),
            "exposure": entity.exposure,
            "disposition": entity.disposition,
            "location": _local(entity.location),
            "stats": {name: effective(definition, entity, name) for name in declared},
            "pools": pools,
            "inventory": {
                _local(item): quantity for item, quantity in entity.inventory.items()
            },
            "equipment": {
                slot: _local(item) for slot, item in entity.equipment.items()
            },
            "custom": dict(definition.custom or {}),
        }


def _local(qualified: str | None) -> str:
    """Strip the pack from a qualified id, for readability in expressions.

    Parameters
    ----------
    qualified : str or None
        A qualified id.

    Returns
    -------
    str
        The local part, or an empty string for None.
    """
    if qualified is None:
        return ""
    _pack, local_id = split(qualified)
    return local_id
