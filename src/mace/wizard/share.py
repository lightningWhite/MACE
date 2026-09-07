"""Handing a pack to somebody, and taking one from them.

A pack is a directory of YAML and nothing else, so sharing one is a zip. What
makes this a module rather than two lines of `shutil` is the two rules on
either side of the exchange.

**Errors block an export.** Saving is never blocked — an author has to be able
to stop mid-thought — but handing somebody a pack that will not load is a
different thing, and this is the one place the wizard is allowed to say no.
Warnings and notes do not block: a road with no encounters is an opinion, not
a fault.

**An imported pack is untrusted.** Content packs are community input, which
docs/02 says to treat as such, and a zip is the classic way to be handed a
path that escapes where you meant to put it. So every entry is checked against
the destination before anything is written, and an archive that is not a pack
is refused before it can leave a directory of loose files behind.

Importing does not merge, remix, or rename. It puts somebody else's pack
beside yours, and then `requires` is how you build on it — which is the
mechanism packs already have and the reason `fantasy.core` exists.

One thing an archive never carries: `.mace/`. That directory is the author's
own — where their playtest setup and their notes-to-self live — and it is not
part of the pack. The loader already ignores it and so does the wizard; an
export that shipped it would be handing somebody a copy of the reminders you
left yourself at midnight.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import yaml

from mace.content import ContentError
from mace.content.discovery import MANIFEST_NAME, content_files
from mace.content.validation import Severity
from mace.model import Pack
from mace.wizard.project import NOTES_PATH, Project

__all__ = ["MANIFEST_NAME", "export_pack", "import_pack", "read_manifest"]


def export_pack(project: Project, into: Path | None = None) -> Path:
    """Write a pack out as one file somebody else can open.

    Unsaved changes are saved first, because an export that silently left an
    author's last twenty minutes on the floor would be worse than no export.

    Parameters
    ----------
    project : Project
        The pack to write out.
    into : Path or None
        The directory to write into. None writes beside the pack.

    Returns
    -------
    Path
        The archive.

    Raises
    ------
    ContentError
        If the pack has errors, naming them. Warnings and notes do not block.
    """
    project.save()
    report = project.report()
    errors = [one for one in report.problems if one.severity is Severity.ERROR]
    if errors:
        listed = "; ".join(str(one) for one in errors[:3])
        more = f" (and {len(errors) - 3} more)" if len(errors) > 3 else ""
        raise ContentError(
            f"this pack will not load, so it cannot be handed to anybody: "
            f"{listed}{more}",
            pack=project.manifest.id,
        )

    where = (into or project.root.parent).resolve()
    where.mkdir(parents=True, exist_ok=True)
    archive = where / f"{project.manifest.id}-{project.manifest.version}.zip"

    root = project.root.resolve()
    private = root / NOTES_PATH.parent
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as writing:
        writing.write(root / MANIFEST_NAME, MANIFEST_NAME)
        for path in content_files(root):
            if path.resolve().is_relative_to(private):
                continue
            writing.write(path, str(path.resolve().relative_to(root)))
    return archive


def read_manifest(archive: Path) -> Pack:
    """What pack an archive holds, without unpacking it anywhere.

    Parameters
    ----------
    archive : Path
        The zip.

    Returns
    -------
    Pack
        Its manifest.

    Raises
    ------
    ContentError
        If it is not a readable pack archive.
    """
    try:
        with zipfile.ZipFile(archive) as opened:
            body = yaml.safe_load(opened.read(MANIFEST_NAME))
    except (OSError, KeyError, zipfile.BadZipFile, yaml.YAMLError) as error:
        raise ContentError(
            f"{archive} is not a MACE pack: {error}", path=archive
        ) from error

    try:
        return Pack.model_validate(body)
    except ValueError as error:
        raise ContentError(
            f"{archive} has a `pack.yml` that will not load: {error}", path=archive
        ) from error


def import_pack(archive: Path, into: Path, *, overwrite: bool = False) -> Path:
    """Unpack somebody else's pack beside yours.

    Parameters
    ----------
    archive : Path
        The zip.
    into : Path
        The directory packs live in. The pack lands in `into/<pack-id>`.
    overwrite : bool
        Whether to replace a pack of that id that is already there. False
        refuses, because quietly overwriting somebody's work is not a thing a
        tool should do on a keystroke. True replaces it outright rather than
        unpacking over the top: a file the new version dropped would otherwise
        stay on disk and go on being loaded, which is a pack that is neither
        the old one nor the new one.

    Returns
    -------
    Path
        The pack directory.

    Raises
    ------
    ContentError
        If it is not a pack, if one of that id is already there, or if the
        archive tries to write outside where it was told to.
    """
    manifest = read_manifest(archive)
    root = (into / manifest.id).resolve()
    if root.exists() and not overwrite:
        raise ContentError(
            f"`{manifest.id}` is already at {root} — move it, or import over it "
            "on purpose",
            pack=manifest.id,
            path=root,
        )

    with zipfile.ZipFile(archive) as opened:
        for name in opened.namelist():
            _inside(root, name, archive)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        opened.extractall(root)
    return root


def _inside(root: Path, name: str, archive: Path) -> None:
    """Refuse an archive entry that would land outside where it was told to.

    The classic zip attack, and worth spelling out rather than trusting a
    library to have handled: a content pack is untrusted community input
    (docs/02, boundary 5), and `../../.ssh/authorized_keys` is a perfectly
    legal name inside a zip file.

    Parameters
    ----------
    root : Path
        Where the pack is going.
    name : str
        The entry's name.
    archive : Path
        The zip, for the error.

    Raises
    ------
    ContentError
        If the entry escapes.
    """
    landing = (root / name).resolve()
    if landing == root or root in landing.parents:
        return
    raise ContentError(
        f"{archive} holds `{name}`, which would be written outside the pack "
        "directory. Refusing it.",
        path=archive,
    )
