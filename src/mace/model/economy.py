"""Goods and markets — the content half of a living economy.

A **good** is not a new kind of thing. It is the market behaviour of an item
that already exists, which is why it names one rather than redeclaring its
name, weight and value. [ADR-0002](../../docs/decisions/0002-unified-entity-model.md)
spent a whole decision on there being one `Entity`; a parallel `grain` that is
a good and a separate `grain` that is an item would undo that quietly, and the
first bug would be a shop selling something the player cannot carry.

A **market** is a settlement's stock and prices. It sits at a location, it
produces some things and consumes others, and what it charges falls out of how
much of a thing it has against how much it wants — see `mace.engine.economy`.

Two numbers carry most of the design:

`elasticity` decides whether a shortage means *expensive* or *absent*. Grain at
0.4 gets dear and people still buy it; a luxury at 1.4 simply stops selling.
Getting these right is most of economic balance, which is why it is content and
not engine.

`wealth` is what a place will pay. A city pays over the odds for what it wants
and a hamlet cannot, and that difference is a reason to carry something
somewhere.

See docs/08-economy.md and [ADR-0007](../../docs/decisions/0007-full-market-economy.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, model_validator

from mace.model.base import (
    ContentModel,
    EntityRef,
    GoodRef,
    Id,
    LocationRef,
    MarketRef,
    Tag,
)

__all__ = ["MARKET_SIZES", "Flow", "Good", "Market", "Perishable", "Size", "Stock"]

#: How big a place is, and how deep its shelves are. The multiplier scales a
#: good's default capacity, so an author who writes `size: city` gets a city's
#: stock without writing a number per good.
MARKET_SIZES: dict[str, float] = {
    "hamlet": 0.35,
    "village": 1.0,
    "town": 3.0,
    "city": 9.0,
}

Size = Literal["hamlet", "village", "town", "city"]


class Perishable(ContentModel):
    """A good that does not keep.

    Attributes
    ----------
    ticks_to_spoil : int
        How long a unit lasts before it is worth nothing. Perishability is
        what stops a player buying out a harvest and sitting on it.
    """

    ticks_to_spoil: int = Field(gt=0)


class Flow(ContentModel):
    """A good a market makes or uses, and how fast.

    Attributes
    ----------
    good : str
        Which good.
    per_tick : float
        Units per tick. Small numbers: a hamlet growing 0.8 grain a tick is
        producing a few hundred over a season, which is what its shelves hold.
    """

    good: GoodRef
    per_tick: float = Field(gt=0.0)


class Stock(ContentModel):
    """How much of one good a market holds, and how much it wants.

    Attributes
    ----------
    capacity : float
        The most it can hold. Above this, production spills and is lost —
        a market is a town, not a warehouse.
    target : float or None
        What it aims to have. Scarcity is measured against this, so it is the
        number that decides the price. None is half of capacity: a place that
        would like its shelves comfortably stocked and not groaning.
    initial : float or None
        What it starts a playthrough with. None is `target`, so a game opens
        at the ordinary price rather than in a shortage nobody wrote.
    """

    capacity: float = Field(gt=0.0)
    target: float | None = Field(default=None, gt=0.0)
    initial: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _fits(self) -> Stock:
        """Wanting or starting with more than it can hold is a typo."""
        for name in ("target", "initial"):
            value = getattr(self, name)
            if value is not None and value > self.capacity:
                raise ValueError(
                    f"{name} ({value}) is above capacity ({self.capacity})"
                )
        return self

    @property
    def wanted(self) -> float:
        """What the market aims to hold.

        Returns
        -------
        float
            `target`, or half of capacity.
        """
        return self.capacity / 2 if self.target is None else self.target

    @property
    def opening(self) -> float:
        """What it holds when a playthrough starts.

        Returns
        -------
        float
            `initial`, or whatever it wants.
        """
        return self.wanted if self.initial is None else self.initial


class Good(ContentModel):
    """An item with market behaviour.

    Attributes
    ----------
    id : str
        Identity.
    extends : str or None
        A good to inherit from.
    item : str
        The item this is the market behaviour of. Its `baseValue` is the price
        anchor and its `weight` is what a cartload costs to carry — both live
        on the item, because a good is not a second kind of bread.
    category : str or None
        A label a shock or a merchant can name a whole class of goods by:
        `food`, `metal`, `luxury`.
    elasticity : float
        How hard demand falls as the price rises. Below 1 is a necessity —
        scarcity makes it expensive. Above 1 is a luxury — scarcity makes it
        simply absent. This is the single most load-bearing number in the
        economy.
    perishable : Perishable or None
        What spoils, and how fast.
    produced_by, consumed_by : tuple of str
        Market tags. A market tagged `farmland` grows every good that names
        `farmland` here, without listing them one by one — which is what
        makes a world of twenty markets cheap to write. An explicit
        `produces`/`consumes` entry on the market overrides it.
    """

    id: Id
    extends: GoodRef | None = None
    item: EntityRef
    category: Tag | None = None
    elasticity: float = Field(default=1.0, gt=0.0)
    perishable: Perishable | None = None
    produced_by: tuple[Tag, ...] = ()
    consumed_by: tuple[Tag, ...] = ()


class Market(ContentModel):
    """A settlement's shelves and what it charges for what is on them.

    Attributes
    ----------
    id : str
        Identity.
    extends : str or None
        A market to inherit from.
    location : str
        Where it is. A player has to be standing here to trade.
    name : str or None
        What to call it. None takes the location's name.
    size : {'hamlet', 'village', 'town', 'city'}
        How deep its shelves are, by way of `MARKET_SIZES`.
    wealth : float
        0 to 1. What this place will pay: a city bids over the odds for what
        it wants, a hamlet cannot afford to.
    tags : tuple of str
        Labels a good's `producedBy` and `consumedBy` match against.
    produces, consumes : tuple of Flow
        What it makes and uses, per tick, spelled out. Overrides whatever the
        tags would have implied.
    stock : mapping
        Good to how much of it this market holds. A good it produces,
        consumes or trades and does not list here gets a default depth from
        its `size`.
    trades : tuple of str
        Goods it will buy and sell without making or using them — a
        middleman's stock in trade.
    """

    id: Id
    extends: MarketRef | None = None
    location: LocationRef
    name: str | None = None

    size: Size = "village"
    wealth: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: tuple[Tag, ...] = ()

    produces: tuple[Flow, ...] = ()
    consumes: tuple[Flow, ...] = ()
    stock: Mapping[GoodRef, Stock] = Field(default_factory=dict)
    trades: tuple[GoodRef, ...] = ()

    @property
    def depth(self) -> float:
        """How much this market's size scales its default shelves by.

        Returns
        -------
        float
            The multiplier from `MARKET_SIZES`.
        """
        return MARKET_SIZES[self.size]
