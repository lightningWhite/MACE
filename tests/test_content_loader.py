"""Loading packs: discovery, dependency order, inheritance, and id resolution.

Every test builds its packs on disk, because the things that break a loader —
a child above its parent in a file, two files claiming one id, a dependency
that isn't there — are all facts about directories rather than about data.
"""

from pathlib import Path

import pytest

from conftest import troll, write_pack
from mace.content import ContentError, Library, load_library

# ── Discovery ─────────────────────────────────────────────────────────────────


def test_a_root_that_is_itself_a_pack_loads_just_that_pack(tmp_path: Path) -> None:
    pack_root = write_pack(tmp_path, "solo")
    library = load_library(pack_root)
    assert [pack.id for pack in library.packs] == ["solo"]


def test_a_root_of_packs_loads_all_of_them(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "one")
    write_pack(tmp_path / "packs" / "nested", "two")
    library = load_library(tmp_path / "packs")
    assert {pack.id for pack in library.packs} == {"one", "two"}


def test_a_missing_root_says_so(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="no such directory"):
        load_library(tmp_path / "nowhere")


def test_content_may_be_organised_however_the_author_likes(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "split",
        files={
            "entities/monsters.yml": {"entities": [troll()]},
            "entities/items.yml": {
                "entities": [{"id": "rope", "kind": "item", "name": "Rope"}]
            },
        },
    )
    library = load_library(tmp_path / "split")
    assert set(library.pack("split").entities) == {"bridge-troll", "rope"}


def test_two_files_may_not_claim_the_same_id(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "clash",
        files={"a.yml": {"entities": [troll()]}, "b.yml": {"entities": [troll()]}},
    )
    with pytest.raises(ContentError, match="defined twice"):
        load_library(tmp_path / "clash")


def test_an_unknown_collection_suggests_the_right_one(tmp_path: Path) -> None:
    write_pack(tmp_path, "typo", files={"a.yml": {"entites": []}})
    with pytest.raises(ContentError, match="did you mean `entities`"):
        load_library(tmp_path / "typo")


def test_collections_no_model_covers_yet_are_kept_as_they_were(tmp_path: Path) -> None:
    """A phase-2 collection must survive a phase-1 load untouched."""
    write_pack(
        tmp_path,
        "weather",
        files={"regions.yml": {"regions": [{"id": "the-lowlands", "elevation": 40}]}},
    )
    library = load_library(tmp_path / "weather")
    assert library.pack("weather").unmodelled["regions"] == (
        {"id": "the-lowlands", "elevation": 40},
    )


# ── Dependency ordering ───────────────────────────────────────────────────────


def test_packs_load_after_what_they_require(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "core")
    write_pack(tmp_path / "packs", "fantasy", requires=["core"])
    write_pack(tmp_path / "packs", "game", kind="library", requires=["fantasy"])
    library = load_library(tmp_path / "packs")
    assert [pack.id for pack in library.packs] == ["core", "fantasy", "game"]


def test_a_missing_dependency_is_named(tmp_path: Path) -> None:
    write_pack(tmp_path, "lonely", requires=["absent"])
    with pytest.raises(ContentError, match="requires `absent`"):
        load_library(tmp_path / "lonely")


def test_a_dependency_cycle_is_reported_as_one(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "a", requires=["b"])
    write_pack(tmp_path / "packs", "b", requires=["a"])
    with pytest.raises(ContentError, match="cycle"):
        load_library(tmp_path / "packs")


def test_two_packs_may_not_share_an_id(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs" / "here", "twin")
    write_pack(tmp_path / "packs" / "there", "twin")
    with pytest.raises(ContentError, match="claimed twice"):
        load_library(tmp_path / "packs")


# ── Inheritance ───────────────────────────────────────────────────────────────


def test_a_child_inherits_what_it_leaves_out(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "inherit",
        files={
            "a.yml": {
                "entities": [
                    troll(),
                    {
                        "id": "gorm",
                        "extends": "bridge-troll",
                        "name": "Gorm",
                        "stats": {"strength": {"base": 85}},
                    },
                ]
            }
        },
    )
    gorm = load_library(tmp_path / "inherit").pack("inherit").entities["gorm"]
    assert gorm.name == "Gorm"
    assert gorm.kind == "actor"
    assert gorm.stats is not None
    assert gorm.stats["strength"].base == 85
    assert gorm.stats["hitpoints"].base == 80, "maps merge deeply"


def test_a_child_may_be_written_above_its_parent(tmp_path: Path) -> None:
    """Order in a file is the author's business, not a load-order constraint."""
    write_pack(
        tmp_path,
        "order",
        files={
            "a.yml": {
                "entities": [
                    {"id": "gorm", "extends": "bridge-troll", "name": "Gorm"},
                    troll(),
                ]
            }
        },
    )
    gorm = load_library(tmp_path / "order").pack("order").entities["gorm"]
    assert gorm.kind == "actor"


def test_lists_replace_unless_told_to_append(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "lists",
        files={
            "a.yml": {
                "entities": [
                    troll(),
                    {"id": "quiet", "extends": "bridge-troll", "tags": ["shy"]},
                    {
                        "id": "named",
                        "extends": "bridge-troll",
                        "tags": ["$append", "quest-giver"],
                    },
                ]
            }
        },
    )
    entities = load_library(tmp_path / "lists").pack("lists").entities
    assert entities["quiet"].tags == ("shy",)
    assert entities["named"].tags == ("monster", "large", "quest-giver")


def test_remove_drops_an_inherited_key(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "removal",
        files={
            "a.yml": {
                "entities": [
                    troll(),
                    {"id": "plain", "extends": "bridge-troll", "$remove": ["tags"]},
                ]
            }
        },
    )
    plain = load_library(tmp_path / "removal").pack("removal").entities["plain"]
    assert plain.tags == ()


def test_a_sentinel_without_a_parent_is_a_mistake(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "stray",
        files={
            "a.yml": {
                "entities": [{"id": "gorm", "name": "Gorm", "tags": ["$append", "x"]}]
            }
        },
    )
    with pytest.raises(ContentError, match="extends nothing"):
        load_library(tmp_path / "stray")


def test_inheritance_may_cross_packs(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "fantasy", files={"a.yml": {"entities": [troll()]}})
    write_pack(
        tmp_path / "packs",
        "quest",
        requires=["fantasy"],
        files={
            "a.yml": {
                "entities": [
                    {
                        "id": "gorm",
                        "extends": "fantasy:bridge-troll",
                        "name": "Gorm",
                        "tags": ["$append", "named"],
                    }
                ]
            }
        },
    )
    gorm = load_library(tmp_path / "packs").pack("quest").entities["gorm"]
    assert gorm.tags == ("monster", "large", "named")
    assert gorm.stats is not None and gorm.stats["hitpoints"].base == 80


def test_a_pack_may_only_extend_what_it_requires(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "fantasy", files={"a.yml": {"entities": [troll()]}})
    write_pack(
        tmp_path / "packs",
        "rude",
        files={
            "a.yml": {
                "entities": [
                    {"id": "gorm", "extends": "fantasy:bridge-troll", "name": "Gorm"}
                ]
            }
        },
    )
    with pytest.raises(ContentError, match="does not `require`"):
        load_library(tmp_path / "packs")


def test_an_extends_cycle_is_caught(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "loop",
        files={
            "a.yml": {
                "entities": [
                    {"id": "a", "extends": "b", "name": "A"},
                    {"id": "b", "extends": "a", "name": "B"},
                ]
            }
        },
    )
    with pytest.raises(ContentError, match="cycle"):
        load_library(tmp_path / "loop")


# ── Validation reporting ──────────────────────────────────────────────────────


def test_an_invalid_object_is_reported_with_its_file_and_id(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "broken",
        files={
            "beasts.yml": {"entities": [{"id": "gorm", "name": "Gorm", "kind": "og"}]}
        },
    )
    with pytest.raises(ContentError) as caught:
        load_library(tmp_path / "broken")
    message = str(caught.value)
    assert "beasts.yml" in message
    assert "entities/gorm" in message


def test_a_game_pack_needs_a_game_manifest(tmp_path: Path) -> None:
    write_pack(tmp_path, "gameless", kind="game")
    with pytest.raises(ContentError, match="no `game:` manifest"):
        load_library(tmp_path / "gameless")


def test_a_game_manifest_is_loaded(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "playable",
        kind="game",
        files={
            "game.yml": {
                "game": {
                    "name": "A Test",
                    "player": {"entity": "hero", "startLocation": "home"},
                }
            },
            "world.yml": {
                "entities": [{"id": "hero", "kind": "actor", "name": "Hero"}],
                "locations": [{"id": "home", "name": "Home"}],
            },
        },
    )
    pack = load_library(tmp_path / "playable").pack("playable")
    assert pack.game is not None and pack.game.name == "A Test"
    assert pack.manifest.is_game


# ── Id resolution ─────────────────────────────────────────────────────────────


@pytest.fixture
def two_packs(tmp_path: Path) -> Library:
    """A game pack over a library pack, each with an entity of its own.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    Library
        The loaded packs.
    """
    write_pack(tmp_path / "packs", "fantasy", files={"a.yml": {"entities": [troll()]}})
    write_pack(
        tmp_path / "packs",
        "quest",
        requires=["fantasy"],
        files={
            "a.yml": {"entities": [{"id": "letholin", "kind": "actor", "name": "L"}]}
        },
    )
    return load_library(tmp_path / "packs")


def test_a_bare_reference_finds_its_own_pack_first(two_packs: Library) -> None:
    assert two_packs.resolve("letholin", "entities", within="quest") == "quest:letholin"


def test_a_bare_reference_falls_through_to_dependencies(two_packs: Library) -> None:
    assert (
        two_packs.resolve("bridge-troll", "entities", within="quest")
        == "fantasy:bridge-troll"
    )


def test_a_qualified_reference_is_checked_not_trusted(two_packs: Library) -> None:
    assert (
        two_packs.resolve("fantasy:bridge-troll", "entities", within="quest")
        == "fantasy:bridge-troll"
    )
    with pytest.raises(ContentError, match="not a entity in pack `fantasy`"):
        two_packs.resolve("fantasy:letholin", "entities", within="quest")


def test_an_unresolvable_reference_names_where_it_looked(two_packs: Library) -> None:
    with pytest.raises(ContentError, match="nothing named `absent`"):
        two_packs.resolve("absent", "entities", within="quest")


def test_a_dependency_cannot_see_its_dependents(two_packs: Library) -> None:
    with pytest.raises(ContentError, match="no dependencies"):
        two_packs.resolve("letholin", "entities", within="fantasy")


def test_find_returns_the_definition(two_packs: Library) -> None:
    found = two_packs.find("bridge-troll", "entities", within="quest")
    assert found.name == "Bridge Troll"  # type: ignore[attr-defined]


def test_an_ambiguous_bare_reference_is_an_error_not_a_guess(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "north", files={"a.yml": {"entities": [troll()]}})
    write_pack(tmp_path / "packs", "south", files={"a.yml": {"entities": [troll()]}})
    write_pack(tmp_path / "packs", "both", requires=["north", "south"])
    library = load_library(tmp_path / "packs")
    with pytest.raises(ContentError, match="ambiguous"):
        library.resolve("bridge-troll", "entities", within="both")
