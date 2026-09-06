"""Quests — the middle layer between a scene and the end of the game.

A game can get by with `game.winConditions` alone. A game that feels like it
has a plot needs stages: something to be doing now, a journal line saying what,
and a way to fail it that is not death.
"""

from __future__ import annotations

from pydantic import Field

from mace.model.base import ContentModel, Id
from mace.model.conditions import Conditions
from mace.model.effects import Effect

__all__ = [
    "Quest",
    "QuestStage",
]


class QuestStage(ContentModel):
    """One step of a quest.

    Attributes
    ----------
    id : str
        Stage id, referenced by the `questStage` condition.
    journal : str
        What the player reads in the quest log while this stage is current.
    complete : tuple of Condition
        Conditions that advance to the next stage.
    fail : tuple of Condition or None
        Conditions that fail the whole quest.
    on_enter : tuple of Effect
        Effects fired when this stage becomes current.
    deadline_ticks : int or None
        Shorthand for a tick-count fail condition.
    """

    id: Id
    journal: str
    complete: Conditions = Field(min_length=1)
    fail: Conditions | None = None
    on_enter: tuple[Effect, ...] = ()
    deadline_ticks: int | None = Field(default=None, gt=0)


class Quest(ContentModel):
    """An objective with stages, a journal, and consequences."""

    id: Id
    name: str
    summary: str | None = None
    hidden_until: Conditions | None = None
    stages: tuple[QuestStage, ...] = Field(min_length=1)
    on_complete: tuple[Effect, ...] = ()
    on_fail: tuple[Effect, ...] = ()
