"""Field types: what a step is asking for, as data.

A field says what kind of answer a step wants and how to turn one into content.
It does not print anything and does not read anything — the CLI renders these
and so will the web client, which is the whole reason they are declarative
(docs/09-authoring-and-wizard.md § The flow graph).

Two methods carry most of the weight. `describe` says what the current value
is, in English, and is what the task list and the review screens show.
`parse` turns one line of typed text into an authored value, which is what
makes the terminal renderer thin and this module testable without a terminal.

Some fields cannot be answered on one line — a condition is built by a
cascade, a repeat is a list of sub-answers. Those raise `NotOneLine` from
`parse` and declare `interactive = True`, and every front-end that offers them
drives the matching builder. `MapEditor` is the case the docs call out
specifically: it is a drag-and-drop field in a browser and a pair of numbers in
a terminal, and the terminal form is a fallback rather than a refusal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from mace.wizard.query import Catalog, Option

__all__ = [
    "Bool",
    "ConditionBuilder",
    "EffectBuilder",
    "Field",
    "Fixed",
    "Invalid",
    "MapEditor",
    "MultiSelect",
    "NotOneLine",
    "Number",
    "Repeat",
    "Select",
    "Source",
    "StatAllocator",
    "Text",
    "TextList",
]


class Invalid(Exception):
    """What the author typed cannot be turned into an answer.

    Carries a message written for them rather than for a log — the front-end
    prints it and asks again.
    """


class NotOneLine(Exception):
    """This field is not answered by typing a line, and never was.

    Raised by `parse` on the fields a builder drives. Front-ends check
    `interactive` first; this exists so one that forgets gets an error rather
    than a wrong answer.
    """


class Source(Protocol):
    """Anything that can produce a list of options."""

    def options(self, catalog: Catalog) -> tuple[Option, ...]:
        """The options on offer.

        Parameters
        ----------
        catalog : Catalog
            What exists.

        Returns
        -------
        tuple of Option
            The choices.
        """
        ...  # pragma: no cover — protocol


@dataclass(frozen=True, slots=True)
class Fixed:
    """A fixed list of options, for a field whose choices are not content.

    An entity's `kind` is one of five words the engine knows about; it is not
    something an author defines, so it does not come from a `Query`.

    Attributes
    ----------
    choices : tuple of Option
        The options, in offer order.
    """

    choices: tuple[Option, ...]

    @classmethod
    def of(cls, *values: str | tuple[str, str]) -> Fixed:
        """Build from bare values, or from value/label pairs.

        Parameters
        ----------
        *values
            A value, or a `(value, label)` pair.

        Returns
        -------
        Fixed
            The option list.
        """
        return cls(
            tuple(
                (
                    Option(value=v, label=v.replace("-", " "))
                    if isinstance(v, str)
                    else Option(value=v[0], label=v[1])
                )
                for v in values
            )
        )

    def options(self, catalog: Catalog) -> tuple[Option, ...]:
        """The fixed choices.

        Parameters
        ----------
        catalog : Catalog
            Ignored; the choices do not depend on content.

        Returns
        -------
        tuple of Option
            The choices.
        """
        return self.choices


@dataclass(frozen=True, slots=True)
class Field:
    """Base class for every field type.

    Attributes
    ----------
    optional : bool
        Whether an empty answer is allowed. A required field with no answer is
        what the task list counts as unfinished; it never blocks saving.
    """

    kind: ClassVar[str] = "field"

    #: Whether a builder drives this field rather than a line of typed text.
    interactive: ClassVar[bool] = False

    optional: bool = False

    def describe(self, value: Any, catalog: Catalog) -> str:
        """Say what the current value is.

        Parameters
        ----------
        value : object
            The authored value, or None.
        catalog : Catalog
            What exists, for naming references.

        Returns
        -------
        str
            A phrase for the review screen, or `—` for nothing yet.
        """
        return "—" if value is None else str(value)

    def parse(self, typed: str, catalog: Catalog) -> Any:
        """Turn a line of typed text into an authored value.

        Parameters
        ----------
        typed : str
            What the author typed, already stripped.
        catalog : Catalog
            What exists.

        Returns
        -------
        object
            The authored value, or None for an empty answer.

        Raises
        ------
        Invalid
            If it cannot be read as an answer.
        NotOneLine
            If this field is driven by a builder instead.
        """
        return typed or None

    def hint(self, catalog: Catalog) -> str:
        """A short line saying what kind of answer this is.

        Parameters
        ----------
        catalog : Catalog
            What exists.

        Returns
        -------
        str
            The hint, or an empty string when the title says enough.
        """
        return ""


@dataclass(frozen=True, slots=True)
class Text(Field):
    """A line, or a paragraph.

    Attributes
    ----------
    placeholder : str
        An example, shown as the hint. Worth writing: an author staring at
        `Description:` writes a label, and an author staring at "A stone span
        over black water" writes prose.
    """

    kind: ClassVar[str] = "text"

    placeholder: str = ""

    def describe(self, value: Any, catalog: Catalog) -> str:
        return "—" if not value else str(value)

    def parse(self, typed: str, catalog: Catalog) -> Any:
        if not typed and not self.optional:
            raise Invalid("this one needs something")
        return typed or None

    def hint(self, catalog: Catalog) -> str:
        return f"e.g. {self.placeholder}" if self.placeholder else ""


@dataclass(frozen=True, slots=True)
class TextList(Field):
    """Several lines, in order.

    Attributes
    ----------
    min_items : int
        How many are needed before the step counts as answered.
    placeholder : str
        An example line.
    """

    kind: ClassVar[str] = "text-list"
    interactive: ClassVar[bool] = True

    min_items: int = 0
    placeholder: str = ""

    def describe(self, value: Any, catalog: Catalog) -> str:
        lines = _sequence(value)
        if not lines:
            return "—"
        first = str(_line_text(lines[0]))
        extra = f" (+{len(lines) - 1} more)" if len(lines) > 1 else ""
        return f"{_shorten(first)}{extra}"

    def parse(self, typed: str, catalog: Catalog) -> Any:
        raise NotOneLine("a text list is collected a line at a time")

    def hint(self, catalog: Catalog) -> str:
        return "one line at a time; a blank line ends it"


@dataclass(frozen=True, slots=True)
class Number(Field):
    """A number, with bounds.

    Attributes
    ----------
    minimum, maximum : float or None
        Bounds, checked here so an author is told before the model is.
    integer : bool
        Whether a whole number is required. Ticks are; a multiplier is not.
    """

    kind: ClassVar[str] = "number"

    minimum: float | None = None
    maximum: float | None = None
    integer: bool = True

    def describe(self, value: Any, catalog: Catalog) -> str:
        return "—" if value is None else _number(value)

    def parse(self, typed: str, catalog: Catalog) -> Any:
        if not typed:
            if self.optional:
                return None
            raise Invalid("a number, please")
        try:
            value: float = int(typed) if self.integer else float(typed)
        except ValueError:
            what = "a whole number" if self.integer else "a number"
            raise Invalid(f"{what}, please — `{typed}` is not one") from None
        if self.minimum is not None and value < self.minimum:
            raise Invalid(f"no lower than {_number(self.minimum)}")
        if self.maximum is not None and value > self.maximum:
            raise Invalid(f"no higher than {_number(self.maximum)}")
        return value

    def hint(self, catalog: Catalog) -> str:
        if self.minimum is not None and self.maximum is not None:
            return f"{_number(self.minimum)} to {_number(self.maximum)}"
        if self.minimum is not None:
            return f"{_number(self.minimum)} or more"
        if self.maximum is not None:
            return f"{_number(self.maximum)} or less"
        return ""


@dataclass(frozen=True, slots=True)
class Bool(Field):
    """Yes or no."""

    kind: ClassVar[str] = "bool"

    def describe(self, value: Any, catalog: Catalog) -> str:
        return "—" if value is None else ("yes" if value else "no")

    def parse(self, typed: str, catalog: Catalog) -> Any:
        if not typed:
            if self.optional:
                return None
            raise Invalid("yes or no")
        if typed in {"y", "yes", "true", "1"}:
            return True
        if typed in {"n", "no", "false", "0"}:
            return False
        raise Invalid("yes or no")

    def hint(self, catalog: Catalog) -> str:
        return "y / n"


@dataclass(frozen=True, slots=True)
class Select(Field):
    """Pick one of the things that exist.

    Attributes
    ----------
    options : Source
        Where the choices come from — usually a `Query`.
    allow_create : str or None
        A collection name, when "+ create a new one" belongs on the list. The
        front-end opens that collection's flow and comes back with the new id,
        which is what keeps an author from having to leave what they are doing
        to define the thing they just realised they need.
    """

    kind: ClassVar[str] = "select"

    options: Source = field(default_factory=lambda: Fixed(()))
    allow_create: str | None = None

    def describe(self, value: Any, catalog: Catalog) -> str:
        if value is None:
            return "—"
        return _labelled(str(value), self.options.options(catalog))

    def parse(self, typed: str, catalog: Catalog) -> Any:
        offered = self.options.options(catalog)
        if not typed:
            if self.optional:
                return None
            raise Invalid("pick one")
        return _one_of(typed, offered)

    def hint(self, catalog: Catalog) -> str:
        return "" if self.options.options(catalog) else "nothing to pick yet"


@dataclass(frozen=True, slots=True)
class MultiSelect(Field):
    """Pick any number of the things that exist.

    Attributes
    ----------
    options : Source
        Where the choices come from.
    allow_create : str or None
        A collection to offer "+ create a new one" for.
    min_items : int
        How many are needed before the step counts as answered.
    free_text : bool
        Whether typing something not on offer is itself an answer, rather
        than a mistake. True for a field of free labels — tags — where
        `options` is only ever a list of *suggestions*: values other objects
        already used, not a closed set to pick from.
    """

    kind: ClassVar[str] = "multi-select"

    options: Source = field(default_factory=lambda: Fixed(()))
    allow_create: str | None = None
    min_items: int = 0
    free_text: bool = False

    def describe(self, value: Any, catalog: Catalog) -> str:
        chosen = _sequence(value)
        if not chosen:
            return "—"
        offered = self.options.options(catalog)
        return ", ".join(_labelled(str(one), offered) for one in chosen)

    def parse(self, typed: str, catalog: Catalog) -> Any:
        offered = self.options.options(catalog)
        if not typed:
            if self.min_items:
                raise Invalid(f"pick at least {self.min_items}")
            return []
        picked = [self._one(part.strip(), offered) for part in typed.split(",")]
        if len(picked) < self.min_items:
            raise Invalid(f"pick at least {self.min_items}")
        return list(dict.fromkeys(picked))

    def _one(self, typed: str, offered: Sequence[Option]) -> str:
        if not self.free_text:
            return _one_of(typed, offered)
        try:
            return _one_of(typed, offered)
        except Invalid:
            if typed == "":
                raise
            return typed

    def hint(self, catalog: Catalog) -> str:
        if self.free_text:
            return "names separated by commas — pick one shown, or type a new one"
        return "numbers separated by commas, or blank for none"


@dataclass(frozen=True, slots=True)
class StatAllocator(Field):
    """A statblock: named numbers, optionally against a budget.

    Genre-neutral on purpose. The engine knows nothing about `strength`, so
    neither does this — `stats` holds suggestions drawn from what the pack
    already uses, and an author is free to invent `hull-integrity` instead.

    A `points` budget turns it into the statblock assistant the docs describe:
    "how hard should this fight be" becomes a number to spend, and the author
    decides where a troll is dangerous rather than deriving it from a table.

    Attributes
    ----------
    points : int
        The budget, or 0 for no budget at all.
    stats : tuple of str
        Names to offer. Never a restriction.
    """

    kind: ClassVar[str] = "stat-allocator"
    interactive: ClassVar[bool] = True

    points: int = 0
    stats: tuple[str, ...] = ()

    def describe(self, value: Any, catalog: Catalog) -> str:
        spread = value if isinstance(value, Mapping) else {}
        if not spread:
            return "—"
        return " · ".join(
            f"{name} {_number(_base(spread[name]))}" for name in sorted(spread)
        )

    def parse(self, typed: str, catalog: Catalog) -> Any:
        raise NotOneLine("a statblock is filled in one stat at a time")

    def hint(self, catalog: Catalog) -> str:
        if self.points:
            return f"{self.points} points to spread"
        return "a name and a number at a time; blank ends it"


@dataclass(frozen=True, slots=True)
class ConditionBuilder(Field):
    """One or more conditions, built by the guided cascade.

    Attributes
    ----------
    single : bool
        Whether the field holds one condition rather than a list. A
        description line takes one; a scene's `when` takes several.
    """

    kind: ClassVar[str] = "conditions"
    interactive: ClassVar[bool] = True

    single: bool = False

    def describe(self, value: Any, catalog: Catalog) -> str:
        from mace.wizard.language import say_conditions

        authored = [value] if self.single and value is not None else _sequence(value)
        if not authored:
            return "always"
        parsed = _as_models(authored, "conditions")
        if parsed is None:
            return _unparsed(len(authored), "condition")
        return say_conditions(parsed, _names(catalog))

    def parse(self, typed: str, catalog: Catalog) -> Any:
        raise NotOneLine("a condition is built rather than typed")

    def hint(self, catalog: Catalog) -> str:
        return "built one question at a time"


@dataclass(frozen=True, slots=True)
class EffectBuilder(Field):
    """One or more effects, built by the guided cascade."""

    kind: ClassVar[str] = "effects"
    interactive: ClassVar[bool] = True

    def describe(self, value: Any, catalog: Catalog) -> str:
        from mace.wizard.language import say_effects

        authored = _sequence(value)
        if not authored:
            return "nothing happens"
        parsed = _as_models(authored, "effects")
        if parsed is None:
            return _unparsed(len(authored), "effect")
        return say_effects(parsed, _names(catalog))

    def parse(self, typed: str, catalog: Catalog) -> Any:
        raise NotOneLine("an effect is built rather than typed")

    def hint(self, catalog: Catalog) -> str:
        return "built one question at a time"


@dataclass(frozen=True, slots=True)
class MapEditor(Field):
    """Where something sits on the map.

    The docs require any field the terminal cannot render usefully to declare a
    text fallback, and this is that field: a browser drags a node, a terminal
    takes two numbers. Neither is the "real" one — the value is a pair of
    coordinates either way.
    """

    kind: ClassVar[str] = "map-position"

    def describe(self, value: Any, catalog: Catalog) -> str:
        if not isinstance(value, Mapping):
            return "—"
        return f"({_number(value.get('x', 0))}, {_number(value.get('y', 0))})"

    def parse(self, typed: str, catalog: Catalog) -> Any:
        if not typed:
            return None
        parts = [part.strip() for part in typed.replace(",", " ").split()]
        if len(parts) != 2:
            raise Invalid("two numbers: `x y`")
        try:
            return {"x": float(parts[0]), "y": float(parts[1])}
        except ValueError:
            raise Invalid("two numbers: `x y`") from None

    def hint(self, catalog: Catalog) -> str:
        return "`x y` — or leave it blank and let the map lay itself out"


@dataclass(frozen=True, slots=True)
class Repeat(Field):
    """A list of sub-objects, each built by its own little flow.

    Attributes
    ----------
    of : str
        What one entry is called — `exit`, `choice`, `stage`.
    steps : tuple
        The steps that build one entry. Held loosely typed to keep this module
        free of a cycle with `flow`; the flow module is what walks them.
    """

    kind: ClassVar[str] = "repeat"
    interactive: ClassVar[bool] = True

    of: str = "entry"
    steps: tuple[Any, ...] = ()

    def describe(self, value: Any, catalog: Catalog) -> str:
        entries = _sequence(value)
        if not entries:
            return "—"
        return f"{len(entries)} {self.of}{'' if len(entries) == 1 else 's'}"

    def parse(self, typed: str, catalog: Catalog) -> Any:
        raise NotOneLine("a repeat is filled in one entry at a time")

    def hint(self, catalog: Catalog) -> str:
        return f"add {self.of}s one at a time"


def _base(stat: Any) -> Any:
    """The number in a stat entry, which may be a mapping or a bare value.

    Parameters
    ----------
    stat : object
        `{base: 32, growth: slow}`, or `32`.

    Returns
    -------
    object
        The base value.
    """
    return stat.get("base", 0) if isinstance(stat, Mapping) else stat


def _unparsed(count: int, noun: str) -> str:
    """Say that something here will not build yet, without hiding it.

    A project holds content that is allowed to be wrong for a while, and a
    field that went blank rather than admitting it would leave an author
    hunting for the thing they broke.

    Parameters
    ----------
    count : int
        How many entries there are.
    noun : str
        `condition` or `effect`.

    Returns
    -------
    str
        A phrase saying what is wrong.
    """
    if count == 1:
        return f"a {noun} that does not build yet"
    return f"{count} {noun}s, one of which does not build yet"


def _names(catalog: Catalog) -> Any:
    """The naming service for one open project.

    Parameters
    ----------
    catalog : Catalog
        What exists.

    Returns
    -------
    Names
        Naming that reads the project's raw objects and its libraries alike.
    """
    from mace.wizard.language import Names

    return Names(
        library=catalog.project.dependencies,
        within=catalog.project.manifest.id,
        catalog=catalog,
    )


def _as_models(authored: Sequence[Any], collection: str) -> Any:
    """Validate authored conditions or effects, tolerating the ones that don't.

    Content in a project is allowed to be wrong for a while, so a field that
    could not describe a half-written condition would be a field that goes
    blank exactly when an author is looking at it.

    Parameters
    ----------
    authored : sequence
        The raw authored mappings.
    collection : str
        `conditions` or `effects`.

    Returns
    -------
    list or None
        The parsed models, or None when any of them will not build.
    """
    from mace.model import Condition, Effect

    model = Condition if collection == "conditions" else Effect
    try:
        return [model.model_validate(one) for one in authored]
    except ValueError:
        return None


def _one_of(typed: str, offered: Sequence[Option]) -> str:
    """Read one pick, by number or by name.

    Parameters
    ----------
    typed : str
        What the author typed.
    offered : sequence of Option
        The options, in the order they were shown.

    Returns
    -------
    str
        The chosen option's value.

    Raises
    ------
    Invalid
        If it matches nothing.
    """
    if typed.isdigit() and 1 <= int(typed) <= len(offered):
        return offered[int(typed) - 1].value
    lowered = typed.lower()
    for option in offered:
        if lowered in {option.value.lower(), option.label.lower()}:
            return option.value
    if not offered:
        raise Invalid("there is nothing to pick yet")
    raise Invalid(f"pick a number between 1 and {len(offered)}, or type its name")


def _labelled(value: str, offered: Sequence[Option]) -> str:
    """Show a chosen value by its label, or as written when nothing matches.

    Parameters
    ----------
    value : str
        The stored reference.
    offered : sequence of Option
        What was on offer.

    Returns
    -------
    str
        The label, or the raw value marked as unresolved.
    """
    for option in offered:
        if option.value == value:
            return option.label
    return f"{value} (?)"


def _sequence(value: Any) -> list[Any]:
    """Read a value that may be a list, a lone item, or nothing.

    Parameters
    ----------
    value : object
        The authored value.

    Returns
    -------
    list
        Its entries.
    """
    if value is None:
        return []
    if isinstance(value, str | Mapping):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _line_text(line: Any) -> Any:
    """The text of a narration line, which may be a bare string.

    Parameters
    ----------
    line : object
        A string or a `{text: ..., when: ...}` mapping.

    Returns
    -------
    object
        The text.
    """
    return line.get("text", "") if isinstance(line, Mapping) else line


def _shorten(text: str, width: int = 48) -> str:
    """Trim a line for a summary column.

    Parameters
    ----------
    text : str
        The line.
    width : int
        How much room there is.

    Returns
    -------
    str
        The line, or its beginning with an ellipsis.
    """
    return text if len(text) <= width else f"{text[: width - 1]}…"


def _number(value: Any) -> str:
    """Render a number without a pointless decimal point.

    Parameters
    ----------
    value : object
        The number.

    Returns
    -------
    str
        `8` rather than `8.0`.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):  # pragma: no cover — non-numeric slipped in
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)
