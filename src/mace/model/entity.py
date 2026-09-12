"""Entities — the universal noun.

One type covers the player, an innkeeper, a troll, a sword, a locked chest, and
the gate they stand in front of. `kind` selects which optional field groups
apply; it does not select special-case engine logic (ADR-0002).

Everything here is what a thing *is*. A troll's `base` strength lives in a
content pack and is shared by every troll ever spawned; this particular troll's
current hitpoints live in session state and never come back here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, PlainValidator, WithJsonSchema, model_validator

from mace.model.base import (
    CombatProfileRef,
    ContentModel,
    EntityRef,
    Flag,
    Id,
    MoveRef,
    Name,
    RouteRef,
    SceneRef,
    SlotName,
    Tag,
)
from mace.model.conditions import Conditions
from mace.model.economy import Merchant
from mace.model.effects import Effect
from mace.model.text import Description

__all__ = [
    "CombatAssignment",
    "ContainerProps",
    "Damage",
    "Entity",
    "EntityKind",
    "EnvResponse",
    "ItemProps",
    "ItemUse",
    "InventoryEntry",
    "Merchant",
    "PortalProps",
    "Range",
    "RelativeStat",
    "RelativeValue",
    "Stat",
    "StatModifier",
]

EntityKind = Literal["actor", "item", "fixture", "container", "portal"]
Disposition = Literal["friendly", "neutral", "hostile"]
Growth = Literal["none", "slow", "normal", "fast"]

#: Which optional block belongs to which `kind`. A block on the wrong kind is
#: an authoring mistake worth catching at load time.
KIND_BLOCKS: dict[str, EntityKind] = {
    "item": "item",
    "container": "container",
    "portal": "portal",
    "merchant": "actor",
}


class RelativeStat(ContentModel):
    """A number expressed as a multiple of the player's own stat.

    Resolved against the player's stat *cap*, not their fluctuating current
    value — a hit re-rolls fresh every time it's asked for, but a monster's
    stat is baked into an absolute number once, at the moment it's created.
    It does not keep tracking the player afterward: a monster that quietly
    gets tougher mid-playthrough because the player leveled up would be a
    bug for most games, not a feature. A game that wants that anyway can
    already build it with `raiseMax`/`adjustStat` — this type doesn't need
    to cover that case too.

    Attributes
    ----------
    stat : str
        Which of the player's own stats to read.
    factor : float
        The multiple of it — `0.15` for "15%", `3` for "3x".
    """

    stat: Name
    factor: float = 1.0


def _to_relative_value(value: Any) -> Any:
    """Coerce a value that may be a literal number or a relative reference.

    Parameters
    ----------
    value : object
        The raw YAML value.

    Returns
    -------
    object
        The literal number unchanged, or a parsed `RelativeStat`.

    Raises
    ------
    ValueError
        If the value is a mapping that is not a `relativeToPlayer` wrapper,
        or is not a number at all.
    """
    if isinstance(value, RelativeStat):
        return value
    if isinstance(value, Mapping):
        if set(value) == {"relativeToPlayer"}:
            return RelativeStat.model_validate(value["relativeToPlayer"])
        raise ValueError(
            "a value may be a number or `{relativeToPlayer: {stat, factor}}`; "
            f"got a mapping with keys {sorted(map(str, value))}"
        )
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(
            f"expected a number or a relative value, got {type(value).__name__}"
        )
    return float(value)


#: A field that holds either a literal number or a `{relativeToPlayer: {...}}`
#: reference to the player's own stat.
RelativeValue = Annotated[
    RelativeStat | float,
    PlainValidator(_to_relative_value),
    WithJsonSchema(
        {
            "oneOf": [
                {"type": "number"},
                {
                    "type": "object",
                    "properties": {
                        "relativeToPlayer": {
                            "type": "object",
                            "properties": {
                                "stat": {"type": "string"},
                                "factor": {"type": "number"},
                            },
                            "required": ["stat"],
                        }
                    },
                    "required": ["relativeToPlayer"],
                    "additionalProperties": False,
                },
            ]
        }
    ),
]


class Stat(ContentModel):
    """A single ability or pool, before anything acts on it.

    Attributes
    ----------
    base : float or RelativeStat
        The value with nothing acting on it. May be a multiple of the
        player's own stat instead of a literal number.
    max : float, RelativeStat, or None
        Cap. Defaults to 100 for abilities; pools should set it explicitly.
    min : float
        Floor. Defaults to 0.
    customizable : bool
        Whether the player may spend creation points here at game start.
    growth : {'none', 'slow', 'normal', 'fast'}
        How fast the stat improves through use.
    """

    base: RelativeValue
    max: RelativeValue | None = None
    min: float = 0.0
    customizable: bool = False
    growth: Growth = "none"

    @model_validator(mode="after")
    def _range_is_sane(self) -> Stat:
        """A stat whose floor is above its cap can never be satisfied."""
        if (
            self.max is not None
            and not isinstance(self.max, RelativeStat)
            and self.min > self.max
        ):
            raise ValueError(f"min ({self.min}) is above max ({self.max})")
        return self

    @model_validator(mode="after")
    def _customizable_is_literal(self) -> Stat:
        """A player-customizable stat can't be relative to the player."""
        if self.customizable and (
            isinstance(self.base, RelativeStat) or isinstance(self.max, RelativeStat)
        ):
            raise ValueError(
                "a customizable stat's base/max can't be relative to the "
                "player — it is the player's own stat"
            )
        return self


class StatModifier(ContentModel):
    """An adjustment to a stat while some condition holds.

    Attributes
    ----------
    stat : str
        Which stat is affected.
    add : float or None
        A flat adjustment.
    mult : float or None
        A multiplier, applied after `add`.
    """

    stat: Name
    add: float | None = None
    mult: float | None = None

    @model_validator(mode="after")
    def _changes_something(self) -> StatModifier:
        """A modifier that neither adds nor multiplies does nothing."""
        if self.add is None and self.mult is None:
            raise ValueError("a stat modifier needs `add`, `mult`, or both")
        return self


class EnvResponse(ContentModel):
    """How an entity answers the weather, the dark, or the season.

    Attributes
    ----------
    when : tuple of Condition
        When this response applies.
    modify : tuple of StatModifier
        Adjustments held for as long as the condition does.
    effects : tuple of Effect
        One-shot effects fired on entering the condition.
    """

    when: Conditions
    modify: tuple[StatModifier, ...] = ()
    effects: tuple[Effect, ...] = ()


class InventoryEntry(ContentModel):
    """A stack of one item.

    Attributes
    ----------
    item : str
        Reference to the item entity.
    qty : int
        How many.
    """

    item: EntityRef
    qty: int = Field(default=1, ge=1)


class Damage(ContentModel):
    """A weapon's damage range.

    Attributes
    ----------
    min, max : float or RelativeStat
        The bounds of a single hit, before stats and gear. Either bound may
        be a multiple of the player's own stat instead of a literal number.
    type : str
        Author-defined: `slash`, `pierce`, `plasma`.
    """

    min: RelativeValue
    max: RelativeValue
    type: Id | None = None

    @model_validator(mode="after")
    def _range_is_sane(self) -> Damage:
        """Damage that can never roll is a content mistake."""
        if (
            not isinstance(self.min, RelativeStat)
            and not isinstance(self.max, RelativeStat)
            and self.min > self.max
        ):
            raise ValueError(f"min damage ({self.min}) is above max ({self.max})")
        return self


class Range(ContentModel):
    """How close or far a move works, and where it works best.

    Distance is one shared scalar per fight (docs/07-combat.md § Range), so
    this is feet along that line, not a 2D or relative measure.

    Attributes
    ----------
    min, max : float
        The band a move can be attempted in at all. Outside it, the move
        cannot be attempted — a bow's `min` is what keeps it from being
        usable point-blank.
    sweet_min, sweet_max : float
        The band inside `[min, max]` where the move is at its best.
        Effectiveness ramps from 0 at the outer edges of `[min, max]` to 1.0
        across `[sweetMin, sweetMax]` — the same shape `precision` uses for
        timing.
    """

    min: float = Field(ge=0.0)
    max: float = Field(gt=0.0)
    sweet_min: float
    sweet_max: float

    @model_validator(mode="after")
    def _band_is_sane(self) -> Range:
        """A sweet spot outside its own band, or an inverted one, can never be hit."""
        if self.min > self.max:
            raise ValueError(f"min range ({self.min}) is above max ({self.max})")
        if not (self.min <= self.sweet_min <= self.sweet_max <= self.max):
            raise ValueError(
                f"sweet spot ({self.sweet_min}-{self.sweet_max}) must sit "
                f"inside the range ({self.min}-{self.max}), in order"
            )
        return self


class ItemUse(ContentModel):
    """What happens when an item is used from the inventory.

    Attributes
    ----------
    effects : tuple of Effect
        What using it does.
    consumed : bool
        Whether the item is spent in the using.
    """

    effects: tuple[Effect, ...] = Field(min_length=1)
    consumed: bool = False


class ItemProps(ContentModel):
    """The `kind: item` block.

    Attributes
    ----------
    weight : float or None
        Carried weight.
    stackable : bool or None
        Whether copies collapse into one inventory entry.
    equip_slot : str or None
        Which slot it occupies when equipped.
    damage : Damage or None
        For weapons.
    range : Range or None
        For weapons: how close or far it works. `strike` — the player's only
        source of damage — reads this from whatever is equipped, falling
        back to bare hands when nothing is (docs/07-combat.md § Range).
        `None` on a weapon means the melee default, the same way `None`
        armor means no reduction.
    ammo : int or None
        For weapons: how many times it can be used before it's spent.
        `None` is unlimited, a sword. A thrown rock is `1`.
    armor : float or None
        Damage reduction when worn.
    moves : tuple of str
        Combat moves this item grants its wielder. A weapon is how a fighter
        gets a `thrust` to answer with; a shield is how they get a `block`.
    use : ItemUse or None
        What using it from the inventory does.
    base_value : float or None
        The price anchor. `simple` economies use it as the price; `market`
        economies price around it. Same name as a good's, because it is the
        same idea.
    """

    weight: float | None = None
    stackable: bool | None = None
    equip_slot: SlotName | None = None
    damage: Damage | None = None
    range: Range | None = None
    ammo: int | None = Field(default=None, ge=1)
    armor: float | None = None
    moves: tuple[MoveRef, ...] = ()
    use: ItemUse | None = None
    base_value: float | None = None


class ContainerProps(ContentModel):
    """The `kind: container` block.

    Attributes
    ----------
    capacity : int or None
        How much it holds. `None` means no limit.
    contents : tuple of InventoryEntry
        What is inside at game start.
    """

    capacity: int | None = Field(default=None, gt=0)
    contents: tuple[InventoryEntry, ...] = ()


class PortalProps(ContentModel):
    """The `kind: portal` block.

    Attributes
    ----------
    route : str
        The route this portal gates.
    requires_item : str or None
        A key, a writ, a password token.
    """

    route: RouteRef
    requires_item: EntityRef | None = None


class CombatAssignment(ContentModel):
    """How an actor fights.

    Attributes
    ----------
    profile : str
        The combat profile that supplies moves, patterns, and temperament.
    moves : tuple of str
        Extra moves this actor knows, over and above its profile's. A signature
        move on an otherwise ordinary bandit, without a profile to maintain.
    """

    profile: CombatProfileRef
    moves: tuple[MoveRef, ...] = ()


class Entity(ContentModel):
    """Anything the world contains that content can refer to by id."""

    id: Id
    extends: EntityRef | None = None
    kind: EntityKind = "fixture"
    name: str
    description: Description | None = None
    tags: tuple[Tag, ...] = ()
    playable: bool = False
    visible: bool = True

    stats: Mapping[Name, Stat] | None = None
    pools: Mapping[Name, float] | None = None
    inventory: tuple[InventoryEntry, ...] = ()
    equipment: Mapping[SlotName, EntityRef] | None = None
    skills: Mapping[EntityRef, int] | None = None
    disposition: Disposition | None = None
    combat: CombatAssignment | None = None
    env: tuple[EnvResponse, ...] = ()
    scenes: tuple[SceneRef, ...] = ()
    flags: tuple[Flag, ...] = ()

    item: ItemProps | None = None
    container: ContainerProps | None = None
    portal: PortalProps | None = None
    merchant: Merchant | None = None

    custom: Mapping[str, Any] | None = None

    @model_validator(mode="after")
    def _blocks_match_kind(self) -> Entity:
        """Reject an `item:` block on a fixture, and so on.

        The blocks are the one place where `kind` is load-bearing, so a
        mismatch is almost always a copy-paste error rather than an intent.
        """
        for block, kind in KIND_BLOCKS.items():
            if getattr(self, block) is not None and self.kind != kind:
                raise ValueError(
                    f"`{block}:` belongs to `kind: {kind}`, but `{self.id}` is "
                    f"`kind: {self.kind}`"
                )
        if self.kind == "portal" and self.portal is None:
            raise ValueError(f"`{self.id}` is a portal but has no `portal:` block")
        if self.playable and self.kind != "actor":
            raise ValueError(f"`{self.id}` is playable but is not `kind: actor`")
        return self
