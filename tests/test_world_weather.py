"""Per-region weather: the Markov chain, its seasons, and what it costs.

The properties worth pinning down are the ones the rest of phase 2 will lean
on: that two regions do not disturb each other's weather, that reading the sky
never changes it, that a season's weights can genuinely rule a condition out,
and that fast-forwarding a region the player was not in gives the same answer
as having stepped it all along.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Wait
from mace.engine.state import GameState
from mace.engine.step import begin, step
from mace.engine.world import Clock, observe, region_of, sync
from mace.model.calendar import STANDARD_YEAR

REPO_ROOT = Path(__file__).resolve().parent.parent


CONDITIONS: list[dict[str, Any]] = [
    {"id": "clear", "name": "clear"},
    {
        "id": "rain",
        "name": "rain",
        "visibility": 0.6,
        "travelMultiplier": 1.5,
        "tags": ["wet"],
        "freezesTo": "snow",
        "description": ["It starts raining."],
    },
    {
        "id": "snow",
        "name": "snow",
        "visibility": 0.5,
        "tags": ["cold", "wet"],
        "blocksTravel": True,
    },
]


def weather_pack(
    root: Path,
    *,
    climate: dict[str, Any] | None = None,
    regions: list[dict[str, Any]] | None = None,
    game: dict[str, Any] | None = None,
    locations: list[dict[str, Any]] | None = None,
) -> Any:
    """A playable pack with weather in it.

    Parameters
    ----------
    root : Path
        Where to write it.
    climate : dict or None
        Fields to replace on the climate.
    regions : list or None
        Region definitions, replacing the default two.
    game : dict or None
        Fields to merge into the `game:` manifest.
    locations : list or None
        Location definitions, replacing the defaults.

    Returns
    -------
    Library
        The loaded library.
    """
    base: dict[str, Any] = {
        "id": "temperate",
        "stepTicks": 1,
        "seasons": [
            {
                "id": "autumn",
                "temperature": {"min": 4, "max": 12},
                "weights": [
                    {"condition": "clear", "weight": 50},
                    {"condition": "rain", "weight": 50},
                ],
            },
            {
                "id": "winter",
                "temperature": {"min": -10, "max": -2},
                "weights": [
                    {"condition": "clear", "weight": 50},
                    {"condition": "rain", "weight": 50},
                ],
            },
        ],
        "transitions": [
            {"source": "clear", "target": "clear", "weight": 60},
            {"source": "clear", "target": "rain", "weight": 40},
            {"source": "rain", "target": "rain", "weight": 60},
            {"source": "rain", "target": "clear", "weight": 40},
            {"source": "snow", "target": "rain", "weight": 60},
            {"source": "snow", "target": "clear", "weight": 40},
        ],
    }
    base.update(climate or {})

    game_pack(
        root,
        game={
            "world": {
                "startSeason": "autumn",
                "startRegion": "valley",
                "startTick": 20,
            },
            **(game or {}),
        },
        world={
            "weatherConditions": CONDITIONS,
            "climates": [base],
            "regions": regions
            or [
                {"id": "valley", "climate": "temperate", "neighbors": ["ridge"]},
                {"id": "ridge", "climate": "temperate", "elevation": 800},
            ],
            "locations": locations
            or [
                {
                    "id": "home",
                    "name": "Home",
                    "region": "valley",
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle", "region": "ridge"},
            ],
        },
    )
    return load_library(root)


def statuses(events: Any) -> list[dict[str, Any]]:
    """The status projections in an event stream.

    Parameters
    ----------
    events : iterable of Event
        The stream.

    Returns
    -------
    list of dict
        Their payloads.
    """
    return [e.payload() for e in events if e.kind == "world.status"]


# ── The chain runs, and is visible ───────────────────────────────────────────


def test_a_game_with_a_climate_has_weather_from_the_first_event(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    status = statuses(result.events)[-1]
    assert status["weather"] in {"tiny:clear", "tiny:rain"}
    assert status["region"] == "tiny:valley"
    assert status["temperature"] is not None


def test_temperature_defaults_to_celsius(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    status = statuses(result.events)[-1]
    assert status["temperatureUnit"] == "celsius"


def test_a_climate_can_declare_its_own_scale(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, climate={"temperatureUnit": "fahrenheit"})
    result = begin(library, "tiny")
    status = statuses(result.events)[-1]
    assert status["temperatureUnit"] == "fahrenheit"
    # The number itself is untouched — the climate simply says what scale the
    # author already wrote its bands in. A fahrenheit-declared 4-12 band reads
    # as 4-12, not as a conversion of some assumed celsius original.
    assert status["temperature"] is not None


def test_a_game_with_no_regions_still_plays(tmp_path: Path) -> None:
    """Weather is optional. A pack that says nothing about it gets none."""
    game_pack(tmp_path)
    library = load_library(tmp_path)
    result = begin(library, "tiny")
    status = statuses(result.events)[-1]
    assert status["weather"] is None
    assert status["sky"] == ""
    assert result.state.weather == {}


def test_the_sky_changing_is_narrated_and_holding_is_not(tmp_path: Path) -> None:
    """Weather that is doing what it was doing is not news."""
    library = weather_pack(tmp_path)
    result = begin(library, "tiny", seed="rainy")

    changes = 0
    for _turn in range(40):
        result = step(result.state, Wait(1), library)
        changes += sum(1 for e in result.events if e.kind == "weather.changed")
    assert 0 < changes < 40


# ── Determinism and independence ─────────────────────────────────────────────


def test_regions_do_not_disturb_each_others_weather(tmp_path: Path) -> None:
    """One region's chain draws from its own stream, so adding one is safe."""
    library = weather_pack(tmp_path)
    state = begin(library, "tiny", seed="s").state
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")

    alone = []
    for tick in range(20, 60):
        state.tick = tick
        sync(library, state, clock, "tiny", "tiny:valley")
        alone.append(state.weather["tiny:valley"].condition)

    together_state = begin(library, "tiny", seed="s").state
    together = []
    for tick in range(20, 60):
        together_state.tick = tick
        sync(library, together_state, clock, "tiny", "tiny:ridge")
        sync(library, together_state, clock, "tiny", "tiny:valley")
        together.append(together_state.weather["tiny:valley"].condition)

    assert alone == together


def test_fast_forwarding_a_region_matches_having_stepped_it(tmp_path: Path) -> None:
    """Lazy evaluation is an optimization, not a different world."""
    library = weather_pack(tmp_path)
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")

    stepped = begin(library, "tiny", seed="s").state
    for tick in range(20, 80):
        stepped.tick = tick
        sync(library, stepped, clock, "tiny", "tiny:ridge")

    lazy = begin(library, "tiny", seed="s").state
    lazy.tick = 79
    sync(library, lazy, clock, "tiny", "tiny:ridge")

    assert lazy.weather["tiny:ridge"].condition == (
        stepped.weather["tiny:ridge"].condition
    )
    assert lazy.weather["tiny:ridge"].stepped_to == (
        stepped.weather["tiny:ridge"].stepped_to
    )


def test_reading_the_weather_never_changes_it(tmp_path: Path) -> None:
    """A question about the world must not be an action on it."""
    library = weather_pack(tmp_path)
    state = begin(library, "tiny", seed="s").state
    location = library.pack("tiny").locations["home"]

    before = state.rng.positions()
    first = observe(library, state, Clock(30), "tiny", location, "valley")
    second = observe(library, state, Clock(30), "tiny", location, "valley")
    assert state.rng.positions() == before
    assert first == second


# ── Seasons, temperature, and freezing ───────────────────────────────────────


def test_a_season_that_weights_a_condition_at_zero_rules_it_out(
    tmp_path: Path,
) -> None:
    library = weather_pack(
        tmp_path,
        climate={
            "seasons": [
                {
                    "id": "autumn",
                    "temperature": {"min": 4, "max": 12},
                    "weights": [
                        {"condition": "clear", "weight": 100},
                        {"condition": "rain", "weight": 0},
                    ],
                }
            ]
        },
    )
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")
    state = begin(library, "tiny", seed="dry").state
    for tick in range(20, 400):
        state.tick = tick
        sync(library, state, clock, "tiny", "tiny:valley")
        assert state.weather["tiny:valley"].condition == "tiny:clear"


def test_below_freezing_the_same_draw_falls_as_snow(tmp_path: Path) -> None:
    """One transition matrix covers the whole year; temperature does the rest."""
    library = weather_pack(
        tmp_path, game={"world": {"startSeason": "winter", "startRegion": "valley"}}
    )
    clock = Clock.for_season(30, STANDARD_YEAR, "winter")
    state = begin(library, "tiny", seed="cold").state

    seen = set()
    for tick in range(20, 300):
        state.tick = tick
        sync(library, state, clock, "tiny", "tiny:valley")
        seen.add(state.weather["tiny:valley"].condition)

    assert "tiny:snow" in seen
    assert "tiny:rain" not in seen


def test_elevation_makes_the_high_country_colder(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")
    state = begin(library, "tiny", seed="s").state
    state.tick = 40
    sync(library, state, clock, "tiny", "tiny:valley")
    sync(library, state, clock, "tiny", "tiny:ridge")

    # 800 units up, at 0.65 degrees per hundred, is 5.2 degrees of lapse.
    assert state.weather["tiny:ridge"].high < state.weather["tiny:valley"].high


# ── What a location can say about its own sky ────────────────────────────────


def test_a_location_override_beats_the_region(tmp_path: Path) -> None:
    """It is always winter on the Dark Mountain, whatever the lowlands do."""
    library = weather_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "climate": {"condition": "snow"},
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle", "region": "ridge"},
        ],
    )
    result = begin(library, "tiny")
    assert statuses(result.events)[-1]["weather"] == "tiny:snow"


def test_indoors_suppresses_the_weathers_bite_but_not_the_weather(
    tmp_path: Path,
) -> None:
    library = weather_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "indoors": True,
                "climate": {"condition": "rain"},
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle", "region": "ridge"},
        ],
    )
    state = begin(library, "tiny").state
    location = library.pack("tiny").locations["home"]
    inside = observe(library, state, Clock(30), "tiny", location, "valley")

    assert inside.label == "rain"
    assert inside.sheltered
    assert inside.tags == ()
    assert inside.visibility == 1.0
    # Travel is the exception: you cannot be indoors and on the road.
    assert inside.travel_multiplier == 1.5


def test_a_location_with_no_region_falls_back_to_the_games(tmp_path: Path) -> None:
    library = weather_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle"},
        ],
    )
    location = library.pack("tiny").locations["home"]
    assert region_of(library, "tiny", location, "valley") == "tiny:valley"


# ── Conditions and expressions ───────────────────────────────────────────────


def test_weather_and_weather_tag_conditions_read_the_sky(tmp_path: Path) -> None:
    library = weather_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "climate": {"condition": "rain"},
                "description": [
                    {"text": "Wet.", "when": {"weatherTag": ["wet"]}},
                    {"text": "Dry."},
                ],
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle", "region": "ridge"},
        ],
    )
    result = begin(library, "tiny")
    spoken = [e.payload()["text"] for e in result.events if e.kind == "narrate"]
    assert "Wet." in spoken


def test_expressions_can_read_the_weather(tmp_path: Path) -> None:
    library = weather_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "climate": {"condition": "rain"},
                "description": [
                    {"text": "Dim.", "when": {"expr": "world.light < 0.7"}},
                    {"text": "Bright."},
                ],
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle", "region": "ridge"},
        ],
    )
    result = begin(library, "tiny")
    spoken = [e.payload()["text"] for e in result.events if e.kind == "narrate"]
    assert "Dim." in spoken


# ── The shipped packs ────────────────────────────────────────────────────────


def test_the_shipped_game_has_weather_over_it() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="stormy")
    status = statuses(result.events)[-1]
    assert status["region"] == "peasants-quest:the-lowlands"
    assert status["sky"]


def test_a_playthrough_replays_identically(tmp_path: Path) -> None:
    """The whole point of drawing weather from seeded streams."""
    library = weather_pack(tmp_path)

    def run() -> list[dict[str, Any]]:
        result = begin(library, "tiny", seed="repeat")
        records = result.records()
        state: GameState = result.state
        for _turn in range(12):
            result = step(state, Wait(2), library)
            records.extend(result.records())
            state = result.state
        return records

    assert run() == run()
