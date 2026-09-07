"""Goods, markets, price formation, and trade flow between markets.

`markets` is the content half: what a place deals in, and which roads reach it.
`flow` is the playthrough half: how shelves move, and how goods cross a road to
wherever they are worth more. `pricing` is the one formula that turns a shelf
into a number.

Markets are carried forward when something looks at them rather than stepped
every tick, so a hundred of them cost nothing until they matter — and because a
road makes two markets depend on each other, they are carried forward a whole
trading group at a time. See `flow` for why that is a fast-forward and not a
different world.

`trade` is the counter — buying, selling, and a merchant's purse — and
`haggle` is the argument over the bill.

**Only `haggle` draws randomness, and only because it is an action.** Anything
caught up lazily must draw from a *position* hashed from the tick rather than
walking a stream in sequence: it would otherwise land at a different stream
position depending on when the player happened to look, and two playthroughs
with the same action log would diverge. A push is taken in sequence like a
sword swing, so a named stream is both allowed and correct.

See docs/08-economy.md.
"""

from mace.engine.economy.flow import (
    DANGER_WEIGHT,
    MAX_SHARE,
    TRADE_RATE,
    haulage,
    hauled,
    opening,
    projected,
    shock_on,
    sync,
)
from mace.engine.economy.markets import (
    DEFAULT_DEPTH,
    IMPLIED_FLOW,
    Dealt,
    Group,
    Link,
    Network,
    Prepared,
    at,
    prepare,
)
from mace.engine.economy.pricing import (
    MAX_RATIO,
    MIN_RATIO,
    price_of,
    scarcity_of,
    wealth_factor,
)

__all__ = [
    "DANGER_WEIGHT",
    "DEFAULT_DEPTH",
    "IMPLIED_FLOW",
    "MAX_RATIO",
    "MAX_SHARE",
    "MIN_RATIO",
    "TRADE_RATE",
    "Dealt",
    "Group",
    "Link",
    "Network",
    "Prepared",
    "at",
    "haulage",
    "hauled",
    "opening",
    "prepare",
    "price_of",
    "projected",
    "scarcity_of",
    "shock_on",
    "sync",
    "wealth_factor",
]
