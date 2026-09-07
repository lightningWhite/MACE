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
from mace.model.text import Description

__all__ = [
    "MARKET_SIZES",
    "Deals",
    "Flow",
    "Good",
    "Market",
    "Merchant",
    "Perishable",
    "Size",
    "Stock",
]

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


class Deals(ContentModel):
    """Which goods a merchant will take, or part with.

    Naming nothing means everything its market deals in, which is what most
    merchants are. A filter is for the specialist: the smith who buys metal
    and is not interested in your wool.

    Attributes
    ----------
    goods : tuple of str
        Named goods.
    categories : tuple of str
        Whole classes of good, by a good's `category`. `[food]` is every good
        an author has labelled food, including ones written after this
        merchant was.
    """

    goods: tuple[GoodRef, ...] = ()
    categories: tuple[Tag, ...] = ()

    @property
    def everything(self) -> bool:
        """Whether this filter narrows anything at all.

        Returns
        -------
        bool
            True when neither list says anything, which means the whole
            market.
        """
        return not self.goods and not self.categories


class Merchant(ContentModel):
    """An actor who buys and sells against a market's prices.

    A merchant is the way a player reaches a market at all. The shelves and
    the prices belong to the settlement — a market is a town, not a shop — and
    this is the person standing in front of them who will deal with you, which
    is why the block sits on an actor rather than on a location.

    Attributes
    ----------
    market : str or None
        Which market it deals for. None is the market where it is standing,
        which is what a merchant usually is.
    spread : float
        The gap between what it buys at and what it sells at, as a fraction of
        the market price. 0.25 buys at 0.875× and sells at 1.125×. This is the
        merchant's living, and the reason carrying goods somewhere else can
        beat selling them here.
    buys, sells : Deals
        What it will take off you, and what it will part with.
    capital : float or None
        What it can pay out, in the game's currency. None is bottomless, which
        is what a market stall backed by a whole town is; a number makes it a
        person with a purse, and the difference is that a player who arrives
        with forty sacks of grain finds out the buyer has run out of money.
        The purse is the coin in the merchant's own `inventory`, so an author
        who wrote one has already set the opening balance and a scene that
        hands the merchant money is not a second system.
    restock_ticks : int or None
        How often the purse comes back up to `capital` — the caravan arriving,
        the week's takings banked. None means it never does, so a merchant
        cleaned out stays cleaned out. Restocking never takes money *away*: a
        merchant who had a good day keeps it.
    max_swing : float or None
        How far haggling can move this merchant's price, as a fraction of the
        item's value. None is a merchant who does not haggle — a quartermaster
        with a ledger and a fixed rate, which is a real kind of person and the
        right default. 0.2 is a peddler who expects to be argued with.
    patience : int
        How many pushes it takes before the odds turn against the player. Low
        is a merchant who sours fast. Only meaningful with `maxSwing`.
    prompt : str or None
        What the option to trade is called. None is `Trade with <name>`.
    remarks : Description
        What it says about its own prices, first matching line. Written as
        ordinary conditional description, so `priceOf` is what makes a line
        about a shortage and the weather and the season can join in —
        "Grain? You'll pay for grain this week."
    """

    market: MarketRef | None = None
    spread: float = Field(default=0.2, ge=0.0, lt=1.0)
    buys: Deals = Deals()
    sells: Deals = Deals()
    capital: float | None = Field(default=None, ge=0.0)
    restock_ticks: int | None = Field(default=None, gt=0)
    max_swing: float | None = Field(default=None, gt=0.0, le=1.0)
    patience: int = Field(default=3, ge=1)
    prompt: str | None = None
    remarks: Description = ()

    @model_validator(mode="after")
    def _restock_has_something_to_restock(self) -> Merchant:
        """A purse that refills to nothing in particular is a typo."""
        if self.restock_ticks is not None and self.capital is None:
            raise ValueError("`restockTicks` needs a `capital` to come back up to")
        return self
