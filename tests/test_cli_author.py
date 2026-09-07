"""Driving the wizard from a script, the way an author drives it from a chair.

The screens are rendering over `mace.wizard`, so what is worth testing here is
the wiring: that a number opens the right thing, that a built condition
reaches the author's own file, that a playtest runs the project as it stands
in memory, and that quitting never loses work without asking.
"""

import builtins
import io
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from conftest import game_pack
from mace.cli.author import Stop, Wizard, author
from mace.wizard.project import Project

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS = REPO_ROOT / "packs"


def drive(project: Project, *typed: str) -> str:
    """Run the wizard against a scripted set of answers.

    Parameters
    ----------
    project : Project
        The pack to author.
    *typed
        The lines the author "types", in order.

    Returns
    -------
    str
        Everything the wizard printed.
    """
    out = io.StringIO()
    wizard = Wizard(project, out, interactive=False)
    answers: Iterator[str] = iter(typed)

    def read(_prompt: str = "") -> str:
        return next(answers)

    original = builtins.input
    builtins.input = read  # type: ignore[assignment]
    try:
        wizard.home()
    except (Stop, StopIteration):
        # `Stop` is the author quitting; `StopIteration` is a script that ran
        # out, which for these tests means the same thing.
        pass
    finally:
        builtins.input = original
    return out.getvalue()


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project.open(game_pack(tmp_path), tmp_path)


@pytest.fixture
def quest(tmp_path: Path) -> Project:
    """A copy of the real pack, so a test may edit and save it."""
    shutil.copytree(PACKS, tmp_path / "packs")
    return Project.open(
        tmp_path / "packs" / "games" / "peasants-quest", tmp_path / "packs"
    )


def test_the_task_list_is_the_first_thing_you_see(project: Project) -> None:
    shown = drive(project, "q", "n")

    assert "TINY" in shown
    assert "Game setup" in shown
    assert "% complete" in shown
    assert "[p] playtest" in shown


def test_a_section_lists_what_it_holds(project: Project) -> None:
    shown = drive(project, "2", "b", "q", "n")

    assert "WORLD MAP" in shown
    assert "Home" in shown
    assert "The Castle" in shown


def test_answering_a_step_writes_it_into_the_project(project: Project) -> None:
    drive(project, "1", "2", "Seven days, one road.", "b", "q", "n")

    assert dict(project.game or {})["tagline"] == "Seven days, one road."


def test_a_bad_answer_is_refused_and_asked_again(project: Project) -> None:
    shown = drive(project, "1", "8", "half", "45", "b", "q", "n")

    assert "whole number" in shown
    assert dict(project.game or {})["world"]["minutesPerTick"] == 45


def test_a_new_object_exists_before_it_is_finished(project: Project) -> None:
    """It has to be pointable-at long before anybody has filled it in."""
    drive(project, "2", "n", "1", "The Windmill", "b", "b", "q", "n")

    assert project.get("locations", "the-windmill") is not None
    assert (
        dict(project.get("locations", "the-windmill") or {})["name"] == "The Windmill"
    )


def test_a_section_that_spans_collections_opens_the_right_flow(
    project: Project,
) -> None:
    """The world map is places and roads together; a road is not a place."""
    shown = drive(project, "2", "3", "b", "b", "q", "n")

    assert "A ROAD BETWEEN TWO PLACES" in shown


def test_the_cascade_builds_a_condition_and_reads_it_back(project: Project) -> None:
    shown = drive(
        project,
        "5",  # scenes
        "n",
        "The Gate",  # a new scene
        "2",  # when
        "a",
        "1",  # something somebody is carrying
        "1",  # gold
        "10",
        "",  # the player, by default
        "d",
        "b",
        "b",
        "q",
        "n",
    )

    assert "the player is carrying at least 10 Gold" in shown
    written = dict(project.get("scenes", "the-gate") or {})
    assert written["when"] == [{"hasItem": {"item": "gold", "qty": 10}}]


def test_saving_writes_only_what_changed(quest: Project) -> None:
    before = {
        path: (quest.root / path).read_text()
        for path in ("scenes.yml", "entities.yml", "locations.yml")
    }
    drive(quest, "1", "2", "A different tagline.", "b", "s", "q", "n")

    assert yaml.safe_load((quest.root / "game.yml").read_text())["game"]["tagline"] == (
        "A different tagline."
    )
    for path, text in before.items():
        assert (quest.root / path).read_text() == text, f"{path} was rewritten"


def test_quitting_with_unsaved_work_offers_to_save(project: Project) -> None:
    shown = drive(project, "1", "2", "Something", "b", "q", "y")

    assert "Save" in shown
    assert yaml.safe_load((project.root / "game.yml").read_text())["game"][
        "tagline"
    ] == ("Something")


def test_quitting_with_nothing_to_save_just_leaves(project: Project) -> None:
    shown = drive(project, "q")

    assert "Until next time" in shown
    assert "Save" not in shown


def test_validate_shows_the_whole_problem_list(project: Project) -> None:
    project.put("locations", {"id": "nowhere", "name": "Nowhere", "onArrive": "gone"})
    shown = drive(project, "v", "q", "n")

    assert "gone" in shown
    assert "error" in shown


def test_a_playtest_runs_the_project_as_it_stands(quest: Project) -> None:
    """Unsaved changes included — that is the whole point of it."""
    drive(quest, "1", "1", "The Barley War", "b", "q", "n")
    shown = drive(quest, "p", "", "q", "q", "n")

    assert "You are a peasant" in shown
    assert "Back to the wizard" in shown


def test_a_playtest_can_start_anywhere_in_any_weather(quest: Project) -> None:
    shown = drive(
        quest,
        "p",
        "c",
        "autumn",  # seed
        "4",  # the old bridge
        "40",  # tick
        "1",  # blizzard
        "",  # no extra kit
        "y",  # debug overlay
        "q",  # stop playing
        "q",
        "n",
    )

    assert "The Old Bridge" in shown
    assert "blizzard" in shown
    assert "┊ tick 40" in shown


def test_the_playtest_setup_is_remembered(quest: Project) -> None:
    drive(quest, "p", "c", "autumn", "4", "40", "", "", "n", "q", "q", "n")

    assert quest.notes.playtest.seed == "autumn"
    assert quest.notes.playtest.start_location == "troll-bridge"
    assert quest.notes.playtest.start_tick == 40


def test_a_note_survives_the_session(project: Project) -> None:
    drive(project, "n", "locations/castle", "needs a gate", "s", "q", "n")

    written = yaml.safe_load((project.root / ".mace" / "project.yml").read_text())
    assert written["project"]["notes"] == [
        {"about": "locations/castle", "text": "needs a gate"}
    ]


def test_opening_a_pack_that_is_not_there_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert author(tmp_path / "nowhere", tmp_path) == 1
    assert "error" in capsys.readouterr().err


def test_a_statblock_takes_a_cap_and_keeps_whole_numbers_whole(
    project: Project,
) -> None:
    """A pool with no `max` has nothing to refill to, and `base: 20.0` is not
    what an author typed."""
    drive(
        project,
        "3",  # characters
        "n",
        "Gorm",
        "6",  # what is it made of
        "hitpoints 20/20",
        "strength 32",
        "",
        "b",
        "b",
        "q",
        "n",
    )

    assert dict(project.get("entities", "gorm") or {})["stats"] == {
        "hitpoints": {"base": 20, "max": 20},
        "strength": {"base": 32},
    }
