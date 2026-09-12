"""Weather fronts — storms with somewhere to be.

A per-region Markov chain gives weather that is coherent in time but
independent in space: it can rain in the valley and be clear on the ridge
next door, forever, with no reason. A front is the thing that ties them
together. It occupies a region, biases that region's chain toward its own kind
of weather, and every few ticks hops to the next region along its heading.

That buys four things a chain alone cannot:

1. **Correlation across space** — neighbours have related weather.
2. **Predictability** — the region ahead of a front gets a share of the bias
   and an omen, so a player can read the sky and choose to wait a day. That is
   skill, which is the point.
3. **Direction** — "the storm came down out of the north" is a true sentence.
4. **Cheap** — a handful of objects, one hop every few ticks.

This model is the *kind* of front; where one actually is lives in session
state. See docs/05-world-simulation.md § Layer 3.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from mace.model.base import ContentModel, FrontRef, Id
from mace.model.conditions import Conditions
from mace.model.text import Description
from mace.model.weather import IntensityRange, WeatherWeight

__all__ = ["HopRange", "WeatherFront"]


class HopRange(ContentModel):
    """The smallest and largest number of regions a front's heading may cross.

    Attributes
    ----------
    min, max : int
        At least one region either way.
    """

    min: int = Field(default=2, ge=1)
    max: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def _check_order(self) -> HopRange:
        """Reject a band whose floor is above its ceiling."""
        if self.min > self.max:
            raise ValueError(f"min {self.min} is higher than max {self.max}")
        return self


class WeatherFront(ContentModel):
    """A kind of weather system that crosses the map.

    Attributes
    ----------
    id, name : str
        Identity. `name` is a phrase, not a noun — "a storm out of the west" —
        because it is read inside a sentence.
    extends : str or None
        A front to inherit from.
    weight : float
        How likely this kind is, relative to the other kinds a climate offers,
        once the climate has decided a front spawns at all.
    when : tuple of Condition or None
        Extra gating — a front that only forms in winter, or once the player
        has crossed the range.
    seasons : tuple of str
        Seasons this front can form in. Empty means any.
    intensity_range : IntensityRange
        The band a new front's intensity is drawn within. Intensity scales the
        bias and decays as the front ages.
    speed_ticks : int
        Ticks spent in each region before hopping to the next.
    lifespan_ticks : int
        How long the front lives, whatever its heading has left.
    hops : HopRange
        The smallest and largest number of regions a heading may cross.
    biases : tuple of WeatherWeight
        Multipliers on the transition weights of the region the front is over.
        Above 1 makes a condition likelier, below 1 rarer, and the whole effect
        scales with the front's current intensity.
    ahead_bias : float
        The share of the bias the region *ahead* of the front receives. This
        is the foreshadowing dial: 0 means a front arrives without warning.
    omen : Description or None
        What the player sees when the front is in the next region along and
        coming this way. Ordinary narration, never a system message.
    """

    id: Id
    extends: FrontRef | None = None
    name: str | None = None

    weight: float = Field(default=1.0, gt=0.0)
    when: Conditions | None = None
    seasons: tuple[Id, ...] = ()

    intensity_range: IntensityRange = Field(
        default_factory=lambda: IntensityRange(min=0.4, max=1.0)
    )
    speed_ticks: int = Field(default=6, gt=0)
    lifespan_ticks: int = Field(default=54, gt=0)
    hops: HopRange = Field(default_factory=HopRange)

    biases: tuple[WeatherWeight, ...] = ()
    ahead_bias: float = Field(default=0.3, ge=0.0, le=1.0)
    omen: Description | None = None

    @property
    def label(self) -> str:
        """What to call this front in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id
