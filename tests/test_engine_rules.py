"""Conditions and effects: the two halves of what content can say.

A condition asks a question about the world and must not change it. An effect
changes the world and must say what it changed. Everything below is one or the
other.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import Library, load_library
from mace.engine.conditions import RuleError, holds
from mace.engine.context import RuleContext
from mace.engine.effects import apply_all
from mace.engine.state import GameState
from mace.engine.step import begin
from mace.engine.world import Clock
from mace.model import Condition, Effect


def playthrough(
    tmp_path: Path, *, game: dict[str, Any] | None = None, **world: Any
) -> tuple[RuleContext, GameState, Library]:
    """Start a small game and hand back everything a rule needs.

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
    tuple
        A context, the state it wraps, and the library behind it.
    """
    game_pack(tmp_path, game=game, world=world or None)
    library = load_library(tmp_path / "tiny")
    state = begin(library, "tiny", seed="test").state
    manifest = library.pack("tiny").game
    assert manifest is not None
    context = RuleContext(
        library=library,
        state=state,
        clock=Clock(manifest.world.minutes_per_tick),
        game=manifest,
    )
    return context, state, library


def ask(context: RuleContext, authored: dict[str, Any]) -> bool:
    """Evaluate one authored condition.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    authored : dict
        The condition as written in YAML.

    Returns
    -------
    bool
        The answer.
    """
    return holds(Condition.model_validate(authored), context)


def do(context: RuleContext, *authored: dict[str, Any]) -> Any:
    """Apply authored effects.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    *authored
        The effects as written in YAML.

    Returns
    -------
    EffectOutcome
        What happened.
    """
    return apply_all([Effect.model_validate(item) for item in authored], context)


# ── Conditions ────────────────────────────────────────────────────────────────


def test_has_item_counts_the_inventory(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert ask(context, {"hasItem": {"item": "gold", "qty": 5}})
    assert not ask(context, {"hasItem": {"item": "gold", "qty": 6}})


def test_at_location_follows_the_player(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert ask(context, {"atLocation": {"location": "home"}})
    assert not ask(context, {"atLocation": {"location": "castle"}})


def test_flags_default_to_absent(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert not ask(context, {"flag": {"entity": "hero", "flag": "warned"}})
    assert ask(context, {"flag": {"entity": "hero", "flag": "warned", "is": False}})


def test_stat_comparisons_read_effective_values(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert ask(context, {"statAtLeast": {"stat": "charisma", "value": 30}})
    assert not ask(context, {"statAtLeast": {"stat": "charisma", "value": 31}})
    assert ask(context, {"statAtMost": {"stat": "charisma", "value": 30}})


def test_logic_combines_conditions(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    here = {"atLocation": {"location": "home"}}
    there = {"atLocation": {"location": "castle"}}
    assert ask(context, {"all": [here, {"not": there}]})
    assert ask(context, {"any": [there, here]})
    assert not ask(context, {"all": [here, there]})


def test_expressions_read_the_world(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert ask(context, {"expr": "world.day == 1"})
    assert ask(context, {"expr": "player.pools.hitpoints.current == 20"})
    assert ask(context, {"expr": "player.stats.charisma > 20"})


def test_an_unanswerable_condition_is_reported_not_guessed(tmp_path: Path) -> None:
    """Answering `false` quietly is how a game becomes unplayable in silence."""
    context, _state, _library = playthrough(tmp_path)
    with pytest.raises(RuleError, match="hitponts"):
        ask(context, {"expr": "player.pools.hitponts.current < 5"})


def test_a_condition_about_a_missing_entity_is_an_error(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    with pytest.raises(RuleError):
        ask(context, {"flag": {"entity": "nobody", "flag": "x"}})


def test_chance_draws_from_a_stream(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    before = state.rng.stream("ambient").position
    ask(context, {"chance": 0.5})
    assert state.rng.stream("ambient").position == before + 1


def test_weather_conditions_are_false_until_there_is_weather(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    assert not ask(context, {"weather": ["rain"]})
    assert not ask(context, {"weatherTag": ["wet"]})


def test_day_part_comes_from_the_clock(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    state.tick = 20  # 10:00 at thirty minutes a tick
    assert ask(context, {"dayPart": ["day"]})
    state.tick = 40  # 20:00
    assert ask(context, {"dayPart": ["night"]})


# ── Effects ───────────────────────────────────────────────────────────────────


def test_giving_and_taking_items_reports_the_new_total(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    outcome = do(context, {"giveItem": {"item": "gold", "qty": 3}})
    assert state.protagonist.inventory["tiny:gold"] == 8
    assert outcome.events[0].payload()["quantity"] == 8

    do(context, {"takeItem": {"item": "gold", "qty": 100}})
    assert "tiny:gold" not in state.protagonist.inventory, "never goes negative"


def test_adjusting_a_stat_reports_what_actually_landed(tmp_path: Path) -> None:
    """A heal that overflows must not tell the player it healed for twenty."""
    context, state, _library = playthrough(tmp_path)
    do(context, {"adjustStat": {"stat": "hitpoints", "delta": -8}})
    assert state.protagonist.pools["hitpoints"] == 12

    outcome = do(context, {"adjustStat": {"stat": "hitpoints", "delta": 20}})
    assert state.protagonist.pools["hitpoints"] == 20
    assert outcome.events[0].payload()["delta"] == 8


def test_setting_a_stat_may_use_an_expression(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    do(context, {"adjustStat": {"stat": "hitpoints", "delta": -15}})
    do(
        context,
        {
            "setStat": {
                "stat": "hitpoints",
                "value": {"expr": "player.pools.hitpoints.max"},
            }
        },
    )
    assert state.protagonist.pools["hitpoints"] == 20


def test_a_stat_nobody_declared_is_an_error(tmp_path: Path) -> None:
    context, _state, _library = playthrough(tmp_path)
    with pytest.raises(RuleError, match="no stat `courage`"):
        do(context, {"adjustStat": {"stat": "courage", "delta": 1}})


def test_flags_variables_and_dispositions_are_set(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    do(
        context,
        {"setFlag": {"entity": "hero", "flag": "warned"}},
        {"setVar": {"name": "kingWarned", "value": True}},
        {"setDisposition": {"actor": "hero", "to": "hostile"}},
    )
    assert "warned" in state.protagonist.flags
    assert state.variables["kingWarned"] is True
    assert state.protagonist.disposition == "hostile"


def test_moving_puts_the_player_somewhere_else(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    do(context, {"move": {"to": "castle"}})
    assert state.protagonist.location == "tiny:castle"
    assert "tiny:castle" in state.revealed


def test_advancing_time_moves_the_clock(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    outcome = do(context, {"advanceTime": {"ticks": 4}})
    assert state.tick == 4
    assert outcome.events[-1].payload()["elapsed"] == 4


def test_a_modifier_changes_a_stat_until_it_expires(tmp_path: Path) -> None:
    context, state, _library = playthrough(tmp_path)
    do(
        context,
        {
            "applyModifier": {
                "stat": "charisma",
                "add": 20,
                "ticks": 6,
                "label": "Bold",
            }
        },
    )
    assert ask(context, {"statAtLeast": {"stat": "charisma", "value": 50}})
    assert state.protagonist.modifiers[0].expires_at_tick == 6


def test_transferring_contents_empties_the_source(tmp_path: Path) -> None:
    context, state, _library = playthrough(
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
            {"id": "gold", "kind": "item", "name": "Gold"},
            {
                "id": "chest",
                "kind": "container",
                "name": "Chest",
                "inventory": [{"item": "gold", "qty": 40}],
            },
        ],
        locations=[
            {"id": "home", "name": "Home", "entities": ["chest"]},
            {"id": "castle", "name": "The Castle"},
        ],
        routes=[],
    )
    do(context, {"transferContents": {"from": "chest", "to": "hero"}})
    assert state.protagonist.inventory["tiny:gold"] == 40
    assert state.entities["tiny:chest"].inventory == {}


def test_effects_from_later_phases_say_so_rather_than_pretending(
    tmp_path: Path,
) -> None:
    context, _state, _library = playthrough(tmp_path)
    outcome = do(context, {"startCombat": {"against": "hero"}})
    assert outcome.events[0].record() == {
        "kind": "engine.unsupported",
        "feature": "startCombat",
        "arrives": "phase 3 — combat",
    }
