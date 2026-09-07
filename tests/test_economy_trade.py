"""Trade flow: what the road between two markets does to the price at each end.

This is the payoff ADR-0007 was written for. A closed pass has to make iron
dear in the mountains *because trade actually stopped*, not because a script
fired, so the tests here are mostly about roads: a long one, a dangerous one,
a one-way one, and a shut one.

Two of them are load-bearing rather than illustrative.
`test_a_long_catch_up_is_the_same_world_as_a_short_one` is the market laziness
property from `test_economy_markets.py` asked again now that markets depend on
each other — coupling is exactly the kind of change that quietly breaks it.
And `test_shutting_a_road_does_not_reach_back_before_it_shut` is the other
half of the same promise: a catch-up applies today's roads to every tick it
crosses, so a landslide has to commit the ticks before it first, or a market
nobody looked at will have been cut off since the world began.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import load_library
from mace.engine import economy
from mace.engine.effects import apply_all
from mace.engine.state import GameState, RouteState
from mace.engine.step import context_for
from mace.model import Effect
from test_economy_markets import GOODS, ITEMS, playthrough

GROWER = "tiny:grower"
EATER = "tiny:eater"
ROAD = "tiny:road"
GRAIN = "tiny:grain"
IRON = "tiny:iron"


def valley(
    root: Path,
    *,
    road: dict[str, Any] | None = None,
    grower: dict[str, Any] | None = None,
    eater: dict[str, Any] | None = None,
    library: bool = False,
) -> Any:
    """Two markets a road apart: `home` grows grain and `castle` eats it.

    Parameters
    ----------
    root : Path
        Where to write the pack.
    road : dict or None
        Fields to merge into the route between them.
    grower, eater : dict or None
        Fields to merge into the market at each end.
    library : bool
        Return the loaded library rather than the prepared network, for the
        tests that need to build a playthrough against it.

    Returns
    -------
    Network or Library
        Whichever was asked for.
    """
    game_pack(
        root,
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {"hitpoints": {"base": 20, "max": 20}},
                },
                *ITEMS,
            ],
            "goods": GOODS,
            "routes": [
                {
                    "id": "road",
                    "from": "home",
                    "to": "castle",
                    "ticks": 6,
                    **(road or {}),
                }
            ],
            "markets": [
                {
                    "id": "grower",
                    "location": "home",
                    "produces": [{"good": "grain", "perTick": 2.0}],
                    "stock": {"grain": {"initial": 400, "capacity": 800}},
                    **(grower or {}),
                },
                {
                    "id": "eater",
                    "location": "castle",
                    "consumes": [{"good": "grain", "perTick": 1.0}],
                    "stock": {"grain": {"initial": 100, "capacity": 400}},
                    **(eater or {}),
                },
            ],
        },
    )
    loaded = load_library(root)
    return loaded if library else economy.prepare(loaded)


def chain(root: Path) -> economy.Network:
    """Three markets in a line, with the hamlet in the middle.

    `peasants-quest` in miniature: a caravan post two ticks down a safe track
    makes iron, a poor hamlet passes it along, and a rich castle six ticks up
    a dangerous road eats it.

    Parameters
    ----------
    root : Path
        Where to write the pack.

    Returns
    -------
    Network
        The three markets and the two roads between them.
    """
    game_pack(
        root,
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {"hitpoints": {"base": 20, "max": 20}},
                },
                *ITEMS,
            ],
            "goods": GOODS,
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle"},
                {"id": "post", "name": "The Post"},
            ],
            "routes": [
                {
                    "id": "road",
                    "from": "home",
                    "to": "castle",
                    "ticks": 6,
                    "dangerLevel": 5,
                    "encounters": "nothing",
                },
                {"id": "track", "from": "home", "to": "post", "ticks": 2},
            ],
            "markets": [
                {
                    "id": "grower",
                    "location": "home",
                    "size": "hamlet",
                    "wealth": 0.3,
                    "consumes": [{"good": "iron", "perTick": 0.05}],
                },
                {
                    "id": "eater",
                    "location": "castle",
                    "size": "town",
                    "wealth": 0.8,
                    "consumes": [{"good": "iron", "perTick": 0.4}],
                    "stock": {"iron": {"initial": 25, "capacity": 80}},
                },
                {
                    "id": "caravan",
                    "location": "post",
                    "wealth": 0.5,
                    "produces": [{"good": "iron", "perTick": 0.45}],
                    "stock": {"iron": {"initial": 12, "capacity": 40}},
                },
            ],
        },
    )
    return economy.prepare(load_library(root))


def after(network: economy.Network, ticks: int, shut: bool = False) -> GameState:
    """Run a valley forward and hand back the playthrough.

    Parameters
    ----------
    network : Network
        The markets and roads.
    ticks : int
        How far to run.
    shut : bool
        Whether the road was closed the whole time.

    Returns
    -------
    GameState
        With every market in the group committed to `ticks`.
    """
    state = playthrough(tick=ticks)
    if shut:
        state.routes[ROAD] = RouteState(route=ROAD, closed=True)
    economy.sync(state, network, GROWER)
    return state


def price(network: economy.Network, state: GameState, market_id: str) -> float:
    """What grain costs at a market, as a multiple of its base value.

    Parameters
    ----------
    network : Network
        The markets and roads.
    state : GameState
        A playthrough with that market committed.
    market_id : str
        Qualified market id.

    Returns
    -------
    float
        The multiple.
    """
    prepared = network.markets[market_id]
    dealt = prepared.goods[GRAIN]
    held = state.markets[market_id].stock[GRAIN]
    return economy.price_of(dealt, held, prepared.market.wealth) / dealt.base_value


# ── What a road is, for trade ─────────────────────────────────────────────────


def test_a_road_between_two_markets_is_a_trade_link(tmp_path: Path) -> None:
    network = valley(tmp_path)
    assert [link.route for link in network.links] == [ROAD]
    assert network.group(GROWER).markets == (EATER, GROWER)


def test_markets_with_no_road_between_them_are_separate_economies(
    tmp_path: Path,
) -> None:
    """A market nothing reaches is its own world, and is carried alone."""
    game_pack(
        tmp_path,
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {"hitpoints": {"base": 20, "max": 20}},
                },
                *ITEMS,
            ],
            "goods": GOODS,
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle"},
                {"id": "island", "name": "The Island"},
            ],
            "markets": [
                {"id": "grower", "location": "home", "trades": ["grain"]},
                {"id": "eater", "location": "castle", "trades": ["grain"]},
                {"id": "hermit", "location": "island", "trades": ["grain"]},
            ],
        },
    )
    network = economy.prepare(load_library(tmp_path))
    assert network.group(GROWER).markets == (EATER, GROWER)
    assert network.group("tiny:hermit").markets == ("tiny:hermit",)


def test_only_goods_both_ends_deal_in_cross(tmp_path: Path) -> None:
    """A market with no shelf for iron has nowhere to put it."""
    network = valley(tmp_path, grower={"trades": ["grain", "iron"]})
    state = after(network, 200)
    assert state.markets[GROWER].stock[IRON] > 0
    assert IRON not in state.markets[EATER].stock


# ── What a road does to a price ───────────────────────────────────────────────


def test_goods_move_from_where_they_are_cheap_to_where_they_are_dear(
    tmp_path: Path,
) -> None:
    network = valley(tmp_path)
    state = after(network, 200)
    assert state.markets[EATER].stock[GRAIN] > 100
    assert price(network, state, EATER) > price(network, state, GROWER)


def test_a_shut_road_moves_nothing(tmp_path: Path) -> None:
    network = valley(tmp_path)
    state = after(network, 200, shut=True)
    # The eater eats one a tick out of a hundred and nothing comes up the road.
    assert state.markets[EATER].stock[GRAIN] == 0.0


def test_a_shut_road_makes_the_two_sides_diverge(tmp_path: Path) -> None:
    """The reason weather and events were built first."""
    open_road = after(network := valley(tmp_path), 200)
    shut_road = after(network, 200, shut=True)

    assert price(network, shut_road, EATER) > price(network, open_road, EATER)
    assert price(network, shut_road, GROWER) < price(network, open_road, GROWER)


def test_a_longer_road_keeps_a_wider_gap(tmp_path: Path) -> None:
    """Distance is what leaves a profit for whoever makes the trip."""
    near = valley(tmp_path / "a", road={"ticks": 2})
    far = valley(tmp_path / "b", road={"ticks": 40})

    def spread(network: economy.Network) -> float:
        state = after(network, 200)
        return price(network, state, EATER) - price(network, state, GROWER)

    assert spread(far) > spread(near)


def test_a_dangerous_road_keeps_a_wider_gap(tmp_path: Path) -> None:
    """Bandit country is expensive country."""
    safe = valley(tmp_path / "a", road={"dangerLevel": 0})
    robbed = valley(tmp_path / "b", road={"dangerLevel": 10, "encounters": "nothing"})

    def spread(network: economy.Network) -> float:
        state = after(network, 200)
        return price(network, state, EATER) - price(network, state, GROWER)

    assert spread(robbed) > spread(safe)


def test_trade_capacity_scales_what_a_road_carries(tmp_path: Path) -> None:
    """A highway and a goat path are not the same road."""
    path = valley(tmp_path / "a", road={"tradeCapacity": 0.1})
    highway = valley(tmp_path / "b", road={"tradeCapacity": 4.0})

    assert (
        after(highway, 200).markets[EATER].stock[GRAIN]
        > after(path, 200).markets[EATER].stock[GRAIN]
    )


def test_a_one_way_road_carries_trade_one_way(tmp_path: Path) -> None:
    """Goods cannot be carted back up a cliff either."""
    network = valley(
        tmp_path,
        road={"bidirectional": False},
        grower={
            "produces": [],
            "consumes": [{"good": "grain", "perTick": 1.0}],
            "stock": {"grain": {"initial": 50, "capacity": 800}},
        },
        eater={
            "consumes": [],
            "produces": [{"good": "grain", "perTick": 2.0}],
        },
    )
    state = after(network, 200)
    # The castle is the one with grain, and the road only runs the other way.
    assert state.markets[GROWER].stock[GRAIN] == 0.0
    assert state.markets[EATER].stock[GRAIN] > 100


# ── The properties everything else rests on ───────────────────────────────────


def test_trade_never_overshoots_the_price_it_is_chasing(tmp_path: Path) -> None:
    """A luxury shipped back and forth every tick is a ringing shelf.

    Iron's `elasticity` of 1.3 makes its price move sharply with its shelf,
    which is the case that oscillates if a haul may carry past the point where
    the two ends agree. The shape that shows it is a place in the middle: the
    hamlet takes iron off the short road from the caravan post and puts it
    straight onto the long road to the castle, and without `levelling` the
    second haul overshoots what the first brought and sends it back next tick.
    This is `peasants-quest` in miniature, where it was first seen.
    """
    network = chain(tmp_path)
    state = playthrough()
    economy.sync(state, network, GROWER)

    trail = []
    for tick in range(1, 501):
        state.tick = tick
        trail.append(economy.sync(state, network, GROWER).stock[IRON])

    steps = [b - a for a, b in zip(trail[-100:], trail[-99:], strict=False)]
    turns = sum(1 for a, b in zip(steps, steps[1:], strict=False) if a * b < 0)
    assert turns == 0, f"the shelf is ringing: {turns} reversals in a hundred ticks"


@pytest.mark.parametrize("ticks", [1, 7, 50, 500])
def test_a_long_catch_up_is_the_same_world_as_a_short_one(
    tmp_path: Path, ticks: int
) -> None:
    """Coupling markets must not have cost the laziness its correctness."""
    network = valley(tmp_path)

    watched = playthrough()
    for tick in range(1, ticks + 1):
        watched.tick = tick
        economy.sync(watched, network, GROWER)

    ignored = playthrough(tick=ticks)
    economy.sync(ignored, network, EATER)

    for market_id in (GROWER, EATER):
        assert watched.markets[market_id].stock == pytest.approx(
            ignored.markets[market_id].stock
        )


def test_syncing_one_market_commits_everything_it_trades_with(
    tmp_path: Path,
) -> None:
    """They moved each other's shelves to get here; one cannot be kept back."""
    network = valley(tmp_path)
    state = playthrough(tick=50)
    economy.sync(state, network, GROWER)

    assert state.markets[EATER].stepped_to == 50
    assert state.markets[GROWER].stepped_to == 50


def test_asking_a_price_carries_the_whole_group_without_committing_it(
    tmp_path: Path,
) -> None:
    """The overlay reads a price that came up the road, and moves nothing."""
    network = valley(tmp_path)
    state = playthrough(tick=200)

    seen = economy.projected(state, network, EATER, 200)
    assert seen[GRAIN] > 100
    assert state.markets == {}


def test_shutting_a_road_does_not_reach_back_before_it_shut(
    tmp_path: Path,
) -> None:
    """A landslide on day two did not close the road on day one.

    A catch-up applies today's roads to every tick it crosses, so a market
    nobody has looked at since the world began would find the pass had always
    been shut. The closure commits the ticks before it first; this checks that
    a lazily-caught-up world and a watched one end up in the same place.
    """
    library = valley(tmp_path, library=True)
    network = economy.prepare(library)
    closure = [Effect.model_validate({"closeRoute": {"route": "road"}})]

    watched = playthrough()
    for tick in range(1, 201):
        watched.tick = tick
        economy.sync(watched, network, GROWER)
        if tick == 100:
            apply_all(closure, context_for(library, watched))

    lazy = playthrough(tick=100)
    apply_all(closure, context_for(library, lazy))
    lazy.tick = 200
    economy.sync(lazy, network, GROWER)

    for market_id in (GROWER, EATER):
        assert watched.markets[market_id].stock == pytest.approx(
            lazy.markets[market_id].stock
        )


def test_a_market_never_ships_more_than_it_has(tmp_path: Path) -> None:
    """A market is a town, not a creditor, however dear the next town is."""
    network = valley(
        tmp_path,
        grower={"stock": {"grain": {"initial": 5, "capacity": 800}}},
        eater={"consumes": [{"good": "grain", "perTick": 4.0}]},
    )
    state = after(network, 300)
    assert all(held >= 0.0 for held in state.markets[GROWER].stock.values())
    assert all(held >= 0.0 for held in state.markets[EATER].stock.values())


def test_a_road_never_fills_a_shelf_past_its_capacity(tmp_path: Path) -> None:
    """A market is a town, not a warehouse, however cheap the last one was."""
    network = valley(
        tmp_path,
        grower={"produces": [{"good": "grain", "perTick": 20.0}]},
        eater={"stock": {"grain": {"initial": 10, "capacity": 40}}},
    )
    state = after(network, 300)
    assert state.markets[EATER].stock[GRAIN] <= 40.0
