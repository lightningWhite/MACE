"""Locations — the places a player can be.

A location is a place, not a node in a graph: the graph lives in `exits` and in
the routes those exits name. Waypoints on a route are ordinary locations too,
which is why the same model covers a village and the middle of a bridge.
"""

from __future__ import annotations

from mace.model.base import ContentModel, Flag, Id, Ref
from mace.model.conditions import Conditions
from mace.model.text import Description

__all__ = [
    "ClimateOverride",
    "Exit",
    "Location",
    "MapPosition",
]


class ClimateOverride(ContentModel):
    """A hard weather override for one place.

    It is always winter on the Dark Mountain, whatever the season is doing in
    the lowlands. This bypasses the climate model rather than biasing it.

    Attributes
    ----------
    condition : str or None
        The weather condition that always holds here.
    day_part : str or None
        A day part that always holds here — for caves and deep forest.
    locked : bool
        Whether the override resists weather fronts moving through.
    """

    condition: Ref | None = None
    day_part: Id | None = None
    locked: bool = False


class MapPosition(ContentModel):
    """Where a location sits on the map view.

    Attributes
    ----------
    x, y : float
        Map coordinates. Optional overall — the layout engine can infer them.
    """

    x: float
    y: float


class Exit(ContentModel):
    """A way out of a location.

    Attributes
    ----------
    to : str
        The destination location.
    route : str or None
        The route taken. Omitted, the loader synthesizes a one-tick route.
    label : str or None
        Overrides the default "Travel to X".
    when : tuple of Condition or None
        Conditions gating the exit — a locked gate, a quest requirement.
    hidden_until : tuple of Condition or None
        Conditions revealing a secret passage.
    """

    to: Ref
    route: Ref | None = None
    label: str | None = None
    when: Conditions | None = None
    hidden_until: Conditions | None = None


class Location(ContentModel):
    """A place in the world."""

    id: Id
    extends: Ref | None = None
    name: str
    type: Id | None = None
    description: Description | None = None

    region: Ref | None = None
    biome: Ref | None = None
    climate: ClimateOverride | None = None
    indoors: bool = False

    visible: bool = True
    discovered: bool | None = None

    entities: tuple[Ref, ...] = ()
    scenes: tuple[Ref, ...] = ()
    on_arrive: Ref | None = None

    encounters: Ref | None = None
    safe: bool = False

    exits: tuple[Exit, ...] = ()
    map_position: MapPosition | None = None
    flags: tuple[Flag, ...] = ()

    @property
    def starts_discovered(self) -> bool:
        """Whether the player begins the game knowing this place exists.

        Returns
        -------
        bool
            `discovered` when the author set it, otherwise `visible`.
        """
        return self.visible if self.discovered is None else self.discovered
