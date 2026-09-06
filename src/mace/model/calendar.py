"""Calendars — how a world divides its time.

Day parts and seasons are declared rather than hard-coded, because a world on
a tidally-locked planet, in a lightless undercity, or on a thirteen-month
calendar is a world MACE should be able to describe. A game that says nothing
gets `mace.core:standard-year`, which is twenty-four hours and four seasons.

The calendar owns `ticksPerDay`; `game.world.minutesPerTick` says what a tick
is worth in real-world minutes, and the two together decide how long a day is.
Setting them to 48 and 30 gives the twenty-four hours everyone expects. See
docs/05-world-simulation.md § Layer 1.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from mace.model.base import CalendarRef, ContentModel, Id

__all__ = [
    "Calendar",
    "DayPart",
    "Season",
]


class DayPart(ContentModel):
    """One named stretch of the day.

    A part runs from its `startTick` until the next part begins, and the last
    wraps around midnight — which is why `night` starting at tick 40 of 48
    also covers ticks 0 to 9.

    Attributes
    ----------
    id : str
        How content names it: `dayPart: [dusk, night]`.
    name : str or None
        What the player reads. Defaults to the id.
    start_tick : int
        The tick of the day this part begins on.
    light : float
        How much light it brings, 0 to 1. Multiplied by the weather's
        visibility to give the single number stealth, ranged accuracy,
        encounter detection, and description selection all read.
    """

    id: Id
    name: str | None = None
    start_tick: int = Field(ge=0)
    light: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def label(self) -> str:
        """What to call this part in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id


class Season(ContentModel):
    """One season of the year.

    Attributes
    ----------
    id : str
        How content names it, and how a climate keys its weather profile.
    name : str or None
        What the player reads. Defaults to the id.
    days : int
        How long it lasts. The seasons together define the year's length.
    day_part_shift : mapping
        Ticks to move each day part by, this season. Negative is earlier.
        `{dawn: -3, night: +3}` is a long summer evening, without needing a
        model of where the sun is.
    """

    id: Id
    name: str | None = None
    days: int = Field(gt=0)
    day_part_shift: dict[Id, int] = Field(default_factory=dict)

    @property
    def label(self) -> str:
        """What to call this season in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id


class Calendar(ContentModel):
    """A world's division of time into days, parts of days, and seasons.

    Attributes
    ----------
    id, name : str
        Identity.
    ticks_per_day : int
        How many ticks a day holds.
    day_parts : tuple of DayPart
        The parts of the day, in ascending `startTick` order.
    seasons : tuple of Season
        The seasons, in the order the year runs through them.
    day_names : tuple of str
        A repeating cycle of weekday names, for the journal and status line.
    month_names : tuple of str
        Month names. The year is split evenly between them; months are naming
        only, and nothing in the simulation reads them.
    """

    id: Id
    extends: CalendarRef | None = None
    name: str | None = None
    ticks_per_day: int = Field(default=48, gt=0)
    day_parts: tuple[DayPart, ...] = Field(min_length=1)
    seasons: tuple[Season, ...] = Field(min_length=1)
    day_names: tuple[str, ...] = ()
    month_names: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_coherent(self) -> Calendar:
        """Reject calendars whose own parts contradict each other."""
        seen: set[str] = set()
        previous = -1
        for part in self.day_parts:
            if part.id in seen:
                raise ValueError(f"day part `{part.id}` is declared twice")
            seen.add(part.id)
            if part.start_tick >= self.ticks_per_day:
                raise ValueError(
                    f"day part `{part.id}` starts at tick {part.start_tick}, "
                    f"but a day is only {self.ticks_per_day} ticks long"
                )
            if part.start_tick <= previous:
                raise ValueError(
                    f"day part `{part.id}` starts at tick {part.start_tick}, "
                    "which is not after the part before it. Day parts are "
                    "written in the order the day runs through them."
                )
            previous = part.start_tick

        season_ids: set[str] = set()
        for season in self.seasons:
            if season.id in season_ids:
                raise ValueError(f"season `{season.id}` is declared twice")
            season_ids.add(season.id)
            for shifted in season.day_part_shift:
                if shifted not in seen:
                    raise ValueError(
                        f"season `{season.id}` shifts day part `{shifted}`, "
                        f"which this calendar does not declare"
                    )
        return self

    @property
    def days_per_year(self) -> int:
        """How many days the seasons add up to.

        Returns
        -------
        int
            The length of a year.
        """
        return sum(season.days for season in self.seasons)

    def season_at(self, day_of_year: int) -> Season:
        """Which season a day of the year falls in.

        Parameters
        ----------
        day_of_year : int
            Zero-based, and already reduced modulo the year's length.

        Returns
        -------
        Season
            The season that day belongs to.
        """
        remaining = day_of_year
        for season in self.seasons:
            if remaining < season.days:
                return season
            remaining -= season.days
        return self.seasons[-1]  # pragma: no cover — the loop covers the year

    def part_at(self, tick_of_day: int, season: Season) -> DayPart:
        """Which part of the day a tick falls in, given the season's shift.

        The season's `dayPartShift` moves each part's boundary, which is how
        summer gets long evenings. A shifted boundary that lands outside the
        day wraps, and the part whose shifted start is latest but not after
        `tick_of_day` wins — so shifts that reorder the parts still resolve to
        something rather than raising.

        Parameters
        ----------
        tick_of_day : int
            Zero-based tick within the day.
        season : Season
            The season now, whose shifts apply.

        Returns
        -------
        DayPart
            The part in force.
        """
        starts = [
            (
                (part.start_tick + season.day_part_shift.get(part.id, 0))
                % self.ticks_per_day,
                index,
                part,
            )
            for index, part in enumerate(self.day_parts)
        ]
        starts.sort(key=lambda entry: (entry[0], entry[1]))
        current = starts[-1][2]
        for start, _index, part in starts:
            if start <= tick_of_day:
                current = part
            else:
                break
        return current


def _standard_year() -> Calendar:
    """The calendar a game gets when it names none.

    Twenty-four hours at thirty minutes a tick, four equal seasons, and the
    long summer evenings that `dayPartShift` exists for. `mace.core` ships the
    same calendar as `standard-year`, so a game may also name it explicitly;
    a test keeps the two identical.

    Returns
    -------
    Calendar
        The default calendar.
    """
    return Calendar.model_validate(
        {
            "id": "standard-year",
            "name": "The Standard Year",
            "ticksPerDay": 48,
            "dayParts": [
                {"id": "dawn", "name": "dawn", "startTick": 10, "light": 0.5},
                {"id": "day", "name": "daylight", "startTick": 14, "light": 1.0},
                {"id": "dusk", "name": "dusk", "startTick": 36, "light": 0.5},
                {"id": "night", "name": "night", "startTick": 40, "light": 0.15},
            ],
            "seasons": [
                {"id": "spring", "name": "Spring", "days": 30},
                {
                    "id": "summer",
                    "name": "Summer",
                    "days": 30,
                    "dayPartShift": {"dawn": -3, "night": 3},
                },
                {"id": "autumn", "name": "Autumn", "days": 30},
                {
                    "id": "winter",
                    "name": "Winter",
                    "days": 30,
                    "dayPartShift": {"dawn": 3, "night": -3},
                },
            ],
        }
    )


#: The calendar a game with no `world.calendar` runs on.
STANDARD_YEAR: Calendar = _standard_year()
