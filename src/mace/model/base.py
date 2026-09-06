"""Shared building blocks for every content model.

Three things live here because every other model in this package needs them:
the base class that fixes the authoring conventions (camelCase keys, frozen
instances, unknown keys rejected), the string patterns that define what an id
and a reference look like, and the two annotated types that let an author write
``{expr: "..."}`` anywhere a value is expected.

Author expressions are parsed *here*, at model-validation time, so a typo in a
condition is a load-time error with a caret under it rather than a surprise
three hours into a playthrough. See docs/04-schema-reference.md § Expressions.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainValidator,
    StringConstraints,
    WithJsonSchema,
    model_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel

from mace.engine.expr import Expression, ExprSyntaxError, parse

__all__ = [
    "AuthoredValue",
    "ContentModel",
    "ExpressionField",
    "Flag",
    "Id",
    "Name",
    "PackId",
    "Ref",
    "SlotName",
    "Tag",
    "VersionRange",
    "Version",
    "authored_value",
    "one_or_many_schema",
    "unwrap_tagged",
]

#: A `kebab-case` id, unique within its pack.
LOCAL_ID_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"

#: A pack's dotted namespace, e.g. `fantasy.core` or `peasants-quest`.
PACK_ID_PATTERN = rf"{LOCAL_ID_PATTERN}(?:\.{LOCAL_ID_PATTERN})*"

#: A reference: bare (resolved against this pack, then its dependencies) or
#: fully qualified as `pack-id:local-id`.
REF_PATTERN = rf"(?:{PACK_ID_PATTERN}:)?{LOCAL_ID_PATTERN}"

#: An identifier the author chose but the engine never resolves — a slot name,
#: a variable name. These follow the camelCase convention of YAML keys.
CAMEL_NAME_PATTERN = r"[a-z][a-zA-Z0-9]*"

Id = Annotated[str, StringConstraints(pattern=rf"^{LOCAL_ID_PATTERN}$")]
PackId = Annotated[str, StringConstraints(pattern=rf"^{PACK_ID_PATTERN}$")]
Ref = Annotated[str, StringConstraints(pattern=rf"^{REF_PATTERN}$")]

#: Stat names, day parts, and the like: kebab-case, like ids, because a sci-fi
#: pack defines `hull-integrity` the same way a fantasy one defines `hitpoints`.
Name = Id

#: Boolean flags on an entity — `locked`, `has-spoken`, `knows-the-wood`.
Flag = Id

#: Free-form grouping labels, matched by encounter tables and `env` responses.
Tag = Id

#: An equipment slot or a game variable: `mainHand`, `kingWarned`.
SlotName = Annotated[str, StringConstraints(pattern=rf"^{CAMEL_NAME_PATTERN}$")]

Version = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
    ),
]

#: A dependency range such as `^0.1` or `>=2.0.0`. Deliberately loose: the
#: comparison rules live in the loader, not in the shape.
VersionRange = Annotated[
    str,
    StringConstraints(pattern=r"^(?:\^|~|>=|<=|>|<|=)?\d+(?:\.\d+){0,2}$"),
]


class ContentModel(BaseModel):
    """Base class for everything an author writes.

    Fixes four conventions in one place:

    - **camelCase keys.** YAML content uses camelCase; Python uses snake_case.
      The alias generator bridges them, so `startLocation` in a pack becomes
      `start_location` in code with no per-field boilerplate.
    - **Frozen.** Content is immutable after load (architecture boundary 1).
      Runtime values belong in session state, never written back here.
    - **Unknown keys are errors.** A misspelled field is the single most common
      authoring mistake and the cheapest one to catch.
    - **Defaults are validated**, so a default can't quietly violate its own
      constraint.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        validate_default=True,
    )

    #: When set, this model accepts a bare value in place of its mapping, and
    #: renders back to that bare value when every other field is at its
    #: default. `{chance: 0.15}` rather than `{chance: {probability: 0.15}}`;
    #: a description line that is only its own text.
    shorthand_field: ClassVar[str | None] = None

    #: Whether the bare value may itself be a mapping, as it is for `not`,
    #: whose shorthand body is another condition. When false a mapping is taken
    #: to be the full form and passed through untouched, which is what lets
    #: `{text: ..., when: ...}` coexist with a bare `"..."`.
    shorthand_wraps_mapping: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _expand_shorthand(cls, value: Any) -> Any:
        """Expand this model's bare authored form into its mapping form."""
        field = cls.shorthand_field
        if field is None:
            return value
        if isinstance(value, Mapping) and (
            set(value) <= {field} or not cls.shorthand_wraps_mapping
        ):
            return value
        return {field: value}

    def authored(self) -> Any:
        """Render this model back into the shape its author wrote.

        Content round-trips: a pack is loaded from YAML, compiled to a JSON
        bundle, and edited by the wizard, and all three want the authoring
        shape rather than pydantic's field names. Fields left at their default
        are omitted, so the output is the smallest content that reproduces this
        model.

        Returns
        -------
        object
            A mapping of authored keys to authored values.
        """
        shorthand = type(self).shorthand_field
        if shorthand is not None and self._renders_as_shorthand():
            return authored_value(getattr(self, shorthand))

        rendered: dict[str, Any] = {}
        for name, field in type(self).model_fields.items():
            value = getattr(self, name)
            if not field.is_required():
                default = field.get_default(call_default_factory=True)
                if value is None or value == default:
                    continue
            rendered[field.alias or name] = authored_value(value)
        return rendered

    def _renders_as_shorthand(self) -> bool:
        """Whether this instance carries nothing but its shorthand field.

        Returns
        -------
        bool
            True when the bare authored form says everything this model holds.
        """
        shorthand = type(self).shorthand_field
        if shorthand is None:
            return False
        for name, field in type(self).model_fields.items():
            if name == shorthand:
                continue
            if field.is_required():
                return False
            if getattr(self, name) != field.get_default(call_default_factory=True):
                return False
        return True

    @model_serializer(mode="plain")
    def _serialize(self) -> Any:
        """Serialize through `authored`, so `model_dump` yields valid content."""
        return self.authored()


def _to_expression(value: Any) -> Expression:
    """Coerce an authored value into a parsed expression.

    Parameters
    ----------
    value : object
        The raw YAML value: the source text, or an already-parsed expression.

    Returns
    -------
    Expression
        The parsed expression.

    Raises
    ------
    ValueError
        If the value is not expression source, or does not parse. The parser's
        own message — which carries the source and a caret — is kept, and
        pydantic adds the field it came from, so an author is told both what
        is wrong and where.
    """
    if isinstance(value, Expression):
        return value
    if isinstance(value, str):
        try:
            return parse(value)
        except ExprSyntaxError as error:
            raise ValueError(str(error)) from error
    raise ValueError(f"expected expression text, got {type(value).__name__}")


def _to_authored_value(value: Any) -> Any:
    """Coerce an authored value that may be a literal or an expression.

    ``{expr: "..."}`` is the one wrapper that turns a literal into a question
    about the world. Everything else is taken literally — there is no quoting
    convention to remember (ADR-0003).

    Parameters
    ----------
    value : object
        The raw YAML value.

    Returns
    -------
    object
        A parsed `Expression`, or the literal unchanged.

    Raises
    ------
    ValueError
        If the value is a mapping that is not an `expr` wrapper, or a list.
    """
    if isinstance(value, Expression):
        return value
    if isinstance(value, Mapping):
        if set(value) == {"expr"}:
            return _to_expression(value["expr"])
        raise ValueError(
            'a value may be a literal or `{expr: "..."}`; '
            f"got a mapping with keys {sorted(map(str, value))}"
        )
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise ValueError(f"expected a literal or an expression, got {type(value).__name__}")


#: A field that must hold an author expression, parsed at load time.
ExpressionField = Annotated[
    Expression,
    PlainValidator(_to_expression),
    WithJsonSchema({"type": "string", "description": "A MACE expression."}),
]

#: A field that holds either a literal or an `{expr: "..."}` wrapper.
AuthoredValue = Annotated[
    Expression | bool | int | float | str | None,
    PlainValidator(_to_authored_value),
    WithJsonSchema(
        {
            "oneOf": [
                {"type": ["string", "number", "boolean", "null"]},
                {
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                    "additionalProperties": False,
                },
            ]
        }
    ),
]


def unwrap_tagged(
    value: Any, *, kind: str, vocabulary: Sequence[str]
) -> tuple[str, Any]:
    """Split a single-key mapping into its tag and its body.

    Conditions and effects are written as one-key mappings — `{hasItem: {...}}`,
    `{setFlag: {...}}` — so that a list of them reads as a list of statements.
    This unwraps that shape and checks the tag against the known vocabulary,
    suggesting a correction when the author is close.

    Parameters
    ----------
    value : object
        The raw YAML mapping.
    kind : str
        What is being unwrapped, for the error message: `condition` or `effect`.
    vocabulary : sequence of str
        The tags that are allowed here.

    Returns
    -------
    tuple of (str, object)
        The tag and the untouched body.

    Raises
    ------
    ValueError
        If the value is not a one-key mapping, or the tag is unknown.
    """
    if not isinstance(value, Mapping):
        raise ValueError(
            f"a {kind} is a single-key mapping such as "
            f"`{{{vocabulary[0]}: ...}}`; got {type(value).__name__}"
        )
    if len(value) != 1:
        keys = ", ".join(sorted(map(str, value))) or "nothing"
        raise ValueError(
            f"a {kind} is a single-key mapping; got {len(value)} keys ({keys}). "
            f"Write each {kind} as its own list entry."
        )

    tag = str(next(iter(value)))
    if tag not in vocabulary:
        near = difflib.get_close_matches(tag, vocabulary, n=1)
        hint = f"; did you mean `{near[0]}`?" if near else ""
        raise ValueError(f"unknown {kind} `{tag}`{hint}")

    return tag, value[tag]


def authored_value(value: Any) -> Any:
    """Render a validated value back into the shape an author wrote.

    Parameters
    ----------
    value : object
        A model, expression, collection, or scalar.

    Returns
    -------
    object
        The authoring-shaped equivalent.
    """
    if isinstance(value, ContentModel):
        return value.authored()
    if isinstance(value, Expression):
        return {"expr": value.source}
    if isinstance(value, Mapping):
        return {key: authored_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [authored_value(item) for item in value]
    return value


def one_or_many_schema(definition: str) -> dict[str, Any]:
    """Describe a field that takes one thing or a list of them.

    Several fields are kind to authors this way: a description line's `when`
    takes one condition and a scene's takes several, and nobody should have to
    remember which. Pydantic cannot see that through a `BeforeValidator`, so
    the JSON Schema says it explicitly.

    Parameters
    ----------
    definition : str
        The name of the definition in the generated `$defs` block.

    Returns
    -------
    dict
        A JSON Schema fragment.
    """
    reference = {"$ref": f"#/$defs/{definition}"}
    return {"anyOf": [reference, {"type": "array", "items": reference}]}
