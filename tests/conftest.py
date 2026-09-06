"""Shared helpers for tests that need real packs on disk.

The things that break a content pipeline — a child above its parent in a file,
two files claiming one id, a dependency that isn't there — are facts about
directories, so the tests build directories.
"""

from pathlib import Path
from typing import Any

import yaml


def write_pack(
    root: Path,
    pack_id: str,
    *,
    kind: str = "library",
    requires: list[str] | None = None,
    files: dict[str, Any] | None = None,
) -> Path:
    """Write a minimal pack to disk.

    Parameters
    ----------
    root : Path
        Directory to create the pack under.
    pack_id : str
        The pack's id; also its directory name.
    kind : str
        `library` or `game`.
    requires : list of str or None
        Pack ids to depend on, at `^0.1`.
    files : dict or None
        Filename to document, for the pack's content files.

    Returns
    -------
    Path
        The pack directory.
    """
    pack_root = root / pack_id
    pack_root.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "id": pack_id,
        "name": pack_id,
        "version": "0.1.0",
        "kind": kind,
        "maceVersion": "^0.1",
    }
    if requires:
        manifest["requires"] = [{"id": name, "version": "^0.1"} for name in requires]
    (pack_root / "pack.yml").write_text(yaml.safe_dump(manifest))

    for filename, document in (files or {}).items():
        path = pack_root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False))
    return pack_root


def troll(**overrides: Any) -> dict[str, Any]:
    """A small entity to inherit from.

    Parameters
    ----------
    **overrides
        Fields to change.

    Returns
    -------
    dict
        An entity definition.
    """
    return {
        "id": "bridge-troll",
        "kind": "actor",
        "name": "Bridge Troll",
        "tags": ["monster", "large"],
        "stats": {"hitpoints": {"base": 80}, "strength": {"base": 70}},
        **overrides,
    }
