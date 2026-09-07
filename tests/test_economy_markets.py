"""Markets: what a place deals in, and how its shelves move unobserved.

The load-bearing test here is `test_a_long_catch_up_is_the_same_world_as_a_short_one`.
Markets are carried forward when something looks at them rather than stepped
every tick, and that is only allowed to be an optimization — a player who
visits a town every day and a player who arrives after a season must find the
same shelves. Everything else in the economy is built on that being true, so
it is checked directly rather than trusted.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import Library, load_library
from mace.engine import economy
from mace.engine.rng import RandomSource
from mace.engine.state import GameState, MarketState

GOODS: list[dict[str, Any]] = [
    {
        "id": "grain",
        "item": "grain",
        "elasticity": 0.4,
        "producedBy": ["farmland"],
        "consumedBy": ["settlement"],
    },
    {"id": "iron", "item": "iron", "elasticity": 1.3, "consumedBy": ["smithy"]},
    {
        "id": "milk",
        "item": "milk",
        "elasticity": 0.5,
        "perishable": {"ticksToSpoil": 100},
    },
]

MARKET = "tiny:market"

ITEMS: list[dict[str, Any]] = [
    {"id": "grain", "kind": "item", "name": "Grain", "item": {"baseValue": 4}},
    {"id": "iron", "kind": "item", "name": "Iron", "item": {"baseValue": 30}},
    {"id": "milk", "kind": "item", "name": "Milk", "item": {"baseValue": 2}},
]


def trading_world(root: Path, *markets: dict[str, Any]) -> Library:
    """A game pack with items, goods, and whatever markets a test needs.

    Parameters
    ----------
    root : Path
        Where to write it.
    *markets
        Market definitions.

    Returns
    -------
    Library
        The loaded library.
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
            "markets": list(markets),
        },
    )
    return load_library(root)


def playthrough(tick: int = 0, start_tick: int = 0) -> GameState:
    """A bare state, for the market functions that only need a clock.

    Parameters
    ----------
    tick : int
        Now.
    start_tick : int
        The tick the playthrough opened on.

    Returns
    -------
    GameState
        The state.
    """
    return GameState(
        pack="tiny",
        seed="seed",
        rng=RandomSource("seed"),
        player="hero",
        tick=tick,
        start_tick=start_tick,
    )


def one_market(root: Path, **fields: Any) -> economy.Network:
    """A network holding one market at `home`, with the given fields.

    Parameters
    ----------
    root : Path
        Where to write the pack.
    **fields
        Fields for the market definition.

    Returns
    -------
    Network
        The resolved market, alone in its group — `MARKET` is its id.
    """
    library = trading_world(root, {"id": "market", "location": "home", **fields})
    return economy.prepare(library)


# ── What a market deals in ────────────────────────────────────────────────────


def test_a_market_deals_in_what_it_makes_and_uses(tmp_path: Path) -> None:
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 0.8}],
        consumes=[{"good": "iron", "perTick": 0.1}],
    )
    assert set(network.markets[MARKET].goods) == {"tiny:grain", "tiny:iron"}
    assert network.markets[MARKET].goods["tiny:grain"].produced == 0.8
    assert network.markets[MARKET].goods["tiny:iron"].consumed == 0.1


def test_a_tag_grows_every_good_that_names_it(tmp_path: Path) -> None:
    """The reason a world of twenty markets is cheap to write."""
    network = one_market(tmp_path, tags=["farmland"])
    assert network.markets[MARKET].goods["tiny:grain"].produced > 0
    assert network.markets[MARKET].goods["tiny:grain"].consumed == 0


def test_a_written_flow_beats_the_one_a_tag_implies(tmp_path: Path) -> None:
    """An author who wrote a number meant that number."""
    network = one_market(
        tmp_path, tags=["farmland"], produces=[{"good": "grain", "perTick": 0.8}]
    )
    assert network.markets[MARKET].goods["tiny:grain"].produced == 0.8


def test_size_scales_what_a_tag_implies(tmp_path: Path) -> None:
    hamlet = one_market(tmp_path / "a", tags=["farmland"], size="hamlet")
    city = one_market(tmp_path / "b", tags=["farmland"], size="city")
    assert (
        city.markets[MARKET].goods["tiny:grain"].produced
        > hamlet.markets[MARKET].goods["tiny:grain"].produced
    )


def test_a_middleman_deals_in_what_it_only_trades(tmp_path: Path) -> None:
    network = one_market(tmp_path, trades=["grain"])
    assert network.markets[MARKET].goods["tiny:grain"].net == 0
    assert network.markets[MARKET].goods["tiny:grain"].stock.capacity > 0


def test_a_good_nobody_sized_gets_shelves_from_the_market_size(
    tmp_path: Path,
) -> None:
    hamlet = one_market(tmp_path / "a", trades=["grain"], size="hamlet")
    city = one_market(tmp_path / "b", trades=["grain"], size="city")
    assert city.markets[MARKET].goods["tiny:grain"].stock.capacity > (
        hamlet.markets[MARKET].goods["tiny:grain"].stock.capacity
    )


def test_a_market_is_found_by_where_it_stands(tmp_path: Path) -> None:
    library = trading_world(tmp_path, {"id": "market", "location": "home"})
    network = economy.prepare(library)
    assert economy.at(network, "tiny:home") is not None
    assert economy.at(network, "tiny:castle") is None


# ── Shelves moving ────────────────────────────────────────────────────────────


def test_production_fills_a_shelf(tmp_path: Path) -> None:
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 10, "capacity": 100}},
    )
    state = playthrough(tick=5)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == pytest.approx(15.0)


def test_consumption_empties_one(tmp_path: Path) -> None:
    network = one_market(
        tmp_path,
        consumes=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 10, "capacity": 100}},
    )
    state = playthrough(tick=5)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == pytest.approx(5.0)


def test_a_shelf_never_goes_below_empty(tmp_path: Path) -> None:
    """A market is a town, not a creditor."""
    network = one_market(
        tmp_path,
        consumes=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 3, "capacity": 100}},
    )
    state = playthrough(tick=50)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == 0.0


def test_production_above_capacity_spills(tmp_path: Path) -> None:
    """A market is a town, not a warehouse."""
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 5.0}],
        stock={"grain": {"initial": 10, "capacity": 40}},
    )
    state = playthrough(tick=100)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == 40.0


def test_what_spoils_settles_where_making_and_rotting_balance(
    tmp_path: Path,
) -> None:
    """Perishability is what stops a player buying out a harvest.

    Making one unit a tick of something that keeps for a hundred settles just
    under a hundred on the shelf, however long the world runs — a shelf that
    would otherwise have climbed to ten thousand.
    """
    network = one_market(
        tmp_path,
        produces=[{"good": "milk", "perTick": 1.0}],
        stock={"milk": {"initial": 0, "capacity": 10_000}},
    )
    state = playthrough(tick=5_000)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:milk"] == pytest.approx(99.0, abs=0.5)


def test_what_keeps_fills_the_shelf_that_what_spoils_cannot(
    tmp_path: Path,
) -> None:
    network = one_market(
        tmp_path,
        produces=[{"good": "milk", "perTick": 1.0}, {"good": "grain", "perTick": 1.0}],
        stock={
            "milk": {"initial": 0, "capacity": 10_000},
            "grain": {"initial": 0, "capacity": 10_000},
        },
    )
    state = playthrough(tick=2_000)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == pytest.approx(2_000.0)
    assert held.stock["tiny:milk"] < 100


# ── The property the laziness rests on ────────────────────────────────────────


@pytest.mark.parametrize("ticks", [1, 7, 50, 500])
def test_a_long_catch_up_is_the_same_world_as_a_short_one(
    tmp_path: Path, ticks: int
) -> None:
    """Fast-forwarding is an optimization, not a different world.

    A player who looks every tick and a player who arrives after a season must
    find the same shelves, or the whole lazy design is a bug generator.
    """
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 0.8}],
        consumes=[{"good": "iron", "perTick": 0.05}],
        stock={
            "grain": {"initial": 400, "capacity": 800},
            "iron": {"initial": 20, "capacity": 60},
        },
    )

    watched = playthrough()
    for tick in range(1, ticks + 1):
        watched.tick = tick
        economy.sync(watched, network, MARKET)

    ignored = playthrough(tick=ticks)
    economy.sync(ignored, network, MARKET)

    assert watched.markets[MARKET].stock == pytest.approx(ignored.markets[MARKET].stock)


def test_a_market_opened_late_opens_at_the_start_of_the_playthrough(
    tmp_path: Path,
) -> None:
    """Arriving on day fifty finds the shelves it would have had all along."""
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 0, "capacity": 10_000}},
    )
    state = playthrough(tick=120, start_tick=20)
    held = economy.sync(state, network, MARKET)
    assert held.stock["tiny:grain"] == pytest.approx(100.0)


def test_syncing_twice_moves_nothing(tmp_path: Path) -> None:
    """Arriving somewhere and time passing both want the shelves current."""
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 0, "capacity": 100}},
    )
    state = playthrough(tick=10)
    once = dict(economy.sync(state, network, MARKET).stock)
    twice = dict(economy.sync(state, network, MARKET).stock)
    assert once == twice


def test_asking_what_a_shelf_holds_does_not_move_it(tmp_path: Path) -> None:
    """A question about the world must not change it — replay depends on it."""
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 1.0}],
        stock={"grain": {"initial": 0, "capacity": 100}},
    )
    state = playthrough(tick=10)
    state.markets[MARKET] = MarketState(
        market=MARKET, stock={"tiny:grain": 0.0}, stepped_to=0
    )
    projected = economy.projected(state, network, MARKET, 10)
    assert projected["tiny:grain"] == pytest.approx(10.0)
    assert state.markets[MARKET].stock["tiny:grain"] == 0.0
    assert state.markets[MARKET].stepped_to == 0


def test_a_projection_is_what_the_catch_up_commits(tmp_path: Path) -> None:
    """The pure answer and the committed one cannot be allowed to disagree."""
    network = one_market(
        tmp_path,
        produces=[{"good": "grain", "perTick": 0.8}],
        consumes=[{"good": "iron", "perTick": 0.05}],
        stock={
            "grain": {"initial": 400, "capacity": 800},
            "iron": {"initial": 20, "capacity": 60},
        },
    )
    state = playthrough(tick=0)
    economy.sync(state, network, MARKET)
    ahead = economy.projected(state, network, MARKET, 90)

    state.tick = 90
    committed = economy.sync(state, network, MARKET)
    assert committed.stock == pytest.approx(ahead)
