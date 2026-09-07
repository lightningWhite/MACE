"""Actions: the only things a player can do to the world.

An action log plus a seed plus the pack list is a whole save file, so every
action has to render to a plain record and read back from one. Anything a
front-end can do must be expressible here; anything not expressible here is
something a front-end is doing on its own, which is a bug.

`Choose` addresses an option by **index**, and that stays the protocol: it is
what a `choices` event's ordering means, and it needs no text matching in the
engine. But an index is a terrible thing to *write down*. A recorded log of
`choose 3` silently means something different the moment an author inserts an
option above it — the log still replays, down a different road, and nothing
says so. So `decode` also accepts a recorded choice written as the option's
prompt, resolves it against what was actually offered, and fails loudly with
the menu in the message when it is not there. Records are for people; the
protocol is for machines.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

__all__ = [
    "Action",
    "Choose",
    "Haggle",
    "Interact",
    "Look",
    "Respond",
    "Trade",
    "Travel",
    "Use",
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


@dataclass(frozen=True, slots=True)
class Use(BaseAction):
    """Use something you are carrying.

    Attributes
    ----------
    item : str
        The item reference, bare or qualified.
    """

    kind: ClassVar[str] = "use"
    item: str

    def payload(self) -> dict[str, Any]:
        return {"item": self.item}


@dataclass(frozen=True, slots=True)
class Haggle(BaseAction):
    """Press the merchant you are dealing with on their price.

    Takes nothing: what a push is worth is decided by who the player is, how
    many times they have already pushed, and what they know about prices
    elsewhere — none of which a front-end should be choosing.
    """

    kind: ClassVar[str] = "haggle"


@dataclass(frozen=True, slots=True)
class Trade(BaseAction):
    """Buy from the merchant you are dealing with, or sell to them.

    A quantity, not a single unit, because the whole of trading is carrying
    twenty sacks somewhere they are worth more. The engine also offers one-
    and ten-unit trades as ordinary menu options, so a terminal can do this
    without a quantity control; both go through the same arithmetic.

    Attributes
    ----------
    good : str
        The good reference, bare or qualified.
    qty : int
        How many units. Always positive; `sell` says which way they go.
    sell : bool
        Whether the player is the one handing the goods over.
    """

    kind: ClassVar[str] = "trade"
    good: str
    qty: int = 1
    sell: bool = False

    def payload(self) -> dict[str, Any]:
        return {"good": self.good, "qty": self.qty, "sell": self.sell}


@dataclass(frozen=True, slots=True)
class Respond(BaseAction):
    """Answer the move a fight has just telegraphed.

    `elapsed_ms` is the one place a wall clock reaches the engine, and it does
    so as a *recorded number* rather than as a measurement. The front-end
    measures against a monotonic deadline and puts the result in the action
    log; a replay resolves against that recorded value instead of measuring
    again, and the engine quantizes it so two machines that read 812 ms and
    814 ms resolve the same exchange (ADR-0004).

    Attributes
    ----------
    response : str
        A defense type from the last `combat.responses` event — or `recover`
        or `flee`.
    elapsed_ms : int or None
        Milliseconds from the tell to the keypress. None in tactical mode,
        where no clock is running and precision is fixed.
    """

    kind: ClassVar[str] = "combat.input"
    response: str
    elapsed_ms: int | None = None

    def payload(self) -> dict[str, Any]:
        return {"response": self.response, "elapsedMs": self.elapsed_ms}


Action = Choose | Haggle | Interact | Look | Respond | Trade | Travel | Use | Wait

#: Every action kind, for decoding a saved log.
ACTIONS: dict[str, type[BaseAction]] = {
    action.kind: action
    for action in (
        Choose,
        Haggle,
        Interact,
        Look,
        Respond,
        Trade,
        Travel,
        Use,
        Wait,
    )
}

#: Fields whose recorded name differs from the constructor's, so an action log
#: stays camelCase like everything else an author or a tool reads.
RECORD_FIELDS: dict[str, str] = {"elapsedMs": "elapsed_ms"}


def decode(record: dict[str, Any], *, offered: Sequence[str] | None = None) -> Action:
    """Rebuild an action from its record.

    A `choose` record may name its option either way. `{"option": 2}` is the
    protocol form and needs nothing else. `{"prompt": "Speak to the troll"}` is
    the readable form, and is resolved against `offered` — which is what makes
    a recorded playthrough survive an author inserting a menu entry above the
    one it meant.

    Parameters
    ----------
    record : dict
        A record from `Action.record`.
    offered : sequence of str or None
        The prompts last offered, in order. Required to decode a choice
        written as a prompt; ignored otherwise.

    Returns
    -------
    Action
        The action.

    Raises
    ------
    ValueError
        If the record names no known action, or names an option that was not
        offered.
    """
    fields = dict(record)
    kind = fields.pop("kind", None)
    if kind not in ACTIONS:
        known = ", ".join(sorted(ACTIONS))
        raise ValueError(f"unknown action `{kind}`; known actions: {known}")

    if kind == "choose" and "prompt" in fields:
        fields = {"option": _index_of(str(fields.pop("prompt")), offered, fields)}

    fields = {RECORD_FIELDS.get(name, name): value for name, value in fields.items()}
    built = ACTIONS[kind](**fields)
    assert isinstance(
        built,
        Choose | Haggle | Interact | Look | Respond | Trade | Travel | Use | Wait,
    )
    return built


def _index_of(prompt: str, offered: Sequence[str] | None, rest: dict[str, Any]) -> int:
    """Find which option a recorded prompt meant.

    Parameters
    ----------
    prompt : str
        The option as it was written down.
    offered : sequence of str or None
        What was actually offered, in order.
    rest : dict
        Whatever else the record carried, so an unusable extra field is
        reported rather than silently dropped.

    Returns
    -------
    int
        The index to choose.

    Raises
    ------
    ValueError
        If nothing was offered, nothing matches, or two things do.
    """
    if rest:
        extra = ", ".join(sorted(rest))
        raise ValueError(f"a choice named by `prompt` takes nothing else; got {extra}")
    if offered is None:
        raise ValueError(
            f"cannot resolve the choice `{prompt}`: nothing was on offer. A "
            "choice recorded by prompt needs the options it is chosen from."
        )

    matches = [index for index, text in enumerate(offered) if text == prompt]
    if len(matches) == 1:
        return matches[0]

    menu = "\n  ".join(f"{index}. {text}" for index, text in enumerate(offered))
    if not matches:
        raise ValueError(
            f"no option `{prompt}` was offered. These were:\n  {menu or '(none)'}"
        )
    raise ValueError(
        f"`{prompt}` was offered {len(matches)} times, so naming it is "
        f"ambiguous. The options were:\n  {menu}"
    )
