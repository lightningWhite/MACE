"""Validating a loaded library: what breaks, what smells, and what to say.

The loader's question is "can this be built". These are the checks that answer
"is it any good" — a reference pointing at nothing, a scene no path reaches, a
protagonist who cannot be played.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack, write_pack
from mace.content import Severity, load_library, validate_library, validate_paths
from mace.content.validation import references
from mace.model import Entity, Scene


def playable_game(**overrides: Any) -> dict[str, Any]:
    """A minimal game manifest that validates cleanly.

    Parameters
    ----------
    **overrides
        Fields to change on the `game:` mapping.

    Returns
    -------
    dict
        A content document with a `game:` key.
    """
    game: dict[str, Any] = {
        "name": "A Test",
        "player": {"entity": "hero", "startLocation": "home"},
        "winConditions": [{"atLocation": {"location": "home"}}],
        **overrides,
    }
    return {"game": game}


def world(**overrides: Any) -> dict[str, Any]:
    """A protagonist and somewhere to stand.

    Parameters
    ----------
    **overrides
        Extra collections to include.

    Returns
    -------
    dict
        A content document.
    """
    document: dict[str, Any] = {
        "entities": [
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 20, "max": 20},
                    "stamina": {"base": 10, "max": 10},
                },
            }
        ],
        "locations": [{"id": "home", "name": "Home"}],
    }
    document.update(overrides)
    return document


# ── The reference walker ──────────────────────────────────────────────────────


def test_references_are_found_wherever_they_are_nested() -> None:
    """Including inside an effect's payload, which is where most of them live."""
    scene = Scene.model_validate(
        {
            "id": "s",
            "effects": [
                {"giveItem": {"item": "gold", "qty": 2}},
                {"move": {"to": "hagans-castle"}},
            ],
            "choices": [{"prompt": "on", "goto": "next-scene"}],
            "else": "fallback",
        }
    )
    found = {(f.reference, f.collection) for f in references(scene)}
    assert ("gold", "entities") in found
    assert ("hagans-castle", "locations") in found
    assert ("next-scene", "scenes") in found
    assert ("fallback", "scenes") in found
    assert ("player", "entities") in found, "the default actor is still a reference"


def test_references_are_found_in_mapping_keys_and_values() -> None:
    entity = Entity.model_validate(
        {
            "id": "hero",
            "kind": "actor",
            "name": "Hero",
            "skills": {"reaping-hook": 15},
            "equipment": {"mainHand": "reaping-hook"},
        }
    )
    found = [f for f in references(entity) if f.collection == "entities"]
    assert [f.reference for f in found].count("reaping-hook") == 2
    assert "mainHand" not in [f.reference for f in found], "a slot is not a reference"


# ── Errors ────────────────────────────────────────────────────────────────────


def test_a_reference_to_nothing_is_an_error(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "broken",
        files={
            "a.yml": {
                "locations": [
                    {"id": "home", "name": "Home", "onArrive": "no-such-scene"}
                ]
            }
        },
    )
    report = validate_paths(tmp_path / "broken")
    assert not report.ok
    problem = report.errors[0]
    assert problem.object_id == "home"
    assert problem.field == "onArrive"
    assert "no-such-scene" in problem.message


def test_the_player_alias_is_not_looked_up_as_an_entity(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "aliased",
        files={
            "a.yml": {
                "scenes": [
                    {
                        "id": "rest",
                        "say": ["You rest."],
                        "effects": [
                            {
                                "adjustStat": {
                                    "actor": "player",
                                    "stat": "hp",
                                    "delta": 1,
                                }
                            }
                        ],
                    }
                ]
            }
        },
    )
    assert validate_paths(tmp_path / "aliased").ok


def test_an_entity_may_not_be_called_player(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "collision",
        files={"a.yml": {"entities": [{"id": "player", "name": "You"}]}},
    )
    report = validate_paths(tmp_path / "collision")
    assert any("reserved" in problem.message for problem in report.errors)


def test_the_protagonist_must_be_playable(tmp_path: Path) -> None:
    document = world()
    document["entities"][0]["playable"] = False
    write_pack(
        tmp_path,
        "unplayable",
        kind="game",
        files={"world.yml": document, "game.yml": playable_game()},
    )
    report = validate_paths(tmp_path / "unplayable")
    assert any("playable: true" in problem.message for problem in report.errors)


def test_the_vital_pool_must_exist_on_the_protagonist(tmp_path: Path) -> None:
    document = world()
    document["entities"][0]["stats"] = {"stamina": {"base": 10, "max": 10}}
    write_pack(
        tmp_path,
        "poolless",
        kind="game",
        files={"world.yml": document, "game.yml": playable_game()},
    )
    report = validate_paths(tmp_path / "poolless")
    assert any("vitalPool" in (problem.field or "") for problem in report.errors)


def test_a_load_failure_is_reported_rather_than_raised(tmp_path: Path) -> None:
    write_pack(tmp_path, "needy", requires=["absent"])
    report = validate_paths(tmp_path / "needy")
    assert not report.ok
    assert "absent" in report.errors[0].message


# ── Warnings and notes ────────────────────────────────────────────────────────


def test_an_unreachable_scene_is_a_warning(tmp_path: Path) -> None:
    """Only in a game pack — a library's scenes are reached from elsewhere."""
    game_pack(
        tmp_path,
        pack_id="orphan",
        world={
            "scenes": [
                {"id": "reachable", "say": ["Hello."]},
                {"id": "lonely", "say": ["Nobody comes here."]},
            ],
            "locations": [
                {"id": "home", "name": "Home", "onArrive": "reachable"},
                {"id": "castle", "name": "The Castle"},
            ],
        },
    )
    report = validate_paths(tmp_path / "orphan")
    unreachable = [p for p in report.warnings if p.object_id == "lonely"]
    assert unreachable and "not reached" in unreachable[0].message
    assert not [p for p in report.warnings if p.object_id == "reachable"]


def test_a_scene_reaching_only_itself_is_still_unreachable(tmp_path: Path) -> None:
    game_pack(
        tmp_path,
        pack_id="selfish",
        world={"scenes": [{"id": "loop", "say": ["Again."], "else": "loop"}]},
    )
    report = validate_paths(tmp_path / "selfish")
    assert [p for p in report.warnings if p.object_id == "loop"]


def test_a_quest_nothing_starts_is_a_warning(tmp_path: Path) -> None:
    document = world(
        quests=[
            {
                "id": "forgotten",
                "name": "Forgotten",
                "stages": [
                    {
                        "id": "one",
                        "journal": "Do the thing.",
                        "complete": [{"atLocation": {"location": "home"}}],
                    }
                ],
            }
        ]
    )
    write_pack(
        tmp_path,
        "questless",
        kind="game",
        files={"world.yml": document, "game.yml": playable_game()},
    )
    report = validate_paths(tmp_path / "questless")
    assert any(p.object_id == "forgotten" for p in report.warnings)


def test_a_scene_that_does_nothing_is_a_warning(tmp_path: Path) -> None:
    write_pack(tmp_path, "empty", files={"a.yml": {"scenes": [{"id": "nothing"}]}})
    report = validate_paths(tmp_path / "empty")
    assert any("changes nothing" in p.message for p in report.warnings)


def test_a_dangerous_road_with_no_encounters_is_a_note(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "quiet-road",
        files={
            "a.yml": {
                "locations": [
                    {"id": "here", "name": "Here", "exits": [{"to": "there"}]},
                    {"id": "there", "name": "There", "exits": [{"to": "here"}]},
                ],
                "routes": [
                    {
                        "id": "road",
                        "from": "here",
                        "to": "there",
                        "ticks": 3,
                        "dangerLevel": 7,
                    }
                ],
            }
        },
    )
    report = validate_paths(tmp_path / "quiet-road")
    assert any(p.object_id == "road" for p in report.notes)


# ── Reporting ─────────────────────────────────────────────────────────────────


def test_a_clean_pack_reports_nothing(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "tidy",
        kind="game",
        files={
            "world.yml": world(
                locations=[
                    {"id": "home", "name": "Home", "onArrive": "wake-up"},
                ],
                scenes=[{"id": "wake-up", "say": ["You wake."]}],
            ),
            "game.yml": playable_game(),
        },
    )
    report = validate_paths(tmp_path / "tidy")
    assert report.ok, report.format()
    assert not report.warnings, report.format()


def test_problems_say_where_they_are(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "located",
        files={
            "a.yml": {
                "locations": [{"id": "home", "name": "Home", "onArrive": "missing"}]
            }
        },
    )
    rendered = str(validate_paths(tmp_path / "located").errors[0])
    assert rendered.startswith("error")
    assert "located → locations/home.onArrive" in rendered


def test_the_summary_counts_every_severity(tmp_path: Path) -> None:
    write_pack(tmp_path, "mixed", files={"a.yml": {"scenes": [{"id": "nothing"}]}})
    report = validate_paths(tmp_path / "mixed")
    assert "0 errors" in report.summary()
    assert report.ok


def test_validate_library_accepts_an_already_loaded_library(tmp_path: Path) -> None:
    write_pack(tmp_path, "loaded", files={"a.yml": {"scenes": [{"id": "nothing"}]}})
    library = load_library(tmp_path / "loaded")
    assert validate_library(library).warnings


def test_errors_only_hides_the_rest(tmp_path: Path) -> None:
    write_pack(tmp_path, "noisy", files={"a.yml": {"scenes": [{"id": "nothing"}]}})
    report = validate_paths(tmp_path / "noisy")
    assert "changes nothing" not in report.format(include=Severity.ERROR)
    assert "changes nothing" in report.format()


# ── Keeping the reference map honest ──────────────────────────────────────────


def reference_fields() -> list[tuple[str, str, bool]]:
    """Every model field that holds a content reference.

    Returns
    -------
    list of (str, str, bool)
        Model name, field name, and whether the field says what it points at.
    """
    from typing import get_args

    from pydantic import StringConstraints

    from mace.content.validation import _is_annotated, _marker_of
    from mace.model.base import REF_PATTERN, ContentModel, Reference

    def every_model(root: type[ContentModel]) -> set[type[ContentModel]]:
        found = {root}
        for subclass in root.__subclasses__():
            found |= every_model(subclass)
        return found

    def is_reference(annotation: Any, depth: int = 0) -> bool:
        if depth > 6:
            return False
        for item in getattr(annotation, "__metadata__", ()):
            if (
                isinstance(item, StringConstraints)
                and item.pattern == f"^{REF_PATTERN}$"
            ):
                return True
        return any(is_reference(arg, depth + 1) for arg in get_args(annotation))

    def is_targeted(annotation: Any, depth: int = 0) -> bool:
        if depth > 6:
            return False
        if _is_annotated(annotation) and _marker_of(annotation) is not None:
            return True
        return any(is_targeted(arg, depth + 1) for arg in get_args(annotation))

    fields = []
    for model in sorted(every_model(ContentModel), key=lambda m: m.__name__):
        for name, field in model.model_fields.items():
            targeted = any(isinstance(m, Reference) for m in field.metadata)
            constrained = any(
                isinstance(m, StringConstraints) and m.pattern == f"^{REF_PATTERN}$"
                for m in field.metadata
            )
            if constrained or is_reference(field.annotation):
                fields.append(
                    (model.__name__, name, targeted or is_targeted(field.annotation))
                )
    return fields


#: Reference fields that deliberately say nothing about what they point at,
#: because no model covers that collection yet. Each disappears when its phase
#: lands — see docs/12-roadmap.md.
UNTARGETED_REFERENCES = {
    ("CombatAssignment", "profile"),  # phase 3 — combat profiles
    ("ItemProps", "moves"),  # phase 3 — moves
    ("Location", "biome"),  # phase 2 — biomes
    ("Region", "biome"),  # phase 2 — biomes
    ("Region", "encounters"),  # phase 2 — encounter tables
    ("Location", "encounters"),  # phase 2 — encounter tables
    ("Route", "terrain"),  # phase 2 — terrain
    ("Route", "encounters"),  # phase 2 — encounter tables
    ("Waypoint", "encounters"),  # phase 2 — encounter tables
    ("PlayerSetup", "backgrounds"),  # phase 4 — backgrounds
}


def test_every_reference_field_says_what_it_points_at() -> None:
    """A new reference field must be targeted, or listed as not yet checkable.

    Without this the validator quietly stops checking whatever gets added next,
    and nothing fails.
    """
    untargeted = {
        (model, field) for model, field, targeted in reference_fields() if not targeted
    }
    assert untargeted == UNTARGETED_REFERENCES, (
        "reference fields changed: "
        f"newly untargeted {sorted(untargeted - UNTARGETED_REFERENCES)}, "
        f"now targeted {sorted(UNTARGETED_REFERENCES - untargeted)}"
    )
