"""Arguing over a price, which is a decision rather than a stat check.

The design constraint from docs/08 is the whole of this module: **knowing when
to stop is the skill.** A haggle that were a single roll against charisma would
be a button the player presses once and never thinks about; a haggle with no
ceiling would be a button they press until the price is zero. So every push is
likelier to sour than the last, and the player chooses how far to go.

Three things decide a push, in this order:

- **Charisma** sets the odds. It is the one place in the game where a talker
  beats a fighter, and it is deliberately not a threshold — a charmless player
  can still win an argument, less often.
- **How many pushes already** turns the odds. Past a merchant's `patience` the
  chance of a concession falls and the chance of souring rises, which is what
  makes the third push a real decision rather than a free one.
- **What the player knows** shifts both. A player who has personally been
  quoted a better price for this good somewhere else has something to say, and
  saying it works. That is the docs' "local knowledge helps", and it is why the
  price memory exists.

A soured merchant deals at *worse* than their opening spread for a while.
Refusing to trade at all would be cleaner to model and worse to play: a player
who overreached should feel it in the price and be able to come back, not be
locked out of the only shop in the valley.

Randomness comes from the `haggle` stream in sequence, which is allowed here
and nowhere else in `economy`: this is an action the player takes, not a
subsystem caught up lazily, so it cannot land at a different stream position
depending on when somebody looked.

See docs/08-economy.md § Merchants and haggling.
"""

from __future__ import annotations

from dataclasses import dataclass

from mace.engine.context import RuleContext
from mace.engine.state import EntityState, Haggle
from mace.engine.stats import effective
from mace.model import Merchant

__all__ = ["MOOD_TICKS", "Outcome", "leverage", "push", "standing", "swing_of"]

#: The stat a haggle is argued with. Content names its own stats and the engine
#: knows none of them, so this is the one concession: a game with no
#: `charisma` haggles at the middling odds, which is the right answer for a
#: world where nobody is a talker.
CHARISMA = "charisma"

#: How long a soured merchant stays sour. Two days: long enough to be a real
#: cost, short enough that a player is not locked out of the only shop for the
#: rest of the game.
MOOD_TICKS = 96

#: What souring does to the spread while it lasts, as a fraction.
SOUR_SWING = -0.1

#: How much of the room a single concession gives up. A third, so a good
#: haggler needs three clean pushes to reach the ceiling — and by the third
#: the odds have turned.
CONCESSION = 1 / 3

#: How much having seen a better price elsewhere is worth, in odds.
KNOWING = 0.2


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one push did.

    Attributes
    ----------
    result : {'gave', 'held', 'soured'}
        Which of the three things happened.
    swing : float
        Where the price stands afterwards, as a fraction of the item's value.
        Negative after a souring.
    pushes : int
        How many times the player has pressed, including this one.
    leverage : bool
        Whether the player had seen a better price elsewhere and said so.
    """

    result: str
    swing: float
    pushes: int
    leverage: bool = False


def standing(context: RuleContext, entity: EntityState) -> Haggle:
    """Where the argument with one merchant stands.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The merchant's instance.

    Returns
    -------
    Haggle
        The standing. A soured one that has run its course is cleared here,
        which is the only place a mood expires.
    """
    held = context.state.haggles.get(entity.instance_id)
    if held is None:
        return Haggle()
    if held.soured_until is not None and context.state.tick >= held.soured_until:
        return Haggle()
    return held


def swing_of(context: RuleContext, entity: EntityState) -> float:
    """How far this merchant's price has been argued, right now.

    Pure: reading a standing must not clear a mood that has not expired, and
    must not start one that has not been argued.

    Parameters
    ----------
    context : RuleContext
        The playthrough. Read only.
    entity : EntityState
        The merchant's instance.

    Returns
    -------
    float
        A fraction to take off the spread. Zero when nothing has been said.
    """
    return standing(context, entity).swing


def leverage(
    context: RuleContext, market_id: str, goods: tuple[str, ...], quoted: dict[str, int]
) -> bool:
    """Whether the player has been quoted a better price for any of this.

    The docs' "local knowledge helps", made of the only thing that could
    honestly stand for knowledge: prices the player has personally been
    quoted, somewhere else, and can therefore say out loud.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    market_id : str
        The market being argued with, which does not count against itself.
    goods : tuple of str
        The goods on this counter.
    quoted : dict
        Good id to what this counter is asking now.

    Returns
    -------
    bool
        Whether anywhere else was cheaper for something on this counter.
    """
    for where, seen in context.state.prices.items():
        if where == market_id:
            continue
        for good_id in goods:
            elsewhere, here = seen.get(good_id), quoted.get(good_id)
            if elsewhere is not None and here is not None and elsewhere < here:
                return True
    return False


def odds(charisma: float, pushes: int, patience: int, *, knowing: bool) -> float:
    """The chance a merchant gives ground on this push.

    Parameters
    ----------
    charisma : float
        The player's, 0 to 100.
    pushes : int
        How many pushes have already been made.
    patience : int
        How many the merchant takes in their stride.
    knowing : bool
        Whether the player has a better price to point at.

    Returns
    -------
    float
        0 to 1.
    """
    skill = min(max(charisma / 100.0, 0.0), 1.0)
    over = max(0, pushes - patience + 1)
    chance = 0.2 + 0.6 * skill - 0.22 * over
    return min(max(chance + (KNOWING if knowing else 0.0), 0.02), 0.95)


def souring(charisma: float, pushes: int, patience: int, *, knowing: bool) -> float:
    """The chance a merchant takes offense instead.

    Parameters
    ----------
    charisma : float
        The player's, 0 to 100.
    pushes : int
        How many pushes have already been made.
    patience : int
        How many the merchant takes in their stride.
    knowing : bool
        Whether the player has a better price to point at.

    Returns
    -------
    float
        0 to 1. Zero while the merchant is still being patient, which is what
        makes the first push free and the fourth a gamble.
    """
    over = max(0, pushes - patience + 1)
    if over <= 0:
        return 0.0
    skill = min(max(charisma / 100.0, 0.0), 1.0)
    chance = 0.18 * over - 0.2 * skill - (KNOWING / 2 if knowing else 0.0)
    return min(max(chance, 0.0), 0.75)


def _charisma(context: RuleContext) -> float:
    """How persuasive the player is, in a world that may not have a word for it.

    Content names its own stats and the engine knows none of them. A game
    that declares no `charisma` is a game where nobody is a talker, and the
    honest answer there is middling odds for everyone rather than the worst
    odds for everyone.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    float
        0 to 100.
    """
    player = context.state.protagonist
    definition = context.definition(player)
    if CHARISMA not in (definition.stats or {}):
        return 50.0
    return effective(definition, player, CHARISMA)


def push(
    context: RuleContext,
    entity: EntityState,
    merchant: Merchant,
    *,
    knowing: bool = False,
) -> Outcome:
    """Press a merchant on their price, once.

    Parameters
    ----------
    context : RuleContext
        The playthrough. The standing is recorded.
    entity : EntityState
        The merchant's instance.
    merchant : Merchant
        Its block, for `maxSwing` and `patience`.
    knowing : bool
        Whether the player can point at a better price elsewhere.

    Returns
    -------
    Outcome
        What happened.

    Raises
    ------
    RuleError
        If this merchant does not haggle, or is still sour.
    """
    from mace.engine.conditions import RuleError

    if merchant.max_swing is None:
        raise RuleError("they are not going to argue about it")

    held = standing(context, entity)
    if held.soured_until is not None:
        raise RuleError("they have heard enough from you for now")

    charisma = _charisma(context)
    stream = context.state.rng.stream(f"haggle.{entity.instance_id}")

    pushes = held.pushes + 1
    if stream.chance(odds(charisma, held.pushes, merchant.patience, knowing=knowing)):
        swing = min(held.swing + merchant.max_swing * CONCESSION, merchant.max_swing)
        result, soured = "gave", None
    elif stream.chance(
        souring(charisma, held.pushes, merchant.patience, knowing=knowing)
    ):
        swing, result = SOUR_SWING, "soured"
        soured = context.state.tick + MOOD_TICKS
    else:
        swing, result, soured = held.swing, "held", None

    context.state.haggles[entity.instance_id] = Haggle(
        swing=swing, pushes=pushes, soured_until=soured
    )
    return Outcome(result=result, swing=swing, pushes=pushes, leverage=knowing)
