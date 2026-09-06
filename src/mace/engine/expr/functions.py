"""The function whitelist.

The expression language has no user-defined functions and no way to reach a
Python callable through a path. This module is the complete list of what an
author may call; growing it is a deliberate, reviewable act.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .nodes import Value
from .values import describe

__all__ = ["FunctionSpec", "FUNCTIONS", "call_function"]


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """How many arguments a whitelisted function accepts.

    Attributes
    ----------
    min_args : int
        Fewest arguments accepted.
    max_args : int or None
        Most arguments accepted, or `None` for no upper bound.
    """

    min_args: int
    max_args: int | None


#: Every function an author may call, and its arity. Checked at parse time.
FUNCTIONS: Mapping[str, FunctionSpec] = {
    "abs": FunctionSpec(1, 1),
    "count": FunctionSpec(1, 1),
    "max": FunctionSpec(1, None),
    "min": FunctionSpec(1, None),
}


def call_function(name: str, args: Sequence[Value]) -> Value:
    """Apply a whitelisted function to already-evaluated arguments.

    Parameters
    ----------
    name : str
        The function name. Must be a key of `FUNCTIONS`.
    args : sequence of Value
        The evaluated arguments, arity already checked by the parser.

    Returns
    -------
    Value
        The function's result.

    Raises
    ------
    ValueError
        If an argument is the wrong type or a numeric function got no values.
        The evaluator turns this into an `ExprEvaluationError` with a position.
    """
    if name == "abs":
        return abs(_number(args[0], "abs"))
    if name == "count":
        return _count(args[0])
    return _extreme(name, args)


def _number(value: Value, function: str) -> int | float:
    """Require a numeric argument.

    Parameters
    ----------
    value : Value
        The evaluated argument.
    function : str
        Function name, for the error message.

    Returns
    -------
    int or float
        The argument, unchanged.

    Raises
    ------
    ValueError
        If the argument is not a number. Booleans are not numbers here.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"`{function}` needs a number, got {describe(value)}")
    return value


def _count(value: Value) -> int:
    """Count the entries of a list, the keys of a mapping, or a string's characters.

    Parameters
    ----------
    value : Value
        The evaluated argument.

    Returns
    -------
    int
        The number of entries.

    Raises
    ------
    ValueError
        If the argument is not something countable.
    """
    if isinstance(value, str) or isinstance(value, Mapping | Sequence):
        return len(value)
    raise ValueError(
        f"`count` needs a list, a mapping, or a string, got {describe(value)}"
    )


def _extreme(name: str, args: Sequence[Value]) -> int | float:
    """Apply `min` or `max` to loose arguments or to a single list argument.

    Parameters
    ----------
    name : str
        Either `"min"` or `"max"`.
    args : sequence of Value
        One list of numbers, or two or more numbers.

    Returns
    -------
    int or float
        The smallest or largest value.

    Raises
    ------
    ValueError
        If an argument is not a number, or the single list argument is empty.
    """
    values: Sequence[Value]
    if (
        len(args) == 1
        and not isinstance(args[0], str)
        and isinstance(args[0], Sequence)
    ):
        values = args[0]
        if not values:
            raise ValueError(f"`{name}` was given an empty list")
    else:
        values = args

    numbers = [_number(value, name) for value in values]
    return min(numbers) if name == "min" else max(numbers)
