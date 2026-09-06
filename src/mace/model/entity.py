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
from typing import Any, Literal

from pydantic import Field, model_validator

from mace.model.base import (
    ContentModel,
    EntityRef,
    Flag,
    Id,
    Name,
    Ref,
    RouteRef,
    SceneRef,
    SlotName,
    Tag,
)
from mace.model.conditions import Conditions
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
    "PortalProps",
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
}


class Stat(ContentModel):
    """A single ability or pool, before anything acts on it.

    Attributes
    ----------
    base : float
        The value with nothing acting on it.
    max : float or None
        Cap. Defaults to 100 for abilities; pools should set it explicitly.
    min : float
        Floor. Defaults to 0.
    customizable : bool
        Whether the player may spend creation points here at game start.
    growth : {'none', 'slow', 'normal', 'fast'}
        How fast the stat improves through use.
    """

    base: float
    max: float | None = None
    min: float = 0.0
    customizable: bool = False
    growth: Growth = "none"

    @model_validator(mode="after")
    def _range_is_sane(self) -> Stat:
        """A stat whose floor is above its cap can never be satisfied."""
        if self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) is above max ({self.max})")
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
    min, max : float
        The bounds of a single hit, before stats and gear.
    type : str
        Author-defined: `slash`, `pierce`, `plasma`.
    """

    min: float
    max: float
    type: Id | None = None

    @model_validator(mode="after")
    def _range_is_sane(self) -> Damage:
        """Damage that can never roll is a content mistake."""
        if self.min > self.max:
            raise ValueError(f"min damage ({self.min}) is above max ({self.max})")
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
    armor : float or None
        Damage reduction when worn.
    moves : tuple of str
        Combat moves this item grants its wielder.
    use : ItemUse or None
        What using it from the inventory does.
    value : float or None
        Base trade value, the anchor a market prices from.
    """

    weight: float | None = None
    stackable: bool | None = None
    equip_slot: SlotName | None = None
    damage: Damage | None = None
    armor: float | None = None
    moves: tuple[Ref, ...] = ()
    use: ItemUse | None = None
    value: float | None = None


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
    """

    profile: Ref


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
