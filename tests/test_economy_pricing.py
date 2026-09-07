"""Price formation: what scarcity does to a price, and how far it may do it.

The two things worth protecting are the ones a player builds an intuition on.
A necessity has to get *dear* in a shortage and a luxury has to become
*absent* — that difference is the whole reason elasticity is a number an author
picks. And whatever they pick, the price has to stay inside the bound ADR-0007
promises, because that bound is what stops a feedback loop in somebody else's
game becoming a bug report here.
"""

from pathlib import Path
from typing import Any

import pytest

from mace.engine import economy
from mace.engine.economy import pricing
from test_economy_markets import MARKET, one_market

BASE_GRAIN = 4.0
BASE_IRON = 30.0


def dealt(tmp_path: Path, **fields: Any) -> dict[str, economy.Dealt]:
    """The goods of a market that holds grain and iron.

    Parameters
    ----------
    tmp_path : Path
        Where to write the pack.
    **fields
        Fields for the market definition.

    Returns
    -------
    dict
        Qualified good id to the resolved good.
    """
    network = one_market(
        tmp_path,
        stock={
            "grain": {"target": 400, "capacity": 800},
            "iron": {"target": 30, "capacity": 60},
        },
        **fields,
    )
    return network.markets[MARKET].goods


def test_a_market_holding_what_it_wants_charges_the_going_rate(
    tmp_path: Path,
) -> None:
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.price_of(grain, 400, wealth=0.5) == pytest.approx(BASE_GRAIN)


def test_a_shortage_makes_a_necessity_dear(tmp_path: Path) -> None:
    """Grain at 0.4: people pay, they don't stop buying."""
    grain = dealt(tmp_path)["tiny:grain"]
    short = pricing.price_of(grain, 100, wealth=0.5)
    assert short > BASE_GRAIN
    assert short < BASE_GRAIN * 2


def test_a_shortage_makes_a_luxury_absent(tmp_path: Path) -> None:
    """Iron at 1.3: demand collapses rather than paying."""
    goods = dealt(tmp_path)
    grain_swing = pricing.price_of(goods["tiny:grain"], 1, 0.5) / BASE_GRAIN
    iron_swing = pricing.price_of(goods["tiny:iron"], 1, 0.5) / BASE_IRON
    assert iron_swing > grain_swing


def test_a_glut_makes_things_cheap(tmp_path: Path) -> None:
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.price_of(grain, 800, wealth=0.5) < BASE_GRAIN


@pytest.mark.parametrize("held", [0, 1, 5, 400, 800, 100_000])
def test_no_price_ever_leaves_the_bound(tmp_path: Path, held: float) -> None:
    """The cap ADR-0007 bought in exchange for never debugging hyperinflation.

    The doc's formula clamps scarcity and stops there, which holds only while
    elasticity is at most 1 — iron at 1.3 would price at 6× base. The engine
    clamps the ratio after the exponent too, which is what this checks.
    """
    goods = dealt(tmp_path)
    for good_id, base in (("tiny:grain", BASE_GRAIN), ("tiny:iron", BASE_IRON)):
        one = goods[good_id]
        for wealth in (0.0, 0.5, 1.0):
            price = pricing.price_of(one, held, wealth)
            ceiling = base * pricing.MAX_RATIO * pricing.wealth_factor(wealth)
            floor = base * pricing.MIN_RATIO * pricing.wealth_factor(wealth)
            assert floor <= price <= ceiling


def test_an_empty_shelf_is_expensive_and_not_infinite(tmp_path: Path) -> None:
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.price_of(grain, 0, 0.5) == pricing.price_of(grain, 1, 0.5)


# ── Wealth ────────────────────────────────────────────────────────────────────


def test_a_market_nobody_priced_pays_the_going_rate() -> None:
    """0.5 is the default `wealth`, and it must not be a thumb on the scale."""
    assert pricing.wealth_factor(0.5) == 1.0


def test_a_city_bids_over_the_odds_and_a_hamlet_cannot(tmp_path: Path) -> None:
    """The reason to carry something somewhere."""
    grain = dealt(tmp_path)["tiny:grain"]
    hamlet = pricing.price_of(grain, 400, wealth=0.3)
    city = pricing.price_of(grain, 400, wealth=1.0)
    assert hamlet < BASE_GRAIN < city


def test_wealth_never_outweighs_scarcity(tmp_path: Path) -> None:
    """Scarcity is the signal a player is meant to read; wealth is a nudge."""
    grain = dealt(tmp_path)["tiny:grain"]
    poor_and_starving = pricing.price_of(grain, 1, wealth=0.0)
    rich_and_glutted = pricing.price_of(grain, 800, wealth=1.0)
    assert poor_and_starving > rich_and_glutted


# ── Scarcity ──────────────────────────────────────────────────────────────────


def test_scarcity_is_measured_against_what_a_market_wants(tmp_path: Path) -> None:
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.scarcity_of(grain, 400) == pytest.approx(1.0)
    assert pricing.scarcity_of(grain, 200) == pytest.approx(2.0)
    assert pricing.scarcity_of(grain, 800) == pytest.approx(0.5)


def test_scarcity_is_bounded_at_both_ends(tmp_path: Path) -> None:
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.scarcity_of(grain, 1) == pricing.MAX_RATIO
    assert pricing.scarcity_of(grain, 1_000_000) == pricing.MIN_RATIO


def test_a_price_is_the_same_answer_every_time_it_is_asked(tmp_path: Path) -> None:
    """Nothing here draws, and nothing here writes — replay depends on it."""
    grain = dealt(tmp_path)["tiny:grain"]
    assert pricing.price_of(grain, 137, 0.4) == pricing.price_of(grain, 137, 0.4)
