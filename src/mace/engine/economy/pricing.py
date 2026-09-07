"""What a market charges, and why.

One formula, applied per good per market, deliberately simple enough that a
player can build an intuition for it without ever seeing a number:

    scarcity = clamp(wanted / max(held, 1), 0.25, 4)
    ratio    = clamp(scarcity ** elasticity, 0.25, 4)
    price    = baseValue × ratio × wealth

`elasticity` is the whole design in one number. Below 1 is a necessity, so a
shortage makes it *dear*: grain at 0.4 quadruples in scarcity to only 1.7×, and
people still buy it. Above 1 is a luxury, so a shortage makes it *absent*:
iron at 1.3 goes to 6× and stops selling. That difference is why elasticity is
content and not engine.

**The second clamp is not in the design doc, and it needs to be.** Docs/08 says
the scarcity clamp is what bounds the price to 0.25×–4× base, and that is only
true while elasticity is at most 1 — the exponent is exactly what breaks it.
The 6× above is the counterexample: a luxury in a famine would price outside
the bound ADR-0007 promises, which is the bound that exists so nobody ever has
to debug hyperinflation in somebody else's game. So the ratio is clamped after
the exponent as well, and docs/08-economy.md now says so.

Nothing here is random and nothing here mutates. A price is a question about
the world, and asking it twice gives the same answer — which is what lets the
debug overlay show prices without changing the playthrough it is describing.

There is no transport-cost multiplier and there is not going to be one. The
design doc listed one, but distance already reaches the price by the honest
road: a market far from a producer gets less carted to it, so it holds less,
so scarcity prices it up. Charging a second time for the same distance would
be double-counting — see `flow`.

The one multiplier that is *not* clamped is the event shock, and that is
deliberate. The clamp exists so no feedback loop can run away; a shock is not
a feedback loop, it is an author saying how bad a siege is. An eruption that
could not push food past four times base would be an eruption a bad winter
had already swallowed. Haggling is the multiplier still missing.

See docs/08-economy.md and ADR-0007.
"""

from __future__ import annotations

from mace.engine.economy.markets import Dealt

__all__ = [
    "MAX_RATIO",
    "MIN_RATIO",
    "price_of",
    "scarcity_of",
    "wealth_factor",
]

#: The hard floor and ceiling on what scarcity may do to a price, as a multiple
#: of the item's `baseValue`. ADR-0007 calls this a deliberate cap on realism
#: bought in exchange for never having to debug a runaway feedback loop.
MIN_RATIO = 0.25
MAX_RATIO = 4.0

#: How far a market's `wealth` may move a price. A hamlet at 0.3 pays 0.9×; a
#: capital at 1.0 pays 1.25×. Deliberately narrow: wealth is the reason to
#: carry something somewhere, and it should never be a bigger reason than
#: scarcity is.
WEALTH_SWING = 0.5


def scarcity_of(dealt: Dealt, held: float) -> float:
    """How short of a good a market is, as a multiplier on its price.

    Parameters
    ----------
    dealt : Dealt
        The good, and what this market wants of it.
    held : float
        Units on the shelf.

    Returns
    -------
    float
        1 when the shelf holds what it wants, above 1 when it is short, below
        when it is glutted. Clamped, so an empty shelf is expensive rather
        than infinite.

    Notes
    -----
    The denominator floors at one unit. A market down to its last sack is as
    short as this model lets it be; the alternative is a divide by zero, and
    a price that goes to infinity as the shelf empties is a price no player
    can read.
    """
    return _clamp(dealt.stock.wanted / max(held, 1.0), MIN_RATIO, MAX_RATIO)


def wealth_factor(wealth: float) -> float:
    """What a place's means do to what it will pay.

    Parameters
    ----------
    wealth : float
        The market's `wealth`, 0 to 1.

    Returns
    -------
    float
        A multiplier. 0.5 — the default — is 1.0, so a market whose author
        said nothing about money pays the going rate.
    """
    return 1.0 + (wealth - 0.5) * WEALTH_SWING


def price_of(dealt: Dealt, held: float, wealth: float, shock: float = 1.0) -> float:
    """What one unit of a good costs at a market.

    Parameters
    ----------
    dealt : Dealt
        The good, resolved against the market that deals in it.
    held : float
        Units on the shelf right now.
    wealth : float
        The market's `wealth`.
    shock : float
        What the world is doing to this price — a siege, an eruption, a good
        harvest. 1.0 is nothing happening. Applied *outside* the clamp on
        purpose: the clamp exists so no feedback loop can run away, and a
        shock is not a feedback loop, it is an author saying how bad this is.
        A world event that could not move a price past four times base would
        be an event a famine could swallow.

    Returns
    -------
    float
        The price. Scarcity may move it by no more than `MIN_RATIO` to
        `MAX_RATIO`, whatever the elasticity — see the module docstring.
    """
    ratio = _clamp(
        scarcity_of(dealt, held) ** dealt.good.elasticity, MIN_RATIO, MAX_RATIO
    )
    return dealt.base_value * ratio * wealth_factor(wealth) * shock


def _clamp(value: float, low: float, high: float) -> float:
    """Hold a value between two bounds.

    Parameters
    ----------
    value : float
        The value.
    low, high : float
        The bounds.

    Returns
    -------
    float
        The value, bounded.
    """
    return min(max(value, low), high)
