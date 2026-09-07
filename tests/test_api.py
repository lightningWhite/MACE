"""The session service, over HTTP and over a socket.

The service holds no rules, so what is worth testing is the contract: one
frame shape for every reply, actions that mean nothing refused with a reason,
a save that reopens the same playthrough somewhere else, and a session id that
cannot be guessed at.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import game_pack
from mace.api.app import create_app
from mace.api.sessions import Registry, UnknownSession
from mace.content import load_library
from mace.session import Session
from test_session_view import WORLD


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """A service over a small game with a map and a quest.

    Parameters
    ----------
    tmp_path : Path
        Pytest's temporary directory.

    Returns
    -------
    TestClient
        The client.
    """
    game_pack(tmp_path / "packs", game={"quests": ["the-summons"]}, world=WORLD)
    return TestClient(create_app(library=load_library(tmp_path / "packs")))


def opened(client: TestClient, **body: Any) -> dict[str, Any]:
    """Open a playthrough.

    Parameters
    ----------
    client : TestClient
        The service.
    **body
        Fields for the request.

    Returns
    -------
    dict
        The opening frame.
    """
    response = client.post("/api/sessions", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# ── What there is to play ─────────────────────────────────────────────────────


def test_the_service_lists_its_games(client: TestClient) -> None:
    (game,) = client.get("/api/games").json()["games"]
    assert game["id"] == "tiny"
    assert game["version"] == "0.1.0"


def test_a_game_with_nothing_to_ask_says_so(client: TestClient) -> None:
    """A front-end that opened an empty creation menu anyway would be a form."""
    asked = client.get("/api/games/tiny/creation").json()
    assert asked["asksAnything"] is False
    assert asked["backgrounds"] == []


def test_a_game_nobody_has_is_a_404(client: TestClient) -> None:
    assert client.get("/api/games/nowhere/creation").status_code == 404


# ── One frame shape for everything ────────────────────────────────────────────


def test_opening_hands_back_the_events_and_what_stands(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    assert frame["playing"] is True
    assert frame["choices"] == ["Travel to The Mill", "Travel to The Castle"]
    assert {event["kind"] for event in frame["events"]} >= {"narrate", "choices"}
    assert frame["view"]["sheet"]["name"] == "Hero"
    assert frame["view"]["atlas"]["here"] == "tiny:home"


def test_looking_again_gives_the_same_frame(client: TestClient) -> None:
    """A reconnecting client is given the events again, not told to catch up."""
    frame = opened(client, pack="tiny")
    again = client.get(f"/api/sessions/{frame['session']}").json()
    assert again["events"] == frame["events"]
    assert again["choices"] == frame["choices"]


def test_acting_returns_what_the_action_did(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    acted = client.post(
        f"/api/sessions/{frame['session']}/actions",
        json={"kind": "choose", "prompt": "Travel to The Mill"},
    )
    assert acted.status_code == 200
    assert acted.json()["view"]["atlas"]["here"] == "tiny:mill"


def test_a_choice_may_be_named_by_its_index(client: TestClient) -> None:
    """The protocol form, which is what a live client sends."""
    frame = opened(client, pack="tiny")
    acted = client.post(
        f"/api/sessions/{frame['session']}/actions",
        json={"kind": "choose", "option": 0},
    )
    assert acted.json()["view"]["atlas"]["here"] == "tiny:mill"


# ── Being told no ─────────────────────────────────────────────────────────────


def test_an_action_that_is_not_one_says_which_are(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    refused = client.post(
        f"/api/sessions/{frame['session']}/actions", json={"kind": "yodel"}
    )
    assert refused.status_code == 400
    assert "unknown action" in refused.json()["detail"]


def test_a_choice_that_is_not_on_offer_says_what_was(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    refused = client.post(
        f"/api/sessions/{frame['session']}/actions",
        json={"kind": "choose", "prompt": "Fly to the moon"},
    )
    assert refused.status_code == 400
    assert "Travel to The Mill" in refused.json()["detail"]


def test_a_session_that_is_gone_says_what_to_do(client: TestClient) -> None:
    missing = client.get("/api/sessions/nothing-like-that")
    assert missing.status_code == 404
    assert "post the save" in missing.json()["detail"]


def test_a_game_that_is_not_loaded_is_refused(client: TestClient) -> None:
    refused = client.post("/api/sessions", json={"pack": "nowhere"})
    assert refused.status_code == 400


# ── Saves are how a playthrough outlives the process ──────────────────────────


def test_a_save_reopens_the_same_playthrough(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    client.post(
        f"/api/sessions/{frame['session']}/actions",
        json={"kind": "choose", "prompt": "Travel to The Mill"},
    )
    save = client.get(f"/api/sessions/{frame['session']}/save").json()
    assert save["actions"] == [{"kind": "choose", "prompt": "Travel to The Mill"}]

    carried = opened(client, save=save)
    assert carried["session"] != frame["session"]
    assert carried["view"]["atlas"]["here"] == "tiny:mill"
    assert carried["warnings"] == []


def test_a_save_from_a_newer_engine_is_refused(client: TestClient) -> None:
    refused = client.post(
        "/api/sessions", json={"save": {"format": 99, "pack": "tiny"}}
    )
    assert refused.status_code == 400
    assert "newer MACE" in refused.json()["detail"]


def test_closing_a_session_forgets_it(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    assert client.delete(f"/api/sessions/{frame['session']}").status_code == 204
    assert client.get(f"/api/sessions/{frame['session']}").status_code == 404


# ── The same exchange, held open ──────────────────────────────────────────────


def test_the_socket_opens_on_the_current_frame(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    with client.websocket_connect(f"/api/sessions/{frame['session']}/stream") as socket:
        assert socket.receive_json()["choices"] == frame["choices"]


def test_the_socket_carries_the_same_frames(client: TestClient) -> None:
    frame = opened(client, pack="tiny")
    with client.websocket_connect(f"/api/sessions/{frame['session']}/stream") as socket:
        socket.receive_json()
        socket.send_json({"kind": "choose", "prompt": "Travel to The Mill"})
        assert socket.receive_json()["view"]["atlas"]["here"] == "tiny:mill"


def test_a_bad_action_does_not_close_the_socket(client: TestClient) -> None:
    """A mistyped action is not a reason to reconnect in the middle of a fight."""
    frame = opened(client, pack="tiny")
    with client.websocket_connect(f"/api/sessions/{frame['session']}/stream") as socket:
        socket.receive_json()
        socket.send_json({"kind": "yodel"})
        assert "unknown action" in socket.receive_json()["error"]

        socket.send_json({"kind": "choose", "option": 0})
        assert socket.receive_json()["view"]["atlas"]["here"] == "tiny:mill"


def test_the_socket_says_when_there_is_no_session(client: TestClient) -> None:
    with client.websocket_connect("/api/sessions/nothing/stream") as socket:
        assert socket.receive_json() == {"error": "no such session"}


# ── Serving the client too ────────────────────────────────────────────────────


def test_a_built_client_is_served_beside_the_api(tmp_path: Path) -> None:
    """One origin in a deployment, so there is no CORS list to get wrong."""
    game_pack(tmp_path / "packs", world=WORLD)
    built = tmp_path / "dist"
    built.mkdir()
    (built / "index.html").write_text("<title>MACE</title>", encoding="utf-8")

    served = TestClient(
        create_app(library=load_library(tmp_path / "packs"), client=built)
    )
    assert "MACE" in served.get("/").text
    assert served.get("/api/games").status_code == 200


def test_the_api_wins_over_the_client_at_the_same_path(tmp_path: Path) -> None:
    """The client is mounted at the root, so `/api` has to be reached first."""
    game_pack(tmp_path / "packs", world=WORLD)
    built = tmp_path / "dist"
    (built / "api").mkdir(parents=True)
    (built / "index.html").write_text("client", encoding="utf-8")
    (built / "api" / "games").write_text("not the api", encoding="utf-8")

    served = TestClient(
        create_app(library=load_library(tmp_path / "packs"), client=built)
    )
    assert served.get("/api/games").json()["games"][0]["id"] == "tiny"


def test_a_client_that_is_not_built_is_simply_not_served(tmp_path: Path) -> None:
    game_pack(tmp_path / "packs", world=WORLD)
    served = TestClient(
        create_app(
            library=load_library(tmp_path / "packs"), client=tmp_path / "nothing"
        )
    )
    assert served.get("/").status_code == 404
    assert served.get("/api/games").status_code == 200


# ── The registry ──────────────────────────────────────────────────────────────


def test_a_session_id_is_not_a_counter(tmp_path: Path) -> None:
    """It is a bearer token: holding one is permission to play that game."""
    game_pack(tmp_path / "packs", world=WORLD)
    library = load_library(tmp_path / "packs")
    registry = Registry()
    ids = {registry.add(Session.begin(library, "tiny")) for _ in range(20)}
    assert len(ids) == 20
    assert all(len(one) > 16 for one in ids)


def test_the_registry_drops_the_least_recently_used(tmp_path: Path) -> None:
    game_pack(tmp_path / "packs", world=WORLD)
    library = load_library(tmp_path / "packs")
    registry = Registry(capacity=2)

    first = registry.add(Session.begin(library, "tiny"))
    second = registry.add(Session.begin(library, "tiny"))
    registry.get(first)  # touching it makes the second one the oldest
    third = registry.add(Session.begin(library, "tiny"))

    assert set(registry.open) == {first, third}
    with pytest.raises(UnknownSession):
        registry.get(second)


def test_dropping_something_that_is_not_there_says_so() -> None:
    with pytest.raises(UnknownSession):
        Registry().drop("nothing")
