"""Every condition and effect has to read as a sentence.

The wizard's promise is that an author builds a game and only sees YAML if they
go looking for it. That promise is exactly as good as this module's coverage of
the vocabulary, so the important test here is the one that fails when someone
adds a tag and forgets to say what it means.
"""

from pathlib import Path
from typing import Any

import pytest

from mace.content import load_library
from mace.model import Condition, Effect
from mace.model.conditions import CONDITION_PAYLOADS
from mace.model.effects import EFFECT_PAYLOADS
from mace.wizard.language import (
    Names,
    say_condition,
    say_conditions,
    say_effect,
    say_effects,
)

PACKS = Path(__file__).resolve().parent.parent / "packs"

#: One authored example per condition tag. Kept complete on purpose: the test
#: that walks it is what stops the vocabulary growing past the renderer.
CONDITIONS: dict[str, Any] = {
    "all": {"all": [{"season": ["autumn"]}, {"chance": 0.5}]},
    "any": {"any": [{"season": ["autumn"]}, {"chance": 0.5}]},
    "atLocation": {"atLocation": {"location": "fenmoor"}},
    "chance": {"chance": 0.15},
    "dayPart": {"dayPart": ["dawn", "day"]},
    "expr": {"expr": "world.day > 7"},
    "flag": {"flag": {"entity": "gorm", "flag": "has-been-paid"}},
    "hasItem": {"hasItem": {"item": "fantasy.core:gold", "qty": 10}},
    "not": {"not": {"chance": 0.5}},
    "priceOf": {"priceOf": {"good": "fantasy.core:grain", "above": 1.5}},
    "questComplete": {"questComplete": "the-kings-summons"},
    "questFailed": {"questFailed": "the-kings-summons"},
    "questStage": {"questStage": {"quest": "the-kings-summons", "stage": "set-out"}},
    "season": {"season": ["autumn"]},
    "statAtLeast": {"statAtLeast": {"stat": "strength", "value": 40}},
    "statAtMost": {"statAtMost": {"stat": "strength", "value": 40}},
    "weather": {"weather": ["rain"]},
    "weatherTag": {"weatherTag": ["wet"]},
}

#: One authored example per effect tag, for the same reason.
EFFECTS: dict[str, Any] = {
    "adjustStat": {"adjustStat": {"stat": "hitpoints", "delta": -8}},
    "advanceQuest": {"advanceQuest": {"quest": "the-kings-summons"}},
    "advanceTime": {"advanceTime": {"ticks": 4}},
    "applyModifier": {"applyModifier": {"stat": "speed", "add": 5, "ticks": 12}},
    "attachAlly": {"attachAlly": {"entity": "gorm"}},
    "closeRoute": {"closeRoute": "north-road"},
    "damage": {"damage": {"actor": "gorm", "amount": 8}},
    "dismissAlly": {"dismissAlly": {"entity": "gorm"}},
    "endGame": {"endGame": {}},
    "fireEvent": {"fireEvent": "the-kings-riders"},
    "giveItem": {"giveItem": {"item": "fantasy.core:gold", "qty": 4}},
    "marketShock": {
        "marketShock": {"category": "food", "mult": 2.5, "decayTicks": 600}
    },
    "move": {"move": {"to": "fenmoor"}},
    "openRoute": {"openRoute": "north-road"},
    "playScene": {"playScene": "victory"},
    "rest": {"rest": {"ticks": 8}},
    "restart": {"restart": {}},
    "reveal": {"reveal": {"location": "fenmoor"}},
    "setDisposition": {"setDisposition": {"actor": "gorm", "to": "friendly"}},
    "setFlag": {"setFlag": {"entity": "gorm", "flag": "has-spoken"}},
    "setLight": {"setLight": 0.2},
    "setPressure": {"setPressure": {"event": "the-storm", "value": 0.8}},
    "setRouteTicks": {"setRouteTicks": {"route": "north-road", "ticks": 12}},
    "setStat": {"setStat": {"stat": "hitpoints", "value": 50}},
    "setVar": {"setVar": {"name": "kingWarned", "value": True}},
    "spawnFront": {
        "spawnFront": {"front": "autumn-gale", "at": "the-lowlands"},
    },
    "startCombat": {"startCombat": {"against": ["gorm"]}},
    "takeItem": {"takeItem": {"item": "fantasy.core:gold", "qty": 10}},
    "tellNews": {"tellNews": 1},
    "transferContents": {"transferContents": {"from": "gorm", "to": "player"}},
}


@pytest.fixture(scope="module")
def names() -> Names:
    return Names(load_library(PACKS), "peasants-quest")


def test_every_condition_tag_has_an_example_here() -> None:
    """The table is the coverage, so the table has to stay complete."""
    assert set(CONDITIONS) == set(CONDITION_PAYLOADS)


def test_every_effect_tag_has_an_example_here() -> None:
    assert set(EFFECTS) == set(EFFECT_PAYLOADS)


@pytest.mark.parametrize("tag", sorted(CONDITIONS))
def test_every_condition_reads_as_english(tag: str, names: Names) -> None:
    said = say_condition(Condition.model_validate(CONDITIONS[tag]), names)

    assert said
    assert not said.startswith("["), (
        f"`{tag}` fell through to the argument dump. Give it a phrasing in "
        "mace.wizard.language.say_condition."
    )


@pytest.mark.parametrize("tag", sorted(EFFECTS))
def test_every_effect_reads_as_english(tag: str, names: Names) -> None:
    said = say_effect(Effect.model_validate(EFFECTS[tag]), names)

    assert said
    assert not said.startswith("["), (
        f"`{tag}` fell through to the argument dump. Give it a phrasing in "
        "mace.wizard.language.say_effect."
    )


def test_references_are_shown_by_the_name_the_author_gave_them(names: Names) -> None:
    condition = Condition.model_validate({"atLocation": {"location": "fenmoor"}})

    assert say_condition(condition, names) == "the player is at Fenmoor"


def test_a_reference_to_nothing_is_shown_as_written(names: Names) -> None:
    """A prettified dangling reference is a dangling reference nobody found."""
    condition = Condition.model_validate({"atLocation": {"location": "atlantis"}})

    assert say_condition(condition, names) == "the player is at atlantis"


def test_rendering_works_without_a_library_at_all() -> None:
    """An author mid-sentence still gets readable output from broken content."""
    condition = Condition.model_validate({"atLocation": {"location": "troll-bridge"}})

    assert say_condition(condition, Names()) == "the player is at troll bridge"


def test_a_stat_change_avoids_a_verb_that_cannot_agree(names: Names) -> None:
    """`hitpoints goes down` is wrong and `strength go down` is wrong."""
    effect = Effect.model_validate(
        {"adjustStat": {"stat": "hitpoints", "delta": -8, "reason": "the club"}}
    )

    assert say_effect(effect, names) == (
        "8 comes off the player's hitpoints (the club)"
    )


def test_nested_groups_read_as_one_sentence(names: Names) -> None:
    condition = Condition.model_validate(
        {
            "all": [
                {"hasItem": {"item": "fantasy.core:gold", "qty": 10}},
                {"not": {"flag": {"entity": "gorm", "flag": "has-been-paid"}}},
            ]
        }
    )

    assert say_condition(condition, names) == (
        "the player is carrying at least 10 Gold and "
        "not (Gorm is flagged `has-been-paid`)"
    )


def test_an_empty_list_says_what_empty_means(names: Names) -> None:
    assert say_conditions([], names) == "always"
    assert say_effects([], names) == "nothing happens"
