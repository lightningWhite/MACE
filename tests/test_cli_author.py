"""Driving the wizard from a script, the way an author drives it from a chair.

The screens are rendering over `mace.wizard`, so what is worth testing here is
the wiring: that a number opens the right thing, that a built condition
reaches the author's own file, that a playtest runs the project as it stands
in memory, and that quitting never loses work without asking.
"""

import builtins
import io
import shutil
import zipfile
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
def two_quests(tmp_path: Path) -> Project:
    """A pack with two quests, so a stage picker has something to narrow."""

    def stage(id_: str) -> dict[str, object]:
        return {"id": id_, "journal": "...", "complete": [{"chance": 1}]}

    quests = {
        "quests": [
            {
                "id": "the-summons",
                "name": "The Summons",
                "stages": [stage("set-out"), stage("arrive")],
            },
            {
                "id": "the-heist",
                "name": "The Heist",
                "stages": [stage("case-the-vault"), stage("crack-it")],
            },
        ]
    }
    return Project.open(game_pack(tmp_path, world=quests), tmp_path)


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


def test_an_encounter_table_can_be_built_from_the_wizard(project: Project) -> None:
    """The encounters section used to have no flow at all — `[n] new` did
    nothing because `encounterTables` was not in `FLOWS`."""
    shown = drive(
        project,
        "7",  # encounters
        "n",
        "Forest Road",  # a new table
        "6",  # entries
        "a",
        "wolf-pack",  # entry.id
        "",  # entry.weight — blank
        "d",  # entry.when — no conditions
        "",  # entry.scene — blank, a fight instead
        "1",  # entry.combatAgainst — hero, the only actor
        "",  # entry.combatFleeTo — blank
        "",  # entry.once — blank
        "",  # entry.cooldownTicks — blank
        "",  # entry.maxPerGame — blank
        "d",  # done adding entries
        "b",
        "b",
        "q",
        "n",
    )

    assert "Made `forest-road`" in shown
    written = dict(project.get("encounterTables", "forest-road") or {})
    assert written["entries"] == [{"id": "wolf-pack", "combat": {"against": ["hero"]}}]


def test_a_repeat_entry_can_be_edited_not_only_removed(project: Project) -> None:
    """A choice used to be delete-and-retype-from-scratch. It should not be."""
    shown = drive(
        project,
        "5",  # scenes
        "n",
        "The Gate",  # a new scene
        "5",  # choices
        "a",
        "Pay the toll (10 gold)",  # choice.prompt
        "d",  # choice.when — no conditions
        "",  # choice.showWhenUnavailable — blank
        "",  # choice.unavailableHint — blank
        "",  # choice.goto — blank
        "d",  # choice.effects — nothing happens
        "a",
        "Fight the goblin",  # choice.prompt
        "d",
        "",
        "",
        "",
        "d",
        "e",  # edit, not remove
        "1",  # the toll choice
        "Pay the toll (fifteen gold)",  # choice.prompt, changed
        "d",
        "",
        "",
        "",
        "d",
        "d",  # done with choices
        "b",
        "b",
        "q",
        "n",
    )

    assert "[e] edit" in shown
    assert "now: Pay the toll (10 gold)" in shown
    written = dict(project.get("scenes", "the-gate") or {})
    prompts = [choice["prompt"] for choice in written["choices"]]
    assert prompts == ["Pay the toll (fifteen gold)", "Fight the goblin"]


def test_a_quest_stage_question_is_narrowed_to_the_chosen_quest(
    two_quests: Project,
) -> None:
    shown = drive(
        two_quests,
        "5",  # scenes
        "n",
        "The Vault",  # a new scene
        "2",  # when
        "a",
        "13",  # a quest has reached a stage
        "1",  # the-heist
        "1",  # case-the-vault
        "d",
        "b",
        "b",
        "q",
        "n",
    )

    assert "case the vault" in shown
    assert "crack it" in shown
    assert "set out" not in shown
    assert "arrive" not in shown
    written = dict(two_quests.get("scenes", "the-vault") or {})
    assert written["when"] == [
        {"questStage": {"quest": "the-heist", "stage": "case-the-vault"}}
    ]


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


def test_a_statblock_entry_may_be_relative_to_the_player(project: Project) -> None:
    """`3xhitpoints` means 3x whatever the player's own hitpoints turn out to be."""
    drive(
        project,
        "3",  # characters
        "n",
        "Gorm",
        "6",  # what is it made of
        "hitpoints 3xhitpoints/40",
        "",
        "b",
        "b",
        "q",
        "n",
    )

    assert dict(project.get("entities", "gorm") or {})["stats"] == {
        "hitpoints": {
            "base": {"relativeToPlayer": {"stat": "hitpoints", "factor": 3.0}},
            "max": 40,
        },
    }


def test_a_move_can_be_authored_from_the_wizard(project: Project) -> None:
    drive(
        project,
        "10",  # moves
        "n",
        "Overhead smash",
        "2",  # move.kind
        "1",  # attack
        "3",  # move.type
        "overhead",
        "b",
        "b",
        "q",
        "n",
    )

    held = dict(project.get("moves", "overhead-smash") or {})
    assert held["kind"] == "attack"
    assert held["type"] == "overhead"


def test_an_attack_moves_tell_question_appears_once_kind_is_set(
    project: Project,
) -> None:
    """`visible_when` responds to the sibling answer, in the terminal too."""
    shown = drive(
        project,
        "10",  # moves
        "n",
        "Swing",
        "2",  # move.kind
        "1",  # attack
        "b",
        "b",
        "q",
        "n",
    )

    assert "How is it telegraphed?" in shown


def test_a_defense_moves_tell_question_stays_hidden(project: Project) -> None:
    shown = drive(
        project,
        "10",  # moves
        "n",
        "Dodge",
        "2",  # move.kind
        "2",  # defense
        "b",
        "b",
        "q",
        "n",
    )

    assert "How is it telegraphed?" not in shown


def test_an_actors_item_steps_are_absent_from_the_menu(project: Project) -> None:
    shown = drive(project, "3", "n", "Bandit", "b", "b", "q", "n")

    assert "Minimum damage, if it's a weapon?" not in shown


def test_an_items_steps_include_weapon_damage(project: Project) -> None:
    shown = drive(project, "4", "n", "Dagger", "b", "b", "q", "n")

    assert "Minimum damage, if it's a weapon?" in shown


def test_exporting_writes_a_pack_somebody_else_can_open(
    quest: Project, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    shown = drive(quest, "e", str(out), "q", "n")

    assert "Wrote" in shown and "mace import" in shown
    written = list(out.glob("*.zip"))
    assert len(written) == 1
    with zipfile.ZipFile(written[0]) as opened:
        assert "pack.yml" in opened.namelist()


def test_errors_stop_an_export_and_say_so(project: Project) -> None:
    """The one place the wizard says no — and it still lets you save."""
    project.put(
        "locations", {"id": "cellar", "name": "Cellar", "exits": [{"to": "sea"}]}
    )
    shown = drive(project, "e", "", "s", "q")

    assert "cannot be handed to anybody" in shown
    assert "saving still works" in shown
    # It refused to hand the pack on. It did not refuse to write the file:
    # an export saves first, and saving is never blocked.
    assert "cellar" in (project.root / "world.yml").read_text()
