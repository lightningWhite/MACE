"""How shelves move while nobody is looking, and how goods cross a road.

Stock moves four ways each tick, in this order: a thing is made, then it is
used, then what is left of it rots, then some of it is carted to wherever it is
worth more. The order is part of the contract — rotting first would spoil grain
that was eaten that same tick, and hauling first would ship a sack that had not
been grown.

**Trade flow is the reason routes exist.** Two markets joined by a road pull on
each other's prices:

    haulage = TRADE_RATE × tradeCapacity / (ticks × (1 + DANGER_WEIGHT × danger))
    moved   = min(haulage × (dear price − cheap price) / baseValue,
                  what would level the two prices)

A long road means prices stay different at the two ends, and a profit for
whoever makes the trip. A dangerous road throttles flow, so bandit country is
expensive country. A **shut** road moves nothing, and prices on the two sides
diverge within days — which is the whole payoff of building weather and events
first, and it falls out of the formula rather than out of a special case.

That second line is `levelling`, and it is not decoration: nobody carts so
much that they arrive to find the price below the one they left, and a model
that does ships a luxury back and forth every tick forever.

Because markets pull on each other, a market cannot be carried forward alone.
The unit is the `Group`: everything a road can reach from everything else moves
together, in lockstep, one tick at a time. That is also why the catch-up is a
loop rather than a closed form — spoilage is proportional to the shelf and flow
depends on what the *neighbours* held that tick, so neither has one.

**A market is not stepped every tick.** It carries the tick its shelves have
been brought to and is carried forward when something looks at it, so a hundred
markets cost nothing until they matter, and a market first opened on day fifty
opens at the playthrough's start tick and catches up. That is only allowed to
be an optimization, so catching up runs exactly the loop stepping runs, and
`tests/test_economy_markets.py` checks it directly rather than trusting it.

Two rules keep that true, and both are easy to break later:

- **Reading a price must not move a shelf.** A question that changes its answer
  breaks replay, so the work is split: `projected` is pure and is what a price
  and the debug overlay read, and `sync` commits the identical answer from the
  places where the engine already accepts that time moves.
- **A lazy span must have one weather of its own.** A catch-up applies today's
  route states to every tick it crosses, so anything that changes a route has
  to `sync` the groups it touches *first* — otherwise a pass that shut on day
  fifty would retroactively have been shut since day one. `mace.engine.effects`
  does that where it closes, opens, or relays a road.

See docs/08-economy.md and ADR-0007.
"""

from __future__ import annotations

from collections.abc import Mapping

from mace.engine.economy.markets import Dealt, Group, Link, Network, Prepared
from mace.engine.economy.pricing import price_of, wealth_factor
from mace.engine.state import GameState, MarketState, RouteState

__all__ = [
    "DANGER_WEIGHT",
    "MAX_SHARE",
    "TRADE_RATE",
    "haulage",
    "hauled",
    "levelling",
    "opening",
    "projected",
    "sync",
]

#: Units a road one tick long and perfectly safe carries per tick, for a price
#: gap of one whole `baseValue`. Everything else divides it down: six ticks of
#: forest track at `dangerLevel: 5` carries a twelfth of this. The number is
#: set so that neighbours a couple of ticks apart share a price within a day
#: and a hard day's road keeps a gap worth carrying grain across.
TRADE_RATE = 24.0

#: What `dangerLevel` does to haulage. Ten — the worst road an author can
#: write — carries a third of what the same road would carry if it were safe.
#: Deliberately a smaller lever than distance: danger should make a road dear,
#: not make it a wall. Only a closure is a wall.
DANGER_WEIGHT = 0.2

#: The most of a shelf one road may take in one tick. A backstop behind
#: `levelling`, which is what actually keeps trade from overshooting: this
#: only catches the case where a market is down to a handful of units and the
#: arithmetic that says "level the prices" would take most of them at once.
MAX_SHARE = 0.1


def haulage(link: Link, road: RouteState | None) -> float:
    """How much a road moves per tick, per whole `baseValue` of price gap.

    Parameters
    ----------
    link : Link
        The road, as the author wrote it.
    road : RouteState or None
        What the playthrough has done to it. None is an untouched road.

    Returns
    -------
    float
        Units per tick per unit of gap. Zero for a road that is shut, which is
        what makes a closed pass diverge the prices on its two sides.
    """
    if road is not None and road.closed:
        return 0.0
    ticks = link.ticks if road is None or road.ticks is None else road.ticks
    return (
        TRADE_RATE * link.capacity / (max(ticks, 1) * (1 + DANGER_WEIGHT * link.danger))
    )


def levelling(
    source: Dealt, sink: Dealt, held: float, into: float, tilt: float
) -> float:
    """How much would carry until the two ends agree on the price.

    Nobody carts so much that they arrive to find the price below the one they
    left. Without this the model does exactly that: a luxury — anything with
    an `elasticity` above 1, whose price moves sharply with the shelf — is
    overshot every tick and shipped straight back the next, and the shelves
    ring instead of settling.

    Solving `price` for the amount that levels them is one line, because the
    `baseValue` and the exponent are the same at both ends and cancel:

        m = (tilt × wanted_sink × held − wanted_source × into)
            ÷ (wanted_source + tilt × wanted_sink)

    Parameters
    ----------
    source, sink : Dealt
        The good at the cheap end and at the dear end.
    held : float
        Units at the cheap end.
    into : float
        Units at the dear end.
    tilt : float
        How much richer the dear end is, in shelf terms — the ratio of the two
        wealth factors, taken to the reciprocal of the elasticity. Above 1
        because a place that pays more settles at a fuller shelf, which is
        exactly why carrying things to a rich town is a living.

    Returns
    -------
    float
        Units. Negative when the cheap end is the one that should be short,
        which the caller floors away.
    """
    return (tilt * sink.stock.wanted * held - source.stock.wanted * into) / (
        source.stock.wanted + tilt * sink.stock.wanted
    )


def hauled(
    rate: float, gap: float, level: float, held: float, headroom: float
) -> float:
    """How much of one good crosses one road in one tick.

    Parameters
    ----------
    rate : float
        What `haulage` said this road carries.
    gap : float
        The price difference, as a fraction of the good's `baseValue`, and
        positive — the caller has already worked out which end is dear.
    level : float
        What `levelling` said would close the gap entirely.
    held : float
        Units on the cheap end's shelf. Nobody ships what they do not have.
    headroom : float
        How much more the dear end can hold. A market is a town, not a
        warehouse.

    Returns
    -------
    float
        Units, never negative.
    """
    return max(min(rate * gap, level, held * MAX_SHARE, headroom), 0.0)


def opening(prepared: Prepared, start_tick: int) -> MarketState:
    """A market as it stood when the playthrough began.

    A market opened late is opened *here* and carried forward, rather than at
    whatever tick the player first looked — a world that began when you looked
    at it is not a world.

    Parameters
    ----------
    prepared : Prepared
        The market, resolved.
    start_tick : int
        The tick the playthrough opened on.

    Returns
    -------
    MarketState
        Shelves at their `initial` levels. Not stored anywhere; the caller
        decides whether it is a projection or a commitment.
    """
    return MarketState(
        market=prepared.id,
        stock={
            good_id: dealt.stock.opening for good_id, dealt in prepared.goods.items()
        },
        stepped_to=start_tick,
    )


def projected(
    state: GameState, network: Network, market_id: str, to_tick: int
) -> dict[str, float]:
    """What a market's shelves would hold at a tick, without moving them.

    Pure: `state` is read and never written, which is what lets the debug
    overlay show prices without the playthrough that has it open diverging
    from the one that does not. `sync` runs the identical loop and keeps the
    answer.

    Parameters
    ----------
    state : GameState
        The playthrough. Read only.
    network : Network
        Every market and the roads between them.
    market_id : str
        Qualified id of the market being asked about.
    to_tick : int
        The tick to carry it to. A tick already passed carries nothing.

    Returns
    -------
    dict
        Qualified good id to units held.
    """
    return _carry(state, network, network.group(market_id), to_tick)[market_id]


def sync(
    state: GameState,
    network: Network,
    market_id: str,
    to_tick: int | None = None,
) -> MarketState:
    """Bring a market — and everything it trades with — up to now.

    Called where time moves, where the player arrives somewhere, and before
    anything changes a road; never from a condition or a description. See the
    module docstring.

    The whole group is committed, not just the market asked about: they moved
    each other's shelves to get here, so carrying one forward without the
    others would be a different world.

    Parameters
    ----------
    state : GameState
        The playthrough. Markets are created or advanced in place.
    network : Network
        Every market and the roads between them.
    market_id : str
        Qualified id of the market being asked about.
    to_tick : int or None
        The tick to carry the group to. Defaults to now.

    Returns
    -------
    MarketState
        The asked-about market's shelves, current.
    """
    group = network.group(market_id)
    target = state.tick if to_tick is None else to_tick

    for member in group.markets:
        if member not in state.markets:
            state.markets[member] = opening(network.markets[member], state.start_tick)

    if target <= _from_tick(state, group):
        return state.markets[market_id]

    carried = _carry(state, network, group, target)
    for member in group.markets:
        held = state.markets[member]
        held.stock = carried[member]
        held.stepped_to = target
    return state.markets[market_id]


def _from_tick(state: GameState, group: Group) -> int:
    """Where a group's shelves have got to.

    A group is only ever advanced as a whole, so its markets agree; the
    earliest is taken anyway, because a group that somehow disagreed should
    catch up rather than skip the ticks it is behind by.

    Parameters
    ----------
    state : GameState
        The playthrough.
    group : Group
        The markets in question.

    Returns
    -------
    int
        The tick to carry forward from.
    """
    return min(
        (
            state.markets[member].stepped_to
            for member in group.markets
            if member in state.markets
        ),
        default=state.start_tick,
    )


def _carry(
    state: GameState, network: Network, group: Group, to_tick: int
) -> dict[str, dict[str, float]]:
    """Step a whole group forward, on a copy of its shelves.

    Parameters
    ----------
    state : GameState
        The playthrough. Read only — the copy is what moves.
    network : Network
        Every market and the roads between them.
    group : Group
        The markets to carry, and the roads between them.
    to_tick : int
        The tick to carry them to.

    Returns
    -------
    dict
        Qualified market id to what it holds, by good.
    """
    shelves = {
        member: dict(
            (
                state.markets.get(member)
                or opening(network.markets[member], state.start_tick)
            ).stock
        )
        for member in group.markets
    }
    for _ in range(max(0, to_tick - _from_tick(state, group))):
        _step(shelves, network.markets, group, state.routes)
    return shelves


def _step(
    shelves: dict[str, dict[str, float]],
    markets: Mapping[str, Prepared],
    group: Group,
    roads: Mapping[str, RouteState],
) -> None:
    """Move a group's shelves by one tick, in place.

    Every market makes and uses its own goods first, and only then do the
    carts move — so a road hauls what a place actually had that day, and the
    answer does not depend on which market happened to be stepped first.

    Parameters
    ----------
    shelves : dict
        Market id to good id to units held, updated in place.
    markets : mapping
        The resolved markets.
    group : Group
        The markets and roads being stepped.
    roads : mapping
        The playthrough's route states, for what is shut and what is long.
    """
    for member in group.markets:
        _make_and_use(shelves[member], markets[member])
    for link in group.links:
        _haul(shelves, markets, link, roads.get(link.route))


def _make_and_use(stock: dict[str, float], prepared: Prepared) -> None:
    """Production, consumption and spoilage for one market, for one tick.

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


def _haul(
    shelves: dict[str, dict[str, float]],
    markets: Mapping[str, Prepared],
    link: Link,
    road: RouteState | None,
) -> None:
    """Move goods along one road, for one tick, in place.

    Only goods both ends deal in cross: a market with no shelf for salt has
    nowhere to put it and no price to pull it. Goods move toward the dearer
    end, which is why a rich town ends up better stocked than the hamlet that
    grew the grain — wealth is a reason to carry something somewhere.

    Parameters
    ----------
    shelves : dict
        Market id to good id to units held, updated in place.
    markets : mapping
        The resolved markets.
    link : Link
        The road.
    road : RouteState or None
        What the playthrough has done to it.
    """
    rate = haulage(link, road)
    if rate <= 0.0:
        return

    origin, destination = markets[link.origin], markets[link.destination]
    for good_id, here in origin.goods.items():
        there = destination.goods.get(good_id)
        if there is None or here.base_value <= 0.0:
            continue

        gap = (
            price_of(
                there, shelves[link.destination][good_id], destination.market.wealth
            )
            - price_of(here, shelves[link.origin][good_id], origin.market.wealth)
        ) / here.base_value

        if gap > 0.0:
            cheap, dear = link.origin, link.destination
            source, sink = here, there
        elif gap < 0.0 and link.both_ways:
            cheap, dear = link.destination, link.origin
            source, sink, gap = there, here, -gap
        else:
            continue

        held, into = shelves[cheap][good_id], shelves[dear][good_id]
        tilt = (
            wealth_factor(markets[dear].market.wealth)
            / wealth_factor(markets[cheap].market.wealth)
        ) ** (1.0 / source.good.elasticity)

        moved = hauled(
            rate,
            gap,
            levelling(source, sink, held, into, tilt),
            held,
            sink.stock.capacity - into,
        )
        shelves[cheap][good_id] -= moved
        shelves[dear][good_id] += moved
