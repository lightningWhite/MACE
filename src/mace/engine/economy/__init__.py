"""Goods, markets, price formation, and trade flow between markets.

A market's shelves move with production, consumption and spoilage, and what it
charges falls out of how much it holds against how much it wants. Markets are
carried forward when something looks at them rather than stepped every tick, so
a hundred of them cost nothing until they matter — see `markets` for why that
is a fast-forward and not a different world.

Nothing here draws randomness yet. When it does — production jitter, merchant
restock — it must draw from a *position*, hashed from the tick, rather than
walking the `economy` stream in sequence: a lazily caught-up subsystem would
otherwise land at a different stream position depending on when the player
happened to look, and two playthroughs with the same action log would diverge.

See docs/08-economy.md.
"""

from mace.engine.economy.markets import (
    DEFAULT_DEPTH,
    IMPLIED_FLOW,
    Dealt,
    Prepared,
    at,
    prepare,
    projected,
    sync,
)
from mace.engine.economy.pricing import (
    MAX_RATIO,
    MIN_RATIO,
    price_of,
    scarcity_of,
    wealth_factor,
)

__all__ = [
    "DEFAULT_DEPTH",
    "IMPLIED_FLOW",
    "MAX_RATIO",
    "MIN_RATIO",
    "Dealt",
    "Prepared",
    "at",
    "prepare",
    "price_of",
    "projected",
    "scarcity_of",
    "sync",
    "wealth_factor",
]
