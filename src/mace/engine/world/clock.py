"""World time: ticks, days, and which part of the day it is.

A tick is the atomic unit of world time, and how much of a day one is worth is
the game's decision (`world.minutesPerTick`, default 30). Everything else here
follows from that.

This is the phase-1 clock: a day is twenty-four hours and the day parts are
fixed. Authored calendars — named months, seasons of different lengths, worlds
whose day is not twenty-four hours — arrive with the rest of the world
simulation in phase 2, and will supply these boundaries from content rather
than from here. See docs/05-world-simulation.md.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT_DAY_PARTS", "MINUTES_PER_DAY", "Clock"]

MINUTES_PER_DAY = 24 * 60

#: The minute of the day each part begins, and its name. Ordered, and the last
#: entry wraps around to the start of the next day.
DEFAULT_DAY_PARTS: tuple[tuple[int, str], ...] = (
    (5 * 60, "dawn"),
    (8 * 60, "day"),
    (17 * 60, "dusk"),
    (20 * 60, "night"),
)


@dataclass(frozen=True, slots=True)
class Clock:
    """Converts ticks into the time words content and players use.

    Attributes
    ----------
    minutes_per_tick : int
        How much world time one tick represents.
    """

    minutes_per_tick: int = 30

    @property
    def ticks_per_day(self) -> int:
        """How many ticks make a day.

        Returns
        -------
        int
            At least one, however coarse the tick.
        """
        return max(1, MINUTES_PER_DAY // self.minutes_per_tick)

    def day(self, tick: int) -> int:
        """Which day a tick falls on, counting from one.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        int
            The day number. Day 1 is the day the game starts.
        """
        return tick // self.ticks_per_day + 1

    def minute_of_day(self, tick: int) -> int:
        """How far into its day a tick is, in minutes.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        int
            Minutes since midnight.
        """
        return (tick % self.ticks_per_day) * self.minutes_per_tick % MINUTES_PER_DAY

    def day_part(self, tick: int) -> str:
        """Name the part of the day a tick falls in.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        str
            `dawn`, `day`, `dusk`, or `night`.
        """
        minute = self.minute_of_day(tick)
        part = DEFAULT_DAY_PARTS[-1][1]
        for start, name in DEFAULT_DAY_PARTS:
            if minute >= start:
                part = name
        return part

    def clock_time(self, tick: int) -> str:
        """Render a tick as a wall-clock time, for status lines and journals.

        Parameters
        ----------
        tick : int
            The tick to render.

        Returns
        -------
        str
            `HH:MM`, twenty-four hour.
        """
        minute = self.minute_of_day(tick)
        return f"{minute // 60:02d}:{minute % 60:02d}"
