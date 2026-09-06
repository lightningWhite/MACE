"""Conditions — the questions content asks about the world.

A condition is a one-key mapping whose key names the question and whose body
supplies the arguments::

    when:
      - {hasItem: {actor: player, item: fantasy.core:gold, qty: 10}}
      - {weather: [rain, storm]}
      - {expr: "world.day > 7"}

A list of conditions is ANDed; `all`, `any`, and `not` cover the rest. Every
tag in the vocabulary has a typed body, so a misspelled field is a load-time
error rather than a condition that quietly never fires. See
docs/04-schema-reference.md and ADR-0003.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from mace.model.base import (
    ContentModel,
    ExpressionField,
    Flag,
    Id,
    Name,
    Ref,
    Tag,
    shorthand,
    unwrap_tagged,
)

__all__ = [
    "Condition",
    "ConditionPayload",
    "ConditionTag",
    "Conditions",
]

ConditionTag = Literal[
    "all",
    "any",
    "atLocation",
    "chance",
    "dayPart",
    "expr",
    "flag",
    "hasItem",
    "not",
    "questComplete",
    "questFailed",
    "questStage",
    "statAtLeast",
    "statAtMost",
    "weather",
    "weatherTag",
]


class ConditionPayload(ContentModel):
    """Base class for the typed body of a condition."""


class HasItem(ConditionPayload):
    """The actor carries at least `qty` of an item."""

    actor: Ref = "player"
    item: Ref
    qty: int = Field(default=1, ge=1)


class AtLocation(ConditionPayload):
    """The actor is at a location."""

    actor: Ref = "player"
    location: Ref


class FlagIs(ConditionPayload):
    """An entity's boolean flag has a given value."""

    entity: Ref
    flag: Flag
    is_: bool = Field(default=True, alias="is")


class StatCompare(ConditionPayload):
    """An actor's effective stat is at or beyond a threshold."""

    actor: Ref = "player"
    stat: Name
    value: float


class QuestStage(ConditionPayload):
    """A quest is currently at a given stage."""

    quest: Ref
    stage: Id


class QuestRef(ConditionPayload):
    """A quest has completed, or failed."""

    quest: Ref

    _expand = shorthand("quest")

    def authored(self) -> Any:
        return self.quest


class Chance(ConditionPayload):
    """A weighted coin flip on the surrounding content's RNG stream."""

    probability: float = Field(ge=0.0, le=1.0)

    _expand = shorthand("probability")

    def authored(self) -> Any:
        return self.probability


class ExprCondition(ConditionPayload):
    """An author expression, parsed at load time."""

    expression: ExpressionField

    _expand = shorthand("expression")

    def authored(self) -> Any:
        return self.expression.source


class WeatherIs(ConditionPayload):
    """The current weather is one of these conditions."""

    conditions: tuple[Ref, ...] = Field(min_length=1)

    _expand = shorthand("conditions")

    def authored(self) -> Any:
        return list(self.conditions)


class WeatherTagIs(ConditionPayload):
    """The current weather carries one of these tags — `wet`, `cold`, `dark`."""

    tags: tuple[Tag, ...] = Field(min_length=1)

    _expand = shorthand("tags")

    def authored(self) -> Any:
        return list(self.tags)


class DayPartIs(ConditionPayload):
    """The world clock is in one of these parts of the day."""

    parts: tuple[Id, ...] = Field(min_length=1)

    _expand = shorthand("parts")

    def authored(self) -> Any:
        return list(self.parts)


class ConditionGroup(ConditionPayload):
    """A group of conditions, for `all` and `any`."""

    conditions: tuple[Condition, ...] = Field(min_length=1)

    _expand = shorthand("conditions")

    def authored(self) -> Any:
        return [condition.authored() for condition in self.conditions]


class ConditionNegation(ConditionPayload):
    """A single negated condition."""

    condition: Condition

    _expand = shorthand("condition", bare_mapping=True)

    def authored(self) -> Any:
        return self.condition.authored()


#: The typed body each condition tag expects.
CONDITION_PAYLOADS: dict[ConditionTag, type[ConditionPayload]] = {
    "all": ConditionGroup,
    "any": ConditionGroup,
    "atLocation": AtLocation,
    "chance": Chance,
    "dayPart": DayPartIs,
    "expr": ExprCondition,
    "flag": FlagIs,
    "hasItem": HasItem,
    "not": ConditionNegation,
    "questComplete": QuestRef,
    "questFailed": QuestRef,
    "questStage": QuestStage,
    "statAtLeast": StatCompare,
    "statAtMost": StatCompare,
    "weather": WeatherIs,
    "weatherTag": WeatherTagIs,
}


class Condition(ContentModel):
    """One authored condition: a tag naming the question, and its typed body.

    Attributes
    ----------
    tag : ConditionTag
        Which question is being asked.
    payload : ConditionPayload
        The arguments, validated against the body type registered for `tag`.
    """

    tag: ConditionTag
    payload: ConditionPayload

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        """Turn the authored `{tag: body}` mapping into tag and payload."""
        tag, body = unwrap_tagged(
            value, kind="condition", vocabulary=tuple(CONDITION_PAYLOADS)
        )
        payload = CONDITION_PAYLOADS[tag]  # type: ignore[index]
        return {"tag": tag, "payload": payload.model_validate(body)}

    def authored(self) -> Any:
        return {self.tag: self.payload.authored()}


def _as_condition_list(value: Any) -> Any:
    """Accept a single condition where a list of conditions is expected.

    A description line's `when` takes one condition and a scene's `when` takes
    several; authors should not have to remember which. A lone condition
    becomes a one-element list, and a list is ANDed as usual.

    Parameters
    ----------
    value : object
        The raw YAML value.

    Returns
    -------
    object
        A sequence of conditions.
    """
    if isinstance(value, Mapping) or isinstance(value, Condition):
        return [value]
    return value


#: A list of conditions, ANDed. Accepts a single condition as shorthand.
Conditions = Annotated[tuple[Condition, ...], BeforeValidator(_as_condition_list)]

ConditionGroup.model_rebuild()
ConditionNegation.model_rebuild()
