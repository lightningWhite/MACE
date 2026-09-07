"""Reading and writing authored content without eating the comments.

`ruamel.yaml` is imported inside the functions rather than at the top of the
file, which is worth the small ugliness: it is an *authoring* dependency, and
`import mace.content` is on the path to playing a game. Under Pyodide that is
a wheel the player would download to run a browser tab that never writes a
pack. Reading content needs pyyaml; only writing it needs this.

Everything the wizard saves goes through here, so how MACE renders a pack is
one decision in one place rather than a habit spread across a dozen flows.

The whole reason this is not two lines of `yaml.safe_dump` is that a content
pack is mostly *explanation*. `fantasy.core/combat.yml` opens with nine lines
saying why the counter matrix is content rather than engine code, and
`peasants-quest/encounters.yml` explains why `$append` keeps the atmosphere
entries. A tool that ate those the first time it touched a file would be a tool
people stopped opening — and the wizard is meant to be the primary way games
get made, not a thing you use once and then go back to a text editor.

So reading and writing both go through `ruamel.yaml` in round-trip mode, and
the objects the wizard holds are the *same objects* it read, comments attached.
Editing one in place and dumping its document back leaves everything else in
the file exactly as it was.

What does not survive is cosmetic and small: hand-aligned columns collapse to
one space, redundant braces inside a flow sequence go away
(`[{hasItem: ...}]` becomes `[hasItem: ...]`), and a flow mapping the author
wrapped by hand comes back on one line. Across every file in `packs/` that is
about a tenth of the lines, no comments, and — checked by a test — no change of
meaning anywhere.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mace.content.errors import ContentError

if TYPE_CHECKING:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

__all__ = ["document", "dump", "load_document", "write_document"]

#: How wide a line may get before the dumper folds it. Effectively unlimited:
#: prose is the bulk of a content file, and a sentence wrapped mid-word is much
#: harder to read and to diff than a long one.
WIDTH = 4096

#: Indentation matching how the shipped packs are written — a sequence item
#: sits two spaces in from its key. Chosen by measuring: it is what makes a
#: re-dump of `packs/` come back as nearly the same bytes.
INDENT = {"mapping": 2, "sequence": 4, "offset": 2}


def _writer() -> YAML:
    """Build a round-tripping YAML handler.

    Fresh each time rather than shared: `YAML` carries mutable state, and a
    handler used from two places at once is a bug nobody would find.

    Returns
    -------
    YAML
        A handler that preserves comments, quoting, and key order.
    """
    from ruamel.yaml import YAML  # noqa: PLC0415

    handler = YAML()
    handler.preserve_quotes = True
    handler.width = WIDTH
    handler.indent(**INDENT)
    return handler


def load_document(path: Path) -> Any:
    """Read one content file, keeping its comments attached.

    Parameters
    ----------
    path : Path
        The file to read.

    Returns
    -------
    object
        The parsed document — mappings come back as `CommentedMap`, which is a
        `dict` and validates like one. `None` for an empty file.

    Raises
    ------
    ContentError
        If the file is not readable or not valid YAML.
    """
    from ruamel.yaml.error import YAMLError  # noqa: PLC0415

    try:
        return _writer().load(path.read_text())
    except YAMLError as error:
        raise ContentError(f"is not valid YAML: {error}", path=path) from error
    except OSError as error:
        raise ContentError(f"could not be read: {error}", path=path) from error


def document(body: Mapping[str, Any] | None = None) -> CommentedMap:
    """Start a new content document.

    Parameters
    ----------
    body : mapping or None
        Initial contents.

    Returns
    -------
    CommentedMap
        An empty document that can carry comments once it has any.
    """
    from ruamel.yaml.comments import CommentedMap  # noqa: PLC0415

    return CommentedMap(body or {})


def dump(body: Mapping[str, Any]) -> str:
    """Render one content file.

    Parameters
    ----------
    body : mapping
        Collection name to its list of authored objects. A document that came
        from `load_document` keeps its comments; a plain dict has none to keep.

    Returns
    -------
    str
        YAML text, ready to write.
    """
    out = io.StringIO()
    _writer().dump(_plain(body), out)
    return out.getvalue()


def write_document(path: Path, body: Mapping[str, Any]) -> None:
    """Write one content file, making its directory if it is not there.

    Parameters
    ----------
    path : Path
        Where to write.
    body : mapping
        The document.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(body))


def _plain(value: Any) -> Any:
    """Reduce a value to something the dumper can render.

    Anything ruamel produced is left strictly alone — that is where the
    comments live. Only foreign shapes are converted, because a tuple or a set
    reaching the dumper comes out as a Python object tag and stops being
    content.

    Parameters
    ----------
    value : object
        Any authored value.

    Returns
    -------
    object
        The same thing, made of things YAML has a spelling for.
    """
    if value.__class__.__module__.startswith("ruamel.yaml"):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, str | bytes):
        return value
    if isinstance(value, set | frozenset):
        return sorted(_plain(item) for item in value)
    if isinstance(value, Sequence):
        return [_plain(item) for item in value]
    return value
