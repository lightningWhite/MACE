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

__all__ = ["WeatherCondition"]


class WeatherCondition(ContentModel):
    """One state of the sky, and its consequences.

    Attributes
    ----------
    id, name : str
        Identity. `name` is what the player reads; it defaults to the id.
    description : Description or None
        Lines narrated when this condition begins. Conditional, so the same
        rain can read differently at night.
    intensity_range : tuple of float
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

    intensity_range: tuple[float, float] = (0.0, 1.0)
    visibility: float = Field(default=1.0, ge=0.0, le=1.0)
    travel_multiplier: float = Field(default=1.0, gt=0.0)
    blocks_travel: bool = False

    modify: tuple[StatModifier, ...] = ()
    tags: tuple[Tag, ...] = ()
    freezes_to: WeatherRef | None = None

    @model_validator(mode="after")
    def _check_range(self) -> WeatherCondition:
        """Reject an intensity band that is empty or outside 0 to 1."""
        low, high = self.intensity_range
        if not 0.0 <= low <= high <= 1.0:
            raise ValueError(
                f"intensityRange must be a rising pair within 0 and 1, "
                f"got [{low}, {high}]"
            )
        return self

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
