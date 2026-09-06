"""Character creation: the question, the answer, and what the answer does.

Creation is session setup rather than a turn, so these tests are about three
things — that the question a front-end is handed describes the content
faithfully, that an answer nobody could have typed is refused, and that the
answer lands in *state* and never in the pack.
"""

from pathlib import Path

import pytest

from mace.cli.create import parse_spend, summarise
from mace.content import ContentError, Library, load_library
from mace.engine.creation import Character, check, offer
from mace.engine.step import begin
from mace.model import Entity

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS = REPO_ROOT / "packs"
GAME = "peasants-quest"


@pytest.fixture(scope="module")
def library() -> Library:
    return load_library(PACKS)


def test_the_offer_describes_what_the_game_actually_has(library: Library) -> None:
    creation = offer(library, GAME)

    assert creation.asks_anything
    assert creation.points == 15
    assert [background.name for background in creation.backgrounds] == [
        "Farmhand",
        "Poacher",
        "Old Soldier",
    ]
    assert [stat.stat for stat in creation.stats] == [
        "strength",
        "speed",
        "endurance",
        "charisma",
        "stealth",
    ]


def test_a_background_is_offered_in_english_not_in_yaml(library: Library) -> None:
    """A front-end renders `grants`; it never reads a `Background`."""
    poacher = next(
        b for b in offer(library, GAME).backgrounds if b.id.endswith("poacher")
    )

    assert poacher.grants == (
        "stealth +15",
        "speed +5",
        "charisma −5",
        "rope",
        "dagger",
        "skilled with dagger (20)",
    )


def test_points_are_offered_against_the_stats_the_background_leaves_you(
    library: Library,
) -> None:
    """The poacher spends his last points looking at his stealth, not Letholin's."""
    plain = {stat.stat: stat.base for stat in offer(library, GAME).stats}
    poached = {
        stat.stat: stat.base
        for stat in offer(library, GAME, background="poacher").stats
    }

    assert plain["stealth"] == 18
    assert poached["stealth"] == 33
    assert poached["strength"] == plain["strength"]


def test_an_allocation_nobody_could_have_typed_is_refused(library: Library) -> None:
    creation = offer(library, GAME)

    assert check(creation, Character("poacher", {"stealth": 10})) == ()
    assert "not a background" in check(creation, Character("wizard"))[0]
    assert "creation points" in check(creation, Character("poacher", {"speed": 40}))[0]
    assert (
        "not customizable" in check(creation, Character("poacher", {"hitpoints": 5}))[0]
    )
    assert "pick a background" in check(creation, Character(None))[0]


def test_a_stat_cannot_be_pushed_past_its_own_cap(library: Library) -> None:
    """Spending is clamped, so points do not vanish into a stat that is full."""
    result = begin(library, GAME, character=Character("farmhand", {"strength": 15}))

    assert result.state.protagonist.pools["strength"] == 55  # 32 + 8 + 15


def test_a_background_lands_in_state_and_not_in_content(library: Library) -> None:
    result = begin(library, GAME, character=Character("poacher"))
    player = result.state.protagonist

    assert player.pools["stealth"] == 33
    assert player.inventory["fantasy.core:dagger"] == 1
    assert player.skills["fantasy.core:dagger"] == 20
    assert "knows-the-wood" in player.flags
    assert result.state.background == "peasants-quest:poacher"

    letholin = library.find("letholin", "entities", within=GAME)
    assert isinstance(letholin, Entity)
    assert (letholin.stats or {})["stealth"].base == 18


def test_creating_nobody_leaves_the_protagonist_as_authored(library: Library) -> None:
    """`character=None` is what a game with no creation question has always meant."""
    plain = begin(library, GAME)

    assert plain.state.background is None
    assert plain.state.protagonist.pools["stealth"] == 18
    assert not any(event.kind == "character.created" for event in plain.events)


def test_the_answer_is_announced_so_a_replay_can_carry_it(library: Library) -> None:
    result = begin(library, GAME, character=Character("old-soldier", {"speed": 4}))

    assert result.events[0].record() == {
        "kind": "character.created",
        "background": "peasants-quest:old-soldier",
        "spend": {"speed": 4},
    }


def test_an_illegal_allocation_stops_the_session_starting(library: Library) -> None:
    with pytest.raises(ContentError, match="creation points"):
        begin(library, GAME, character=Character("poacher", {"speed": 99}))


def test_spend_arguments_are_read_the_way_they_are_typed() -> None:
    assert parse_spend(["strength=5", "speed=10"]) == {"strength": 5, "speed": 10}
    with pytest.raises(ValueError, match="stat=points"):
        parse_spend(["strength"])


def test_an_allocation_reads_back_as_the_numbers_it_produced(
    library: Library,
) -> None:
    creation = offer(library, GAME, background="poacher")

    assert summarise(creation, {"stealth": 10}) == "stealth 43 — 5 points unspent."
    assert summarise(creation, {}) == "Nothing spent — 15 points unspent."
