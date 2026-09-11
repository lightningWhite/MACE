"""Finding packs on disk and reading their files.

A pack is any directory with a `pack.yml` in it. Everything else in the
directory is content: the loader globs it and merges by id, so file
organization inside a pack is the author's business, not the loader's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mace.content.errors import ContentError

__all__ = ["MANIFEST_NAME", "content_files", "find_packs", "read_yaml"]

#: The file that makes a directory a pack.
MANIFEST_NAME = "pack.yml"

#: Extensions the loader reads.
CONTENT_SUFFIXES = (".yml", ".yaml")

#: Where authoring tooling keeps its own bookkeeping inside a pack — not
#: content, so the loader never globs it. `mace.wizard.project.NOTES_PATH`
#: lives under here.
TOOLING_DIR = ".mace"


def find_packs(root: Path) -> list[Path]:
    """Find every pack directory under a root.

    A root that is itself a pack counts as one, so both `mace play packs/` and
    `mace play packs/games/peasants-quest` do the obvious thing.

    Parameters
    ----------
    root : Path
        A directory to search.

    Returns
    -------
    list of Path
        Pack directories, sorted for a stable load order.

    Raises
    ------
    ContentError
        If the root does not exist.
    """
    if not root.exists():
        raise ContentError(f"no such directory: {root}")
    if not root.is_dir():
        raise ContentError(f"not a directory: {root}")
    if (root / MANIFEST_NAME).is_file():
        return [root]
    return sorted(manifest.parent for manifest in root.rglob(MANIFEST_NAME))


def content_files(pack_root: Path) -> list[Path]:
    """List a pack's content files, manifest and tooling bookkeeping excluded.

    Parameters
    ----------
    pack_root : Path
        The pack directory.

    Returns
    -------
    list of Path
        Sorted paths, so a duplicate id is always reported against the same
        file rather than whichever the filesystem happened to hand back first.
    """
    return sorted(
        path
        for path in pack_root.rglob("*")
        if path.is_file()
        and path.suffix in CONTENT_SUFFIXES
        and path.name != MANIFEST_NAME
        and not path.is_relative_to(pack_root / TOOLING_DIR)
    )


def read_yaml(path: Path) -> Any:
    """Read one YAML file.

    Parameters
    ----------
    path : Path
        The file to read.

    Returns
    -------
    object
        The parsed document, or None for an empty file.

    Raises
    ------
    ContentError
        If the file is not valid YAML.
    """
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ContentError(f"could not be read as YAML: {error}", path=path) from error
