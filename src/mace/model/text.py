"""Narration: descriptions and the lines a scene says.

Both are lists of lines that may carry a condition, which is what lets one
location read differently at night, in the rain, or once the player knows what
lives under the bridge::

    description:
      - {text: "A stone span over black water.", when: {dayPart: [day, dawn]}}
      - {text: "You hear the river well before you see the bridge."}

First match wins; an entry with no `when` is the fallback. A line that is just
its text may be written as a bare string.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, WithJsonSchema

from mace.model.base import ContentModel, one_or_many_schema
from mace.model.conditions import Conditions

__all__ = [
    "Description",
    "DescriptionLine",
    "Say",
    "SayLine",
]


class DescriptionLine(ContentModel):
    """One candidate line of description.

    Attributes
    ----------
    text : str
        What the player reads.
    when : tuple of Condition or None
        Conditions that must hold for this line to be chosen. `None` makes it
        the fallback.
    """

    shorthand_field: ClassVar[str] = "text"

    text: str
    when: Conditions | None = None


class SayLine(ContentModel):
    """One line of scene narration.

    Attributes
    ----------
    text : str
        What the player reads.
    when : tuple of Condition or None
        Conditions that must hold for this line to be spoken at all.
    pause : bool
        Whether the front-end waits for the player before going on. Pacing is a
        presentation concern, but where the beats fall is the author's call.
    """

    shorthand_field: ClassVar[str] = "text"

    text: str
    when: Conditions | None = None
    pause: bool = False


def _as_lines(value: Any) -> Any:
    """Accept a single line where a list of lines is expected.

    Parameters
    ----------
    value : object
        The raw YAML value: a string, one line mapping, or a list of either.

    Returns
    -------
    object
        A sequence of lines.
    """
    if isinstance(value, str | Mapping):
        return [value]
    return value


#: Conditional description text. A bare string is a single unconditional line.
Description = Annotated[
    tuple[DescriptionLine, ...],
    BeforeValidator(_as_lines),
    WithJsonSchema(one_or_many_schema("DescriptionLine")),
]

#: Scene narration, in order.
Say = Annotated[
    tuple[SayLine, ...],
    BeforeValidator(_as_lines),
    WithJsonSchema(one_or_many_schema("SayLine")),
]
