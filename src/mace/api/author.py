"""The authoring service: one HTTP surface over `mace.wizard.studio`.

The twin of `mace.api.app`, and it obeys the same rule. It renders screens the
studio projects and posts answers back through `Step.write`; it holds no
questions, no vocabulary, and no opinion about what a location is. A step type
is added in `mace.wizard`, not here.

**This one writes to the author's disk**, which the session service never
does, and that is the whole reason it is a separate router mounted only when
somebody asks for it. `mace author --web` and `mace dev` both bind it to
localhost; there is no authentication and no path in the API that names an
arbitrary file — a game is opened or created by id, resolved against a
`Desk`'s own configured directory, never by a client-supplied path. Serving
it to a network would be handing that network a filesystem, so do not.

One pack open at a time, the way `mace author` is one pack per terminal. That
is not a limitation being worked around: a project holds unsaved edits in
memory, and two of them open for editing at once would be two authors
quietly overwriting each other. `Desk` (`mace.wizard.studio`) is what makes
"one at a time" and "switchable" both true together — it refuses to switch
away from a pack with unsaved changes rather than losing them.

See docs/09-authoring-and-wizard.md § CLI and web parity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException

from mace.api.app import Wire
from mace.api.sessions import Registry
from mace.content import ContentError
from mace.session import frame as frame_of
from mace.wizard.notes import PlaytestSetup
from mace.wizard.playtest import start_from
from mace.wizard.share import export_pack
from mace.wizard.studio import Desk, Studio, Unknown, frame

__all__ = [
    "Answer",
    "Built",
    "Made",
    "NewGame",
    "OpenGame",
    "Road",
    "Trial",
    "author_routes",
]


class Answer(Wire):
    """One question answered.

    The value is the authored one, not typed text — a browser has already
    turned a click into `fantasy.core:gold`, and a parser here would be a
    second, worse copy of the field types.

    Attributes
    ----------
    collection : str
        Which collection, or `game` for the manifest.
    step : str
        Which question.
    object : str or None
        Which object. Absent for the manifest.
    value : object
        The answer. None clears the field.
    """

    collection: str
    step: str
    object: str | None = None
    value: Any = None


class Made(Wire):
    """A new object, asked for with as little as its name.

    Attributes
    ----------
    name : str
        What the author called it. The id is derived from it.
    section : str or None
        The section it is being made in, for the fields that section fixes.
    answers : dict
        Any other steps already answered, by step id.
    """

    name: str
    section: str | None = None
    answers: dict[str, Any] = {}  # noqa: RUF012 — pydantic copies per instance


class Road(Wire):
    """A road to draw between two places.

    Attributes
    ----------
    origin, destination : str
        Local ids of the two places.
    ticks : int
        How long it takes in fair weather.
    name : str or None
        What to call it. None names it after where it goes.
    """

    origin: str
    destination: str
    ticks: int = 1
    name: str | None = None


class Trial(Wire):
    """Where and how to open a playtest.

    Every field is a session-opening parameter, the way the seed is, so a
    playtest is an ordinary replayable session rather than a special mode.

    Attributes
    ----------
    seed : str
        Fixed by default, so a change in the pack is the only variable.
    start_location : str or None
        Where to begin, overriding the game's own start.
    start_tick : int or None
        When to begin.
    weather : str or None
        A condition to open in, whatever the climate would have rolled.
    items : dict
        Extra kit, by reference.
    background : str or None
        Which background to create the protagonist with.
    spend : dict
        Where the creation points went.
    combat_mode : str or None
        Which combat presentation to use.
    """

    seed: str = "mace"
    start_location: str | None = None
    start_tick: int | None = None
    weather: str | None = None
    items: dict[str, int] = {}  # noqa: RUF012 — pydantic copies per instance
    background: str | None = None
    spend: dict[str, int] = {}  # noqa: RUF012 — pydantic copies per instance
    combat_mode: str | None = None


class NewGame(Wire):
    """A new game pack, asked for with as little as its title.

    Attributes
    ----------
    name : str
        Its title. The id and directory are derived from it.
    requires : dict
        Pack id to version range — which libraries it builds on.
    """

    name: str
    requires: dict[str, str] = {}  # noqa: RUF012 — pydantic copies per instance


class OpenGame(Wire):
    """Which existing game pack to switch to.

    Attributes
    ----------
    pack : str
        Its id, as `GET /api/author/games` lists it.
    """

    pack: str


class Built(Wire):
    """A cascade's answers, to be turned into content.

    Attributes
    ----------
    kind : str
        `conditions` or `effects`.
    tag : str
        Which one to build.
    answers : dict
        Ask key to the author's answer.
    """

    kind: str
    tag: str
    answers: dict[str, Any] = {}  # noqa: RUF012 — pydantic copies per instance


def author_routes(studio: Studio | Desk, registry: Registry | None = None) -> APIRouter:
    """Build the authoring routes over an open pack, or a switchable desk.

    Parameters
    ----------
    studio : Studio or Desk
        The pack being edited, held for the life of the process the way it
        always was — or a `Desk`, which can hold none yet and can switch
        which one it holds, for a process that lets an author pick.
    registry : Registry or None
        Where a playtest's session goes, so the game client can drive it
        through the ordinary `/api/sessions` routes. None leaves playtesting
        off, which is what a service with no session registry means.

    Returns
    -------
    APIRouter
        The routes, ready to include under `/api/author`.
    """
    held = studio if isinstance(studio, Desk) else Desk(studio)
    router = APIRouter(prefix="/api/author", tags=["authoring"])

    def current() -> Studio:
        """The open pack, or a clear refusal when there is none.

        Returns
        -------
        Studio
            The open pack.

        Raises
        ------
        HTTPException
            409, when nothing is open yet.
        """
        if held.studio is None:
            raise HTTPException(status_code=409, detail="no pack open — pick one first")
        return held.studio

    def screened(screen: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap a screen in the frame every reply carries.

        Parameters
        ----------
        screen : dict or None
            Whatever was asked for.

        Returns
        -------
        dict
            The frame.
        """
        return frame(current(), screen)

    # ── Which pack ────────────────────────────────────────────────────────

    @router.get("/games")
    def games() -> dict[str, Any]:
        """Every authorable game pack, for a picker to offer.

        Returns
        -------
        dict
            `games`, and which one (if any) is open right now.

        Raises
        ------
        HTTPException
            404 if this process has no games directory configured.
        """
        try:
            listed = held.games()
        except ContentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        opened = None if held.studio is None else held.studio.project.manifest.id
        return {"games": listed, "open": opened}

    @router.get("/libraries")
    def libraries() -> dict[str, Any]:
        """Every library pack a new game could depend on.

        Returns
        -------
        dict
            `libraries`.

        Raises
        ------
        HTTPException
            404 if this process has no dependency directory configured.
        """
        try:
            listed = held.libraries()
        except ContentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"libraries": listed}

    @router.post("/games", status_code=201)
    def new_game(body: Annotated[NewGame, Body()]) -> dict[str, Any]:
        """Start a new game pack and open it.

        Parameters
        ----------
        body : NewGame
            Its title, and what it depends on.

        Returns
        -------
        dict
            The frame, with the newly opened pack's task list.

        Raises
        ------
        HTTPException
            400 if it cannot be made — including unsaved edits in whatever
            was open before.
        """
        try:
            held.create(body.name, body.requires)
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened()

    @router.post("/open")
    def open_game(body: Annotated[OpenGame, Body()]) -> dict[str, Any]:
        """Switch to an existing game pack.

        Parameters
        ----------
        body : OpenGame
            Which one.

        Returns
        -------
        dict
            The frame, with the newly opened pack's task list.

        Raises
        ------
        HTTPException
            400 if it cannot be opened — including unsaved edits in
            whatever was open before, or no such game.
        """
        try:
            held.open(body.pack)
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened()

    # ── Reading ───────────────────────────────────────────────────────────

    @router.get("")
    def desk() -> dict[str, Any]:
        """The task list, and nothing else.

        Returns
        -------
        dict
            `{"open": False}` when nothing is open yet — the client's cue to
            offer `GET /api/author/games` instead — or the frame, with no
            screen.
        """
        if held.studio is None:
            return {"open": False}
        return screened()

    @router.get("/vocabulary")
    def vocabulary() -> dict[str, Any]:
        """The condition and effect cascades, with this pack's options on them.

        Returns
        -------
        dict
            `conditions` and `effects`.
        """
        return current().vocabulary()

    @router.get("/map")
    def atlas() -> dict[str, Any]:
        """The world map as the author has drawn it so far.

        Returns
        -------
        dict
            Places and roads.
        """
        return current().atlas()

    @router.get("/preview/{collection}/{object_id}")
    def preview(collection: str, object_id: str) -> dict[str, Any]:
        """One object as the engine will see it, not as the file writes it.

        Parameters
        ----------
        collection : str
            Which collection.
        object_id : str
            The object's local id.

        Returns
        -------
        dict
            The preview.

        Raises
        ------
        HTTPException
            404 if it is not there.
        """
        return _found(lambda: current().preview(collection, object_id))

    @router.get("/graph")
    def graph() -> dict[str, Any]:
        """Every scene, what leads to it, and what it leads to.

        Returns
        -------
        dict
            The graph, with reachability already worked out — the same answer
            `mace validate` gives, because it is the same code.
        """
        return current().graph()

    @router.post("/roads", status_code=201)
    def link(body: Annotated[Road, Body()]) -> dict[str, Any]:
        """Draw a road between two places, and the ways onto it.

        One call rather than three, because drawing a road is one authoring
        intention — see `Studio.link`.

        Parameters
        ----------
        body : Road
            Where it goes and how long it takes.

        Returns
        -------
        dict
            The frame, with the map as it now stands.

        Raises
        ------
        HTTPException
            400 if it cannot be drawn.
        """
        try:
            current().link(body.origin, body.destination, body.ticks, name=body.name)
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened(current().atlas())

    @router.delete("/roads/{route_id}")
    def unlink(route_id: str) -> dict[str, Any]:
        """Rub out a road, and the ways onto it.

        Parameters
        ----------
        route_id : str
            The road's local id.

        Returns
        -------
        dict
            The frame, with the map as it now stands.

        Raises
        ------
        HTTPException
            404 if there was nothing to rub out.
        """
        if not current().unlink(route_id):
            raise HTTPException(
                status_code=404, detail=f"there is no `{route_id}` to rub out"
            )
        return screened(current().atlas())

    @router.get("/problems")
    def problems() -> dict[str, Any]:
        """Everything the validator found, worst first.

        Returns
        -------
        dict
            The problem list.
        """
        return {"problems": current().report()}

    @router.get("/sections/{section_id}")
    def section(section_id: str) -> dict[str, Any]:
        """One section's contents.

        Parameters
        ----------
        section_id : str
            The section.

        Returns
        -------
        dict
            The frame, with the section screen.

        Raises
        ------
        HTTPException
            404 if there is no such section.
        """
        return screened(_found(lambda: current().section(section_id)))

    @router.get("/objects/{collection}")
    def manifest(collection: str) -> dict[str, Any]:
        """The game manifest, or any flow that authors one object.

        Parameters
        ----------
        collection : str
            `game`, usually.

        Returns
        -------
        dict
            The frame, with the object screen.

        Raises
        ------
        HTTPException
            404 if nothing authors it, or it needs an object id.
        """
        return screened(_found(lambda: current().object(collection)))

    @router.get("/objects/{collection}/{object_id}")
    def one(collection: str, object_id: str) -> dict[str, Any]:
        """One object's steps, with everything a form needs to draw them.

        Parameters
        ----------
        collection : str
            Which collection.
        object_id : str
            The object's local id.

        Returns
        -------
        dict
            The frame, with the object screen.

        Raises
        ------
        HTTPException
            404 if it is not there.
        """
        return screened(_found(lambda: current().object(collection, object_id)))

    # ── Changing things ───────────────────────────────────────────────────

    @router.post("/answers")
    def answer(body: Annotated[Answer, Body()]) -> dict[str, Any]:
        """Record one answer, and say where the pack stands afterwards.

        Parameters
        ----------
        body : Answer
            What was answered.

        Returns
        -------
        dict
            The frame, with the step as it now stands. The desk on it is what
            makes a problem count move as an author types.

        Raises
        ------
        HTTPException
            404 for a step nobody has, 400 for an answer that will not land.
        """
        try:
            changed = current().answer(
                body.collection, body.step, body.value, body.object
            )
        except Unknown as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened(changed)

    @router.post("/objects/{collection}", status_code=201)
    def create(collection: str, body: Annotated[Made, Body()]) -> dict[str, Any]:
        """Make a new object and open it.

        Parameters
        ----------
        collection : str
            Which collection.
        body : Made
            The name, and anything else already answered.

        Returns
        -------
        dict
            The frame, with the new object's screen.

        Raises
        ------
        HTTPException
            404 if nothing authors that collection, 400 if it cannot be made.
        """
        try:
            made = current().create(
                collection, body.name, section=body.section, answers=body.answers
            )
        except Unknown as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened(current().object(collection, made))

    @router.delete("/objects/{collection}/{object_id}")
    def remove(collection: str, object_id: str) -> dict[str, Any]:
        """Remove an object.

        Nothing is checked first, deliberately: a wizard that refused to
        delete something other things point at could not be used to
        restructure a world. What breaks shows up in the problem list.

        Parameters
        ----------
        collection : str
            Which collection.
        object_id : str
            The object's local id.

        Returns
        -------
        dict
            The frame, with the section it was in — or none, when no section
            covers that collection.

        Raises
        ------
        HTTPException
            404 if there was nothing to remove.
        """
        if not current().delete(collection, object_id):
            raise HTTPException(
                status_code=404, detail=f"there is no `{object_id}` to delete"
            )
        return screened()

    @router.post("/build")
    def build(body: Annotated[Built, Body()]) -> dict[str, Any]:
        """Turn a cascade's answers into an authored condition or effect.

        The round-trip through the model happens on this side, which is what
        stops a browser writing content the loader would reject.

        Parameters
        ----------
        body : Built
            Which one, and the answers.

        Returns
        -------
        dict
            The authored mapping, and its English rendering.

        Raises
        ------
        HTTPException
            404 if nothing builds that tag, 400 if the answers are not enough.
        """
        try:
            return current().build(body.kind, body.tag, body.answers)
        except Unknown as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.get("/playtest")
    def rehearsal() -> dict[str, Any]:
        """The playtest setup, with its pickers already resolved.

        The setup is the one the author used last, because iterating means
        running the same awkward corner twenty times and retyping "the bridge,
        at midnight, in a blizzard" twenty times is how people stop iterating.

        Returns
        -------
        dict
            The remembered setup, and the options for each of its pickers.
        """
        return current().rehearsal()

    @router.post("/playtest", status_code=201)
    def playtest(body: Annotated[Trial, Body()]) -> dict[str, Any]:
        """Open a playthrough of the pack **as it stands**, unsaved and all.

        The single most important feature for keeping an author engaged, and
        the one the v0 wizard could not offer: nothing was playable until
        everything was done. Compiling never touches the disk, so this really
        is the project in memory — half-finished objects dropped with a note
        rather than a crash.

        The session goes into the ordinary registry, so the answer is a
        session id and the *game* client plays it. Two front-ends, one
        engine: a playtest is a playthrough, not a special mode.

        Parameters
        ----------
        body : Trial
            Where and how to begin.

        Returns
        -------
        dict
            The opening frame, with the session id to address it by.

        Raises
        ------
        HTTPException
            409 if this service holds no sessions, 400 if the project will not
            open as a game.
        """
        if registry is None:
            raise HTTPException(
                status_code=409,
                detail="this service holds no playthroughs, so it cannot play one",
            )
        try:
            setup = PlaytestSetup.model_validate(
                {
                    "seed": body.seed,
                    "startLocation": body.start_location,
                    "startTick": body.start_tick,
                    "weather": body.weather,
                    "items": body.items,
                    "background": body.background,
                    "spend": body.spend,
                    "combatMode": body.combat_mode,
                }
            )
            session = start_from(current().project, setup)
        except (ContentError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        # Remembered only once it has opened, so a setup that will not start
        # is not the one waiting in the form next time.
        current().rehearse(setup)
        return frame_of(registry.add(session), session)

    @router.post("/export")
    def export(
        into: Annotated[str | None, Body(embed=True)] = None,
    ) -> dict[str, Any]:
        """Write the pack out as one file somebody else can open.

        Refused while the pack has errors. Saving is never blocked — an author
        has to be able to stop mid-thought — but handing somebody a pack that
        will not load is a different thing, and the one place the wizard is
        allowed to say no.

        Parameters
        ----------
        into : str or None
            Where to write it. None writes beside the pack.

        Returns
        -------
        dict
            The path written, and how big it is.

        Raises
        ------
        HTTPException
            400 with the errors, when there are any.
        """
        try:
            written = export_pack(
                current().project, None if into is None else Path(into)
            )
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"path": str(written), "bytes": written.stat().st_size}

    @router.post("/save")
    def save() -> dict[str, Any]:
        """Write every changed file.

        Returns
        -------
        dict
            The frame, with the files written.

        Raises
        ------
        HTTPException
            400 if a file could not be written.
        """
        try:
            written = current().save()
        except (ContentError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened({"saved": written})

    return router


def _found(read: Any) -> dict[str, Any]:
    """Run a studio lookup, turning a missing screen into a 404.

    Parameters
    ----------
    read : callable
        The lookup.

    Returns
    -------
    dict
        The screen.

    Raises
    ------
    HTTPException
        404, with what the studio said about it.
    """
    try:
        found: dict[str, Any] = read()
    except Unknown as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return found
