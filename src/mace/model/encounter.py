"""Encounter tables — whether something happens on a road, and what.

Two stages, deliberately, because they answer two different questions and an
author wants to tune them separately.

**Stage one: does anything happen?** `chance`, rolled once per leg. This is the
road's danger dial, and it is one number.

**Stage two: what happens?** Every entry whose `when` passes is eligible, and
one is drawn by weight *among the eligible set*. Normalising among the eligible
is what lets an author write `when` conditions without silently changing how
dangerous a road is: at night the caravan drops out and the ogre becomes
proportionally likelier, so the road does not get quieter, it gets worse.

Most entries should not be fights. A road where a third of legs produce
something and two thirds of that something is weather, strangers and wildlife
reads as alive; a road where a third of legs produce a fight reads as a grind.
See docs/06-travel-and-encounters.md.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from mace.model.base import ContentModel, EncounterRef, EntityRef, Id, SceneRef
from mace.model.conditions import Conditions

__all__ = ["CombatEncounter", "EncounterEntry", "EncounterTable"]


class CombatEncounter(ContentModel):
    """A straight fight, without an interposing scene.

    Attributes
    ----------
    against : tuple of str
        The entities to spawn and fight. Repeat one to get several of it.
    flee_to : str or None
        Where fleeing puts the player. Omitted, they end up back the way they
        came, which for a journey is wherever they last stopped.
    surprise : bool
        Whether the fight opens at melee distance regardless of what the
        player has armed — wolves out of the brush don't wait for a bow to
        come up. False by default: a road encounter, unlike an ambush sprung
        by a scene, may just as well be bandits you saw coming
        (docs/07-combat.md § Range).
    """

    against: tuple[EntityRef, ...] = Field(min_length=1)
    flee_to: EntityRef | None = None
    surprise: bool = False


class EncounterEntry(ContentModel):
    """One thing that can happen, and how likely it is among the rest.

    Attributes
    ----------
    id : str
        Names it, for cooldowns and for the debug overlay.
    weight : float
        Relative weight among the entries currently eligible. Not a
        probability: `5` next to a total of 100 is the five-percent troll.
    when : tuple of Condition or None
        Eligibility. Time, weather, quest state, what the player is carrying.
    scene : str or None
        The scene played.
    combat : CombatEncounter or None
        A fight, for when a scene would only be ceremony.
    once : bool
        Never repeats in a playthrough.
    cooldown_ticks : int
        How long before this entry can recur.
    max_per_game : int or None
        A cap looser than `once`.
    """

    id: Id
    weight: float = Field(default=1.0, ge=0.0)
    when: Conditions | None = None

    scene: SceneRef | None = None
    combat: CombatEncounter | None = None

    once: bool = False
    cooldown_ticks: int = Field(default=0, ge=0)
    max_per_game: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _does_something(self) -> EncounterEntry:
        """An entry that plays nothing and fights nothing is a dead weight."""
        if self.scene is None and self.combat is None:
            raise ValueError(
                f"encounter `{self.id}` has neither a `scene` nor a `combat`, "
                "so nothing would happen if it fired"
            )
        return self


class EncounterTable(ContentModel):
    """A set of things that might happen, and how often anything does.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        A table to inherit from. A bandit-country road is a country road with
        worse entries.
    chance : float
        The probability that *something* happens, per roll. The one dial.
    min_gap_ticks : int
        A hard floor between encounters from this table. Pure independent
        rolls produce three ambushes in a row, and that feels broken even
        when it is fair.
    pressure_step : float
        How much an empty roll adds to the next one's chance. Tightens the
        variance without changing the long-run rate — see `EncounterMemory`
        for why it stays honest. Zero turns the pity system off.
    entries : tuple of EncounterEntry
        What can happen.
    """

    id: Id
    extends: EncounterRef | None = None
    name: str | None = None

    chance: float = Field(default=0.0, ge=0.0, le=1.0)
    min_gap_ticks: int = Field(default=0, ge=0)
    pressure_step: float = Field(default=0.0, ge=0.0, le=1.0)
    entries: tuple[EncounterEntry, ...] = ()

    @model_validator(mode="after")
    def _check_entries(self) -> EncounterTable:
        """Reject a table that can roll but has nothing to roll."""
        if self.chance > 0 and not self.entries:
            raise ValueError(
                "has a `chance` but no `entries`, so the roll would always "
                "find nothing to do"
            )
        ids = [entry.id for entry in self.entries]
        repeated = {name for name in ids if ids.count(name) > 1}
        if repeated:
            raise ValueError(
                f"entry ids repeat: {', '.join(sorted(repeated))}. They are "
                "how cooldowns and caps are tracked, so they must be unique."
            )
        return self
