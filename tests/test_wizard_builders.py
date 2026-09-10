"""The cascade that replaced `defineConditions()`.

The test that matters most is coverage: a tag with no recipe is a thing an
author has to hand-write YAML for, which is exactly what the builder exists to
prevent. The rest check that what the cascade produces is valid content, and
that it is the *smallest* valid content — a file full of `actor: player` that
nobody typed is a file that is harder to read than it needs to be.
"""

from typing import Any

import pytest

from mace.model import Condition, Effect
from mace.model.conditions import CONDITION_PAYLOADS
from mace.model.effects import EFFECT_PAYLOADS
from mace.wizard.builders import (
    CONDITIONS,
    EFFECTS,
    Recipe,
    build_condition,
    build_effect,
    recipe_for,
)

#: Answers good enough to build each condition, by tag. Only the tags whose
#: required questions cannot be guessed need an entry; the rest build from
#: their own defaults.
CONDITION_ANSWERS: dict[str, dict[str, Any]] = {
    "hasItem": {"item": "gold"},
    "atLocation": {"location": "home"},
    "statAtLeast": {"stat": "strength", "value": 40},
    "statAtMost": {"stat": "stamina", "value": 5},
    "flag": {"entity": "gorm", "flag": "has-spoken"},
    "weather": {"": ["rain"]},
    "weatherTag": {"": ["wet"]},
    "season": {"": ["autumn"]},
    "dayPart": {"": ["dawn"]},
    "questComplete": {"": "the-summons"},
    "questFailed": {"": "the-summons"},
    "questStage": {"quest": "the-summons", "stage": "set-out"},
    "chance": {"": 0.15},
    "all": {"": [{"chance": 0.5}, {"season": ["autumn"]}]},
    "any": {"": [{"chance": 0.5}, {"season": ["autumn"]}]},
    "not": {"": {"chance": 0.5}},
    "expr": {"": "world.day > 7"},
    "priceOf": {"good": "grain", "above": 1.5},
}

#: The same, for effects.
EFFECT_ANSWERS: dict[str, dict[str, Any]] = {
    "giveItem": {"item": "gold"},
    "takeItem": {"item": "gold"},
    "transferContents": {"from": "gorm"},
    "setDisposition": {"actor": "gorm", "to": "friendly"},
    "adjustStat": {"stat": "hitpoints", "delta": -8},
    "setStat": {"stat": "hitpoints", "value": 20},
    "applyModifier": {"stat": "speed", "add": 5, "ticks": 12},
    "damage": {"amount": 8},
    "rest": {},
    "marketShock": {"mult": 2.5, "decayTicks": 600},
    "move": {"to": "home"},
    "reveal": {"location": "castle"},
    "advanceTime": {"ticks": 4},
    "closeRoute": {"route": "road"},
    "openRoute": {"": "road"},
    "setRouteTicks": {"route": "road", "ticks": 12},
    "setLight": {"": 0.2},
    "spawnEntity": {"entity": "gorm"},
    "spawnFront": {"front": "gale", "at": "lowlands"},
    "startCombat": {"against": ["gorm"]},
    "attachAlly": {"entity": "gorm"},
    "dismissAlly": {"entity": "gorm"},
    "advanceQuest": {"quest": "the-summons"},
    "setFlag": {"entity": "gorm", "flag": "has-spoken"},
    "setVar": {"name": "kingWarned", "value": "yes"},
    "say": {"": "The troll grunts."},
    "playScene": {"": "victory"},
    "fireEvent": {"": "the-storm"},
    "setPressure": {"event": "the-storm", "value": 0.8},
    "tellNews": {},
    "endGame": {},
    "restart": {},
}


def test_every_condition_can_be_built() -> None:  # noqa: D103 — the assert says it
    assert {recipe.tag for recipe in CONDITIONS} == set(CONDITION_PAYLOADS), (
        "a condition tag with no recipe is one an author has to hand-write "
        "YAML for. Add it to mace.wizard.builders.CONDITIONS."
    )


def test_every_effect_can_be_built() -> None:
    assert {recipe.tag for recipe in EFFECTS} == set(EFFECT_PAYLOADS), (
        "an effect tag with no recipe is one an author has to hand-write YAML "
        "for. Add it to mace.wizard.builders.EFFECTS."
    )


def test_the_answer_tables_here_stay_complete() -> None:
    assert set(CONDITION_ANSWERS) == set(CONDITION_PAYLOADS)
    assert set(EFFECT_ANSWERS) == set(EFFECT_PAYLOADS)


@pytest.mark.parametrize("tag", sorted(CONDITION_ANSWERS))
def test_a_built_condition_is_valid_content(tag: str) -> None:
    built = build_condition(recipe_for(tag, CONDITIONS), CONDITION_ANSWERS[tag])

    assert Condition.model_validate(built).tag == tag


@pytest.mark.parametrize("tag", sorted(EFFECT_ANSWERS))
def test_a_built_effect_is_valid_content(tag: str) -> None:
    built = build_effect(recipe_for(tag, EFFECTS), EFFECT_ANSWERS[tag])

    assert Effect.model_validate(built).tag == tag


def test_defaults_the_author_never_typed_do_not_reach_the_file() -> None:
    """The cascade fills `actor: player` in; the file should not carry it."""
    built = build_condition(
        recipe_for("hasItem", CONDITIONS), {"item": "fantasy.core:gold", "qty": 10}
    )

    assert built == {"hasItem": {"item": "fantasy.core:gold", "qty": 10}}


def test_a_one_argument_tag_is_written_without_a_wrapper() -> None:
    assert build_condition(recipe_for("chance", CONDITIONS), {"": 0.15}) == {
        "chance": 0.15
    }


def test_a_recipe_that_asks_nothing_still_produces_content() -> None:
    assert build_effect(recipe_for("endGame", EFFECTS), {}) == {"endGame": {}}


def test_an_incomplete_answer_is_refused_with_the_models_own_message() -> None:
    with pytest.raises(ValueError, match="value"):
        build_condition(recipe_for("statAtLeast", CONDITIONS), {"stat": "strength"})


def test_nothing_builds_a_tag_that_does_not_exist() -> None:
    with pytest.raises(KeyError, match="dazzle"):
        recipe_for("dazzle", CONDITIONS)


def test_every_recipe_is_offered_under_a_heading() -> None:
    """A flat list of twenty-nine effects is not a menu anybody can read."""
    for recipe in (*CONDITIONS, *EFFECTS):
        assert recipe.group, f"`{recipe.tag}` has no group"
        assert recipe.label
        assert not recipe.label.startswith(recipe.tag), (
            f"`{recipe.tag}` is labelled with its own tag. Label it with the "
            "thing the author is thinking about."
        )


def test_recipes_that_ask_one_bare_question_say_so() -> None:
    bare = [recipe for recipe in (*CONDITIONS, *EFFECTS) if recipe.bare is not None]

    assert bare
    for recipe in bare:
        assert len(recipe.asks) == 1


def test_a_recipe_leaves_out_what_it_was_not_told() -> None:
    sparse = Recipe(label="x", tag="rest", group="g")

    assert sparse.build({}) == {"rest": {}}
