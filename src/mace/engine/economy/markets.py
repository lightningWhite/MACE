"""What a market deals in, and how its shelves move while nobody is looking.

Three things happen here, in the order an author would ask about them.

**What does this place trade?** A market names some goods explicitly and
implies the rest through tags: a market tagged `farmland` grows every good
whose `producedBy` says `farmland`. That is what makes a world of twenty
markets cheap to write, and it means the answer has to be *derived* rather than
read, once, up front — `prepare`.

**How much of each does it have?** Stock moves by production and consumption,
and perishable goods rot. A market the player has never seen still has to have
the stock it *would* have had, or arriving somewhere late would find a world
that started when you looked at it. So a market carries `stepped_to` and is
carried forward from there, exactly the way a region's weather is.

**When is it allowed to move?** Catching up mutates, so it may only happen
where time moves or where the player arrives — never from a condition or a
description, or asking what grain costs would change what grain costs and
replay would stop working. That is why the work is split in two:

- `projected` is pure. It answers "what would the shelves hold at tick N"
  without touching anything, and it is what a price query and the debug
  overlay use.
- `sync` commits that answer into the playthrough, and is called only from
  where the engine already accepts that the world moves.

Both run the same loop, so the committed answer and the projected one cannot
disagree.

Catching up is deliberately a tick-by-tick loop rather than a closed form.
Production and consumption alone would have one — a constant net rate is just
multiplication — but spoilage is proportional to what is on the shelf, and
trade flow (still ahead) will make the rate depend on what the *neighbours*
hold that tick. Stepping is what all three have in common, and a fast-forward
that gives a different answer from stepping would be a bug that only showed up
in playthroughs nobody replayed.

See docs/08-economy.md and ADR-0007.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mace.content import Library
from mace.engine.state import GameState, MarketState
from mace.model import Entity, Good, Market, Stock

__all__ = [
    "DEFAULT_DEPTH",
    "IMPLIED_FLOW",
    "Dealt",
    "Prepared",
    "at",
    "prepare",
    "projected",
    "sync",
]

#: Units per tick a tag implies for a village-sized market, scaled by size so
#: that tagging a city `farmland` grows a city's worth of grain. Small on
#: purpose: half a unit a tick is a few hundred over a season, which is what a
#: village's shelves hold.
IMPLIED_FLOW = 0.5

#: The shelf depth a village-sized market gets for a good it deals in and did
#: not size by hand, scaled the same way.
DEFAULT_DEPTH = 100.0


@dataclass(frozen=True, slots=True)
class Dealt:
    """One good a market deals in, with everything pricing it needs resolved.

    Attributes
    ----------
    good : Good
        The good's market behaviour.
    item : Entity
        The item it is the behaviour of. Its `baseValue` anchors the price.
    stock : Stock
        How much this market holds and wants of it.
    produced : float
        Units made per tick, from an explicit `produces` entry or implied by
        the market's tags.
    consumed : float
        Units used per tick, the same way.
    """

    good: Good
    item: Entity
    stock: Stock
    produced: float = 0.0
    consumed: float = 0.0

    @property
    def base_value(self) -> float:
        """The item's price anchor.

        Returns
        -------
        float
            `item.baseValue`, or 0 for an item nobody priced. A good on a
            valueless item is free, which is odd but is what the author said.
        """
        if self.item.item is None or self.item.item.base_value is None:
            return 0.0
        return self.item.item.base_value

    @property
    def net(self) -> float:
        """How fast the shelf fills, before spoilage.

        Returns
        -------
        float
            Units per tick. Negative for a place that eats more than it makes.
        """
        return self.produced - self.consumed


@dataclass(frozen=True, slots=True)
class Prepared:
    """A market, resolved: where it is, and everything it deals in.

    Attributes
    ----------
    market : Market
        The definition.
    home : str
        The pack it was written in, which its bare references resolve against.
    location : str
        Qualified id of the location it sits at.
    goods : dict
        Qualified good id to what this market does with it, in a fixed order
        so that anything iterating it does so identically every replay.
    """

    market: Market
    home: str
    location: str
    goods: dict[str, Dealt] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """The market's qualified id.

        Returns
        -------
        str
            `pack:local-id`.
        """
        return f"{self.home}:{self.market.id}"


def prepare(library: Library) -> dict[str, Prepared]:
    """Resolve every market and everything it deals in, once.

    Parameters
    ----------
    library : Library
        The loaded content.

    Returns
    -------
    dict
        Qualified market id to the resolved market, in a fixed order.
    """
    prepared: dict[str, Prepared] = {}
    for pack in library.packs:
        for local_id in sorted(pack.markets):
            resolved = _resolve(library, pack.id, pack.markets[local_id])
            prepared[resolved.id] = resolved
    return prepared


def at(prepared: dict[str, Prepared], location: str) -> Prepared | None:
    """The market at a location, if there is one.

    Parameters
    ----------
    prepared : dict
        The output of `prepare`.
    location : str
        Qualified location id.

    Returns
    -------
    Prepared or None
        The market standing there. Two markets in one place is content the
        loader allows and nothing here has an opinion about; the first in
        preparation order wins, which is stable across replays.
    """
    for market in prepared.values():
        if market.location == location:
            return market
    return None


def _resolve(library: Library, home: str, market: Market) -> Prepared:
    """Work out what one market deals in.

    Explicit `produces` and `consumes` win over what the tags imply, because
    an author who wrote a number meant that number. A good named by neither —
    listed only in `stock` or `trades` — is dealt in at no flow at all, which
    is what a middleman is.

    Parameters
    ----------
    library : Library
        The loaded content.
    home : str
        The pack the market was written in.
    market : Market
        The definition.

    Returns
    -------
    Prepared
        The market with its goods resolved.
    """
    location = library.resolve(market.location, "locations", within=home)

    produced: dict[str, float] = {}
    consumed: dict[str, float] = {}
    for flow in market.produces:
        produced[_good_id(library, home, flow.good)] = flow.per_tick
    for flow in market.consumes:
        consumed[_good_id(library, home, flow.good)] = flow.per_tick

    # Stock written by hand, and goods traded without being made or used.
    # Both are keyed by the qualified id, because an author may name a good
    # bare in one place and qualified in another and mean the same good.
    written = {
        _good_id(library, home, reference): entry
        for reference, entry in market.stock.items()
    }
    traded = {_good_id(library, home, reference) for reference in market.trades}

    # Tags imply a flow only where the author did not write one. A market that
    # says `produces: [{good: grain, perTick: 0.8}]` and is also tagged
    # `farmland` grows 0.8 of it, not 0.8 plus a default.
    tags = set(market.tags)
    goods = {
        f"{pack.id}:{local_id}": pack.goods[local_id]
        for pack in library.packs
        for local_id in sorted(pack.goods)
    }
    for good_id, good in goods.items():
        if tags & set(good.produced_by):
            produced.setdefault(good_id, IMPLIED_FLOW * market.depth)
        if tags & set(good.consumed_by):
            consumed.setdefault(good_id, IMPLIED_FLOW * market.depth)

    dealt = {
        good_id: Dealt(
            good=goods[good_id],
            item=_item(library, good_id, goods[good_id]),
            stock=written.get(good_id) or Stock(capacity=DEFAULT_DEPTH * market.depth),
            produced=produced.get(good_id, 0.0),
            consumed=consumed.get(good_id, 0.0),
        )
        for good_id in sorted({*produced, *consumed, *written, *traded})
    }
    return Prepared(market=market, home=home, location=location, goods=dealt)


def _good_id(library: Library, home: str, reference: str) -> str:
    """Qualify a reference to a good.

    Parameters
    ----------
    library : Library
        The loaded content.
    home : str
        The pack the reference was written in.
    reference : str
        As the author wrote it.

    Returns
    -------
    str
        The qualified good id.
    """
    return library.resolve(reference, "goods", within=home)


def _item(library: Library, good_id: str, good: Good) -> Entity:
    """The item a good is the market behaviour of.

    Parameters
    ----------
    library : Library
        The loaded content.
    good_id : str
        The good's qualified id, for the pack its `item` resolves against.
    good : Good
        The good.

    Returns
    -------
    Entity
        The item.
    """
    home = good_id.split(":", 1)[0]
    found = library.find(good.item, "entities", within=home)
    assert isinstance(found, Entity)
    return found


def projected(held: MarketState, prepared: Prepared, to_tick: int) -> dict[str, float]:
    """What a market's shelves would hold at a tick, without moving them.

    Pure: a question about the world must not change it (the same rule the
    weather's `sync` follows), so this is what a price and the debug overlay
    read. `sync` runs the identical loop and keeps the answer.

    Parameters
    ----------
    held : MarketState
        Where the shelves have got to.
    prepared : Prepared
        The market, resolved.
    to_tick : int
        The tick to carry them to. A tick already passed carries nothing.

    Returns
    -------
    dict
        Qualified good id to units held.
    """
    stock = dict(held.stock)
    for _ in range(max(0, to_tick - held.stepped_to)):
        _step(stock, prepared)
    return stock


def sync(
    state: GameState,
    prepared: Prepared,
    to_tick: int | None = None,
) -> MarketState:
    """Bring one market up to now, opening it if it has never been looked at.

    Called where time moves and where the player arrives somewhere, never from
    a condition — see the module docstring.

    A market opened late is opened at the playthrough's *start* tick and
    carried forward, so arriving somewhere on day fifty finds the shelves it
    would have had all along rather than shelves that began when you looked.

    Parameters
    ----------
    state : GameState
        The playthrough. The market is created or advanced in place.
    prepared : Prepared
        The market, resolved.
    to_tick : int or None
        The tick to carry it to. Defaults to now.

    Returns
    -------
    MarketState
        The market's shelves, current.
    """
    target = state.tick if to_tick is None else to_tick
    held = state.markets.get(prepared.id)
    if held is None:
        held = MarketState(
            market=prepared.id,
            stock={
                good_id: dealt.stock.opening
                for good_id, dealt in prepared.goods.items()
            },
            stepped_to=state.start_tick,
        )
        state.markets[prepared.id] = held

    if target <= held.stepped_to:
        return held

    held.stock = projected(held, prepared, target)
    held.stepped_to = target
    return held


def _step(stock: dict[str, float], prepared: Prepared) -> None:
    """Move one market's shelves by one tick, in place.

    Order matters and is part of the contract: a thing is made, then it is
    used, then what is left of it rots. Rotting first would spoil grain that
    was eaten that same tick.

    Parameters
    ----------
    stock : dict
        Qualified good id to units held, updated in place.
    prepared : Prepared
        The market, resolved.
    """
    for good_id, dealt in prepared.goods.items():
        held = stock.get(good_id, 0.0) + dealt.net
        if dealt.good.perishable is not None:
            # A unit lasts `ticksToSpoil`, so that fraction of the shelf is
            # lost each tick. Proportional rather than per-unit ageing: the
            # player sees a shelf, not a queue of sacks with dates on them.
            held -= max(held, 0.0) / dealt.good.perishable.ticks_to_spoil
        stock[good_id] = min(max(held, 0.0), dealt.stock.capacity)
