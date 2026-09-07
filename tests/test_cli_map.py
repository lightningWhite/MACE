"""The map, drawn in characters.

The terminal is the client that keeps the project honest: anything it can draw
is provably engine data. So these tests check the drawing, and check that the
drawing never knows more than the atlas handed it.
"""

from pathlib import Path

import pytest

from conftest import game_pack
from mace.cli.map import GLYPHS, draw
from mace.content import load_library
from mace.engine.actions import Choose
from mace.engine.state import Journey, RouteState
from mace.session import Atlas, Session
from test_session_view import WORLD


@pytest.fixture
def session(tmp_path: Path) -> Session:
    """A session on a world with authored map positions.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    Session
        The session, standing at home.
    """
    game_pack(tmp_path / "packs", game={"quests": ["the-summons"]}, world=WORLD)
    return Session.begin(load_library(tmp_path / "packs"), "tiny")


def drawn(session: Session) -> str:
    """The map as one block of text.

    Parameters
    ----------
    session : Session
        The playthrough.

    Returns
    -------
    str
        Every line, newline-joined.
    """
    return "\n".join(draw(session.view().atlas))


# ── The plot ──────────────────────────────────────────────────────────────────


def test_the_map_names_the_places_you_know(session: Session) -> None:
    text = drawn(session)
    assert "Home" in text
    assert "The Mill" in text
    assert "The Castle" in text


def test_the_map_does_not_name_a_place_you_have_not_heard_of(
    session: Session,
) -> None:
    assert "The Cave" not in drawn(session)


def test_where_you_are_is_a_different_shape(session: Session) -> None:
    """Three shapes rather than three colors, so the map stays legible."""
    text = drawn(session)
    assert f"{GLYPHS['here']} Home" in text
    assert f"{GLYPHS['known']} The Castle" in text

    session.perform(Choose(session.offered.index("Travel to The Castle")))
    walked = drawn(session)
    assert f"{GLYPHS['here']} The Castle" in walked
    assert f"{GLYPHS['visited']} Home" in walked


def test_a_road_is_drawn_with_its_length_on_it(session: Session) -> None:
    plotted = drawn(session).splitlines()[0:12]
    assert any("6" in line for line in plotted)
    assert any("╱" in line or "╲" in line or "─" in line for line in plotted)


def test_the_legend_says_what_the_shapes_mean(session: Session) -> None:
    assert "● here" in drawn(session)


# ── The listing under it ──────────────────────────────────────────────────────


def test_the_roads_from_here_carry_their_length_and_their_weather(
    session: Session,
) -> None:
    text = drawn(session)
    assert "6 ticks  The Castle" in text
    assert "2 ticks  The Mill" in text


def test_a_road_that_is_shut_says_so(session: Session) -> None:
    session.state.routes["tiny:road"] = RouteState(route="tiny:road", closed=True)
    assert "(closed)" in drawn(session)


def test_somewhere_with_no_road_from_here_is_still_listed(session: Session) -> None:
    session.perform(Choose(session.offered.index("Travel to The Mill")))
    text = drawn(session)
    assert "Elsewhere you know of:" in text
    assert "The Castle" in text.split("Elsewhere you know of:")[1]


def test_a_road_part_walked_says_how_far(session: Session) -> None:
    session.state.journey = Journey(
        route="tiny:road", origin="tiny:home", destination="tiny:castle", progress=2.0
    )
    assert "On the road to The Castle — 2 of 6 ticks walked." in drawn(session)


# ── Maps that cannot be plotted ───────────────────────────────────────────────


def test_a_world_with_no_coordinates_still_gets_a_map(tmp_path: Path) -> None:
    """`mapPosition` is optional, and a listing is more use than nothing."""
    game_pack(tmp_path / "packs")
    session = Session.begin(load_library(tmp_path / "packs"), "tiny")
    text = "\n".join(draw(session.view().atlas))
    assert "6 ticks  The Castle" in text
    assert "●" not in text


def test_knowing_nowhere_at_all_says_so() -> None:
    empty = Atlas(here=None, places=(), roads=(), journey=None)
    assert draw(empty) == ["  You have no idea where you are."]


def test_the_plot_never_runs_past_its_own_width(session: Session) -> None:
    for line in draw(session.view().atlas):
        assert len(line) <= 70
