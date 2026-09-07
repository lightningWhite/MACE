"""Buying and selling: the counter in front of the shelves.

The market model already moves stock and forms prices; what these check is the
part a player touches. Three of them are load-bearing rather than
illustrative.

`test_a_lot_is_priced_as_the_shelf_moves_under_it` is the rule that keeps a
stall from being a money printer: the tenth sack costs more than the first
because there are nine fewer sacks by then. Pricing a lot once, at the shelf
level it had before the player arrived, would let a hamlet be emptied at the
price of a full hamlet.

`test_looking_at_a_stall_moves_nothing` is the projection rule the weather and
the debug overlay both follow. A shop panel a client draws every frame must
not be the reason a shelf moved.

`test_the_gap_a_shut_road_opens_is_what_a_merchant_charges_for` is the payoff
the whole subsystem exists for, asked at the counter rather than at the shelf:
close the road and the price the player is quoted diverges, without a line of
special-case code between the closure and the quote.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import Library, load_library
from mace.engine.actions import Choose, Trade
from mace.engine.conditions import RuleError, holds
from mace.engine.economy import trade
from mace.engine.state import RouteState
from mace.engine.step import begin, context_for, step
from mace.model import Condition

GRAIN = "valley:grain"
GOLD = "valley:gold"
HERO = "valley:hero"
KEEPER = "valley:keeper"

ITEMS: list[dict[str, Any]] = [
    {"id": "gold", "kind": "item", "name": "Gold", "item": {"baseValue": 1}},
    {
        "id": "grain",
        "kind": "item",
        "name": "Grain",
        "item": {"baseValue": 10, "stackable": True},
    },
]


def valley(root: Path, **merchant: Any) -> Library:
    """A farm and a garrison, a day apart, with a stallholder at each.

    Parameters
    ----------
    root : Path
        Where to write the pack.
    **merchant
        Extra fields for the farm keeper's `merchant` block.

    Returns
    -------
    Library
        The loaded library.
    """
    game_pack(
        root,
        pack_id="valley",
        game={
            "player": {"entity": "hero", "startLocation": "farm"},
            "winConditions": [{"atLocation": {"location": "fort"}}],
            "rules": {"economy": "market", "currency": "gold"},
        },
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {"hitpoints": {"base": 20, "max": 20}},
                    "inventory": [{"item": "gold", "qty": 500}],
                },
                {
                    "id": "keeper",
                    "kind": "actor",
                    "name": "The Keeper",
                    "merchant": {"spread": 0.2, **merchant},
                },
                {
                    "id": "sergeant",
                    "kind": "actor",
                    "name": "The Sergeant",
                    "merchant": {"spread": 0.2},
                },
                *ITEMS,
            ],
            "goods": [
                {
                    "id": "grain",
                    "item": "grain",
                    "category": "food",
                    "elasticity": 0.5,
                    "producedBy": ["farmland"],
                    "consumedBy": ["settlement"],
                }
            ],
            "markets": [
                {
                    "id": "farm-market",
                    "location": "farm",
                    "wealth": 0.5,
                    "tags": ["farmland"],
                    "stock": {"grain": {"initial": 400, "capacity": 800}},
                },
                {
                    "id": "fort-market",
                    "location": "fort",
                    "wealth": 0.5,
                    "tags": ["settlement"],
                    "stock": {"grain": {"initial": 50, "capacity": 800}},
                },
            ],
            "locations": [
                {
                    "id": "farm",
                    "name": "The Farm",
                    "entities": ["keeper"],
                    "exits": [{"to": "fort", "route": "road"}],
                },
                {"id": "fort", "name": "The Fort", "entities": ["sergeant"]},
            ],
            "routes": [{"id": "road", "from": "farm", "to": "fort", "ticks": 6}],
        },
    )
    return load_library(root)


def opened(library: Library) -> Any:
    """A playthrough standing at the farm with a stall open.

    Parameters
    ----------
    library : Library
        The loaded content.

    Returns
    -------
    StepResult
        The state, with `trading` set to the keeper.
    """
    result = begin(library, "valley", seed="trade")
    where = list(result.state.pending.options)  # type: ignore[union-attr]
    which = next(
        index for index, option in enumerate(where) if option.trade == KEEPER
    )
    return step(result.state, Choose(which), library)


def stall(library: Library, state: Any) -> trade.Stall:
    """The keeper's counter, right now.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.

    Returns
    -------
    Stall
        The offer.
    """
    context = context_for(library, state)
    found = trade.look(context, state.entities[KEEPER])
    assert found is not None
    return found


# ── The counter is offered where a merchant stands ────────────────────────────


def test_a_merchant_is_something_to_do_where_they_stand(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = begin(library, "valley", seed="trade")
    prompts = [option.prompt for option in result.state.pending.options]  # type: ignore[union-attr]
    assert "Trade with The Keeper" in prompts


def test_a_simple_economy_offers_no_stall_at_all(tmp_path: Path) -> None:
    """`economy: simple` prices from `baseValue` and sells through scenes."""
    library = valley(tmp_path)
    game = library.pack("valley").game
    assert game is not None
    object.__setattr__(game.rules, "economy", "simple")

    result = begin(library, "valley", seed="trade")
    prompts = [option.prompt for option in result.state.pending.options]  # type: ignore[union-attr]
    assert not any("Keeper" in prompt for prompt in prompts)


def test_opening_a_stall_takes_the_menu_over(tmp_path: Path) -> None:
    """A counter is not one option among the roads out of town."""
    library = valley(tmp_path)
    result = opened(library)
    prompts = [option.prompt for option in result.state.pending.options]  # type: ignore[union-attr]
    assert any(prompt.startswith("Buy Grain") for prompt in prompts)
    assert prompts[-1] == "Done with The Keeper"
    assert not any("Travel" in prompt for prompt in prompts)


def test_walking_away_closes_the_stall(tmp_path: Path) -> None:
    """A shop cannot follow the player down the road."""
    library = valley(tmp_path)
    result = opened(library)
    assert result.state.trading == KEEPER

    result = step(result.state, Trade(good="grain", qty=1), library)
    done = next(
        index
        for index, option in enumerate(result.state.pending.options)  # type: ignore[union-attr]
        if option.prompt == "Done with The Keeper"
    )
    result = step(result.state, Choose(done), library)
    assert result.state.trading is None


# ── What a lot costs ──────────────────────────────────────────────────────────


def test_a_lot_is_priced_as_the_shelf_moves_under_it(tmp_path: Path) -> None:
    """Ten sacks cost more than ten times one sack, because ten sacks are gone."""
    library = valley(tmp_path)
    result = opened(library)
    context = context_for(library, result.state)
    keeper = result.state.entities[KEEPER]

    one = trade.quote(context, keeper, GRAIN, 1, sell=False)
    ten = trade.quote(context, keeper, GRAIN, 10, sell=False)
    assert one is not None and ten is not None
    assert ten > one * 10 - 10  # not simply ten of the first price
    assert ten >= one * 10


def test_selling_into_a_market_pays_less_the_more_you_bring(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = opened(library)
    context = context_for(library, result.state)
    keeper = result.state.entities[KEEPER]

    one = trade.quote(context, keeper, GRAIN, 1, sell=True)
    ten = trade.quote(context, keeper, GRAIN, 10, sell=True)
    assert one is not None and ten is not None
    assert ten <= one * 10


def test_the_spread_is_the_merchants_living(tmp_path: Path) -> None:
    """You always sell for less than you would pay a moment later."""
    library = valley(tmp_path)
    counter = stall(library, opened(library).state)
    row = counter.row(GRAIN)
    assert row is not None and row.buy is not None and row.sell is not None
    assert row.sell < row.buy


def test_a_round_trip_at_one_counter_loses_money(tmp_path: Path) -> None:
    """Buying and selling back is the one trade that must never pay."""
    library = valley(tmp_path)
    result = opened(library)
    before = result.state.protagonist.inventory[GOLD]

    result = step(result.state, Trade(good="grain", qty=10), library)
    result = step(result.state, Trade(good="grain", qty=10, sell=True), library)

    assert result.state.protagonist.inventory[GOLD] < before
    assert GRAIN not in result.state.protagonist.inventory


# ── What a trade moves ────────────────────────────────────────────────────────


def test_buying_moves_the_shelf_the_coin_and_the_pack(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=1), library)
    shelf = dict(result.state.markets["valley:farm-market"].stock)
    coin = result.state.protagonist.inventory[GOLD]

    result = step(result.state, Trade(good="grain", qty=4), library)
    done = next(
        event for event in result.events if event.record()["kind"] == "trade.done"
    ).record()

    assert done["qty"] == 4 and done["sell"] is False
    assert result.state.protagonist.inventory[GRAIN] == 5
    assert result.state.protagonist.inventory[GOLD] == coin - done["coin"]
    assert result.state.markets["valley:farm-market"].stock[GRAIN] == shelf[GRAIN] - 4


def test_selling_is_the_same_trade_the_other_way(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=6), library)
    shelf = result.state.markets["valley:farm-market"].stock[GRAIN]

    result = step(result.state, Trade(good="grain", qty=6, sell=True), library)
    assert GRAIN not in result.state.protagonist.inventory
    assert result.state.markets["valley:farm-market"].stock[GRAIN] == shelf + 6


def test_you_cannot_buy_what_you_cannot_afford(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = opened(library)
    result.state.protagonist.inventory[GOLD] = 3

    result = step(result.state, Trade(good="grain", qty=1), library)
    assert [event.record()["kind"] for event in result.events] == ["engine.rule-failed"]
    assert GRAIN not in result.state.protagonist.inventory


def test_a_refused_trade_leaves_the_stall_where_it_was(tmp_path: Path) -> None:
    """Being told you cannot afford something does not close the shop."""
    library = valley(tmp_path)
    result = opened(library)
    result.state.protagonist.inventory[GOLD] = 3
    menu = result.state.pending

    result = step(result.state, Trade(good="grain", qty=1), library)
    assert result.state.pending is menu


def test_you_cannot_sell_what_you_are_not_carrying(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=1, sell=True), library)
    assert [event.record()["kind"] for event in result.events] == ["engine.rule-failed"]


def test_trading_with_nobody_is_refused(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = begin(library, "valley", seed="trade")
    result = step(result.state, Trade(good="grain", qty=1), library)
    assert "not trading" in result.events[0].record()["message"]


# ── What a merchant will and will not touch ───────────────────────────────────


def test_a_merchant_that_names_nothing_deals_in_the_whole_market(
    tmp_path: Path,
) -> None:
    library = valley(tmp_path)
    row = stall(library, opened(library).state).row(GRAIN)
    assert row is not None and row.buy is not None and row.sell is not None


def test_a_merchant_can_be_asked_to_specialise(tmp_path: Path) -> None:
    """`buys` and `sells` are separate: a smith takes metal and sells nothing."""
    library = valley(tmp_path, buys={"categories": ["metal"]}, sells={"goods": []})
    row = stall(library, opened(library).state).row(GRAIN)
    assert row is not None
    assert row.buy is not None  # `sells` names nothing, so it sells everything
    assert row.sell is None  # `buys` names metal, and grain is food


def test_a_category_covers_goods_written_after_the_merchant_was(
    tmp_path: Path,
) -> None:
    library = valley(tmp_path, buys={"categories": ["food"]})
    row = stall(library, opened(library).state).row(GRAIN)
    assert row is not None and row.sell is not None


# ── The projection rule ───────────────────────────────────────────────────────


def test_looking_at_a_stall_moves_nothing(tmp_path: Path) -> None:
    """A shop panel drawn every frame must not be why a shelf moved."""
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=1), library)
    before = dict(result.state.markets["valley:farm-market"].stock)

    for _ in range(5):
        stall(library, result.state)

    assert result.state.markets["valley:farm-market"].stock == before


def test_a_merchants_remark_is_a_condition_about_its_own_prices(
    tmp_path: Path,
) -> None:
    """`priceOf` is what makes a line about a shortage rather than about a flag."""
    library = valley(tmp_path)
    context = context_for(library, opened(library).state)

    # The farm opens holding exactly what it wants, so grain is at its
    # ordinary price there and neither a shortage nor a glut.
    ordinary = Condition.model_validate({"priceOf": {"good": "grain", "below": 1.1}})
    dear = Condition.model_validate({"priceOf": {"good": "grain", "above": 1.5}})
    assert holds(ordinary, context)
    assert not holds(dear, context)


def test_a_price_condition_can_name_a_market_the_player_is_not_at(
    tmp_path: Path,
) -> None:
    library = valley(tmp_path)
    context = context_for(library, opened(library).state)
    hungry = Condition.model_validate(
        {"priceOf": {"good": "grain", "market": "fort-market", "above": 1.5}}
    )
    assert holds(hungry, context)


def test_a_price_condition_needs_a_bound() -> None:
    with pytest.raises(ValueError, match="above"):
        Condition.model_validate({"priceOf": {"good": "grain"}})


# ── The payoff ────────────────────────────────────────────────────────────────


def test_the_gap_a_shut_road_opens_is_what_a_merchant_charges_for(
    tmp_path: Path,
) -> None:
    """Close the road and the two counters stop agreeing. No special case."""
    library = valley(tmp_path)

    def quoted(closed: bool, ticks: int) -> tuple[int, int]:
        result = begin(library, "valley", seed="trade")
        state = result.state
        if closed:
            state.routes["valley:road"] = RouteState(route="valley:road", closed=True)
        state.tick = state.world_tick = ticks
        context = context_for(library, state)
        here = trade.look(context, state.entities[KEEPER])
        there = trade.look(context, state.entities["valley:sergeant"])
        assert here is not None and there is not None
        farm, fort = here.row(GRAIN), there.row(GRAIN)
        assert farm is not None and fort is not None
        assert farm.buy is not None and fort.sell is not None
        return farm.buy, fort.sell

    open_buy, open_sell = quoted(False, 200)
    shut_buy, shut_sell = quoted(True, 200)

    # With the road open, carts have levelled the two ends and there is
    # nothing in it. With it shut, the fort is short and pays for it.
    assert shut_sell - shut_buy > open_sell - open_buy


def test_a_market_economy_with_no_currency_is_a_content_error(tmp_path: Path) -> None:
    from mace.content.validation import Severity, validate_library

    game_pack(
        tmp_path,
        pack_id="broke",
        game={"rules": {"economy": "market"}},
    )
    report = validate_library(load_library(tmp_path))
    assert any(
        one.severity is Severity.ERROR and "currency" in one.message
        for one in report.problems
    )


def test_a_stall_in_a_simple_economy_is_a_warning(tmp_path: Path) -> None:
    from mace.content.validation import Severity, validate_library

    library = valley(tmp_path)
    game = library.pack("valley").game
    assert game is not None
    object.__setattr__(game.rules, "economy", "simple")

    report = validate_library(library)
    assert any(
        one.severity is Severity.WARNING and "stall" in one.message
        for one in report.problems
    )


def test_a_trade_is_a_record_a_save_can_replay(tmp_path: Path) -> None:
    library = valley(tmp_path)
    from mace.engine.actions import decode

    action = Trade(good="grain", qty=7, sell=True)
    assert decode(action.record()) == action
    del library


def test_an_empty_lot_is_refused(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=0), library)
    assert "at least one" in result.events[0].record()["message"]


def test_an_absurd_lot_is_refused(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(
        opened(library).state, Trade(good="grain", qty=100_000), library
    )
    assert str(trade.MAX_LOT) in result.events[0].record()["message"]


def test_you_cannot_buy_more_than_the_shelf_holds(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="grain", qty=1), library)
    result.state.markets["valley:farm-market"].stock[GRAIN] = 3.0
    result = step(result.state, Trade(good="grain", qty=9), library)
    assert "do not have" in result.events[0].record()["message"]


def test_a_good_the_merchant_never_heard_of_is_refused(tmp_path: Path) -> None:
    library = valley(tmp_path)
    result = step(opened(library).state, Trade(good="mithril", qty=1), library)
    assert result.events[0].record()["kind"] == "engine.rule-failed"


def test_the_view_carries_the_counter_the_player_is_standing_at(
    tmp_path: Path,
) -> None:
    """A shop panel is a projection like every other panel."""
    from mace.session.view import view

    library = valley(tmp_path)
    result = begin(library, "valley", seed="trade")
    assert view(library, result.state).record()["stall"] is None

    result = opened(library)
    seen = view(library, result.state).record()["stall"]
    assert seen is not None
    assert seen["merchant"] == KEEPER
    assert any(row["good"] == GRAIN for row in seen["goods"])


def test_a_stall_menu_shows_a_price_it_cannot_afford(tmp_path: Path) -> None:
    """In a terminal the menu is the price list; a blank one tells you nothing."""
    library = valley(tmp_path)
    result = opened(library)
    result.state.protagonist.inventory[GOLD] = 1
    result = step(result.state, Choose(0), library)  # buy one, and fail
    assert isinstance(result.events[0], object)

    result = begin(library, "valley", seed="trade")
    result.state.protagonist.inventory[GOLD] = 1
    which = next(
        index
        for index, option in enumerate(result.state.pending.options)  # type: ignore[union-attr]
        if option.trade == KEEPER
    )
    result = step(result.state, Choose(which), library)
    rows = [
        option
        for option in result.state.pending.options  # type: ignore[union-attr]
        if option.prompt.startswith("Buy Grain")
    ]
    assert rows and not rows[0].available and rows[0].hint == "you have 1"


def test_a_trade_cannot_be_made_from_across_the_valley(tmp_path: Path) -> None:
    """The merchant has to still be where the player is."""
    library = valley(tmp_path)
    result = opened(library)
    result.state.entities[KEEPER].location = "valley:fort"
    result = step(result.state, Trade(good="grain", qty=1), library)
    assert "not trading" in result.events[0].record()["message"]


def test_no_currency_means_no_stall(tmp_path: Path) -> None:
    library = valley(tmp_path)
    game = library.pack("valley").game
    assert game is not None
    object.__setattr__(game.rules, "currency", None)

    result = begin(library, "valley", seed="trade")
    context = context_for(library, result.state)
    assert trade.look(context, result.state.entities[KEEPER]) is None


def test_a_merchant_never_sells_the_coin_itself(tmp_path: Path) -> None:
    """A market that dealt in coin would price money in money."""
    library = valley(tmp_path)
    counter = stall(library, opened(library).state)
    assert counter.row(GOLD) is None


def test_the_stall_event_is_reissued_as_prices_move(tmp_path: Path) -> None:
    """A client holding the first price list would be quoting a dead market."""
    library = valley(tmp_path)
    result = opened(library)
    first = next(
        event for event in result.events if event.record()["kind"] == "trade.stall"
    ).record()

    result = step(result.state, Trade(good="grain", qty=40), library)
    second = next(
        event for event in result.events if event.record()["kind"] == "trade.stall"
    ).record()

    assert first["goods"][0]["available"] - second["goods"][0]["available"] == 40
