"""The view-model: everything a front-end may look at that no event carries.

Events are things that *happened*. They are the whole story of a playthrough
and they are useless for drawing a panel, because a panel is a standing fact:
the pack in your hands, the quests in your journal, the map of what you know.
A client that rebuilt those by accumulating events would be keeping a second
copy of the world, and the first thing a second copy does is disagree with the
first.

So this is the other half of architecture boundary 4. A front-end renders the
event stream, and reads a projection for the things that stand. Like the debug
overlay it is a *projection*: it reads content and state, returns a
description, and changes nothing. Nothing is emitted because somebody is
looking, and a playthrough with a map open replays byte-identically to one
without it.

Two things it deliberately does not do. It never advances the weather —
reading never draws (`mace.engine.world.observe`), so a region the player has
not been near shows the sky it had when they last looked at it, which is also
the only honest thing to draw on a fogged map. And it never mentions a place
the player has not heard of: fog of war is a fact about the projection, not a
CSS class the client is trusted to apply.

See docs/10-clients-and-interface.md § The player interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mace.content import ContentError, Library
from mace.content.ids import split
from mace.engine.context import RuleContext
from mace.engine.economy.trade import Stall, look
from mace.engine.state import GameState, QuestStatus
from mace.engine.stats import effective, pool_bounds
from mace.engine.step import context_for
from mace.engine.world import observe
from mace.model import Entity, Location, Quest, Route

__all__ = [
    "Atlas",
    "Carried",
    "Entry",
    "Gauge",
    "Place",
    "Road",
    "Sheet",
    "Stall",
    "Underway",
    "View",
    "view",
]

#: What a location is to the player. `here` and `visited` are earned; `known`
#: is somewhere they have only been told about. Anywhere else is not in the
#: projection at all.
STANDING = ("here", "visited", "known")


@dataclass(frozen=True, slots=True)
class Gauge:
    """One stat of the protagonist's, as it reads right now.

    Attributes
    ----------
    stat : str
        The stat's name, as content spells it.
    value : float
        The effective value — stored, modified, and clamped.
    maximum : float or None
        The cap, where the author set one.
    role : {'vital', 'effort', 'ability'}
        Which of the two pools the game's rules name this as, or neither.
        Content decides; a front-end only has to know that two of these go
        beside a heart and a lightning bolt and the rest go in a list.
    """

    stat: str
    value: float
    maximum: float | None
    role: str

    def record(self) -> dict[str, Any]:
        """The gauge, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "stat": self.stat,
            "value": self.value,
            "maximum": self.maximum,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class Carried:
    """One stack of one thing in the player's pack.

    Attributes
    ----------
    item : str
        Qualified content id.
    name : str
        What to call it.
    qty : int
        How many.
    value : float or None
        The item's price anchor, where it has one.
    """

    item: str
    name: str
    qty: int
    value: float | None

    def record(self) -> dict[str, Any]:
        """The stack, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "item": self.item,
            "name": self.name,
            "qty": self.qty,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class Entry:
    """One quest, as the journal shows it.

    Attributes
    ----------
    quest : str
        Qualified content id.
    name : str
        The quest's title.
    summary : str or None
        Its one-line description.
    status : {'active', 'complete', 'failed'}
        Where it stands. Hidden quests are not entries — the journal is what
        the player knows.
    stage : str or None
        The current stage's id.
    journal : str or None
        What that stage says to read.
    started_at_tick : int or None
        When it became active, which is what a deadline counts from.
    """

    quest: str
    name: str
    summary: str | None
    status: str
    stage: str | None
    journal: str | None
    started_at_tick: int | None

    def record(self) -> dict[str, Any]:
        """The entry, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "quest": self.quest,
            "name": self.name,
            "summary": self.summary,
            "status": self.status,
            "stage": self.stage,
            "journal": self.journal,
            "startedAtTick": self.started_at_tick,
        }


@dataclass(frozen=True, slots=True)
class Place:
    """One node of the map the player can see.

    Attributes
    ----------
    location : str
        Qualified content id.
    name : str
        What to call it.
    standing : {'here', 'visited', 'known'}
        How well the player knows it.
    region : str or None
        Qualified region id.
    weather : str or None
        Qualified id of the condition last seen over it.
    sky : str or None
        What to call that condition.
    indoors : bool
        Whether it is under a roof.
    choice : int or None
        The option currently on offer that goes here, if one is. This is what
        makes a map something you can travel by rather than a picture of one:
        only the engine knows that "Take the north road" is the option that
        walks to Hagan's Castle, and a front-end that matched prompts to
        places by their wording would be guessing at content.
    x, y : float or None
        Authored map coordinates. None means the client lays it out itself,
        which is what `mapPosition` being optional is for.
    """

    location: str
    name: str
    standing: str
    region: str | None
    weather: str | None
    sky: str | None
    indoors: bool
    choice: int | None
    x: float | None
    y: float | None

    def record(self) -> dict[str, Any]:
        """The place, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "location": self.location,
            "name": self.name,
            "standing": self.standing,
            "region": self.region,
            "weather": self.weather,
            "sky": self.sky,
            "indoors": self.indoors,
            "choice": self.choice,
            "x": self.x,
            "y": self.y,
        }


@dataclass(frozen=True, slots=True)
class Road:
    """One edge of the map: a route between two places the player knows.

    Attributes
    ----------
    route : str
        Qualified content id.
    name : str or None
        What the road is called, where it is called anything.
    origin, destination : str
        Qualified location ids, as the route was written.
    bidirectional : bool
        Whether it can be walked the other way.
    ticks : int
        How long it is now — the authored length, unless something has
        lengthened or shortened it. Weather is *not* in this number: what a
        storm does to a journey is the engine's to work out when the player
        sets off.
    closed : bool
        Whether it is shut.
    reason : str or None
        What to tell a player who tries it.
    """

    route: str
    name: str | None
    origin: str
    destination: str
    bidirectional: bool
    ticks: int
    closed: bool
    reason: str | None

    def record(self) -> dict[str, Any]:
        """The road, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "route": self.route,
            "name": self.name,
            "from": self.origin,
            "to": self.destination,
            "bidirectional": self.bidirectional,
            "ticks": self.ticks,
            "closed": self.closed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Underway:
    """A road part-walked.

    Attributes
    ----------
    route : str
        Qualified route id.
    origin, destination : str
        Qualified location ids, in the direction of travel — which may be the
        reverse of the way the route was written.
    walked : float
        How far along, in route ticks. Fractional: bad weather makes a tick of
        walking worth less than a tick of road.
    ticks : int
        How long the road is.
    blocked_at : str or None
        A waypoint still stopping the player.
    """

    route: str
    origin: str
    destination: str
    walked: float
    ticks: int
    blocked_at: str | None

    def record(self) -> dict[str, Any]:
        """The journey, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "route": self.route,
            "from": self.origin,
            "to": self.destination,
            "walked": self.walked,
            "ticks": self.ticks,
            "blockedAt": self.blocked_at,
        }


@dataclass(frozen=True, slots=True)
class Atlas:
    """The map, as much of it as the player has earned.

    Attributes
    ----------
    here : str or None
        Where the player is standing. None while they are on a road.
    places : tuple of Place
        Every location they know about, in id order.
    roads : tuple of Road
        Every route between two places they know about, in id order. A road to
        somewhere unheard-of is not drawn: it would be an arrow pointing at
        the thing fog of war exists to withhold.
    journey : Underway or None
        The road being walked, if one is.
    """

    here: str | None
    places: tuple[Place, ...]
    roads: tuple[Road, ...]
    journey: Underway | None

    def record(self) -> dict[str, Any]:
        """The atlas, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "here": self.here,
            "places": [place.record() for place in self.places],
            "roads": [road.record() for road in self.roads],
            "journey": None if self.journey is None else self.journey.record(),
        }


@dataclass(frozen=True, slots=True)
class Sheet:
    """The character panel.

    Attributes
    ----------
    entity : str
        The protagonist's instance id.
    name : str
        Who they are.
    background : str or None
        The qualified background they were made with.
    stats : tuple of Gauge
        Vitals first, then effort, then abilities in name order.
    exposure : float
        0 to 1. What standing out in the weather has cost them. A number here
        on purpose: how to say it is the front-end's business, and the player
        should never see the number itself.
    """

    entity: str
    name: str
    background: str | None
    stats: tuple[Gauge, ...]
    exposure: float

    def record(self) -> dict[str, Any]:
        """The sheet, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "entity": self.entity,
            "name": self.name,
            "background": self.background,
            "stats": [gauge.record() for gauge in self.stats],
            "exposure": self.exposure,
        }


@dataclass(frozen=True, slots=True)
class View:
    """Everything standing, at one moment of one playthrough.

    Attributes
    ----------
    pack : str
        The game being played.
    tick : int
        World time.
    outcome : {'playing', 'won', 'lost'}
        Whether it is still running.
    ended_because : str or None
        What ended it.
    sheet : Sheet
        The character panel.
    carried : tuple of Carried
        The pack, in item-id order.
    journal : tuple of Entry
        Quests the player knows about, active ones first.
    atlas : Atlas
        The map.
    stall : Stall or None
        The prices in front of the player, when they are dealing with a
        merchant. A standing fact for exactly as long as they are standing at
        the counter, so a shop panel is a projection like every other panel
        rather than a client accumulating `trade.stall` events.
    """

    pack: str
    tick: int
    outcome: str
    ended_because: str | None
    sheet: Sheet
    carried: tuple[Carried, ...]
    journal: tuple[Entry, ...]
    atlas: Atlas
    stall: Stall | None = None

    def record(self) -> dict[str, Any]:
        """The whole view, JSON-safe.

        Returns
        -------
        dict
            camelCase fields, ready for an HTTP response.
        """
        return {
            "pack": self.pack,
            "tick": self.tick,
            "outcome": self.outcome,
            "endedBecause": self.ended_because,
            "sheet": self.sheet.record(),
            "carried": [stack.record() for stack in self.carried],
            "journal": [entry.record() for entry in self.journal],
            "atlas": self.atlas.record(),
            "stall": None if self.stall is None else self.stall.record(),
        }


def view(library: Library, state: GameState) -> View:
    """Project everything a front-end draws but no event tells it.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.

    Returns
    -------
    View
        The projection. Reading it changes nothing.
    """
    context = context_for(library, state)
    return View(
        pack=state.pack,
        tick=state.tick,
        outcome=state.outcome.value,
        ended_because=state.ended_because,
        sheet=_sheet(context),
        carried=_carried(context),
        journal=_journal(context),
        atlas=_atlas(context),
        stall=_stall(context),
    )


def _stall(context: RuleContext) -> Stall | None:
    """The prices the player is being quoted, if they are at a counter.

    Reading this never moves a shelf — `trade.look` projects the market the
    way the weather is read without advancing it — so a client with the shop
    panel open replays identically to one without.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    Stall or None
        The offer, or None when no stall is open.
    """
    trading = context.state.trading
    if trading is None:
        return None
    merchant = context.state.entities.get(trading)
    return None if merchant is None else look(context, merchant)


# ── The character panel ───────────────────────────────────────────────────────


def _sheet(context: RuleContext) -> Sheet:
    """Project the protagonist.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    Sheet
        The character panel.
    """
    player = context.state.protagonist
    definition = context.definition(player)
    rules = context.game.rules
    roles = {rules.vital_pool: "vital", rules.effort_pool: "effort"}

    gauges = [
        Gauge(
            stat=name,
            value=effective(definition, player, name),
            maximum=_cap(definition, name),
            role=roles.get(name, "ability"),
        )
        for name in (definition.stats or {})
    ]
    order = {"vital": 0, "effort": 1, "ability": 2}
    gauges.sort(key=lambda gauge: (order[gauge.role], gauge.stat))

    return Sheet(
        entity=player.instance_id,
        name=definition.name,
        background=context.state.background,
        stats=tuple(gauges),
        exposure=player.exposure,
    )


def _cap(definition: Entity, stat: str) -> float | None:
    """The ceiling an author set on a stat, if they set one.

    A stat with no authored `max` still has a bound — abilities default to
    100 — but a front-end drawing `26/100` beside a stat nobody capped is
    inventing a scale. So the default is reported as no cap at all.

    Parameters
    ----------
    definition : Entity
        The content definition.
    stat : str
        Which stat.

    Returns
    -------
    float or None
        The cap, or None where the author left it open.
    """
    declared = (definition.stats or {}).get(stat)
    if declared is None or declared.max is None:
        return None
    return pool_bounds(definition, stat)[1]


# ── The pack ──────────────────────────────────────────────────────────────────


def _carried(context: RuleContext) -> tuple[Carried, ...]:
    """Project the player's inventory.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    tuple of Carried
        One stack per item, in id order.
    """
    inventory = context.state.protagonist.inventory
    stacks = []
    for item in sorted(inventory):
        if inventory[item] <= 0:
            continue
        found = _entity(context, item)
        stacks.append(
            Carried(
                item=item,
                name=item if found is None else found.name,
                qty=int(inventory[item]),
                value=(
                    None
                    if found is None or found.item is None
                    else found.item.base_value
                ),
            )
        )
    return tuple(stacks)


# ── The journal ───────────────────────────────────────────────────────────────

#: Quests are listed by how much they want the player's attention.
QUEST_ORDER = {
    QuestStatus.ACTIVE: 0,
    QuestStatus.COMPLETE: 1,
    QuestStatus.FAILED: 2,
}


def _journal(context: RuleContext) -> tuple[Entry, ...]:
    """Project the quests the player knows about.

    A hidden quest is not an entry. The journal is what the player knows, and
    a greyed-out line saying "??? — hidden" tells them a secret exists, which
    is most of the secret.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    tuple of Entry
        Active quests first, then complete, then failed; by id within each.
    """
    entries = []
    for quest_id in sorted(context.state.quests):
        progress = context.state.quests[quest_id]
        if progress.status is QuestStatus.HIDDEN:
            continue
        found = _quest(context, quest_id)
        stage = None
        if found is not None and progress.stage is not None:
            stage = next(
                (one for one in found.stages if one.id == progress.stage), None
            )
        entries.append(
            Entry(
                quest=quest_id,
                name=quest_id if found is None else found.name,
                summary=None if found is None else found.summary,
                status=progress.status.value,
                stage=progress.stage,
                journal=None if stage is None else stage.journal,
                started_at_tick=progress.started_at_tick,
            )
        )
    entries.sort(
        key=lambda entry: (QUEST_ORDER[QuestStatus(entry.status)], entry.quest)
    )
    return tuple(entries)


# ── The map ───────────────────────────────────────────────────────────────────


def _atlas(context: RuleContext) -> Atlas:
    """Project as much of the map as the player has earned.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    Atlas
        Places, roads between them, and the road being walked.
    """
    state = context.state
    known = {
        qualified: definition
        for qualified, definition in _locations(context).items()
        if qualified in state.revealed
    }
    ways = _ways_out(context)
    places = tuple(
        _place(context, qualified, known[qualified], ways)
        for qualified in sorted(known)
    )
    roads = tuple(
        road
        for road in (
            _road(context, qualified, definition)
            for qualified, definition in sorted(_routes(context).items())
        )
        if road is not None and road.origin in known and road.destination in known
    )
    return Atlas(
        here=state.location,
        places=places,
        roads=roads,
        journey=_underway(context),
    )


def _ways_out(context: RuleContext) -> dict[str, int]:
    """Which offered option travels to which place.

    Only options that can actually be taken are here. An option the player
    cannot afford is worth showing on a menu, where the author's hint says
    why; it is not worth making a place on the map look reachable.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    dict
        Qualified location id to the index of the option that goes there. The
        first one wins, which is the one a player would reach for.
    """
    pending = context.state.pending
    if pending is None:
        return {}

    ways: dict[str, int] = {}
    for index, option in enumerate(pending.options):
        if option.travel is None or not option.available:
            continue
        ways.setdefault(context.qualify(option.travel, "locations"), index)
    return ways


def _place(
    context: RuleContext,
    qualified: str,
    definition: Location,
    ways: dict[str, int],
) -> Place:
    """Project one location the player knows about.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The location's qualified id.
    definition : Location
        Its content.
    ways : dict
        Location id to the offered option that goes there.

    Returns
    -------
    Place
        The node.
    """
    state = context.state
    if qualified == state.location:
        standing = "here"
    elif qualified in state.visited:
        standing = "visited"
    else:
        standing = "known"

    seen = observe(
        context.library,
        state,
        context.clock,
        state.pack,
        definition,
        context.game.world.start_region,
    )
    return Place(
        location=qualified,
        name=definition.name,
        standing=standing,
        region=seen.region,
        weather=seen.qualified,
        sky=None if seen.condition is None else seen.condition.name,
        indoors=definition.indoors,
        choice=ways.get(qualified),
        x=None if definition.map_position is None else definition.map_position.x,
        y=None if definition.map_position is None else definition.map_position.y,
    )


def _road(context: RuleContext, qualified: str, definition: Route) -> Road | None:
    """Project one route.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The route's qualified id.
    definition : Route
        Its content.

    Returns
    -------
    Road or None
        The edge, or None if either end names nothing — which validation
        catches long before play, and a save replayed against edited content
        can still reach.
    """
    pack, _ = split(qualified)
    within = pack or context.state.pack
    try:
        origin = context.library.resolve(definition.origin, "locations", within=within)
        destination = context.library.resolve(
            definition.destination, "locations", within=within
        )
    except ContentError:
        return None

    happened = context.state.routes.get(qualified)
    return Road(
        route=qualified,
        name=definition.name,
        origin=origin,
        destination=destination,
        bidirectional=definition.bidirectional,
        ticks=(
            definition.ticks
            if happened is None or happened.ticks is None
            else happened.ticks
        ),
        closed=bool(happened is not None and happened.closed),
        reason=None if happened is None else happened.reason,
    )


def _underway(context: RuleContext) -> Underway | None:
    """Project the road being walked, if one is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    Underway or None
        The journey.
    """
    journey = context.state.journey
    if journey is None:
        return None
    found = _route(context, journey.route)
    happened = context.state.routes.get(journey.route)
    ticks = 0 if found is None else found.ticks
    if happened is not None and happened.ticks is not None:
        ticks = happened.ticks
    return Underway(
        route=journey.route,
        origin=journey.origin,
        destination=journey.destination,
        walked=journey.progress,
        ticks=ticks,
        blocked_at=journey.blocked_at,
    )


# ── Reaching into content ─────────────────────────────────────────────────────


def _locations(context: RuleContext) -> dict[str, Location]:
    """Every location in every loaded pack, by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    dict
        Qualified id to definition.
    """
    return {
        f"{pack.id}:{local}": definition
        for pack in context.library.packs
        for local, definition in pack.locations.items()
    }


def _routes(context: RuleContext) -> dict[str, Route]:
    """Every route in every loaded pack, by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    dict
        Qualified id to definition.
    """
    return {
        f"{pack.id}:{local}": definition
        for pack in context.library.packs
        for local, definition in pack.routes.items()
    }


def _entity(context: RuleContext, qualified: str) -> Entity | None:
    """Look up an entity definition by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The id.

    Returns
    -------
    Entity or None
        The definition, or None if it names nothing.
    """
    pack, local = split(qualified)
    if pack is None or pack not in context.library.by_id:
        return None
    return context.library.by_id[pack].entities.get(local)


def _quest(context: RuleContext, qualified: str) -> Quest | None:
    """Look up a quest definition by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The id.

    Returns
    -------
    Quest or None
        The definition, or None if it names nothing.
    """
    pack, local = split(qualified)
    if pack is None or pack not in context.library.by_id:
        return None
    return context.library.by_id[pack].quests.get(local)


def _route(context: RuleContext, qualified: str) -> Route | None:
    """Look up a route definition by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The id.

    Returns
    -------
    Route or None
        The definition, or None if it names nothing.
    """
    pack, local = split(qualified)
    if pack is None or pack not in context.library.by_id:
        return None
    return context.library.by_id[pack].routes.get(local)
