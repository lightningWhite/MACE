"""Character creation in the terminal.

The engine projects the question (`mace.engine.creation`); this asks it. Two
prompts and no ceremony: who were you, and where do the points go. A game that
offers neither is not asked anything at all, and the first thing the player
sees is still the first line of the story.

The web client will render the same `Creation` as cards and a slider. Neither
front-end knows what a `Background` is, which is the point.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TextIO

from mace.content import Library
from mace.engine.creation import Character, Creation, StatOffer, offer

__all__ = ["ask", "parse_spend", "summarise"]

#: The width the stat allocator lines up its numbers at.
_STAT_COLUMN = 12


def ask(
    library: Library, pack_id: str, out: TextIO, *, interactive: bool = True
) -> Character:
    """Ask the player who they are.

    The question is asked twice over, because the second half depends on the
    first: the points are allocated against the stats the chosen background
    leaves you with, not against the protagonist nobody is going to play.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game being started.
    out : TextIO
        Where to write.
    interactive : bool
        Whether there is anybody there to answer. A piped session takes the
        first background and spends nothing, which is what a recorded run
        wants: a fixed answer rather than a hang.

    Returns
    -------
    Character
        The answer. Always legal for this game.
    """
    creation = offer(library, pack_id)
    background = _pick(creation, out, interactive=interactive)
    spend = _allocate(
        offer(library, pack_id, background=background), out, interactive=interactive
    )
    return Character(background=background, spend=spend)


def _pick(creation: Creation, out: TextIO, *, interactive: bool) -> str | None:
    """Choose a background.

    Parameters
    ----------
    creation : Creation
        The question.
    out : TextIO
        Where to write.
    interactive : bool
        Whether to prompt.

    Returns
    -------
    str or None
        The chosen background's qualified id, or None when none are offered.
    """
    if not creation.backgrounds:
        return None
    if not interactive:
        return creation.backgrounds[0].id

    print("", file=out)
    print("  Who were you, before this morning?", file=out)
    print("", file=out)
    for index, background in enumerate(creation.backgrounds, start=1):
        print(f"  {index}. {background.name}", file=out)
        if background.description:
            print(f"     {background.description}", file=out)
        if background.grants:
            print(f"     {' · '.join(background.grants)}", file=out)
        print("", file=out)

    count = len(creation.backgrounds)
    while True:
        typed = _read("> ", out)
        if typed is None:
            return creation.backgrounds[0].id
        if typed.isdigit() and 1 <= int(typed) <= count:
            return creation.backgrounds[int(typed) - 1].id
        print(f"  Pick a number between 1 and {count}.", file=out)


def _allocate(
    creation: Creation, out: TextIO, *, interactive: bool
) -> Mapping[str, int]:
    """Spend the creation points.

    Stat by stat, with what is left shown at every prompt, because the only
    question a player is actually asking here is "can I still afford it".

    Parameters
    ----------
    creation : Creation
        The question, with any chosen background already folded in.
    out : TextIO
        Where to write.
    interactive : bool
        Whether to prompt.

    Returns
    -------
    mapping
        Stat name to points, omitting the stats that got none.
    """
    if not interactive or creation.points <= 0 or not creation.stats:
        return {}

    spend: dict[str, int] = {}
    left = creation.points
    print("", file=out)
    print(
        f"  {creation.points} points to spend on who you became. "
        "Enter passes; `done` stops.",
        file=out,
    )
    print("", file=out)

    for stat in creation.stats:
        if left <= 0:
            break
        put = _spend_on(stat, left, out)
        if put is None:
            break
        if put:
            spend[stat.stat] = put
            left -= put

    print("", file=out)
    print(f"  {summarise(creation, spend)}", file=out)
    return spend


def _spend_on(stat: StatOffer, left: int, out: TextIO) -> int | None:
    """Ask how much goes into one stat.

    Parameters
    ----------
    stat : StatOffer
        The stat.
    left : int
        Points still unspent.
    out : TextIO
        Where to write.

    Returns
    -------
    int or None
        The points to put in, or None to stop allocating entirely.
    """
    room = min(left, stat.room)
    label = f"{stat.stat:<{_STAT_COLUMN}}{_number(stat.base)}"
    if room <= 0:
        print(f"  {label}   (already at its limit)", file=out)
        return 0

    while True:
        typed = _read(f"  {label}   +{room} available, {left} left  > ", out)
        if typed is None or typed in {"done", "q"}:
            return None
        if not typed:
            return 0
        if not typed.lstrip("+").isdigit():
            print("  A number, or enter to pass, or `done`.", file=out)
            continue
        put = int(typed.lstrip("+"))
        if put <= room:
            return put
        print(f"  At most {room} there.", file=out)


def parse_spend(entries: Sequence[str]) -> dict[str, int]:
    """Read `--spend strength=5` arguments.

    Parameters
    ----------
    entries : sequence of str
        `stat=points` pairs.

    Returns
    -------
    dict
        Stat name to points.

    Raises
    ------
    ValueError
        If a pair is not `stat=points` with a whole number of points. The
        engine's own check catches an illegal allocation; this catches a
        mistyped one, which deserves the better message.
    """
    spend: dict[str, int] = {}
    for entry in entries:
        stat, _, points = entry.partition("=")
        if not stat or not points.lstrip("+-").isdigit():
            raise ValueError(f"`{entry}` should be written `stat=points`")
        spend[stat] = spend.get(stat, 0) + int(points)
    return spend


def summarise(creation: Creation, spend: Mapping[str, int]) -> str:
    """Say what an allocation came to, in one line.

    Parameters
    ----------
    creation : Creation
        The question.
    spend : mapping
        Stat name to points.

    Returns
    -------
    str
        `strength 40 · speed 46 — 3 points unspent`, or a note that nothing
        was spent.
    """
    bases = {stat.stat: stat.base for stat in creation.stats}
    changed = [
        f"{name} {_number(min(bases.get(name, 0.0) + points, _cap(creation, name)))}"
        for name, points in spend.items()
        if points
    ]
    left = creation.points - sum(spend.values())
    tail = f"{left} point{'s' if left != 1 else ''} unspent" if left else ""
    if not changed:
        return f"Nothing spent — {tail}." if tail else "Nothing spent."
    return " · ".join(changed) + (f" — {tail}." if tail else ".")


def _cap(creation: Creation, name: str) -> float:
    """The ceiling of one offered stat.

    Parameters
    ----------
    creation : Creation
        The question.
    name : str
        The stat.

    Returns
    -------
    float
        Its maximum, or infinity for a stat that is not offered.
    """
    for stat in creation.stats:
        if stat.stat == name:
            return stat.maximum
    return float("inf")


def _read(prompt: str, out: TextIO) -> str | None:
    """Read one answer, treating a closed input as a shrug.

    Parameters
    ----------
    prompt : str
        What to show.
    out : TextIO
        Where the prompt goes when it is not standard output.

    Returns
    -------
    str or None
        The trimmed answer, or None when there is nobody there.
    """
    print(prompt, end="", file=out, flush=True)
    try:
        return input("").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("", file=out)
        return None


def _number(value: float) -> str:
    """Render a number without a pointless decimal point.

    Parameters
    ----------
    value : float
        The number.

    Returns
    -------
    str
        `32` rather than `32.0`.
    """
    return str(int(value)) if float(value).is_integer() else str(value)
