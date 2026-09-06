"""Moves and combat profiles — what a fighter can do, and how it behaves.

Two content types, and the split between them is the whole of what makes an
enemy learnable.

A **move** is one thing that can happen in an exchange. An attack telegraphs
itself (`tell`), takes a while to land (`windupMs`), and is beaten by particular
defenses (`counters`). A defense is the answer: it has a type, a price in
effort, and a share of the damage it stops when it lands late. The counter
matrix is therefore *content* — a sci-fi pack whose defenses are `sidestep`,
`shieldUp`, and `overload` needs no engine change (docs/07-combat.md).

A **profile** is temperament: which moves a fighter knows, how often it feints,
how legibly it telegraphs, when it runs — and its `patterns`, the weighted
sequences it plays. Patterns are the reason any of this is worth authoring. An
enemy that picks at random is noise, and noise cannot be learned; an enemy that
likes to swing twice high then go low is a thing a player can beat by paying
attention, which is the point of the whole system (ADR-0006).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from mace.model.base import (
    CombatProfileRef,
    ContentModel,
    Id,
    MoveRef,
    Tag,
)
from mace.model.conditions import Conditions
from mace.model.effects import Effect
from mace.model.entity import Damage
from mace.model.text import Description

__all__ = ["CombatProfile", "Move", "MoveKind", "Pattern"]

MoveKind = Literal["attack", "defense"]


class Move(ContentModel):
    """One thing a fighter can do in an exchange.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        A move to inherit from.
    kind : {'attack', 'defense'}
        Whether this is something you telegraph or something you answer with.
    type : str
        Author-defined: `overhead`, `thrust`, `sweep` for attacks; `parry`,
        `dodge`, `block` for defenses. An attack's `counters` names defense
        types, so the two vocabularies meet here and nowhere in the engine.
    tell : Description or None
        The telegraph, for an attack. "The troll hauls the club over its head."
    vague_tell : Description or None
        The same windup, badly read — what a low `tellClarity` shows instead.
        Without one, an unclear tell is simply withheld, which is worse
        atmosphere and the same information.
    windup_ms : int
        How long the defender has, before their speed widens it.
    counters : tuple of str
        Defense *types* that beat this attack.
    damage : Damage or None
        What it does when it lands. A defense may carry damage too — that is
        what `strike` is: an interrupt that answers a grapple by hurting it.
    cost : float
        Effort-pool cost of using it.
    mitigation : float
        For a defense: the share of damage it stops when the read was right
        but the timing was not. A dodge is cheap and stops everything or
        nothing; a block is expensive and always takes some of the sting out.
    feint : bool
        Marks a move as the pack's feint: a windup that means nothing, whose
        only correct answer is whatever `counters` names.
    effects : tuple of Effect
        Applied to the defender when the move lands.
    tags : tuple of str
        Free-form labels.
    """

    id: Id
    extends: MoveRef | None = None
    name: str | None = None
    kind: MoveKind = "attack"
    type: Id

    tell: Description | None = None
    vague_tell: Description | None = None
    windup_ms: int = Field(default=1000, gt=0)
    counters: tuple[Id, ...] = ()

    damage: Damage | None = None
    cost: float = Field(default=0.0, ge=0.0)
    mitigation: float = Field(default=0.5, ge=0.0, le=1.0)
    feint: bool = False

    effects: tuple[Effect, ...] = ()
    tags: tuple[Tag, ...] = ()

    @property
    def label(self) -> str:
        """What to call this move in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Move:
        """Reject an attack that never telegraphs, or a defense that does."""
        if self.kind == "attack":
            if self.tell is None:
                raise ValueError(
                    f"attack `{self.id}` has no `tell`, so the player would be "
                    "asked to answer something they were never shown"
                )
        else:
            if self.tell is not None or self.vague_tell is not None:
                raise ValueError(
                    f"defense `{self.id}` has a `tell`; only attacks telegraph"
                )
            if self.feint:
                raise ValueError(f"defense `{self.id}` cannot be a feint")
        return self


class Pattern(ContentModel):
    """A sequence of moves a fighter tends to play, and how often.

    Attributes
    ----------
    sequence : tuple of str
        The moves, in order. Played to the end before another pattern is
        picked, which is what makes a habit observable.
    weight : float
        Relative weight among the patterns currently eligible.
    when : tuple of Condition or None
        Eligibility. A wolf pack hunts differently in the dark.
    """

    sequence: tuple[MoveRef, ...] = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0.0)
    when: Conditions | None = None


class CombatProfile(ContentModel):
    """How a fighter fights: its moves, its habits, and its nerve.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        A profile to inherit from. A veteran duelist is a duelist that feints
        more and telegraphs less.
    moves : tuple of str
        Every move this fighter can use, attacks and defenses both. A
        defender's answers come from here, so a fighter with no defense moves
        can only take the hit.
    patterns : tuple of Pattern
        Weighted sequences. Empty means moves are drawn at random, which is
        legal, cheap, and unlearnable — see ADR-0006.
    aggression : float
        0 to 1. How readily it presses an attack it cannot really afford.
    feint_chance : float
        0 to 1. How often a windup means nothing.
    tell_clarity : float
        0 to 1. How legibly it telegraphs. A veteran shows you very little.
    flee_threshold : float
        The share of its vital pool at which it tries to run. 0 never runs.
    tags : tuple of str
        Free-form labels.
    """

    id: Id
    extends: CombatProfileRef | None = None
    name: str | None = None

    moves: tuple[MoveRef, ...] = ()
    patterns: tuple[Pattern, ...] = ()

    aggression: float = Field(default=0.5, ge=0.0, le=1.0)
    feint_chance: float = Field(default=0.0, ge=0.0, le=1.0)
    tell_clarity: float = Field(default=1.0, ge=0.0, le=1.0)
    flee_threshold: float = Field(default=0.0, ge=0.0, le=1.0)

    tags: tuple[Tag, ...] = ()

    @property
    def label(self) -> str:
        """What to call this profile in a debug overlay.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id

    @model_validator(mode="after")
    def _feints_need_a_move(self) -> CombatProfile:
        """A feint chance with nothing to feint with never fires."""
        if self.feint_chance > 0 and not self.moves:
            raise ValueError(
                f"profile `{self.id}` has a `feintChance` but no `moves`, so "
                "there is nothing for it to feint with"
            )
        return self
