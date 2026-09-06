"""Unit tests for the content models' shared conventions and guard rails.

The example-pack test proves the models accept the documented content. This one
proves they reject the content they should, and that the shorthands an author
relies on expand to the same thing the long form does.
"""

import pytest
from pydantic import ValidationError

from mace.engine.expr import Expression
from mace.model import (
    Condition,
    Effect,
    Entity,
    Location,
    Pack,
    Scene,
    Stat,
)

# ── Conventions shared by every model ─────────────────────────────────────────


def test_camel_case_keys_are_the_authoring_shape() -> None:
    location = Location.model_validate(
        {"id": "fenmoor", "name": "Fenmoor", "onArrive": "fenmoor-arrival"}
    )
    assert location.on_arrive == "fenmoor-arrival"


def test_python_field_names_are_accepted_too() -> None:
    """So engine and test code can build content without thinking in YAML."""
    location = Location(id="fenmoor", name="Fenmoor", on_arrive="fenmoor-arrival")
    assert location.on_arrive == "fenmoor-arrival"


def test_content_is_frozen() -> None:
    location = Location(id="fenmoor", name="Fenmoor")
    with pytest.raises(ValidationError):
        location.name = "Somewhere else"  # type: ignore[misc]


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Location.model_validate({"id": "fenmoor", "name": "Fenmoor", "safeish": True})


def test_ids_are_kebab_case() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        Location.model_validate({"id": "trollBridge", "name": "The Old Bridge"})


def test_references_may_be_qualified() -> None:
    entity = Entity.model_validate(
        {"id": "gorm", "name": "Gorm", "extends": "fantasy.core:bridge-troll"}
    )
    assert entity.extends == "fantasy.core:bridge-troll"


def test_authored_output_omits_defaults() -> None:
    scene = Scene.model_validate({"id": "quiet", "say": ["Nothing happens."]})
    assert scene.authored() == {"id": "quiet", "say": ["Nothing happens."]}


# ── Conditions ────────────────────────────────────────────────────────────────


def test_condition_unwraps_its_tag_and_body() -> None:
    condition = Condition.model_validate({"hasItem": {"item": "gold", "qty": 10}})
    assert condition.tag == "hasItem"
    assert condition.authored() == {"hasItem": {"item": "gold", "qty": 10}}


def test_unknown_condition_suggests_a_correction() -> None:
    with pytest.raises(ValidationError, match="unknown condition `hasitem`"):
        Condition.model_validate({"hasitem": {"item": "gold"}})


def test_a_condition_is_one_question() -> None:
    with pytest.raises(ValidationError, match="single-key mapping"):
        Condition.model_validate({"hasItem": {"item": "gold"}, "chance": 0.5})


@pytest.mark.parametrize(
    ("authored", "tag"),
    [
        ({"chance": 0.15}, "chance"),
        ({"weather": ["rain", "storm"]}, "weather"),
        ({"dayPart": ["night"]}, "dayPart"),
        ({"questComplete": "the-kings-summons"}, "questComplete"),
        ({"expr": "world.day > 7"}, "expr"),
        ({"not": {"weather": ["blizzard"]}}, "not"),
    ],
)
def test_condition_shorthands_round_trip(authored: dict[str, object], tag: str) -> None:
    condition = Condition.model_validate(authored)
    assert condition.tag == tag
    assert condition.authored() == authored


def test_expressions_are_parsed_when_content_loads() -> None:
    condition = Condition.model_validate({"expr": "world.day > 7"})
    expression = condition.payload.expression  # type: ignore[attr-defined]
    assert isinstance(expression, Expression)
    assert expression.references == ("world.day",)


def test_a_broken_expression_fails_at_load_time() -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate({"expr": "world.day > "})


def test_a_lone_condition_is_accepted_where_a_list_is_expected() -> None:
    scene = Scene.model_validate({"id": "s", "when": {"dayPart": ["night"]}})
    assert scene.when is not None
    assert len(scene.when) == 1


# ── Effects ───────────────────────────────────────────────────────────────────


def test_effect_values_may_be_expressions() -> None:
    effect = Effect.model_validate(
        {"setStat": {"stat": "hitpoints", "value": {"expr": "player.pools.hitpoints"}}}
    )
    assert isinstance(effect.payload.value, Expression)  # type: ignore[attr-defined]


def test_unknown_effect_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown effect `teleport`"):
        Effect.model_validate({"teleport": {"to": "fenmoor"}})


def test_a_single_opponent_needs_no_list() -> None:
    effect = Effect.model_validate({"startCombat": {"against": "gorm"}})
    assert effect.payload.against == ("gorm",)  # type: ignore[attr-defined]


def test_a_modifier_must_modify_something() -> None:
    with pytest.raises(ValidationError, match="needs `add`, `mult`, or both"):
        Effect.model_validate({"applyModifier": {"stat": "speed", "ticks": 6}})


# ── Entities ──────────────────────────────────────────────────────────────────


def test_kind_blocks_must_match_the_kind() -> None:
    with pytest.raises(ValidationError, match="belongs to `kind: item`"):
        Entity.model_validate(
            {"id": "well", "kind": "fixture", "name": "Well", "item": {"weight": 1}}
        )


def test_a_portal_needs_its_route() -> None:
    with pytest.raises(ValidationError, match="no `portal:` block"):
        Entity.model_validate({"id": "gate", "kind": "portal", "name": "The Gate"})


def test_only_an_actor_can_be_playable() -> None:
    with pytest.raises(ValidationError, match="not `kind: actor`"):
        Entity.model_validate(
            {"id": "hook", "kind": "item", "name": "Hook", "playable": True}
        )


def test_a_stat_range_must_be_satisfiable() -> None:
    with pytest.raises(ValidationError, match="above max"):
        Stat.model_validate({"base": 10, "min": 50, "max": 20})


# ── Scenes and locations ──────────────────────────────────────────────────────


def test_a_scene_either_jumps_or_offers_a_choice() -> None:
    with pytest.raises(ValidationError, match="both `goto` and `choices`"):
        Scene.model_validate(
            {
                "id": "fork",
                "goto": "somewhere",
                "choices": [{"prompt": "Stay", "goto": "here"}],
            }
        )


def test_a_choice_must_lead_somewhere() -> None:
    with pytest.raises(ValidationError, match="needs `goto`, `effects`, or both"):
        Scene.model_validate({"id": "s", "choices": [{"prompt": "Do nothing"}]})


def test_a_bare_string_is_a_description() -> None:
    location = Location.model_validate(
        {"id": "fenmoor", "name": "Fenmoor", "description": "Six houses and a well."}
    )
    assert location.description is not None
    assert location.description[0].text == "Six houses and a well."
    assert location.description[0].when is None


def test_discovery_follows_visibility_unless_stated() -> None:
    hidden = Location(id="dark-mountain", name="The Dark Mountain", visible=False)
    assert hidden.starts_discovered is False

    known = Location(
        id="hagans-castle", name="Hagan's Castle", visible=False, discovered=True
    )
    assert known.starts_discovered is True


# ── Packs ─────────────────────────────────────────────────────────────────────


def test_a_pack_declares_a_version_range_for_its_dependencies() -> None:
    pack = Pack.model_validate(
        {
            "id": "peasants-quest",
            "name": "A Peasant's Quest",
            "version": "0.1.0",
            "kind": "game",
            "maceVersion": "^0.1",
            "requires": [{"id": "fantasy.core", "version": "^0.3"}],
        }
    )
    assert pack.is_game
    assert pack.requires[0].id == "fantasy.core"


def test_a_pack_version_must_be_semver() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        Pack.model_validate(
            {
                "id": "broken",
                "name": "Broken",
                "version": "0.1",
                "kind": "library",
                "maceVersion": "^0.1",
            }
        )
