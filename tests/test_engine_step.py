"""Playing: what the engine offers, what an action does, and how a game ends.

The loop these test is the whole product at this stage — the engine offers
options, a front-end renders them, and one of them comes back. Everything a
player will ever see arrives as an event.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import Library, load_library
from mace.engine.actions import Choose, Interact, Look, Travel, Wait, decode
from mace.engine.state import Outcome
from mace.engine.step import StepResult, begin, step


def playable(
    tmp_path: Path, *, game: dict[str, Any] | None = None, **world: Any
) -> Library:
    """Write and load a small game.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.
    game : dict or None
        Overrides for the game manifest.
    **world
        Overrides for the content collections.

    Returns
    -------
    Library
        The loaded pack.
    """
    game_pack(tmp_path, game=game, world=world or None)
    return load_library(tmp_path / "tiny")


def kinds(result: StepResult) -> list[str]:
    """The kinds of the events one step produced.

    Parameters
    ----------
    result : StepResult
        A step's result.

    Returns
    -------
    list of str
        Event kinds, in order.
    """
    return [event.kind for event in result.events]


def offered(result: StepResult) -> list[str]:
    """The kinds one step produced, with the trailing status projection cut.

    Every step ends in `world.status` — it is a projection for the front-end's
    status line, not something that happened — so tests that care about what
    the step *did* read this instead.

    Parameters
    ----------
    result : StepResult
        A step's result.

    Returns
    -------
    list of str
        Event kinds, in order, without a trailing `world.status`.
    """
    without = kinds(result)
    return without[:-1] if without and without[-1] == "world.status" else without


def options(result: StepResult) -> list[str]:
    """The prompts the engine is currently waiting on.

    Parameters
    ----------
    result : StepResult
        A step's result.

    Returns
    -------
    list of str
        The option prompts, in order.
    """
    pending = result.state.pending
    assert pending is not None, "the engine offered nothing"
    return [option.prompt for option in pending.options]


def narration(result: StepResult) -> list[str]:
    """Everything narrated by one step.

    Parameters
    ----------
    result : StepResult
        A step's result.

    Returns
    -------
    list of str
        The lines, in order.
    """
    return [
        event.payload()["text"] for event in result.events if event.kind == "narrate"
    ]


# ── Starting ──────────────────────────────────────────────────────────────────


def test_beginning_places_the_player_and_offers_options(tmp_path: Path) -> None:
    library = playable(tmp_path, game={"introduction": ["A short road."]})
    result = begin(library, "tiny")

    assert "A short road." in narration(result)
    assert offered(result)[-1] == "choices"
    assert result.state.location == "tiny:home"
    assert result.state.protagonist.inventory == {"tiny:gold": 5}


def test_the_options_are_the_scenes_here_and_the_ways_out(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        entities=[
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
            {"id": "hallam", "kind": "actor", "name": "Hallam", "scenes": ["greet"]},
        ],
        locations=[
            {
                "id": "home",
                "name": "Home",
                "entities": ["hallam"],
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle"},
        ],
        scenes=[{"id": "greet", "prompt": "Talk to Hallam", "say": ["Hello."]}],
    )
    result = begin(library, "tiny")
    assert options(result) == ["Talk to Hallam", "Travel to The Castle"]


def test_a_pack_that_is_not_a_game_cannot_be_begun(tmp_path: Path) -> None:
    from conftest import write_pack

    write_pack(tmp_path, "library-only")
    library = load_library(tmp_path / "library-only")
    with pytest.raises(Exception, match="not a playable game"):
        begin(library, "library-only")


# ── Acting ────────────────────────────────────────────────────────────────────


def test_travelling_costs_the_route_its_ticks(tmp_path: Path) -> None:
    library = playable(tmp_path, game={"winConditions": []})
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)

    assert result.state.location == "tiny:castle"
    assert result.state.tick == 6
    moved = next(e for e in result.events if e.kind == "moved")
    assert moved.payload() == {
        "from": "tiny:home",
        "to": "tiny:castle",
        "route": "tiny:road",
        "ticks": 6,
    }


def test_travelling_somewhere_unconnected_is_refused(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        locations=[
            {"id": "home", "name": "Home"},
            {"id": "castle", "name": "The Castle"},
        ],
        routes=[],
    )
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)
    assert kinds(result) == ["engine.rule-failed"]
    assert result.state.location == "tiny:home"


def test_an_exit_may_be_gated(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "exits": [
                    {
                        "to": "castle",
                        "route": "road",
                        "when": [{"flag": {"entity": "hero", "flag": "summoned"}}],
                    }
                ],
            },
            {"id": "castle", "name": "The Castle"},
        ],
    )
    result = begin(library, "tiny")
    assert options(result) == []
    result = step(result.state, Travel("castle"), library)
    assert kinds(result) == ["engine.rule-failed"]


def test_looking_costs_nothing_and_describes_the_place(tmp_path: Path) -> None:
    library = playable(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Look(), library)
    assert "Six houses and a well." in narration(result)
    assert result.state.tick == 0


def test_waiting_moves_the_clock(tmp_path: Path) -> None:
    library = playable(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Wait(3), library)
    assert result.state.tick == 3


# ── Scenes ────────────────────────────────────────────────────────────────────


def scene_pack(tmp_path: Path, scenes: list[dict[str, Any]]) -> Library:
    """A game whose home location offers a set of scenes.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.
    scenes : list of dict
        The scenes.

    Returns
    -------
    Library
        The loaded pack.
    """
    return playable(
        tmp_path,
        scenes=scenes,
        locations=[
            {
                "id": "home",
                "name": "Home",
                "scenes": [scene["id"] for scene in scenes],
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle"},
        ],
    )


def test_a_scene_says_its_lines_then_applies_its_effects(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "gift",
                "prompt": "Accept the gift",
                "say": [
                    "He hands you a coin.",
                    {"text": "You take it.", "pause": True},
                ],
                "effects": [{"giveItem": {"item": "gold", "qty": 1}}],
            }
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)

    assert kinds(result)[:4] == [
        "scene.entered",
        "narrate",
        "narrate",
        "inventory.changed",
    ]
    assert result.state.protagonist.inventory["tiny:gold"] == 6


def test_a_line_may_be_conditional(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "look",
                "prompt": "Look around",
                "say": [
                    {"text": "It is dark.", "when": {"dayPart": ["night"]}},
                    {"text": "It is bright.", "when": {"dayPart": ["day"]}},
                ],
            }
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Wait(20), library)  # 10:00
    result = step(result.state, Choose(0), library)
    assert narration(result) == ["It is bright."]


def test_a_failed_condition_runs_the_else_scene(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "haggle",
                "prompt": "Haggle",
                "when": [{"statAtLeast": {"stat": "charisma", "value": 90}}],
                "say": ["He agrees."],
                "else": "refused",
            },
            {"id": "refused", "say": ["He looks at you the way you look at a goose."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert narration(result) == ["He looks at you the way you look at a goose."]


def test_goto_chains_scenes_together(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {"id": "one", "prompt": "Start", "say": ["First."], "goto": "two"},
            {"id": "two", "say": ["Second."], "goto": "three"},
            {"id": "three", "say": ["Third."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert narration(result) == ["First.", "Second.", "Third."]


def test_scenes_that_loop_forever_are_caught(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {"id": "one", "prompt": "Start", "say": ["Again."], "goto": "two"},
            {"id": "two", "say": ["And again."], "goto": "one"},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert kinds(result)[-1] == "engine.rule-failed"


def test_a_once_scene_stops_being_offered(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [{"id": "gift", "prompt": "Accept", "say": ["Once."], "once": True}],
    )
    result = begin(library, "tiny")
    assert len(options(result)) == 2
    result = step(result.state, Choose(0), library)
    assert options(result) == ["Travel to The Castle"]


def test_choices_wait_for_an_answer(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "fork",
                "prompt": "Decide",
                "choices": [
                    {"prompt": "Left", "goto": "left"},
                    {
                        "prompt": "Right",
                        "effects": [{"setVar": {"name": "went", "value": "right"}}],
                    },
                ],
            },
            {"id": "left", "say": ["You go left."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert offered(result)[-1] == "choices"
    assert result.state.pending is not None
    assert result.state.pending.scene == "tiny:fork"

    result = step(result.state, Choose(1), library)
    assert result.state.variables["went"] == "right"


def test_an_unavailable_choice_is_shown_only_when_asked_for(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "fork",
                "prompt": "Decide",
                "choices": [
                    {
                        "prompt": "Pay 100 gold",
                        "when": [{"hasItem": {"item": "gold", "qty": 100}}],
                        "showWhenUnavailable": True,
                        "unavailableHint": "You don't have a hundred gold.",
                        "goto": "paid",
                    },
                    {
                        "prompt": "Pay 200 gold",
                        "when": [{"hasItem": {"item": "gold", "qty": 200}}],
                        "goto": "paid",
                    },
                    {"prompt": "Leave", "goto": "paid"},
                ],
            },
            {"id": "paid", "say": ["Done."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    offered = next(e for e in result.events if e.kind == "choices").payload()["options"]
    assert [option["prompt"] for option in offered] == ["Pay 100 gold", "Leave"]
    assert offered[0] == {
        "prompt": "Pay 100 gold",
        "available": False,
        "hint": "You don't have a hundred gold.",
    }


def test_taking_an_unavailable_choice_is_refused(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "fork",
                "prompt": "Decide",
                "choices": [
                    {
                        "prompt": "Pay 100 gold",
                        "when": [{"hasItem": {"item": "gold", "qty": 100}}],
                        "showWhenUnavailable": True,
                        "goto": "paid",
                    }
                ],
            },
            {"id": "paid", "say": ["Done."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    result = step(result.state, Choose(0), library)
    assert kinds(result) == ["engine.rule-failed"]


def test_choosing_nothing_on_offer_is_refused(tmp_path: Path) -> None:
    library = playable(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Choose(99), library)
    assert kinds(result) == ["engine.rule-failed"]


def test_a_scene_may_be_played_directly(tmp_path: Path) -> None:
    library = scene_pack(tmp_path, [{"id": "aside", "say": ["A thought."]}])
    result = begin(library, "tiny")
    result = step(result.state, Interact("aside"), library)
    assert narration(result)[0] == "A thought."


def test_play_scene_runs_another_scene(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "trigger",
                "prompt": "Remember",
                "effects": [{"playScene": "memory"}],
            },
            {"id": "memory", "say": ["You remember the barley."]},
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert "You remember the barley." in narration(result)


# ── Ending ────────────────────────────────────────────────────────────────────


def test_a_win_condition_ends_the_game_and_plays_its_scene(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        game={
            "winConditions": [{"atLocation": {"location": "castle"}}],
            "onWin": "victory",
        },
        scenes=[{"id": "victory", "say": ["You made it."]}],
    )
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)

    assert result.state.outcome is Outcome.WON
    assert "You made it." in narration(result)
    over = next(e for e in result.events if e.kind == "game.over")
    assert over.payload()["outcome"] == "won"


def test_losing_beats_winning_when_both_are_true(tmp_path: Path) -> None:
    """Dying on the doorstep of victory is the reading a player expects."""
    library = playable(
        tmp_path,
        game={
            "winConditions": [{"atLocation": {"location": "castle"}}],
            "loseConditions": [{"atLocation": {"location": "castle"}}],
        },
    )
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)
    assert result.state.outcome is Outcome.LOST


def test_nothing_happens_after_the_game_is_over(tmp_path: Path) -> None:
    library = playable(tmp_path)
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)
    assert result.state.outcome is Outcome.WON
    assert step(result.state, Look(), library).events == ()


def test_end_game_ends_it(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [{"id": "give-up", "prompt": "Give up", "effects": [{"endGame": {}}]}],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert result.state.outcome is not Outcome.PLAYING


def test_restart_begins_again(tmp_path: Path) -> None:
    library = scene_pack(
        tmp_path,
        [
            {
                "id": "again",
                "prompt": "Start over",
                "effects": [
                    {"giveItem": {"item": "gold", "qty": 50}},
                    {"restart": {}},
                ],
            }
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Choose(0), library)
    assert result.state.protagonist.inventory["tiny:gold"] == 5


# ── Quests ────────────────────────────────────────────────────────────────────


def test_a_quest_advances_when_its_stage_completes(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        game={"quests": ["errand"], "winConditions": []},
        quests=[
            {
                "id": "errand",
                "name": "The Errand",
                "stages": [
                    {
                        "id": "go",
                        "journal": "Get to the castle.",
                        "complete": [{"atLocation": {"location": "castle"}}],
                    },
                    {
                        "id": "wait",
                        "journal": "Wait to be seen.",
                        "complete": [{"expr": "world.tick > 100"}],
                    },
                ],
            }
        ],
    )
    result = begin(library, "tiny")
    assert result.state.quests["tiny:errand"].stage == "go"

    result = step(result.state, Travel("castle"), library)
    assert result.state.quests["tiny:errand"].stage == "wait"
    update = next(e for e in result.events if e.kind == "quest.updated")
    assert update.payload()["journal"] == "Wait to be seen."


def test_a_quest_can_be_failed(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        game={"quests": ["errand"], "winConditions": []},
        quests=[
            {
                "id": "errand",
                "name": "The Errand",
                "stages": [
                    {
                        "id": "go",
                        "journal": "Be quick.",
                        "complete": [{"atLocation": {"location": "castle"}}],
                        "fail": [{"expr": "world.tick > 2"}],
                    }
                ],
            }
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Wait(5), library)
    assert result.state.quests["tiny:errand"].status.value == "failed"


def test_a_quest_completing_can_win_the_game(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        game={
            "quests": ["errand"],
            "winConditions": [{"questComplete": "errand"}],
        },
        quests=[
            {
                "id": "errand",
                "name": "The Errand",
                "stages": [
                    {
                        "id": "go",
                        "journal": "Get there.",
                        "complete": [{"atLocation": {"location": "castle"}}],
                    }
                ],
            }
        ],
    )
    result = begin(library, "tiny")
    result = step(result.state, Travel("castle"), library)
    assert result.state.outcome is Outcome.WON


# ── Determinism ───────────────────────────────────────────────────────────────


def test_the_same_seed_and_actions_replay_exactly(tmp_path: Path) -> None:
    library = playable(
        tmp_path,
        game={"winConditions": []},
        scenes=[
            {
                "id": "gamble",
                "prompt": "Gamble",
                "when": [{"chance": 0.5}],
                "say": ["Lucky."],
                "else": "unlucky",
            },
            {"id": "unlucky", "say": ["Not this time."]},
        ],
        locations=[
            {
                "id": "home",
                "name": "Home",
                "scenes": ["gamble"],
                "exits": [{"to": "castle", "route": "road"}],
            },
            {"id": "castle", "name": "The Castle"},
        ],
    )

    def play() -> list[dict[str, Any]]:
        result = begin(library, "tiny", seed="fixed")
        records = result.records()
        for action in (Choose(0), Wait(2), Choose(0)):
            result = step(result.state, action, library)
            records.extend(result.records())
        return records

    assert play() == play()


def test_a_different_seed_is_a_different_playthrough(tmp_path: Path) -> None:
    library = playable(tmp_path)
    first = begin(library, "tiny", seed="one").state
    second = begin(library, "tiny", seed="two").state
    assert first.rng.seed != second.rng.seed


# ── The action log ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "action",
    [Look(), Wait(3), Choose(2), Interact("greet"), Travel("castle")],
)
def test_actions_round_trip_through_their_records(action: Any) -> None:
    assert decode(action.record()) == action


def test_an_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown action"):
        decode({"kind": "teleport"})
