"""The engine as a browser tab drives it, and the bundle that gets it there.

The claim being tested is ADR-0005's: one implementation, three deployments.
So most of what follows compares this front-end's answers to the service's,
because a client cannot tell them apart and neither should a bug report.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import game_pack, write_pack
from mace.api.app import create_app
from mace.browser import MANIFEST, Runtime, unpack
from mace.cli.bundle import bundle
from mace.content import ContentError, load_library
from test_session_view import WORLD


@pytest.fixture
def packed(tmp_path: Path) -> Path:
    """A bundle of a small game with a map, a quest and a pack to carry.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    Path
        The zip.
    """
    game_pack(tmp_path / "packs", game={"quests": ["the-summons"]}, world=WORLD)
    written, _ = bundle([tmp_path / "packs"], tmp_path / "bundle.zip")
    return written


@pytest.fixture
def runtime(packed: Path, tmp_path: Path) -> Runtime:
    """A runtime with that bundle installed.

    Parameters
    ----------
    packed : Path
        The bundle.
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    Runtime
        Ready to open a game.
    """
    return Runtime.install(packed.read_bytes(), into=tmp_path / "unpacked")


# ── The bundle ────────────────────────────────────────────────────────────────


def test_a_bundle_carries_the_engine_and_the_worlds(packed: Path) -> None:
    inside = zipfile.ZipFile(packed).namelist()
    assert "mace/engine/step.py" in inside
    assert "mace/session/view.py" in inside
    assert any(name.startswith("packs/tiny/") for name in inside)


def test_a_bundle_says_what_is_in_it(packed: Path) -> None:
    manifest = json.loads(zipfile.ZipFile(packed).read(MANIFEST))
    assert manifest["packs"] == ["packs/tiny"]
    assert manifest["version"]


def test_a_bundle_ships_no_bytecode(packed: Path) -> None:
    """A `.pyc` for the wrong interpreter is a confusing import error."""
    inside = zipfile.ZipFile(packed).namelist()
    assert not [name for name in inside if "__pycache__" in name]
    assert not [name for name in inside if name.endswith(".pyc")]


def test_bundling_nothing_says_where_it_looked(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ContentError, match="no packs found"):
        bundle([empty], tmp_path / "out.zip")


def test_a_bundle_that_cannot_be_written_says_so(packed: Path, tmp_path: Path) -> None:
    blocked = packed / "inside-a-file.zip"
    with pytest.raises(ContentError, match="could not write"):
        bundle([tmp_path / "packs"], blocked)


def test_something_that_is_not_a_bundle_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="not a MACE bundle"):
        unpack(b"this is a diary", tmp_path / "out")


def test_a_zip_with_no_manifest_is_not_a_bundle(tmp_path: Path) -> None:
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(ContentError, match="not a MACE bundle"):
        unpack(path.read_bytes(), tmp_path / "out")


def test_loading_from_nowhere_says_so(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="no MACE bundle"):
        Runtime.load(tmp_path / "nothing")


# ── The same answers as the service ───────────────────────────────────────────


def served(tmp_path: Path) -> TestClient:
    """The HTTP service over the same content, to compare against.

    Parameters
    ----------
    tmp_path : Path
        Where the pack was written.

    Returns
    -------
    TestClient
        The service.
    """
    return TestClient(create_app(library=load_library(tmp_path / "packs")))


def test_it_lists_the_games_the_service_lists(runtime: Runtime, tmp_path: Path) -> None:
    assert runtime.games() == served(tmp_path).get("/api/games").json()


def test_it_asks_the_creation_question_the_service_asks(
    runtime: Runtime, tmp_path: Path
) -> None:
    assert runtime.creation("tiny") == (
        served(tmp_path).get("/api/games/tiny/creation").json()
    )


def test_it_opens_the_frame_the_service_opens(runtime: Runtime, tmp_path: Path) -> None:
    """The whole of ADR-0005 in one assertion: same engine, same answer."""
    here = runtime.open({"pack": "tiny"})
    there = served(tmp_path).post("/api/sessions", json={"pack": "tiny"}).json()

    # The session id is the one thing that differs: a tab plays one game and
    # has nothing to address across a network.
    assert here["session"] == "local"
    assert {**here, "session": None} == {**there, "session": None}


def test_it_plays_the_frames_the_service_plays(
    runtime: Runtime, tmp_path: Path
) -> None:
    client = served(tmp_path)
    opened = client.post("/api/sessions", json={"pack": "tiny"}).json()
    runtime.open({"pack": "tiny"})

    action = {"kind": "choose", "prompt": "Travel to The Mill"}
    here = runtime.act(action)
    there = client.post(
        f"/api/sessions/{opened['session']}/actions", json=action
    ).json()
    assert {**here, "session": None} == {**there, "session": None}


def test_it_writes_the_save_the_service_writes(
    runtime: Runtime, tmp_path: Path
) -> None:
    client = served(tmp_path)
    opened = client.post("/api/sessions", json={"pack": "tiny"}).json()
    runtime.open({"pack": "tiny"})

    action = {"kind": "choose", "option": 0}
    runtime.act(action)
    client.post(f"/api/sessions/{opened['session']}/actions", json=action)

    assert (
        runtime.save() == client.get(f"/api/sessions/{opened['session']}/save").json()
    )


def test_a_save_carries_on_in_the_tab_it_was_not_made_in(runtime: Runtime) -> None:
    """The point of ADR-0009: the save is the playthrough, wherever it runs."""
    runtime.open({"pack": "tiny"})
    runtime.act({"kind": "choose", "prompt": "Travel to The Mill"})
    save = runtime.save()

    carried = runtime.open({"save": save})
    assert carried["view"]["atlas"]["here"] == "tiny:mill"
    assert carried["warnings"] == []


# ── One way in ────────────────────────────────────────────────────────────────


def test_every_request_goes_through_one_door(runtime: Runtime) -> None:
    """The dispatch is here so the worker can be glue and nothing else."""
    assert runtime.handle({"type": "games"}) == runtime.games()
    assert runtime.handle({"type": "creation", "pack": "tiny"})["asksAnything"] is False

    opened = runtime.handle({"type": "open", "request": {"pack": "tiny"}})
    assert opened["choices"]
    assert runtime.handle({"type": "look"})["choices"] == opened["choices"]

    acted = runtime.handle({"type": "act", "action": {"kind": "choose", "option": 0}})
    assert acted["view"]["atlas"]["here"] == "tiny:mill"
    assert runtime.handle({"type": "save"})["pack"] == "tiny"


def test_a_request_that_is_not_one_says_what_is(runtime: Runtime) -> None:
    with pytest.raises(ContentError, match="games, creation, open"):
        runtime.handle({"type": "yodel"})


def test_acting_before_opening_says_to_open_something(runtime: Runtime) -> None:
    with pytest.raises(ContentError, match="no game is open"):
        runtime.act({"kind": "look"})


def test_an_action_that_means_nothing_here_is_refused(runtime: Runtime) -> None:
    runtime.open({"pack": "tiny"})
    with pytest.raises(ContentError, match="unknown action"):
        runtime.act({"kind": "yodel"})


def test_a_choice_that_is_not_on_offer_says_what_was(runtime: Runtime) -> None:
    runtime.open({"pack": "tiny"})
    with pytest.raises(ContentError, match="Travel to The Mill"):
        runtime.act({"kind": "choose", "prompt": "Fly to the moon"})


def test_the_settings_a_session_opens_with_reach_it(runtime: Runtime) -> None:
    runtime.open({"pack": "tiny", "seed": "north", "timePressure": 0.5})
    save = runtime.save()
    assert save["seed"] == "north"
    assert save["timePressure"] == 0.5


def test_a_game_with_no_packs_at_all_is_not_a_runtime(tmp_path: Path) -> None:
    write_pack(tmp_path / "packs", "library-only")
    written, _ = bundle([tmp_path / "packs"], tmp_path / "b.zip")
    runtime = Runtime.install(written.read_bytes(), into=tmp_path / "out")
    assert runtime.games() == {"games": []}
    with pytest.raises(ContentError, match="no game packs found"):
        runtime.open()


def test_any_of_these_dicts_goes_over_a_wire(runtime: Runtime) -> None:
    """The worker moves JSON, so everything here has to survive being JSON."""
    runtime.open({"pack": "tiny"})
    for request in (
        {"type": "games"},
        {"type": "creation", "pack": "tiny"},
        {"type": "look"},
        {"type": "save"},
    ):
        body: Any = runtime.handle(request)
        assert json.loads(json.dumps(body)) == body
