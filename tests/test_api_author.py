"""The authoring service: the wizard over HTTP.

The routes hold no questions, so what is worth testing is the contract — one
frame shape for every reply, a picker that arrives with its options on it, an
answer that lands in the author's own file, and the fact that a session
service without `authoring` has none of this at all.

That last one is the point of `test_a_session_service_has_no_authoring_routes`:
these routes write to somebody's disk, and the service that serves a game to
the world must not grow that ability by accident.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import write_pack
from mace.api.app import create_app
from mace.api.author import author_routes
from mace.content import load_library
from mace.wizard.studio import Desk, Studio

PACK: dict[str, Any] = {
    "locations.yml": {
        "locations": [
            {"id": "home", "name": "Home", "exits": [{"to": "castle"}]},
            {"id": "castle", "name": "The Castle"},
        ]
    },
    "people.yml": {
        "entities": [
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 10, "max": 10},
                    "stamina": {"base": 10, "max": 10},
                },
            },
            {"id": "gold", "kind": "item", "name": "Gold"},
        ]
    },
    "game.yml": {
        "game": {
            "name": "Tiny",
            "player": {"entity": "hero", "startLocation": "home"},
            "winConditions": [{"atLocation": {"location": "castle"}}],
        }
    },
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return write_pack(tmp_path / "packs" / "tiny", "tiny", kind="game", files=PACK)


@pytest.fixture
def client(root: Path) -> TestClient:
    """A service with one pack open for editing.

    Parameters
    ----------
    root : Path
        The pack directory.

    Returns
    -------
    TestClient
        The client.
    """
    return TestClient(
        create_app(
            library=load_library(root.parent),
            authoring=Studio.open(root, root.parent),
        )
    )


def got(client: TestClient, path: str) -> dict[str, Any]:
    """GET one path and insist it worked.

    Parameters
    ----------
    client : TestClient
        The service.
    path : str
        The path.

    Returns
    -------
    dict
        The body.
    """
    response = client.get(path)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# ── The frame ─────────────────────────────────────────────────────────────────


def test_the_desk_is_what_you_get_for_asking_for_nothing(client: TestClient) -> None:
    frame = got(client, "/api/author")
    assert frame["pack"]["id"] == "tiny"
    assert frame["desk"]["name"] == "Tiny"
    assert frame["screen"] is None


def test_every_reply_carries_the_desk(client: TestClient) -> None:
    """A problem count that only moved when you asked for it would be a lie."""
    for path in ("/api/author", "/api/author/sections/world"):
        assert got(client, path)["desk"]["tasks"]


def test_a_section_lists_what_it_holds(client: TestClient) -> None:
    screen = got(client, "/api/author/sections/world")["screen"]
    assert {one["id"] for one in screen["objects"]} == {"home", "castle"}


def test_a_section_nobody_has_is_a_404(client: TestClient) -> None:
    assert client.get("/api/author/sections/dragons").status_code == 404


def test_an_object_comes_with_its_steps(client: TestClient) -> None:
    screen = got(client, "/api/author/objects/locations/home")["screen"]
    name = next(one for one in screen["steps"] if one["id"] == "location.name")
    assert name["value"] == "Home"


def test_the_game_manifest_needs_no_object_id(client: TestClient) -> None:
    screen = got(client, "/api/author/objects/game")["screen"]
    assert screen["id"] is None
    assert screen["steps"]


def test_an_object_nobody_has_is_a_404(client: TestClient) -> None:
    assert client.get("/api/author/objects/locations/nowhere").status_code == 404


def test_a_picker_arrives_with_its_options_on_it(client: TestClient) -> None:
    """The whole reason the wire exists — a browser cannot ask the catalog."""
    screen = got(client, "/api/author/objects/locations/home")["screen"]
    entities = next(one for one in screen["steps"] if one["id"] == "location.entities")
    assert {one["value"] for one in entities["field"]["options"]} >= {"hero", "gold"}


# ── Answering ─────────────────────────────────────────────────────────────────


def test_an_answer_comes_back_as_the_step_and_the_desk(client: TestClient) -> None:
    response = client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.name",
            "value": "The Hearth",
        },
    )
    assert response.status_code == 200, response.text
    frame = response.json()
    assert frame["screen"]["value"] == "The Hearth"
    assert frame["dirty"] == ["locations.yml"]


def test_an_answer_reaches_the_file_when_it_is_saved(
    client: TestClient, root: Path
) -> None:
    client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.name",
            "value": "The Hearth",
        },
    )
    saved = client.post("/api/author/save")
    assert saved.status_code == 200, saved.text
    assert saved.json()["screen"] == {"saved": ["locations.yml"]}
    assert "The Hearth" in (root / "locations.yml").read_text()
    assert saved.json()["dirty"] == []


def test_answering_a_step_nobody_has_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/api/author/answers",
        json={"collection": "locations", "object": "home", "step": "location.vibes"},
    )
    assert response.status_code == 404


def test_answering_an_object_nobody_has_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "nowhere",
            "step": "location.name",
            "value": "X",
        },
    )
    assert response.status_code == 400


# ── Making and unmaking ───────────────────────────────────────────────────────


def test_creating_takes_a_name_and_opens_what_it_made(client: TestClient) -> None:
    response = client.post("/api/author/objects/locations", json={"name": "The Moor"})
    assert response.status_code == 201, response.text
    screen = response.json()["screen"]
    assert screen["id"] == "the-moor"
    assert screen["label"] == "The Moor"


def test_creating_in_a_section_takes_the_fields_that_section_fixes(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/author/objects/entities", json={"name": "Lantern", "section": "items"}
    )
    assert response.status_code == 201, response.text
    screen = response.json()["screen"]
    kind = next(one for one in screen["steps"] if one["id"] == "entity.kind")
    assert kind["value"] == "item"


def test_creating_something_already_there_is_a_400(client: TestClient) -> None:
    response = client.post("/api/author/objects/locations", json={"name": "Home"})
    assert response.status_code == 400


def test_creating_where_nothing_authors_is_a_404(client: TestClient) -> None:
    response = client.post("/api/author/objects/calendars", json={"name": "Wet"})
    assert response.status_code == 404


def test_deleting_says_whether_there_was_one(client: TestClient) -> None:
    assert client.delete("/api/author/objects/locations/castle").status_code == 200
    assert client.delete("/api/author/objects/locations/castle").status_code == 404


def test_deleting_what_things_point_at_is_allowed_and_reported(
    client: TestClient,
) -> None:
    client.delete("/api/author/objects/locations/castle")
    problems = got(client, "/api/author/problems")["problems"]
    assert any("castle" in one["message"] for one in problems)


# ── The cascade ───────────────────────────────────────────────────────────────


def test_the_vocabulary_carries_this_packs_options(client: TestClient) -> None:
    described = got(client, "/api/author/vocabulary")
    has_item = next(one for one in described["conditions"] if one["tag"] == "hasItem")
    which = has_item["asks"][0]
    assert {one["value"] for one in which["field"]["options"]} == {"gold"}


def test_building_returns_content_and_english(client: TestClient) -> None:
    response = client.post(
        "/api/author/build",
        json={"kind": "conditions", "tag": "hasItem", "answers": {"item": "gold"}},
    )
    assert response.status_code == 200, response.text
    built = response.json()
    assert built["authored"] == {"hasItem": {"item": "gold"}}
    assert "Gold" in built["said"]


def test_building_something_nothing_makes_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/api/author/build", json={"kind": "conditions", "tag": "vibeCheck"}
    )
    assert response.status_code == 404


def test_building_nonsense_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/api/author/build",
        json={"kind": "conditions", "tag": "hasItem", "answers": {"qty": 3}},
    )
    assert response.status_code == 400


# ── What the play service must never grow ─────────────────────────────────────


def test_a_session_service_has_no_authoring_routes(root: Path) -> None:
    """These routes write to somebody's disk. Off unless asked for."""
    plain = TestClient(create_app(library=load_library(root.parent)))
    assert plain.get("/api/author").status_code == 404
    assert plain.post("/api/author/save").status_code == 404


def test_an_authoring_service_still_plays(client: TestClient) -> None:
    """One process, two front-ends: playtest-from-anywhere needs both."""
    opened = client.post("/api/sessions", json={"pack": "tiny"})
    assert opened.status_code == 201, opened.text
    assert opened.json()["playing"] is True


# ── The map ───────────────────────────────────────────────────────────────────


def test_the_map_is_what_the_author_has_drawn(client: TestClient) -> None:
    drawn = got(client, "/api/author/map")
    assert {one["id"] for one in drawn["places"]} == {"home", "castle"}
    assert drawn["roads"] == []


def test_drawing_a_road_takes_one_call(client: TestClient) -> None:
    """Drawing a road is one authoring intention, so it is one request."""
    response = client.post(
        "/api/author/roads",
        json={"origin": "home", "destination": "castle", "ticks": 6},
    )
    assert response.status_code == 201, response.text
    screen = response.json()["screen"]
    assert screen["roads"][0]["ticks"] == 6
    # And both ends can walk down it.
    exits = {one["id"]: one["exits"] for one in screen["places"]}
    assert "castle" in exits["home"] and "home" in exits["castle"]


def test_a_road_that_cannot_be_drawn_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/api/author/roads",
        json={"origin": "home", "destination": "nowhere", "ticks": 6},
    )
    assert response.status_code == 400


def test_rubbing_a_road_out(client: TestClient) -> None:
    client.post(
        "/api/author/roads",
        json={"origin": "home", "destination": "castle", "ticks": 6},
    )
    gone = client.delete("/api/author/roads/home-to-castle")
    assert gone.status_code == 200, gone.text
    assert gone.json()["screen"]["roads"] == []
    assert client.delete("/api/author/roads/home-to-castle").status_code == 404


def test_dragging_a_place_is_an_ordinary_answer(client: TestClient) -> None:
    """Nothing special: a position is a field like any other."""
    response = client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.mapPosition",
            "value": {"x": 12, "y": -30},
        },
    )
    assert response.status_code == 200, response.text
    place = next(
        one for one in got(client, "/api/author/map")["places"] if one["id"] == "home"
    )
    assert (place["x"], place["y"]) == (12, -30)


def test_the_graph_is_a_route(client: TestClient) -> None:
    graph = got(client, "/api/author/graph")
    assert graph["scenes"] == []
    assert graph["entrances"] == []


# ── Playtest, and handing the pack on ─────────────────────────────────────────


def test_a_playtest_is_an_ordinary_session(client: TestClient) -> None:
    """Two front-ends, one engine: a playtest is a playthrough, not a mode.

    The proof is that the answer is a session id and the *game* routes drive
    it from there, without knowing it came from the wizard.
    """
    opened = client.post("/api/author/playtest", json={})
    assert opened.status_code == 201, opened.text
    frame = opened.json()
    assert frame["playing"] is True

    acted = client.post(
        f"/api/sessions/{frame['session']}/actions",
        json={"kind": "choose", "option": 0},
    )
    assert acted.status_code == 200, acted.text


def test_the_playtest_form_arrives_with_its_pickers_resolved(
    client: TestClient,
) -> None:
    """A browser cannot ask the catalog what locations exist mid-render."""
    offered = got(client, "/api/author/playtest")
    assert offered["setup"]["seed"] == "mace"
    assert {one["value"] for one in offered["locations"]} == {"home", "castle"}
    assert {one["value"] for one in offered["items"]} == {"gold"}


def test_the_playtest_setup_is_remembered(client: TestClient) -> None:
    """Retyping "the bridge, at midnight" twenty times is how people stop."""
    client.post(
        "/api/author/playtest", json={"startLocation": "castle", "seed": "wind"}
    )
    setup = got(client, "/api/author/playtest")["setup"]

    assert (setup["startLocation"], setup["seed"]) == ("castle", "wind")


def test_a_setup_that_will_not_start_is_not_remembered(client: TestClient) -> None:
    """The form should not open on the thing that just failed."""
    client.post("/api/author/playtest", json={"startLocation": "atlantis"})
    assert got(client, "/api/author/playtest")["setup"]["startLocation"] is None


def test_a_playtest_starts_where_the_author_asked(client: TestClient) -> None:
    """ "Start me at the castle, at midnight" — every part a session parameter."""
    opened = client.post(
        "/api/author/playtest",
        json={"startLocation": "castle", "startTick": 24, "seed": "storm"},
    )
    assert opened.status_code == 201, opened.text
    view = opened.json()["view"]
    assert view["atlas"]["here"] == "tiny:castle"
    assert view["tick"] == 24


def test_a_playtest_runs_the_pack_as_it_stands(client: TestClient) -> None:
    """Unsaved changes included. Compiling never touches the disk, so this is
    the project in memory rather than the project on disk."""
    client.post(
        "/api/author/objects/locations",
        json={"name": "The Tower", "section": "world", "answers": {}},
    )
    opened = client.post("/api/author/playtest", json={"startLocation": "the-tower"})
    assert opened.status_code == 201, opened.text
    assert opened.json()["view"]["atlas"]["here"] == "tiny:the-tower"


def test_a_playtest_that_cannot_start_is_a_400(client: TestClient) -> None:
    refused = client.post("/api/author/playtest", json={"startLocation": "atlantis"})
    assert refused.status_code == 400
    assert "atlantis" in refused.json()["detail"]


def test_exporting_hands_back_a_file(client: TestClient, root: Path) -> None:
    written = client.post("/api/author/export", json={"into": str(root.parent / "out")})
    assert written.status_code == 200, written.text

    archive = Path(written.json()["path"])
    assert archive.is_file()
    assert archive.stat().st_size == written.json()["bytes"]


def test_errors_block_an_export(client: TestClient) -> None:
    """The one place the wizard says no. Saving is still allowed."""
    client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.exits",
            "value": [{"to": "atlantis"}],
        },
    )
    refused = client.post("/api/author/export", json={})
    assert refused.status_code == 400
    assert "atlantis" in refused.json()["detail"]
    assert client.post("/api/author/save").status_code == 200


def test_a_wizard_with_nowhere_to_put_a_playthrough_says_so(root: Path) -> None:
    """The routes can be mounted without a session registry. Then there is
    nowhere for a playtest to live, and saying 409 beats pretending."""
    alone = FastAPI()
    alone.include_router(author_routes(Studio.open(root, root.parent)))
    refused = TestClient(alone).post("/api/author/playtest", json={})

    assert refused.status_code == 409


# ── A desk that can switch, or hold nothing yet ────────────────────────────


@pytest.fixture
def empty_desk(root: Path) -> TestClient:
    """A service whose wizard has no pack open yet, but can list `tiny`."""
    alone = FastAPI()
    alone.include_router(
        author_routes(Desk(studio=None, root=root.parent, search=root.parent))
    )
    return TestClient(alone)


def test_nothing_open_says_so_plainly(empty_desk: TestClient) -> None:
    assert got(empty_desk, "/api/author") == {"open": False}


def test_routes_that_need_a_pack_are_409_with_nothing_open(
    empty_desk: TestClient,
) -> None:
    assert empty_desk.get("/api/author/map").status_code == 409
    assert empty_desk.get("/api/author/sections/world").status_code == 409
    assert (
        empty_desk.post(
            "/api/author/answers",
            json={"collection": "locations", "step": "location.name", "value": "x"},
        ).status_code
        == 409
    )


def test_the_games_list_is_reachable_with_nothing_open(
    empty_desk: TestClient, root: Path
) -> None:
    listed = got(empty_desk, "/api/author/games")
    assert listed == {
        "games": [{"id": "tiny", "name": "tiny", "path": str(root)}],
        "open": None,
    }


def test_the_libraries_list_is_empty_when_there_are_none(
    empty_desk: TestClient,
) -> None:
    assert got(empty_desk, "/api/author/libraries") == {"libraries": []}


def test_opening_one_makes_the_desk_answer_normally(empty_desk: TestClient) -> None:
    opened = empty_desk.post("/api/author/open", json={"pack": "tiny"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["pack"]["id"] == "tiny"
    assert got(empty_desk, "/api/author")["pack"]["id"] == "tiny"


def test_opening_something_that_is_not_there_is_a_400(empty_desk: TestClient) -> None:
    refused = empty_desk.post("/api/author/open", json={"pack": "dragons"})
    assert refused.status_code == 400
    assert "dragons" in refused.json()["detail"]


def test_creating_a_game_opens_it(empty_desk: TestClient) -> None:
    made = empty_desk.post("/api/author/games", json={"name": "A New Quest"})
    assert made.status_code == 201, made.text
    assert made.json()["pack"]["id"] == "a-new-quest"
    assert got(empty_desk, "/api/author/games")["open"] == "a-new-quest"


def test_switching_away_from_unsaved_changes_is_refused(root: Path) -> None:
    alone = FastAPI()
    alone.include_router(
        author_routes(Desk(studio=Studio.open(root, root.parent), root=root.parent))
    )
    client = TestClient(alone)
    client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.safe",
            "value": True,
        },
    )

    made = client.post("/api/author/games", json={"name": "Somewhere Else"})
    assert made.status_code == 400
    assert "unsaved" in made.json()["detail"]
    # And the original pack is exactly as it was — still open, still dirty.
    assert got(client, "/api/author")["pack"]["id"] == "tiny"


def test_discard_switches_away_from_unsaved_changes_anyway(root: Path) -> None:
    alone = FastAPI()
    alone.include_router(
        author_routes(Desk(studio=Studio.open(root, root.parent), root=root.parent))
    )
    client = TestClient(alone)
    client.post(
        "/api/author/answers",
        json={
            "collection": "locations",
            "object": "home",
            "step": "location.safe",
            "value": True,
        },
    )

    made = client.post(
        "/api/author/games",
        json={"name": "Somewhere Else", "discard": True},
    )
    assert made.status_code == 201, made.text
    assert made.json()["pack"]["id"] == "somewhere-else"


def test_a_pack_that_does_not_validate_is_still_listed(root: Path) -> None:
    """An author has to be able to open a half-written pack, not just a
    finished one — the same tolerance `Project` gives raw content
    everywhere else."""
    (root / "locations.yml").write_text("locations: [{id: home, exits: not-a-list}]\n")
    with pytest.raises(Exception):  # noqa: B017, PT011 — proving it really doesn't load
        load_library(root.parent)

    alone = FastAPI()
    alone.include_router(
        author_routes(Desk(studio=None, root=root.parent, search=root.parent))
    )
    listed = got(TestClient(alone), "/api/author/games")
    assert listed["games"] == [{"id": "tiny", "name": "tiny", "path": str(root)}]
