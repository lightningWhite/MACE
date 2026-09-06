"""The public face of the expression language: parse once, evaluate many times.

Packs are parsed at load time, so a typo in a condition is a load-time error
with a file, an id, and a caret — not a surprise three hours into a playthrough.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .evaluator import evaluate_node
from .nodes import Node, Path, Value, children
from .parser import parse_tokens
from .values import truthy

__all__ = ["Expression", "parse", "evaluate", "is_true"]


@dataclass(frozen=True, slots=True)
class Expression:
    """A parsed, reusable author expression.

    Attributes
    ----------
    source : str
        The text the author wrote, kept for error messages and round-tripping
        back into YAML unchanged.
    root : Node
        The parsed tree.
    references : tuple of str
        Every dotted path the expression reads, sorted and de-duplicated. The
        content validator uses this to check paths against the vocabulary a
        pack is allowed to read, which is how `player.hitponts` gets caught at
        author time rather than at play time.
    """

    source: str
    root: Node
    references: tuple[str, ...]

    def evaluate(self, context: Mapping[str, Any]) -> Value:
        """Evaluate the expression against a context.

        Parameters
        ----------
        context : mapping of str to object
            Root names the expression may read, e.g. `{"player": ..., "world": ...}`.

        Returns
        -------
        Value
            The expression's value.

        Raises
        ------
        ExprEvaluationError
            If a path is unknown or a type is wrong.
        """
        return evaluate_node(self.root, context, self.source)

    def is_true(self, context: Mapping[str, Any]) -> bool:
        """Evaluate the expression as a condition.

        Parameters
        ----------
        context : mapping of str to object
            The evaluation context.

        Returns
        -------
        bool
            The result's truthiness, per `mace.engine.expr.values.truthy`.
        """
        return truthy(self.evaluate(context))

    @property
    def roots(self) -> tuple[str, ...]:
        """Name the context entries the expression needs.

        Returns
        -------
        tuple of str
            The first segment of every path, sorted and de-duplicated —
            `("player", "world")` and so on.
        """
        return tuple(sorted({reference.split(".")[0] for reference in self.references}))

    def __str__(self) -> str:
        """Render the expression as the author wrote it.

        Returns
        -------
        str
            The original source text.
        """
        return self.source


def parse(source: str) -> Expression:
    """Parse an expression.

    Parameters
    ----------
    source : str
        The author's expression text, e.g. the value of a `{expr: "..."}` node.

    Returns
    -------
    Expression
        The parsed expression, ready to evaluate against any context.

    Raises
    ------
    ExprSyntaxError
        If the text is not a well-formed expression.
    """
    root = parse_tokens(source)
    references = tuple(sorted({node.dotted for node in _paths(root)}))
    return Expression(source=source, root=root, references=references)


def evaluate(expression: Expression | str, context: Mapping[str, Any]) -> Value:
    """Evaluate an expression, parsing it first if it is still text.

    Parameters
    ----------
    expression : Expression or str
        A parsed expression, or source to parse. Content should be parsed once
        at load time; the string form is a convenience for tests and one-offs.
    context : mapping of str to object
        The evaluation context.

    Returns
    -------
    Value
        The expression's value.
    """
    parsed = parse(expression) if isinstance(expression, str) else expression
    return parsed.evaluate(context)


def is_true(expression: Expression | str, context: Mapping[str, Any]) -> bool:
    """Evaluate an expression as a condition.

    Parameters
    ----------
    expression : Expression or str
        A parsed expression, or source to parse.
    context : mapping of str to object
        The evaluation context.

    Returns
    -------
    bool
        The result's truthiness.
    """
    return truthy(evaluate(expression, context))


def _paths(node: Node) -> Iterator[Path]:
    """Walk a parsed tree, yielding every path it reads.

    Parameters
    ----------
    node : Node
        The root to walk.

    Yields
    ------
    Path
        Each path node, in no particular order.
    """
    pending = [node]
    while pending:
        current = pending.pop()
        if isinstance(current, Path):
            yield current
        pending.extend(children(current))
