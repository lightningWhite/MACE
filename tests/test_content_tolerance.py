"""Loading a pack that is only half-written, which is the normal state of one.

Playing wants a hard stop: content that will not compile cannot be played.
Authoring wants the opposite, and until now could not have it — one misspelled
field on one location aborted the load, so `mace validate` reported that single
error and every other problem in the pack was invisible until it was fixed.
Fixing a world one hidden error at a time is not authoring.

These tests pin both halves: strict still stops, collecting carries on, and
what survives a collecting load is as usable as anything strict would have
produced.
"""

from pathlib import Path
from typing import Any

import pytest
from conftest import write_pack

from mace.content import ContentError, load_library, validate_paths
from mace.content.loader import load_best_effort
from mace.content.tolerance import collecting


def broken_pack(root: Path, **files: Any) -> Path:
    """A pack with one good location and one problem, plus whatever else.

    Parameters
    ----------
    root : Path
        Where to write it.
    **files
        Extra files, filename stem to document.

    Returns
    -------
    Path
        The pack directory.
    """
    documents: dict[str, Any] = {
        "a.yml": {
            "locations": [
                {"id": "fine", "name": "Fine"},
                {"id": "wrong", "name": "Wrong", "nonsense": True},
            ]
        }
    }
    documents.update({f"{name}.yml": body for name, body in files.items()})
    return write_pack(root, "half-written", files=documents)


def test_a_strict_load_still_stops_at_the_first_problem(tmp_path: Path) -> None:
    """Content that will not compile cannot be played, and should not load."""
    broken_pack(tmp_path)
    with pytest.raises(ContentError, match="Extra inputs are not permitted"):
        load_library(tmp_path / "half-written")


def test_a_collecting_load_keeps_what_built(tmp_path: Path) -> None:
    broken_pack(tmp_path)
    loaded = load_best_effort(tmp_path / "half-written")
    assert sorted(loaded.library.pack("half-written").locations) == ["fine"]
    assert not loaded.ok


def test_a_collecting_load_reports_what_did_not(tmp_path: Path) -> None:
    broken_pack(tmp_path)
    loaded = load_best_effort(tmp_path / "half-written")
    assert [error.object_id for error in loaded.problems] == ["wrong"]


def test_one_bad_object_no_longer_hides_the_rest(tmp_path: Path) -> None:
    """The whole reason this exists, checked end to end through `validate`."""
    broken_pack(
        tmp_path,
        b={
            "locations": [
                {"id": "third", "name": "Third", "exits": [{"to": "nowhere-at-all"}]}
            ]
        },
    )
    report = validate_paths(tmp_path / "half-written")
    assert {problem.object_id for problem in report.errors} == {"wrong", "third"}


def test_every_bad_object_is_reported_not_just_the_first(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "rubble",
        files={
            "a.yml": {
                "locations": [
                    {"id": f"broken-{n}", "name": "Broken", "nonsense": True}
                    for n in range(4)
                ]
            }
        },
    )
    loaded = load_best_effort(tmp_path / "rubble")
    assert len(loaded.problems) == 4


def test_a_child_of_a_broken_parent_says_so(tmp_path: Path) -> None:
    """A consequence, but an honest one — silence would be worse."""
    write_pack(
        tmp_path,
        "lineage",
        files={
            "a.yml": {
                "entities": [
                    {"id": "parent", "name": "Parent", "nonsense": True},
                    {"id": "child", "extends": "parent"},
                ]
            }
        },
    )
    loaded = load_best_effort(tmp_path / "lineage")
    assert {error.object_id for error in loaded.problems} == {"parent", "child"}
    assert any("did not build" in error.message for error in loaded.problems)


def test_a_malformed_file_costs_only_that_file(tmp_path: Path) -> None:
    pack = broken_pack(tmp_path)
    (pack / "junk.yml").write_text("- this is a list, not a mapping\n")
    loaded = load_best_effort(pack)
    assert "fine" in loaded.library.pack("half-written").locations
    assert any("must be a mapping" in error.message for error in loaded.problems)


def test_an_unreadable_file_costs_only_that_file(tmp_path: Path) -> None:
    pack = broken_pack(tmp_path)
    (pack / "junk.yml").write_text("locations: [\n")
    loaded = load_best_effort(pack)
    assert "fine" in loaded.library.pack("half-written").locations
    assert len(loaded.problems) == 2


def test_a_misspelled_collection_costs_only_that_key(tmp_path: Path) -> None:
    pack = broken_pack(tmp_path, b={"entites": [{"id": "typo"}]})
    loaded = load_best_effort(pack)
    assert "fine" in loaded.library.pack("half-written").locations
    assert any("not a content collection" in error.message for error in loaded.problems)


def test_a_definition_with_no_id_costs_only_itself(tmp_path: Path) -> None:
    pack = broken_pack(
        tmp_path, b={"scenes": [{"say": "nameless"}, {"id": "named", "say": "hello"}]}
    )
    loaded = load_best_effort(pack)
    assert sorted(loaded.library.pack("half-written").scenes) == ["named"]


def test_a_repeated_id_keeps_the_first_and_says_so(tmp_path: Path) -> None:
    pack = broken_pack(
        tmp_path,
        b={
            "scenes": [
                {"id": "twice", "say": "first"},
                {"id": "twice", "say": "second"},
            ]
        },
    )
    loaded = load_best_effort(pack)
    scene = loaded.library.pack("half-written").scenes["twice"]
    assert scene.say[0].text == "first"
    assert any("defined twice" in error.message for error in loaded.problems)


def test_a_pack_with_a_broken_manifest_is_skipped_not_fatal(tmp_path: Path) -> None:
    broken_pack(tmp_path)
    (tmp_path / "nonsense").mkdir()
    (tmp_path / "nonsense" / "pack.yml").write_text("id: 'Not A Valid Id'\n")
    loaded = load_best_effort(tmp_path)
    assert "half-written" in loaded.library.by_id
    assert loaded.problems


def test_a_pack_missing_a_dependency_is_left_out(tmp_path: Path) -> None:
    """Loading it anyway would bury the one real problem under its consequences."""
    write_pack(tmp_path, "standalone", files={"a.yml": {}})
    write_pack(tmp_path, "dependent", requires=["not-here"], files={"a.yml": {}})
    loaded = load_best_effort(tmp_path)
    assert sorted(loaded.library.by_id) == ["standalone"]
    assert any("was not found" in error.message for error in loaded.problems)


def test_packs_in_a_cycle_are_left_out(tmp_path: Path) -> None:
    write_pack(tmp_path, "left", requires=["right"], files={"a.yml": {}})
    write_pack(tmp_path, "right", requires=["left"], files={"a.yml": {}})
    loaded = load_best_effort(tmp_path)
    assert loaded.library.by_id == {}
    assert any("in a cycle" in error.message for error in loaded.problems)


def test_a_game_pack_with_no_manifest_still_loads_its_content(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "unfinished",
        kind="game",
        files={"a.yml": {"locations": [{"id": "home", "name": "Home"}]}},
    )
    loaded = load_best_effort(tmp_path / "unfinished")
    assert "home" in loaded.library.pack("unfinished").locations
    assert any("no `game:` manifest" in error.message for error in loaded.problems)


def test_a_clean_pack_collects_nothing(tmp_path: Path) -> None:
    write_pack(
        tmp_path,
        "tidy",
        files={"a.yml": {"locations": [{"id": "home", "name": "Home"}]}},
    )
    loaded = load_best_effort(tmp_path / "tidy")
    assert loaded.ok
    assert loaded.problems == ()


def test_the_shipped_packs_load_cleanly_either_way() -> None:
    packs = Path(__file__).resolve().parent.parent / "packs"
    loaded = load_best_effort(packs)
    assert loaded.ok, [str(error) for error in loaded.problems]


def test_two_collecting_loads_do_not_share_a_problem_list(tmp_path: Path) -> None:
    """A shared tolerance would report the other load's problems."""
    broken_pack(tmp_path)
    first = collecting()
    second = collecting()
    load_library(tmp_path / "half-written", tolerance=first)
    load_library(tmp_path / "half-written", tolerance=second)
    assert len(first.problems) == len(second.problems) == 1
