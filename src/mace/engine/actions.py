"""Actions: the only things a player can do to the world.

An action log plus a seed plus the pack list is a whole save file, so every
action has to render to a plain record and read back from one. Anything a
front-end can do must be expressible here; anything not expressible here is
something a front-end is doing on its own, which is a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

__all__ = [
    "Action",
    "Choose",
    "Interact",
    "Look",
    "Travel",
    "Wait",
    "decode",
]


@dataclass(frozen=True, slots=True)
class BaseAction:
    """Base class for everything a player can do."""

    kind: ClassVar[str] = "action"

    def payload(self) -> dict[str, Any]:
        """The action's fields, without its kind.

        Returns
        -------
        dict
            JSON-safe values.
        """
        return {}

    def record(self) -> dict[str, Any]:
        """The action as it appears in an action log.

        Returns
        -------
        dict
            The kind, then the payload.
        """
        return {"kind": self.kind, **self.payload()}


@dataclass(frozen=True, slots=True)
class Look(BaseAction):
    """Take in the surroundings. Costs no time."""

    kind: ClassVar[str] = "look"


@dataclass(frozen=True, slots=True)
class Choose(BaseAction):
    """Pick one of the options the engine last offered.

    Attributes
    ----------
    option : int
        Index into the options of the last `choices` event.
    """

    kind: ClassVar[str] = "choose"
    option: int

    def payload(self) -> dict[str, Any]:
        return {"option": self.option}


@dataclass(frozen=True, slots=True)
class Interact(BaseAction):
    """Play a scene directly, by id.

    Front-ends normally use `Choose`; this is what a test, a debug console, or
    a wizard playtest uses to jump straight at a scene.

    Attributes
    ----------
    scene : str
        The scene reference, bare or qualified.
    """

    kind: ClassVar[str] = "interact"
    scene: str

    def payload(self) -> dict[str, Any]:
        return {"scene": self.scene}


@dataclass(frozen=True, slots=True)
class Travel(BaseAction):
    """Go somewhere, by whatever route connects here to there.

    Attributes
    ----------
    to : str
        The destination location reference.
    """

    kind: ClassVar[str] = "travel"
    to: str

    def payload(self) -> dict[str, Any]:
        return {"to": self.to}


@dataclass(frozen=True, slots=True)
class Wait(BaseAction):
    """Let time pass.

    Attributes
    ----------
    ticks : int
        How many ticks to wait.
    """

    kind: ClassVar[str] = "wait"
    ticks: int = 1

    def payload(self) -> dict[str, Any]:
        return {"ticks": self.ticks}


Action = Look | Choose | Interact | Travel | Wait

#: Every action kind, for decoding a saved log.
ACTIONS: dict[str, type[BaseAction]] = {
    action.kind: action for action in (Look, Choose, Interact, Travel, Wait)
}


def decode(record: dict[str, Any]) -> Action:
    """Rebuild an action from its record.

    Parameters
    ----------
    record : dict
        A record from `Action.record`.

    Returns
    -------
    Action
        The action.

    Raises
    ------
    ValueError
        If the record names no known action.
    """
    fields = dict(record)
    kind = fields.pop("kind", None)
    if kind not in ACTIONS:
        known = ", ".join(sorted(ACTIONS))
        raise ValueError(f"unknown action `{kind}`; known actions: {known}")
    built = ACTIONS[kind](**fields)
    assert isinstance(built, Look | Choose | Interact | Travel | Wait)
    return built
