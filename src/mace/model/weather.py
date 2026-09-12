"""Weather conditions — what the sky is doing, and what that costs you.

A condition is the leaf of the weather model: climates decide which one holds
where and when, and this says what holding it means. Weather that only reads
nicely is scenery, so every field here is something the rest of the engine
acts on — visibility feeds light, `travelMultiplier` lengthens roads,
`blocksTravel` closes them, `modify` reaches every exposed actor, and `tags`
are what entity `env` responses and encounter tables match against.

Tags matter more than they look: an entity that reacts to `cold` reacts to a
snow type invented three packs later without anyone touching it. See
docs/05-world-simulation.md § Layer 4.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from mace.model.base import ContentModel, Id, Name, Tag, WeatherRef
from mace.model.entity import StatModifier
from mace.model.text import Description

__all__ = ["IntensityRange", "WeatherCondition", "WeatherWeight"]


class IntensityRange(ContentModel):
    """The band a condition's or a front's intensity is drawn within.

    Attributes
    ----------
    min, max : float
        0 to 1. Intensity scales `modify`, a front's bias, and how the
        front-end phrases what is happening.
    """

    min: float = Field(default=0.0, ge=0.0, le=1.0)
    max: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_order(self) -> IntensityRange:
        """Reject a band whose floor is above its ceiling."""
        if self.min > self.max:
            raise ValueError(f"min {self.min} is higher than max {self.max}")
        return self


class WeatherWeight(ContentModel):
    """A weather condition, and how much of it there should be.

    Used both for a season's preference among conditions and for a front's
    bias on top of the transition matrix — the same shape either way.

    Attributes
    ----------
    condition : str
        The weather condition.
    weight : float
        Never negative. A season's `weights` reads this as a relative
        preference; a front's `biases` reads it as a multiplier.
    """

    condition: WeatherRef
    weight: float = Field(ge=0.0)


class WeatherCondition(ContentModel):
    """One state of the sky, and its consequences.

    Attributes
    ----------
    id, name : str
        Identity. `name` is what the player reads; it defaults to the id.
    description : Description or None
        Lines narrated when this condition begins. Conditional, so the same
        rain can read differently at night.
    intensity_range : IntensityRange
        The band this condition's intensity is drawn within, 0 to 1.
        Intensity scales `modify` and how the front-end phrases it.
    visibility : float
        0 to 1, multiplied into the day part's light. Fog at noon is dimmer
        than clear weather at dusk, and both are one number by the time
        anything reads it.
    travel_multiplier : float
        Route ticks scale by this. A storm turns a three-tick road into a
        five-tick slog.
    blocks_travel : bool
        Whether the roads close entirely and the player must shelter.
    modify : tuple of StatModifier
        Blanket adjustments to anyone exposed to it.
    tags : tuple of str
        `wet`, `cold`, `dark`, `windy`, `severe`. What `weatherTag`
        conditions, `env` responses, and encounter tables match on.
    freezes_to : str or None
        The condition this becomes below freezing. The same "wet" draw is
        rain above zero and light snow below, which is how a climate gets
        winter without a second transition matrix.
    """

    id: Id
    extends: WeatherRef | None = None
    name: str | None = None
    description: Description | None = None

    intensity_range: IntensityRange = Field(default_factory=IntensityRange)
    visibility: float = Field(default=1.0, ge=0.0, le=1.0)
    travel_multiplier: float = Field(default=1.0, gt=0.0)
    blocks_travel: bool = False

    modify: tuple[StatModifier, ...] = ()
    tags: tuple[Tag, ...] = ()
    freezes_to: WeatherRef | None = None

    @property
    def label(self) -> str:
        """What to call this condition in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id

    def stat_names(self) -> tuple[Name, ...]:
        """Which stats this condition touches.

        Returns
        -------
        tuple of str
            Stat names, in the order the author wrote them.
        """
        return tuple(modifier.stat for modifier in self.modify)
