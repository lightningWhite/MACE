"""Pydantic content models — the authoring-time shapes.

These describe what a thing *is* (a troll's base strength), never what it is
doing right now in a playthrough. Content models are frozen after load; runtime
values live in `mace.engine.state`. See docs/03-content-model.md.

These models validate **compiled** content: the loader globs a pack's files,
resolves `extends` inheritance and its `$append` / `$remove` sentinels on the
raw mappings, and only then builds models. By the time an `Entity` exists,
inheritance is a thing that happened, not a thing to do — which is why `name`
is required here even though a child entity may inherit it.

Two conveniences run at validation time rather than being left to the engine:
author expressions are parsed (so a typo in a condition is a load-time error
with a caret under it), and shorthands are expanded — a bare string where a
description was expected, a lone condition where a list was expected.
"""

from mace.model.background import Background, StatGrant
from mace.model.base import (
    AuthoredValue,
    ContentModel,
    ExpressionField,
    Flag,
    Id,
    Name,
    PackId,
    Ref,
    SlotName,
    Tag,
    Version,
    VersionRange,
    authored_value,
)
from mace.model.calendar import STANDARD_YEAR, Calendar, DayPart, Season
from mace.model.climate import (
    Climate,
    ClimateSequence,
    ClimateStep,
    SeasonProfile,
    TemperatureRange,
)
from mace.model.combat import CombatProfile, Move, MoveKind, Pattern
from mace.model.conditions import (
    Condition,
    ConditionPayload,
    Conditions,
    ConditionTag,
)
from mace.model.effects import Effect, EffectPayload, EffectTag
from mace.model.encounter import CombatEncounter, EncounterEntry, EncounterTable
from mace.model.entity import (
    CombatAssignment,
    ContainerProps,
    Damage,
    Entity,
    EntityKind,
    EnvResponse,
    InventoryEntry,
    ItemProps,
    ItemUse,
    PortalProps,
    Stat,
    StatModifier,
)
from mace.model.event import (
    CelestialEvent,
    EventPhaseBody,
    EventScope,
    EventWhile,
    Omen,
    Period,
    Phase,
    Pressure,
    PressureEvent,
    PressureModifier,
    PressureStart,
)
from mace.model.front import WeatherFront
from mace.model.game import (
    CombatMode,
    Game,
    GameRules,
    PlayerSetup,
    WorldSetup,
)
from mace.model.location import ClimateOverride, Exit, Location, MapPosition
from mace.model.pack import Pack, PackKind, PackRequirement
from mace.model.quest import Quest, QuestStage
from mace.model.region import Region
from mace.model.route import Route, Waypoint
from mace.model.scene import Choice, Scene
from mace.model.terrain import Terrain
from mace.model.text import Description, DescriptionLine, Say, SayLine
from mace.model.weather import WeatherCondition

__all__ = [
    "AuthoredValue",
    "STANDARD_YEAR",
    "Background",
    "Calendar",
    "CelestialEvent",
    "Choice",
    "Climate",
    "ClimateOverride",
    "ClimateSequence",
    "ClimateStep",
    "CombatAssignment",
    "CombatEncounter",
    "CombatMode",
    "CombatProfile",
    "Condition",
    "ConditionPayload",
    "ConditionTag",
    "Conditions",
    "ContainerProps",
    "ContentModel",
    "Damage",
    "DayPart",
    "Description",
    "DescriptionLine",
    "Effect",
    "EffectPayload",
    "EffectTag",
    "EncounterEntry",
    "EncounterTable",
    "EventPhaseBody",
    "EventScope",
    "EventWhile",
    "EncounterTable",
    "Entity",
    "EntityKind",
    "EnvResponse",
    "Exit",
    "ExpressionField",
    "Flag",
    "Game",
    "GameRules",
    "Id",
    "InventoryEntry",
    "ItemProps",
    "ItemUse",
    "Location",
    "MapPosition",
    "Move",
    "MoveKind",
    "Name",
    "Omen",
    "Pack",
    "PackId",
    "PackKind",
    "PackRequirement",
    "Pattern",
    "PlayerSetup",
    "Period",
    "Phase",
    "PortalProps",
    "Pressure",
    "PressureEvent",
    "PressureModifier",
    "PressureStart",
    "Quest",
    "QuestStage",
    "Ref",
    "Region",
    "Route",
    "Say",
    "SayLine",
    "Scene",
    "Season",
    "SeasonProfile",
    "SlotName",
    "Stat",
    "StatGrant",
    "StatModifier",
    "Tag",
    "TemperatureRange",
    "Terrain",
    "Version",
    "VersionRange",
    "Waypoint",
    "WeatherCondition",
    "WeatherFront",
    "WorldSetup",
    "authored_value",
]
