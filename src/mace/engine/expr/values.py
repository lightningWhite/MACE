"""Value semantics shared by the evaluator and the function whitelist.

Truthiness and equality are defined here, once, rather than inherited from
Python's, so that the rules an author has to hold in their head are written down
in one place — and so a second engine implementation can match them exactly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .nodes import Value

__all__ = ["describe", "truthy", "equal"]


def truthy(value: Value) -> bool:
    """Reduce a value to a boolean for `and`, `or`, `not`, and conditions.

    Booleans are themselves; `null` is false; numbers are true when non-zero;
    strings, lists, and mappings are true when non-empty.

    Parameters
    ----------
    value : Value
        The value to test.

    Returns
    -------
    bool
        The value's truthiness.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float):
        return value != 0
    return len(value) > 0


def equal(left: Value, right: Value) -> bool:
    """Compare two values for `==`.

    Types do not cross: a boolean equals only a boolean, so `true == 1` is
    false rather than the surprise Python would hand back.

    Parameters
    ----------
    left, right : Value
        The values to compare.

    Returns
    -------
    bool
        True if the values are equal.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    return bool(left == right)


def describe(value: Value) -> str:
    """Name a value's type the way an author would recognise it.

    Parameters
    ----------
    value : Value
        The value to describe.

    Returns
    -------
    str
        A short description, e.g. ``a string ('rain')``.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"a boolean ({'true' if value else 'false'})"
    if isinstance(value, int | float):
        return f"a number ({value})"
    if isinstance(value, str):
        return f"a string ({value!r})"
    if isinstance(value, Mapping):
        return "a mapping"
    if isinstance(value, Sequence):
        return "a list"
    return type(value).__name__
