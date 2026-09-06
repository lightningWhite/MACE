"""Backgrounds — who the protagonist was before the game started.

A game's protagonist is one entity, authored once. A background is a variant
of that person offered at character creation: the farmhand's arms, the
poacher's quiet feet, the old soldier's worn blade and the fact that the
captain of the guard remembers his face.

This is deliberately not a class system. A background grants starting stats,
items, skills, a flag scenes can check, and sometimes a different opening
scene — all of it content, none of it engine. An author who wants six
backgrounds writes six; an author who wants none writes none, and character
creation is then just the creation points (open question 6).

See docs/13-open-questions.md #6 and docs/04-schema-reference.md § Background.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from pydantic import Field, model_validator

from mace.model.base import (
    BackgroundRef,
    ContentModel,
    EntityRef,
    Flag,
    Id,
    Name,
    SceneRef,
)
from mace.model.entity import InventoryEntry

__all__ = ["Background", "StatGrant"]


class StatGrant(ContentModel):
    """What a background does to one of the protagonist's stats.

    `add` is the ordinary case, because a background is a variation on a person
    rather than a replacement for them: the poacher is *the protagonist, plus
    fifteen stealth*, so an author who later raises the protagonist's base
    stealth raises every background's with it. `set` exists for the case where
    a background genuinely fixes a value regardless of the entity it modifies.

    Attributes
    ----------
    add : float or None
        A relative adjustment to the stat's base.
    set_ : float or None
        An absolute base, replacing whatever the entity declared.
    """

    shorthand_field: ClassVar[str] = "add"

    add: float | None = None
    set_: float | None = Field(default=None, alias="set")

    @model_validator(mode="after")
    def _changes_something(self) -> StatGrant:
        """A grant that neither adds nor sets does nothing."""
        if self.add is None and self.set_ is None:
            raise ValueError("a stat grant needs `add`, `set`, or both")
        return self

    def apply(self, base: float) -> float:
        """What this grant makes of a starting value.

        Parameters
        ----------
        base : float
            The protagonist's own base for the stat.

        Returns
        -------
        float
            The background's base for it. `set` lands first and `add` moves
            off it, so `{set: 10, add: 5}` is fifteen rather than ambiguous.
        """
        value = base if self.set_ is None else self.set_
        return value if self.add is None else value + self.add


class Background(ContentModel):
    """A starting variant of the protagonist, offered at character creation.

    Attributes
    ----------
    id, name : str
        Identity. `name` is what the player is offered.
    extends : str or None
        A background to inherit from.
    description : str
        Shown at character creation. This is the whole of the pitch, so it is
        the one field worth writing properly.
    stats : mapping
        Stat name to the grant applied to the protagonist's base.
    inventory : tuple of InventoryEntry
        Items the protagonist starts with, on top of their own.
    skills : mapping
        Item reference to starting proficiency, merged over the entity's own.
    grants_flag : str or None
        A flag set on the protagonist, so scenes can recognise them later.
    opening_scene : str or None
        Played instead of arriving at the start location.
    """

    id: Id
    extends: BackgroundRef | None = None
    name: str | None = None
    description: str = ""

    stats: Mapping[Name, StatGrant] = Field(default_factory=dict)
    inventory: tuple[InventoryEntry, ...] = ()
    skills: Mapping[EntityRef, int] = Field(default_factory=dict)
    grants_flag: Flag | None = None
    opening_scene: SceneRef | None = None

    @property
    def label(self) -> str:
        """What to call this background in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id
