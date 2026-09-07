"""Effects — the changes content makes to the world.

An effect is a one-key mapping, like a condition, but where a condition asks a
question an effect answers with a change::

    effects:
      - {adjustStat: {actor: player, stat: hitpoints, delta: -8, reason: "the club"}}
      - {giveItem: {actor: player, item: fantasy.core:gold, qty: 1}}
      - {startCombat: {against: [gorm], canFlee: true}}

Effects replace the v0 magic-string modifiers and the `_attack_` sentinel: every
change a scene can make is a named, typed, validatable thing. Growing this
vocabulary is a deliberate, reviewable act (ADR-0003).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from mace.model.base import (
    AuthoredValue,
    ContentModel,
    EntityRef,
    Flag,
    FrontRef,
    GoodRef,
    Id,
    LocationRef,
    MarketRef,
    Name,
    QuestRef,
    Ref,
    RegionRef,
    RouteRef,
    SceneRef,
    SlotName,
    Tag,
    unwrap_tagged,
)
from mace.model.conditions import Condition

__all__ = [
    "Effect",
    "EffectPayload",
    "EffectTag",
]

EffectTag = Literal[
    "adjustStat",
    "advanceQuest",
    "advanceTime",
    "applyModifier",
    "attachAlly",
    "closeRoute",
    "damage",
    "dismissAlly",
    "endGame",
    "fireEvent",
    "giveItem",
    "marketShock",
    "move",
    "openRoute",
    "playScene",
    "rest",
    "restart",
    "reveal",
    "setDisposition",
    "setFlag",
    "setLight",
    "setPressure",
    "setRouteTicks",
    "setStat",
    "setVar",
    "spawnFront",
    "startCombat",
    "takeItem",
    "tellNews",
    "transferContents",
]


class EffectPayload(ContentModel):
    """Base class for the typed body of an effect."""


class AdjustStat(EffectPayload):
    """Move a stat or pool by a relative amount."""

    actor: EntityRef = "player"
    stat: Name
    delta: AuthoredValue
    reason: str | None = None


class SetStat(EffectPayload):
    """Set a stat or pool to an absolute value."""

    actor: EntityRef = "player"
    stat: Name
    value: AuthoredValue


class SetDisposition(EffectPayload):
    """Change how an entity feels about the player."""

    actor: EntityRef
    to: Literal["friendly", "neutral", "hostile"]


class ApplyModifier(EffectPayload):
    """Apply a temporary stat modifier, the way a potion or a spell would."""

    actor: EntityRef = "player"
    stat: Name
    add: float | None = None
    mult: float | None = None
    ticks: int = Field(gt=0)
    label: str | None = None

    @model_validator(mode="after")
    def _needs_a_change(self) -> ApplyModifier:
        """A modifier that neither adds nor multiplies does nothing."""
        if self.add is None and self.mult is None:
            raise ValueError("applyModifier needs `add`, `mult`, or both")
        return self


class ItemTransfer(EffectPayload):
    """Give an actor items, or take them away."""

    actor: EntityRef = "player"
    item: EntityRef
    qty: int = Field(default=1, ge=1)


class TransferContents(EffectPayload):
    """Move everything in one container or actor into another."""

    source: EntityRef = Field(alias="from")
    target: EntityRef = Field(alias="to")


class MoveActor(EffectPayload):
    """Put an actor somewhere else, without travelling there."""

    actor: EntityRef = "player"
    to: LocationRef


class SetFlag(EffectPayload):
    """Set or clear a boolean flag on an entity."""

    entity: EntityRef
    flag: Flag
    value: bool = True


class SetVar(EffectPayload):
    """Set a game variable, readable from expressions as `vars.name`."""

    name: SlotName
    value: AuthoredValue


class Reveal(EffectPayload):
    """Make a location known, so it appears on the map and in travel menus."""

    location: LocationRef


class AdvanceQuest(EffectPayload):
    """Move a quest to a given stage, or to its next one."""

    quest: QuestRef
    stage: Id | None = None


class StartCombat(EffectPayload):
    """Hand control to the combat system.

    A fight is not a scene and does not nest inside one: it takes over until
    it ends, and then plays whichever of `onWin`, `onLose`, and `onFlee`
    applies. Writing all three is how a fight has consequences rather than
    just an outcome — the bridge you can now cross, the debt you now owe, the
    twenty yards of road you gave up running.

    Attributes
    ----------
    against : tuple of str
        Who to fight. Repeat one to get several of it.
    can_flee : bool
        Whether running is allowed at all.
    on_win, on_lose, on_flee : str or None
        Scenes played after the fight. `onLose` is what a game with
        `deathIsPermanent: false` uses instead of ending; without one, losing
        leaves the vital pool empty and the game's own lose conditions decide.
    """

    against: tuple[EntityRef, ...] = Field(min_length=1)
    can_flee: bool = True
    on_win: SceneRef | None = None
    on_lose: SceneRef | None = None
    on_flee: SceneRef | None = None

    @model_validator(mode="before")
    @classmethod
    def _expand_single_opponent(cls, value: Any) -> Any:
        """Accept `against: troll` for the common one-opponent fight."""
        if isinstance(value, Mapping) and isinstance(value.get("against"), str):
            return {**value, "against": [value["against"]]}
        return value


class AttachAlly(EffectPayload):
    """Add an entity to the player's party, optionally until a condition holds."""

    entity: EntityRef
    until: Condition | None = None


class DismissAlly(EffectPayload):
    """Remove an entity from the player's party."""

    entity: EntityRef


class AdvanceTime(EffectPayload):
    """Push the world clock forward — resting, waiting, a long conversation."""

    ticks: int = Field(gt=0)


class Rest(EffectPayload):
    """Sit out the weather: clear exposure, refill pools, and lose the hours.

    The cost of rest is time, and time is not free — it runs down quest
    deadlines, moves weather fronts, and lets event pressure keep rising. That
    is what makes "shelter here until it passes, or push on cold" a real
    decision rather than a button.

    Attributes
    ----------
    ticks : int
        How long it takes. The clock advances by this, one tick at a time, so
        the world happens around the sleeper.
    pools : tuple of str
        Which pools to refill. Empty refills every pool the actor has a
        maximum for, which is what an author usually means.
    fraction : float
        How much of each pool's range a full rest restores.
    """

    ticks: int = Field(default=8, gt=0)
    pools: tuple[Name, ...] = ()
    fraction: float = Field(default=1.0, ge=0.0, le=1.0)


class MarketShock(EffectPayload):
    """Move what a whole class of goods costs, somewhere, for a while.

    The other half of what makes an event worth simulating. A closed pass
    stops trade; an eruption or a siege does not stop it, it changes what
    people will pay — and the two together are what turn a world event into
    something a trader feels three towns away.

    Where it lands is narrowed by `region` or `market`, and what it lands on
    by `category` or `good`. Naming none of them is a shock to everything,
    everywhere, which is a plague.

    Attributes
    ----------
    region : str or None
        Only markets in this region. None is everywhere.
    market : str or None
        Only this market. Narrower than `region`, and both may be given.
    category : str or None
        Only goods with this `category` — `food`, `metal`.
    good : str or None
        Only this good.
    mult : float
        What it does to the price at its peak. Above 1 is a shortage, below 1
        a glut — an eruption is 2.5, a good harvest is 0.7.
    decay_ticks : int
        How long it takes to fade back to nothing, straight-line. Shocks
        recover, because a world that never recovers is a world where the
        player's only information is how long ago something happened.
    reason : str or None
        What to call it, for a debug overlay and a merchant's remark.
    """

    region: RegionRef | None = None
    market: MarketRef | None = None
    category: Tag | None = None
    good: GoodRef | None = None
    mult: float = Field(gt=0.0)
    decay_ticks: int = Field(gt=0)
    reason: str | None = None


class CloseRoute(EffectPayload):
    """Shut a road, for a while or for good.

    The aftermath of an event is the thing that separates it from a weather
    condition: a landslide that closes a route for the rest of the game leaves
    the world permanently different, which is what an event is for.

    Attributes
    ----------
    route : str
        The road.
    permanent : bool
        Whether it stays shut. A temporary closure is lifted by `openRoute`,
        or by the event's own aftermath.
    reason : str or None
        What to tell a player who tries it.
    """

    shorthand_field: ClassVar[str] = "route"

    route: RouteRef
    permanent: bool = False
    reason: str | None = None


class OpenRoute(EffectPayload):
    """Reopen a road something closed."""

    shorthand_field: ClassVar[str] = "route"

    route: RouteRef


class SetRouteTicks(EffectPayload):
    """Change how long a road takes, for the rest of the game.

    Twelve lines of content and a detour that is genuinely longer now. This is
    how a world gets a memory.

    Attributes
    ----------
    route : str
        The road.
    ticks : int
        Its new length.
    """

    route: RouteRef
    ticks: int = Field(gt=0)


class SpawnFront(EffectPayload):
    """Put a weather system on the map, without waiting for one to form.

    An eruption's ash cloud is a front: it has an origin, a direction, and a
    life, and everything downwind of it gets the weather it brings.

    Attributes
    ----------
    front : str
        The kind of front.
    at : str
        The region it forms over.
    heading : tuple of str
        The regions it crosses. Empty walks the neighbour graph as usual.
    intensity : float or None
        Overrides the kind's own band.
    lifespan_ticks : int or None
        Overrides the kind's own lifespan.
    """

    front: FrontRef
    at: RegionRef
    heading: tuple[RegionRef, ...] = ()
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    lifespan_ticks: int | None = Field(default=None, gt=0)


class DealDamage(EffectPayload):
    """Hurt whoever is in the way.

    Named `DealDamage` rather than `Damage` because a weapon's damage range is
    already `Damage`, and the generated JSON Schema keys its definitions by
    class name — two of them would collide and one would silently vanish.

    Attributes
    ----------
    actor : str or None
        One entity. Omitted with `in_region` set, everyone there.
    in_region : str or None
        A region. The player is hurt if they are in it.
    amount : float
        How much comes off the vital pool.
    reason : str or None
        What did it.
    """

    actor: EntityRef | None = None
    in_region: RegionRef | None = None
    amount: float = Field(gt=0.0)
    reason: str | None = None


class SetLight(EffectPayload):
    """Override how much light the sky gives, until something clears it."""

    shorthand_field: ClassVar[str] = "light"

    light: float | None = Field(default=None, ge=0.0, le=1.0)


class FireEvent(EffectPayload):
    """Make a world event happen now, whatever its own clock was doing.

    The third kind of event: one the story causes. A quest that wakes the
    mountain is this effect, and nothing else about the event changes.
    """

    shorthand_field: ClassVar[str] = "event"

    event: Ref


class SetPressure(EffectPayload):
    """Nudge a pressure event toward its threshold, or back from it.

    An act-two beat that puts the volcano on the brink and lets the simulation
    deliver act three.

    Attributes
    ----------
    event : str
        The pressure event.
    value : float
        Its new accumulator, as a share of the threshold.
    """

    event: Ref
    value: float = Field(ge=0.0, le=1.0)


class TellNews(EffectPayload):
    """Pass on something that happened somewhere the player was not.

    Events fire whether or not anyone is watching, and a world where things
    only happen in your presence is not a world. News waits in a queue and
    arrives through ordinary channels — a traveller on the road, a rider, a
    refugee, an innkeeper — which is what this effect is for.

    Attributes
    ----------
    count : int
        How many items to pass on at once.
    max_days_old : int or None
        Ignore anything older. A rumour that has been going round for a month
        is not news any more.
    """

    shorthand_field: ClassVar[str] = "count"

    count: int = Field(default=1, ge=1)
    max_days_old: int | None = Field(default=None, ge=0)


class PlayScene(EffectPayload):
    """Run another scene."""

    shorthand_field: ClassVar[str] = "scene"

    scene: SceneRef


class NoArguments(EffectPayload):
    """An effect that takes nothing: `{restart: {}}`, `{endGame: {}}`."""

    @model_validator(mode="before")
    @classmethod
    def _accept_empty(cls, value: Any) -> Any:
        """Accept `{}`, `null`, and an omitted body alike."""
        return value if isinstance(value, Mapping) else {}


#: The typed body each effect tag expects.
EFFECT_PAYLOADS: dict[EffectTag, type[EffectPayload]] = {
    "adjustStat": AdjustStat,
    "advanceQuest": AdvanceQuest,
    "advanceTime": AdvanceTime,
    "applyModifier": ApplyModifier,
    "attachAlly": AttachAlly,
    "closeRoute": CloseRoute,
    "damage": DealDamage,
    "dismissAlly": DismissAlly,
    "endGame": NoArguments,
    "fireEvent": FireEvent,
    "giveItem": ItemTransfer,
    "marketShock": MarketShock,
    "move": MoveActor,
    "openRoute": OpenRoute,
    "playScene": PlayScene,
    "rest": Rest,
    "restart": NoArguments,
    "reveal": Reveal,
    "setDisposition": SetDisposition,
    "setFlag": SetFlag,
    "setLight": SetLight,
    "setPressure": SetPressure,
    "setRouteTicks": SetRouteTicks,
    "setStat": SetStat,
    "setVar": SetVar,
    "spawnFront": SpawnFront,
    "startCombat": StartCombat,
    "takeItem": ItemTransfer,
    "tellNews": TellNews,
    "transferContents": TransferContents,
}


class Effect(ContentModel):
    """One authored effect: a tag naming the change, and its typed body.

    Attributes
    ----------
    tag : EffectTag
        Which change is being made.
    payload : EffectPayload
        The arguments, validated against the body type registered for `tag`.
    """

    tag: EffectTag
    payload: EffectPayload

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        """Turn the authored `{tag: body}` mapping into tag and payload."""
        tag, body = unwrap_tagged(
            value, kind="effect", vocabulary=tuple(EFFECT_PAYLOADS)
        )
        payload = EFFECT_PAYLOADS[tag]  # type: ignore[index]
        return {"tag": tag, "payload": payload.model_validate(body)}

    def authored(self) -> Any:
        return {self.tag: self.payload.authored()}
