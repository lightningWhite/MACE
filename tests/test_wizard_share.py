"""Handing a pack to somebody, and taking one from them.

Two rules sit on either side of the exchange and neither is about zip files.
On the way out, a pack that will not load cannot be handed to anybody — the
one place the wizard says no, when saving never does. On the way in, the
archive is untrusted community input, so an entry that would land outside the
pack directory is refused before anything is written.

The third property is quieter and would be missed only once, by the author who
discovered their notes-to-self in somebody else's copy of their game.
"""

import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import write_pack
from mace.content import ContentError, load_library
from mace.content.validation import Severity
from mace.wizard.notes import Note
from mace.wizard.project import NOTES_PATH, Project
from mace.wizard.share import export_pack, import_pack, read_manifest

PACK: dict[str, Any] = {
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


@pytest.fixture
def project(tmp_path: Path) -> Project:
    """A small, valid game pack, open in the wizard.

    Parameters
    ----------
    tmp_path : Path
        Pytest's directory.

    Returns
    -------
    Project
        The pack being authored.
    """
    root = write_pack(tmp_path / "packs", "tiny", kind="game", files=PACK)
    return Project.open(root, root.parent)


def names(archive: Path) -> set[str]:
    """What is in an archive.

    Parameters
    ----------
    archive : Path
        The zip.

    Returns
    -------
    set of str
        Entry names.
    """
    with zipfile.ZipFile(archive) as opened:
        return set(opened.namelist())


def test_an_export_is_the_pack_and_only_the_pack(project: Project) -> None:
    written = export_pack(project)
    assert written.name == "tiny-0.1.0.zip"
    assert names(written) == {"pack.yml", "locations.yml", "people.yml", "game.yml"}


def test_an_export_leaves_the_author_their_notes(project: Project) -> None:
    """`.mace/` is the author's, not the pack's.

    A playtest setup and a list of reminders left at midnight are not content,
    and somebody who is handed the game should not be handed those too.
    """
    project.remember(project.notes.model_copy(update={"notes": [Note(text="fix me")]}))
    written = export_pack(project)

    assert (project.root / NOTES_PATH).is_file()
    assert not any(name.startswith(".mace") for name in names(written))


def test_unsaved_work_goes_into_the_export(project: Project) -> None:
    """An export that left the last twenty minutes on the floor is worse than none."""
    project.put("locations", {"id": "tower", "name": "The Tower"})
    with zipfile.ZipFile(export_pack(project)) as opened:
        written = yaml.safe_load(opened.read("locations.yml"))
    assert "tower" in {one["id"] for one in written["locations"]}


def test_errors_block_an_export(project: Project) -> None:
    """The one place the wizard says no. Saving still does not."""
    project.put(
        "locations", {"id": "cellar", "name": "Cellar", "exits": [{"to": "sea"}]}
    )

    with pytest.raises(ContentError) as refused:
        export_pack(project)
    assert "cannot be handed to anybody" in str(refused.value)
    assert "sea" in str(refused.value)
    # Saving is never blocked, and the export saved before it looked.
    assert (project.root / "locations.yml").read_text().count("cellar") == 1


def test_advice_does_not_block_an_export(project: Project) -> None:
    """A shed nobody can leave is an opinion, not a fault."""
    project.put("locations", {"id": "shed", "name": "A Shed"})
    problems = project.report().problems

    assert problems and not any(one.severity is Severity.ERROR for one in problems)
    assert export_pack(project).is_file()


def test_a_pack_survives_the_round_trip(project: Project, tmp_path: Path) -> None:
    """The point of the whole exercise: somebody else can load what you sent."""
    archive = export_pack(project, tmp_path / "out")
    landed = import_pack(archive, tmp_path / "theirs")

    assert landed == (tmp_path / "theirs" / "tiny").resolve()
    library = load_library(tmp_path / "theirs")
    assert library.pack("tiny").manifest.name == "tiny"
    assert set(library.pack("tiny").locations) == {"home", "castle"}


def test_reading_a_manifest_unpacks_nothing(project: Project, tmp_path: Path) -> None:
    archive = export_pack(project, tmp_path / "out")
    manifest = read_manifest(archive)

    assert (manifest.id, manifest.version) == ("tiny", "0.1.0")
    assert list((tmp_path / "out").iterdir()) == [archive]


def test_a_zip_that_is_not_a_pack_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "holiday.zip"
    with zipfile.ZipFile(archive, "w") as writing:
        writing.writestr("photos.txt", "not a pack")

    with pytest.raises(ContentError, match="is not a MACE pack"):
        import_pack(archive, tmp_path / "packs")
    assert not (tmp_path / "packs").exists()


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "notes.zip"
    archive.write_text("dear diary")

    with pytest.raises(ContentError, match="is not a MACE pack"):
        import_pack(archive, tmp_path / "packs")


def test_an_entry_that_escapes_is_refused(tmp_path: Path) -> None:
    """The classic zip attack. A pack is untrusted input, so this is checked."""
    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as writing:
        writing.writestr("pack.yml", yaml.safe_dump(dict(MANIFEST)))
        writing.writestr("../../taken.yml", "locations: []")

    with pytest.raises(ContentError, match="outside the pack directory"):
        import_pack(archive, tmp_path / "packs")
    assert not (tmp_path / "taken.yml").exists()
    assert not (tmp_path / "packs" / "hostile").exists()


def test_importing_over_somebody_else_is_refused_by_default(
    project: Project, tmp_path: Path
) -> None:
    archive = export_pack(project, tmp_path / "out")
    into = tmp_path / "theirs"
    import_pack(archive, into)

    with pytest.raises(ContentError, match="is already at"):
        import_pack(archive, into)


def test_importing_over_a_pack_on_purpose_replaces_it(
    project: Project, tmp_path: Path
) -> None:
    """Replaces, rather than unpacks over the top.

    A file the new version dropped would otherwise stay on disk and go on
    being loaded — a pack that is neither the old one nor the new one.
    """
    archive = export_pack(project, tmp_path / "out")
    into = tmp_path / "theirs"
    landed = import_pack(archive, into)
    (landed / "stowaway.yml").write_text("locations: []")

    import_pack(archive, into, overwrite=True)
    assert not (landed / "stowaway.yml").exists()
    assert (landed / "game.yml").is_file()


MANIFEST = {
    "id": "hostile",
    "name": "hostile",
    "version": "0.1.0",
    "kind": "game",
    "maceVersion": "^0.1",
}
