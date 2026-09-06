"""Terrain — what a road is made of, and how badly the weather ruins it.

The point of terrain is that weather does not slow every road equally. Rain on
a paved highway is an inconvenience; rain on a forest track is mud to the
ankles. A weather condition's own `travelMultiplier` says how bad the *weather*
is; a terrain's `inWeather` says how badly *this surface* takes it, and the two
multiply.

That split is what lets an author make a detour worth considering. The long way
round on a good road can genuinely beat the short way through the wood, but
only when it is wet — which is a decision rather than a fixed answer.

See docs/06-travel-and-encounters.md.
"""

from __future__ import annotations

from pydantic import Field

from mace.model.base import ContentModel, Id, Tag, TerrainRef

__all__ = ["Terrain"]


class Terrain(ContentModel):
    """A road surface, and what conditions do to it.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        A terrain to inherit from.
    travel_multiplier : float
        How slow this surface is in fair weather. A mountain path is slow
        before anything falls on it.
    in_weather : mapping
        Weather tag to an extra multiplier, applied on top of the weather's
        own. Only the largest applies, not the product: a wet, cold, windy
        night on a forest track should be bad, not impossible.
    tags : tuple of str
        Free-form labels for encounter tables and content to match on.
    """

    id: Id
    extends: TerrainRef | None = None
    name: str | None = None

    travel_multiplier: float = Field(default=1.0, gt=0.0)
    in_weather: dict[Tag, float] = Field(default_factory=dict)
    tags: tuple[Tag, ...] = ()

    def cost(self, weather_tags: tuple[str, ...]) -> float:
        """How much this surface multiplies a journey by, in this weather.

        Parameters
        ----------
        weather_tags : tuple of str
            The tags in force.

        Returns
        -------
        float
            The multiplier, the surface's own included.
        """
        worst = max(
            (self.in_weather[tag] for tag in weather_tags if tag in self.in_weather),
            default=1.0,
        )
        return self.travel_multiplier * worst

    @property
    def label(self) -> str:
        """What to call this terrain in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id
