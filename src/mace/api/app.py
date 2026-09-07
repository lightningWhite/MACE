"""The session service: one HTTP surface over `mace.session`.

This is a front-end, and it obeys the rules every front-end obeys. It drives a
`Session`, renders the ordered event stream, reads the view-model for the
things that stand, and never reaches into engine state for anything. The
terminal and the browser tab differ in what they draw, not in what they are
allowed to know — swap the renderer and the same JSON is the CLI.

There are two ways to play through it and they carry the same frames. `POST
/sessions/{id}/actions` is a plain request per action, which is enough for a
client that only ever acts when the player clicks. The WebSocket at
`/sessions/{id}/stream` is the same exchange held open, and exists because
combat has a clock in it: a `combat.tell` opens a window measured in
milliseconds, and spending a chunk of that window on connection setup would
make the fight unfair in a way the player would feel and could not name.

What the service does *not* do is decide anything. It holds no rules, no
balance, and no prose. A bug that shows up here is a bug in the engine, or it
is a bug in the JSON.

See docs/10-clients-and-interface.md § Technology.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from mace import __version__
from mace.api.sessions import Registry, UnknownSession
from mace.content import ContentError, Library, load_library
from mace.engine.actions import decode
from mace.engine.conditions import RuleError
from mace.engine.creation import Character, Creation
from mace.engine.creation import offer as creation_offer
from mace.session import Save, SaveError, Session, choose_game, resume

__all__ = ["DEV_ORIGINS", "New", "create_app", "frame"]

#: Where a development web client is served from. The PWA is built by Vite,
#: which means a different origin from this service until they are deployed
#: together, and a browser will not talk to it without being told to.
DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class Wire(BaseModel):
    """Base for request bodies: camelCase in, snake_case in Python."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class Made(Wire):
    """What the player answered at character creation.

    Attributes
    ----------
    background : str or None
        The chosen background.
    spend : mapping
        Stat name to creation points put into it.
    """

    background: str | None = None
    spend: dict[str, int] = Field(default_factory=dict)


class New(Wire):
    """A request to open a playthrough.

    Either a fresh one, or `save` to carry an existing one on. A save carries
    its own seed, combat mode and character, so the rest is ignored beside it —
    the same rule the terminal's `--load` follows.

    Attributes
    ----------
    pack : str or None
        Which game. None picks the only one loaded.
    seed : str
        The session seed.
    combat_mode : str or None
        Override the game's default combat presentation.
    time_pressure : float
        How hard the clock presses in `reflex` combat. 1.0 is the fight as
        written; 0.5 gives twice the window.
    character : Made or None
        Who the player is.
    save : mapping or None
        A save record to resume from.
    """

    pack: str | None = None
    seed: str = "mace"
    combat_mode: str | None = None
    time_pressure: float = Field(default=1.0, gt=0.0, le=10.0)
    character: Made | None = None
    save: dict[str, Any] | None = None


def frame(session_id: str, session: Session) -> dict[str, Any]:
    """Everything a client needs after something happened.

    One shape for every reply, so a client has one renderer rather than one
    per endpoint. The events are what happened; the view is what stands; the
    choices are what may be done next, named the way a save names them.

    Parameters
    ----------
    session_id : str
        Which playthrough.
    session : Session
        The playthrough.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "session": session_id,
        "playing": session.playing,
        "events": [event.record() for event in session.events],
        "choices": list(session.offered),
        "view": session.view().record(),
    }


def _creation(offered: Creation) -> dict[str, Any]:
    """Render the character-creation question.

    Parameters
    ----------
    offered : Creation
        The projection `mace.engine.creation` already built.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "asksAnything": offered.asks_anything,
        "points": offered.points,
        "backgrounds": [
            {
                "id": one.id,
                "name": one.name,
                "description": one.description,
                "grants": list(one.grants),
            }
            for one in offered.backgrounds
        ],
        "stats": [
            {
                "stat": one.stat,
                "base": one.base,
                "minimum": one.minimum,
                "maximum": one.maximum,
                "room": one.room,
            }
            for one in offered.stats
        ],
    }


def create_app(
    paths: Sequence[Path] | None = None,
    *,
    library: Library | None = None,
    origins: Sequence[str] = DEV_ORIGINS,
    capacity: int | None = None,
    client: Path | None = None,
) -> FastAPI:
    """Build the service over some loaded content.

    Parameters
    ----------
    paths : sequence of Path or None
        Pack directories to load. Ignored when `library` is given.
    library : Library or None
        Already-loaded content, which is what the tests hand it.
    origins : sequence of str
        Origins a browser may call this from.
    capacity : int or None
        How many playthroughs to hold open. None takes the default.
    client : Path or None
        A built web client (`web/dist`) to serve alongside the API. When it is
        there, the game and the service share an origin and the CORS list is
        beside the point; in development the two are separate and the Vite
        dev server proxies `/api` to here instead.

    Returns
    -------
    FastAPI
        The application.

    Raises
    ------
    ContentError
        If the content will not load.
    """
    loaded = (
        library if library is not None else load_library(*(paths or [Path("packs")]))
    )
    registry = Registry() if capacity is None else Registry(capacity=capacity)

    app = FastAPI(
        title="MACE",
        version=__version__,
        description="Play a MACE world over HTTP.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.library = loaded
    app.state.sessions = registry

    def held(session_id: str) -> Session:
        """Find a playthrough, or say plainly that it is gone.

        Parameters
        ----------
        session_id : str
            The id.

        Returns
        -------
        Session
            The playthrough.

        Raises
        ------
        HTTPException
            404, with what to do about it.
        """
        try:
            return registry.get(session_id)
        except UnknownSession:
            raise HTTPException(
                status_code=404,
                detail=(
                    "no such session. Sessions live in one process and are "
                    "dropped when it restarts or fills up — open a new one, "
                    "or post the save you were given."
                ),
            ) from None

    # ── What there is to play ─────────────────────────────────────────────

    @app.get("/api/games")
    def games() -> dict[str, Any]:
        """List the playable packs.

        Returns
        -------
        dict
            One entry per game pack.
        """
        return {
            "games": [
                {
                    "id": pack.id,
                    "name": pack.manifest.name,
                    "version": str(pack.manifest.version),
                    "description": pack.manifest.description,
                }
                for pack in loaded.games
            ]
        }

    @app.get("/api/games/{pack}/creation")
    def creation(
        pack: str,
        background: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        """The character-creation question, if the game asks one.

        Parameters
        ----------
        pack : str
            The game pack.
        background : str or None
            A background already chosen, so the stats are the ones the player
            will actually start with.

        Returns
        -------
        dict
            The question, JSON-safe.

        Raises
        ------
        HTTPException
            404 if there is no such game.
        """
        try:
            return _creation(creation_offer(loaded, pack, background=background))
        except ContentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    # ── Playing ───────────────────────────────────────────────────────────

    @app.post("/api/sessions", status_code=201)
    def open_session(
        new: Annotated[New | None, Body()] = None,
    ) -> dict[str, Any]:
        """Start a playthrough, or carry a saved one on.

        Parameters
        ----------
        new : New or None
            What to open. An empty body opens the only game loaded.

        Returns
        -------
        dict
            The opening frame, with the session id to address it by.

        Raises
        ------
        HTTPException
            400 if the content will not open it, or the save will not replay.
        """
        asked = new if new is not None else New()
        try:
            if asked.save is not None:
                session, drift = resume(Save.restore(asked.save), loaded)
            else:
                drift = []
                session = Session.begin(
                    loaded,
                    choose_game(loaded, asked.pack),
                    seed=asked.seed,
                    combat_mode=asked.combat_mode,
                    time_pressure=asked.time_pressure,
                    character=(
                        None
                        if asked.character is None
                        else Character(
                            background=asked.character.background,
                            spend=dict(asked.character.spend),
                        )
                    ),
                )
        except (ContentError, SaveError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return {**frame(registry.add(session), session), "warnings": drift}

    @app.get("/api/sessions/{session_id}")
    def look(session_id: str) -> dict[str, Any]:
        """Where a playthrough stands, and what it last said.

        A reconnecting client is handed the last step's events again rather
        than being told to work out what it missed from the state.

        Parameters
        ----------
        session_id : str
            Which playthrough.

        Returns
        -------
        dict
            The frame.
        """
        return frame(session_id, held(session_id))

    @app.post("/api/sessions/{session_id}/actions")
    def act(
        session_id: str, action: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        """Do one thing.

        Parameters
        ----------
        session_id : str
            Which playthrough.
        action : dict
            An action record — `{"kind": "choose", "option": 2}`, or the same
            named by `prompt`.

        Returns
        -------
        dict
            The frame the action produced.

        Raises
        ------
        HTTPException
            400 if the action means nothing here.
        """
        session = held(session_id)
        return _acted(session_id, session, action)

    @app.get("/api/sessions/{session_id}/save")
    def save(session_id: str) -> dict[str, Any]:
        """The playthrough as a save file.

        Parameters
        ----------
        session_id : str
            Which playthrough.

        Returns
        -------
        dict
            The save record — post it back as `save` to reopen this exact
            playthrough, here or anywhere else running the same content.
        """
        return Save.of(held(session_id)).record()

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def close(session_id: str) -> None:
        """Stop holding a playthrough open.

        Parameters
        ----------
        session_id : str
            Which playthrough.
        """
        held(session_id)
        registry.drop(session_id)

    # ── The same exchange, held open ──────────────────────────────────────

    @app.websocket("/api/sessions/{session_id}/stream")
    async def stream(websocket: WebSocket, session_id: str) -> None:
        """Play over one connection.

        The client is sent the current frame on connect, then one frame per
        action it sends. An action that means nothing comes back as an error
        frame and the connection stays open, because a mistyped action is not
        a reason to make the player reconnect mid-fight.

        Parameters
        ----------
        websocket : WebSocket
            The connection.
        session_id : str
            Which playthrough.
        """
        await websocket.accept()
        try:
            session = registry.get(session_id)
        except UnknownSession:
            await websocket.send_json({"error": "no such session"})
            await websocket.close(code=4404)
            return

        await websocket.send_json(frame(session_id, session))
        try:
            while True:
                action = await websocket.receive_json()
                try:
                    await websocket.send_json(_acted(session_id, session, action))
                except HTTPException as error:
                    await websocket.send_json({"error": error.detail})
        except WebSocketDisconnect:
            return

    # Mounted last, at the root, so every `/api` route above wins. `html=True`
    # serves index.html for a path the build has no file for, which is what a
    # client with its own routes needs and costs nothing to a client without.
    if client is not None and client.is_dir():
        app.mount("/", StaticFiles(directory=client, html=True), name="client")

    return app


def _acted(
    session_id: str, session: Session, action: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply one action record and describe what it did.

    Choices are resolved against what is on offer *now*, which is what lets a
    client send `{"kind": "choose", "prompt": "Speak to the troll"}` and mean
    it. An index still works and is what a live client will usually send.

    Parameters
    ----------
    session_id : str
        Which playthrough.
    session : Session
        The playthrough.
    action : mapping
        The action record.

    Returns
    -------
    dict
        The frame.

    Raises
    ------
    HTTPException
        400 if the record names no action, or one that means nothing here.
    """
    if not isinstance(action, Mapping):
        raise HTTPException(status_code=400, detail="an action is an object")
    try:
        session.perform(decode(dict(action), offered=session.offered))
    except (ValueError, RuleError, ContentError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return frame(session_id, session)
