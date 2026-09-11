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
    "Combatant",
    "CombatState",
    "EncounterMemory",
    "EntityState",
    "GameState",
    "Journey",
    "MarketState",
    "Modifier",
    "Outcome",
    "PendingChoice",
    "PendingChoices",
    "QuestState",
    "NewsItem",
    "QuestStatus",
    "PendingTell",
    "EventPhase",
    "EventState",
    "FrontState",
    "Haggle",
    "RegionWeather",
    "RouteState",
    "Shock",
]


class EventPhase(Enum):
    """Where a world event has got to.

    The same lifecycle for every kind of event, so front-ends and content hook
    the same names whether the thing coming is an eclipse or a landslide.

    - `DORMANT` — not yet anything.
    - `BUILDING` — omens fire. The player's only information channel.
    - `IMMINENT` — unambiguous. Routes close, people flee. The last exit, and
      it should be *late*: the tension lives in the gap between probably and
      certainly.
    - `ACTIVE` — it has happened, and the world is different for a while.
    - `SPENT` — over, its aftermath applied. Permanently.
    """

    DORMANT = "dormant"
    BUILDING = "building"
    IMMINENT = "imminent"
    ACTIVE = "active"
    SPENT = "spent"


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
class EncounterMemory:
    """What one encounter table remembers about this playthrough.

    Two jobs, both about how a road *feels* rather than what it contains.

    `last_at_tick` enforces `minGapTicks`: independent rolls produce three
    ambushes in a row, and that reads as broken even when it is fair.

    `pressure` is the pity system, and it is written so that it does not
    quietly make a road more dangerous than its author asked for. An empty
    roll adds `pressureStep`; a roll that fires subtracts
    `pressureStep × (1/chance − 1)`. Over a long run at the authored rate the
    misses outnumber the hits by exactly `(1 − chance) : chance`, so the two
    terms cancel and the mean stays put. What changes is the variance: long
    empty stretches get likelier to end and streaks get likelier to stop.

    Attributes
    ----------
    table : str
        Qualified table id.
    pressure : float
        Added to `chance` on the next roll. May be negative.
    last_at_tick : int or None
        When this table last produced something.
    fired : dict
        Entry id to how many times it has fired.
    last_entry_tick : dict
        Entry id to when it last fired, for `cooldownTicks`.
    """

    table: str
    pressure: float = 0.0
    last_at_tick: int | None = None
    fired: dict[str, int] = field(default_factory=dict)
    last_entry_tick: dict[str, int] = field(default_factory=dict)


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
    exposure : float
        0 to 1. How much the weather has taken out of this entity. Only the
        player accumulates it — it exists for the decision a player makes, and
        a wandering NPC's cold-weather death spiral is simulation for its own
        sake.
    skills : dict
        Qualified item id to skill, 0 to 100, raised by using the thing. What
        a character has learned to do with a particular weapon.
    familiarity : dict
        Qualified combat-profile id to how many correct reads this entity has
        made against it. The character learning trolls, as distinct from the
        *player* learning trolls — both are meant to matter, and only one of
        them can be stored (docs/07-combat.md § Growth).
    ally : bool
        Whether this entity travels with the player and fights on their side.
    transient : bool
        Whether this instance goes when the player moves on. What an encounter
        spawns is here while you are here; what an author placed at a location
        stays where they put it.
    ally_until : object or None
        The condition that ends the arrangement, when one was set. Held as the
        authored `Condition` rather than re-derived, because the effect that
        attached them is long gone by the time it comes true — "as far as the
        castle" has to outlive the scene that said it.
    stat_caps : dict
        Permanent additions to a stat's ceiling, on top of whatever `max` the
        content declared — a heart found, a season of training, `chopped
        wood twenty times`. Session state, never content: the same troll
        definition stays `max: 40` for every other playthrough: this one's
        troll just happens to have outgrown it.
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
    exposure: float = 0.0
    skills: dict[str, float] = field(default_factory=dict)
    familiarity: dict[str, int] = field(default_factory=dict)
    ally: bool = False
    transient: bool = False
    ally_until: Any = None
    stat_caps: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class EventState:
    """One world event's progress through its own life.

    Attributes
    ----------
    event : str
        Qualified id of the event definition.
    phase : EventPhase
        Where it has got to.
    pressure : float
        The hidden accumulator, as a share of the threshold. Meaningless for
        a celestial event, whose timing is a pure function of the calendar.
    onset_tick : int or None
        When it happened.
    ends_at_tick : int or None
        When `active` runs out.
    fired : int
        How many times it has happened, for `maxPerGame`.
    omens_seen : set of str
        Which omens have been shown, for `once`.
    last_omen_tick : int or None
        When the last one showed. Two omens in a row read as a weather
        report; the gap between them is part of what makes one land.
    """

    event: str
    phase: EventPhase = EventPhase.DORMANT
    pressure: float = 0.0
    onset_tick: int | None = None
    ends_at_tick: int | None = None
    fired: int = 0
    omens_seen: set[str] = field(default_factory=set)
    last_omen_tick: int | None = None


@dataclass(slots=True)
class RouteState:
    """What has happened to a road since the game started.

    Attributes
    ----------
    route : str
        Qualified route id.
    closed : bool
        Whether it is shut.
    permanent : bool
        Whether the closure outlives whatever caused it.
    reason : str or None
        What to tell a player who tries it.
    ticks : int or None
        A new length, when something has lengthened or shortened it.
    """

    route: str
    closed: bool = False
    permanent: bool = False
    reason: str | None = None
    ticks: int | None = None


@dataclass(slots=True)
class MarketState:
    """One market's shelves, and how far they have been carried.

    A market the player has never visited is not stepped every tick. It is
    opened at the playthrough's start tick and carried forward when something
    needs to look at it, the same way a region's weather is — so arriving
    somewhere on day fifty finds the stock it would have had all along, not
    stock that began when you looked.

    Attributes
    ----------
    market : str
        Qualified market id.
    stock : dict
        Qualified good id to units held.
    stepped_to : int
        The tick the shelves have been carried to.
    """

    market: str
    stock: dict[str, float] = field(default_factory=dict)
    stepped_to: int = 0


@dataclass(slots=True)
class Haggle:
    """Where an argument over a price has got to, with one merchant.

    Attributes
    ----------
    swing : float
        How far the price has been moved in the player's favour, as a
        fraction. Negative after a merchant has soured.
    pushes : int
        How many times the player has pressed. The number that turns a
        negotiation into a decision: every push is likelier to sour than the
        last, so knowing when to stop is the whole skill.
    soured_until : int or None
        The tick this merchant will deal properly again. None is not soured.
    """

    swing: float = 0.0
    pushes: int = 0
    soured_until: int | None = None


@dataclass(slots=True)
class Shock:
    """A pressure on prices somewhere, fading on its own clock.

    The event system's hand on the economy. A closed pass stops trade; a
    siege or an eruption does not stop it, it changes what people will pay,
    and this is that. Every field is a filter — the ones set are the ones
    that have to match.

    Attributes
    ----------
    region, market : str or None
        Qualified ids narrowing where it lands. None matches anywhere.
    category, good : str or None
        What it lands on. None matches anything.
    mult : float
        What it does to a price at its peak.
    from_tick : int
        When it started.
    decay_ticks : int
        How long it takes to fade to nothing, straight-line.
    reason : str or None
        What to call it.
    """

    mult: float
    from_tick: int
    decay_ticks: int
    region: str | None = None
    market: str | None = None
    category: str | None = None
    good: str | None = None
    reason: str | None = None

    def at(self, tick: int) -> float:
        """What this shock multiplies a price by, at some tick.

        Parameters
        ----------
        tick : int
            When.

        Returns
        -------
        float
            The multiplier, decaying straight-line to 1.0 and staying there.
        """
        left = 1.0 - (tick - self.from_tick) / self.decay_ticks
        if left <= 0.0:
            return 1.0
        return 1.0 + (self.mult - 1.0) * min(left, 1.0)


@dataclass(slots=True)
class NewsItem:
    """Something that happened somewhere the player was not.

    Events fire whether or not the player is watching, and a world where
    things only happen in your presence is not a world. News carries its age
    and its distance, so a rumour three days old and two regions away can
    arrive garbled — which is free atmosphere and makes the player's
    information imperfect in a way that feels like a medieval world rather
    than like a notification.

    Attributes
    ----------
    event : str
        Qualified id of what happened.
    tick : int
        When it happened.
    region : str or None
        Where.
    text : str
        The plainest telling of it.
    told : bool
        Whether the player has heard it.
    """

    event: str
    tick: int
    region: str | None
    text: str
    told: bool = False


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
class Combatant:
    """One fighter in a fight, and where its habits have got to.

    Everything durable about a combatant — hitpoints, effort, what it is
    holding — lives in its `EntityState` and is not copied here. What is here
    is what only exists while the fight does.

    Attributes
    ----------
    actor : str
        The entity's instance id.
    side : str
        `player` or `enemy`. Allies fight on the player's side.
    profile : str or None
        Qualified id of the combat profile it is fighting on. None means it
        has none, and can only take the hit.
    meter : float
        The action meter, filling in proportion to speed. At 1.0 the
        combatant is ready to act. This is where multi-combatant pressure
        comes from: three wolves are three meters filling at once, not one
        enemy with bigger numbers.
    pattern : tuple of str
        The qualified moves of the sequence being played out.
    pattern_step : int
        How far through it. A pattern is played to the end before another is
        picked, which is what makes a habit observable.
    momentum : int
        Index into the momentum ladder. Rises on a clean read, resets on a
        clean hit taken.
    streak : int
        Consecutive successful reads, for the front-end to celebrate.
    routed : bool
        Whether this combatant has run.
    defeated : bool
        Whether it is down.
    spawned : bool
        Whether this fight put it in the world. A fight tidies away what it
        made and leaves alone what it found: two wolves conjured by a road
        leave when they are beaten, and the troll who lives under the bridge
        is still under the bridge afterwards.
    """

    actor: str
    side: str = "enemy"
    profile: str | None = None
    meter: float = 0.0
    pattern: tuple[str, ...] = ()
    pattern_step: int = 0
    momentum: int = 0
    streak: int = 0
    routed: bool = False
    defeated: bool = False
    spawned: bool = False


@dataclass(slots=True)
class PendingTell:
    """A move that has been telegraphed and is waiting for an answer.

    The window is computed once, when the tell is emitted, and stored — so a
    replay resolves against the same window the live session did even if the
    defender's speed has moved since.

    Attributes
    ----------
    attacker : str
        Instance id of whoever is winding up.
    defender : str
        Instance id of whoever has to answer.
    move : str
        Qualified id of the move being played.
    feint : bool
        Whether the windup means nothing.
    clear : bool
        Whether the telegraph was legible. A vague tell withholds the move's
        type, which is the whole of what `tellClarity` costs the reader.
    window_ms : int
        How long the defender has, their speed already taken into account.
    """

    attacker: str
    defender: str
    move: str
    feint: bool = False
    clear: bool = True
    window_ms: int = 0


@dataclass(slots=True)
class CombatState:
    """A fight in progress.

    A fight happens *inside* a tick: its clock is milliseconds of simulated
    exchange time and it never moves the world clock. That is what keeps a
    forty-exchange fight from aging the world more than a twelve-exchange one
    (docs/02-architecture.md § Time).

    Attributes
    ----------
    id : str
        Session-unique — `combat#2`. Names this fight's random stream, so a
        long fight cannot shift what any other subsystem draws.
    mode : str
        `reflex`, `tactical`, or `auto`. How the response is collected, and
        the only thing the three modes differ in.
    combatants : list of Combatant
        Everyone in it, in a stable order.
    tell : PendingTell or None
        The move awaiting an answer.
    exchange : int
        How many exchanges have resolved.
    can_flee : bool
        Whether running is allowed at all.
    after : dict
        Outcome name — `won`, `lost`, `fled` — to the qualified scene played
        once the fight ends. A fight with consequences rather than just an
        outcome is a fight worth writing.
    flee_to : str or None
        Qualified location id to put them down at. None leaves them where the
        journey left them, which for a road is partway along it.
    focus : str or None
        The instance id the player's allies are concentrating on. Set by
        spending an exchange on an order, which is why it lives here rather
        than being recomputed: an order the player paid for has to outlast
        the exchange they paid for it in.
    spoils : dict
        Qualified item id to quantity, taken from the defeated.
    outcome : str or None
        `won`, `lost`, or `fled`, once it is over.
    """

    id: str
    mode: str = "tactical"
    combatants: list[Combatant] = field(default_factory=list)
    tell: PendingTell | None = None
    exchange: int = 0
    can_flee: bool = True
    after: dict[str, str] = field(default_factory=dict)
    flee_to: str | None = None
    focus: str | None = None
    spoils: dict[str, int] = field(default_factory=dict)
    outcome: str | None = None

    def find(self, actor: str) -> Combatant | None:
        """The combatant standing for one entity instance.

        Parameters
        ----------
        actor : str
            The instance id.

        Returns
        -------
        Combatant or None
            The combatant, or None when that entity is not in this fight.
        """
        return next((c for c in self.combatants if c.actor == actor), None)

    def standing(self, side: str) -> list[Combatant]:
        """Everyone on one side who is still in the fight.

        Parameters
        ----------
        side : str
            `player` or `enemy`.

        Returns
        -------
        list of Combatant
            Combatants who are neither down nor gone, in a stable order.
        """
        return [
            c
            for c in self.combatants
            if c.side == side and not c.defeated and not c.routed
        ]


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
    use : str or None
        Qualified id of an item this option spends.
    trade : str or None
        Instance id of a merchant to open a stall with. Set on the menu the
        engine offers; a scene's own choices never trade.
    haggle : bool
        Whether this option argues the price rather than moving anything.
    deal : tuple or None
        A good, a quantity, and whether the player is selling — the one-click
        form of a `trade` action, so a terminal can trade without a quantity
        control. Both go through the same arithmetic.
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
    use: str | None = None
    trade: str | None = None
    haggle: bool = False
    deal: tuple[str, int, bool] | None = None
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
        Qualified ids of locations the player knows about — heard of, or
        stood in.
    visited : set of str
        Qualified ids of locations the player has actually stood in. A subset
        of `revealed`, kept apart from it because a map that cannot tell
        somewhere you have been from somewhere you were told about has thrown
        away the reward for going there.
    played : set of str
        Qualified ids of scenes that have run, for `once`.
    weather : dict
        Qualified region id to what the sky is doing there.
    fronts : list of FrontState
        The weather systems currently crossing the map.
    fronts_spawned : int
        How many have ever formed, so instance ids stay unique.
    encounters : dict
        Qualified table id to what that table remembers.
    events : dict
        Qualified event id to how far along it is.
    routes : dict
        Qualified route id to what has happened to that road.
    markets : dict
        Qualified market id to that market's shelves. A market appears here
        once something has looked at it, and not before.
    restocked : dict
        Merchant instance id to the tick its purse was last brought back up
        to its `capital`. Only merchants with a purse appear here, and only
        once one has been looked at.
    haggles : dict
        Merchant instance id to where the argument with them stands.
    prices : dict
        Qualified market id to good id to the last unit price the player was
        quoted there. What the journal shows and the map shades by, and what
        gives an author's "I know what this costs two towns over" something
        real to stand on — only prices the player has personally seen are in
        it, which is the whole point.
    shocks : list of Shock
        Pressures on prices, each fading on its own clock. Spent ones are
        left in place rather than swept up: they multiply by exactly 1.0, and
        a list that quietly reordered itself would be a list a replay could
        disagree about.
    news : list of NewsItem
        Things that happened out of sight, waiting to travel.
    light_override : float or None
        An override on the sky's light, set by an eclipse and cleared by its
        aftermath. Night, at noon.
    journey : Journey or None
        A road part-walked, if one was interrupted.
    combat : CombatState or None
        A fight in progress. While one is set, the only actions that mean
        anything are combat responses.
    combats_begun : int
        How many fights have started, so a fight's stream name is unique.
    combat_mode : str or None
        The player's own choice of combat presentation, overriding the game's
        default. A session setting rather than an action: it belongs with the
        seed, in the parameters a save opens with, because changing it midway
        would change what a recorded elapsed time means.
    time_pressure : float
        How hard the clock presses in `reflex` combat. 1.0 is the fight as
        authored; 0.5 gives twice the window; 2.0 gives half of it. An
        accessibility setting (docs/10 § Accessibility) for players who want
        the reading game without that much of the reaction game, and a session
        setting for the same reason `combat_mode` is one — it changes what a
        recorded elapsed time means, so it cannot move mid-playthrough.

        It scales the window and nothing else. Precision is still measured
        against the window the player was actually given, so a slower window
        is a longer door and not an easier one to aim at.
    background : str or None
        The qualified background the protagonist was created with, kept
        because conditions ask about it and a save has to reopen as the same
        person. What it *granted* is already in the pools, inventory, skills,
        and flags around it; this is the answer, not the consequences.
    pending : PendingChoices or None
        Choices awaiting an answer.
    trading : str or None
        Instance id of the merchant the player has a stall open with. Only a
        presentation state — it decides which menu the engine offers — but it
        lives here because it has to survive a replay, and it is cleared the
        moment the player is anywhere else.
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
    visited: set[str] = field(default_factory=set)
    played: set[str] = field(default_factory=set)
    weather: dict[str, RegionWeather] = field(default_factory=dict)
    fronts: list[FrontState] = field(default_factory=list)
    fronts_spawned: int = 0
    encounters: dict[str, EncounterMemory] = field(default_factory=dict)
    events: dict[str, EventState] = field(default_factory=dict)
    routes: dict[str, RouteState] = field(default_factory=dict)
    markets: dict[str, MarketState] = field(default_factory=dict)
    restocked: dict[str, int] = field(default_factory=dict)
    haggles: dict[str, Haggle] = field(default_factory=dict)
    prices: dict[str, dict[str, int]] = field(default_factory=dict)
    shocks: list[Shock] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
    light_override: float | None = None
    journey: Journey | None = None
    combat: CombatState | None = None
    combats_begun: int = 0
    combat_mode: str | None = None
    time_pressure: float = 1.0
    background: str | None = None
    pending: PendingChoices | None = None
    trading: str | None = None
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
