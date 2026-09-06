"""Session state: what a particular playthrough is doing right now.

The counterpart to `mace.model`, and the other half of architecture boundary 1.
Content says trolls have base strength 70; state says *this* troll is at 31
hitpoints and afraid. Ten goblins from one definition are ten state objects
pointing at one content object.

State is mutable. Determinism does not need immutability — it needs the same
seed and the same actions to produce the same sequence — and a save is the
seed plus the action log, so no earlier state ever has to be kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from mace.engine.rng import RandomSource

__all__ = [
    "EntityState",
    "GameState",
    "Modifier",
    "Outcome",
    "PendingChoice",
    "PendingChoices",
    "QuestState",
    "QuestStatus",
]


class Outcome(Enum):
    """How a playthrough stands."""

    PLAYING = "playing"
    WON = "won"
    LOST = "lost"


class QuestStatus(Enum):
    """Where a quest has got to."""

    HIDDEN = "hidden"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(slots=True)
class Modifier:
    """A temporary adjustment to one stat.

    Attributes
    ----------
    stat : str
        The stat affected.
    add : float
        A flat adjustment, applied before `mult`.
    mult : float
        A multiplier.
    label : str
        What the player sees this called — "Elixir of Haste".
    source : str
        Where it came from, for debugging and for removing a whole source.
    expires_at_tick : int or None
        When it lapses. None never lapses.
    """

    stat: str
    add: float = 0.0
    mult: float = 1.0
    label: str = ""
    source: str = ""
    expires_at_tick: int | None = None


@dataclass(slots=True)
class EntityState:
    """One entity, as it exists in this playthrough.

    Attributes
    ----------
    instance_id : str
        Unique within the session. `bridge-troll#3` for the third one spawned.
    definition : str
        The fully qualified content id this was instantiated from.
    location : str or None
        Qualified location id, or None for something being carried.
    pools : dict
        Current value of each pool — hitpoints, stamina.
    inventory : dict
        Qualified item id to quantity.
    equipment : dict
        Slot name to qualified item id.
    flags : set of str
        Boolean flags an author set or a scene raised.
    modifiers : list of Modifier
        Temporary stat adjustments.
    disposition : str or None
        Current stance toward the player.
    """

    instance_id: str
    definition: str
    location: str | None = None
    pools: dict[str, float] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    equipment: dict[str, str] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    modifiers: list[Modifier] = field(default_factory=list)
    disposition: str | None = None


@dataclass(slots=True)
class QuestState:
    """One quest's progress.

    Attributes
    ----------
    quest : str
        Qualified quest id.
    status : QuestStatus
        Hidden, active, complete, or failed.
    stage : str or None
        The current stage's id.
    started_at_tick : int or None
        When it became active, for deadline conditions.
    """

    quest: str
    status: QuestStatus = QuestStatus.HIDDEN
    stage: str | None = None
    started_at_tick: int | None = None


@dataclass(slots=True)
class PendingChoice:
    """One option currently on offer.

    Attributes
    ----------
    prompt : str
        What the player reads.
    goto : str or None
        The scene it leads to.
    travel : str or None
        The location it goes to. Set on the menu the engine offers between
        scenes; a scene's own choices never travel.
    effects : tuple
        Inline effects to apply if it is taken.
    available : bool
        Whether it can be taken. An unavailable choice is only ever shown
        because the author asked for it to be, so the player can see what they
        are missing.
    hint : str or None
        Why it is unavailable.
    """

    prompt: str
    goto: str | None = None
    travel: str | None = None
    effects: tuple[Any, ...] = ()
    available: bool = True
    hint: str | None = None


@dataclass(slots=True)
class PendingChoices:
    """The choices the game is waiting on.

    While this is set, the only action that means anything is choosing one.

    Attributes
    ----------
    scene : str
        The qualified id of the scene that offered them.
    options : tuple of PendingChoice
        The options, in the order they were presented.
    """

    scene: str
    options: tuple[PendingChoice, ...]


@dataclass(slots=True)
class GameState:
    """Everything one playthrough knows about itself.

    Attributes
    ----------
    pack : str
        The game pack's id. Bare references in content resolve against it.
    seed : str
        The session seed. With the pack list and the action log, this is the
        whole save.
    rng : RandomSource
        Named random streams, positioned wherever play has taken them.
    tick : int
        World time. Its real-world meaning is `game.world.minutesPerTick`.
    player : str
        The protagonist's instance id.
    entities : dict
        Instance id to entity state.
    quests : dict
        Qualified quest id to progress.
    variables : dict
        Author-set game variables, readable from expressions as `vars.name`.
    revealed : set of str
        Qualified ids of locations the player knows about.
    played : set of str
        Qualified ids of scenes that have run, for `once`.
    pending : PendingChoices or None
        Choices awaiting an answer.
    outcome : Outcome
        Whether the game is still running, and how it ended if not.
    ended_because : str or None
        What ended it, for the `game.over` event.
    """

    pack: str
    seed: str
    rng: RandomSource
    player: str
    tick: int = 0
    entities: dict[str, EntityState] = field(default_factory=dict)
    quests: dict[str, QuestState] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    revealed: set[str] = field(default_factory=set)
    played: set[str] = field(default_factory=set)
    pending: PendingChoices | None = None
    outcome: Outcome = Outcome.PLAYING
    ended_because: str | None = None

    @property
    def protagonist(self) -> EntityState:
        """The player's entity.

        Returns
        -------
        EntityState
            The protagonist's state.
        """
        return self.entities[self.player]

    @property
    def location(self) -> str | None:
        """Where the player is.

        Returns
        -------
        str or None
            Qualified location id.
        """
        return self.protagonist.location

    def here(self) -> list[EntityState]:
        """Every entity in the player's location, the player excluded.

        Returns
        -------
        list of EntityState
            Present entities, in instance-id order so nothing depends on how
            a dict happened to be built.
        """
        where = self.location
        return [
            entity
            for _key, entity in sorted(self.entities.items())
            if entity.location == where and entity.instance_id != self.player
        ]
