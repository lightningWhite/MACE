"""Errors raised while parsing or evaluating author expressions.

Every error carries the source text and, where known, the character position it
came from, so a front-end or the validator can point an author at the exact
character rather than at a stack trace.
"""

from __future__ import annotations

__all__ = ["ExprError", "ExprSyntaxError", "ExprEvaluationError"]


class ExprError(Exception):
    """Base class for every expression failure.

    Parameters
    ----------
    message : str
        What went wrong, phrased for a content author rather than a programmer.
    source : str
        The full expression text the error came from.
    position : int or None
        Zero-based character offset in `source` the error points at, if known.
    """

    def __init__(self, message: str, source: str, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.position = position

    def __str__(self) -> str:
        """Render the message above the source with a caret under the position.

        Returns
        -------
        str
            A multi-line, author-readable rendering of the failure.
        """
        if self.position is None:
            return f"{self.message}\n  {self.source}"
        caret = " " * max(self.position, 0) + "^"
        return f"{self.message}\n  {self.source}\n  {caret}"


class ExprSyntaxError(ExprError):
    """The expression could not be parsed.

    Raised at pack-load time, so authors hear about it before play starts.
    """


class ExprEvaluationError(ExprError):
    """The expression parsed but could not be evaluated against a context.

    An unknown path, a type mismatch, or a division by zero. Never silently
    coerced to `false`: a condition that cannot be answered is a content bug,
    and hiding it is how a game ends up quietly unplayable.
    """
