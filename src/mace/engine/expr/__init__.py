"""Safe evaluation of author-supplied conditions and effects.

Content packs are untrusted community input. Nothing here may use `eval` or
`exec`; author expressions go through a restricted parser and evaluator.
See docs/decisions/0003-structured-conditions-and-effects.md.

The language is deliberately small: comparisons, arithmetic, boolean logic,
dotted paths into a context, list literals, and four whitelisted functions
(`abs`, `count`, `max`, `min`). It has no assignment, no loops, no function
definitions, and no way to reach a Python callable — an expression can only ask
questions about a world it is handed.

    >>> from mace.engine.expr import parse
    >>> condition = parse("player.stats.hitpoints < 10 and 'rain' in world.weather")
    >>> condition.references
    ('player.stats.hitpoints', 'world.weather')
    >>> world = {"player": {"stats": {"hitpoints": 4}}, "world": {"weather": ["rain"]}}
    >>> condition.is_true(world)
    True

Grammar and semantics are documented in docs/04-schema-reference.md.
"""

from .errors import ExprError, ExprEvaluationError, ExprSyntaxError
from .expression import Expression, evaluate, is_true, parse
from .functions import FUNCTIONS
from .nodes import Value
from .values import truthy

__all__ = [
    "FUNCTIONS",
    "ExprError",
    "ExprEvaluationError",
    "ExprSyntaxError",
    "Expression",
    "Value",
    "evaluate",
    "is_true",
    "parse",
    "truthy",
]
