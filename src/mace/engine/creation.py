"""Character creation — who the player is before the first tick.

Two questions, both answered before a playthrough opens: which **background**
the protagonist has, and how their **creation points** are spent on the stats
the author marked `customizable`.

Creation is session *setup*, like the seed and the combat mode, rather than a
turn the player takes. That is a deliberate choice and it buys two things.
Determinism: the answers are part of what a seed replays, so a golden file
covers a poacher as exactly as it covers a farmhand. And a wizard playtest
that says "start me as the old soldier with everything in speed" is one
argument rather than a scripted walk through an opening menu.

Front-ends do not read content to build the menu. `offer()` projects the
question into a read-only view-model — backgrounds with their grants already
phrased in English, stats with their bounds — and the front-end renders that
and hands back a `Character`. Architecture boundary 4 holds: the CLI and the
web client ask the same question and neither one knows what a `Background` is.

See docs/13-open-questions.md #6 and docs/09-authoring-and-wizard.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from mace.content import ContentError, Library
from mace.engine.stats import DEFAULT_ABILITY_MAX
from mace.model import Background, Entity, Game
from mace.model.background import StatGrant

__all__ = [
    "BackgroundOffer",
    "Character",
    "Creation",
    "StatOffer",
    "check",
    "grants",
    "offer",
]


@dataclass(frozen=True, slots=True)
class StatOffer:
    """One stat the player may spend creation points on.

    Attributes
    ----------
    stat : str
        The stat's name.
    base : float
        What the protagonist has before any points are spent, the chosen
        background included.
    minimum, maximum : float
        The stat's own bounds. Spending may not push it past the cap, which is
        the only thing stopping twenty points going into a stat that tops out
        four above where it started.
    """

    stat: str
    base: float
    minimum: float
    maximum: float

    @property
    def room(self) -> int:
        """How many points this stat can still take.

        Returns
        -------
        int
            The distance to the cap, floored at zero.
        """
        return max(0, int(self.maximum - self.base))


@dataclass(frozen=True, slots=True)
class BackgroundOffer:
    """One background, phrased for whoever is choosing.

    Attributes
    ----------
    id : str
        The qualified background id, which is what a `Character` names.
    name : str
        What to call it.
    description : str
        The author's pitch.
    grants : tuple of str
        What picking it does, in English — `strength +8`, `2 × bread`,
        `bow 20`. Built here rather than in each front-end, so the terminal
        and the browser describe a background the same way.
    """

    id: str
    name: str
    description: str
    grants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Creation:
    """Everything a front-end needs to ask the character-creation question.

    Attributes
    ----------
    points : int
        Creation points to spend.
    backgrounds : tuple of BackgroundOffer
        The choices, in the order the game lists them.
    stats : tuple of StatOffer
        The customizable stats, in the order the protagonist declares them.
        `base` is the protagonist's own, before a background moves it — the
        two grants are shown separately because that is how a player reads
        them: this is who you are, and this is what the poacher adds.
    """

    points: int = 0
    backgrounds: tuple[BackgroundOffer, ...] = ()
    stats: tuple[StatOffer, ...] = ()

    @property
    def asks_anything(self) -> bool:
        """Whether there is a question here at all.

        A game with no backgrounds and no creation points has nothing to ask,
        and a front-end that opened an empty menu anyway would be a form.

        Returns
        -------
        bool
            True when the player has something to decide.
        """
        return bool(self.backgrounds) or (self.points > 0 and bool(self.stats))


@dataclass(frozen=True, slots=True)
class Character:
    """What the player answered.

    Attributes
    ----------
    background : str or None
        The chosen background, bare or qualified as the game writes it.
    spend : mapping
        Stat name to points put into it. Absent stats get nothing.
    """

    background: str | None = None
    spend: Mapping[str, int] = field(default_factory=dict)

    @property
    def spent(self) -> int:
        """How many points this allocation uses.

        Returns
        -------
        int
            The total.
        """
        return sum(self.spend.values())


def offer(library: Library, pack_id: str, *, background: str | None = None) -> Creation:
    """Project a game's character-creation question into a view-model.

    Asked twice in the ordinary flow: once with no background, to offer the
    choice, and once with the chosen one, so the points are spent against the
    numbers the player will actually start with. A poacher deciding where his
    last five points go should be looking at his stealth, not Letholin's.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack.
    background : str or None
        A chosen background, whose stat grants are folded into each stat's
        `base`. None shows the protagonist as authored.

    Returns
    -------
    Creation
        What to ask. Empty for a game that offers neither backgrounds nor
        points.

    Raises
    ------
    ContentError
        If the pack is not a playable game, its protagonist is missing, or the
        background names nothing.
    """
    pack = library.pack(pack_id)
    if pack.game is None:
        raise ContentError("is not a playable game pack", pack=pack_id)
    protagonist = _protagonist(library, pack_id, pack.game)

    granted: Mapping[str, object] = {}
    if background is not None:
        chosen = library.find(background, "backgrounds", within=pack_id)
        assert isinstance(chosen, Background)
        granted = chosen.stats

    return Creation(
        points=pack.game.player.creation_points,
        backgrounds=tuple(
            _describe(library, pack_id, reference)
            for reference in pack.game.player.backgrounds
        ),
        stats=tuple(
            StatOffer(
                stat=name,
                base=_granted(granted.get(name), float(stat.base)),
                minimum=float(stat.min),
                maximum=_cap(stat.max),
            )
            for name, stat in (protagonist.stats or {}).items()
            if stat.customizable
        ),
    )


def _granted(grant: object, base: float) -> float:
    """A stat's base once a background has had its say.

    Parameters
    ----------
    grant : object
        The background's `StatGrant` for this stat, or None.
    base : float
        The protagonist's own base.

    Returns
    -------
    float
        What the player starts from.
    """
    return base if not isinstance(grant, StatGrant) else grant.apply(base)


def check(creation: Creation, character: Character) -> tuple[str, ...]:
    """Say what is wrong with an allocation, in the player's terms.

    Front-ends call this before starting, and `begin` calls it again — a
    playtest can hand in an allocation nobody typed, and a stat that silently
    absorbed thirty points would be a very confusing playtest.

    Parameters
    ----------
    creation : Creation
        The question that was asked.
    character : Character
        The answer.

    Returns
    -------
    tuple of str
        One message per problem, or empty when the allocation is legal.
    """
    problems: list[str] = []

    if character.background is not None:
        known = {chosen.id for chosen in creation.backgrounds}
        local = {chosen.id.split(":", 1)[-1] for chosen in creation.backgrounds}
        if character.background not in known | local:
            offered = ", ".join(sorted(local)) or "none"
            problems.append(
                f"`{character.background}` is not a background this game "
                f"offers; it offers: {offered}"
            )
    elif creation.backgrounds:
        problems.append("this game asks you to pick a background")

    if character.spent > creation.points:
        problems.append(
            f"that spends {character.spent} creation points and there are "
            f"{creation.points}"
        )

    room = {stat.stat: stat for stat in creation.stats}
    for name, points in sorted(character.spend.items()):
        if points < 0:
            problems.append(f"`{name}` cannot take {points} points")
        elif name not in room:
            customizable = ", ".join(sorted(room)) or "none"
            problems.append(
                f"`{name}` is not customizable in this game; "
                f"these are: {customizable}"
            )
    return tuple(problems)


def _describe(library: Library, pack_id: str, reference: str) -> BackgroundOffer:
    """Phrase one background for the player choosing it.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack, which the reference is written inside.
    reference : str
        The background as the game manifest names it.

    Returns
    -------
    BackgroundOffer
        The background, with its grants in English.

    Raises
    ------
    ContentError
        If the reference names no background.
    """
    qualified = library.resolve(reference, "backgrounds", within=pack_id)
    found = library.find(reference, "backgrounds", within=pack_id)
    assert isinstance(found, Background)
    return BackgroundOffer(
        id=qualified,
        name=found.label,
        description=found.description,
        grants=grants(found),
    )


def grants(background: Background) -> tuple[str, ...]:
    """Say what a background does, in the order a reader cares about it.

    Stats first, because that is what people compare; then what you are
    carrying, then what you already know how to do. The flag and the opening
    scene are deliberately not listed — a background that quietly changes how
    the captain greets you is a nicer surprise than a bullet point.

    Parameters
    ----------
    background : Background
        The background.

    Returns
    -------
    tuple of str
        One phrase per grant.
    """
    lines: list[str] = []
    for name, grant in background.stats.items():
        if grant.set_ is not None and grant.add is None:
            lines.append(f"{name} {_number(grant.set_)}")
        else:
            total = (grant.set_ or 0.0) + (grant.add or 0.0)
            sign = "+" if total >= 0 else "−"
            lines.append(f"{name} {sign}{_number(abs(total))}")
    for entry in background.inventory:
        item = entry.item.split(":", 1)[-1].replace("-", " ")
        lines.append(f"{entry.qty} × {item}" if entry.qty > 1 else item)
    for item, level in background.skills.items():
        known = item.split(":", 1)[-1].replace("-", " ")
        lines.append(f"skilled with {known} ({level})")
    return tuple(lines)


def _protagonist(library: Library, pack_id: str, game: Game) -> Entity:
    """Find the entity a game's player plays.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack.
    game : Game
        Its manifest.

    Returns
    -------
    Entity
        The protagonist's definition.

    Raises
    ------
    ContentError
        If the entity is missing.
    """
    found = library.find(game.player.entity, "entities", within=pack_id)
    assert isinstance(found, Entity)
    return found


def _cap(maximum: float | None) -> float:
    """A stat's ceiling, defaulted the way the stat pipeline defaults it.

    Parameters
    ----------
    maximum : float or None
        The author's cap, if they set one.

    Returns
    -------
    float
        The ceiling.
    """
    return DEFAULT_ABILITY_MAX if maximum is None else float(maximum)


def _number(value: float) -> str:
    """Render a number without a pointless decimal point.

    Parameters
    ----------
    value : float
        The number.

    Returns
    -------
    str
        `8` rather than `8.0`.
    """
    return str(int(value)) if float(value).is_integer() else str(value)
