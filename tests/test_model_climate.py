"""Unit tests for the climate, weather, front, and terrain models.

These pin down the reshape from raw tuples/dicts (`intensityRange: [0.4,
1.0]`, `transitions: {clear: {overcast: 3}}`) to named sub-models and lists of
named rows (`intensityRange: {min: 0.4, max: 1.0}`, `transitions: [{source:
clear, target: overcast, weight: 3}]`) — the change that makes every one of
these fields addressable by the wizard's `dig`/`plant` binding system the same
way everything else in the model already is.
"""

import pytest
from pydantic import ValidationError

from mace.model import Climate, ClimateSequence, Terrain, WeatherCondition, WeatherFront


def test_an_intensity_range_rejects_a_falling_pair() -> None:
    with pytest.raises(ValidationError, match="is higher than max"):
        WeatherCondition.model_validate(
            {"id": "storm", "intensityRange": {"min": 0.8, "max": 0.2}}
        )


def test_a_hop_range_rejects_a_falling_pair() -> None:
    with pytest.raises(ValidationError, match="is higher than max"):
        WeatherFront.model_validate({"id": "gale", "hops": {"min": 5, "max": 2}})


def test_a_transition_row_that_is_all_zero_is_rejected() -> None:
    with pytest.raises(ValidationError, match="could never leave it"):
        Climate.model_validate(
            {
                "id": "stuck",
                "transitions": [{"source": "clear", "target": "overcast", "weight": 0}],
            }
        )


def test_climate_season_finds_the_matching_row() -> None:
    climate = Climate.model_validate(
        {
            "id": "temperate",
            "seasons": [
                {"id": "autumn", "temperature": {"min": 2, "max": 16}},
                {"id": "winter", "temperature": {"min": -10, "max": 2}},
            ],
        }
    )
    assert climate.season("winter") is not None
    assert climate.season("winter").temperature.min == -10
    assert climate.season("summer") is None


def test_season_weights_fold_into_the_matching_season() -> None:
    """The wizard authors weights as flat rows; they land nested, unharmed."""
    climate = Climate.model_validate(
        {
            "id": "temperate",
            "seasons": [{"id": "autumn", "temperature": {"min": 2, "max": 16}}],
            "seasonWeights": [
                {"season": "autumn", "condition": "clear", "weight": 50},
                {"season": "autumn", "condition": "rain", "weight": 30},
                {"season": "winter", "condition": "clear", "weight": 10},
            ],
        }
    )
    autumn = climate.season("autumn")
    assert autumn is not None
    assert autumn.temperature is not None and autumn.temperature.min == 2
    assert {(w.condition, w.weight) for w in autumn.weights} == {
        ("clear", 50.0),
        ("rain", 30.0),
    }
    winter = climate.season("winter")
    assert winter is not None
    assert winter.temperature is None
    assert [(w.condition, w.weight) for w in winter.weights] == [("clear", 10.0)]


def test_a_season_weight_row_overwrites_its_own_condition_only() -> None:
    climate = Climate.model_validate(
        {
            "id": "temperate",
            "seasons": [
                {
                    "id": "autumn",
                    "weights": [{"condition": "clear", "weight": 1}],
                }
            ],
            "seasonWeights": [{"season": "autumn", "condition": "clear", "weight": 99}],
        }
    )
    autumn = climate.season("autumn")
    assert autumn is not None
    assert [(w.condition, w.weight) for w in autumn.weights] == [("clear", 99.0)]


def test_climate_transitions_from_gathers_one_sources_row() -> None:
    climate = Climate.model_validate(
        {
            "id": "temperate",
            "transitions": [
                {"source": "clear", "target": "overcast", "weight": 3},
                {"source": "clear", "target": "rain", "weight": 1},
                {"source": "rain", "target": "clear", "weight": 1},
            ],
        }
    )
    assert climate.transitions_from("clear") == {"overcast": 3.0, "rain": 1.0}
    assert climate.transitions_from("rain") == {"clear": 1.0}
    assert climate.transitions_from("fog") == {}


def test_a_sequence_step_may_be_a_bare_condition_ticks_line() -> None:
    sequence = ClimateSequence.model_validate(
        {"id": "storm-front", "steps": ["clear", "rain 2", "storm 3"]}
    )
    assert [(step.condition, step.ticks) for step in sequence.steps] == [
        ("clear", 1),
        ("rain", 2),
        ("storm", 3),
    ]


def test_a_sequence_step_line_needs_one_or_two_words() -> None:
    with pytest.raises(ValidationError, match="condition.*or.*condition ticks"):
        ClimateSequence.model_validate({"id": "storm-front", "steps": ["clear rain 2"]})


def test_terrain_cost_takes_the_worst_matching_tag() -> None:
    terrain = Terrain.model_validate(
        {
            "id": "track",
            "inWeather": [
                {"tag": "wet", "multiplier": 2.0},
                {"tag": "cold", "multiplier": 3.0},
            ],
        }
    )
    assert terrain.cost(("wet", "cold")) == 3.0
    assert terrain.cost(("wet",)) == 2.0
    assert terrain.cost(()) == 1.0


def test_a_climate_round_trips_through_its_authored_shape() -> None:
    authored = {
        "id": "temperate",
        "seasons": [
            {
                "id": "autumn",
                "temperature": {"min": 2, "max": 16},
                "weights": [{"condition": "clear", "weight": 50.0}],
            }
        ],
        "transitions": [{"source": "clear", "target": "clear", "weight": 90.0}],
    }
    climate = Climate.model_validate(authored)
    assert climate.authored() == authored
