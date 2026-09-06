"""Unit tests for the move and combat-profile models.

The guard rails here all protect the same thing: an unanswerable fight. An
attack nobody was shown, a defense that pretends to telegraph, a feint chance
with nothing to feint with — each of them produces a fight rather than a crash,
which is exactly why they are worth rejecting at load time.
"""

import pytest
from pydantic import ValidationError

from mace.model import CombatProfile, Move


def test_an_attack_must_telegraph() -> None:
    with pytest.raises(ValidationError, match="has no `tell`"):
        Move.model_validate({"id": "club-overhead", "type": "overhead"})


def test_a_defense_must_not_telegraph() -> None:
    with pytest.raises(ValidationError, match="only attacks telegraph"):
        Move.model_validate(
            {"id": "parry", "kind": "defense", "type": "parry", "tell": "..."}
        )


def test_a_defense_cannot_be_a_feint() -> None:
    with pytest.raises(ValidationError, match="cannot be a feint"):
        Move.model_validate(
            {"id": "parry", "kind": "defense", "type": "parry", "feint": True}
        )


def test_a_tell_may_be_a_bare_string() -> None:
    move = Move.model_validate(
        {"id": "thrust", "type": "thrust", "tell": "The point comes up."}
    )
    assert move.tell is not None
    assert move.tell[0].text == "The point comes up."


def test_a_tell_may_vary_with_the_world() -> None:
    move = Move.model_validate(
        {
            "id": "thrust",
            "type": "thrust",
            "tell": [
                {
                    "text": "You barely see the point come up.",
                    "when": {"dayPart": ["night"]},
                },
                {"text": "The point comes up."},
            ],
        }
    )
    assert move.tell is not None
    assert len(move.tell) == 2


def test_a_defense_may_deal_damage() -> None:
    """A strike is a defense that answers by hurting — that is the interrupt."""
    move = Move.model_validate(
        {
            "id": "strike",
            "kind": "defense",
            "type": "strike",
            "damage": {"min": 3, "max": 7},
        }
    )
    assert move.damage is not None
    assert move.damage.max == 7


def test_a_move_falls_back_to_its_id_for_a_name() -> None:
    move = Move.model_validate({"id": "club-sweep", "type": "sweep", "tell": "..."})
    assert move.label == "club-sweep"


def test_a_feint_chance_needs_something_to_feint_with() -> None:
    with pytest.raises(ValidationError, match="nothing for it to feint with"):
        CombatProfile.model_validate({"id": "duelist", "feintChance": 0.2})


def test_a_pattern_needs_at_least_one_move() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        CombatProfile.model_validate(
            {"id": "duelist", "moves": ["thrust"], "patterns": [{"sequence": []}]}
        )


def test_a_profile_round_trips_through_its_authored_shape() -> None:
    authored = {
        "id": "quick-duelist",
        "moves": ["thrust", "parry"],
        "patterns": [{"sequence": ["thrust", "thrust"], "weight": 40.0}],
        "feintChance": 0.2,
    }
    profile = CombatProfile.model_validate(authored)
    assert profile.authored() == authored
