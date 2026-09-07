"""Unit tests for the goods and markets models.

Two things are being protected here. The first is that a good is the market
behaviour of an item that already exists — a good that described its own name
and weight would be a second `grain`, and the first bug would be a shop selling
something the player cannot carry.

The second is that the numbers an author leaves out have answers that make a
world open in the ordinary way: a market that starts at the price it will
mostly charge, rather than in a shortage nobody wrote.
"""

import pytest
from pydantic import ValidationError

from mace.content.validation import references
from mace.model import Good, Market, Stock


def test_a_good_is_the_behaviour_of_an_item() -> None:
    good = Good.model_validate({"id": "grain", "item": "grain", "elasticity": 0.4})
    assert good.item == "grain"


def test_a_good_must_name_an_item() -> None:
    """Weight and value live on the item; a good that repeated them would drift."""
    with pytest.raises(ValidationError, match="item"):
        Good.model_validate({"id": "grain", "name": "Grain", "baseValue": 4})


def test_an_items_reference_is_checked_against_entities() -> None:
    good = Good.model_validate({"id": "grain", "item": "fantasy.core:grain"})
    found = {reference.field: reference.collection for reference in references(good)}
    assert found["item"] == "entities"


def test_elasticity_must_be_positive() -> None:
    """Zero elasticity is demand that never responds — the model is meaningless."""
    with pytest.raises(ValidationError, match="greater than 0"):
        Good.model_validate({"id": "grain", "item": "grain", "elasticity": 0})


# ── Stock ─────────────────────────────────────────────────────────────────────


def test_a_market_aims_at_half_its_shelves_by_default() -> None:
    assert Stock(capacity=800).wanted == 400


def test_a_market_opens_at_the_price_it_will_mostly_charge() -> None:
    """No `initial` means no shortage on turn one."""
    assert Stock(capacity=800, target=500).opening == 500


def test_an_explicit_opening_is_kept() -> None:
    assert Stock(capacity=800, target=500, initial=20).opening == 20


def test_a_market_cannot_want_more_than_it_can_hold() -> None:
    with pytest.raises(ValidationError, match="target .* is above capacity"):
        Stock(capacity=100, target=200)


def test_a_market_cannot_start_with_more_than_it_can_hold() -> None:
    with pytest.raises(ValidationError, match="initial .* is above capacity"):
        Stock(capacity=100, initial=200)


def test_a_market_may_start_empty() -> None:
    """A besieged town is a real thing to want to write."""
    assert Stock(capacity=100, initial=0).opening == 0


# ── Market ────────────────────────────────────────────────────────────────────


def test_size_scales_the_default_shelves() -> None:
    hamlet = Market(id="fenmoor-market", location="fenmoor", size="hamlet")
    city = Market(id="capital-market", location="capital", size="city")
    assert hamlet.depth < city.depth


def test_a_market_is_a_village_unless_told_otherwise() -> None:
    market = Market(id="fenmoor-market", location="fenmoor")
    assert market.size == "village"
    assert market.depth == 1.0


def test_an_unknown_size_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Market.model_validate(
            {"id": "fenmoor-market", "location": "fenmoor", "size": "metropolis"}
        )


def test_wealth_is_a_fraction() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Market.model_validate(
            {"id": "fenmoor-market", "location": "fenmoor", "wealth": 1.5}
        )


def test_stock_keys_are_goods_the_validator_can_check() -> None:
    """The key of a `stock` mapping is a reference like any other."""
    market = Market.model_validate(
        {
            "id": "fenmoor-market",
            "location": "fenmoor",
            "stock": {"grain": {"capacity": 800}},
        }
    )
    found = {
        reference.reference: reference.collection for reference in references(market)
    }
    assert found["grain"] == "goods"
    assert found["fenmoor"] == "locations"


def test_a_flow_must_actually_flow() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        Market.model_validate(
            {
                "id": "fenmoor-market",
                "location": "fenmoor",
                "produces": [{"good": "grain", "perTick": 0}],
            }
        )


def test_a_market_round_trips_through_its_authored_shape() -> None:
    authored = {
        "id": "fenmoor-market",
        "location": "fenmoor",
        "size": "hamlet",
        "wealth": 0.3,
        "tags": ["farmland", "settlement"],
        "produces": [{"good": "grain", "perTick": 0.8}],
        "stock": {"grain": {"initial": 400, "capacity": 800}},
        "trades": ["salt"],
    }
    market = Market.model_validate(authored)
    assert market.authored() == authored
