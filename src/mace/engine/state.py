"""Session state: what a particular playthrough is doing right now.

The counterpart to `mace.model`, and the other half of architecture boundary 1.
Content says trolls have base strength 70; state says *this* troll is at 31
hitpoints and afraid. Ten goblins from one definition are ten state objects
pointing at one content object.

State is mutable. Determinism does not need immutability — it needs the same
seed and the same actions to produce the same sequence — and a save is the
seed plus the action log, so no earlier state ever has to be kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from mace.engine.rng import RandomSource

__all__ = [
    "EntityState",
    "GameState",
    "Journey",
    "Modifier",
    "Outcome",
    "PendingChoice",
    "PendingChoices",
    "QuestState",
    "QuestStatus",
    "FrontState",
    "RegionWeather",
]


class Outcome(Enum):
    """How a playthrough stands."""

    PLAYING = "playing"
    WON = "won"
    LOST = "lost"


class QuestStatus(Enum):
    """Where a quest has got to."""

    HIDDEN = "hidden"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(slots=True)
class Modifier:
    """A temporary adjustment to one stat.

    Attributes
    ----------
    stat : str
        The stat affected.
    add : float
        A flat adjustment, applied before `mult`.
    mult : float
        A multiplier.
    label : str
        What the player sees this called — "Elixir of Haste".
    source : str
        Where it came from, for debugging and for removing a whole source.
    expires_at_tick : int or None
        When it lapses. None never lapses.
    """

    stat: str
    add: float = 0.0
    mult: float = 1.0
    label: str = ""
    source: str = ""
    expires_at_tick: int | None = None


@dataclass(slots=True)
class EntityState:
    """One entity, as it exists in this playthrough.

    Attributes
    ----------
    instance_id : str
        Unique within the session. `bridge-troll#3` for the third one spawned.
    definition : str
        The fully qualified content id this was instantiated from.
    location : str or None
        Qualified location id, or None for something being carried.
    pools : dict
        Current value of each pool — hitpoints, stamina.
    inventory : dict
        Qualified item id to quantity.
    equipment : dict
        Slot name to qualified item id.
    flags : set of str
        Boolean flags an author set or a scene raised.
    modifiers : list of Modifier
        Temporary stat adjustments.
    disposition : str or None
        Current stance toward the player.
    """

    instance_id: str
    definition: str
    location: str | None = None
    pools: dict[str, float] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    equipment: dict[str, str] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    modifiers: list[Modifier] = field(default_factory=list)
    disposition: str | None = None


@dataclass(slots=True)
class FrontState:
    """One weather system, somewhere on the map, on its way somewhere else.

    A front is the only part of the weather model with a position and a
    direction, which is what makes "the storm came down out of the north" a
    true sentence rather than a flourish.

    Attributes
    ----------
    id : str
        Unique within the session — `westerly#3`.
    kind : str
        Qualified id of the front definition.
    heading : tuple of str
        The regions it crosses, in order. The first is where it formed.
    position : int
        Which region of the heading it is over now.
    intensity : float
        0 to 1 at birth, decaying with age. Scales the bias it applies.
    born_at_tick : int
        When it formed.
    expires_at_tick : int
        When it dies, whatever its heading has left.
    hops_at_tick : int
        When it next moves along.
    announced : bool
        Whether its omen has been shown to the player. Once is enough — a
        front that keeps announcing itself stops being an omen and starts
        being a notification.
    """

    id: str
    kind: str
    heading: tuple[str, ...]
    position: int = 0
    intensity: float = 1.0
    born_at_tick: int = 0
    expires_at_tick: int = 0
    hops_at_tick: int = 0
    announced: bool = False

    @property
    def at(self) -> str:
        """The region the front is over.

        Returns
        -------
        str
            Qualified region id.
        """
        return self.heading[min(self.position, len(self.heading) - 1)]

    @property
    def ahead(self) -> str | None:
        """The region it is heading for next.

        Returns
        -------
        str or None
            Qualified region id, or None when this is the last of its heading.
        """
        following = self.position + 1
        if following >= len(self.heading):
            return None
        return self.heading[following]


@dataclass(slots=True)
class RegionWeather:
    """What the sky is doing over one region, and where its chain has got to.

    Weather is per region because a world where it rains everywhere at once is
    a world with one place in it. Each region walks its own Markov chain on its
    own random stream, so a storm crossing the mountains does not shift what
    the lowlands were going to get.

    A region the player is not in is not stepped every tick: it is fast
    forwarded from `stepped_to` when something needs to look at it. That is an
    optimization and not a change of behavior — replaying the same number of
    steps from the same stream position gives the same weather either way.

    Attributes
    ----------
    region : str
        Qualified region id.
    condition : str
        Qualified id of the weather condition in force.
    intensity : float
        0 to 1, drawn within the condition's band when it began.
    low, high : float
        Today's temperature floor and ceiling, after elevation.
    temperature_day : int
        The day `low` and `high` were drawn for.
    stepped_to : int
        The tick the chain has been advanced to.
    began_at_tick : int
        When the current condition started, for "easing" and "settling in".
    sequence : str or None
        The authored sequence running, if one is.
    sequence_step : int
        Which step of it is in force.
    sequence_until : int
        The tick that step ends on.
    """

    region: str
    condition: str
    intensity: float = 0.0
    low: float = 0.0
    high: float = 0.0
    temperature_day: int = 0
    stepped_to: int = 0
    began_at_tick: int = 0
    sequence: str | None = None
    sequence_step: int = 0
    sequence_until: int = 0


@dataclass(slots=True)
class QuestState:
    """One quest's progress.

    Attributes
    ----------
    quest : str
        Qualified quest id.
    status : QuestStatus
        Hidden, active, complete, or failed.
    stage : str or None
        The current stage's id.
    started_at_tick : int or None
        When it became active, for deadline conditions.
    """

    quest: str
    status: QuestStatus = QuestStatus.HIDDEN
    stage: str | None = None
    started_at_tick: int | None = None


@dataclass(slots=True)
class Journey:
    """A road being walked, and how far along it the player is.

    Travel is a process rather than a transition, which is the whole reason
    routes have a length. Keeping the journey in state is what makes it
    *interruptible*: a bridge that stops you, and later a fight you flee from,
    leave you partway along a road rather than teleported to one end of it.

    Attributes
    ----------
    route : str
        Qualified route id.
    origin, destination : str
        Qualified location ids, in the direction of travel — which may be the
        reverse of the way the route was written.
    progress : float
        How far along, in route ticks. Fractional, because bad weather makes
        a tick of walking worth less than a tick of road.
    passed : tuple of str
        Waypoints already reached and got past, so a resumed journey does not
        meet the same bridge twice.
    blocked_at : str or None
        A waypoint that stopped the player and is still stopping them. It is
        deliberately *not* in `passed`: a bridge with a troll on it is not
        somewhere you have been past, it is somewhere you have been stopped,
        and carrying on has to meet it again.
    """

    route: str
    origin: str
    destination: str
    progress: float = 0.0
    passed: tuple[str, ...] = ()
    blocked_at: str | None = None


@dataclass(slots=True)
class PendingChoice:
    """One option currently on offer.

    Attributes
    ----------
    prompt : str
        What the player reads.
    goto : str or None
        The scene it leads to.
    travel : str or None
        The location it goes to. Set on the menu the engine offers between
        scenes; a scene's own choices never travel.
    journey : str or None
        `onward` or `back`, on the two options an interrupted journey offers.
        Neither starts a new journey, which is why they are not `travel`.
    effects : tuple
        Inline effects to apply if it is taken.
    available : bool
        Whether it can be taken. An unavailable choice is only ever shown
        because the author asked for it to be, so the player can see what they
        are missing.
    hint : str or None
        Why it is unavailable.
    """

    prompt: str
    goto: str | None = None
    travel: str | None = None
    journey: str | None = None
    effects: tuple[Any, ...] = ()
    available: bool = True
    hint: str | None = None


@dataclass(slots=True)
class PendingChoices:
    """The choices the game is waiting on.

    While this is set, the only action that means anything is choosing one.

    Attributes
    ----------
    scene : str
        The qualified id of the scene that offered them.
    options : tuple of PendingChoice
        The options, in the order they were presented.
    """

    scene: str
    options: tuple[PendingChoice, ...]


@dataclass(slots=True)
class GameState:
    """Everything one playthrough knows about itself.

    Attributes
    ----------
    pack : str
        The game pack's id. Bare references in content resolve against it.
    seed : str
        The session seed. With the pack list and the action log, this is the
        whole save.
    rng : RandomSource
        Named random streams, positioned wherever play has taken them.
    tick : int
        World time. Its real-world meaning is `game.world.minutesPerTick`.
    world_tick : int
        How far the world simulation has been driven. Never behind `tick` by
        the time a front-end sees anything; it exists so that an action which
        moves the clock six ticks steps the world six times rather than once.
    start_tick : int
        The tick the playthrough opened on. A region the player has never
        visited begins its weather here and is fast-forwarded to now, so
        looking at a place late gives the weather it would have had all
        along rather than weather that started when you looked.
    player : str
        The protagonist's instance id.
    entities : dict
        Instance id to entity state.
    quests : dict
        Qualified quest id to progress.
    variables : dict
        Author-set game variables, readable from expressions as `vars.name`.
    revealed : set of str
        Qualified ids of locations the player knows about.
    played : set of str
        Qualified ids of scenes that have run, for `once`.
    weather : dict
        Qualified region id to what the sky is doing there.
    fronts : list of FrontState
        The weather systems currently crossing the map.
    fronts_spawned : int
        How many have ever formed, so instance ids stay unique.
    journey : Journey or None
        A road part-walked, if one was interrupted.
    pending : PendingChoices or None
        Choices awaiting an answer.
    outcome : Outcome
        Whether the game is still running, and how it ended if not.
    ended_because : str or None
        What ended it, for the `game.over` event.
    """

    pack: str
    seed: str
    rng: RandomSource
    player: str
    tick: int = 0
    world_tick: int = 0
    start_tick: int = 0
    entities: dict[str, EntityState] = field(default_factory=dict)
    quests: dict[str, QuestState] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    revealed: set[str] = field(default_factory=set)
    played: set[str] = field(default_factory=set)
    weather: dict[str, RegionWeather] = field(default_factory=dict)
    fronts: list[FrontState] = field(default_factory=list)
    fronts_spawned: int = 0
    journey: Journey | None = None
    pending: PendingChoices | None = None
    outcome: Outcome = Outcome.PLAYING
    ended_because: str | None = None

    @property
    def protagonist(self) -> EntityState:
        """The player's entity.

        Returns
        -------
        EntityState
            The protagonist's state.
        """
        return self.entities[self.player]

    @property
    def location(self) -> str | None:
        """Where the player is.

        Returns
        -------
        str or None
            Qualified location id.
        """
        return self.protagonist.location

    def here(self) -> list[EntityState]:
        """Every entity in the player's location, the player excluded.

        Returns
        -------
        list of EntityState
            Present entities, in instance-id order so nothing depends on how
            a dict happened to be built.
        """
        where = self.location
        return [
            entity
            for _key, entity in sorted(self.entities.items())
            if entity.location == where and entity.instance_id != self.player
        ]
