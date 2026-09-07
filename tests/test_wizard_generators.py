"""Scaffolding: it has to be real content, and it has to be leaveable.

Two things make a generator worth having rather than a novelty. What it
produces must *validate* — a starter map that opens with five notes is a worse
start than an empty file. And it must be made of things that exist: entries
borrowed from the loaded libraries, not invented references an author then has
to go and define.
"""

import shutil
from pathlib import Path

import pytest

from conftest import write_pack
from mace.content import load_library
from mace.content.validation import Severity, validate_library
from mace.wizard.generators import (
    FLAVOURS,
    PRESETS,
    start_world,
    suggest_table,
)
from mace.wizard.project import Project

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS = REPO_ROOT / "packs"


@pytest.fixture
def blank(tmp_path: Path) -> Project:
    """A new game pack that builds on the real libraries."""
    for library in ("fantasy.core", "mace.core"):
        shutil.copytree(PACKS / library, tmp_path / library)
    return Project.create(
        tmp_path / "world",
        tmp_path,
        pack_id="world",
        name="World",
        requires={"fantasy.core": "^0.1"},
    )


def playable(project: Project) -> None:
    """Give a scaffolded pack the protagonist and manifest a game needs.

    The starter map is the map and nothing else, so a pack that has only been
    scaffolded is a game pack with no game in it — which the validator says,
    correctly, and which would drown out everything these tests are looking
    for.

    Parameters
    ----------
    project : Project
        The pack, edited in place.
    """
    somewhere = project.ids("locations")[0]
    project.put(
        "entities",
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
    )
    project.set_game(
        {
            "name": "World",
            "player": {"entity": "hero", "startLocation": somewhere},
            "winConditions": [{"atLocation": {"location": somewhere}}],
        }
    )


def test_a_starter_map_is_content_that_validates(blank: Project) -> None:
    """Nothing broken, and nothing the author has to guess at.

    The one thing it *does* leave behind is a note per road saying it has a
    `dangerLevel` and no encounter table — which is the next thing to do and
    the next generator along, rather than a defect.
    """
    made = start_world(blank, size="small", seed="one")
    playable(blank)

    assert made
    about_the_map = [
        problem
        for problem in blank.report().problems
        if problem.collection in {"locations", "routes", "regions"}
    ]
    assert [one for one in about_the_map if one.severity is not Severity.NOTE] == []
    assert all("encounter table" in one.message for one in about_the_map)


def test_every_place_it_makes_can_be_left(blank: Project) -> None:
    """A map of places nobody can walk out of is worse than a blank file."""
    start_world(blank, size="medium", seed="one")

    for local_id in blank.ids("locations"):
        body = blank.get("locations", local_id) or {}
        assert body.get("exits"), f"{local_id} has no way out"


def test_the_same_seed_makes_the_same_map(tmp_path: Path, blank: Project) -> None:
    """ "Give me another one" is a different seed, not a dice roll."""
    once = start_world(blank, seed="one")
    twice = start_world(
        Project.create(tmp_path / "again", tmp_path, pack_id="again", name="Again"),
        seed="one",
    )

    assert once == twice


def test_a_different_seed_makes_a_different_map(tmp_path: Path, blank: Project) -> None:
    other = Project.create(tmp_path / "other", tmp_path, pack_id="other", name="Other")

    assert start_world(blank, seed="one") != start_world(other, seed="two")


def test_it_never_overwrites_what_is_already_there(blank: Project) -> None:
    blank.put("locations", {"id": "market-cross", "name": "Mine, actually"})
    start_world(blank, seed="one")

    assert dict(blank.get("locations", "market-cross") or {})["name"] == (
        "Mine, actually"
    )


def test_every_flavour_makes_a_map_of_the_same_shape(tmp_path: Path) -> None:
    """A flavour is a naming palette. The shape is not a genre idea."""
    shapes = []
    for flavour in FLAVOURS:
        project = Project.create(
            tmp_path / flavour.id, tmp_path, pack_id=flavour.id, name=flavour.id
        )
        made = start_world(project, flavour=flavour.id, size="medium", seed="one")
        shapes.append([one.split("/")[0] for one in made])

    assert len(set(map(tuple, shapes))) == 1


def test_an_unknown_flavour_or_size_says_what_there_is(blank: Project) -> None:
    with pytest.raises(KeyError, match="settled-land"):
        start_world(blank, flavour="cyberpunk")
    with pytest.raises(KeyError, match="small"):
        start_world(blank, size="enormous")


def test_a_suggested_table_borrows_from_the_libraries(blank: Project) -> None:
    """Every reference in it is real, which is the point of the wizard."""
    start_world(blank, seed="one")
    playable(blank)
    table = suggest_table(blank, local_id="the-road", name="The Road", danger=5)
    blank.put("encounterTables", table)

    assert table["entries"]
    assert all(
        str(entry["scene"]).startswith("fantasy.core:")
        for entry in table["entries"]
        if "scene" in entry
    )
    assert not [
        problem
        for problem in blank.report().problems
        if problem.severity is Severity.ERROR
    ]


def test_danger_picks_a_preset_and_the_preset_sets_the_chance(
    blank: Project,
) -> None:
    quiet = suggest_table(blank, local_id="a", name="A", danger=0)
    bad = suggest_table(blank, local_id="b", name="B", danger=10)

    assert quiet["chance"] == PRESETS[0].chance
    assert bad["chance"] == PRESETS[-1].chance


def test_a_preset_given_outright_wins_over_the_danger_level(blank: Project) -> None:
    table = suggest_table(blank, local_id="a", name="A", danger=0, preset=PRESETS[-1])

    assert table["chance"] == PRESETS[-1].chance


def test_a_table_with_nothing_to_draw_on_comes_back_switched_off(
    tmp_path: Path,
) -> None:
    """A `chance` with no entries is a load-time error, not a suggestion."""
    write_pack(tmp_path, "empty")
    alone = Project.create(
        tmp_path / "alone",
        tmp_path,
        pack_id="alone",
        name="Alone",
        kind="library",
        requires={},
    )
    table = suggest_table(alone, local_id="a", name="A", danger=8)
    alone.put("encounterTables", table)

    assert table["chance"] == 0.0
    assert "entries" not in table
    assert not [
        problem
        for problem in alone.report().problems
        if problem.severity is Severity.ERROR
    ]


def test_the_weights_add_up_even_when_one_half_is_missing(blank: Project) -> None:
    """fantasy.core offers no fights, so a bandit road cannot be one — but the
    table it produces must still be a table, not one that adds to 35."""
    table = suggest_table(blank, local_id="a", name="A", preset=PRESETS[-1])
    total = sum(float(entry["weight"]) for entry in table["entries"])

    assert 99 <= total <= 101


def test_a_generated_world_still_needs_its_libraries_loaded(blank: Project) -> None:
    """A pack requiring `fantasy.core` gets `mace.core` too, because it does."""
    assert {pack.id for pack in blank.dependencies.packs} == {
        "fantasy.core",
        "mace.core",
    }


def test_a_generated_pack_loads_as_a_library_would_load_it(blank: Project) -> None:
    start_world(blank, seed="one")
    playable(blank)
    blank.save()
    library = load_library(blank.root.parent)

    assert "world" in {pack.id for pack in library.packs}
    assert not [
        problem
        for problem in validate_library(library).problems
        if problem.severity is Severity.ERROR
        and problem.pack == "world"
        and problem.collection in {"locations", "routes", "regions"}
    ]
