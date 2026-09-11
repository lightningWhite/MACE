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

from typing import Literal

from pydantic import Field, model_validator

from mace.model.base import ClimateRef, ContentModel, FrontRef, Id, WeatherRef
from mace.model.conditions import Conditions

__all__ = ["Climate", "ClimateSequence", "SeasonProfile", "TemperatureRange"]


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


class SeasonProfile(ContentModel):
    """What one season is like in one climate.

    Attributes
    ----------
    temperature : TemperatureRange or None
        The daily band. Without one, nothing ever freezes here.
    weights : mapping
        Relative preference for each weather condition this season. These
        multiply the transition matrix, so a condition weighted 0 cannot
        happen this season however the chain gets there.
    """

    temperature: TemperatureRange | None = None
    weights: dict[WeatherRef, float] = Field(default_factory=dict)


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
        The conditions, in order, with how long each holds.
    """

    id: Id
    weight: float = Field(default=0.0, ge=0.0)
    when: Conditions | None = None
    steps: tuple[ClimateStep, ...] = Field(min_length=1)


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
    seasons : mapping
        Season id to what that season is like here. A season the calendar has
        and the climate does not falls back to the transition matrix alone.
    transitions : mapping
        Condition to the relative weight of each condition it can become.
        A condition absent from the matrix holds until something else moves
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

    seasons: dict[Id, SeasonProfile] = Field(default_factory=dict)
    transitions: dict[WeatherRef, dict[WeatherRef, float]] = Field(default_factory=dict)
    step_ticks: int = Field(default=1, gt=0)

    sequences: tuple[ClimateSequence, ...] = ()
    fronts: tuple[FrontRef, ...] = ()
    front_frequency: float = Field(default=0.0, ge=0.0, le=1.0)
    freezing_point: float = 0.0
    lapse_rate: float = 0.65
    temperature_unit: Literal["celsius", "fahrenheit"] = "celsius"

    @model_validator(mode="after")
    def _check_weights(self) -> Climate:
        """Reject weights that cannot select anything."""
        for name, row in self.transitions.items():
            if row and not any(weight > 0 for weight in row.values()):
                raise ValueError(
                    f"transitions from `{name}` are all zero, so the weather "
                    "could never leave it"
                )
        for season, profile in self.seasons.items():
            for condition, weight in profile.weights.items():
                if weight < 0:
                    raise ValueError(
                        f"season `{season}` weights `{condition}` at {weight}; "
                        "weights are never negative"
                    )
        return self

    def conditions_named(self) -> set[str]:
        """Every weather condition this climate refers to.

        Returns
        -------
        set of str
            References, as the author wrote them.
        """
        named: set[str] = set()
        for profile in self.seasons.values():
            named.update(profile.weights)
        for source, row in self.transitions.items():
            named.add(source)
            named.update(row)
        for sequence in self.sequences:
            named.update(step.condition for step in sequence.steps)
        return named


ClimateSequence.model_rebuild()
