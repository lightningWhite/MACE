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
from fastapi.testclient import TestClient

from conftest import write_pack
from mace.api.app import create_app
from mace.content import load_library
from mace.wizard.studio import Studio

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
    response = client.post("/api/author/objects/climates", json={"name": "Wet"})
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
