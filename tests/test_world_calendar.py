"""Calendars and the clock built on them.

Time is the layer every other part of the world simulation stands on, so the
things worth pinning down are the ones everything else will assume: that a
tick resolves to exactly one day part, that seasons wrap, and that the
`dayPartShift` which gives summer its long evenings does not accidentally
lose a part of the day.
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from conftest import game_pack, write_pack
from mace.content import load_library, validate_library
from mace.engine.world import Clock
from mace.model import Calendar
from mace.model.calendar import STANDARD_YEAR

REPO_ROOT = Path(__file__).resolve().parent.parent


def calendar(**overrides: object) -> Calendar:
    """A small calendar to vary one field of at a time.

    Parameters
    ----------
    **overrides
        Fields to replace.

    Returns
    -------
    Calendar
        The validated calendar.
    """
    data: dict[str, object] = {
        "id": "tiny-year",
        "ticksPerDay": 8,
        "dayParts": [
            {"id": "day", "startTick": 2, "light": 1.0},
            {"id": "night", "startTick": 6, "light": 0.1},
        ],
        "seasons": [
            {"id": "warm", "days": 3},
            {"id": "cold", "days": 2},
        ],
    }
    data.update(overrides)
    return Calendar.model_validate(data)


# ── The shipped default ──────────────────────────────────────────────────────


def test_the_engine_default_is_the_calendar_macecore_ships() -> None:
    """A game that names no calendar and one that names `standard-year` agree.

    They are written in two places — Python, so the engine has a fallback that
    needs no pack, and YAML, so an author can extend it — and the moment they
    disagree the fallback becomes a silent bug.
    """
    library = load_library(REPO_ROOT / "packs" / "mace.core")
    shipped = library.pack("mace.core").calendars["standard-year"]
    assert shipped == STANDARD_YEAR


def test_the_standard_year_is_twenty_four_hours() -> None:
    clock = Clock(30, STANDARD_YEAR)
    assert clock.ticks_per_day == 48
    assert clock.minutes_per_day == 24 * 60
    assert clock.clock_time(0) == "00:00"
    assert clock.clock_time(20) == "10:00"
    assert clock.day(48) == 2


# ── Day parts ────────────────────────────────────────────────────────────────


def test_every_tick_of_the_day_lands_in_exactly_one_part() -> None:
    """The last part wraps midnight, so no tick may be left unaccounted for."""
    for season in STANDARD_YEAR.seasons:
        parts = {
            STANDARD_YEAR.part_at(tick, season).id
            for tick in range(STANDARD_YEAR.ticks_per_day)
        }
        assert parts == {"dawn", "day", "dusk", "night"}


def test_ticks_before_the_first_part_belong_to_the_last() -> None:
    """Midnight is night, even though `night` starts at tick 40 of 48."""
    clock = Clock(30, STANDARD_YEAR)
    assert clock.day_part(0) == "night"
    assert clock.day_part(9) == "night"
    assert clock.day_part(10) == "dawn"


def test_a_season_can_shift_when_the_day_parts_fall() -> None:
    """Summer dawns three ticks early and holds off night three ticks late."""
    calendar = STANDARD_YEAR
    summer = next(season for season in calendar.seasons if season.id == "summer")
    autumn = next(season for season in calendar.seasons if season.id == "autumn")

    assert calendar.part_at(7, summer).id == "dawn"
    assert calendar.part_at(7, autumn).id == "night"
    assert calendar.part_at(42, summer).id == "dusk"
    assert calendar.part_at(42, autumn).id == "night"


def test_light_comes_from_the_day_part() -> None:
    clock = Clock(30, STANDARD_YEAR)
    assert clock.light(20) == 1.0
    assert clock.light(0) == 0.15


# ── Seasons ──────────────────────────────────────────────────────────────────


def test_seasons_run_in_order_and_wrap_at_the_year() -> None:
    clock = Clock(30, calendar())
    days = [clock.season(day * 8).id for day in range(7)]
    assert days == ["warm", "warm", "warm", "cold", "cold", "warm", "warm"]


def test_a_game_can_open_in_a_season_other_than_the_first() -> None:
    """`startSeason` puts day 1 at the start of that season, not the year."""
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")
    assert clock.season(0).id == "autumn"
    assert clock.season(30 * 48).id == "winter"


def test_an_unknown_start_season_leaves_the_year_where_it_starts() -> None:
    """Validation reports the typo; the clock is not the place to fail on it."""
    clock = Clock.for_season(30, STANDARD_YEAR, "harvest")
    assert clock.season(0).id == "spring"


# ── Naming ───────────────────────────────────────────────────────────────────


def test_day_and_month_names_are_optional_flavor() -> None:
    plain = Clock(30, calendar())
    assert plain.day_name(0) is None
    assert plain.month_name(0) is None

    named = Clock(
        30,
        calendar(dayNames=["Sunsday", "Moonsday"], monthNames=["Frost", "Thaw"]),
    )
    assert named.day_name(0) == "Sunsday"
    assert named.day_name(8) == "Moonsday"
    assert named.day_name(16) == "Sunsday"
    assert named.month_name(0) == "Frost"
    assert named.month_name(4 * 8) == "Thaw"


# ── What a calendar may not say ──────────────────────────────────────────────


def test_day_parts_must_be_written_in_order() -> None:
    with pytest.raises(ValidationError, match="not after the part before it"):
        calendar(
            dayParts=[
                {"id": "night", "startTick": 6},
                {"id": "day", "startTick": 2},
            ]
        )


def test_a_day_part_cannot_start_after_the_day_ends() -> None:
    with pytest.raises(ValidationError, match="only 8 ticks long"):
        calendar(dayParts=[{"id": "day", "startTick": 9}])


def test_a_season_cannot_shift_a_day_part_that_does_not_exist() -> None:
    with pytest.raises(ValidationError, match="does not declare"):
        calendar(seasons=[{"id": "warm", "days": 3, "dayPartShift": {"evening": 2}}])


def test_a_calendar_needs_at_least_one_part_and_one_season() -> None:
    with pytest.raises(ValidationError):
        calendar(dayParts=[])
    with pytest.raises(ValidationError):
        calendar(seasons=[])


# ── Validation against real content ──────────────────────────────────────────


def test_content_naming_a_day_part_the_calendar_lacks_is_an_error(
    tmp_path: Path,
) -> None:
    """A condition that can never hold is worth an error, not a silent shrug."""
    write_pack(
        tmp_path,
        "clocks",
        files={"calendars.yml": {"calendars": [yaml.safe_load(_TINY_CALENDAR)]}},
    )
    game_pack(
        tmp_path,
        game={"world": {"calendar": "clocks:tiny-year"}},
        world={
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "description": [{"text": "Dark.", "when": {"dayPart": ["dusk"]}}],
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle"},
            ]
        },
    )
    (tmp_path / "tiny" / "pack.yml").write_text(
        (tmp_path / "tiny" / "pack.yml").read_text()
        + "requires:\n  - {id: clocks, version: '^0.1'}\n"
    )

    report = validate_library(load_library(tmp_path))
    messages = [problem.message for problem in report.problems]
    assert any("day part `dusk`" in message for message in messages)


def test_an_unknown_start_season_is_an_error(tmp_path: Path) -> None:
    game_pack(tmp_path, game={"world": {"startSeason": "harvest"}})
    report = validate_library(load_library(tmp_path))
    assert any("season `harvest`" in problem.message for problem in report.problems)


def test_the_shipped_packs_still_validate() -> None:
    report = validate_library(load_library(REPO_ROOT / "packs"))
    assert not report.errors


_TINY_CALENDAR = """
id: tiny-year
ticksPerDay: 8
dayParts:
  - {id: day, startTick: 2}
  - {id: night, startTick: 6}
seasons:
  - {id: warm, days: 3}
"""
