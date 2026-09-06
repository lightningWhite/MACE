"""World time: ticks, days, seasons, and which part of the day it is.

A tick is the atomic unit of world time. How many make a day is the
**calendar's** decision (`calendar.ticksPerDay`); what one is worth in
real-world minutes is the **game's** (`world.minutesPerTick`). Setting them to
48 and 30 gives the twenty-four hours everyone expects, and a game that wants
a thirty-hour day on a slow planet just says so.

Everything else here follows from those two numbers and the calendar's day
parts and seasons. This module is pure: it reads no files and no wall clock,
and the same tick always resolves to the same day, season, and light level.
See docs/05-world-simulation.md § Layer 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mace.model.calendar import STANDARD_YEAR, Calendar, DayPart, Season

__all__ = ["MINUTES_PER_HOUR", "Clock"]

MINUTES_PER_HOUR = 60


@dataclass(frozen=True, slots=True)
class Clock:
    """Converts ticks into the time words content and players use.

    Attributes
    ----------
    minutes_per_tick : int
        How much world time one tick represents.
    calendar : Calendar
        The world's division of time. Defaults to `standard-year`.
    season_offset : int
        How many days to add before reading the season, so a game that opens
        in autumn puts day 1 at the start of autumn rather than of spring.
    """

    minutes_per_tick: int = 30
    calendar: Calendar = field(default=STANDARD_YEAR)
    season_offset: int = 0

    @classmethod
    def for_season(
        cls, minutes_per_tick: int, calendar: Calendar, start_season: str | None
    ) -> Clock:
        """Build a clock whose day 1 falls in a chosen season.

        Parameters
        ----------
        minutes_per_tick : int
            How much world time one tick represents.
        calendar : Calendar
            The world's calendar.
        start_season : str or None
            The season day 1 should fall on. Unknown or absent starts the year
            where the calendar does — content validation reports the typo, and
            a clock is not the place to fail a playthrough over one.

        Returns
        -------
        Clock
            The clock.
        """
        offset = 0
        if start_season is not None:
            elapsed = 0
            for season in calendar.seasons:
                if season.id == start_season:
                    offset = elapsed
                    break
                elapsed += season.days
        return cls(minutes_per_tick, calendar, offset)

    @property
    def ticks_per_day(self) -> int:
        """How many ticks make a day.

        Returns
        -------
        int
            The calendar's day length.
        """
        return self.calendar.ticks_per_day

    @property
    def minutes_per_day(self) -> int:
        """How long a day is in world minutes.

        Returns
        -------
        int
            Ticks per day times minutes per tick.
        """
        return self.ticks_per_day * self.minutes_per_tick

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

    def tick_of_day(self, tick: int) -> int:
        """How far into its day a tick is.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        int
            Zero-based tick within the day.
        """
        return tick % self.ticks_per_day

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
        return self.tick_of_day(tick) * self.minutes_per_tick

    def day_of_year(self, tick: int) -> int:
        """Which day of the year a tick falls on.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        int
            Zero-based, wrapped at the year's length, and shifted by the
            game's starting season.
        """
        elapsed = self.day(tick) - 1 + self.season_offset
        return elapsed % self.calendar.days_per_year

    def season(self, tick: int) -> Season:
        """Which season a tick falls in.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        Season
            The season in force.
        """
        return self.calendar.season_at(self.day_of_year(tick))

    def part(self, tick: int) -> DayPart:
        """Which part of the day a tick falls in.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        DayPart
            The part in force, with the season's `dayPartShift` applied.
        """
        return self.calendar.part_at(self.tick_of_day(tick), self.season(tick))

    def day_part(self, tick: int) -> str:
        """Name the part of the day a tick falls in.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        str
            The day part's id — what `{dayPart: [...]}` matches against.
        """
        return self.part(tick).id

    def light(self, tick: int) -> float:
        """How much light the sky gives at a tick, before weather.

        Weather multiplies this by its visibility to give the one number that
        feeds stealth, ranged accuracy, encounter detection, and which
        description variant is shown.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        float
            0 to 1.
        """
        return self.part(tick).light

    def day_name(self, tick: int) -> str | None:
        """The weekday name for a tick, if the calendar names its days.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        str or None
            The name, or None when the calendar declares no day names.
        """
        names = self.calendar.day_names
        if not names:
            return None
        return names[(self.day(tick) - 1) % len(names)]

    def month_name(self, tick: int) -> str | None:
        """The month name for a tick, if the calendar names its months.

        Months are naming only: the year is divided evenly between the names
        and nothing in the simulation reads the result.

        Parameters
        ----------
        tick : int
            The tick to place.

        Returns
        -------
        str or None
            The name, or None when the calendar declares no month names.
        """
        names = self.calendar.month_names
        if not names:
            return None
        length = self.calendar.days_per_year / len(names)
        index = int(self.day_of_year(tick) / length)
        return names[min(index, len(names) - 1)]

    def clock_time(self, tick: int) -> str:
        """Render a tick as a wall-clock time, for status lines and journals.

        Parameters
        ----------
        tick : int
            The tick to render.

        Returns
        -------
        str
            `HH:MM`, counted from the start of the day however long a day is.
        """
        minute = self.minute_of_day(tick)
        return f"{minute // MINUTES_PER_HOUR:02d}:{minute % MINUTES_PER_HOUR:02d}"
