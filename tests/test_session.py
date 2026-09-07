"""The session layer: a playthrough held open, and written down.

A save is the recipe, not the photograph — packs and versions, the seed, and
the ordered log of what the player did. So the interesting tests are all about
what happens when the content moves underneath one.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack, write_pack
from mace.content import ContentError, load_library
from mace.engine.actions import Choose, Wait
from mace.engine.creation import Character
from mace.session import (
    FORMAT,
    Save,
    SaveError,
    Session,
    choose_game,
    load,
    read,
    resume,
)
from mace.session import write as write_save

# ── A world with a fork in it ─────────────────────────────────────────────────


def forked(root: Path, *, first: str = "castle") -> Path:
    """Write a game whose start location has two roads out of it.

    Two exits mean a menu with an order, which is what a save recorded by
    prompt has to survive being changed.

    Parameters
    ----------
    root : Path
        Directory to create the pack under.
    first : str
        Which exit is listed first — `castle` or `mill`.

    Returns
    -------
    Path
        The pack directory.
    """
    exits = [
        {"to": "castle", "route": "road"},
        {"to": "mill", "route": "lane"},
    ]
    if first == "mill":
        exits.reverse()

    return game_pack(
        root,
        world={
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "description": "A well.",
                    "exits": exits,
                },
                {"id": "castle", "name": "The Castle"},
                {"id": "mill", "name": "The Mill"},
            ],
            "routes": [
                {"id": "road", "from": "home", "to": "castle", "ticks": 6},
                {"id": "lane", "from": "home", "to": "mill", "ticks": 2},
            ],
        },
    )


def opened(root: Path, **kwargs: Any) -> Session:
    """Load a forked game and open a session on it.

    Parameters
    ----------
    root : Path
        Directory to create the pack under.
    **kwargs
        Passed to `forked`.

    Returns
    -------
    Session
        The session, at the fork.
    """
    forked(root, **kwargs)
    return Session.begin(load_library(root), "tiny")


# ── Holding a game open ───────────────────────────────────────────────────────


def test_a_session_opens_with_the_events_that_opened_it(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    assert session.playing
    assert "choices" in {event.kind for event in session.events}


def test_a_session_offers_the_prompts_that_are_pending(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    assert session.offered == ("Travel to The Castle", "Travel to The Mill")


def test_nothing_is_offered_when_nothing_is_pending(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    session.perform(Choose(0))
    assert not session.playing
    assert session.offered == ()


def test_a_session_remembers_every_action_in_order(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    session.perform(Wait(ticks=1))
    session.perform(Choose(1))
    assert session.log == [
        {"kind": "wait", "ticks": 1},
        {"kind": "choose", "prompt": "Travel to The Mill"},
    ]


def test_a_choice_the_menu_does_not_hold_records_as_an_index(tmp_path: Path) -> None:
    """An out-of-range choice is the engine's to complain about, not the log's."""
    session = opened(tmp_path / "packs")
    assert session.record_of(Choose(9)) == {"kind": "choose", "option": 9}


# ── Which game ────────────────────────────────────────────────────────────────


def test_the_only_game_loaded_needs_no_naming(tmp_path: Path) -> None:
    forked(tmp_path / "packs")
    assert choose_game(load_library(tmp_path / "packs")) == "tiny"


def test_several_games_have_to_be_told_apart(tmp_path: Path) -> None:
    forked(tmp_path / "packs")
    game_pack(tmp_path / "packs", pack_id="other")
    with pytest.raises(ContentError, match="several games"):
        choose_game(load_library(tmp_path / "packs"))


def test_no_game_at_all_says_what_a_game_pack_is(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "library-only")
    with pytest.raises(ContentError, match="kind: game"):
        choose_game(load_library(tmp_path / "packs"))


# ── The round trip ────────────────────────────────────────────────────────────


def test_a_save_replays_to_where_it_was_written(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    session.perform(Wait(ticks=2))
    session.perform(Choose(1))

    library = session.library
    resumed, drift = load(write_save(session, tmp_path / "save.json"), library)

    assert not drift
    assert resumed.state.location == session.state.location
    assert resumed.state.tick == session.state.tick
    assert resumed.log == session.log


def test_a_save_carries_the_character_that_was_made(tmp_path: Path) -> None:
    game_pack(
        tmp_path / "packs",
        game={
            "player": {
                "entity": "hero",
                "startLocation": "home",
                "creationPoints": 2,
            }
        },
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {
                        "hitpoints": {"base": 20, "max": 30, "customizable": True},
                    },
                }
            ]
        },
    )
    library = load_library(tmp_path / "packs")
    session = Session.begin(
        library,
        "tiny",
        seed="north",
        combat_mode="tactical",
        character=Character(background=None, spend={"hitpoints": 2}),
    )
    resumed, _ = load(write_save(session, tmp_path / "save.json"), library)

    assert resumed.seed == "north"
    assert resumed.combat_mode == "tactical"
    assert resumed.character == session.character
    assert resumed.state.protagonist.pools == session.state.protagonist.pools


def test_a_save_records_the_packs_it_was_played_against(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    assert Save.of(session).packs == {"tiny": "0.1.0"}


def test_a_save_reads_as_prose(tmp_path: Path) -> None:
    """It has to fit in a bug report, so it is a list of things a person did."""
    session = opened(tmp_path / "packs")
    session.perform(Choose(1))
    record = Save.of(session).record()

    assert record["format"] == FORMAT
    assert record["pack"] == "tiny"
    assert record["actions"] == [{"kind": "choose", "prompt": "Travel to The Mill"}]


# ── Content that moved underneath ─────────────────────────────────────────────


def test_a_menu_entry_inserted_above_does_not_redirect_a_save(tmp_path: Path) -> None:
    """The whole reason a choice is written down by prompt and not by index."""
    session = opened(tmp_path / "packs")
    session.perform(Choose(0))
    path = write_save(session, tmp_path / "save.json")

    forked(tmp_path / "moved", first="mill")
    resumed, _ = load(path, load_library(tmp_path / "moved"))

    assert resumed.state.location == session.state.location


def test_a_save_that_stops_fitting_says_at_which_action(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    session.perform(Wait(ticks=1))
    session.perform(Choose(0))
    path = write_save(session, tmp_path / "save.json")

    game_pack(
        tmp_path / "gone",
        world={
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "exits": [{"to": "mill", "route": "lane"}],
                },
                {"id": "castle", "name": "The Castle"},
                {"id": "mill", "name": "The Mill"},
            ],
            "routes": [{"id": "lane", "from": "home", "to": "mill", "ticks": 2}],
        },
    )
    with pytest.raises(SaveError, match="action 2") as raised:
        load(path, load_library(tmp_path / "gone"))
    assert "Travel to The Castle" in str(raised.value)
    assert "Travel to The Mill" in str(raised.value)


def test_a_pack_that_moved_since_the_save_is_worth_saying(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    session.perform(Wait(ticks=1))
    path = write_save(session, tmp_path / "save.json")

    manifest = tmp_path / "packs" / "tiny" / "pack.yml"
    manifest.write_text(manifest.read_text().replace("0.1.0", "0.2.0"))

    _, drift = load(path, load_library(tmp_path / "packs"))
    assert drift == ["`tiny` was 0.1.0 when this was saved, and is now 0.2.0"]


def test_a_pack_that_is_no_longer_loaded_is_worth_saying(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    written = Save.of(session).record()
    written["packs"] = {**written["packs"], "ghost": "0.1.0"}

    _, drift = resume(Save.restore(written), session.library)
    assert drift == ["`ghost` 0.1.0 is not loaded now"]


def test_a_save_of_a_game_that_is_not_loaded_cannot_be_opened(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    path = write_save(session, tmp_path / "save.json")

    game_pack(tmp_path / "elsewhere", pack_id="different")
    with pytest.raises(SaveError, match="cannot be opened"):
        load(path, load_library(tmp_path / "elsewhere"))


# ── Files that are not saves ──────────────────────────────────────────────────


def test_a_save_from_a_newer_engine_says_so(tmp_path: Path) -> None:
    with pytest.raises(SaveError, match="newer MACE"):
        Save.restore({"format": FORMAT + 1, "pack": "tiny"})


def test_a_save_that_does_not_name_a_game_is_refused() -> None:
    with pytest.raises(SaveError, match="which game"):
        Save.restore({"format": FORMAT, "seed": "mace"})


def test_a_save_whose_actions_are_not_a_list_is_refused() -> None:
    with pytest.raises(SaveError, match="must be a list"):
        Save.restore({"pack": "tiny", "actions": {"kind": "wait"}})


def test_a_missing_save_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(SaveError, match="could not read"):
        read(tmp_path / "nowhere.json")


def test_a_file_that_is_not_json_is_not_a_save(tmp_path: Path) -> None:
    path = tmp_path / "save.json"
    path.write_text("this is a diary, not a save")
    with pytest.raises(SaveError, match="not a save file"):
        read(path)


def test_json_that_is_not_an_object_is_not_a_save(tmp_path: Path) -> None:
    path = tmp_path / "save.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(SaveError, match="not an object"):
        read(path)


def test_a_save_that_cannot_be_written_says_where(tmp_path: Path) -> None:
    session = opened(tmp_path / "packs")
    blocked = tmp_path / "packs" / "tiny" / "pack.yml" / "save.json"
    with pytest.raises(SaveError, match="could not write"):
        write_save(session, blocked)
