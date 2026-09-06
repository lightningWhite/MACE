"""Weather fronts: correlation across space, and warning before weather.

A per-region chain alone can rain in the valley and be clear on the ridge
forever, for no reason. What a front has to buy is spatial correlation, a
direction, and — the part that actually matters to a player — an omen early
enough to act on. Those are the things tested here.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Wait
from mace.engine.state import FrontState
from mace.engine.step import begin, step
from mace.engine.world import Clock, fronts, prepare
from mace.model.calendar import STANDARD_YEAR

REPO_ROOT = Path(__file__).resolve().parent.parent

CONDITIONS: list[dict[str, Any]] = [
    {"id": "clear", "name": "clear"},
    {"id": "rain", "name": "rain", "tags": ["wet"]},
]


def front_pack(
    root: Path,
    *,
    front: dict[str, Any] | None = None,
    frequency: float = 1.0,
) -> Any:
    """A three-region map with one kind of front that always forms.

    Parameters
    ----------
    root : Path
        Where to write it.
    front : dict or None
        Fields to replace on the front definition.
    frequency : float
        The climate's `frontFrequency`.

    Returns
    -------
    Library
        The loaded library.
    """
    definition: dict[str, Any] = {
        "id": "westerly",
        "name": "a westerly",
        "speedTicks": 4,
        "lifespanTicks": 40,
        "hops": [3, 3],
        "intensityRange": [1.0, 1.0],
        "biases": {"rain": 50.0, "clear": 0.0},
        "aheadBias": 0.0,
        "omen": ["The wind has shifted."],
    }
    definition.update(front or {})

    game_pack(
        root,
        game={
            "world": {
                "startSeason": "autumn",
                "startRegion": "west",
                "startTick": 20,
            }
        },
        world={
            "weatherConditions": CONDITIONS,
            "weatherFronts": [definition],
            "climates": [
                {
                    "id": "temperate",
                    "stepTicks": 1,
                    "fronts": ["westerly"],
                    "frontFrequency": frequency,
                    "seasons": {
                        "autumn": {
                            "temperature": {"min": 6, "max": 14},
                            "weights": {"clear": 90, "rain": 10},
                        }
                    },
                    "transitions": {
                        "clear": {"clear": 90, "rain": 10},
                        "rain": {"rain": 50, "clear": 50},
                    },
                }
            ],
            "regions": [
                {"id": "west", "climate": "temperate", "neighbors": ["middle"]},
                {
                    "id": "middle",
                    "climate": "temperate",
                    "neighbors": ["west", "east"],
                },
                {"id": "east", "climate": "temperate", "neighbors": ["middle"]},
            ],
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "region": "middle",
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle", "region": "east"},
            ],
        },
    )
    return load_library(root)


# ── Forming and moving ───────────────────────────────────────────────────────


def test_a_front_forms_and_walks_the_neighbour_graph(tmp_path: Path) -> None:
    library = front_pack(tmp_path)
    # A playthrough opens with weather but no fronts: something is always
    # happening in the sky, but a front is an event, and events need a tick.
    assert begin(library, "tiny", seed="s").state.fronts == []

    result = step(begin(library, "tiny", seed="s").state, Wait(1), library)
    assert result.state.fronts

    front = result.state.fronts[0]
    assert len(front.heading) == 3
    assert len(set(front.heading)) == 3
    for step_index in range(len(front.heading) - 1):
        here = front.heading[step_index].split(":", 1)[1]
        onward = front.heading[step_index + 1].split(":", 1)[1]
        neighbours = library.pack("tiny").regions[here].neighbors
        assert onward in neighbours


def test_a_front_moves_along_and_then_dies(tmp_path: Path) -> None:
    library = front_pack(tmp_path)
    result = step(begin(library, "tiny", seed="s").state, Wait(1), library)
    first = result.state.fronts[0]
    where = first.at

    moved = False
    for _turn in range(20):
        result = step(result.state, Wait(1), library)
        alive = [f for f in result.state.fronts if f.id == first.id]
        if not alive:
            break
        if alive[0].at != where:
            moved = True
            break
    assert moved


def test_one_roll_is_made_for_the_whole_map(tmp_path: Path) -> None:
    """Adding regions must not silently make a game stormier."""
    library = front_pack(tmp_path)
    result = begin(library, "tiny", seed="s")
    before = result.state.fronts_spawned
    result = step(result.state, Wait(1), library)
    assert result.state.fronts_spawned == before + 1


def test_no_fronts_form_without_a_frequency(tmp_path: Path) -> None:
    library = front_pack(tmp_path, frequency=0.0)
    result = begin(library, "tiny", seed="s")
    for _turn in range(20):
        result = step(result.state, Wait(1), library)
    assert result.state.fronts == []


def test_a_front_only_forms_in_the_seasons_it_can(tmp_path: Path) -> None:
    library = front_pack(tmp_path, front={"seasons": ["winter"]})
    result = begin(library, "tiny", seed="s")
    for _turn in range(20):
        result = step(result.state, Wait(1), library)
    assert result.state.fronts == []


# ── What a front does to the sky ─────────────────────────────────────────────


def test_a_front_bends_the_weather_under_it(tmp_path: Path) -> None:
    """The climate wants clear; the front wants rain, and it is over you."""
    library = front_pack(tmp_path)
    result = begin(library, "tiny", seed="s")
    wet = 0
    for _turn in range(30):
        result = step(result.state, Wait(1), library)
        for front in result.state.fronts:
            if front.at == "tiny:middle":
                wet += result.state.weather["tiny:middle"].condition == "tiny:rain"
                break
    assert wet


def test_the_bias_decays_as_the_front_ages(tmp_path: Path) -> None:
    library = front_pack(tmp_path)
    state = step(begin(library, "tiny", seed="s").state, Wait(1), library).state
    front = state.fronts[0]
    front.heading = ("tiny:middle", "tiny:east")
    front.position = 0
    front.born_at_tick = 0

    early = fronts.biases_for(library, state, "tiny:middle", 0)
    late = fronts.biases_for(library, state, "tiny:middle", 30)
    assert early["tiny:rain"] > late["tiny:rain"] > 1.0


def test_the_region_ahead_gets_a_share_of_the_bias(tmp_path: Path) -> None:
    """Foreshadowing, in one number: `aheadBias` is why a player can plan."""
    library = front_pack(tmp_path, front={"aheadBias": 0.5}, frequency=0.0)
    state = begin(library, "tiny", seed="s").state
    state.fronts = [
        FrontState(
            id="f#1",
            kind="tiny:westerly",
            heading=("tiny:west", "tiny:middle"),
            intensity=1.0,
            born_at_tick=state.tick,
            expires_at_tick=state.tick + 40,
            hops_at_tick=state.tick + 4,
        )
    ]
    over = fronts.biases_for(library, state, "tiny:west", state.tick)
    ahead = fronts.biases_for(library, state, "tiny:middle", state.tick)
    behind = fronts.biases_for(library, state, "tiny:east", state.tick)

    assert over["tiny:rain"] > ahead["tiny:rain"] > 1.0
    assert behind == {}


# ── Omens ────────────────────────────────────────────────────────────────────


def test_the_omen_fires_once_when_a_front_is_one_region_away(
    tmp_path: Path,
) -> None:
    library = front_pack(tmp_path, frequency=0.0)
    state = begin(library, "tiny", seed="s").state
    state.fronts = [
        FrontState(
            id="f#1",
            kind="tiny:westerly",
            heading=("tiny:west", "tiny:middle"),
            intensity=1.0,
            born_at_tick=state.tick,
            expires_at_tick=state.tick + 400,
            hops_at_tick=state.tick + 400,
        )
    ]

    said = 0
    for _turn in range(6):
        result = step(state, Wait(1), library)
        state = result.state
        said += sum(
            1
            for event in result.events
            if event.kind == "narrate"
            and event.payload()["text"] == "The wind has shifted."
        )
    assert said == 1


def test_a_front_that_forms_on_top_of_you_gives_no_omen(tmp_path: Path) -> None:
    """A warning that arrives with the storm is not a warning."""
    library = front_pack(tmp_path, frequency=0.0)
    state = begin(library, "tiny", seed="s").state
    state.fronts = [
        FrontState(
            id="f#1",
            kind="tiny:westerly",
            heading=("tiny:middle", "tiny:east"),
            intensity=1.0,
            born_at_tick=state.tick,
            expires_at_tick=state.tick + 400,
            hops_at_tick=state.tick + 400,
        )
    ]
    result = step(state, Wait(1), library)
    assert not [
        event
        for event in result.events
        if event.kind == "narrate"
        and event.payload()["text"] == "The wind has shifted."
    ]


# ── Determinism ──────────────────────────────────────────────────────────────


def test_fronts_draw_from_their_own_stream(tmp_path: Path) -> None:
    """A busy front system must not shift any region's own chain."""
    library = front_pack(tmp_path)
    state = step(begin(library, "tiny", seed="s").state, Wait(1), library).state
    positions = state.rng.positions()
    assert "weather.fronts" in positions
    assert "weather.tiny:middle" in positions


def test_the_world_advances_the_same_way_however_time_is_spent(
    tmp_path: Path,
) -> None:
    """Six one-tick waits and one six-tick wait must leave the same world."""
    library = front_pack(tmp_path)

    slow = begin(library, "tiny", seed="pace").state
    for _turn in range(6):
        slow = step(slow, Wait(1), library).state

    fast = begin(library, "tiny", seed="pace").state
    fast = step(fast, Wait(6), library).state

    assert slow.tick == fast.tick
    assert [f.id for f in slow.fronts] == [f.id for f in fast.fronts]
    assert {r: w.condition for r, w in slow.weather.items()} == {
        r: w.condition for r, w in fast.weather.items()
    }


def test_prepare_resolves_every_region_once() -> None:
    library = load_library(REPO_ROOT / "packs")
    prepared = prepare(library)
    assert "peasants-quest:the-lowlands" in prepared
    region, climate, home = prepared["peasants-quest:the-marches"]
    assert climate is not None
    assert climate.id == "upland"
    assert home == "fantasy.core"
    assert region.elevation == 460


def test_a_region_with_no_neighbours_gets_a_one_stop_heading(
    tmp_path: Path,
) -> None:
    library = front_pack(tmp_path, front={"hops": [3, 3]})
    clock = Clock.for_season(30, STANDARD_YEAR, "autumn")
    state = begin(library, "tiny", seed="s").state

    prepared = prepare(library)
    lonely = {"tiny:east": prepared["tiny:east"]}
    formed, _faded = fronts.step(library, state, clock, lonely)
    assert formed
    assert formed[0].heading == ("tiny:east",)
