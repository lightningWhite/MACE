"""Regions — the unit weather happens to.

Weather runs per region rather than globally, because a world where it rains
on the whole map at once is a world with one place in it. A region owns a
climate, an elevation, and a list of neighbors; the neighbors are the graph
that weather fronts walk across, which is what makes a storm something that
comes *from* somewhere.

See docs/05-world-simulation.md § Layer 2 and § Layer 3.
"""

from __future__ import annotations

from mace.model.base import (
    ClimateRef,
    ContentModel,
    EncounterRef,
    Id,
    Ref,
    RegionRef,
)
from mace.model.text import Description

__all__ = ["Region"]


class Region(ContentModel):
    """A stretch of the map that shares its weather.

    Attributes
    ----------
    id, name : str
        Identity.
    description : Description or None
        How the region reads when it is named at distance — a front seen from
        the next valley over.
    climate : str or None
        The climate governing it. Without one the region has no weather, which
        is the right answer for an undercity or a station interior.
    neighbors : tuple of str
        Adjacent regions, for front propagation. Adjacency is not made
        symmetric automatically: a front that crosses a range one way and not
        the other is a thing an author may want.
    elevation : float
        Height above the map's baseline. Colder with altitude, which is what
        turns the same rain into snow up the mountain.
    biome : str or None
        The region's default biome, which a location may override.
    encounters : str or None
        A table rolled anywhere in the region, on top of the route's or the
        location's. Region-wide flavor: you hear wolves.
    """

    id: Id
    extends: RegionRef | None = None
    name: str | None = None
    description: Description | None = None

    climate: ClimateRef | None = None
    neighbors: tuple[RegionRef, ...] = ()
    elevation: float = 0.0
    biome: Ref | None = None
    encounters: EncounterRef | None = None

    @property
    def label(self) -> str:
        """What to call this region in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id
