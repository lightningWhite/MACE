"""Buying and selling: the one place a player touches a market.

Everything else in `economy` is the world moving on its own — shelves filling,
carts crossing roads, prices settling. This is the counter. A merchant stands
in front of a settlement's shelves and will deal with you at those prices plus
a `spread`, and that spread is its living and the reason carrying grain north
can beat selling it here.

**Every unit is priced separately, as the shelf moves under it.** Buying the
tenth sack costs more than the first, because there are nine fewer sacks by
then; selling the tenth pays less. That is not a penalty bolted on to stop an
exploit — it is the same `price_of` the whole model uses, asked once per unit
instead of once per lot. Asking once per lot would let a player empty a hamlet
at the empty-shelf price it had before they arrived, which is a money printer
and, worse, a market that lies about what it is short of.

Coin is whole. A price is rounded *against* the player at each end — up when
they buy, down when they sell — so the spread cannot be arbitraged away by
trading one unit at a time, and so nobody ever has to render a third of a
penny.

A merchant with `capital` has a **purse**, and the purse is simply the coin in
its own `inventory` — not a second money system beside the one the player
carries. So a scene that hands the peddler ten gold has made him ten gold
richer, and a player who arrives with forty sacks of grain can find out that
the buyer has run out of money. A merchant without `capital` is a stall backed
by a whole town, and its pockets cannot be emptied.

Haggling is the one thing still missing: `spread` is the whole of the
negotiation. See docs/08-economy.md § Merchants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mace.content import ContentError
from mace.engine.context import RuleContext
from mace.engine.economy.flow import projected, shock_on, sync
from mace.engine.economy.markets import Dealt, Network, Prepared, at, prepare
from mace.engine.economy.pricing import price_of
from mace.engine.state import EntityState
from mace.model import Entity, Merchant
from mace.model.economy import Deals

__all__ = [
    "MAX_LOT",
    "Priced",
    "Sale",
    "Stall",
    "deal",
    "look",
    "merchant_at",
    "purse_at",
    "quote",
    "restock",
    "unit_price",
]

#: The most units one trade may move. A bound rather than a rule: it keeps a
#: mistyped quantity from spending a second in a pricing loop, and no honest
#: trade comes near it.
MAX_LOT = 999


@dataclass(frozen=True, slots=True)
class Priced:
    """One good on offer, and what it costs a unit right now.

    Attributes
    ----------
    good : str
        Qualified good id — what a `trade` action names.
    item : str
        Qualified id of the item the player would carry.
    name : str
        What to call it.
    buy : int or None
        What one costs the player, or None when the merchant will not sell it
        or the shelf is empty.
    sell : int or None
        What the merchant pays for one, or None when it will not buy it.
    available : int
        Whole units the shelf holds.
    carried : int
        Whole units the player is carrying.
    """

    good: str
    item: str
    name: str
    buy: int | None
    sell: int | None
    available: int
    carried: int

    def record(self) -> dict[str, object]:
        """The row, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "good": self.good,
            "item": self.item,
            "name": self.name,
            "buy": self.buy,
            "sell": self.sell,
            "available": self.available,
            "carried": self.carried,
        }


@dataclass(frozen=True, slots=True)
class Stall:
    """What one merchant is offering, right now.

    Attributes
    ----------
    merchant : str
        The merchant's instance id — what a `trade` action is addressed to.
    name : str
        What to call them.
    market : str
        Qualified id of the market they deal for.
    currency : str
        Qualified item id trade is settled in.
    coin : int
        What the player has of it.
    purse : int or None
        What the merchant can pay out. None is bottomless — a stall backed by
        a whole town is not somebody whose pockets can be emptied.
    goods : tuple of Priced
        Everything on offer, in good-id order.
    """

    merchant: str
    name: str
    market: str
    currency: str
    coin: int
    purse: int | None
    goods: tuple[Priced, ...]

    def row(self, good_id: str) -> Priced | None:
        """One good's row, by qualified id.

        Parameters
        ----------
        good_id : str
            The qualified good id.

        Returns
        -------
        Priced or None
            The row, or None when this merchant does not deal in it.
        """
        for priced in self.goods:
            if priced.good == good_id:
                return priced
        return None

    def record(self) -> dict[str, object]:
        """The stall, JSON-safe.

        Returns
        -------
        dict
            camelCase fields.
        """
        return {
            "merchant": self.merchant,
            "name": self.name,
            "market": self.market,
            "currency": self.currency,
            "coin": self.coin,
            "purse": self.purse,
            "goods": [priced.record() for priced in self.goods],
        }


@dataclass(frozen=True, slots=True)
class Sale:
    """What one completed trade moved.

    Attributes
    ----------
    good : str
        Qualified good id.
    item : str
        Qualified item id.
    qty : int
        Units, always positive.
    sell : bool
        Whether the player was the one handing goods over.
    coin : int
        Whole currency that changed hands, always positive.
    """

    good: str
    item: str
    qty: int
    sell: bool
    coin: int


def merchant_at(context: RuleContext, entity: EntityState) -> Merchant | None:
    """The merchant block on an entity instance, if it has one.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The instance.

    Returns
    -------
    Merchant or None
        Its merchant block.
    """
    try:
        definition: Entity = context.definition(entity)
    except (KeyError, ContentError):  # pragma: no cover — content changed
        return None
    return definition.merchant


def look(context: RuleContext, entity: EntityState) -> Stall | None:
    """What a merchant is offering, without moving anything.

    Pure, in the sense `flow.projected` is pure: the shelves are carried
    forward on a copy, so a front-end may draw a price list every frame and a
    playthrough with the shop panel open replays identically to one without.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The merchant's instance.

    Returns
    -------
    Stall or None
        The offer, or None when this is not a merchant, its market is not
        there, or the game has named no currency.
    """
    found = _resolve(context, entity)
    if found is None:
        return None
    merchant, network, prepared = found
    currency = _currency(context)
    if currency is None:
        return None

    held = projected(context.state, network, prepared.id, context.state.tick)
    return _stall(context, entity, merchant, prepared, currency, held)


def quote(
    context: RuleContext, entity: EntityState, good: str, qty: int, *, sell: bool
) -> int | None:
    """What a lot would come to, without moving anything.

    Pure, so a menu may be priced every turn. The answer is the same one
    `deal` charges, because both go through `_lot`.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The merchant's instance.
    good : str
        Qualified good id.
    qty : int
        How many units.
    sell : bool
        Whether the player would be handing them over.

    Returns
    -------
    int or None
        Whole coin, or None when this merchant cannot price that.
    """
    found = _resolve(context, entity)
    if found is None:  # pragma: no cover — the caller has a stall already
        return None
    merchant, network, prepared = found
    dealt = prepared.goods.get(good)
    if dealt is None:  # pragma: no cover — the stall listed it
        return None
    held = projected(context.state, network, prepared.id, context.state.tick)
    return _lot(
        dealt,
        prepared,
        merchant,
        held.get(good, 0.0),
        qty,
        sell=sell,
        shock=shock_on(context.state, prepared, good, context.state.tick),
    )


def deal(
    context: RuleContext,
    entity: EntityState,
    good: str,
    qty: int,
    *,
    sell: bool,
) -> Sale:
    """Buy from a merchant, or sell to one. Moves both the shelf and the pack.

    Parameters
    ----------
    context : RuleContext
        The playthrough. The market's group is brought up to now and the
        traded units are committed to its shelf.
    entity : EntityState
        The merchant's instance.
    good : str
        A good reference, bare or qualified.
    qty : int
        Units. Positive.
    sell : bool
        Whether the player is handing the goods over.

    Returns
    -------
    Sale
        What moved.

    Raises
    ------
    RuleError
        If the trade cannot happen, phrased for the player.
    """
    from mace.engine.conditions import RuleError

    if qty < 1:
        raise RuleError("trade at least one of something")
    if qty > MAX_LOT:
        raise RuleError(f"nobody deals in more than {MAX_LOT} at a time")

    found = _resolve(context, entity)
    if found is None:
        raise RuleError("there is nobody here to trade with")
    merchant, network, prepared = found

    currency = _currency(context)
    if currency is None:
        raise RuleError("this game has no currency to trade in")

    good_id = _good_id(context, good)
    dealt = prepared.goods.get(good_id)
    wanted = merchant.buys if sell else merchant.sells
    if dealt is None or not _deals_in(wanted, _named(context, wanted), dealt, good_id):
        raise RuleError("that is not something they deal in")

    # Bring the whole trading group up to now *before* touching a shelf: the
    # price the player is quoted has to be the price of the market they are
    # standing in, not of the one it was when somebody last looked.
    state = sync(context.state, network, prepared.id)
    held = state.stock.get(good_id, 0.0)
    player = context.state.protagonist
    item = dealt.item_id
    carried = player.inventory.get(item, 0)

    if sell:
        if carried < qty:
            raise RuleError(f"you do not have {qty} {dealt.item.name} to sell")
        headroom = dealt.stock.capacity - held
        if headroom < qty:
            raise RuleError(f"they have nowhere to put that much {dealt.item.name}")
    elif int(held) < qty:
        raise RuleError(f"they do not have {qty} {dealt.item.name} to sell you")

    coin = _lot(
        dealt,
        prepared,
        merchant,
        held,
        qty,
        sell=sell,
        shock=shock_on(context.state, prepared, good_id, context.state.tick),
    )
    if sell and coin <= 0:
        raise RuleError(f"nobody here will give you anything for {dealt.item.name}")
    if not sell and player.inventory.get(currency, 0) < coin:
        raise RuleError(f"you cannot afford that — it is {coin}")

    purse = restock(context, entity, merchant, currency)
    if sell and purse is not None and purse < coin:
        raise RuleError(f"they have {purse} to their name, and that is worth {coin}")

    _move(player.inventory, item, qty if not sell else -qty)
    _move(player.inventory, currency, -coin if not sell else coin)
    if purse is not None:
        # Only a merchant with a purse holds the coin. A stall backed by a
        # whole town is not somebody whose pockets can be emptied.
        _move(entity.inventory, currency, coin if not sell else -coin)
    state.stock[good_id] = held + (qty if sell else -qty)

    return Sale(good=good_id, item=item, qty=qty, sell=sell, coin=coin)


def purse_at(
    context: RuleContext, entity: EntityState, merchant: Merchant, currency: str
) -> int | None:
    """What a merchant could pay out now, without moving anything.

    Pure, the way `flow.projected` is: a shop panel drawn every frame must not
    be the reason a purse refilled. `restock` runs the identical arithmetic
    and keeps the answer.

    Parameters
    ----------
    context : RuleContext
        The playthrough. Read only.
    entity : EntityState
        The merchant's instance.
    merchant : Merchant
        Its block.
    currency : str
        Qualified item id trade is settled in.

    Returns
    -------
    int or None
        Coin, or None for a merchant with no purse at all — a stall backed by
        a whole town is not somebody whose pockets can be emptied.
    """
    if merchant.capital is None:
        return None
    purse = entity.inventory.get(currency, 0)
    if _due(context, entity, merchant) < 1:
        return purse
    return max(purse, int(merchant.capital))


def restock(
    context: RuleContext,
    entity: EntityState,
    merchant: Merchant,
    currency: str,
) -> int | None:
    """Bring a merchant's purse up to date, and say what is in it.

    Lazy, the way a market's shelves are: a merchant nobody has spoken to for
    a season is topped up when somebody looks, not on every tick, and there is
    no roll in it — only arithmetic on the tick — so a playthrough that
    visited every day and one that arrived late find the same purse.

    Restocking never takes money *away*. A merchant who sold a lot keeps the
    takings; `capital` is a floor it comes back up to, not a level it is
    clamped at.

    Parameters
    ----------
    context : RuleContext
        The playthrough. The purse and the restock tick are updated in place.
    entity : EntityState
        The merchant's instance.
    merchant : Merchant
        Its block.
    currency : str
        Qualified item id trade is settled in.

    Returns
    -------
    int or None
        What the merchant can pay out, or None when it has no purse at all.
    """
    if merchant.capital is None:
        return None

    state = context.state
    purse = entity.inventory.get(currency, 0)
    due = _due(context, entity, merchant)
    if due < 1:
        state.restocked.setdefault(entity.instance_id, state.start_tick)
        return purse

    assert merchant.restock_ticks is not None
    state.restocked[entity.instance_id] = (
        state.restocked.get(entity.instance_id, state.start_tick)
        + due * merchant.restock_ticks
    )
    filled = max(purse, int(merchant.capital))
    _write(entity, currency, filled)
    return filled


def _write(entity: EntityState, currency: str, coin: int) -> None:
    """Put a purse back into the merchant's pack.

    Parameters
    ----------
    entity : EntityState
        The merchant's instance.
    currency : str
        Qualified item id trade is settled in.
    coin : int
        How much.
    """
    if coin > 0:
        entity.inventory[currency] = coin
    else:
        entity.inventory.pop(currency, None)


def _due(context: RuleContext, entity: EntityState, merchant: Merchant) -> int:
    """How many restocks a merchant has coming.

    Parameters
    ----------
    context : RuleContext
        The playthrough. Read only.
    entity : EntityState
        The merchant's instance.
    merchant : Merchant
        Its block.

    Returns
    -------
    int
        The count, or 0 for a merchant whose purse never refills.
    """
    if merchant.restock_ticks is None:
        return 0
    state = context.state
    since = state.restocked.get(entity.instance_id, state.start_tick)
    return (state.tick - since) // merchant.restock_ticks


# ── Working out a price ───────────────────────────────────────────────────────


def unit_price(
    dealt: Dealt,
    wealth: float,
    spread: float,
    held: float,
    *,
    sell: bool,
    shock: float = 1.0,
) -> int:
    """What one unit costs, or fetches, at a given shelf level.

    Parameters
    ----------
    dealt : Dealt
        The good, resolved against the market.
    wealth : float
        The market's `wealth`.
    spread : float
        The merchant's cut.
    held : float
        Units on the shelf at the moment this unit changes hands.
    sell : bool
        Whether the player is the one handing it over.
    shock : float
        What the world is doing to this price — a siege, an eruption.

    Returns
    -------
    int
        Whole coin, rounded against the player: down when they sell, up when
        they buy. Never negative, and never zero when they are buying — a
        market with more than it can use still asks for a coin.
    """
    price = price_of(dealt, held, wealth, shock)
    if sell:
        return max(0, math.floor(price * (1.0 - spread / 2.0)))
    return max(1, math.ceil(price * (1.0 + spread / 2.0)))


def _lot(
    dealt: Dealt,
    prepared: Prepared,
    merchant: Merchant,
    held: float,
    qty: int,
    *,
    sell: bool,
    shock: float = 1.0,
) -> int:
    """What a whole lot comes to, priced a unit at a time as the shelf moves.

    Parameters
    ----------
    dealt : Dealt
        The good.
    prepared : Prepared
        The market.
    merchant : Merchant
        Whose spread applies.
    held : float
        Units on the shelf before the trade.
    qty : int
        How many units.
    sell : bool
        Whether the player is handing them over.
    shock : float
        What the world is doing to this price.

    Returns
    -------
    int
        Whole coin for the lot.
    """
    wealth = prepared.market.wealth
    step = 1.0 if sell else -1.0
    return sum(
        unit_price(
            dealt, wealth, merchant.spread, held + step * unit, sell=sell, shock=shock
        )
        for unit in range(qty)
    )


# ── Resolving who and what ────────────────────────────────────────────────────


def _resolve(
    context: RuleContext, entity: EntityState
) -> tuple[Merchant, Network, Prepared] | None:
    """Find a merchant's market, and the network it trades in.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The instance.

    Returns
    -------
    tuple or None
        The merchant block, the network, and its market — or None when it is
        not a merchant or its market is not there.
    """
    merchant = merchant_at(context, entity)
    if merchant is None:
        return None

    network = prepare(context.library)
    if merchant.market is not None:
        try:
            market_id = context.qualify(merchant.market, "markets")
        except ContentError:  # pragma: no cover — validation catches these
            return None
        prepared = network.markets.get(market_id)
    else:
        where = entity.location
        prepared = None if where is None else at(network, where)

    return None if prepared is None else (merchant, network, prepared)


def _stall(
    context: RuleContext,
    entity: EntityState,
    merchant: Merchant,
    prepared: Prepared,
    currency: str,
    held: dict[str, float],
) -> Stall:
    """Build the price list from shelves the caller has already worked out.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    entity : EntityState
        The merchant's instance.
    merchant : Merchant
        Its block.
    prepared : Prepared
        Its market.
    currency : str
        Qualified item id trade is settled in.
    held : dict
        Qualified good id to units on the shelf.

    Returns
    -------
    Stall
        The offer.
    """
    player = context.state.protagonist
    wealth = prepared.market.wealth
    will_buy, will_sell = _named(context, merchant.buys), _named(
        context, merchant.sells
    )
    rows: list[Priced] = []

    for good_id, dealt in prepared.goods.items():
        item = dealt.item_id
        if item == currency:
            # A market that dealt in coin would price money in money.
            continue
        on_shelf = held.get(good_id, 0.0)
        shock = shock_on(context.state, prepared, good_id, context.state.tick)
        carried = player.inventory.get(item, 0)
        sells = _deals_in(merchant.sells, will_sell, dealt, good_id)
        buys = _deals_in(merchant.buys, will_buy, dealt, good_id)
        rows.append(
            Priced(
                good=good_id,
                item=item,
                name=dealt.item.name,
                buy=(
                    unit_price(
                        dealt,
                        wealth,
                        merchant.spread,
                        on_shelf,
                        sell=False,
                        shock=shock,
                    )
                    if sells and int(on_shelf) >= 1
                    else None
                ),
                sell=(
                    unit_price(
                        dealt,
                        wealth,
                        merchant.spread,
                        on_shelf,
                        sell=True,
                        shock=shock,
                    )
                    if buys
                    else None
                ),
                available=int(on_shelf),
                carried=carried,
            )
        )

    return Stall(
        merchant=entity.instance_id,
        name=context.definition(entity).name,
        market=prepared.id,
        currency=currency,
        coin=player.inventory.get(currency, 0),
        purse=purse_at(context, entity, merchant, currency),
        goods=tuple(rows),
    )


def _named(context: RuleContext, deals: Deals) -> frozenset[str]:
    """Qualify the goods a filter names, once, so matching is an id comparison.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    deals : Deals
        The filter.

    Returns
    -------
    frozenset of str
        Qualified good ids. A reference that names nothing is dropped —
        validation reports it, and a merchant is not the place to raise.
    """
    found: set[str] = set()
    for reference in deals.goods:
        try:
            found.add(context.qualify(reference, "goods"))
        except ContentError:  # pragma: no cover — validation catches these
            continue
    return frozenset(found)


def _deals_in(deals: Deals, named: frozenset[str], dealt: Dealt, good_id: str) -> bool:
    """Whether one side of a merchant's trade covers a good.

    Parameters
    ----------
    deals : Deals
        The filter — `buys` when the player is handing goods over, `sells`
        when they are taking them.
    named : frozenset of str
        The qualified ids that filter's `goods` list resolves to.
    dealt : Dealt
        The good, resolved.
    good_id : str
        Its qualified id.

    Returns
    -------
    bool
        Whether it is on offer in that direction.
    """
    if deals.everything:
        return True
    if dealt.good.category is not None and dealt.good.category in deals.categories:
        return True
    return good_id in named


def _good_id(context: RuleContext, reference: str) -> str:
    """Qualify a good reference.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    reference : str
        As it was written.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    from mace.engine.conditions import RuleError

    try:
        return context.qualify(reference, "goods")
    except ContentError as error:
        raise RuleError(error.message) from error


def _currency(context: RuleContext) -> str | None:
    """The item this game settles trade in.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    str or None
        Qualified item id, or None when the game names none.
    """
    named = context.game.rules.currency
    return None if named is None else context.item_id(named)


def _move(inventory: dict[str, int], item: str, delta: int) -> int:
    """Add to or take from a pack, dropping an entry that runs out.

    Parameters
    ----------
    inventory : dict
        Qualified item id to quantity, updated in place.
    item : str
        Which item.
    delta : int
        How many, signed.

    Returns
    -------
    int
        What is left.
    """
    left = inventory.get(item, 0) + delta
    if left > 0:
        inventory[item] = left
    else:
        inventory.pop(item, None)
    return max(left, 0)
