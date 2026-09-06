"""Answering the questions content asks.

Every condition tag in the vocabulary is answered here, and nowhere else. Two
rules govern the whole file:

- **A condition that cannot be answered is not `false`.** An unknown path, a
  missing entity, a stat nobody declared — these are content bugs, and quietly
  answering `false` is how a game ends up unplayable three hours in with no
  indication why. They raise, and the caller reports them.
- **Asking costs nothing except where it obviously does.** `chance` draws from
  a random stream; nothing else does. A condition evaluated twice must give the
  same answer both times, or replay stops working.

See docs/03-content-model.md § Conditions and effects.
"""

from __future__ import annotations

from collections.abc import Sequence

from mace.content import ContentError
from mace.engine.context import RuleContext
from mace.engine.state import EntityState
from mace.engine.stats import effective
from mace.model import Condition
from mace.model.conditions import (
    AtLocation,
    Chance,
    ConditionGroup,
    ConditionNegation,
    DayPartIs,
    ExprCondition,
    FlagIs,
    HasItem,
    QuestAtStage,
    QuestOutcome,
    SeasonIs,
    StatCompare,
    WeatherIs,
    WeatherTagIs,
)

__all__ = ["RuleError", "all_hold", "holds"]


class RuleError(Exception):
    """A condition or effect could not be evaluated.

    Parameters
    ----------
    message : str
        What went wrong, phrased for whoever wrote the content.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def all_hold(conditions: Sequence[Condition] | None, context: RuleContext) -> bool:
    """Whether every condition in a list holds.

    An empty or absent list holds — content that gates nothing is not gated.

    Parameters
    ----------
    conditions : sequence of Condition or None
        The conditions, ANDed.
    context : RuleContext
        What they may look at.

    Returns
    -------
    bool
        Whether all of them hold.
    """
    return all(holds(condition, context) for condition in conditions or ())


def holds(condition: Condition, context: RuleContext) -> bool:
    """Answer one condition.

    Parameters
    ----------
    condition : Condition
        The question.
    context : RuleContext
        What it may look at.

    Returns
    -------
    bool
        The answer.

    Raises
    ------
    RuleError
        If the question cannot be answered.
    """
    payload = condition.payload

    if isinstance(payload, ConditionGroup):
        if condition.tag == "all":
            return all(holds(inner, context) for inner in payload.conditions)
        return any(holds(inner, context) for inner in payload.conditions)

    if isinstance(payload, ConditionNegation):
        return not holds(payload.condition, context)

    if isinstance(payload, ExprCondition):
        return _expression(payload, context)

    if isinstance(payload, HasItem):
        actor = _actor(payload.actor, context)
        item = context.item_id(payload.item)
        if item is None:
            raise RuleError(f"`{payload.item}` is not an item that exists")
        return actor.inventory.get(item, 0) >= payload.qty

    if isinstance(payload, AtLocation):
        actor = _actor(payload.actor, context)
        return actor.location == _location(payload.location, context)

    if isinstance(payload, FlagIs):
        actor = _actor(payload.entity, context)
        return (payload.flag in actor.flags) is payload.is_

    if isinstance(payload, StatCompare):
        actor = _actor(payload.actor, context)
        value = effective(context.definition(actor), actor, payload.stat)
        if condition.tag == "statAtLeast":
            return value >= payload.value
        return value <= payload.value

    if isinstance(payload, DayPartIs):
        return context.clock.day_part(context.state.tick) in payload.parts

    if isinstance(payload, SeasonIs):
        return context.clock.season(context.state.tick).id in payload.seasons

    if isinstance(payload, QuestAtStage):
        quest = context.state.quests.get(_quest(payload.quest, context))
        return quest is not None and quest.stage == payload.stage

    if isinstance(payload, QuestOutcome):
        quest = context.state.quests.get(_quest(payload.quest, context))
        wanted = "complete" if condition.tag == "questComplete" else "failed"
        return quest is not None and quest.status.value == wanted

    if isinstance(payload, Chance):
        return context.state.rng.stream("ambient").chance(payload.probability)

    if isinstance(payload, WeatherIs):
        observed = context.weather()
        if observed.id is None:
            return False
        return any(
            _weather(reference, context) == observed.id
            for reference in payload.conditions
        )

    if isinstance(payload, WeatherTagIs):
        tags = context.weather().tags
        return any(tag in tags for tag in payload.tags)

    raise RuleError(f"condition `{condition.tag}` is not answerable yet")


def _expression(payload: ExprCondition, context: RuleContext) -> bool:
    """Evaluate an author expression against the world.

    Parameters
    ----------
    payload : ExprCondition
        The parsed expression.
    context : RuleContext
        What it may read.

    Returns
    -------
    bool
        Its truthiness.

    Raises
    ------
    RuleError
        If a path is unknown or a comparison is between wrong types.
    """
    from mace.engine.expr import ExprEvaluationError

    try:
        return payload.expression.is_true(context.expression_context())
    except ExprEvaluationError as error:
        raise RuleError(str(error)) from error


def _actor(reference: str, context: RuleContext) -> EntityState:
    """Find an entity, or say clearly that it is not here.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    EntityState
        The instance.

    Raises
    ------
    RuleError
        If nothing matches.
    """
    actor = context.actor(reference)
    if actor is None:
        raise RuleError(f"`{reference}` is not an entity in this playthrough")
    return actor


def _location(reference: str, context: RuleContext) -> str:
    """Qualify a location reference.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    try:
        return context.qualify(reference, "locations")
    except ContentError as error:
        raise RuleError(error.message) from error


def _weather(reference: str, context: RuleContext) -> str:
    """Reduce a weather-condition reference to the local id weather reports.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The local id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    try:
        qualified = context.qualify(reference, "weatherConditions")
    except ContentError as error:
        raise RuleError(error.message) from error
    return qualified.split(":", 1)[1]


def _quest(reference: str, context: RuleContext) -> str:
    """Qualify a quest reference.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    try:
        return context.qualify(reference, "quests")
    except ContentError as error:
        raise RuleError(error.message) from error
