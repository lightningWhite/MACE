"""Clock, calendar, day parts, seasons, climate, weather fronts, world events.

See docs/05-world-simulation.md.
"""

from mace.engine.world.clock import MINUTES_PER_HOUR, Clock
from mace.engine.world.weather import (
    DEFAULT_LAPSE_RATE,
    Observation,
    climate_of,
    observe,
    region_of,
    sync,
)

__all__ = [
    "Clock",
    "DEFAULT_LAPSE_RATE",
    "MINUTES_PER_HOUR",
    "Observation",
    "climate_of",
    "observe",
    "region_of",
    "sync",
]
