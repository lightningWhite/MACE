"""The Project: a pack being written rather than a pack being played.

The properties that matter are the ones an author would notice losing. Their
half-finished world opens. Their file organisation survives. Saving touches
only what changed. Nothing they wrote is silently dropped, including content
this version of MACE does not model yet. And compiling never needs a save,
because "playtest with unsaved changes" is the feature that keeps people
iterating.
"""

import difflib
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import write_pack
from mace.content import ContentError
from mace.wizard.notes import Note, ProjectNotes
from mace.wizard.project import NOTES_PATH, Project

REPO_ROOT = Path(__file__).resolve().parent.parent


def world(root: Path, **files: Any) -> Path:
    """A small game pack to open.

    Parameters
    ----------
    root : Path
        Where to write it.
    **files
        Filename stem to document.

    Returns
    -------
    Path
        The pack directory.
    """
    documents: dict[str, Any] = {
        "locations.yml": {
            "locations": [
                {"id": "home", "name": "Home", "exits": [{"to": "castle"}]},
                {"id": "castle", "name": "The Castle", "exits": [{"to": "home"}]},
            ]
        },
        "people.yml": {
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {
                        "hitpoints": {"base": 10, "max": 10},
                        "stamina": {"base": 10, "max": 10},
                    },
                }
            ]
        },
        "game.yml": {
            "game": {
                "name": "Tiny",
                "player": {"entity": "hero", "startLocation": "home"},
                "winConditions": [{"atLocation": {"location": "castle"}}],
            }
        },
    }
    documents.update({f"{name}.yml": body for name, body in files.items()})
    return write_pack(root, "tiny", kind="game", files=documents)


# ── Opening ───────────────────────────────────────────────────────────────────


def test_a_project_opens_what_is_on_disk(tmp_path: Path) -> None:
    project = Project.open(world(tmp_path))
    assert project.ids("locations") == ["castle", "home"]
    assert project.ids("entities") == ["hero"]
    assert project.game is not None


def test_a_project_without_a_manifest_will_not_open(tmp_path: Path) -> None:
    """Everything else is survivable; not knowing which pack this is, is not."""
    (tmp_path / "nothing").mkdir()
    with pytest.raises(ContentError, match="no pack.yml"):
        Project.open(tmp_path / "nothing")


def test_a_half_written_project_still_opens(tmp_path: Path) -> None:
    """The normal state of a pack being written."""
    root = world(tmp_path, broken={"locations": [{"id": "bad", "nonsense": True}]})
    project = Project.open(root)
    assert project.get("locations", "bad") is not None
    assert any(p.object_id == "bad" for p in project.report().errors)
    assert "home" in project.compile().library.pack("tiny").locations


def test_a_file_that_will_not_parse_is_left_alone(tmp_path: Path) -> None:
    root = world(tmp_path)
    (root / "junk.yml").write_text("locations: [\n")
    project = Project.open(root)
    assert project.ids("locations") == ["castle", "home"]
    assert project.report().errors
    project.save()
    assert (root / "junk.yml").read_text() == "locations: [\n"


def test_dependencies_are_loaded_and_the_project_is_not_one(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "shared", files={"a.yml": {}})
    write_pack(
        tmp_path / "packs",
        "mine",
        kind="game",
        requires=["shared"],
        files={
            "game.yml": {
                "game": {"name": "M", "player": {"entity": "h", "startLocation": "l"}}
            }
        },
    )
    project = Project.open(tmp_path / "packs" / "mine", tmp_path / "packs")
    assert [pack.id for pack in project.dependencies.packs] == ["shared"]


def test_a_dependency_that_is_not_required_is_left_out(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "unrelated", files={"a.yml": {}})
    world(tmp_path / "packs")
    project = Project.open(tmp_path / "packs" / "tiny", tmp_path / "packs")
    assert project.dependencies.packs == ()


# ── Editing ───────────────────────────────────────────────────────────────────


def test_a_new_object_appears_in_the_compiled_library(tmp_path: Path) -> None:
    project = Project.open(world(tmp_path))
    project.put("locations", {"id": "mill", "name": "The Mill"})
    assert "mill" in project.compile().library.pack("tiny").locations


def test_compiling_never_needs_a_save(tmp_path: Path) -> None:
    """ "Playtest with unsaved changes" has to be true, not approximately true."""
    root = world(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    assert "mill" in project.compile().library.pack("tiny").locations
    assert "mill" not in (root / "locations.yml").read_text()


def test_replacing_an_object_keeps_its_file(tmp_path: Path) -> None:
    """An author's file organisation is theirs, not the wizard's."""
    root = world(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "home", "name": "Somewhere Else"})
    project.save()
    assert "Somewhere Else" in (root / "locations.yml").read_text()


def test_a_new_object_goes_to_a_file_named_for_its_collection(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    project.put("scenes", {"id": "wake", "say": "You wake."})
    assert project.save() == [Path("scenes.yml")]
    assert (root / "scenes.yml").is_file()


def test_a_new_object_joins_its_collection_where_it_already_lives(
    tmp_path: Path,
) -> None:
    """A pack whose scenes live in `story.yml` should not sprout a `scenes.yml`."""
    root = world(tmp_path, story={"scenes": [{"id": "wake", "say": "You wake."}]})
    project = Project.open(root)
    project.put("scenes", {"id": "sleep", "say": "You sleep."})
    assert project.save() == [Path("story.yml")]
    assert not (root / "scenes.yml").exists()


def test_a_collection_split_across_files_gets_a_file_of_its_own(
    tmp_path: Path,
) -> None:
    """No right answer, so pick the least surprising one."""
    root = world(
        tmp_path,
        here={"scenes": [{"id": "wake", "say": "You wake."}]},
        there={"scenes": [{"id": "sleep", "say": "You sleep."}]},
    )
    project = Project.open(root)
    project.put("scenes", {"id": "dream", "say": "You dream."})
    assert project.save() == [Path("scenes.yml")]


def test_dropping_an_object_removes_it(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    assert project.drop("locations", "castle") is True
    assert project.drop("locations", "castle") is False
    project.save()
    written = yaml.safe_load((root / "locations.yml").read_text())
    assert [place["id"] for place in written["locations"]] == ["home"]


def test_an_object_with_no_id_is_refused(tmp_path: Path) -> None:
    project = Project.open(world(tmp_path))
    with pytest.raises(ContentError, match="needs an `id`"):
        project.put("locations", {"name": "Nameless"})


def test_an_unknown_collection_is_refused(tmp_path: Path) -> None:
    project = Project.open(world(tmp_path))
    with pytest.raises(ContentError, match="not a content collection"):
        project.put("aspirations", {"id": "someday"})


def test_the_game_manifest_can_be_replaced(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    assert project.game is not None
    project.set_game({**project.game, "tagline": "Seven days."})
    project.save()
    assert "Seven days." in (root / "game.yml").read_text()


# ── Saving ────────────────────────────────────────────────────────────────────


def test_saving_touches_only_what_changed(tmp_path: Path) -> None:
    """What keeps a hand-written pack's comments alive where the wizard is not."""
    root = world(tmp_path)
    before = {path: path.read_text() for path in root.rglob("*.yml")}

    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    assert project.save() == [Path("locations.yml")]

    for path, text in before.items():
        if path.name != "locations.yml":
            assert path.read_text() == text


def test_saving_nothing_writes_nothing(tmp_path: Path) -> None:
    project = Project.open(world(tmp_path))
    assert project.save() == []


def test_a_saved_file_reopens_to_the_same_content(tmp_path: Path) -> None:
    """Presentation is not preserved; content is. That is the whole contract."""
    root = world(tmp_path)
    first = Project.open(root)
    first.put("locations", {"id": "mill", "name": "The Mill"})
    first.save()

    second = Project.open(root)
    assert second.get("locations", "mill") == {"id": "mill", "name": "The Mill"}
    assert second.get("locations", "home") == first.get("locations", "home")


def test_a_saved_file_is_stable_across_saves(tmp_path: Path) -> None:
    """A diff should be about what changed, not about dict ordering."""
    root = world(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    once = (root / "locations.yml").read_text()

    again = Project.open(root)
    again.put("locations", {"id": "mill", "name": "The Mill"})
    again.save()
    assert (root / "locations.yml").read_text() == once


def test_content_no_model_covers_yet_survives_a_round_trip(tmp_path: Path) -> None:
    """An author must not lose work to a phase that has not happened."""
    root = world(tmp_path, goods={"goods": [{"id": "iron", "density": 3}]})
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    assert Project.open(root).unmodelled["goods"] == ({"id": "iron", "density": 3},)


# ── Comments ──────────────────────────────────────────────────────────────────
#
# The reason `mace.content.writing` round-trips instead of dumping. A content
# pack is mostly explanation, and a tool that ate the explanation the first time
# it touched a file would be a tool people stopped opening.


def commented(root: Path) -> Path:
    """A pack whose file carries comments in all three positions.

    Parameters
    ----------
    root : Path
        Where to write it.

    Returns
    -------
    Path
        The pack directory.
    """
    pack = world(root)
    (pack / "locations.yml").write_text(
        "# Two places and the road between them.\n"
        "locations:\n"
        "\n"
        "  # Where it starts.\n"
        "  - id: home\n"
        '    name: "Home"\n'
        "    exits:\n"
        "      - {to: castle}   # the only way out\n"
        "\n"
        "  - id: castle\n"
        '    name: "The Castle"\n'
        "    exits:\n"
        "      - {to: home}\n"
    )
    return pack


def test_a_files_own_comments_survive_an_edit_elsewhere_in_it(
    tmp_path: Path,
) -> None:
    root = commented(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()

    written = (root / "locations.yml").read_text()
    assert "# Two places and the road between them." in written
    assert "# Where it starts." in written
    assert "# the only way out" in written


def test_an_edited_objects_untouched_keys_keep_their_comments(
    tmp_path: Path,
) -> None:
    """The edit is in place, so a note beside a key you did not touch stays."""
    root = commented(tmp_path)
    project = Project.open(root)
    home = dict(project.get("locations", "home") or {})
    home["name"] = "Somewhere Else"
    project.put("locations", home)
    project.save()

    written = (root / "locations.yml").read_text()
    assert "Somewhere Else" in written
    assert "# the only way out" in written
    assert "# Where it starts." in written


def test_quoting_and_key_order_survive(tmp_path: Path) -> None:
    root = commented(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    written = (root / "locations.yml").read_text()
    assert 'name: "Home"' in written
    assert written.index("id: home") < written.index("name:")


def test_an_appended_object_matches_the_files_spacing(tmp_path: Path) -> None:
    root = commented(tmp_path)
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    assert "\n\n  - id: mill\n" in (root / "locations.yml").read_text()


def test_a_file_the_wizard_never_touched_is_byte_identical(tmp_path: Path) -> None:
    root = commented(tmp_path)
    before = (root / "people.yml").read_text()
    project = Project.open(root)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    assert (root / "people.yml").read_text() == before


def test_dropping_an_object_leaves_the_rest_of_the_file_alone(
    tmp_path: Path,
) -> None:
    root = commented(tmp_path)
    project = Project.open(root)
    project.drop("locations", "castle")
    project.save()
    written = (root / "locations.yml").read_text()
    assert "# Two places and the road between them." in written
    assert "# Where it starts." in written
    remaining = yaml.safe_load(written)["locations"]
    assert [place["id"] for place in remaining] == ["home"]


# ── The sidecar ───────────────────────────────────────────────────────────────


def test_notes_round_trip(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    project.remember(
        ProjectNotes(
            completed=("game", "map"),
            notes=(Note(about="locations/home", text="needs a well"),),
        )
    )
    project.save()

    reopened = Project.open(root)
    assert reopened.notes.completed == ("game", "map")
    assert reopened.notes.notes[0].text == "needs a well"


def test_the_sidecar_lives_inside_the_pack(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    project.remember(ProjectNotes(completed=("game",)))
    project.save()
    assert (root / NOTES_PATH).is_file()


def test_the_sidecar_is_not_mistaken_for_content(tmp_path: Path) -> None:
    root = world(tmp_path)
    project = Project.open(root)
    project.remember(ProjectNotes(completed=("game",)))
    project.save()
    assert Project.open(root).report().errors == ()


def test_an_unreadable_sidecar_starts_fresh_rather_than_failing(
    tmp_path: Path,
) -> None:
    """It holds notes, not work. Losing it costs nothing that matters."""
    root = world(tmp_path)
    (root / NOTES_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / NOTES_PATH).write_text("project: {completed: 'not a list'}\n")
    assert Project.open(root).notes.completed == ()


# ── Creating ──────────────────────────────────────────────────────────────────


def test_a_new_project_is_written_and_reopens(tmp_path: Path) -> None:
    Project.create(tmp_path / "fresh", pack_id="fresh", name="Something Fresh")
    assert (tmp_path / "fresh" / "pack.yml").is_file()
    assert Project.open(tmp_path / "fresh").manifest.name == "Something Fresh"


def test_a_new_project_may_require_a_library(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "shared", files={"a.yml": {}})
    project = Project.create(
        tmp_path / "packs" / "fresh",
        tmp_path / "packs",
        pack_id="fresh",
        name="Fresh",
        requires={"shared": "^0.1"},
    )
    assert [pack.id for pack in project.dependencies.packs] == ["shared"]


def test_creating_over_an_existing_pack_is_refused(tmp_path: Path) -> None:
    root = world(tmp_path)
    with pytest.raises(ContentError, match="already a pack"):
        Project.create(root, pack_id="tiny", name="Tiny")


# ── The shipped world ─────────────────────────────────────────────────────────


def test_the_shipped_game_opens_and_reports_nothing(tmp_path: Path) -> None:
    packs = tmp_path / "packs"
    shutil.copytree(REPO_ROOT / "packs", packs)
    project = Project.open(packs / "games" / "peasants-quest", packs)
    assert project.report().errors == ()
    assert [pack.id for pack in project.dependencies.packs] == [
        "mace.core",
        "fantasy.core",
    ]


def test_editing_the_shipped_game_loses_no_content(tmp_path: Path) -> None:
    packs = tmp_path / "packs"
    shutil.copytree(REPO_ROOT / "packs", packs)
    root = packs / "games" / "peasants-quest"

    before = yaml.safe_load((root / "locations.yml").read_text())
    project = Project.open(root, packs)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()

    after = yaml.safe_load((root / "locations.yml").read_text())
    assert after["locations"][:-1] == before["locations"]
    assert after["locations"][-1] == {"id": "mill", "name": "The Mill"}


def test_editing_the_shipped_game_loses_none_of_its_prose(tmp_path: Path) -> None:
    """`packs/` is mostly explanation. Losing it would be losing the pack."""
    packs = tmp_path / "packs"
    shutil.copytree(REPO_ROOT / "packs", packs)
    root = packs / "games" / "peasants-quest"

    def comments(path: Path) -> list[str]:
        return [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip().startswith("#")
        ]

    before = comments(root / "locations.yml")
    assert before, "this test needs a commented file to be about anything"

    project = Project.open(root, packs)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()
    assert comments(root / "locations.yml") == before


def test_editing_the_shipped_game_stays_a_small_diff(tmp_path: Path) -> None:
    """A one-object change should read as a one-object change."""
    packs = tmp_path / "packs"
    shutil.copytree(REPO_ROOT / "packs", packs)
    root = packs / "games" / "peasants-quest"

    before = (REPO_ROOT / "packs/games/peasants-quest/locations.yml").read_text()
    project = Project.open(root, packs)
    project.put("locations", {"id": "mill", "name": "The Mill"})
    project.save()

    changed = [
        line
        for line in difflib.unified_diff(
            before.splitlines(),
            (root / "locations.yml").read_text().splitlines(),
            lineterm="",
            n=0,
        )
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert len(changed) <= 6, "\n".join(changed)
