"""What a market deals in, and which roads reach it.

Three questions, in the order an author would ask them.

**What does this place trade?** A market names some goods explicitly and
implies the rest through tags: a market tagged `farmland` grows every good
whose `producedBy` says `farmland`. That is what makes a world of twenty
markets cheap to write, and it means the answer has to be *derived* rather than
read, once, up front — `prepare`.

**Who does it trade with?** A route whose two ends both have a market is a
road that goods move along, and `prepare` turns the route graph into a
`Network` of `Link`s. Markets reachable from each other form a `Group`, and a
group is the unit everything downstream works in: shelves in one group move
together because they pull on each other, and two groups with no road between
them are two economies that happen to share a world.

**How does any of it move?** That is `flow`, next door. It is a separate
module because this one is about content — what the author wrote, resolved
once — and that one is about a playthrough, which is the only thing allowed to
change.

A link is a route between two market *locations*, directly. A road that runs
from one town to another through a pass with no market at it is still one
route and still a link; a chain of two routes meeting at a market-less
crossroads is not, and goods will not cross it. That is a real limit and worth
knowing when laying out a map: put a market where trade should pass through,
or draw the long route as one route.

See docs/08-economy.md and ADR-0007.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mace.content import ContentError, Library
from mace.model import Entity, Good, Market, Stock

__all__ = [
    "DEFAULT_DEPTH",
    "IMPLIED_FLOW",
    "Dealt",
    "Group",
    "Link",
    "Network",
    "Prepared",
    "at",
    "dealt_in",
    "prepare",
]

#: Units per tick a tag implies for a village-sized market, scaled by size so
#: that tagging a city `farmland` grows a city's worth of grain.
#:
#: Small against `DEFAULT_DEPTH` on purpose: a tenth of a unit a tick is about
#: ten days of a village's shelves, which is the stock a market keeps. It was
#: five times this until trade flow arrived, and nothing noticed, because
#: until markets fed each other a village that ate half its shelf a day simply
#: ran out and stayed out.
IMPLIED_FLOW = 0.1

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
    item_id : str
        That item's qualified id — what an inventory is keyed by, so trade can
        put the sack a market priced into the pack the player carries.
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
    item_id: str
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
    region : str or None
        Qualified id of the region that location is in, resolved once here
        rather than per price — a shock lands on a region, and asking which
        region a market is in inside the hauling loop would be asking the same
        question a few thousand times a season.
    goods : dict
        Qualified good id to what this market does with it, in a fixed order
        so that anything iterating it does so identically every replay.
    """

    market: Market
    home: str
    location: str
    region: str | None = None
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


@dataclass(frozen=True, slots=True)
class Link:
    """A road between two markets, and everything trade over it depends on.

    Attributes
    ----------
    route : str
        Qualified route id. What the playthrough's `RouteState` is keyed by,
        so a landslide that shuts this road is found through it.
    origin, destination : str
        Qualified market ids, the route's two ends.
    ticks : int
        How long the road is, as written. A playthrough may have lengthened
        it since; `flow` prefers the `RouteState` when there is one.
    capacity : float
        `tradeCapacity` — how much traffic the road carries against an
        ordinary road's one.
    danger : int
        `dangerLevel`, 0 to 10. Bandit country throttles trade, which is what
        makes it expensive country.
    both_ways : bool
        Whether goods may move in either direction. A one-way route carries
        trade one way too.
    """

    route: str
    origin: str
    destination: str
    ticks: int
    capacity: float
    danger: int
    both_ways: bool


@dataclass(frozen=True, slots=True)
class Group:
    """Markets that can reach each other, and the roads that let them.

    A group is the unit shelves move in. Two markets joined by a road pull on
    each other's prices every tick, so neither can be carried forward alone —
    see `flow`.

    Attributes
    ----------
    markets : tuple of str
        Qualified market ids, sorted, so anything walking them walks them the
        same way every replay.
    links : tuple of Link
        The roads inside this group, in a fixed order for the same reason.
    """

    markets: tuple[str, ...]
    links: tuple[Link, ...]


@dataclass(frozen=True, slots=True)
class Network:
    """Every market in a library, and the roads between them.

    Attributes
    ----------
    markets : dict
        Qualified market id to the resolved market, in a fixed order.
    links : tuple of Link
        Every road between two markets, in a fixed order.
    groups : tuple of Group
        The markets partitioned by what can reach what. Every market is in
        exactly one group; a market no road reaches is a group of one.
    """

    markets: dict[str, Prepared]
    links: tuple[Link, ...]
    groups: tuple[Group, ...]

    def group(self, market_id: str) -> Group:
        """The trading group one market belongs to.

        Parameters
        ----------
        market_id : str
            Qualified market id.

        Returns
        -------
        Group
            The group containing it.

        Raises
        ------
        KeyError
            If no market has that id.
        """
        for group in self.groups:
            if market_id in group.markets:
                return group
        raise KeyError(market_id)

    def touching(self, route_id: str) -> tuple[Group, ...]:
        """The groups a road runs inside.

        What a landslide has to bring up to date before it lands: shutting a
        road changes how every shelf in the group moves from that tick on, so
        the ticks *before* it have to be committed first. See
        `mace.engine.effects`.

        Parameters
        ----------
        route_id : str
            Qualified route id.

        Returns
        -------
        tuple of Group
            The groups containing a link on that route, in a fixed order.
            Empty when the road joins nothing that trades.
        """
        return tuple(
            group
            for group in self.groups
            if any(link.route == route_id for link in group.links)
        )


def dealt_in(library: Library) -> dict[str, Dealt]:
    """Every good in a library, resolved, with no market behind it.

    What a caravan deals in. It has no shelves and no scarcity — it carries
    what it carries — so the `stock` here is a placeholder and only the good
    and its item mean anything.

    Parameters
    ----------
    library : Library
        The loaded content.

    Returns
    -------
    dict
        Qualified good id to the good, in a fixed order.
    """
    found: dict[str, Dealt] = {}
    for pack in library.packs:
        for local_id in sorted(pack.goods):
            good_id = f"{pack.id}:{local_id}"
            item_id, item = _item(library, good_id, pack.goods[local_id])
            found[good_id] = Dealt(
                good=pack.goods[local_id],
                item=item,
                item_id=item_id,
                stock=Stock(capacity=DEFAULT_DEPTH),
            )
    return found


def prepare(library: Library) -> Network:
    """Resolve every market, everything it deals in, and every road between.

    Parameters
    ----------
    library : Library
        The loaded content.

    Returns
    -------
    Network
        The markets and the roads joining them.
    """
    markets: dict[str, Prepared] = {}
    for pack in library.packs:
        for local_id in sorted(pack.markets):
            resolved = _resolve(library, pack.id, pack.markets[local_id])
            markets[resolved.id] = resolved

    links = _links(library, markets)
    return Network(markets=markets, links=links, groups=_groups(markets, links))


def at(network: Network, location: str) -> Prepared | None:
    """The market at a location, if there is one.

    Parameters
    ----------
    network : Network
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
    for market in network.markets.values():
        if market.location == location:
            return market
    return None


def _links(library: Library, markets: dict[str, Prepared]) -> tuple[Link, ...]:
    """Every route whose two ends both have a market.

    Parameters
    ----------
    library : Library
        The loaded content.
    markets : dict
        The resolved markets, keyed by qualified id.

    Returns
    -------
    tuple of Link
        In pack then route id order, so trade is applied identically every
        replay.
    """
    standing = {market.location: market.id for market in markets.values()}
    links: list[Link] = []
    for pack in library.packs:
        for local_id in sorted(pack.routes):
            route = pack.routes[local_id]
            origin = standing.get(
                library.resolve(route.origin, "locations", within=pack.id)
            )
            destination = standing.get(
                library.resolve(route.destination, "locations", within=pack.id)
            )
            if origin is None or destination is None or origin == destination:
                continue
            links.append(
                Link(
                    route=f"{pack.id}:{local_id}",
                    origin=origin,
                    destination=destination,
                    ticks=route.ticks,
                    capacity=route.trade_capacity,
                    danger=route.danger_level or 0,
                    both_ways=route.bidirectional,
                )
            )
    return tuple(links)


def _groups(markets: dict[str, Prepared], links: tuple[Link, ...]) -> tuple[Group, ...]:
    """Partition markets by what can reach what.

    Reachability is undirected even where a route is not: a one-way road
    still means the price at one end depends on the other, so both markets
    have to be carried forward together whichever way the goods go.

    Parameters
    ----------
    markets : dict
        The resolved markets.
    links : tuple of Link
        The roads between them.

    Returns
    -------
    tuple of Group
        Every market in exactly one group, in sorted order.
    """
    neighbours: dict[str, set[str]] = {market_id: set() for market_id in markets}
    for link in links:
        neighbours[link.origin].add(link.destination)
        neighbours[link.destination].add(link.origin)

    seen: set[str] = set()
    groups: list[Group] = []
    for market_id in sorted(markets):
        if market_id in seen:
            continue
        reached = {market_id}
        frontier = [market_id]
        while frontier:
            for onward in sorted(neighbours[frontier.pop()]):
                if onward not in reached:
                    reached.add(onward)
                    frontier.append(onward)
        seen |= reached
        groups.append(
            Group(
                markets=tuple(sorted(reached)),
                links=tuple(link for link in links if link.origin in reached),
            )
        )
    return tuple(groups)


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

    dealt: dict[str, Dealt] = {}
    for good_id in sorted({*produced, *consumed, *written, *traded}):
        item_id, item = _item(library, good_id, goods[good_id])
        dealt[good_id] = Dealt(
            good=goods[good_id],
            item=item,
            item_id=item_id,
            stock=written.get(good_id) or Stock(capacity=DEFAULT_DEPTH * market.depth),
            produced=produced.get(good_id, 0.0),
            consumed=consumed.get(good_id, 0.0),
        )
    return Prepared(
        market=market,
        home=home,
        location=location,
        region=_region(library, home, location),
        goods=dealt,
    )


def _region(library: Library, home: str, location: str) -> str | None:
    """Which region a market's location belongs to.

    Parameters
    ----------
    library : Library
        The loaded content.
    home : str
        The pack the market was written in.
    location : str
        Qualified location id.

    Returns
    -------
    str or None
        Qualified region id, or None where the location names none. A game's
        `startRegion` fallback is deliberately *not* applied: a shock on the
        lowlands should hit the places an author put in the lowlands, not
        every place they never got round to assigning.
    """
    pack_id, local_id = location.split(":", 1)
    found = library.pack(pack_id).locations.get(local_id)
    if found is None or found.region is None:  # pragma: no cover — validated
        return None
    try:
        return library.resolve(found.region, "regions", within=home)
    except ContentError:  # pragma: no cover — validation catches these
        return None


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


def _item(library: Library, good_id: str, good: Good) -> tuple[str, Entity]:
    """The item a good is the market behaviour of, and its qualified id.

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
    tuple of (str, Entity)
        The item's qualified id — which is what an inventory is keyed by —
        and the item.
    """
    home = good_id.split(":", 1)[0]
    item_id = library.resolve(good.item, "entities", within=home)
    found = library.find(good.item, "entities", within=home)
    assert isinstance(found, Entity)
    return item_id, found
