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

from dataclasses import dataclass
from typing import Any, ClassVar

__all__ = [
    "ChoiceOffered",
    "ChoicesOffered",
    "EncounterFired",
    "Event",
    "FlagChanged",
    "GameOver",
    "LocationRevealed",
    "InventoryChanged",
    "Moved",
    "Narrated",
    "QuestUpdated",
    "RuleFailed",
    "SceneEntered",
    "TravelInterrupted",
    "TravelLeg",
    "StatChanged",
    "TimePassed",
    "Unsupported",
    "VariableChanged",
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
