"""Writing authored content back out as YAML.

Everything the wizard saves goes through here, so that how MACE renders a pack
is one decision in one place rather than a habit spread across a dozen flows.

**A known cost, stated rather than discovered.** This writes with
`yaml.safe_dump`, which does not preserve comments or an author's chosen
layout. A file the wizard rewrites comes back tidy and uncommented. That is
fine for a pack the wizard created and wrong for one like `fantasy.core`, whose
comments carry most of what a reader needs — so the wizard only ever rewrites
files it has actually changed, and a hand-written pack keeps everything the
wizard did not touch.

Fixing it properly means a round-tripping YAML library (`ruamel.yaml`), which
is a dependency decision rather than an implementation detail. This module is
the seam where that change would happen: one function, one import.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

__all__ = ["dump", "write_document"]

#: How wide a line may get before the dumper folds it. Generous: prose is the
#: bulk of a content file, and a wrapped sentence is much harder to read and to
#: diff than a long one.
WIDTH = 100


def dump(document: Mapping[str, Any]) -> str:
    """Render one content file.

    Parameters
    ----------
    document : mapping
        Collection name to its list of authored objects.

    Returns
    -------
    str
        YAML text, ready to write.
    """
    return str(
        yaml.safe_dump(
            _plain(document),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=WIDTH,
        )
    )


def write_document(path: Path, document: Mapping[str, Any]) -> None:
    """Write one content file, making its directory if it is not there.

    Parameters
    ----------
    path : Path
        Where to write.
    document : mapping
        Collection name to its list of authored objects.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(document))


def _plain(value: Any) -> Any:
    """Reduce a value to the primitives the dumper can render.

    Authored objects come back from the models as ordinary dicts and lists, but
    a tuple or a set slipped in by hand would be dumped as a Python object tag
    and stop being content. This flattens them instead.

    Parameters
    ----------
    value : object
        Any authored value.

    Returns
    -------
    object
        The same thing, made of dicts, lists, and scalars.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, str | bytes):
        return value
    if isinstance(value, Sequence):
        return [_plain(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_plain(item) for item in value)
    return value
