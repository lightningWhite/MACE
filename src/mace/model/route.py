"""Routes — the road between two places, and the time it costs.

The single most important upgrade over the v0 `links` list: a route has a
length in ticks, a terrain, waypoints you pass through, and its own encounter
table. Travel is resolved leg by leg, so a journey that starts at dusk finishes
in the dark, and that matters.
"""

from __future__ import annotations

from pydantic import Field

from mace.model.base import ContentModel, Id, Ref
from mace.model.conditions import Conditions
from mace.model.text import Description

__all__ = [
    "Route",
    "Waypoint",
]


class Waypoint(ContentModel):
    """A place passed through on the way to somewhere else.

    Attributes
    ----------
    location : str
        A real location definition — waypoints are locations.
    at_tick : int or None
        How far into the journey it is reached. Defaults to even spacing.
    stop_if : tuple of Condition or None
        Conditions that force a stop here, such as a bridge with a troll on it.
    encounters : str or None
        A waypoint-specific table, rolled in addition to the route's.
    """

    location: Ref
    at_tick: int | None = Field(default=None, ge=0)
    stop_if: Conditions | None = None
    encounters: Ref | None = None


class Route(ContentModel):
    """A connection between two locations, with a length."""

    id: Id
    name: str | None = None
    origin: Ref = Field(alias="from")
    destination: Ref = Field(alias="to")
    bidirectional: bool = True
    ticks: int = Field(gt=0)

    terrain: Ref | None = None
    waypoints: tuple[Waypoint, ...] = ()
    encounters: Ref | None = None

    description: Description | None = None
    leg_descriptions: Description | None = None

    when: Conditions | None = None
    danger_level: int | None = Field(default=None, ge=0, le=10)
