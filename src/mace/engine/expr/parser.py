"""Recursive-descent parser for the `expr` mini-language.

The grammar, loosest binding first::

    expression  := or
    or          := and ( "or" and )*
    and         := not ( "and" not )*
    not         := "not" not | comparison
    comparison  := sum ( ( "==" | "!=" | "<" | "<=" | ">" | ">=" | "in"
                         | "not" "in" ) sum )?
    sum         := product ( ( "+" | "-" ) product )*
    product     := unary ( ( "*" | "/" | "%" ) unary )*
    unary       := ( "-" | "+" ) unary | primary
    primary     := number | string | "true" | "false" | "null"
                 | list | call | path | "(" expression ")"
    list        := "[" ( expression ( "," expression )* ","? )? "]"
    call        := NAME "(" ( expression ( "," expression )* )? ")"
    path        := NAME ( "." NAME )*

There is no assignment, no loop, no lambda, and no way to define a name: the
language can only ask questions about a world it is handed. That is the point.
"""

from __future__ import annotations

from .errors import ExprSyntaxError
from .functions import FUNCTIONS
from .nodes import (
    BinaryOp,
    BoolOp,
    Call,
    ListLiteral,
    Literal,
    Node,
    Path,
    UnaryOp,
    children,
)
from .tokens import KEYWORDS, Token, TokenKind, tokenize

__all__ = ["MAX_DEPTH", "parse_tokens"]

#: How deeply a parsed expression may nest. Untrusted content does not get to
#: exhaust the interpreter stack — of the parser here, or of the evaluator later.
#: A long chain such as `a + b + c + ...` nests one level per step, so this
#: bounds those too. No honest condition comes near it.
MAX_DEPTH = 32

#: Constants spelled as bare words, using YAML's spelling rather than Python's.
_CONSTANTS: dict[str, bool | None] = {"true": True, "false": False, "null": None}

_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})
_SUM_OPS = frozenset({"+", "-"})
_PRODUCT_OPS = frozenset({"*", "/", "%"})


def parse_tokens(source: str) -> Node:
    """Parse an expression into a tree.

    Parameters
    ----------
    source : str
        The author's expression text.

    Returns
    -------
    Node
        The root of the parsed expression.

    Raises
    ------
    ExprSyntaxError
        If the text is not a well-formed expression.
    """
    root = _Parser(source, tokenize(source)).parse()
    _check_depth(root, source)
    return root


def _check_depth(root: Node, source: str) -> None:
    """Reject a parsed tree that nests deeper than `MAX_DEPTH`.

    The parser guards its own recursion as it goes, but a left-associative
    chain (`1 + 1 + 1 + ...`) builds a deep tree from a flat loop, and it is the
    *evaluator* that would then recurse through it. Checking the finished tree
    catches both shapes with one rule.

    Parameters
    ----------
    root : Node
        The parsed expression.
    source : str
        The expression text, for error rendering.

    Raises
    ------
    ExprSyntaxError
        If any part of the tree is deeper than `MAX_DEPTH`.
    """
    pending: list[tuple[Node, int]] = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise ExprSyntaxError(
                f"the expression nests more than {MAX_DEPTH} levels deep; "
                "split it into several conditions",
                source,
                node.position,
            )
        pending.extend((child, depth + 1) for child in children(node))


class _Parser:
    """One-shot parser over a token list.

    Parameters
    ----------
    source : str
        The expression text, kept for error rendering.
    tokens : list of Token
        The scanned tokens, ending with an `END` token.
    """

    def __init__(self, source: str, tokens: list[Token]) -> None:
        self._source = source
        self._tokens = tokens
        self._index = 0
        self._depth = 0

    def parse(self) -> Node:
        """Parse the whole token list.

        Returns
        -------
        Node
            The root node.

        Raises
        ------
        ExprSyntaxError
            If the expression is empty or has trailing tokens.
        """
        if self._peek().kind is TokenKind.END:
            raise self._error("the expression is empty", self._peek())
        node = self._parse_or()
        trailing = self._peek()
        if trailing.kind is not TokenKind.END:
            raise self._error(
                f"unexpected `{trailing.text}` after the expression", trailing
            )
        return node

    # -- grammar ---------------------------------------------------------

    def _parse_or(self) -> Node:
        """Parse `a or b`.

        Returns
        -------
        Node
            The parsed node.
        """
        node = self._parse_and()
        while self._at_keyword("or"):
            token = self._advance()
            node = BoolOp(token.position, "or", node, self._parse_and())
        return node

    def _parse_and(self) -> Node:
        """Parse `a and b`.

        Returns
        -------
        Node
            The parsed node.
        """
        node = self._parse_not()
        while self._at_keyword("and"):
            token = self._advance()
            node = BoolOp(token.position, "and", node, self._parse_not())
        return node

    def _parse_not(self) -> Node:
        """Parse `not a`.

        Returns
        -------
        Node
            The parsed node.
        """
        if self._at_keyword("not"):
            token = self._advance()
            with _Depth(self):
                return UnaryOp(token.position, "not", self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> Node:
        """Parse a single, non-chained comparison or membership test.

        Returns
        -------
        Node
            The parsed node.

        Raises
        ------
        ExprSyntaxError
            If comparisons are chained, e.g. `1 < x < 10`.
        """
        left = self._parse_sum()
        operator = self._comparison_operator()
        if operator is None:
            return left

        token = self._advance()
        if operator == "not in":
            self._advance()
        node = BinaryOp(token.position, operator, left, self._parse_sum())

        if self._comparison_operator() is not None:
            raise self._error(
                "comparisons cannot be chained; write `a < b and b < c`", self._peek()
            )
        return node

    def _parse_sum(self) -> Node:
        """Parse `a + b` and `a - b`.

        Returns
        -------
        Node
            The parsed node.
        """
        node = self._parse_product()
        while self._at_operator(_SUM_OPS):
            token = self._advance()
            node = BinaryOp(token.position, token.text, node, self._parse_product())
        return node

    def _parse_product(self) -> Node:
        """Parse `a * b`, `a / b`, and `a % b`.

        Returns
        -------
        Node
            The parsed node.
        """
        node = self._parse_unary()
        while self._at_operator(_PRODUCT_OPS):
            token = self._advance()
            node = BinaryOp(token.position, token.text, node, self._parse_unary())
        return node

    def _parse_unary(self) -> Node:
        """Parse a leading `-` or `+`.

        Returns
        -------
        Node
            The parsed node.
        """
        if self._at_operator(_SUM_OPS):
            token = self._advance()
            with _Depth(self):
                return UnaryOp(token.position, token.text, self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Node:
        """Parse a literal, list, call, path, or parenthesised expression.

        Returns
        -------
        Node
            The parsed node.

        Raises
        ------
        ExprSyntaxError
            If the next token cannot begin a value.
        """
        with _Depth(self):
            token = self._peek()

            if token.kind is TokenKind.NUMBER or token.kind is TokenKind.STRING:
                self._advance()
                return Literal(token.position, token.value)

            if token.kind is TokenKind.NAME:
                if token.text in _CONSTANTS:
                    self._advance()
                    return Literal(token.position, _CONSTANTS[token.text])
                if token.text in KEYWORDS:
                    raise self._error(
                        f"`{token.text}` needs something before it", token
                    )
                if self._peek(1).text == "(" and self._peek(1).kind is TokenKind.OP:
                    return self._parse_call()
                return self._parse_path()

            if token.kind is TokenKind.OP and token.text == "(":
                self._advance()
                node = self._parse_or()
                self._expect(")", "unclosed `(`")
                return node

            if token.kind is TokenKind.OP and token.text == "[":
                return self._parse_list()

            if token.kind is TokenKind.END:
                raise self._error(
                    "the expression ends early; something is missing", token
                )

            raise self._error(f"expected a value, found `{token.text}`", token)

    def _parse_list(self) -> Node:
        """Parse a bracketed list literal.

        Returns
        -------
        Node
            The parsed `ListLiteral`.
        """
        start = self._advance()
        items: list[Node] = []
        while not (self._peek().kind is TokenKind.OP and self._peek().text == "]"):
            items.append(self._parse_or())
            if self._peek().kind is TokenKind.OP and self._peek().text == ",":
                self._advance()
                continue
            break
        self._expect("]", "unclosed `[`")
        return ListLiteral(start.position, tuple(items))

    def _parse_call(self) -> Node:
        """Parse a call to a whitelisted function.

        Returns
        -------
        Node
            The parsed `Call`.

        Raises
        ------
        ExprSyntaxError
            If the function is not whitelisted or the arity is wrong.
        """
        name = self._advance()
        if name.text not in FUNCTIONS:
            available = ", ".join(sorted(FUNCTIONS))
            raise self._error(
                f"there is no function called `{name.text}`; available: {available}",
                name,
            )

        self._advance()  # the "(" the caller already looked ahead at
        args: list[Node] = []
        while not (self._peek().kind is TokenKind.OP and self._peek().text == ")"):
            args.append(self._parse_or())
            if self._peek().kind is TokenKind.OP and self._peek().text == ",":
                self._advance()
                continue
            break
        self._expect(")", f"unclosed `(` after `{name.text}`")

        spec = FUNCTIONS[name.text]
        if len(args) < spec.min_args or (
            spec.max_args is not None and len(args) > spec.max_args
        ):
            wanted = _arity(spec.min_args, spec.max_args)
            raise self._error(f"`{name.text}` takes {wanted}, got {len(args)}", name)
        return Call(name.position, name.text, tuple(args))

    def _parse_path(self) -> Node:
        """Parse a dotted path into the evaluation context.

        Returns
        -------
        Node
            The parsed `Path`.

        Raises
        ------
        ExprSyntaxError
            If a segment is a keyword or starts with an underscore. Underscored
            names are refused so that content can never walk into an object's
            internals — packs are untrusted input.
        """
        first = self._peek()
        segments: list[str] = [self._path_segment()]
        while self._peek().kind is TokenKind.OP and self._peek().text == ".":
            self._advance()
            segments.append(self._path_segment())
        return Path(first.position, tuple(segments))

    def _path_segment(self) -> str:
        """Read one name of a dotted path.

        Returns
        -------
        str
            The segment's text.

        Raises
        ------
        ExprSyntaxError
            If the segment is missing, a keyword, or underscore-prefixed.
        """
        token = self._peek()
        if token.kind is not TokenKind.NAME:
            raise self._error(
                f"expected a name, found `{token.text or 'nothing'}`", token
            )
        if token.text.startswith("_"):
            raise self._error(
                f"`{token.text}` may not start with `_`; underscored names "
                "are not readable from content",
                token,
            )
        if token.text in KEYWORDS:
            raise self._error(
                f"`{token.text}` is a keyword and cannot be part of a path", token
            )
        self._advance()
        return token.text

    # -- token helpers ---------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        """Look at a token without consuming it.

        Parameters
        ----------
        ahead : int
            How many tokens past the current one to look.

        Returns
        -------
        Token
            The token, or the final `END` token past the end.
        """
        index = min(self._index + ahead, len(self._tokens) - 1)
        return self._tokens[index]

    def _advance(self) -> Token:
        """Consume and return the current token.

        Returns
        -------
        Token
            The consumed token.
        """
        token = self._peek()
        if self._index < len(self._tokens) - 1:
            self._index += 1
        return token

    def _expect(self, text: str, message: str) -> Token:
        """Consume a specific operator or fail.

        Parameters
        ----------
        text : str
            The operator expected.
        message : str
            What to say if it is not there.

        Returns
        -------
        Token
            The consumed token.

        Raises
        ------
        ExprSyntaxError
            If the current token is not the expected operator.
        """
        token = self._peek()
        if token.kind is not TokenKind.OP or token.text != text:
            raise self._error(f"{message}: expected `{text}`", token)
        return self._advance()

    def _at_keyword(self, keyword: str) -> bool:
        """Say whether the current token is a given keyword.

        Parameters
        ----------
        keyword : str
            The keyword to look for.

        Returns
        -------
        bool
            True if the current token is that keyword.
        """
        token = self._peek()
        return token.kind is TokenKind.NAME and token.text == keyword

    def _at_operator(self, operators: frozenset[str]) -> bool:
        """Say whether the current token is one of a set of operators.

        Parameters
        ----------
        operators : frozenset of str
            The operators to look for.

        Returns
        -------
        bool
            True if the current token is one of them.
        """
        token = self._peek()
        return token.kind is TokenKind.OP and token.text in operators

    def _comparison_operator(self) -> str | None:
        """Identify a comparison or membership operator at the cursor.

        Returns
        -------
        str or None
            The operator (`in` and `not in` included), or `None` if the current
            token does not start one.
        """
        token = self._peek()
        if token.kind is TokenKind.OP and token.text in _COMPARISONS:
            return token.text
        if self._at_keyword("in"):
            return "in"
        if self._at_keyword("not") and self._peek(1).text == "in":
            return "not in"
        return None

    def enter_nesting(self) -> None:
        """Descend one level of nesting.

        Raises
        ------
        ExprSyntaxError
            If the expression nests deeper than `MAX_DEPTH`. Untrusted content
            does not get to exhaust the interpreter stack.
        """
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise self._error(
                f"the expression nests more than {MAX_DEPTH} levels deep; "
                "split it into several conditions",
                self._peek(),
            )

    def leave_nesting(self) -> None:
        """Ascend one level of nesting."""
        self._depth -= 1

    def _error(self, message: str, token: Token) -> ExprSyntaxError:
        """Build a syntax error positioned at a token.

        Parameters
        ----------
        message : str
            What went wrong.
        token : Token
            The token to point the caret at.

        Returns
        -------
        ExprSyntaxError
            The error, for the caller to raise.
        """
        return ExprSyntaxError(message, self._source, token.position)


class _Depth:
    """Context manager enforcing `MAX_DEPTH` on nested sub-expressions.

    Parameters
    ----------
    parser : _Parser
        The parser whose depth counter to guard.
    """

    def __init__(self, parser: _Parser) -> None:
        self._parser = parser

    def __enter__(self) -> None:
        """Enter one level of nesting."""
        self._parser.enter_nesting()

    def __exit__(self, *exc_info: object) -> None:
        """Leave one level of nesting."""
        self._parser.leave_nesting()


def _arity(minimum: int, maximum: int | None) -> str:
    """Describe an argument count in words.

    Parameters
    ----------
    minimum : int
        Fewest arguments accepted.
    maximum : int or None
        Most arguments accepted, or `None` for no upper bound.

    Returns
    -------
    str
        A phrase such as `exactly 1 argument` or `at least 1 argument`.
    """
    plural = "" if minimum == 1 else "s"
    if maximum is None:
        return f"at least {minimum} argument{plural}"
    if maximum == minimum:
        return f"exactly {minimum} argument{plural}"
    return f"between {minimum} and {maximum} arguments"
