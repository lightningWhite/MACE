"""The game manifest — what turns a pack of content into something playable.

`game.yml` is the one file a game pack has that a library pack does not. It
names the protagonist, where they wake up, how fast time moves, which pools are
structural, and what winning and losing mean.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from mace.model.base import (
    CalendarRef,
    ContentModel,
    EntityRef,
    Id,
    LocationRef,
    Name,
    QuestRef,
    Ref,
    RegionRef,
    SceneRef,
)
from mace.model.conditions import Conditions
from mace.model.text import Say

__all__ = [
    "CombatMode",
    "Game",
    "GameRules",
    "PlayerSetup",
    "WorldSetup",
]

CombatMode = Literal["reflex", "tactical", "auto"]
EconomyMode = Literal["simple", "market"]


class PlayerSetup(ContentModel):
    """Who the player is and where they start.

    Attributes
    ----------
    entity : str
        An entity with `playable: true`.
    start_location : str
        Where the game opens.
    creation_points : int
        Points the player may spend on stats marked `customizable`.
    backgrounds : tuple of str
        Optional starting variants offered at character creation.
    """

    entity: EntityRef
    start_location: LocationRef
    creation_points: int = Field(default=0, ge=0)
    backgrounds: tuple[Ref, ...] = ()


class WorldSetup(ContentModel):
    """How time and place are configured at the start of a playthrough.

    Attributes
    ----------
    minutes_per_tick : int
        How much world time one tick represents. Sets the pace of everything:
        travel, weather, hunger, the seven days you have left.
    calendar : str or None
        The calendar governing days, seasons, and day parts.
    start_tick : int
        The tick the game opens on — dawn of day one, or mid-morning.
    start_season : str or None
        Which season the game opens in.
    start_region : str or None
        Which region seeds the weather model.
    """

    minutes_per_tick: int = Field(default=30, gt=0)
    calendar: CalendarRef | None = None
    start_tick: int = Field(default=0, ge=0)
    start_season: Id | None = None
    start_region: RegionRef | None = None


class GameRules(ContentModel):
    """The structural choices a game makes about its own simulation.

    Attributes
    ----------
    vital_pool : str
        The pool whose exhaustion means death.
    effort_pool : str
        The pool combat actions are paid from.
    combat_mode : {'reflex', 'tactical', 'auto'}
        The default combat presentation. The player may override it.
    death_is_permanent : bool
        Whether death ends the playthrough or returns to a scene.
    survival : tuple of str
        Which survival systems are on: `exposure`, `rest`, `hunger`, `thirst`.
        Exposure and rest are on by default because they are what give the
        weather model teeth; hunger and thirst are not, because not every
        world wants to be about rations. `[]` disables them all.
    economy : {'simple', 'market'}
        `simple` prices from each item's `value`; `market` runs the full
        supply-and-demand model.
    """

    vital_pool: Name = "hitpoints"
    effort_pool: Name = "stamina"
    combat_mode: CombatMode = "tactical"
    death_is_permanent: bool = False
    survival: tuple[Id, ...] = ("exposure", "rest")
    economy: EconomyMode = "simple"


class Game(ContentModel):
    """The contents of a game pack's `game.yml`, under its `game:` key."""

    name: str
    tagline: str | None = None
    authors: tuple[str, ...] = ()
    difficulty: Id | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    introduction: Say = ()

    player: PlayerSetup
    world: WorldSetup = WorldSetup()
    rules: GameRules = GameRules()

    quests: tuple[QuestRef, ...] = ()
    win_conditions: Conditions = ()
    lose_conditions: Conditions = ()
    on_win: SceneRef | None = None
    on_lose: SceneRef | None = None
