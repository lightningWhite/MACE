"""Scenes — every interaction the player has, as a named, flat graph.

The v0 model nested a scene's fallbacks inside the scene, and their fallbacks
inside those, until nothing could be read or reused. Scenes here are named and
flat: branching is `goto`, the fallback is `else`, and both are references. The
wizard and the web editor can therefore draw the graph and find the parts of it
no player will ever reach.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from mace.model.base import ContentModel, Id, Ref, Tag
from mace.model.conditions import Conditions
from mace.model.effects import Effect
from mace.model.text import Say

__all__ = [
    "Choice",
    "Scene",
]


class Choice(ContentModel):
    """One option offered to the player.

    Attributes
    ----------
    prompt : str
        The option text.
    when : tuple of Condition or None
        Conditions required for the choice to be available.
    show_when_unavailable : bool
        Show the choice greyed out rather than hiding it, so the player can see
        what they are missing.
    unavailable_hint : str or None
        Why it is unavailable — "(You'd need ten gold.)"
    goto : str or None
        The scene this choice leads to.
    effects : tuple of Effect
        Inline effects, for one-liners not worth a scene of their own.
    """

    prompt: str
    when: Conditions | None = None
    show_when_unavailable: bool = False
    unavailable_hint: str | None = None
    goto: Ref | None = None
    effects: tuple[Effect, ...] = ()

    @model_validator(mode="after")
    def _leads_somewhere(self) -> Choice:
        """A choice that neither goes anywhere nor does anything is dead text."""
        if self.goto is None and not self.effects:
            raise ValueError(f"choice {self.prompt!r} needs `goto`, `effects`, or both")
        return self


class Scene(ContentModel):
    """A unit of interaction: some narration, some changes, and what comes next."""

    id: Id
    prompt: str | None = None
    visible: bool = True
    when: Conditions | None = None
    say: Say = ()
    effects: tuple[Effect, ...] = ()
    choices: tuple[Choice, ...] = ()
    goto: Ref | None = None
    otherwise: Ref | None = Field(default=None, alias="else")
    once: bool = False
    tags: tuple[Tag, ...] = ()

    @model_validator(mode="after")
    def _one_way_onward(self) -> Scene:
        """`goto` and `choices` are two answers to the same question."""
        if self.goto is not None and self.choices:
            raise ValueError(
                f"scene `{self.id}` has both `goto` and `choices`; a scene "
                "either jumps onward or offers a choice"
            )
        return self
