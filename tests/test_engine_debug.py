"""The debug overlay: a projection, and only a projection.

Two properties matter. It has to answer the questions an author actually asks
— why is that choice greyed out, what is acting on my speed, how close is that
table to firing. And watching must change nothing: a playthrough with the
overlay open has to produce the same events as one without it, or the overlay
is a second engine.
"""

from pathlib import Path

import pytest

from mace.content import Library, load_library
from mace.engine.actions import Choose
from mace.engine.debug import overlay
from mace.engine.step import StepResult, begin, step
from mace.wizard.language import Names, say_conditions

PACKS = Path(__file__).resolve().parent.parent / "packs"
GAME = "peasants-quest"


@pytest.fixture(scope="module")
def library() -> Library:
    return load_library(PACKS)


def at_the_bridge(library: Library) -> StepResult:
    """A session standing in front of the troll, mid-conversation.

    Returns
    -------
    StepResult
        The step whose pending choices are the troll's.
    """
    result = begin(library, GAME, seed="autumn", start_at="troll-bridge")
    for _ in range(6):
        pending = result.state.pending
        if pending and any("troll" in one.prompt.lower() for one in pending.options):
            index = next(
                number
                for number, one in enumerate(pending.options)
                if "troll" in one.prompt.lower()
            )
            return step(result.state, Choose(index), library)
        result = step(result.state, Choose(0), library)
    raise AssertionError("never reached the troll")  # pragma: no cover


def test_the_overlay_says_where_and_when_it_is(library: Library) -> None:
    seen = overlay(library, begin(library, GAME, seed="autumn").state)

    assert seen.day == 1
    assert seen.location == "peasants-quest:fenmoor"
    assert seen.region == "peasants-quest:the-lowlands"
    assert " at " in seen.weather


def test_it_says_why_a_choice_is_not_available(library: Library) -> None:
    """The engine records *whether*; an author needs *why not*."""
    result = at_the_bridge(library)
    seen = overlay(library, result.state)
    names = Names(library, GAME)

    said = {
        tested.subject: (say_conditions(tested.when, names), tested.holds)
        for tested in seen.conditions
    }
    assert "Pay the toll (10 gold)" in said
    phrase, holds = said["Pay the toll (10 gold)"]
    assert phrase == "the player is carrying at least 10 Gold"
    assert holds is False  # Letholin starts with four


def test_a_condition_that_cannot_be_asked_says_so_rather_than_reading_false(
    library: Library,
) -> None:
    """`false` and `this reference points at nothing` need different fixes."""
    from mace.engine.debug import _test
    from mace.engine.step import context_for
    from mace.model import Condition

    result = begin(library, GAME, seed="autumn")
    broken = (Condition.model_validate({"atLocation": {"location": "atlantis"}}),)
    tested = _test("go to Atlantis", broken, context_for(library, result.state))

    assert tested.holds is False
    assert tested.error is not None


def test_it_shows_what_is_acting_on_a_stat(library: Library) -> None:
    result = begin(library, GAME, seed="autumn", start_at="troll-bridge")
    result = step(result.state, Choose(0), library)
    seen = overlay(library, result.state)

    for modifier in seen.modifiers:
        assert modifier.source, "a modifier with no source is not worth showing"


def test_it_shows_where_the_random_streams_have_got_to(library: Library) -> None:
    seen = overlay(library, begin(library, GAME, seed="autumn").state)

    assert seen.streams
    assert all(position >= 0 for _name, position in seen.streams)


def test_watching_changes_nothing(library: Library) -> None:
    """Same seed, same actions, same events — overlay or no overlay."""
    watched = begin(library, GAME, seed="autumn")
    quiet = begin(library, GAME, seed="autumn")

    for _ in range(4):
        overlay(library, watched.state)
        watched = step(watched.state, Choose(0), library)
        quiet = step(quiet.state, Choose(0), library)

    assert watched.records() == quiet.records()


def test_an_engine_menu_has_no_authored_conditions_to_show(library: Library) -> None:
    """The travel menu is the engine's own; there is no `when` behind it."""
    seen = overlay(library, begin(library, GAME, seed="autumn").state)

    assert seen.conditions == ()
