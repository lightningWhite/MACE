"""The view-model: what a front-end may look at that no event carries.

Two things are being tested. That the projection says what is true — the pack,
the sheet, the journal, the map — and that it says nothing else: fog of war is
applied here, not left to a client to apply politely.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Choose
from mace.engine.state import Journey, QuestState, QuestStatus, RouteState
from mace.session import Session

# ── A world worth drawing ─────────────────────────────────────────────────────

WORLD: dict[str, Any] = {
    "entities": [
        {
            "id": "hero",
            "kind": "actor",
            "name": "Hero",
            "playable": True,
            "stats": {
                "hitpoints": {"base": 18, "max": 20},
                "stamina": {"base": 7, "max": 10},
                "strength": {"base": 32},
            },
            "inventory": [{"item": "gold", "qty": 5}, {"item": "bread", "qty": 2}],
        },
        {"id": "gold", "kind": "item", "name": "Gold", "item": {"baseValue": 1}},
        {"id": "bread", "kind": "item", "name": "Bread"},
    ],
    "locations": [
        {
            "id": "home",
            "name": "Home",
            "description": "A well.",
            "mapPosition": {"x": 0, "y": 100},
            "exits": [{"to": "mill", "route": "lane"}, {"to": "castle", "route": "road"}],
        },
        {
            "id": "mill",
            "name": "The Mill",
            "mapPosition": {"x": -40, "y": 60},
            "exits": [{"to": "home", "route": "lane"}],
        },
        {"id": "castle", "name": "The Castle", "mapPosition": {"x": 30, "y": 0}},
        {"id": "cave", "name": "The Cave", "visible": False},
    ],
    "routes": [
        {"id": "lane", "from": "home", "to": "mill", "ticks": 2},
        {"id": "road", "from": "home", "to": "castle", "ticks": 6},
        {"id": "tunnel", "from": "mill", "to": "cave", "ticks": 9},
    ],
    "quests": [
        {
            "id": "the-summons",
            "name": "The Summons",
            "summary": "Reach the castle.",
            "stages": [
                {
                    "id": "walk",
                    "journal": "The road north is six ticks of mud.",
                    "complete": [{"atLocation": {"location": "castle"}}],
                }
            ],
        }
    ],
}


def opened(root: Path, **kwargs: Any) -> Session:
    """Open a session on a world with a map, a pack, and a quest.

    Parameters
    ----------
    root : Path
        Directory to create the pack under.
    **kwargs
        Passed to `Session.begin`.

    Returns
    -------
    Session
        The session, standing at home.
    """
    game_pack(root, game={"quests": ["the-summons"]}, world=WORLD)
    return Session.begin(load_library(root), "tiny", **kwargs)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    """A session on that world.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    Session
        The session.
    """
    return opened(tmp_path / "packs")


# ── The character panel ───────────────────────────────────────────────────────


def test_the_sheet_is_who_the_player_is(session: Session) -> None:
    sheet = session.view().sheet
    assert sheet.name == "Hero"
    assert sheet.entity == session.state.player
    assert sheet.exposure == 0.0


def test_the_vital_and_effort_pools_are_named_by_the_rules(session: Session) -> None:
    """A front-end should not have to know that hitpoints go beside a heart."""
    roles = {gauge.stat: gauge.role for gauge in session.view().sheet.stats}
    assert roles == {
        "hitpoints": "vital",
        "stamina": "effort",
        "strength": "ability",
    }


def test_the_pools_come_first(session: Session) -> None:
    assert [gauge.stat for gauge in session.view().sheet.stats] == [
        "hitpoints",
        "stamina",
        "strength",
    ]


def test_a_stat_nobody_capped_reports_no_cap(session: Session) -> None:
    """`26/100` beside a stat nobody capped is a scale the front-end invented."""
    caps = {gauge.stat: gauge.maximum for gauge in session.view().sheet.stats}
    assert caps == {"hitpoints": 20.0, "stamina": 10.0, "strength": None}


def test_a_gauge_reads_what_the_stat_is_worth_now(session: Session) -> None:
    gauges = {gauge.stat: gauge.value for gauge in session.view().sheet.stats}
    assert gauges["hitpoints"] == 18.0
    assert gauges["strength"] == 32.0


# ── The pack ──────────────────────────────────────────────────────────────────


def test_the_pack_names_what_is_in_it(session: Session) -> None:
    assert [(stack.name, stack.qty) for stack in session.view().carried] == [
        ("Bread", 2),
        ("Gold", 5),
    ]


def test_an_item_carries_its_price_anchor(session: Session) -> None:
    priced = {stack.name: stack.value for stack in session.view().carried}
    assert priced == {"Bread": None, "Gold": 1.0}


def test_a_stack_spent_to_nothing_is_not_carried(session: Session) -> None:
    session.state.protagonist.inventory["tiny:gold"] = 0
    assert [stack.name for stack in session.view().carried] == ["Bread"]


# ── The journal ───────────────────────────────────────────────────────────────


def test_the_journal_reads_the_current_stage(session: Session) -> None:
    (entry,) = session.view().journal
    assert entry.name == "The Summons"
    assert entry.summary == "Reach the castle."
    assert entry.status == "active"
    assert entry.journal == "The road north is six ticks of mud."


def test_a_hidden_quest_is_not_in_the_journal(session: Session) -> None:
    """A greyed-out `??? — hidden` line is most of the secret."""
    session.state.quests["tiny:the-summons"] = QuestState(
        quest="tiny:the-summons", status=QuestStatus.HIDDEN
    )
    assert session.view().journal == ()


def test_the_journal_puts_what_is_live_first(session: Session) -> None:
    session.state.quests["tiny:done"] = QuestState(
        quest="tiny:done", status=QuestStatus.COMPLETE
    )
    session.state.quests["tiny:lost"] = QuestState(
        quest="tiny:lost", status=QuestStatus.FAILED
    )
    assert [entry.status for entry in session.view().journal] == [
        "active",
        "complete",
        "failed",
    ]


# ── The map ───────────────────────────────────────────────────────────────────


def test_the_map_knows_where_you_are_standing(session: Session) -> None:
    atlas = session.view().atlas
    assert atlas.here == "tiny:home"
    standing = {place.location: place.standing for place in atlas.places}
    assert standing["tiny:home"] == "here"


def test_somewhere_only_heard_of_is_not_somewhere_you_have_been(
    session: Session,
) -> None:
    standing = {
        place.location: place.standing for place in session.view().atlas.places
    }
    assert standing["tiny:castle"] == "known"

    session.perform(Choose(session.offered.index("Travel to The Castle")))
    walked = {
        place.location: place.standing for place in session.view().atlas.places
    }
    assert walked["tiny:castle"] == "here"
    assert walked["tiny:home"] == "visited"


def test_a_place_nobody_has_heard_of_is_not_on_the_map(session: Session) -> None:
    """Fog of war is applied here, not left to a client to apply politely."""
    drawn = {place.location for place in session.view().atlas.places}
    assert "tiny:cave" not in drawn


def test_a_road_to_nowhere_known_is_not_drawn(session: Session) -> None:
    """An arrow into the fog points at the thing the fog is withholding."""
    drawn = {road.route for road in session.view().atlas.roads}
    assert drawn == {"tiny:lane", "tiny:road"}


def test_a_road_carries_its_length_and_its_ends(session: Session) -> None:
    (road,) = [
        one for one in session.view().atlas.roads if one.route == "tiny:road"
    ]
    assert (road.origin, road.destination, road.ticks) == (
        "tiny:home",
        "tiny:castle",
        6,
    )


def test_a_road_something_has_lengthened_reports_its_new_length(
    session: Session,
) -> None:
    session.state.routes["tiny:road"] = RouteState(route="tiny:road", ticks=11)
    lengths = {road.route: road.ticks for road in session.view().atlas.roads}
    assert lengths["tiny:road"] == 11


def test_a_road_that_is_shut_says_so_and_why(session: Session) -> None:
    session.state.routes["tiny:road"] = RouteState(
        route="tiny:road", closed=True, reason="The bridge is out."
    )
    (road,) = [
        one for one in session.view().atlas.roads if one.route == "tiny:road"
    ]
    assert road.closed
    assert road.reason == "The bridge is out."


def test_the_map_carries_authored_coordinates(session: Session) -> None:
    placed = {
        place.location: (place.x, place.y) for place in session.view().atlas.places
    }
    assert placed["tiny:home"] == (0.0, 100.0)
    assert placed["tiny:castle"] == (30.0, 0.0)


def test_a_road_part_walked_shows_how_far(session: Session) -> None:
    session.state.journey = Journey(
        route="tiny:road", origin="tiny:home", destination="tiny:castle", progress=2.5
    )
    journey = session.view().atlas.journey
    assert journey is not None
    assert (journey.walked, journey.ticks) == (2.5, 6)
    assert journey.destination == "tiny:castle"


# ── What a projection may not do ──────────────────────────────────────────────


def standing(session: Session) -> tuple[Any, ...]:
    """Everything about a playthrough that a projection must not touch.

    The weather is the one worth naming: reading a region's sky could
    plausibly fast-forward its Markov chain, and a map that steps the weather
    by being opened is a map that changes the game.

    Parameters
    ----------
    session : Session
        The playthrough.

    Returns
    -------
    tuple
        A comparable snapshot.
    """
    state = session.state
    return (
        state.tick,
        state.world_tick,
        repr(sorted(state.weather.items())),
        tuple(sorted(state.revealed)),
        tuple(sorted(state.visited)),
        state.rng.snapshot(),
    )


def test_looking_at_the_world_does_not_change_it(session: Session) -> None:
    """A playthrough with the map open has to replay like one without it."""
    before = standing(session)
    session.view()
    session.view()
    assert standing(session) == before


def test_the_view_goes_over_the_wire(session: Session) -> None:
    import json

    written = json.loads(json.dumps(session.view().record()))
    assert written["pack"] == "tiny"
    assert written["outcome"] == "playing"
    assert written["sheet"]["name"] == "Hero"
    assert written["atlas"]["here"] == "tiny:home"
    assert written["atlas"]["roads"][0]["from"] == "tiny:home"
