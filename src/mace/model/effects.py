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
from typing import Any, Literal

from pydantic import Field, model_validator

from mace.model.base import (
    AuthoredValue,
    ContentModel,
    Flag,
    Id,
    Name,
    Ref,
    SlotName,
    shorthand,
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
    "dismissAlly",
    "endGame",
    "giveItem",
    "move",
    "playScene",
    "restart",
    "reveal",
    "setDisposition",
    "setFlag",
    "setStat",
    "setVar",
    "startCombat",
    "takeItem",
    "transferContents",
]


class EffectPayload(ContentModel):
    """Base class for the typed body of an effect."""


class AdjustStat(EffectPayload):
    """Move a stat or pool by a relative amount."""

    actor: Ref = "player"
    stat: Name
    delta: AuthoredValue
    reason: str | None = None


class SetStat(EffectPayload):
    """Set a stat or pool to an absolute value."""

    actor: Ref = "player"
    stat: Name
    value: AuthoredValue


class SetDisposition(EffectPayload):
    """Change how an entity feels about the player."""

    actor: Ref
    to: Literal["friendly", "neutral", "hostile"]


class ApplyModifier(EffectPayload):
    """Apply a temporary stat modifier, the way a potion or a spell would."""

    actor: Ref = "player"
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

    actor: Ref = "player"
    item: Ref
    qty: int = Field(default=1, ge=1)


class TransferContents(EffectPayload):
    """Move everything in one container or actor into another."""

    source: Ref = Field(alias="from")
    target: Ref = Field(alias="to")


class Move(EffectPayload):
    """Put an actor somewhere else, without travelling there."""

    actor: Ref = "player"
    to: Ref


class SetFlag(EffectPayload):
    """Set or clear a boolean flag on an entity."""

    entity: Ref
    flag: Flag
    value: bool = True


class SetVar(EffectPayload):
    """Set a game variable, readable from expressions as `vars.name`."""

    name: SlotName
    value: AuthoredValue


class Reveal(EffectPayload):
    """Make a location known, so it appears on the map and in travel menus."""

    location: Ref


class AdvanceQuest(EffectPayload):
    """Move a quest to a given stage, or to its next one."""

    quest: Ref
    stage: Id | None = None


class StartCombat(EffectPayload):
    """Hand control to the combat system."""

    against: tuple[Ref, ...] = Field(min_length=1)
    can_flee: bool = True
    on_flee: Ref | None = None

    @model_validator(mode="before")
    @classmethod
    def _expand_single_opponent(cls, value: Any) -> Any:
        """Accept `against: troll` for the common one-opponent fight."""
        if isinstance(value, Mapping) and isinstance(value.get("against"), str):
            return {**value, "against": [value["against"]]}
        return value


class AttachAlly(EffectPayload):
    """Add an entity to the player's party, optionally until a condition holds."""

    entity: Ref
    until: Condition | None = None


class DismissAlly(EffectPayload):
    """Remove an entity from the player's party."""

    entity: Ref


class AdvanceTime(EffectPayload):
    """Push the world clock forward — resting, waiting, a long conversation."""

    ticks: int = Field(gt=0)

    _expand = shorthand("ticks")


class PlayScene(EffectPayload):
    """Run another scene."""

    scene: Ref

    _expand = shorthand("scene")

    def authored(self) -> Any:
        return self.scene


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
    "dismissAlly": DismissAlly,
    "endGame": NoArguments,
    "giveItem": ItemTransfer,
    "move": Move,
    "playScene": PlayScene,
    "restart": NoArguments,
    "reveal": Reveal,
    "setDisposition": SetDisposition,
    "setFlag": SetFlag,
    "setStat": SetStat,
    "setVar": SetVar,
    "startCombat": StartCombat,
    "takeItem": ItemTransfer,
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
