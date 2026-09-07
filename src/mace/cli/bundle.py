"""Packing the engine and its worlds into one file for a browser.

The static build has no server, so everything the tab needs has to arrive as
files: the `mace` package itself, and the content packs it plays. This writes
both into one zip, with a small manifest saying which directories in it are
packs.

A zip rather than a wheel, and no build backend, on purpose. `mace` is pure
Python with no package data and nothing that reads `__file__`, so a directory
on `sys.path` is all an interpreter needs — and a zip is one fetch, one stdlib
module to open it, and nothing to keep in step with a packaging tool. The
browser side is `web/src/local/`.

See docs/decisions/0005-python-core-with-pyodide.md.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Sequence
from pathlib import Path

import mace
from mace.content import ContentError, find_packs

__all__ = ["MANIFEST", "bundle"]

#: The manifest inside the zip. Named so somebody who opens the file can see
#: what it is without guessing from the directory names.
MANIFEST = "bundle.json"

#: Never shipped: bytecode is per-interpreter and the browser's is not this
#: one, and a `.pyc` for the wrong version is a confusing import error rather
#: than a missing file.
SKIP = ("__pycache__",)


def bundle(paths: Sequence[Path], out: Path) -> tuple[Path, list[str]]:
    """Write the engine and some packs to one zip.

    Parameters
    ----------
    paths : sequence of Path
        Directories to look for packs under.
    out : Path
        Where to write the zip.

    Returns
    -------
    tuple of (Path, list of str)
        The path written, and the paths inside it that are packs.

    Raises
    ------
    ContentError
        If no packs were found, or the file cannot be written.
    """
    found = [root for path in paths for root in find_packs(path)]
    if not found:
        named = ", ".join(str(path) for path in paths)
        raise ContentError(f"no packs found under {named}")

    source = Path(mace.__file__).parent
    packed: list[str] = []

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in _walk(source):
                archive.write(file, f"mace/{file.relative_to(source)}")

            for root in sorted(found, key=lambda one: one.name):
                inside = f"packs/{root.name}"
                packed.append(inside)
                for file in _walk(root):
                    archive.write(file, f"{inside}/{file.relative_to(root)}")

            archive.writestr(
                MANIFEST,
                json.dumps({"version": mace.__version__, "packs": packed}, indent=2)
                + "\n",
            )
    except OSError as error:
        raise ContentError(f"could not write the bundle to {out}: {error}") from error

    return out, packed


def _walk(root: Path) -> list[Path]:
    """Every file under a directory worth shipping, in a stable order.

    Parameters
    ----------
    root : Path
        The directory.

    Returns
    -------
    list of Path
        Files, sorted, with bytecode and other build leavings left out.
    """
    return sorted(
        file
        for file in root.rglob("*")
        if file.is_file()
        and not any(part in SKIP for part in file.relative_to(root).parts)
    )
