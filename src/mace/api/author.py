"""The authoring service: one HTTP surface over `mace.wizard.studio`.

The twin of `mace.api.app`, and it obeys the same rule. It renders screens the
studio projects and posts answers back through `Step.write`; it holds no
questions, no vocabulary, and no opinion about what a location is. A step type
is added in `mace.wizard`, not here.

**This one writes to the author's disk**, which the session service never
does, and that is the whole reason it is a separate router mounted only when
somebody asks for it. `mace author --web` binds it to localhost and opens one
pack; there is no authentication, no second pack, and no path in the API that
names a file. Serving it to a network would be handing that network a
filesystem, so do not.

One pack per process, the way `mace author` is one pack per terminal. That is
not a limitation being worked around: a project holds unsaved edits in memory,
and two of them behind one process would be two authors quietly overwriting
each other.

See docs/09-authoring-and-wizard.md § CLI and web parity.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException

from mace.api.app import Wire
from mace.content import ContentError
from mace.wizard.studio import Studio, Unknown, frame

__all__ = ["Answer", "Built", "Made", "Road", "author_routes"]


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


def author_routes(studio: Studio) -> APIRouter:
    """Build the authoring routes over one open pack.

    Parameters
    ----------
    studio : Studio
        The pack being edited. Held for the life of the process.

    Returns
    -------
    APIRouter
        The routes, ready to include under `/api/author`.
    """
    router = APIRouter(prefix="/api/author", tags=["authoring"])

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
        return frame(studio, screen)

    # ── Reading ───────────────────────────────────────────────────────────

    @router.get("")
    def desk() -> dict[str, Any]:
        """The task list, and nothing else.

        Returns
        -------
        dict
            The frame, with no screen.
        """
        return screened()

    @router.get("/vocabulary")
    def vocabulary() -> dict[str, Any]:
        """The condition and effect cascades, with this pack's options on them.

        Returns
        -------
        dict
            `conditions` and `effects`.
        """
        return studio.vocabulary()

    @router.get("/map")
    def atlas() -> dict[str, Any]:
        """The world map as the author has drawn it so far.

        Returns
        -------
        dict
            Places and roads.
        """
        return studio.atlas()

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
        return _found(lambda: studio.preview(collection, object_id))

    @router.get("/graph")
    def graph() -> dict[str, Any]:
        """Every scene, what leads to it, and what it leads to.

        Returns
        -------
        dict
            The graph, with reachability already worked out — the same answer
            `mace validate` gives, because it is the same code.
        """
        return studio.graph()

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
            studio.link(body.origin, body.destination, body.ticks, name=body.name)
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened(studio.atlas())

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
        if not studio.unlink(route_id):
            raise HTTPException(
                status_code=404, detail=f"there is no `{route_id}` to rub out"
            )
        return screened(studio.atlas())

    @router.get("/problems")
    def problems() -> dict[str, Any]:
        """Everything the validator found, worst first.

        Returns
        -------
        dict
            The problem list.
        """
        return {"problems": studio.report()}

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
        return screened(_found(lambda: studio.section(section_id)))

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
        return screened(_found(lambda: studio.object(collection)))

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
        return screened(_found(lambda: studio.object(collection, object_id)))

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
            changed = studio.answer(body.collection, body.step, body.value, body.object)
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
            made = studio.create(
                collection, body.name, section=body.section, answers=body.answers
            )
        except Unknown as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ContentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return screened(studio.object(collection, made))

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
        if not studio.delete(collection, object_id):
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
            return studio.build(body.kind, body.tag, body.answers)
        except Unknown as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

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
            written = studio.save()
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
