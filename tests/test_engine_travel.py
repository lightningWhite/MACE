"""Travel as a process: legs, waypoints, weather, and being stopped partway.

The point of routes having a length is that a journey is something that
happens rather than something that resolves. What has to be true for that to
pay off: bad weather costs real hours, a waypoint on the road is met whether
you chose it or not, a journey that stops can be carried on or turned back,
and a bridge with a troll on it keeps stopping you until you deal with it.
"""

from pathlib import Path
from typing import Any

import yaml

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Choose
from mace.engine.step import begin, step

REPO_ROOT = Path(__file__).resolve().parent.parent

WET = [
    {"id": "clear", "name": "clear"},
    {"id": "slog", "name": "heavy going", "travelMultiplier": 2.0, "tags": ["wet"]},
    {
        "id": "storm",
        "name": "storm",
        "travelMultiplier": 2.0,
        "blocksTravel": True,
        "tags": ["wet"],
    },
]


def road_pack(
    root: Path,
    *,
    route: dict[str, Any] | None = None,
    locations: list[dict[str, Any]] | None = None,
    weather: str | None = None,
    extra_entities: list[dict[str, Any]] | None = None,
) -> Any:
    """A pack with one road worth walking.

    Parameters
    ----------
    root : Path
        Where to write it.
    route : dict or None
        Fields to merge into the road.
    locations : list or None
        Locations, replacing the defaults.
    weather : str or None
        A condition to pin over the starting location.
    extra_entities : list or None
        Entities to add alongside the default protagonist and coin.

    Returns
    -------
    Library
        The loaded library.
    """
    road: dict[str, Any] = {
        "id": "road",
        "name": "The Road",
        "from": "home",
        "to": "castle",
        "ticks": 6,
        "legDescriptions": ["The road goes on."],
    }
    road.update(route or {})

    home: dict[str, Any] = {
        "id": "home",
        "name": "Home",
        "region": "valley",
        "exits": [{"to": "castle", "route": "road"}],
    }
    if weather is not None:
        home["climate"] = {"condition": weather}

    people: list[dict[str, Any]] = [
        {
            "id": "hero",
            "kind": "actor",
            "name": "Hero",
            "playable": True,
            "stats": {
                "hitpoints": {"base": 20, "max": 20},
                "stamina": {"base": 10, "max": 10},
            },
        },
        {"id": "gold", "kind": "item", "name": "Gold", "item": {"baseValue": 1}},
        *(extra_entities or []),
    ]

    game_pack(
        root,
        game={
            "world": {"startRegion": "valley", "startTick": 20},
            # Reaching the castle must not end the game: several of these
            # tests walk the road back again.
            "winConditions": [{"flag": {"entity": "hero", "flag": "mustered"}}],
        },
        world={
            "entities": people,
            "weatherConditions": WET,
            "climates": [
                {
                    "id": "still",
                    "seasons": {"spring": {"weights": {"clear": 1}}},
                    "transitions": {"clear": {"clear": 1}},
                }
            ],
            "regions": [{"id": "valley", "climate": "still"}],
            "routes": [road],
            "locations": locations
            or [
                home,
                {"id": "castle", "name": "The Castle", "region": "valley"},
                {"id": "bridge", "name": "The Bridge", "region": "valley"},
            ],
        },
    )
    return load_library(root)


def kinds(result: Any) -> list[str]:
    """The kinds of one step's events.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    list of str
        Event kinds, in order.
    """
    return [event.kind for event in result.events]


def legs(result: Any) -> list[dict[str, Any]]:
    """The travel-leg events of one step.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    list of dict
        Their payloads.
    """
    return [e.payload() for e in result.events if e.kind == "travel.leg"]


def moved(result: Any) -> dict[str, Any] | None:
    """The arrival event of one step, if it arrived.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    dict or None
        The payload of the `moved` event.
    """
    for event in result.events:
        if event.kind == "moved":
            return event.payload()
    return None


# ── Legs ─────────────────────────────────────────────────────────────────────


def test_a_journey_is_walked_leg_by_leg(tmp_path: Path) -> None:
    library = road_pack(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)

    assert [leg["leg"] for leg in legs(result)] == [1, 2, 3, 4, 5, 6]
    assert all(leg["of"] == 6 for leg in legs(result))
    assert result.state.location == "tiny:castle"


def test_time_is_reported_once_for_the_whole_journey(tmp_path: Path) -> None:
    """Six legs is one `world.time`, not six: three hours went by, not six halves."""
    library = road_pack(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert kinds(result).count("world.time") == 1
    assert moved(result) == {
        "from": "tiny:home",
        "to": "tiny:castle",
        "route": "tiny:road",
        "ticks": 6,
    }


def test_an_exit_with_no_route_is_a_doorway_not_a_road(tmp_path: Path) -> None:
    library = road_pack(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "exits": [{"to": "castle"}],
            },
            {"id": "castle", "name": "The Castle", "region": "valley"},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert legs(result) == []
    assert result.state.location == "tiny:castle"


# ── Weather ──────────────────────────────────────────────────────────────────


def test_bad_weather_makes_the_road_longer(tmp_path: Path) -> None:
    """A six-tick road at a two-times multiplier is twelve ticks of walking."""
    fair = road_pack(tmp_path / "fair")
    result = step(begin(fair, "tiny").state, Choose(0), fair)
    assert moved(result) == {
        "from": "tiny:home",
        "to": "tiny:castle",
        "route": "tiny:road",
        "ticks": 6,
    }

    foul = road_pack(tmp_path / "foul", weather="slog")
    result = step(begin(foul, "tiny").state, Choose(0), foul)
    assert moved(result) is not None
    assert moved(result)["ticks"] == 12  # type: ignore[index]
    # The road is still six legs long. It just took twice as long to walk.
    assert [leg["leg"] for leg in legs(result)] == [1, 2, 3, 4, 5, 6]


def test_a_closed_road_cannot_be_set_out_on(tmp_path: Path) -> None:
    library = road_pack(tmp_path, weather="storm")
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert kinds(result) == ["engine.rule-failed"]
    assert "the road is closed" in result.events[0].payload()["message"]
    assert result.state.location == "tiny:home"


# ── Waypoints ────────────────────────────────────────────────────────────────


def test_a_waypoint_is_met_whether_you_chose_it_or_not(tmp_path: Path) -> None:
    library = road_pack(
        tmp_path, route={"waypoints": [{"location": "bridge", "atTick": 3}]}
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)

    stops = [leg["waypoint"] for leg in legs(result) if leg["waypoint"]]
    assert stops == ["tiny:bridge"]
    assert result.state.location == "tiny:castle"


def test_waypoints_with_no_tick_are_spaced_evenly(tmp_path: Path) -> None:
    library = road_pack(
        tmp_path,
        route={"ticks": 6, "waypoints": [{"location": "bridge"}]},
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    reached = [leg for leg in legs(result) if leg["waypoint"]]
    assert reached and reached[0]["leg"] == 3


def test_a_waypoint_is_mirrored_when_the_road_is_walked_the_other_way(
    tmp_path: Path,
) -> None:
    """The bridge is three ticks from home whichever end you started at."""
    library = road_pack(
        tmp_path,
        route={"waypoints": [{"location": "bridge", "atTick": 2}]},
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "exits": [{"to": "castle", "route": "road"}],
            },
            {
                "id": "castle",
                "name": "The Castle",
                "region": "valley",
                "exits": [{"to": "home", "route": "road"}],
            },
            {"id": "bridge", "name": "The Bridge", "region": "valley"},
        ],
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    outbound = [leg["leg"] for leg in legs(result) if leg["waypoint"]]
    assert outbound == [2]

    back = step(result.state, Choose(0), library)
    homeward = [leg["leg"] for leg in legs(back) if leg["waypoint"]]
    assert homeward == [4]


# ── Being stopped ────────────────────────────────────────────────────────────


def barred(tmp_path: Path) -> Any:
    """A road with a bridge on it that will not let you past.

    Parameters
    ----------
    tmp_path : Path
        Where to write the pack.

    Returns
    -------
    Library
        The loaded library.
    """
    return road_pack(
        tmp_path,
        route={
            "waypoints": [
                {
                    "location": "bridge",
                    "atTick": 3,
                    "stopIf": [
                        {"flag": {"entity": "gate", "flag": "open", "is": False}}
                    ],
                }
            ]
        },
        locations=[
            {
                "id": "home",
                "name": "Home",
                "region": "valley",
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle", "region": "valley"},
            {
                "id": "bridge",
                "name": "The Bridge",
                "region": "valley",
                "entities": ["gate"],
            },
        ],
        extra_entities=[{"id": "gate", "kind": "fixture", "name": "The Gate"}],
    )


def test_a_stop_condition_ends_the_journey_where_it_stands(tmp_path: Path) -> None:
    library = barred(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)

    assert "travel.interrupted" in kinds(result)
    assert result.state.location == "tiny:bridge"
    assert result.state.journey is not None
    assert result.state.journey.blocked_at == "tiny:bridge"


def test_an_interrupted_journey_offers_carrying_on_or_turning_back(
    tmp_path: Path,
) -> None:
    library = barred(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)
    prompts = [
        option["prompt"]
        for event in result.events
        if event.kind == "choices"
        for option in event.payload()["options"]
    ]
    assert "Carry on to The Castle" in prompts
    assert "Turn back to Home" in prompts


def test_carrying_on_while_still_barred_costs_nothing_and_gets_nowhere(
    tmp_path: Path,
) -> None:
    """Trying the bridge again while the troll is still owed is not a free pass."""
    library = barred(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)
    at = result.state.tick

    onward = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"].startswith("Carry on")
    ][0]
    result = step(result.state, Choose(onward), library)

    assert result.state.location == "tiny:bridge"
    assert result.state.tick == at
    assert "travel.interrupted" in kinds(result)


def test_once_the_way_clears_the_journey_carries_on(tmp_path: Path) -> None:
    library = barred(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)
    result.state.entities["tiny:gate"].flags.add("open")

    onward = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"].startswith("Carry on")
    ][0]
    result = step(result.state, Choose(onward), library)

    assert result.state.location == "tiny:castle"
    assert result.state.journey is None


def test_turning_back_walks_the_road_again(tmp_path: Path) -> None:
    """Turning round is a decision with a cost, not an undo."""
    library = barred(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)
    at_bridge = result.state.tick

    back = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"].startswith("Turn back")
    ][0]
    result = step(result.state, Choose(back), library)

    assert result.state.location == "tiny:home"
    assert result.state.tick > at_bridge
    assert result.state.journey is None


# ── The shipped game ─────────────────────────────────────────────────────────


def test_the_bridge_on_the_north_road_is_a_waypoint() -> None:
    """You do not choose to visit the Old Bridge; it is in the way."""
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="mace")
    result = step(result.state, Choose(2), library)

    assert result.state.location == "peasants-quest:troll-bridge"
    assert result.state.journey is not None
    assert result.state.journey.destination == "peasants-quest:hagans-castle"


# ── Terrain ──────────────────────────────────────────────────────────────────


def terrain_pack(tmp_path: Path, *, weather: str, surface: dict[str, Any]) -> Any:
    """A road with a named surface, under a pinned condition.

    Parameters
    ----------
    tmp_path : Path
        Where to write the pack.
    weather : str
        The condition pinned over home.
    surface : dict
        The terrain definition.

    Returns
    -------
    Library
        The loaded library.
    """
    library = road_pack(
        tmp_path,
        weather=weather,
        route={
            "id": "road",
            "from": "home",
            "to": "castle",
            "ticks": 4,
            "terrain": surface["id"],
        },
    )
    del library

    path = tmp_path / "tiny" / "terrains.yml"
    path.write_text(yaml.safe_dump({"terrains": [surface]}, sort_keys=False))
    return load_library(tmp_path)


def test_terrain_multiplies_on_top_of_the_weather(tmp_path: Path) -> None:
    """Rain on a paved road is an inconvenience; rain on a track is mud."""
    good = terrain_pack(
        tmp_path / "good",
        weather="slog",
        surface={"id": "paved", "travelMultiplier": 1.0, "inWeather": {"wet": 1.0}},
    )
    bad = terrain_pack(
        tmp_path / "bad",
        weather="slog",
        surface={"id": "track", "travelMultiplier": 1.0, "inWeather": {"wet": 2.0}},
    )

    quick = moved(step(begin(good, "tiny").state, Choose(0), good))
    slow = moved(step(begin(bad, "tiny").state, Choose(0), bad))
    assert quick is not None and slow is not None
    assert slow["ticks"] > quick["ticks"]


def test_only_the_worst_weather_tag_counts(tmp_path: Path) -> None:
    """A wet, cold, windy night should be bad, not impossible."""
    library = terrain_pack(
        tmp_path,
        weather="slog",
        surface={
            "id": "track",
            "travelMultiplier": 1.0,
            "inWeather": {"wet": 2.0, "cold": 3.0},
        },
    )
    surface = library.pack("tiny").terrains["track"]
    assert surface.cost(("wet", "cold")) == 3.0
    assert surface.cost(()) == 1.0
