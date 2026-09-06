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
from typing import Annotated, Any

from pydantic import BeforeValidator

from mace.model.base import ContentModel, shorthand
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

    text: str
    when: Conditions | None = None

    _expand = shorthand("text")

    def authored(self) -> Any:
        if self.when is None:
            return self.text
        return super().authored()


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

    text: str
    when: Conditions | None = None
    pause: bool = False

    _expand = shorthand("text")

    def authored(self) -> Any:
        if self.when is None and not self.pause:
            return self.text
        return super().authored()


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
Description = Annotated[tuple[DescriptionLine, ...], BeforeValidator(_as_lines)]

#: Scene narration, in order.
Say = Annotated[tuple[SayLine, ...], BeforeValidator(_as_lines)]
