"""Deep merge with the two inheritance sentinels.

`extends` is resolved here, on raw mappings, before anything is validated — so
a child may leave out what its parent supplies, and a sentinel never reaches a
model. See docs/03-content-model.md § Inheritance.

Maps merge deeply and lists replace, which is the behaviour that surprises
nobody. The two sentinels cover the cases where replacing is the wrong answer:

- `$append` as a list's first element adds to the inherited list instead of
  replacing it.
- `$remove: [key, ...]` drops inherited keys the child does not want.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["APPEND", "REMOVE", "find_sentinels", "merge"]

#: Prepended to a list to add to the inherited one rather than replace it.
APPEND = "$append"

#: A mapping key whose value lists inherited keys to drop.
REMOVE = "$remove"


def merge(parent: Mapping[str, Any], child: Mapping[str, Any]) -> dict[str, Any]:
    """Merge a child definition over the parent it extends.

    Parameters
    ----------
    parent : mapping
        The inherited definition, already fully resolved.
    child : mapping
        The definition written by the author, sentinels included.

    Returns
    -------
    dict
        The merged definition, with no sentinels left in it.
    """
    merged: dict[str, Any] = dict(parent)

    for key, value in child.items():
        if key == REMOVE:
            continue
        inherited = merged.get(key)
        if isinstance(inherited, Mapping) and isinstance(value, Mapping):
            merged[key] = merge(inherited, value)
        elif _is_append(value):
            base = inherited if isinstance(inherited, Sequence) else []
            merged[key] = [*base, *list(value)[1:]]
        else:
            merged[key] = value

    for key in child.get(REMOVE, ()):
        merged.pop(key, None)

    return merged


def _is_append(value: Any) -> bool:
    """Whether a value is a list asking to be appended to its inherited one.

    Parameters
    ----------
    value : object
        A value from the child definition.

    Returns
    -------
    bool
        True for a non-empty list whose first element is the append sentinel.
    """
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str)
        and len(value) > 0
        and value[0] == APPEND
    )


def find_sentinels(value: Any, path: str = "") -> list[str]:
    """Find merge sentinels left in a definition.

    A sentinel only means something against an inherited definition, so one in
    an object that extends nothing is a mistake worth naming rather than
    letting it fail later as an odd-looking pattern error.

    Parameters
    ----------
    value : object
        Raw data to search.
    path : str
        The dotted path walked so far, used to build the report.

    Returns
    -------
    list of str
        Paths at which a sentinel was found, in the order encountered.
    """
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            here = f"{path}.{key}" if path else str(key)
            if key == REMOVE:
                found.append(here)
            else:
                found.extend(find_sentinels(item, here))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(value):
            here = f"{path}[{index}]"
            if item == APPEND:
                found.append(here)
            else:
                found.extend(find_sentinels(item, here))
    return found
