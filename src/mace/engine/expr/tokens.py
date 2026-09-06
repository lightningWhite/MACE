"""Hand-written scanner for the `expr` mini-language.

There is no regular expression engine and no `eval` here; content packs are
untrusted community input, so the grammar is read one character at a time and
anything unrecognised is a syntax error with a position.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import ExprSyntaxError

__all__ = ["Token", "TokenKind", "KEYWORDS", "MAX_SOURCE_LENGTH", "tokenize"]

#: Longest expression accepted. Untrusted content does not get to hand the
#: parser an arbitrarily large input; no honest condition comes near this.
MAX_SOURCE_LENGTH = 2000

#: Bare words with grammatical meaning. They may not be used as path segments.
KEYWORDS = frozenset({"and", "or", "not", "in", "true", "false", "null"})

#: Multi-character operators, longest first so `<=` wins over `<`.
_OPERATORS = (
    "==",
    "!=",
    "<=",
    ">=",
    "<",
    ">",
    "+",
    "-",
    "*",
    "/",
    "%",
    "(",
    ")",
    "[",
    "]",
    ",",
    ".",
)

#: Punctuation an author might reach for from another language, and the fix.
_MISSPELLINGS = {
    "=": "use `==` to compare",
    "&": "use `and`",
    "|": "use `or`",
    "!": "use `not` (or `!=` to compare)",
    "&&": "use `and`",
    "||": "use `or`",
}

#: Backslash escapes understood inside string literals.
_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "n": "\n", "t": "\t"}


class TokenKind(Enum):
    """What a token is, independent of its text."""

    NUMBER = "number"
    STRING = "string"
    NAME = "name"
    OP = "operator"
    END = "end of expression"


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical unit of an expression.

    Attributes
    ----------
    kind : TokenKind
        The token's category.
    text : str
        The exact source text, used in error messages.
    value : bool | int | float | str | None
        The decoded value for `NUMBER` and `STRING` tokens; `None` otherwise.
    position : int
        Zero-based offset of the token's first character in the source.
    """

    kind: TokenKind
    text: str
    value: int | float | str | None
    position: int


def tokenize(source: str) -> list[Token]:
    """Split an expression into tokens.

    Parameters
    ----------
    source : str
        The author's expression text.

    Returns
    -------
    list of Token
        The tokens, always ending with a single `END` token.

    Raises
    ------
    ExprSyntaxError
        If the source is over-long or contains a character sequence the
        grammar does not recognise.
    """
    if len(source) > MAX_SOURCE_LENGTH:
        raise ExprSyntaxError(
            f"expression is {len(source)} characters long; "
            f"the limit is {MAX_SOURCE_LENGTH}",
            source[:MAX_SOURCE_LENGTH],
            None,
        )

    tokens: list[Token] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]

        if char.isspace():
            index += 1
            continue

        if char.isdigit():
            token, index = _scan_number(source, index)
        elif char in "'\"":
            token, index = _scan_string(source, index)
        elif char.isalpha() or char == "_":
            token, index = _scan_name(source, index)
        else:
            token, index = _scan_operator(source, index)

        tokens.append(token)

    tokens.append(Token(TokenKind.END, "", None, length))
    return tokens


def _scan_number(source: str, start: int) -> tuple[Token, int]:
    """Scan an integer or decimal number beginning at `start`.

    Parameters
    ----------
    source : str
        The expression text.
    start : int
        Offset of the first digit.

    Returns
    -------
    tuple of (Token, int)
        The number token and the offset just past it.
    """
    index = start
    length = len(source)
    is_float = False

    while index < length and source[index].isdigit():
        index += 1

    if (
        index < length
        and source[index] == "."
        and index + 1 < length
        and source[index + 1].isdigit()
    ):
        is_float = True
        index += 1
        while index < length and source[index].isdigit():
            index += 1

    if index < length and source[index] in "eE":
        after = index + 1
        if after < length and source[after] in "+-":
            after += 1
        if after < length and source[after].isdigit():
            is_float = True
            index = after
            while index < length and source[index].isdigit():
                index += 1

    text = source[start:index]
    if index < length and (source[index].isalpha() or source[index] == "_"):
        raise ExprSyntaxError(f"`{text}{source[index]}` is not a number", source, start)

    value: int | float = float(text) if is_float else int(text)
    return Token(TokenKind.NUMBER, text, value, start), index


def _scan_string(source: str, start: int) -> tuple[Token, int]:
    """Scan a single- or double-quoted string beginning at `start`.

    Parameters
    ----------
    source : str
        The expression text.
    start : int
        Offset of the opening quote.

    Returns
    -------
    tuple of (Token, int)
        The string token and the offset just past the closing quote.
    """
    quote = source[start]
    index = start + 1
    length = len(source)
    parts: list[str] = []

    while index < length:
        char = source[index]
        if char == quote:
            text = source[start : index + 1]
            return Token(TokenKind.STRING, text, "".join(parts), start), index + 1
        if char == "\\":
            if index + 1 >= length:
                break
            escape = source[index + 1]
            if escape not in _ESCAPES:
                raise ExprSyntaxError(
                    f"`\\{escape}` is not a valid escape; use one of "
                    + ", ".join(f"\\{key}" for key in _ESCAPES),
                    source,
                    index,
                )
            parts.append(_ESCAPES[escape])
            index += 2
            continue
        parts.append(char)
        index += 1

    raise ExprSyntaxError(f"unterminated string: no closing `{quote}`", source, start)


def _scan_name(source: str, start: int) -> tuple[Token, int]:
    """Scan an identifier or keyword beginning at `start`.

    Parameters
    ----------
    source : str
        The expression text.
    start : int
        Offset of the first character.

    Returns
    -------
    tuple of (Token, int)
        The name token and the offset just past it.
    """
    index = start
    length = len(source)
    while index < length and (source[index].isalnum() or source[index] == "_"):
        index += 1
    return Token(TokenKind.NAME, source[start:index], None, start), index


def _scan_operator(source: str, start: int) -> tuple[Token, int]:
    """Scan a punctuation operator beginning at `start`.

    Parameters
    ----------
    source : str
        The expression text.
    start : int
        Offset of the first character.

    Returns
    -------
    tuple of (Token, int)
        The operator token and the offset just past it.

    Raises
    ------
    ExprSyntaxError
        If the character sequence is not part of the grammar.
    """
    for operator in _OPERATORS:
        if source.startswith(operator, start):
            return Token(TokenKind.OP, operator, None, start), start + len(operator)

    for candidate in (source[start : start + 2], source[start]):
        if candidate in _MISSPELLINGS:
            raise ExprSyntaxError(
                f"`{candidate}` is not part of the expression language "
                f"— {_MISSPELLINGS[candidate]}",
                source,
                start,
            )

    raise ExprSyntaxError(
        f"`{source[start]}` is not part of the expression language", source, start
    )
