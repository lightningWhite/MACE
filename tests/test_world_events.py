"""World events: a date you can learn, and a disaster you can only read.

The two kinds exist to produce two different kinds of play, and that is what
these tests pin down. A celestial event has to be a pure function of the
calendar, because a date that cannot be known cannot be planned around. A
pressure event has to build with jitter, because an accumulator you can count
is a schedule wearing a costume — and its omens have to get more frequent as it
rises, because that is the only honest signal the player gets.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack
from mace.content import load_library, validate_library
from mace.engine.actions import Choose, Wait
from mace.engine.state import EventPhase
from mace.engine.step import begin, step

REPO_ROOT = Path(__file__).resolve().parent.parent


def event_pack(
    root: Path,
    *,
    celestial: list[dict[str, Any]] | None = None,
    pressure: list[dict[str, Any]] | None = None,
    scenes: list[dict[str, Any]] | None = None,
) -> Any:
    """A two-region pack with world events in it.

    Parameters
    ----------
    root : Path
        Where to write it.
    celestial : list or None
        Celestial event definitions.
    pressure : list or None
        Pressure event definitions.
    scenes : list or None
        Extra scenes.

    Returns
    -------
    Library
        The loaded library.
    """
    game_pack(
        root,
        game={
            "world": {"startRegion": "valley", "startTick": 0},
            "winConditions": [{"flag": {"entity": "hero", "flag": "done"}}],
        },
        world={
            "weatherConditions": [{"id": "clear", "name": "clear"}],
            "climates": [
                {
                    "id": "still",
                    "seasons": {"spring": {"weights": {"clear": 1}}},
                    "transitions": {"clear": {"clear": 1}},
                }
            ],
            "regions": [
                {"id": "valley", "climate": "still", "neighbors": ["ridge"]},
                {"id": "ridge", "climate": "still", "neighbors": ["valley"]},
            ],
            "celestialEvents": celestial or [],
            "pressureEvents": pressure or [],
            "routes": [{"id": "road", "from": "home", "to": "castle", "ticks": 2}],
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "region": "valley",
                    "scenes": [s["id"] for s in (scenes or []) if s.get("prompt")],
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle", "region": "ridge"},
            ],
            "scenes": scenes or [],
        },
    )
    return load_library(root)


def beats(result: Any) -> list[tuple[str, str]]:
    """The event beats of one step.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    list of tuple
        Event id and phase.
    """
    return [
        (e.payload()["event"], e.payload()["phase"])
        for e in result.events
        if e.kind == "world.event"
    ]


def spoken(result: Any) -> list[str]:
    """Everything narrated in one step.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    list of str
        The lines.
    """
    return [e.payload()["text"] for e in result.events if e.kind == "narrate"]


ECLIPSE = {
    "id": "eclipse",
    "name": "The Swallowing",
    "period": 100,
    "phase": 3,
    "durationTicks": 4,
    "warnTicks": 24,
    "global": True,
    "warning": ["The old people have gone quiet."],
    "announce": ["The sun goes out."],
    "while": {"light": 0.05, "weatherTags": ["ominous"]},
    "aftermath": [{"setVar": {"name": "sawIt", "value": True}}],
}


# ── Celestial: a date, and therefore a plan ──────────────────────────────────


def test_a_celestial_event_lands_exactly_when_the_calendar_says(
    tmp_path: Path,
) -> None:
    """No randomness at all: not even the seed changes the date."""
    library = event_pack(tmp_path, celestial=[ECLIPSE])

    for seed in ("one", "two", "three"):
        result = begin(library, "tiny", seed=seed)
        onset = None
        for _turn in range(150):
            result = step(result.state, Wait(1), library)
            if ("tiny:eclipse", "onset") in beats(result):
                onset = result.state.tick
                break
        # Day 3 of a 48-tick day: tick 96.
        assert onset == 96


def test_it_warns_before_it_happens(tmp_path: Path) -> None:
    library = event_pack(tmp_path, celestial=[ECLIPSE])
    result = begin(library, "tiny")

    warned = None
    for _turn in range(100):
        result = step(result.state, Wait(1), library)
        if ("tiny:eclipse", "building") in beats(result):
            warned = result.state.tick
            assert "The old people have gone quiet." in spoken(result)
            break
    assert warned == 96 - 24


def test_while_it_runs_the_sky_is_out(tmp_path: Path) -> None:
    library = event_pack(tmp_path, celestial=[ECLIPSE])
    result = begin(library, "tiny")
    for _turn in range(96):
        result = step(result.state, Wait(1), library)

    status = [e.payload() for e in result.events if e.kind == "world.status"][-1]
    assert status["light"] == 0.05
    assert result.state.events["tiny:eclipse"].phase is EventPhase.ACTIVE


def test_when_it_ends_the_world_goes_back_and_keeps_the_aftermath(
    tmp_path: Path,
) -> None:
    library = event_pack(tmp_path, celestial=[ECLIPSE])
    result = begin(library, "tiny")
    for _turn in range(104):
        result = step(result.state, Wait(1), library)

    status = [e.payload() for e in result.events if e.kind == "world.status"][-1]
    assert status["light"] > 0.05
    assert result.state.variables["sawIt"] is True


def test_it_comes_round_again_on_its_period(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path, celestial=[{**ECLIPSE, "period": 2, "phase": 2, "warnTicks": 0}]
    )
    result = begin(library, "tiny")
    onsets = 0
    for _turn in range(300):
        result = step(result.state, Wait(1), library)
        onsets += ("tiny:eclipse", "onset") in beats(result)
    assert onsets >= 2


# ── Pressure: a risk, and therefore a decision ───────────────────────────────


VOLCANO = {
    "id": "volcano",
    "name": "The Mountain",
    "regions": ["valley"],
    "pressure": {"ratePerTick": 0.05, "variance": 0.5},
    "omens": [
        {"atPressure": 0.3, "weight": 30, "text": "Grey snow."},
        {"atPressure": 0.7, "weight": 60, "text": "The birds have gone."},
    ],
    "imminentAtPressure": 0.9,
    "imminent": {"announce": ["It draws a long breath."]},
    "onset": {"announce": ["The mountain opens."]},
    "activeTicks": 10,
    "while": {"travelMultiplier": 2.0},
    "aftermath": [{"setVar": {"name": "erupted", "value": True}}],
}


def test_a_pressure_event_builds_and_then_fires(tmp_path: Path) -> None:
    library = event_pack(tmp_path, pressure=[VOLCANO])
    result = begin(library, "tiny", seed="boom")

    order: list[str] = []
    for _turn in range(80):
        result = step(result.state, Wait(1), library)
        order.extend(phase for event, phase in beats(result) if event == "tiny:volcano")
        if "aftermath" in order:
            break

    assert [p for p in order if p != "omen"] == ["imminent", "onset", "aftermath"]
    assert result.state.variables["erupted"] is True


def test_the_jitter_means_two_seeds_give_two_dates(tmp_path: Path) -> None:
    """Without it a player could count ticks and derive the date."""
    library = event_pack(tmp_path, pressure=[VOLCANO])

    dates = set()
    for seed in ("a", "b", "c", "d", "e"):
        result = begin(library, "tiny", seed=seed)
        for _turn in range(80):
            result = step(result.state, Wait(1), library)
            if ("tiny:volcano", "onset") in beats(result):
                dates.add(result.state.tick)
                break
    assert len(dates) > 1


def test_omens_get_likelier_as_it_gets_closer(tmp_path: Path) -> None:
    """The honest signal: more omens genuinely means closer."""
    library = event_pack(
        tmp_path,
        pressure=[{**VOLCANO, "pressure": {"ratePerTick": 0.004, "variance": 0.0}}],
    )
    early, late = 0, 0
    for seed in ("s1", "s2", "s3", "s4", "s5", "s6"):
        result = begin(library, "tiny", seed=seed)
        for turn in range(240):
            result = step(result.state, Wait(1), library)
            shown = sum(1 for event, phase in beats(result) if phase == "omen")
            if turn < 120:
                early += shown
            else:
                late += shown
    assert late > early


def test_an_omen_is_narration_and_never_a_number(tmp_path: Path) -> None:
    library = event_pack(tmp_path, pressure=[VOLCANO])
    result = begin(library, "tiny", seed="quiet")
    for _turn in range(40):
        result = step(result.state, Wait(1), library)
        for _event, phase in beats(result):
            if phase == "omen":
                assert set(spoken(result)) & {"Grey snow.", "The birds have gone."}
                return


def test_earliest_day_holds_it_off(tmp_path: Path) -> None:
    library = event_pack(tmp_path, pressure=[{**VOLCANO, "earliestDay": 3}])
    result = begin(library, "tiny", seed="held")
    for _turn in range(90):
        result = step(result.state, Wait(1), library)
        assert not [p for _e, p in beats(result) if p == "onset"] or (
            result.state.tick >= 96
        )


def test_latest_day_makes_sure_it_is_not_missed(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[
            {
                **VOLCANO,
                "pressure": {"ratePerTick": 0.0, "variance": 0.0},
                "latestDay": 2,
            }
        ],
    )
    result = begin(library, "tiny", seed="forced")
    fired = False
    for _turn in range(120):
        result = step(result.state, Wait(1), library)
        fired = fired or ("tiny:volcano", "onset") in beats(result)
    assert fired


def test_a_modifier_can_hold_an_event_back_or_hurry_it_on(tmp_path: Path) -> None:
    slow = event_pack(
        tmp_path / "slow",
        pressure=[
            {
                **VOLCANO,
                "pressure": {
                    "ratePerTick": 0.02,
                    "variance": 0.0,
                    "modifiers": [
                        {"when": {"expr": "vars.appeased == true"}, "mult": 0.1}
                    ],
                },
            }
        ],
    )
    result = begin(slow, "tiny", seed="calm")
    result.state.variables["appeased"] = True
    for _turn in range(40):
        result = step(result.state, Wait(1), library=slow)
    assert result.state.events["tiny:volcano"].phase is not EventPhase.ACTIVE


# ── Triggered ────────────────────────────────────────────────────────────────


def test_a_scene_can_fire_an_event_outright(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[{**VOLCANO, "pressure": {"ratePerTick": 0.0}}],
        scenes=[
            {
                "id": "ritual",
                "prompt": "Perform the ritual",
                "say": ["You say the words."],
                "effects": [{"fireEvent": "volcano"}],
            }
        ],
    )
    result = begin(library, "tiny")
    ritual = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Perform the ritual"
    ][0]
    result = step(result.state, Choose(ritual), library)

    assert ("tiny:volcano", "onset") in beats(result)
    assert "The mountain opens." in spoken(result)


def test_a_scene_can_put_an_event_on_the_brink(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[{**VOLCANO, "pressure": {"ratePerTick": 0.0}}],
        scenes=[
            {
                "id": "ritual",
                "prompt": "Perform the ritual",
                "say": ["You say the words."],
                "effects": [{"setPressure": {"event": "volcano", "value": 0.95}}],
            }
        ],
    )
    result = begin(library, "tiny")
    ritual = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Perform the ritual"
    ][0]
    result = step(result.state, Choose(ritual), library)
    assert result.state.events["tiny:volcano"].pressure == 0.95


# ── Aftermath: what makes it an event and not a weather condition ────────────


def test_an_aftermath_can_shut_a_road_for_good(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[
            {
                **VOLCANO,
                "activeTicks": 0,
                "aftermath": [
                    {
                        "closeRoute": {
                            "route": "road",
                            "permanent": True,
                            "reason": "The road is gone.",
                        }
                    }
                ],
            }
        ],
        scenes=[
            {
                "id": "ritual",
                "prompt": "Perform the ritual",
                "effects": [{"fireEvent": "volcano"}],
            }
        ],
    )
    result = begin(library, "tiny")
    ritual = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Perform the ritual"
    ][0]
    result = step(result.state, Choose(ritual), library)
    result = step(result.state, Wait(1), library)

    assert result.state.routes["tiny:road"].closed
    travel = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"].startswith("Travel")
    ][0]
    result = step(result.state, Choose(travel), library)
    assert [e.kind for e in result.events] == ["engine.rule-failed"]
    assert "The road is gone." in result.events[0].payload()["message"]


def test_an_aftermath_can_make_a_road_longer(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[
            {
                **VOLCANO,
                "activeTicks": 0,
                "aftermath": [{"setRouteTicks": {"route": "road", "ticks": 5}}],
            }
        ],
        scenes=[
            {
                "id": "ritual",
                "prompt": "Perform the ritual",
                "effects": [{"fireEvent": "volcano"}],
            }
        ],
    )
    result = begin(library, "tiny")
    ritual = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Perform the ritual"
    ][0]
    result = step(result.state, Choose(ritual), library)
    result = step(result.state, Wait(1), library)

    travel = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"].startswith("Travel")
    ][0]
    result = step(result.state, Choose(travel), library)
    legs = [e.payload() for e in result.events if e.kind == "travel.leg"]
    assert legs and legs[-1]["of"] == 5


# ── News ─────────────────────────────────────────────────────────────────────


def test_something_that_happens_out_of_sight_becomes_news(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[{**VOLCANO, "regions": ["ridge"], "activeTicks": 0}],
    )
    result = begin(library, "tiny", seed="afar")
    for _turn in range(80):
        result = step(result.state, Wait(1), library)
        if result.state.news:
            break

    assert result.state.news
    item = result.state.news[0]
    assert item.event == "tiny:volcano"
    assert not item.told
    # It happened somewhere else, so it was not narrated where the player was.
    assert "The mountain opens." not in spoken(result)


def test_news_is_passed_on_by_a_scene_that_asks_for_it(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        pressure=[{**VOLCANO, "regions": ["ridge"], "activeTicks": 0}],
        scenes=[
            {
                "id": "gossip",
                "prompt": "Ask what the news is",
                "effects": [{"tellNews": 1}],
            }
        ],
    )
    result = begin(library, "tiny", seed="afar")
    for _turn in range(80):
        result = step(result.state, Wait(1), library)
        if result.state.news:
            break

    gossip = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Ask what the news is"
    ][0]
    result = step(result.state, Choose(gossip), library)

    assert "The mountain opens." in spoken(result)
    assert [e.kind for e in result.events].count("world.news") == 1
    assert result.state.news[0].told


# ── Determinism, and the shipped packs ───────────────────────────────────────


def test_omens_do_not_shift_the_date(tmp_path: Path) -> None:
    """Separate streams: a chatty omen must not move the eruption."""
    library = event_pack(tmp_path, pressure=[VOLCANO])
    state = begin(library, "tiny", seed="streams").state
    for _turn in range(20):
        state = step(state, Wait(1), library).state
    assert "world.events" in state.rng.positions()
    assert "world.omens" in state.rng.positions()


def test_the_shipped_game_has_events_in_it() -> None:
    library = load_library(REPO_ROOT / "packs")
    pack = library.pack("peasants-quest")
    assert "the-swallowing" in pack.celestial_events
    assert "hillside-slip" in pack.pressure_events
    assert not validate_library(library).errors


def test_a_dangling_event_reference_is_caught_at_load(tmp_path: Path) -> None:
    library = event_pack(
        tmp_path,
        scenes=[
            {
                "id": "ritual",
                "prompt": "Perform the ritual",
                "effects": [{"fireEvent": "no-such-mountain"}],
            }
        ],
    )
    report = validate_library(library)
    assert any(
        "not a celestial or pressure event" in problem.message
        for problem in report.problems
    )
