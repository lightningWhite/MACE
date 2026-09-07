"""Events: everything the engine has to say, in the order it happened.

A front-end's whole job is turning these into characters or pixels. The CLI
prints `narrate` and waits on `pause`; the browser will animate the same event.
Neither reaches into engine state to find out what happened, which is what lets
one engine drive a terminal, a browser, and eventually a server.

Every event renders to a plain JSON-safe record, because the golden replay
tests compare recorded event streams and a second implementation of this engine
has to be able to produce the same ones.
See docs/02-architecture.md § Boundary 3.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

__all__ = [
    "CharacterCreated",
    "ChoiceOffered",
    "ChoicesOffered",
    "CombatBegan",
    "CombatEnded",
    "CombatResolved",
    "CombatTell",
    "EncounterFired",
    "Event",
    "FlagChanged",
    "GameOver",
    "Haggled",
    "NewsHeard",
    "PricesShocked",
    "LocationRevealed",
    "InventoryChanged",
    "Moved",
    "Narrated",
    "QuestUpdated",
    "ResponseOffered",
    "RouteChanged",
    "RuleFailed",
    "SceneEntered",
    "StallOpened",
    "Traded",
    "TravelInterrupted",
    "TravelLeg",
    "StatChanged",
    "TimePassed",
    "Unsupported",
    "VariableChanged",
    "WorldEvent",
    "FrontMoved",
    "WeatherChanged",
    "WorldStatus",
    "records",
]


@dataclass(frozen=True, slots=True)
class Event:
    """Base class for everything the engine emits."""

    kind: ClassVar[str] = "event"

    def payload(self) -> dict[str, Any]:
        """The event's fields, without its kind.

        Returns
        -------
        dict
            JSON-safe values.
        """
        return {}

    def record(self) -> dict[str, Any]:
        """The event as it appears in a golden file.

        Returns
        -------
        dict
            The kind, then the payload.
        """
        return {"kind": self.kind, **self.payload()}


@dataclass(frozen=True, slots=True)
class CharacterCreated(Event):
    """The protagonist was made before the first tick.

    Emitted only when the player answered something — a game that offers
    neither backgrounds nor creation points opens on its first line of prose,
    the way it always did.

    Attributes
    ----------
    background : str or None
        The qualified background chosen.
    spend : dict
        Stat name to creation points put into it.
    """

    kind: ClassVar[str] = "character.created"
    background: str | None = None
    spend: Mapping[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "background": self.background,
            "spend": {name: self.spend[name] for name in sorted(self.spend)},
        }


@dataclass(frozen=True, slots=True)
class Narrated(Event):
    """A line of prose.

    Attributes
    ----------
    text : str
        What the player reads.
    pause : bool
        Whether the front-end waits before going on. Where the beats fall is
        the author's call; how to wait is the front-end's.
    """

    kind: ClassVar[str] = "narrate"
    text: str
    pause: bool = False

    def payload(self) -> dict[str, Any]:
        return {"text": self.text, "pause": self.pause}


@dataclass(frozen=True, slots=True)
class ChoiceOffered:
    """One option in a `choices` event.

    Attributes
    ----------
    prompt : str
        The option text.
    available : bool
        Whether it can be taken.
    hint : str or None
        Why not, when it cannot.
    """

    prompt: str
    available: bool = True
    hint: str | None = None

    def record(self) -> dict[str, Any]:
        """The option as it appears in a golden file.

        Returns
        -------
        dict
            JSON-safe values.
        """
        return {"prompt": self.prompt, "available": self.available, "hint": self.hint}


@dataclass(frozen=True, slots=True)
class ChoicesOffered(Event):
    """The game is waiting for the player to pick something.

    Attributes
    ----------
    scene : str
        The qualified id of the scene offering them.
    options : tuple of ChoiceOffered
        The options, in presentation order. The index into this tuple is what
        a `Choose` action names.
    """

    kind: ClassVar[str] = "choices"
    scene: str
    options: tuple[ChoiceOffered, ...] = ()

    def payload(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "options": [option.record() for option in self.options],
        }


@dataclass(frozen=True, slots=True)
class SceneEntered(Event):
    """A scene began.

    Attributes
    ----------
    scene : str
        Its qualified id.
    """

    kind: ClassVar[str] = "scene.entered"
    scene: str

    def payload(self) -> dict[str, Any]:
        return {"scene": self.scene}


@dataclass(frozen=True, slots=True)
class Moved(Event):
    """The player is somewhere else.

    Attributes
    ----------
    origin : str or None
        Where they were.
    destination : str
        Where they are.
    route : str or None
        The route travelled, if they walked rather than were moved.
    ticks : int
        How long it took.
    """

    kind: ClassVar[str] = "moved"
    origin: str | None
    destination: str
    route: str | None = None
    ticks: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "from": self.origin,
            "to": self.destination,
            "route": self.route,
            "ticks": self.ticks,
        }


@dataclass(frozen=True, slots=True)
class EncounterFired(Event):
    """Something happened on the road, or in a room the player lingered in.

    Emitted before whatever it turned into — the scene, or the fight — so a
    debug overlay can show the roll next to its consequence. A player-facing
    front-end has no reason to render this at all: the encounter *is* the
    scene that follows.

    Attributes
    ----------
    table : str
        Qualified id of the table that produced it.
    entry : str
        The entry's id.
    chance : float
        The effective chance it was rolled against, after anti-clumping.
    where : str or None
        Qualified id of the location or route it happened on.
    """

    kind: ClassVar[str] = "encounter"
    table: str
    entry: str
    chance: float = 0.0
    where: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "entry": self.entry,
            "chance": self.chance,
            "where": self.where,
        }


@dataclass(frozen=True, slots=True)
class TravelLeg(Event):
    """One stretch of a journey went by.

    Attributes
    ----------
    route : str
        Qualified route id.
    leg : int
        Which leg of the road this was, counting from one.
    of : int
        How many legs the road has, before weather lengthens it.
    waypoint : str or None
        A place reached on this leg, if one was.
    text : str or None
        A line of road flavor, chosen for the hour and the weather.
    """

    kind: ClassVar[str] = "travel.leg"
    route: str
    leg: int
    of: int
    waypoint: str | None = None
    text: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "leg": self.leg,
            "of": self.of,
            "waypoint": self.waypoint,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class TravelInterrupted(Event):
    """A journey stopped partway, and can be carried on later.

    Attributes
    ----------
    route : str
        Qualified route id.
    at : str
        Where the player is now — the waypoint they were stopped at.
    destination : str
        Where they were going.
    remaining : float
        How much road is left, in route ticks.
    reason : str or None
        What stopped them.
    """

    kind: ClassVar[str] = "travel.interrupted"
    route: str
    at: str
    destination: str
    remaining: float = 0.0
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "at": self.at,
            "destination": self.destination,
            "remaining": self.remaining,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TimePassed(Event):
    """The world clock moved.

    Attributes
    ----------
    tick : int
        The new tick.
    day : int
        Which day that is.
    day_part : str
        Which part of it.
    season : str
        Which season the calendar says it is.
    elapsed : int
        How many ticks passed.
    """

    kind: ClassVar[str] = "world.time"
    tick: int
    day: int
    day_part: str
    season: str = ""
    elapsed: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "day": self.day,
            "dayPart": self.day_part,
            "season": self.season,
            "elapsed": self.elapsed,
        }


@dataclass(frozen=True, slots=True)
class FrontMoved(Event):
    """A weather system formed, crossed into a region, or died.

    Mostly for the map view and for debugging: the *player's* experience of a
    front is the omen it throws ahead of itself and the weather it brings, not
    a notification that one exists. A front-end that shows this as a message
    has misread the whole layer.

    Attributes
    ----------
    front : str
        The front's session id.
    definition : str
        Qualified id of the front's content definition.
    phase : str
        `formed`, `moved`, or `faded`.
    at : str
        The region it is over.
    ahead : str or None
        The region it is heading for.
    intensity : float
        0 to 1, decaying with age.
    """

    kind: ClassVar[str] = "weather.front"
    front: str
    definition: str
    phase: str = "formed"
    at: str = ""
    ahead: str | None = None
    intensity: float = 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "front": self.front,
            "definition": self.definition,
            "phase": self.phase,
            "at": self.at,
            "ahead": self.ahead,
            "intensity": self.intensity,
        }


@dataclass(frozen=True, slots=True)
class WeatherChanged(Event):
    """The sky over a region started doing something else.

    Emitted when the condition changes, never every tick. Weather that is
    doing what it was doing is not news, and a front-end that had to filter
    a message a tick would end up inventing this rule for itself.

    Attributes
    ----------
    region : str
        The region's qualified id.
    condition : str
        The new condition's qualified id.
    name : str
        What to call it — "light snow".
    intensity : float
        0 to 1.
    tags : tuple of str
        `wet`, `cold`, `dark`.
    visibility : float
        0 to 1, the multiplier on the day part's light.
    temperature : float or None
        Now, at this region's elevation.
    text : str or None
        The condition's own line, when the author wrote one.
    """

    kind: ClassVar[str] = "weather.changed"
    region: str
    condition: str
    name: str = ""
    intensity: float = 0.0
    tags: tuple[str, ...] = ()
    visibility: float = 1.0
    temperature: float | None = None
    text: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "condition": self.condition,
            "name": self.name,
            "intensity": self.intensity,
            "tags": list(self.tags),
            "visibility": self.visibility,
            "temperature": self.temperature,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class WorldStatus(Event):
    """Where and when the player is, for a status line.

    The one event that is a projection rather than a happening. A front-end
    needs to render `Day 3 · dusk · Fenmoor · light rain` somewhere permanent,
    and the alternative — letting the UI reach into engine state for it — is
    the boundary this whole event protocol exists to hold. It is emitted after
    every action, so the line is never stale.

    Attributes
    ----------
    tick : int
        World time.
    day : int
        Which day.
    day_part : str
        Which part of it.
    season : str
        Which season.
    time : str
        The wall-clock reading.
    location : str or None
        Qualified id of where the player is.
    place : str
        What that place is called.
    region : str or None
        Qualified id of the region it is in.
    weather : str or None
        Qualified id of the condition in force.
    sky : str
        What to call the weather. Empty where there is none.
    temperature : float or None
        Now.
    light : float
        The day part's light after the weather has had its share, 0 to 1.
    indoors : bool
        Whether the player is under a roof.
    exposure : float
        0 to 1. What standing out in it has cost the player so far. A number
        here rather than a word on purpose: how to say it is the front-end's
        business, and the player should never see the number itself.
    """

    kind: ClassVar[str] = "world.status"
    tick: int
    day: int
    day_part: str
    season: str
    time: str
    location: str | None = None
    place: str = ""
    region: str | None = None
    weather: str | None = None
    sky: str = ""
    temperature: float | None = None
    light: float = 1.0
    indoors: bool = False
    exposure: float = 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "day": self.day,
            "dayPart": self.day_part,
            "season": self.season,
            "time": self.time,
            "location": self.location,
            "place": self.place,
            "region": self.region,
            "weather": self.weather,
            "sky": self.sky,
            "temperature": self.temperature,
            "light": self.light,
            "indoors": self.indoors,
            "exposure": self.exposure,
        }


@dataclass(frozen=True, slots=True)
class StatChanged(Event):
    """A stat or pool moved.

    Attributes
    ----------
    actor : str
        The entity's instance id.
    stat : str
        Which stat.
    delta : float
        How much it moved, after clamping — so a heal that overflows reports
        what actually happened rather than what was asked for.
    value : float
        Where it ended up.
    reason : str or None
        What did it, for the front-end to show.
    """

    kind: ClassVar[str] = "stat.changed"
    actor: str
    stat: str
    delta: float
    value: float
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "stat": self.stat,
            "delta": self.delta,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class InventoryChanged(Event):
    """Something was gained or lost.

    Attributes
    ----------
    actor : str
        The entity's instance id.
    item : str
        The item's qualified content id.
    delta : int
        How many were gained, or lost as a negative.
    quantity : int
        How many are held now.
    """

    kind: ClassVar[str] = "inventory.changed"
    actor: str
    item: str
    delta: int
    quantity: int

    def payload(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "item": self.item,
            "delta": self.delta,
            "quantity": self.quantity,
        }


@dataclass(frozen=True, slots=True)
class StallOpened(Event):
    """A merchant laid its prices out.

    Carries the whole price list rather than a reference to one, because a
    price is a fact about a moment: what the shelf held when the player asked.
    A front-end that went and looked it up again a second later would be
    drawing a different market from the one the player is standing in.

    Attributes
    ----------
    merchant : str
        The merchant's instance id — what a `trade` action is addressed to.
    name : str
        What to call them. Carried rather than looked up, because resolving an
        instance id to a name is reaching into state, which is the one thing a
        front-end may not do.
    market : str
        Qualified market id. Empty for a caravan, which deals for nowhere.
    mobile : bool
        Whether this is a caravan carrying its own prices.
    currency : str
        Qualified item id trade is settled in.
    purse : int or None
        What the merchant can pay out. None is bottomless — a stall backed by
        a whole town is not somebody whose pockets can be emptied.
    goods : tuple of dict
        One row per good: id, name, unit prices, shelf, and what the player
        already carries.
    """

    kind: ClassVar[str] = "trade.stall"
    merchant: str
    market: str
    currency: str
    name: str = ""
    mobile: bool = False
    purse: int | None = None
    goods: tuple[Mapping[str, Any], ...] = ()

    def payload(self) -> dict[str, Any]:
        return {
            "merchant": self.merchant,
            "name": self.name,
            "market": self.market,
            "mobile": self.mobile,
            "currency": self.currency,
            "purse": self.purse,
            "goods": [dict(row) for row in self.goods],
        }


@dataclass(frozen=True, slots=True)
class Haggled(Event):
    """The player pushed on a price, and something came of it.

    Attributes
    ----------
    merchant : str
        The merchant's instance id.
    name : str
        What to call them.
    result : {'gave', 'held', 'soured'}
        Which of the three things happened.
    swing : float
        How far the bill has been moved in the player's favour. Negative
        after a souring.
    pushes : int
        How many times the player has pressed.
    leverage : bool
        Whether they had a better price elsewhere to point at, and did.
    """

    kind: ClassVar[str] = "trade.haggled"
    merchant: str
    name: str
    result: str
    swing: float
    pushes: int
    leverage: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "merchant": self.merchant,
            "name": self.name,
            "result": self.result,
            "swing": round(self.swing, 4),
            "pushes": self.pushes,
            "leverage": self.leverage,
        }


@dataclass(frozen=True, slots=True)
class Traded(Event):
    """Goods and coin changed hands.

    The `inventory.changed` events beside this one say what moved; this says
    what the deal *was*, which is the thing a journal or a ledger wants and
    cannot reconstruct from two stack sizes.

    Attributes
    ----------
    merchant : str
        The merchant's instance id.
    market : str
        Qualified market id.
    good : str
        Qualified good id.
    item : str
        Qualified item id.
    qty : int
        Units, always positive.
    sell : bool
        Whether the player was the one handing goods over.
    coin : int
        Whole currency that changed hands.
    """

    kind: ClassVar[str] = "trade.done"
    merchant: str
    market: str
    good: str
    item: str
    qty: int
    sell: bool
    coin: int

    def payload(self) -> dict[str, Any]:
        return {
            "merchant": self.merchant,
            "market": self.market,
            "good": self.good,
            "item": self.item,
            "qty": self.qty,
            "sell": self.sell,
            "coin": self.coin,
        }


@dataclass(frozen=True, slots=True)
class FlagChanged(Event):
    """A flag was raised or cleared.

    Attributes
    ----------
    entity : str
        The entity's instance id.
    flag : str
        Which flag.
    value : bool
        Its new value.
    """

    kind: ClassVar[str] = "flag.changed"
    entity: str
    flag: str
    value: bool

    def payload(self) -> dict[str, Any]:
        return {"entity": self.entity, "flag": self.flag, "value": self.value}


@dataclass(frozen=True, slots=True)
class VariableChanged(Event):
    """A game variable was set.

    Attributes
    ----------
    name : str
        The variable.
    value : object
        Its new value.
    """

    kind: ClassVar[str] = "var.changed"
    name: str
    value: Any

    def payload(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


@dataclass(frozen=True, slots=True)
class LocationRevealed(Event):
    """A place the player did not know about is now on the map.

    Attributes
    ----------
    location : str
        Its qualified id.
    """

    kind: ClassVar[str] = "location.revealed"
    location: str

    def payload(self) -> dict[str, Any]:
        return {"location": self.location}


@dataclass(frozen=True, slots=True)
class RouteChanged(Event):
    """A road closed, reopened, or got longer.

    The aftermath of a world event is what separates it from a weather
    condition: a landslide that shuts a pass for the rest of the game leaves
    the map permanently different, and the map view has to know.

    Attributes
    ----------
    route : str
        Qualified route id.
    closed : bool
        Whether it is shut.
    ticks : int or None
        Its length now, if something changed it.
    reason : str or None
        What to tell a player who tries it.
    """

    kind: ClassVar[str] = "route.changed"
    route: str
    closed: bool = False
    ticks: int | None = None
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "closed": self.closed,
            "ticks": self.ticks,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PricesShocked(Event):
    """Something has moved what a class of goods is worth, somewhere.

    A front-end has no reason to render this as prose — the merchant's own
    remark is where a player hears about it, and the price itself is where
    they feel it. It exists so a debug overlay, a journal, and a second
    implementation of this engine can all see the same world changing.

    Attributes
    ----------
    region, market : str or None
        Qualified ids narrowing where it landed.
    category, good : str or None
        What it landed on.
    mult : float
        What it does to a price at its peak.
    ticks : int
        How long it takes to fade to nothing.
    reason : str or None
        What to call it.
    """

    kind: ClassVar[str] = "market.shocked"
    mult: float
    ticks: int
    region: str | None = None
    market: str | None = None
    category: str | None = None
    good: str | None = None
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "market": self.market,
            "category": self.category,
            "good": self.good,
            "mult": self.mult,
            "ticks": self.ticks,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class QuestUpdated(Event):
    """A quest started, advanced, finished, or failed.

    Attributes
    ----------
    quest : str
        Its qualified id.
    status : str
        `hidden`, `active`, `complete`, or `failed`.
    stage : str or None
        The current stage.
    journal : str or None
        What to write in the journal.
    """

    kind: ClassVar[str] = "quest.updated"
    quest: str
    status: str
    stage: str | None = None
    journal: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "quest": self.quest,
            "status": self.status,
            "stage": self.stage,
            "journal": self.journal,
        }


@dataclass(frozen=True, slots=True)
class WorldEvent(Event):
    """A world event moved through one beat of its life.

    The narration that comes with it arrives as ordinary `narrate` events, on
    purpose. An omen surfaced as a system message is not an omen; there is no
    pressure bar, and the player should never see a number. This event is for
    the map, the journal, and the debug overlay.

    Attributes
    ----------
    event : str
        Qualified id of the event.
    phase : str
        `building`, `omen`, `imminent`, `onset`, or `aftermath`.
    region : str or None
        Where it happened.
    visible : bool
        Whether the player was somewhere they would have noticed.
    """

    kind: ClassVar[str] = "world.event"
    event: str
    phase: str
    region: str | None = None
    visible: bool = True

    def payload(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "phase": self.phase,
            "region": self.region,
            "visible": self.visible,
        }


@dataclass(frozen=True, slots=True)
class NewsHeard(Event):
    """Something that happened out of sight has reached the player.

    News carries its age, because a rumour three days old and two regions away
    should arrive imperfect — which is free atmosphere and makes the player's
    information feel like a medieval world's rather than like a notification.

    Attributes
    ----------
    event : str
        Qualified id of what happened.
    days_old : int
        How long ago, in days.
    region : str or None
        Where it happened.
    """

    kind: ClassVar[str] = "world.news"
    event: str
    days_old: int = 0
    region: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "daysOld": self.days_old,
            "region": self.region,
        }


# ── Combat ────────────────────────────────────────────────────────────────────
#
# Four events carry a whole fight, and between them they say everything a
# front-end needs without it ever asking the engine what the state is. The CLI
# renders `combat.tell` as a line of text with a keypress deadline; the browser
# renders the same event as a shrinking bar with the sweet zone marked. Same
# event, same engine, same fairness — which is the point of the arrangement.


@dataclass(frozen=True, slots=True)
class CombatBegan(Event):
    """A fight started.

    Attributes
    ----------
    combat : str
        The fight's session id, which also names its random stream.
    mode : str
        `reflex`, `tactical`, or `auto`.
    combatants : tuple of tuple
        Instance id, name, side, and profile id for everyone in it.
    can_flee : bool
        Whether running is allowed at all.
    matrix : tuple of tuple
        Move type to the defense types that beat it, for every attack anyone
        in this fight can throw. Published rather than left for a front-end to
        work out, because the matrix is *content* and a UI that reconstructed
        it would be reconstructing content. It is not a spoiler: a player
        learns the matrix in five minutes and then spends the rest of the game
        learning enemies, which is where the depth is. What a tell withholds
        is which move is coming, not what would beat it.
    """

    kind: ClassVar[str] = "combat.begin"
    combat: str
    mode: str = "tactical"
    combatants: tuple[tuple[str, str, str, str], ...] = ()
    can_flee: bool = True
    matrix: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def payload(self) -> dict[str, Any]:
        return {
            "combat": self.combat,
            "mode": self.mode,
            "combatants": [
                {"actor": actor, "name": name, "side": side, "profile": profile}
                for actor, name, side, profile in self.combatants
            ],
            "canFlee": self.can_flee,
            "matrix": [
                {"type": move, "beatenBy": list(answers)}
                for move, answers in self.matrix
            ],
        }


@dataclass(frozen=True, slots=True)
class CombatTell(Event):
    """Something is winding up, and the defender has `windowMs` to answer.

    The prose is the tell. `type` names the move's type only when the
    telegraph was legible — that is the whole of what a low `tellClarity`
    costs a reader, and a front-end that shows the type regardless has given
    the difficulty dial away.

    Attributes
    ----------
    combat : str
        The fight's session id.
    attacker, defender : str
        Instance ids.
    move : str
        Qualified move id. For the debug overlay; a player-facing UI should
        read the prose instead.
    type : str
        The move's type, or empty when the tell was not legible.
    text : str
        The telegraph, as the player reads it.
    window_ms : int
        How long the defender has, their speed already accounted for.
    clear : bool
        Whether the telegraph was legible.
    """

    kind: ClassVar[str] = "combat.tell"
    combat: str
    attacker: str
    defender: str
    move: str
    type: str = ""
    text: str = ""
    window_ms: int = 0
    clear: bool = True

    def payload(self) -> dict[str, Any]:
        return {
            "combat": self.combat,
            "attacker": self.attacker,
            "defender": self.defender,
            "move": self.move,
            "type": self.type,
            "text": self.text,
            "windowMs": self.window_ms,
            "clear": self.clear,
        }


@dataclass(frozen=True, slots=True)
class ResponseOffered(Event):
    """The engine is waiting for the player's answer, and here is what they have.

    The combat counterpart of `choices`, and it exists for the same reason:
    without it a front-end would have to reach into engine state to find out
    what the player can do, which is the boundary this protocol holds. It
    carries stamina and momentum too, because those are the resources being
    managed and a UI has to show them somewhere permanent.

    Attributes
    ----------
    combat : str
        The fight's session id.
    options : tuple of tuple
        Response name and label, in presentation order. A `combat.input`
        action names the response; the label is what to call it. Both, for the
        same reason `choices` carries a prompt: only the engine knows that
        `use:fantasy.core:healing-draught` is called "Healing Draught", and a
        front-end that worked it out would be reading content.
    stamina : float
        What the player has left to spend.
    momentum : float
        The damage multiplier a streak has earned, 1.0 at rest.
    streak : int
        Consecutive correct reads.
    """

    kind: ClassVar[str] = "combat.responses"
    combat: str
    options: tuple[tuple[str, str], ...] = ()
    stamina: float = 0.0
    momentum: float = 1.0
    streak: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "combat": self.combat,
            "options": [
                {"response": response, "label": label}
                for response, label in self.options
            ],
            "stamina": self.stamina,
            "momentum": self.momentum,
            "streak": self.streak,
        }


@dataclass(frozen=True, slots=True)
class CombatResolved(Event):
    """One exchange resolved, and here is why it went the way it did.

    Every field a front-end needs to say "Clean parry — you read the thrust"
    rather than "-8 hp". Attribution is what turns an outcome into learning,
    and learning is the entire design target.

    Attributes
    ----------
    combat : str
        The fight's session id.
    exchange : int
        Which exchange this was, counting from one.
    attacker, defender : str
        Instance ids.
    move : str
        Qualified id of what was thrown.
    response : str
        What the defender answered with.
    read : str
        `correct` or `wrong`.
    result : str
        `counter`, `absorbed`, `glancing`, or `clean`.
    precision : float
        How well it was timed, 0 to 1.
    damage_taken, damage_dealt : float
        What landed, each way.
    critical : bool
        Whether the opening was a critical one.
    momentum : float
        The defender's damage multiplier after this exchange.
    stamina : float
        What the defender has left.
    feint : bool
        Whether the windup meant nothing.
    """

    kind: ClassVar[str] = "combat.resolve"
    combat: str
    exchange: int
    attacker: str
    defender: str
    move: str
    response: str
    read: str = "wrong"
    result: str = "clean"
    precision: float = 0.0
    damage_taken: float = 0.0
    damage_dealt: float = 0.0
    critical: bool = False
    momentum: float = 1.0
    stamina: float = 0.0
    feint: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "combat": self.combat,
            "exchange": self.exchange,
            "attacker": self.attacker,
            "defender": self.defender,
            "move": self.move,
            "response": self.response,
            "read": self.read,
            "result": self.result,
            "precision": self.precision,
            "damageTaken": self.damage_taken,
            "damageDealt": self.damage_dealt,
            "critical": self.critical,
            "momentum": self.momentum,
            "stamina": self.stamina,
            "feint": self.feint,
        }


@dataclass(frozen=True, slots=True)
class CombatEnded(Event):
    """The fight is over.

    Attributes
    ----------
    combat : str
        The fight's session id.
    outcome : str
        `won`, `lost`, or `fled`.
    exchanges : int
        How many it took. The measure the acceptance test is read off: a
        skilled player finishes a troll in eight where a novice takes
        twenty-five.
    spoils : tuple of tuple
        Qualified item id and quantity taken from the defeated.
    """

    kind: ClassVar[str] = "combat.end"
    combat: str
    outcome: str
    exchanges: int = 0
    spoils: tuple[tuple[str, int], ...] = ()

    def payload(self) -> dict[str, Any]:
        return {
            "combat": self.combat,
            "outcome": self.outcome,
            "exchanges": self.exchanges,
            "spoils": [{"item": item, "qty": qty} for item, qty in self.spoils],
        }


@dataclass(frozen=True, slots=True)
class GameOver(Event):
    """The playthrough ended.

    Attributes
    ----------
    outcome : str
        `won` or `lost`.
    reason : str or None
        What ended it.
    """

    kind: ClassVar[str] = "game.over"
    outcome: str
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class Unsupported(Event):
    """Content asked for something this version of the engine cannot do yet.

    Emitted rather than raised, so a pack written against the finished design
    still plays as far as it can. A front-end may show it, log it, or ignore
    it; what it must not do is pretend the thing happened.

    Attributes
    ----------
    feature : str
        What was asked for.
    arrives : str
        Which phase brings it.
    """

    kind: ClassVar[str] = "engine.unsupported"
    feature: str
    arrives: str

    def payload(self) -> dict[str, Any]:
        return {"feature": self.feature, "arrives": self.arrives}


@dataclass(frozen=True, slots=True)
class RuleFailed(Event):
    """A condition or effect could not be evaluated.

    A condition that cannot be answered is a content bug, and answering `false`
    quietly is how a game ends up unplayable three hours in. It is reported
    instead, loudly, with the content that caused it.

    Attributes
    ----------
    message : str
        What went wrong.
    where : str or None
        The content that caused it.
    """

    kind: ClassVar[str] = "engine.rule-failed"
    message: str
    where: str | None = None

    def payload(self) -> dict[str, Any]:
        return {"message": self.message, "where": self.where}


def records(events: tuple[Event, ...] | list[Event]) -> list[dict[str, Any]]:
    """Render a stream of events for a golden file.

    Parameters
    ----------
    events : sequence of Event
        The stream.

    Returns
    -------
    list of dict
        One JSON-safe record per event.
    """
    return [event.record() for event in events]
