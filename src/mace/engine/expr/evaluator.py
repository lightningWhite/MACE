"""Evaluation of a parsed expression against a context.

The context is a mapping of root names — `player`, `world`, an entity id — to
whatever the caller wants to expose. Paths walk mappings by key and objects by
attribute, but never call anything: the only callables in the language are the
whitelisted functions, applied to values that have already been computed.

A lookup that cannot be answered raises rather than returning `null`. A silently
false condition is a bug an author will find three hours into a playthrough.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import ExprEvaluationError
from .functions import call_function
from .nodes import (
    BinaryOp,
    BoolOp,
    Call,
    ListLiteral,
    Literal,
    Node,
    Path,
    UnaryOp,
    Value,
)
from .values import describe, equal, truthy

__all__ = ["evaluate_node"]

#: How many candidate names an "unknown field" error lists before giving up.
_SUGGESTION_LIMIT = 8

#: Comparisons that need an ordering, and so need numbers on both sides.
_ORDERED_OPS = frozenset({"<", "<=", ">", ">="})


def evaluate_node(node: Node, context: Mapping[str, Any], source: str) -> Value:
    """Evaluate one node of a parsed expression.

    Parameters
    ----------
    node : Node
        The node to evaluate.
    context : mapping of str to object
        Root names the expression may read, e.g. `{"player": ..., "world": ...}`.
    source : str
        The original expression text, for error rendering.

    Returns
    -------
    Value
        The node's value.

    Raises
    ------
    ExprEvaluationError
        If a path is unknown, a type is wrong, or a division divides by zero.
    """
    match node:
        case Literal():
            return node.value
        case Path():
            return _resolve_path(node, context, source)
        case ListLiteral():
            return [evaluate_node(item, context, source) for item in node.items]
        case UnaryOp():
            return _unary(node, context, source)
        case BoolOp():
            return _boolean(node, context, source)
        case BinaryOp():
            return _binary(node, context, source)
        case Call():
            return _call(node, context, source)
        case _:  # pragma: no cover - every node kind is handled above
            raise ExprEvaluationError(
                f"cannot evaluate a {type(node).__name__}", source, node.position
            )


def _unary(node: UnaryOp, context: Mapping[str, Any], source: str) -> Value:
    """Evaluate `not x`, `-x`, or `+x`.

    Parameters
    ----------
    node : UnaryOp
        The node to evaluate.
    context : mapping of str to object
        The evaluation context.
    source : str
        The original expression text.

    Returns
    -------
    Value
        The result.
    """
    operand = evaluate_node(node.operand, context, source)
    if node.op == "not":
        return not truthy(operand)
    if isinstance(operand, bool) or not isinstance(operand, int | float):
        raise ExprEvaluationError(
            f"`{node.op}` needs a number, got {describe(operand)}",
            source,
            node.position,
        )
    return -operand if node.op == "-" else operand


def _boolean(node: BoolOp, context: Mapping[str, Any], source: str) -> Value:
    """Evaluate a short-circuiting `and` / `or`.

    The right operand is only evaluated when the left does not settle the
    answer, so `has_pack and pack.weight > 10` is safe to write.

    Parameters
    ----------
    node : BoolOp
        The node to evaluate.
    context : mapping of str to object
        The evaluation context.
    source : str
        The original expression text.

    Returns
    -------
    Value
        `True` or `False` — never one of the operands, unlike Python's.
    """
    left = truthy(evaluate_node(node.left, context, source))
    if node.op == "and" and not left:
        return False
    if node.op == "or" and left:
        return True
    return truthy(evaluate_node(node.right, context, source))


def _binary(node: BinaryOp, context: Mapping[str, Any], source: str) -> Value:
    """Evaluate arithmetic, comparison, or membership.

    Parameters
    ----------
    node : BinaryOp
        The node to evaluate.
    context : mapping of str to object
        The evaluation context.
    source : str
        The original expression text.

    Returns
    -------
    Value
        The result.
    """
    left = evaluate_node(node.left, context, source)
    right = evaluate_node(node.right, context, source)
    op = node.op

    if op == "==":
        return equal(left, right)
    if op == "!=":
        return not equal(left, right)
    if op in ("in", "not in"):
        found = _contains(right, left, node, source)
        return found if op == "in" else not found
    if op in _ORDERED_OPS:
        return _ordered(op, left, right, node, source)
    return _arithmetic(op, left, right, node, source)


def _ordered(op: str, left: Value, right: Value, node: BinaryOp, source: str) -> bool:
    """Evaluate `< <= > >=` over two numbers.

    Parameters
    ----------
    op : str
        The operator.
    left, right : Value
        The already-evaluated operands.
    node : BinaryOp
        The node, for error positioning.
    source : str
        The original expression text.

    Returns
    -------
    bool
        The comparison's result.

    Raises
    ------
    ExprEvaluationError
        If either operand is not a number.
    """
    first, second = _numbers(op, "compares", left, right, node, source)
    if op == "<":
        return first < second
    if op == "<=":
        return first <= second
    if op == ">":
        return first > second
    return first >= second


def _arithmetic(
    op: str, left: Value, right: Value, node: BinaryOp, source: str
) -> int | float:
    """Evaluate `+ - * / %` over two numbers.

    Parameters
    ----------
    op : str
        The operator.
    left, right : Value
        The already-evaluated operands.
    node : BinaryOp
        The node, for error positioning.
    source : str
        The original expression text.

    Returns
    -------
    int or float
        The result. `/` always produces a float.

    Raises
    ------
    ExprEvaluationError
        If an operand is not a number, or the divisor is zero.
    """
    first, second = _numbers(op, "needs", left, right, node, source)

    if op == "+":
        return first + second
    if op == "-":
        return first - second
    if op == "*":
        return first * second
    if second == 0:
        raise ExprEvaluationError(
            f"`{op}` cannot divide by zero", source, node.right.position
        )
    return first / second if op == "/" else first % second


def _numbers(
    op: str, verb: str, left: Value, right: Value, node: BinaryOp, source: str
) -> tuple[int | float, int | float]:
    """Require both operands of an operator to be numbers.

    Parameters
    ----------
    op : str
        The operator, for the error message.
    verb : str
        How the message reads, e.g. `"needs"` or `"compares"`.
    left, right : Value
        The already-evaluated operands.
    node : BinaryOp
        The node, for error positioning.
    source : str
        The original expression text.

    Returns
    -------
    tuple of (int or float, int or float)
        The two operands, unchanged.

    Raises
    ------
    ExprEvaluationError
        If either operand is not a number. Booleans are not numbers.
    """
    if (
        isinstance(left, bool)
        or isinstance(right, bool)
        or not isinstance(left, int | float)
        or not isinstance(right, int | float)
    ):
        raise ExprEvaluationError(
            f"`{op}` {verb} numbers; got {describe(left)} and {describe(right)}",
            source,
            node.position,
        )
    return left, right


def _contains(container: Value, item: Value, node: BinaryOp, source: str) -> bool:
    """Test membership for `in` / `not in`.

    Parameters
    ----------
    container : Value
        The right-hand operand: a list, or a mapping (tested against its keys).
    item : Value
        The left-hand operand.
    node : BinaryOp
        The node, for error positioning.
    source : str
        The original expression text.

    Returns
    -------
    bool
        True if the item is in the container.

    Raises
    ------
    ExprEvaluationError
        If the container is a string, a number, or `null`. Strings are refused
        because "is this a substring" and "is this an element" are different
        questions that should not share a spelling.
    """
    if isinstance(container, Mapping):
        return any(equal(key, item) for key in container)
    if isinstance(container, Sequence) and not isinstance(container, str):
        return any(equal(element, item) for element in container)
    raise ExprEvaluationError(
        f"`in` needs a list or a mapping on the right, got {describe(container)}",
        source,
        node.right.position,
    )


def _call(node: Call, context: Mapping[str, Any], source: str) -> Value:
    """Evaluate a call to a whitelisted function.

    Parameters
    ----------
    node : Call
        The node to evaluate.
    context : mapping of str to object
        The evaluation context.
    source : str
        The original expression text.

    Returns
    -------
    Value
        The function's result.

    Raises
    ------
    ExprEvaluationError
        If an argument has the wrong type for the function.
    """
    args = [evaluate_node(argument, context, source) for argument in node.args]
    try:
        return call_function(node.name, args)
    except ValueError as error:
        raise ExprEvaluationError(str(error), source, node.position) from error


def _resolve_path(node: Path, context: Mapping[str, Any], source: str) -> Value:
    """Walk a dotted path through the evaluation context.

    Parameters
    ----------
    node : Path
        The path to resolve.
    context : mapping of str to object
        The evaluation context.
    source : str
        The original expression text.

    Returns
    -------
    Value
        The value the path names.

    Raises
    ------
    ExprEvaluationError
        If any segment is missing, or the path ends on something that is not a
        value — a method, a class, an engine object.
    """
    root = node.segments[0]
    if root not in context:
        raise ExprEvaluationError(
            f"there is nothing called `{root}` here; available: {_names(context)}",
            source,
            node.position,
        )

    current: Any = context[root]
    for depth, segment in enumerate(node.segments[1:], start=1):
        current = _step(current, segment, node, depth, source)

    return _as_value(current, node, source)


def _step(current: Any, segment: str, node: Path, depth: int, source: str) -> Any:
    """Take one segment of a path.

    Mappings are read by key and everything else by attribute. Underscored
    names were already refused by the parser, so no object's internals are
    reachable from content.

    Parameters
    ----------
    current : object
        What the path has reached so far.
    segment : str
        The next segment to read.
    node : Path
        The whole path, for error messages.
    depth : int
        Index of `segment` within the path.
    source : str
        The original expression text.

    Returns
    -------
    object
        The value at that segment, possibly an object to walk further.

    Raises
    ------
    ExprEvaluationError
        If the segment does not exist on `current`.
    """
    walked = ".".join(node.segments[:depth])

    if isinstance(current, Mapping):
        if segment in current:
            return current[segment]
        raise ExprEvaluationError(
            f"`{walked}` has no `{segment}`; available: {_names(current)}",
            source,
            node.position,
        )

    if current is None or isinstance(current, bool | int | float | str | Sequence):
        raise ExprEvaluationError(
            f"`{walked}` is {describe(current)} and has no `{segment}`",
            source,
            node.position,
        )

    try:
        return getattr(current, segment)
    except AttributeError as error:
        raise ExprEvaluationError(
            f"`{walked}` has no `{segment}`", source, node.position
        ) from error


def _as_value(current: Any, node: Path, source: str) -> Value:
    """Check that a resolved path ended on something the language can use.

    Parameters
    ----------
    current : object
        Whatever the path resolved to.
    node : Path
        The path, for error messages.
    source : str
        The original expression text.

    Returns
    -------
    Value
        The value, unchanged.

    Raises
    ------
    ExprEvaluationError
        If the path ended on a method, a class, or any other non-value. This is
        what stops content from reaching engine internals through a path.
    """
    if current is None or isinstance(current, bool | int | float | str):
        return current
    if isinstance(current, Mapping | Sequence) and not callable(current):
        return current
    raise ExprEvaluationError(
        f"`{node.dotted}` is not a value the expression language can read "
        f"(it is a {type(current).__name__})",
        source,
        node.position,
    )


def _names(container: Mapping[str, Any]) -> str:
    """List a mapping's keys for an error message.

    Parameters
    ----------
    container : mapping of str to object
        The mapping whose keys to list.

    Returns
    -------
    str
        Up to `_SUGGESTION_LIMIT` sorted keys, comma-separated.
    """
    keys = sorted(str(key) for key in container if not str(key).startswith("_"))
    if not keys:
        return "nothing"
    if len(keys) > _SUGGESTION_LIMIT:
        return ", ".join(keys[:_SUGGESTION_LIMIT]) + ", ..."
    return ", ".join(keys)
