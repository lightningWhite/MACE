"""The parsed shape of an expression.

Nodes are frozen dataclasses: an expression is parsed once when a pack loads and
then evaluated many times per playthrough, so the tree must be safe to share and
must never carry per-evaluation state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Value",
    "children",
    "Node",
    "Literal",
    "Path",
    "ListLiteral",
    "UnaryOp",
    "BinaryOp",
    "BoolOp",
    "Call",
]

#: Everything an expression may produce or read. Anything else reached through a
#: path — a function, a class, an engine object — is a content error, not a value.
type Value = bool | int | float | str | None | Mapping[str, Any] | Sequence[Any]


@dataclass(frozen=True, slots=True)
class Node:
    """Base class for every node in a parsed expression.

    Attributes
    ----------
    position : int
        Zero-based offset in the source text the node starts at, so evaluation
        errors can point at the offending part of the expression.
    """

    position: int


@dataclass(frozen=True, slots=True)
class Literal(Node):
    """A constant: a number, string, boolean, or `null`."""

    value: Value


@dataclass(frozen=True, slots=True)
class Path(Node):
    """A dotted lookup into the evaluation context, e.g. `player.stats.speed`."""

    segments: tuple[str, ...]

    @property
    def dotted(self) -> str:
        """Render the path the way the author wrote it.

        Returns
        -------
        str
            The segments joined with dots.
        """
        return ".".join(self.segments)


@dataclass(frozen=True, slots=True)
class ListLiteral(Node):
    """A bracketed list, e.g. `['rain', 'storm']`."""

    items: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class UnaryOp(Node):
    """A prefix operation: `-` or `not`."""

    op: str
    operand: Node


@dataclass(frozen=True, slots=True)
class BinaryOp(Node):
    """Arithmetic, comparison, or membership: `+ - * / % == != < <= > >= in`."""

    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class BoolOp(Node):
    """A short-circuiting `and` / `or`.

    Separate from `BinaryOp` because the right operand is only evaluated when
    the left one does not already settle the answer.
    """

    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Call(Node):
    """A call to one of the whitelisted functions."""

    name: str
    args: tuple[Node, ...]


def children(node: Node) -> tuple[Node, ...]:
    """List a node's sub-expressions.

    Parameters
    ----------
    node : Node
        The node to inspect.

    Returns
    -------
    tuple of Node
        The node's children, left to right; empty for literals and paths.
    """
    match node:
        case ListLiteral():
            return node.items
        case Call():
            return node.args
        case UnaryOp():
            return (node.operand,)
        case BinaryOp() | BoolOp():
            return (node.left, node.right)
        case _:
            return ()
