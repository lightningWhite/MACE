"""Tests for the `expr` mini-language.

Three things are being pinned down here, in order of importance:

1. **Safety.** Content packs are untrusted input. No path may reach a Python
   callable, an object's internals, or unbounded work.
2. **Semantics.** Truthiness, equality, and precedence are written down so a
   second engine implementation can match them exactly.
3. **Error quality.** Authors are not programmers; every failure names the
   problem and points at the character.
"""

from collections.abc import Mapping
from typing import Any

import pytest

from mace.engine.expr import (
    Expression,
    ExprEvaluationError,
    ExprSyntaxError,
    evaluate,
    is_true,
    parse,
)

CONTEXT: Mapping[str, Any] = {
    "player": {
        "name": "Letholin",
        "stats": {"hitpoints": 12, "strength": 55, "speed": 40.5},
        "pools": {"hitpoints": {"current": 12, "max": 40}},
        "inventory": ["gold", "gold", "rope"],
        "flags": {"conscripted": True, "warned-the-king": False},
    },
    "world": {"day": 3, "weather": ["rain", "wind"], "tick": 96, "moon": None},
    "troll": {"disposition": "hostile", "stats": {"hitpoints": 60}},
}


def check(source: str, expected: object, context: Mapping[str, Any] = CONTEXT) -> None:
    """Assert that an expression evaluates to a value.

    Parameters
    ----------
    source : str
        The expression to evaluate.
    expected : object
        The value it must produce.
    context : mapping of str to object
        The evaluation context. Defaults to the shared fixture world.
    """
    assert evaluate(source, context) == expected


# -- literals and paths ---------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1", 1),
        ("1.5", 1.5),
        ("1e3", 1000.0),
        ("2.5e-2", 0.025),
        ("'rain'", "rain"),
        ('"rain"', "rain"),
        ("'it\\'s'", "it's"),
        ("'a\\nb'", "a\nb"),
        ("true", True),
        ("false", False),
        ("null", None),
        ("[]", []),
        ("[1, 2, 3]", [1, 2, 3]),
        ("[1, 2,]", [1, 2]),
    ],
)
def test_literals(source: str, expected: object) -> None:
    check(source, expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("world.day", 3),
        ("player.name", "Letholin"),
        ("player.stats.hitpoints", 12),
        ("player.pools.hitpoints.max", 40),
        ("player.flags.conscripted", True),
        ("world.moon", None),
        ("player.inventory", ["gold", "gold", "rope"]),
    ],
)
def test_paths_read_the_context(source: str, expected: object) -> None:
    check(source, expected)


def test_paths_read_attributes_of_objects() -> None:
    class Clock:
        """A stand-in for an engine object exposed to content."""

        def __init__(self) -> None:
            self.day = 7
            self.season = "autumn"

    check("world.clock.day", 7, {"world": {"clock": Clock()}})


# -- operators ------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 - 2 - 3", 5),
        ("7 % 3", 1),
        ("7 / 2", 3.5),
        ("-3 + 1", -2),
        ("- -3", 3),
        ("2 * player.stats.hitpoints", 24),
        ("player.pools.hitpoints.max * 0.25", 10.0),
    ],
)
def test_arithmetic(source: str, expected: object) -> None:
    check(source, expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1 < 2", True),
        ("2 <= 2", True),
        ("3 > 4", False),
        ("3 >= 4", False),
        ("world.day == 3", True),
        ("world.day != 3", False),
        ("player.name == 'Letholin'", True),
        ("troll.disposition != 'hostile'", False),
        ("world.moon == null", True),
        ("player.stats.hitpoints < player.pools.hitpoints.max * 0.25", False),
    ],
)
def test_comparisons(source: str, expected: object) -> None:
    check(source, expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("'rain' in world.weather", True),
        ("'snow' in world.weather", False),
        ("'snow' not in world.weather", True),
        ("'conscripted' in player.flags", True),
        ("'gold' in player.inventory", True),
        ("2 in [1, 2, 3]", True),
    ],
)
def test_membership(source: str, expected: object) -> None:
    check(source, expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("true and false", False),
        ("true or false", True),
        ("not true", False),
        ("not false", True),
        ("false or 1 < 2", True),
        ("world.day > 1 and 'rain' in world.weather", True),
        ("not (world.day > 1 and world.day < 10)", False),
        # `and` binds tighter than `or`
        ("true or false and false", True),
        ("(true or false) and false", False),
        # `not` binds looser than a comparison
        ("not world.day == 3", False),
    ],
)
def test_boolean_logic(source: str, expected: object) -> None:
    check(source, expected)


def test_boolean_operators_return_booleans_not_operands() -> None:
    # Python would answer 2 and 0 here; the language answers true and false, so
    # that a condition never leaks a number into a place expecting a boolean.
    check("2 and 3", True)
    check("0 or 0", False)


def test_boolean_operators_short_circuit() -> None:
    # The right side names a path that does not exist. If it were evaluated the
    # expression would raise, so this passing *is* the short-circuit test.
    check("false and missing.path", False)
    check("true or missing.path", True)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("''", ""),
        ("not ''", True),
        ("not 'x'", False),
        ("not 0", True),
        ("not 0.0", True),
        ("not 1", False),
        ("not []", True),
        ("not [0]", False),
        ("not null", True),
        ("not player.flags", False),
    ],
)
def test_truthiness(source: str, expected: object) -> None:
    check(source, expected)


def test_equality_does_not_cross_types() -> None:
    # Python says True == 1. An author who writes `flag == 1` has made a
    # mistake, and quietly agreeing with them hides it.
    check("true == 1", False)
    check("false == 0", False)
    check("true == true", True)
    check("1 == 1.0", True)
    check("'1' == 1", False)


# -- functions ------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("abs(-3)", 3),
        ("abs(3.5)", 3.5),
        ("min(4, 2, 9)", 2),
        ("max(4, 2, 9)", 9),
        ("min([4, 2, 9])", 2),
        ("max(player.stats.hitpoints, 20)", 20),
        ("count(player.inventory)", 3),
        ("count(player.flags)", 2),
        ("count('rain')", 4),
        ("count(world.weather) == 2", True),
    ],
)
def test_functions(source: str, expected: object) -> None:
    check(source, expected)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("sqrt(4)", "there is no function called `sqrt`"),
        ("open('/etc/passwd')", "there is no function called `open`"),
        ("abs()", "takes exactly 1 argument"),
        ("abs(1, 2)", "takes exactly 1 argument"),
    ],
)
def test_only_whitelisted_functions_parse(source: str, message: str) -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse(source)
    assert message in caught.value.message


@pytest.mark.parametrize(
    "source",
    ["abs('x')", "min([])", "count(3)", "max(1, 'two')"],
)
def test_functions_reject_wrong_argument_types(source: str) -> None:
    with pytest.raises(ExprEvaluationError):
        evaluate(source, CONTEXT)


# -- safety ---------------------------------------------------------------


class Sneaky:
    """An engine object of the kind content might be handed."""

    secret = "do not read me"

    def __init__(self) -> None:
        self.name = "gorm"

    def wipe(self) -> None:  # pragma: no cover - must never be reachable
        raise AssertionError("content reached a method")


@pytest.mark.parametrize(
    "source",
    [
        "player.__class__",
        "player._private",
        "player.stats.__dict__",
        "_x",
    ],
)
def test_underscored_names_are_refused_at_parse_time(source: str) -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse(source)
    assert "_" in caught.value.message


def test_paths_may_not_end_on_a_callable() -> None:
    with pytest.raises(ExprEvaluationError) as caught:
        evaluate("gorm.wipe", {"gorm": Sneaky()})
    assert "not a value" in caught.value.message


def test_methods_cannot_be_called() -> None:
    # `wipe` is not a whitelisted function name, so this never reaches a lookup.
    with pytest.raises(ExprSyntaxError):
        parse("gorm.wipe()")


def test_deep_nesting_is_rejected_rather_than_crashing() -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse("(" * 200 + "1" + ")" * 200)
    assert "nests more than" in caught.value.message


def test_long_chains_are_rejected_rather_than_crashing() -> None:
    # A flat loop in the parser still builds a deep tree, and it is the
    # *evaluator* that would recurse through it. The limit is on the tree.
    with pytest.raises(ExprSyntaxError) as caught:
        parse("1 + " * 400 + "1")
    assert "nests more than" in caught.value.message


def test_expressions_at_the_limit_still_evaluate() -> None:
    # One below the limit, in both shapes, to show the guard is not off by one
    # in the direction that would reject honest content.
    assert evaluate("(" * 30 + "1" + ")" * 30, CONTEXT) == 1
    assert evaluate("1 + " * 30 + "1", CONTEXT) == 31


def test_long_sources_are_rejected() -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse("1 + " * 2000 + "1")
    assert "the limit is" in caught.value.message


# -- errors ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "the expression is empty"),
        ("1 +", "the expression ends early"),
        ("1 + * 2", "expected a value"),
        ("(1 + 2", "unclosed `(`"),
        ("[1, 2", "unclosed `["),
        ("1 2", "unexpected `2`"),
        ("world.day = 3", "use `==` to compare"),
        ("a && b", "use `and`"),
        ("a || b", "use `or`"),
        ("!a", "use `not`"),
        ("1 < 2 < 3", "cannot be chained"),
        ("world.", "expected a name"),
        ("world.and", "is a keyword"),
        ("'unclosed", "unterminated string"),
        ("1 ~ 2", "not part of the expression language"),
        ("'a\\qb'", "not a valid escape"),
    ],
)
def test_syntax_errors_explain_themselves(source: str, message: str) -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse(source)
    assert message in caught.value.message


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("dragon.disposition", "there is nothing called `dragon`"),
        ("player.hitponts", "has no `hitponts`"),
        ("player.stats.hitpoints.max", "is a number (12) and has no `max`"),
        ("world.day + 'x'", "needs numbers"),
        ("world.day < 'x'", "compares numbers"),
        ("1 / 0", "cannot divide by zero"),
        ("1 % 0", "cannot divide by zero"),
        ("-player.name", "needs a number"),
        ("'a' in player.name", "needs a list or a mapping"),
        ("1 in world.day", "needs a list or a mapping"),
    ],
)
def test_evaluation_errors_explain_themselves(source: str, message: str) -> None:
    with pytest.raises(ExprEvaluationError) as caught:
        evaluate(source, CONTEXT)
    assert message in caught.value.message


def test_unknown_root_lists_what_is_available() -> None:
    with pytest.raises(ExprEvaluationError) as caught:
        evaluate("dragon.disposition", CONTEXT)
    assert "player, troll, world" in caught.value.message


def test_unknown_field_lists_what_is_available() -> None:
    with pytest.raises(ExprEvaluationError) as caught:
        evaluate("player.stats.hitponts", CONTEXT)
    assert "hitpoints, speed, strength" in caught.value.message


def test_errors_point_at_the_character() -> None:
    with pytest.raises(ExprSyntaxError) as caught:
        parse("world.day > = 3")
    rendered = str(caught.value)
    assert "world.day > = 3" in rendered
    assert rendered.splitlines()[-1] == "  " + " " * 12 + "^"


# -- the Expression object ------------------------------------------------


def test_parse_collects_references_for_the_validator() -> None:
    expression = parse(
        "player.stats.hitpoints < player.pools.hitpoints.max * 0.25 "
        "and 'rain' in world.weather and count(player.inventory) > 0"
    )
    assert expression.references == (
        "player.inventory",
        "player.pools.hitpoints.max",
        "player.stats.hitpoints",
        "world.weather",
    )
    assert expression.roots == ("player", "world")


def test_expression_round_trips_its_source() -> None:
    source = "world.day > 7"
    assert str(parse(source)) == source


def test_expression_is_reusable_and_immutable() -> None:
    expression = parse("world.day > 2")
    assert expression.is_true(CONTEXT)
    assert not expression.is_true({"world": {"day": 1}})
    assert expression.is_true(CONTEXT)
    with pytest.raises(AttributeError):
        expression.source = "world.day > 3"  # type: ignore[misc]


def test_is_true_applies_truthiness() -> None:
    assert is_true("player.inventory", CONTEXT)
    assert not is_true("world.moon", CONTEXT)


def test_evaluate_accepts_a_parsed_expression() -> None:
    expression = parse("world.day")
    assert isinstance(expression, Expression)
    assert evaluate(expression, CONTEXT) == 3


def test_evaluation_is_deterministic() -> None:
    source = "min(world.day * 3, count(player.inventory) + 7) / 2"
    results = {evaluate(source, CONTEXT) for _ in range(50)}
    assert results == {4.5}
