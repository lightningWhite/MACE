"""Climates — what a place's weather is like, and how it changes.

Two halves, and the split is the whole idea. **Seasonal weights** say what a
region is *like*: an autumn lowland is mostly overcast with some drizzle. The
**transition matrix** says how weather actually *moves*: you do not go from
clear to blizzard, you go clear, overcast, drizzle, rain. Weights alone give a
slot machine; transitions alone give a world with no seasons. Multiplied
together they give weather with both character and coherence.

Hand-authored `sequences` are the escape hatch for drama an author wants to
happen exactly: once one is chosen it plays out uninterrupted, then the chain
resumes. See docs/05-world-simulation.md § Layer 2.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field, model_validator

from mace.model.base import ClimateRef, ContentModel, FrontRef, Id, WeatherRef
from mace.model.conditions import Conditions
from mace.model.weather import WeatherWeight

__all__ = [
    "Climate",
    "ClimateSequence",
    "SeasonWeather",
    "TemperatureRange",
    "Transition",
]


class TemperatureRange(ContentModel):
    """The band a season's daily temperatures are drawn from.

    Written in whatever scale the climate that holds it declares with
    `temperatureUnit` — the engine itself only ever compares against
    `freezingPoint`, so it never needs to know which one a pack chose.

    Attributes
    ----------
    min, max : float
        The coldest and warmest a day gets, before elevation.
    """

    min: float
    max: float

    @model_validator(mode="after")
    def _check_order(self) -> TemperatureRange:
        """Reject a band whose floor is above its ceiling."""
        if self.min > self.max:
            raise ValueError(f"min {self.min} is warmer than max {self.max}")
        return self


class SeasonWeather(ContentModel):
    """What one season is like in one climate.

    Attributes
    ----------
    id : str
        The season, as the calendar names it.
    temperature : TemperatureRange or None
        The daily band. Without one, nothing ever freezes here.
    weights : tuple of WeatherWeight
        Relative preference for each weather condition this season. These
        multiply the transition matrix, so a condition weighted 0 cannot
        happen this season however the chain gets there.
    """

    id: Id
    temperature: TemperatureRange | None = None
    weights: tuple[WeatherWeight, ...] = ()


class Transition(ContentModel):
    """One line of a climate's transition matrix.

    Attributes
    ----------
    source : str
        The condition the chain is currently in.
    target : str
        A condition it can become from there.
    weight : float
        Relative likelihood, among every `target` a `source` has a row for.
    """

    source: WeatherRef
    target: WeatherRef
    weight: float = Field(ge=0.0)


class ClimateSequence(ContentModel):
    """A hand-authored progression of conditions, played straight through.

    The v0 `conditionSequences` idea, kept: a three-day storm that breaks on
    the morning of the fourth is a story beat, and a Markov chain will not
    reliably produce one. Once chosen, a sequence runs to its end without the
    chain interfering.

    Attributes
    ----------
    id : str
        Names it, so an effect can call for it directly.
    weight : float
        How likely the chain is to enter this sequence rather than take an
        ordinary step. Zero means only an effect can start it.
    when : tuple of Condition or None
        Extra gating — a sequence that only happens in winter, or once the
        player has crossed the range.
    steps : tuple of ClimateStep
        The conditions, in order, with how long each holds. May also be
        written as a plain `"condition ticks"` line per step (`"clear 2"`,
        or bare `"clear"` for one tick) — the shape the wizard authors, since
        it has no nested-repeat control for a list within a list.
    """

    id: Id
    weight: float = Field(default=0.0, ge=0.0)
    when: Conditions | None = None
    steps: tuple[ClimateStep, ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _expand_step_lines(cls, value: Any) -> Any:
        """Expand `steps` written as bare `"condition ticks"` lines."""
        if not isinstance(value, Mapping):
            return value
        lines = value.get("steps")
        if not isinstance(lines, Sequence) or isinstance(lines, str | Mapping):
            return value
        if not all(isinstance(line, str) for line in lines):
            return value

        expanded: list[dict[str, Any]] = []
        for line in lines:
            parts = line.split()
            if len(parts) not in (1, 2):
                raise ValueError(
                    f'a sequence step is `"condition"` or `"condition ticks"`; '
                    f"got `{line}`"
                )
            step: dict[str, Any] = {"condition": parts[0]}
            if len(parts) == 2:
                step["ticks"] = parts[1]
            expanded.append(step)
        return {**value, "steps": expanded}


class ClimateStep(ContentModel):
    """One condition in a sequence, and how long it lasts.

    Attributes
    ----------
    condition : str
        The weather condition.
    ticks : int
        How many ticks it holds before the sequence moves on.
    """

    condition: WeatherRef
    ticks: int = Field(default=1, gt=0)


class Climate(ContentModel):
    """How weather behaves in the regions that use it.

    Attributes
    ----------
    id, name : str
        Identity.
    seasons : tuple of SeasonWeather
        What each season is like here. A season the calendar has and the
        climate does not falls back to the transition matrix alone.
    transitions : tuple of Transition
        Condition to the relative weight of each condition it can become.
        A condition with no `source` row holds until something else moves
        it, which is a reasonable reading of "the author forgot".
    step_ticks : int
        How many ticks pass between chain steps. One means the sky is
        reconsidered every tick, which is twitchy at thirty minutes a tick;
        two is an hour and reads much better.
    sequences : tuple of ClimateSequence
        Authored progressions that override the chain while they run.
    fronts : tuple of str
        The kinds of front that can form in regions with this climate.
    front_frequency : float
        The chance **per tick** that a front forms somewhere on the map. One
        roll is made across the whole world rather than one per region, so
        adding regions does not silently make a game stormier. Two or three
        fronts alive at once is plenty, so this wants to be small: at a
        sixty-tick lifespan, 0.02 keeps about one and a bit in the air.
    freezing_point : float
        The temperature below which a condition becomes its `freezesTo`.
    lapse_rate : float
        Degrees lost per hundred units of a region's `elevation`. 0.65 is the
        real world's; a game whose elevations are in feet, or whose
        temperatures are in Fahrenheit, sets its own.
    temperature_unit : "celsius" or "fahrenheit"
        The scale every temperature in this climate is written in. A
        front-end that lets a player choose °F or °C needs to know which one
        it was handed before it can convert; this is the one place that says
        so. Defaults to Celsius, which is what every temperature elsewhere in
        this model was already written assuming.
    """

    id: Id
    extends: ClimateRef | None = None
    name: str | None = None

    seasons: tuple[SeasonWeather, ...] = ()
    transitions: tuple[Transition, ...] = ()
    step_ticks: int = Field(default=1, gt=0)

    sequences: tuple[ClimateSequence, ...] = ()
    fronts: tuple[FrontRef, ...] = ()
    front_frequency: float = Field(default=0.0, ge=0.0, le=1.0)
    freezing_point: float = 0.0
    lapse_rate: float = 0.65
    temperature_unit: Literal["celsius", "fahrenheit"] = "celsius"

    @model_validator(mode="before")
    @classmethod
    def _fold_season_weights(cls, value: Any) -> Any:
        """Fold `seasonWeights` rows into their season's own `weights`.

        The wizard authors season weights as a flat `{season, condition,
        weight}` row at a time — its `Repeat` control cannot nest another
        `Repeat` inside one of its own entries, so naming the season on each
        row is the only way to build this a row at a time. This merges each
        row into the matching entry of `seasons` (adding the season if it
        is not there yet, overwriting only the one condition each row
        names) without disturbing anything already written by hand.
        """
        if not isinstance(value, Mapping):
            return value
        rows = value.get("seasonWeights")
        if not isinstance(rows, Sequence) or isinstance(rows, str | Mapping):
            return value

        by_id: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for season in value.get("seasons") or ():
            if isinstance(season, Mapping) and isinstance(season.get("id"), str):
                season_id = season["id"]
                by_id[season_id] = dict(season)
                by_id[season_id]["weights"] = list(season.get("weights") or ())
                order.append(season_id)

        for row in rows:
            if not isinstance(row, Mapping):
                continue
            season_id = row.get("season")
            if not isinstance(season_id, str):
                continue
            if season_id not in by_id:
                by_id[season_id] = {"id": season_id, "weights": []}
                order.append(season_id)
            weights = by_id[season_id]["weights"]
            entry = {"condition": row.get("condition"), "weight": row.get("weight")}
            for index, existing in enumerate(weights):
                if (
                    isinstance(existing, Mapping)
                    and existing.get("condition") == entry["condition"]
                ):
                    weights[index] = entry
                    break
            else:
                weights.append(entry)

        merged = dict(value)
        merged.pop("seasonWeights", None)
        merged["seasons"] = [by_id[season_id] for season_id in order]
        return merged

    @model_validator(mode="after")
    def _check_weights(self) -> Climate:
        """Reject a source whose transitions can never leave it."""
        by_source: dict[str, list[float]] = {}
        for row in self.transitions:
            by_source.setdefault(row.source, []).append(row.weight)
        for name, weights in by_source.items():
            if not any(weight > 0 for weight in weights):
                raise ValueError(
                    f"transitions from `{name}` are all zero, so the weather "
                    "could never leave it"
                )
        return self

    def season(self, season_id: str) -> SeasonWeather | None:
        """What this climate does in one season.

        Parameters
        ----------
        season_id : str
            The season, as the calendar names it.

        Returns
        -------
        SeasonWeather or None
            The season, or None when this climate says nothing special
            about it.
        """
        for one in self.seasons:
            if one.id == season_id:
                return one
        return None

    def transitions_from(self, condition: str) -> dict[str, float]:
        """Where the chain can go from one condition, and how likely each is.

        Parameters
        ----------
        condition : str
            The condition the chain is currently in.

        Returns
        -------
        dict
            Target condition to relative weight. Empty when the matrix says
            nothing about `condition`, which holds until something else
            moves it.
        """
        return {
            row.target: row.weight
            for row in self.transitions
            if row.source == condition
        }

    def conditions_named(self) -> set[str]:
        """Every weather condition this climate refers to.

        Returns
        -------
        set of str
            References, as the author wrote them.
        """
        named: set[str] = set()
        for season in self.seasons:
            named.update(weight.condition for weight in season.weights)
        for row in self.transitions:
            named.add(row.source)
            named.add(row.target)
        for sequence in self.sequences:
            named.update(step.condition for step in sequence.steps)
        return named


ClimateSequence.model_rebuild()
