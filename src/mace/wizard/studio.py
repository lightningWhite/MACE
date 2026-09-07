"""A pack held open for editing, and one shape for everything a client is told.

`mace.session` is this module's twin. A session holds a playthrough open and
hands a front-end frames; a studio holds a *project* open and hands an
authoring front-end screens. Both exist for the same reason: the terminal was
the only thing that could drive the wizard, because the wizard's four screens
lived inside `mace.cli.author` as a loop over `input()`. The steps were always
data — that is what phase 4 was for — but nothing had ever turned the screens
*around* them into data as well.

So this is the flow graph made renderable by something that is not a terminal.
Three things it adds over `mace.wizard.flow`, and none of them is a rule:

- **Options are resolved.** A `Select` on the wire carries the list a `Query`
  produced, because a browser cannot ask the catalog a question mid-render.
  This is the piece that makes a form possible at all.
- **Screens are described.** The task list, a section's contents, one object's
  steps: the same three screens the terminal walks, as JSON.
- **The cascade is data too.** The condition and effect vocabularies ship with
  their questions, so a web client renders the builder rather than reimplements
  it — and a tag added to `mace.wizard.builders` appears in the browser without
  anybody touching the browser.

What it does *not* do is decide anything. Every answer goes through `Step.write`
and lands in the project's own document, comments and all; every problem comes
from the same validator `mace validate` runs. A bug that shows up in a web form
is a bug in the wizard, or it is a bug in the JSON.

See docs/09-authoring-and-wizard.md § CLI and web parity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mace.content import ContentError
from mace.content.validation import Problem, Severity
from mace.wizard.builders import (
    CONDITIONS,
    EFFECTS,
    Ask,
    Recipe,
    build_condition,
    build_effect,
    recipe_for,
)
from mace.wizard.fields import (
    ConditionBuilder,
    EffectBuilder,
    Field,
    Fixed,
    MapEditor,
    MultiSelect,
    Number,
    Repeat,
    Select,
    StatAllocator,
    Text,
    TextList,
)
from mace.wizard.flow import Flow, Step, answered, slug
from mace.wizard.flows import FLOWS, GAME
from mace.wizard.language import Names, say_conditions, say_effects
from mace.wizard.project import Project
from mace.wizard.query import Catalog, Option, Query
from mace.wizard.tasks import SECTIONS, Section, TaskList, review

__all__ = ["Studio", "Unknown", "frame", "vocabulary"]

#: The binding target that stands for the game manifest rather than an object.
GAME_COLLECTION = "game"


class Unknown(Exception):
    """A client asked for a screen that is not there.

    Its own exception rather than a `KeyError` so an HTTP layer can answer 404
    without guessing which lookups were the client's fault.
    """


@dataclass(slots=True)
class Studio:
    """One pack, open for editing.

    Attributes
    ----------
    project : Project
        The pack. Held as the author's own raw mappings, so an object the
        models would reject is still something a form can show and fix.
    """

    project: Project

    @classmethod
    def open(cls, root: Path, *search: Path) -> Studio:
        """Open a pack on disk.

        Parameters
        ----------
        root : Path
            The pack directory.
        *search : Path
            Where its dependencies live.

        Returns
        -------
        Studio
            The open pack.

        Raises
        ------
        ContentError
            If there is no readable `pack.yml`.
        """
        return cls(Project.open(root, *search))

    @property
    def catalog(self) -> Catalog:
        """What exists, for the pickers.

        Rebuilt on every read rather than cached: an answer can create the
        thing the next question offers, and a stale picker is the one bug that
        would make the web forms feel like a different tool from the terminal.

        Returns
        -------
        Catalog
            The catalog over this project.
        """
        return Catalog(self.project)

    @property
    def names(self) -> Names:
        """The naming service, for rendering conditions in English.

        Returns
        -------
        Names
            Naming that reads the project's raw objects and its libraries.
        """
        return Names(
            library=self.project.dependencies,
            within=self.project.manifest.id,
            catalog=self.catalog,
        )

    # ── The three screens ─────────────────────────────────────────────────

    def desk(self) -> dict[str, Any]:
        """The task list: where the pack stands, right now.

        Nothing is cached, because the point of the screen is that it tells
        the truth about a pack somebody may have hand-edited between sessions.

        Returns
        -------
        dict
            JSON-safe.
        """
        listed: TaskList = review(self.project)
        return {
            "name": listed.name,
            "percent": listed.percent,
            "problems": listed.problems,
            "errors": listed.errors,
            "tasks": [
                {
                    "section": task.section.id,
                    "title": task.section.title,
                    "help": task.section.help,
                    "state": task.state.value,
                    "summary": task.summary,
                    "note": task.note,
                    "errors": task.errors,
                    "flow": task.section.flow,
                    "collections": list(task.section.collections),
                }
                for task in listed.tasks
            ],
        }

    def section(self, section_id: str) -> dict[str, Any]:
        """One section's contents, and what may be made in it.

        Parameters
        ----------
        section_id : str
            The section.

        Returns
        -------
        dict
            JSON-safe.

        Raises
        ------
        Unknown
            If there is no such section.
        """
        found = _section(section_id)
        catalog = self.catalog
        held = [
            {
                "collection": collection,
                "id": option.value,
                "label": option.label,
                "unfinished": (
                    bool(FLOWS[collection].unanswered(self.project, option.value))
                    if collection in FLOWS
                    else False
                ),
            }
            for collection in found.collections
            for option in Query(
                collection, scope="project", where=found.where or {}
            ).options(catalog)
        ]
        return {
            "section": found.id,
            "title": found.title,
            "help": found.help,
            # The game manifest is one object rather than a collection, and a
            # client opens it directly rather than picking it off a list.
            "manifest": found.id == "game",
            "creates": [one for one in found.collections if one in FLOWS],
            "objects": held,
            "problems": [
                _problem(one) for one in review(self.project).task(found.id).problems
            ],
        }

    def atlas(self) -> dict[str, Any]:
        """The world map as the author has drawn it so far.

        Not the player's atlas: this one has no fog of war, no weather and no
        opinion about where the player has been. It is the shape of the pack,
        which is the thing an author drags around.

        Positions come back as the author wrote them, `null` included. A place
        with no `mapPosition` is a place the author has not put anywhere yet,
        and the client laying it out is *not* the same as the author having
        chosen — so the wizard says which is which and lets the client decide
        what to draw.

        Returns
        -------
        dict
            JSON-safe: `places` and `roads`.
        """
        places = [
            {
                "id": local_id,
                "name": str(self._read("locations", local_id, "name") or local_id),
                "x": _coordinate(self._read("locations", local_id, "mapPosition"), "x"),
                "y": _coordinate(self._read("locations", local_id, "mapPosition"), "y"),
                "exits": [
                    str(one.get("to"))
                    for one in _sequence(self._read("locations", local_id, "exits"))
                    if isinstance(one, Mapping) and one.get("to") is not None
                ],
            }
            for local_id in self.project.ids("locations")
        ]
        roads = [
            {
                "id": local_id,
                "name": _plain(self._read("routes", local_id, "name")),
                "from": _plain(self._read("routes", local_id, "from")),
                "to": _plain(self._read("routes", local_id, "to")),
                "ticks": _plain(self._read("routes", local_id, "ticks")),
                "bidirectional": self._read("routes", local_id, "bidirectional")
                is not False,
            }
            for local_id in self.project.ids("routes")
        ]
        return {"places": places, "roads": roads}

    def graph(self) -> dict[str, Any]:
        """Every scene, what leads to it, and what it leads to.

        The other half of what a browser is for. A scene graph is not an
        authoring *step* — nothing here writes — but it is the thing an author
        cannot hold in their head past about a dozen scenes, and the question
        it answers is the one the validator already asks: is there any way in?

        Reachability is computed from the compiled pack, so it is the same
        answer `mace validate` gives. A scene reachable only from itself is
        unreachable, which is the rule that makes a `goto` loop show up as an
        island rather than as a healthy corner of the map.

        Returns
        -------
        dict
            JSON-safe: `scenes`, each with the scenes it leads to, and
            `entrances` — the scenes something outside the scene graph points
            at, which are the roots the rest hangs off.
        """
        from mace.content.validation import _each_definition, _scene_targets

        loaded = self.project.compile()
        pack = loaded.library.pack(self.project.manifest.id)

        leads: dict[str, list[str]] = {}
        entrances: set[str] = set()
        for local_id in sorted(pack.scenes):
            leads[local_id] = sorted(
                _local(one)
                for one in _scene_targets(loaded.library, pack, pack.scenes[local_id])
                if _local(one) in pack.scenes
            )

        for collection, _local_id, definition in _each_definition(pack):
            if collection == "scenes":
                continue
            entrances.update(
                _local(one) for one in _scene_targets(loaded.library, pack, definition)
            )
        if pack.game is not None:
            entrances.update(
                _local(one) for one in _scene_targets(loaded.library, pack, pack.game)
            )

        reached = _walk(entrances & set(pack.scenes), leads)
        return {
            "entrances": sorted(entrances & set(pack.scenes)),
            "scenes": [
                {
                    "id": local_id,
                    "prompt": _plain(pack.scenes[local_id].prompt),
                    "leadsTo": leads[local_id],
                    "entrance": local_id in entrances,
                    "reachable": local_id in reached,
                    "ends": _ends(pack.scenes[local_id]),
                }
                for local_id in sorted(pack.scenes)
            ],
            "unreadable": [str(error) for error in self.project.unreadable],
            "dropped": sorted(_dropped(loaded, "scenes")),
        }

    def link(
        self,
        origin: str,
        destination: str,
        ticks: int,
        *,
        name: str | None = None,
    ) -> str:
        """Draw a road between two places, and the ways onto it.

        One operation rather than three, because drawing a road is one
        authoring *intention*. A route is a road; an exit is the option to walk
        down it. A wizard that made the route and left the exits to the author
        would be a wizard whose maps open with a validator note at every place,
        which is the rule the world starter already follows.

        Parameters
        ----------
        origin, destination : str
            Local ids of the two places.
        ticks : int
            How long it takes in fair weather.
        name : str or None
            What to call it. None names it after where it goes.

        Returns
        -------
        str
            The new route's local id.

        Raises
        ------
        ContentError
            If either end is not there, they are the same place, or a road
            between them already exists.
        """
        for end in (origin, destination):
            if self.project.get("locations", end) is None:
                raise ContentError(f"there is no `{end}` to draw a road to")
        if origin == destination:
            raise ContentError("a road has to go somewhere else")

        local_id = slug(name) if name else f"{origin}-to-{destination}"
        if self.project.get("routes", local_id) is not None:
            raise ContentError(f"`{local_id}` is already there", collection="routes")

        self.project.put(
            "routes",
            {
                "id": local_id,
                "name": name or f"The road to {self._label(destination)}",
                "from": origin,
                "to": destination,
                "ticks": ticks,
            },
        )
        self._open(origin, destination, local_id)
        self._open(destination, origin, local_id)
        return local_id

    def unlink(self, route_id: str) -> bool:
        """Rub out a road, and the ways onto it.

        The exits go with it for the same reason they came with it: an exit
        naming a route that is not there is a dangling reference, and leaving
        the author to find two of them is not a tool being helpful.

        Parameters
        ----------
        route_id : str
            The road's local id.

        Returns
        -------
        bool
            Whether there was one to rub out.
        """
        if self.project.get("routes", route_id) is None:
            return False
        for local_id in self.project.ids("locations"):
            body = self.project.get("locations", local_id)
            if body is None:  # pragma: no cover — it was just listed
                continue
            kept = [
                one
                for one in _sequence(body.get("exits"))
                if not (isinstance(one, Mapping) and one.get("route") == route_id)
            ]
            if len(kept) != len(_sequence(body.get("exits"))):
                self.project.put("locations", {**body, "exits": kept})
        return self.project.drop("routes", route_id)

    def _open(self, at: str, to: str, route_id: str) -> None:
        """Give one place the option of walking down one road.

        Parameters
        ----------
        at : str
            The place the exit is on.
        to : str
            Where it leads.
        route_id : str
            The road it takes.
        """
        body = self.project.get("locations", at)
        if body is None:  # pragma: no cover — the caller checked
            return
        exits = list(_sequence(body.get("exits")))
        if any(isinstance(one, Mapping) and one.get("to") == to for one in exits):
            return
        exits.append({"to": to, "route": route_id})
        self.project.put("locations", {**body, "exits": exits})

    def _read(self, collection: str, local_id: str, key: str) -> Any:
        """One field of one object, read through `extends`.

        Parameters
        ----------
        collection : str
            Which collection.
        local_id : str
            The object.
        key : str
            The field.

        Returns
        -------
        object
            The value, or None.
        """
        return self.project.effective(collection, local_id, key)

    def _label(self, local_id: str) -> str:
        """What a place is called, for naming a road after it.

        Parameters
        ----------
        local_id : str
            The place.

        Returns
        -------
        str
            Its name, or a readable form of its id.
        """
        named = self._read("locations", local_id, "name")
        return str(named) if named else local_id.replace("-", " ")

    def object(self, collection: str, object_id: str | None = None) -> dict[str, Any]:
        """One object's steps, with everything a form needs to draw them.

        Parameters
        ----------
        collection : str
            The collection, or `game` for the manifest.
        object_id : str or None
            The object's local id. Ignored for the manifest.

        Returns
        -------
        dict
            JSON-safe.

        Raises
        ------
        Unknown
            If the collection has no flow, or the object is not there.
        """
        flow = _flow(collection)
        if flow.collection is not None:
            if object_id is None:
                raise Unknown(f"`{collection}` needs to know which object")
            if self.project.get(flow.collection, object_id) is None:
                raise Unknown(f"there is no `{object_id}` in `{collection}`")

        catalog = self.catalog
        return {
            "collection": collection,
            "id": object_id,
            "title": flow.title,
            "noun": flow.noun,
            "label": (
                flow.title
                if object_id is None
                else catalog.label(object_id, flow.collection or collection)
            ),
            "steps": [self._step(one, object_id, catalog) for one in flow.steps],
        }

    def step(
        self, collection: str, step_id: str, object_id: str | None = None
    ) -> dict[str, Any]:
        """One step on its own, for a form that asks one question at a time.

        Parameters
        ----------
        collection : str
            The collection, or `game`.
        step_id : str
            The step's id.
        object_id : str or None
            Which object.

        Returns
        -------
        dict
            JSON-safe.

        Raises
        ------
        Unknown
            If there is no such step.
        """
        flow = _flow(collection)
        try:
            found = flow.step(step_id)
        except KeyError as error:
            raise Unknown(str(error)) from error
        return self._step(found, object_id, self.catalog)

    # ── Changing things ───────────────────────────────────────────────────

    def answer(
        self,
        collection: str,
        step_id: str,
        value: Any,
        object_id: str | None = None,
    ) -> dict[str, Any]:
        """Record one answer.

        The value is the authored one, not typed text: a browser has already
        turned a click into `fantasy.core:gold`, and a parser that ran here
        would be a second, worse copy of the field types.

        Parameters
        ----------
        collection : str
            The collection, or `game`.
        step_id : str
            Which question.
        value : object
            The answer. None clears the field rather than writing a null.
        object_id : str or None
            Which object.

        Returns
        -------
        dict
            The step as it now stands.

        Raises
        ------
        Unknown
            If there is no such step or object.
        ContentError
            If the object this binds to does not exist.
        """
        flow = _flow(collection)
        try:
            found = flow.step(step_id)
        except KeyError as error:
            raise Unknown(str(error)) from error
        found.write(self.project, value, object_id)
        return self._step(found, object_id, self.catalog)

    def create(
        self,
        collection: str,
        name: str,
        *,
        section: str | None = None,
        answers: Mapping[str, Any] | None = None,
    ) -> str:
        """Make a new object, from as little as its name.

        An object has to exist before anything can point at it, and it has to
        be pointable-at long before it is finished — so this asks the least it
        can. The id is derived from the name the same way the terminal derives
        it, because a browser and a terminal that named the same place
        differently would be two tools.

        Parameters
        ----------
        collection : str
            Which collection.
        name : str
            What the author called it.
        section : str or None
            The section it is being made in, for the fields that section
            fixes. An item made under Items is `kind: item` without anybody
            answering a question about it.
        answers : mapping or None
            Any other steps already answered, by step id.

        Returns
        -------
        str
            The new object's local id.

        Raises
        ------
        Unknown
            If the collection has no flow, or there is no such section.
        ContentError
            If the name is empty, or the id it makes is taken.
        """
        flow = _flow(collection)
        if flow.collection is None:
            raise Unknown("the game manifest is not something you create")
        if not name.strip():
            raise ContentError(
                f"a new {flow.noun} needs a name", collection=flow.collection
            )

        local_id = slug(name)
        if self.project.get(flow.collection, local_id) is not None:
            raise ContentError(
                f"`{local_id}` is already there", collection=flow.collection
            )

        body: dict[str, Any] = {"id": local_id}
        if any(step.binding.leaf == "name" for step in flow.steps):
            body["name"] = name
        if section is not None:
            body.update(_section(section).where or {})
        self.project.put(flow.collection, body)

        for step_id, value in (answers or {}).items():
            if answered(value):
                flow.step(step_id).write(self.project, value, local_id)
        return local_id

    def delete(self, collection: str, object_id: str) -> bool:
        """Remove an object.

        Nothing is checked first. An author deleting a location that scenes
        point at gets a validated pack full of dangling references and a
        problem list saying so, which is the same thing they would get by
        deleting it from the file — and a wizard that refused would be a wizard
        that could not be used to restructure a world.

        Parameters
        ----------
        collection : str
            Which collection.
        object_id : str
            The object's local id.

        Returns
        -------
        bool
            Whether there was one to remove.
        """
        return self.project.drop(collection, object_id)

    def save(self) -> list[str]:
        """Write every changed file.

        Returns
        -------
        list of str
            The paths written, relative to the pack root.
        """
        return [str(path) for path in self.project.save()]

    def report(self) -> list[dict[str, Any]]:
        """Everything the validator found, worst first.

        Returns
        -------
        list of dict
            JSON-safe problems.
        """
        order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.NOTE: 2}
        problems = sorted(
            self.project.report().problems, key=lambda one: order[one.severity]
        )
        return [_problem(one) for one in problems]

    # ── The cascade ───────────────────────────────────────────────────────

    def build(self, kind: str, tag: str, answers: Mapping[str, Any]) -> dict[str, Any]:
        """Turn a cascade's answers into an authored condition or effect.

        The round-trip through the model happens here rather than in the
        client, which is what keeps a browser from being able to write content
        the loader would reject.

        Parameters
        ----------
        kind : str
            `conditions` or `effects`.
        tag : str
            Which one to build.
        answers : mapping
            Ask key to the author's answer.

        Returns
        -------
        dict
            The authored mapping, and the English rendering of it.

        Raises
        ------
        Unknown
            If nothing builds that tag.
        ValueError
            If the answers do not make a valid condition or effect.
        """
        recipes = CONDITIONS if kind == "conditions" else EFFECTS
        try:
            recipe = recipe_for(tag, recipes)
        except KeyError as error:
            raise Unknown(str(error)) from error
        built = (
            build_condition(recipe, answers)
            if kind == "conditions"
            else build_effect(recipe, answers)
        )
        return {"authored": built, "said": self.say(kind, [built])}

    def vocabulary(self) -> dict[str, Any]:
        """The cascade, with its pickers resolved against this pack.

        Returns
        -------
        dict
            `conditions` and `effects`, each a list of recipes whose asks
            carry the options this project can actually offer.
        """
        return vocabulary(self.catalog)

    def say(self, kind: str, authored: Sequence[Any]) -> str:
        """Render authored conditions or effects in English.

        Parameters
        ----------
        kind : str
            `conditions` or `effects`.
        authored : sequence
            The authored mappings.

        Returns
        -------
        str
            A phrase, or a plain note when one of them will not build. Content
            in a project is allowed to be wrong for a while, and a renderer
            that raised would go blank exactly where an author is looking.
        """
        from mace.model import Condition, Effect

        model = Condition if kind == "conditions" else Effect
        try:
            parsed = [model.model_validate(one) for one in authored]
        except ValueError:
            count = len(authored)
            noun = "condition" if kind == "conditions" else "effect"
            return f"{count} {noun}{'' if count == 1 else 's'}, one of which is wrong"
        if kind == "conditions":
            return say_conditions(parsed, self.names)  # type: ignore[arg-type]
        return say_effects(parsed, self.names)  # type: ignore[arg-type]

    # ── Projecting one step ───────────────────────────────────────────────

    def _step(
        self, one: Step, object_id: str | None, catalog: Catalog
    ) -> dict[str, Any]:
        """One question, its answer, and everything a form needs to draw it.

        Parameters
        ----------
        one : Step
            The step.
        object_id : str or None
            Which object.
        catalog : Catalog
            What exists.

        Returns
        -------
        dict
            JSON-safe.
        """
        value = one.read(self.project, object_id)
        return {
            "id": one.id,
            "title": one.title,
            "help": one.help,
            "optional": one.optional,
            "binds": one.binds,
            "value": _plain(value),
            "described": one.field.describe(value, catalog),
            "answered": answered(value),
            "field": _field(one.field, catalog),
            "entries": self._entries(one.field, value),
        }

    def _entries(self, field: Field, value: Any) -> list[dict[str, Any]] | None:
        """The pieces of a field that holds several of something.

        `described` says what the whole answer is; this says what each piece
        of it is, which is what a front-end needs to show a list somebody can
        take one thing out of. The terminal computes the same lines itself,
        one screen at a time; a browser cannot, because it does not have the
        model or the naming service.

        Parameters
        ----------
        field : Field
            The field.
        value : object
            The authored value.

        Returns
        -------
        list of dict or None
            One entry per piece, or None for a field that holds one answer.
        """
        if isinstance(field, ConditionBuilder | EffectBuilder):
            kind = "conditions" if isinstance(field, ConditionBuilder) else "effects"
            single = isinstance(field, ConditionBuilder) and field.single
            authored = [value] if single and value is not None else _sequence(value)
            return [
                {"authored": _plain(one), "said": self.say(kind, [one])}
                for one in authored
            ]

        if isinstance(field, Repeat):
            return [
                {"values": _plain(one), "summary": _summarise(one)}
                for one in _sequence(value)
            ]

        if isinstance(field, StatAllocator):
            spread = value if isinstance(value, Mapping) else {}
            return [
                {
                    "stat": name,
                    "base": _number_of(spread[name], "base"),
                    "max": _number_of(spread[name], "max"),
                }
                for name in sorted(spread)
            ]

        return None


def frame(studio: Studio, screen: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Everything a client is told after anything happens.

    One shape for every reply, the way `mace.session.frame` is, so a client has
    one renderer rather than one per endpoint — and so the header that says how
    many problems a pack has updates on every answer without anybody asking
    for it.

    Parameters
    ----------
    studio : Studio
        The open pack.
    screen : mapping or None
        Whatever the client asked for — a section, an object, a step.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "pack": {
            "id": studio.project.manifest.id,
            "name": studio.project.manifest.name,
            "kind": studio.project.manifest.kind,
            "version": str(studio.project.manifest.version),
        },
        "dirty": sorted(str(path) for path in studio.project.dirty),
        "unreadable": [str(error) for error in studio.project.unreadable],
        "desk": studio.desk(),
        "screen": dict(screen) if screen is not None else None,
    }


def vocabulary(catalog: Catalog | None = None) -> dict[str, Any]:
    """The condition and effect builders, as data a form can render.

    A tag added to `mace.wizard.builders` appears in the browser without
    anybody touching the browser, which is the same promise the terminal has
    and the reason the recipes were data in the first place.

    Parameters
    ----------
    catalog : Catalog or None
        What exists, so a "which item?" ask arrives with the items on it.
        None describes the vocabulary itself, before any pack is chosen.

    Returns
    -------
    dict
        `conditions` and `effects`, each a list of recipes.
    """
    return {
        "conditions": [_recipe(one, catalog) for one in CONDITIONS],
        "effects": [_recipe(one, catalog) for one in EFFECTS],
    }


# ── Rendering the pieces ──────────────────────────────────────────────────────


def _recipe(recipe: Recipe, catalog: Catalog | None = None) -> dict[str, Any]:
    """One way of building a condition or an effect, as data.

    Parameters
    ----------
    recipe : Recipe
        The recipe.
    catalog : Catalog or None
        What exists, for the asks that pick from content.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "tag": recipe.tag,
        "label": recipe.label,
        "group": recipe.group,
        "help": recipe.help,
        "bare": recipe.bare is not None,
        "asks": [_ask(one, catalog) for one in recipe.asks],
    }


def _ask(ask: Ask, catalog: Catalog | None = None) -> dict[str, Any]:
    """One question inside a recipe.

    Parameters
    ----------
    ask : Ask
        The question.
    catalog : Catalog or None
        What exists, for an ask that picks from content.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "key": ask.key,
        "title": ask.title,
        "help": ask.help,
        "default": _plain(ask.default),
        "field": _field(ask.field, catalog),
    }


def _field(one: Field, catalog: Catalog | None) -> dict[str, Any]:
    """A field type, with its options already resolved.

    Resolving here is the whole reason this module exists: a browser cannot
    ask the catalog a question in the middle of a render, so the wire carries
    the list a `Query` produced rather than the query.

    Parameters
    ----------
    one : Field
        The field.
    catalog : Catalog or None
        What exists. None leaves option lists out, for a recipe's asks, which
        are described before any project is chosen.

    Returns
    -------
    dict
        JSON-safe.
    """
    body: dict[str, Any] = {
        "kind": one.kind,
        "optional": one.optional,
        "interactive": one.interactive,
        "hint": one.hint(catalog) if catalog is not None else "",
    }

    if isinstance(one, Text):
        body["placeholder"] = one.placeholder
    elif isinstance(one, TextList):
        body["placeholder"] = one.placeholder
        body["minItems"] = one.min_items
    elif isinstance(one, Number):
        body["minimum"] = one.minimum
        body["maximum"] = one.maximum
        body["integer"] = one.integer
    elif isinstance(one, Select | MultiSelect):
        body["options"] = (
            [_option(found) for found in one.options.options(catalog)]
            if catalog is not None
            else _fixed(one.options)
        )
        body["allowCreate"] = one.allow_create
        if isinstance(one, MultiSelect):
            body["minItems"] = one.min_items
    elif isinstance(one, StatAllocator):
        body["points"] = one.points
        body["stats"] = list(one.stats)
    elif isinstance(one, ConditionBuilder):
        body["single"] = one.single
    elif isinstance(one, Repeat):
        body["of"] = one.of
        body["steps"] = [
            {
                "id": step.id,
                "title": step.title,
                "help": step.help,
                "binds": step.binds,
                "optional": step.optional,
                "field": _field(step.field, catalog),
            }
            for step in one.steps
            if isinstance(step, Step)
        ]
    elif isinstance(one, MapEditor):
        # Nothing of its own: the value is a pair of coordinates, and how to
        # collect them is exactly what separates a browser from a terminal.
        pass

    return body


def _fixed(source: Any) -> list[dict[str, str]]:
    """The options of a source that does not need a project to answer.

    Parameters
    ----------
    source : Source
        The option source.

    Returns
    -------
    list of dict
        The choices, or an empty list for a `Query`, which has nothing to say
        until a pack is open.
    """
    if not isinstance(source, Fixed):
        return []
    return [_option(one) for one in source.choices]


def _option(option: Option) -> dict[str, str]:
    """One thing an author can pick.

    Parameters
    ----------
    option : Option
        The option.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {"value": option.value, "label": option.label, "note": option.note}


def _problem(problem: Problem) -> dict[str, Any]:
    """One validation problem, as a client shows it.

    Parameters
    ----------
    problem : Problem
        The problem.

    Returns
    -------
    dict
        JSON-safe.
    """
    return {
        "severity": problem.severity.value,
        "message": problem.message,
        "pack": problem.pack,
        "path": None if problem.path is None else str(problem.path),
        "collection": problem.collection,
        "object": problem.object_id,
        "field": problem.field,
    }


def _section(section_id: str) -> Section:
    """One section of the task list, by id.

    Parameters
    ----------
    section_id : str
        The id.

    Returns
    -------
    Section
        The section.

    Raises
    ------
    Unknown
        If there is no such section.
    """
    for found in SECTIONS:
        if found.id == section_id:
            return found
    raise Unknown(f"no section `{section_id}`")


def _flow(collection: str) -> Flow:
    """The flow that authors a collection, or the game manifest's.

    Parameters
    ----------
    collection : str
        The collection name, or `game`.

    Returns
    -------
    Flow
        The flow.

    Raises
    ------
    Unknown
        If nothing authors it.
    """
    if collection == GAME_COLLECTION:
        return GAME
    found = FLOWS.get(collection)
    if found is None:
        raise Unknown(f"nothing authors `{collection}` yet")
    return found


def _dropped(loaded: Any, collection: str) -> set[str]:
    """Objects the loader could not build, so the graph can say they are gone.

    A scene that will not compile is not on the graph, and an author looking
    for it deserves to be told that rather than left to conclude they had
    deleted it.

    Parameters
    ----------
    loaded : Loaded
        What `Project.compile` returned.
    collection : str
        Which collection.

    Returns
    -------
    set of str
        Local ids.
    """
    return {
        problem.object_id
        for problem in loaded.problems
        if problem.collection == collection and problem.object_id is not None
    }


def _walk(roots: set[str], leads: dict[str, list[str]]) -> set[str]:
    """Everything reachable from a set of roots.

    Parameters
    ----------
    roots : set of str
        Where the player can get in.
    leads : dict
        Scene to the scenes it leads to.

    Returns
    -------
    set of str
        Every scene reachable, roots included.
    """
    seen = set(roots)
    frontier = list(roots)
    while frontier:
        for onward in leads.get(frontier.pop(), ()):
            if onward not in seen:
                seen.add(onward)
                frontier.append(onward)
    return seen


def _ends(scene: Any) -> bool:
    """Whether a scene is somewhere the player can be left standing.

    Parameters
    ----------
    scene : Scene
        The scene.

    Returns
    -------
    bool
        Whether it offers choices or leads anywhere. A scene that does
        neither hands control back to the location's menu, which is a fine
        thing to be and worth marking on a graph so it does not read as a
        dead end.
    """
    return not scene.choices and scene.goto is None


def _local(qualified: str) -> str:
    """The local half of a qualified id.

    Parameters
    ----------
    qualified : str
        `pack:id`, or a bare id.

    Returns
    -------
    str
        The id.
    """
    return qualified.split(":", 1)[-1]


def _coordinate(position: Any, axis: str) -> float | None:
    """One axis out of an authored map position.

    Parameters
    ----------
    position : object
        `{x: 0, y: 120}`, or None.
    axis : str
        `x` or `y`.

    Returns
    -------
    float or None
        The number, or None where the author has not placed it.
    """
    if not isinstance(position, Mapping):
        return None
    found = position.get(axis)
    return None if found is None else float(found)


def _sequence(value: Any) -> list[Any]:
    """Read a value that may be a list, a lone item, or nothing.

    Parameters
    ----------
    value : object
        The authored value.

    Returns
    -------
    list
        Its entries.
    """
    if value is None:
        return []
    if isinstance(value, str | Mapping):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _summarise(entry: Any) -> str:
    """Say what one repeat entry holds, for a list somebody edits.

    Parameters
    ----------
    entry : object
        The authored entry.

    Returns
    -------
    str
        `to: castle · route: road`.
    """
    if not isinstance(entry, Mapping):
        return str(entry)
    return " · ".join(f"{key}: {value}" for key, value in entry.items())


def _number_of(stat: Any, key: str) -> float | None:
    """One number out of a stat entry, which may be a bare value.

    Parameters
    ----------
    stat : object
        `{base: 32, max: 40}`, or `32`.
    key : str
        `base` or `max`.

    Returns
    -------
    float or None
        The number, or None where the author set none.
    """
    if isinstance(stat, Mapping):
        found = stat.get(key)
        return None if found is None else float(found)
    return float(stat) if key == "base" else None


def _plain(value: Any) -> Any:
    """Strip a round-trip YAML value back to something JSON can carry.

    The project holds the author's own objects — comments, key order and
    quoting attached — and those are exactly what must not go over a wire.

    Parameters
    ----------
    value : object
        An authored value.

    Returns
    -------
    object
        Plain dicts, lists, and scalars.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(inner) for key, inner in value.items()}
    if isinstance(value, str | bytes):
        return str(value) if isinstance(value, str) else value.decode()
    if isinstance(value, Sequence):
        return [_plain(inner) for inner in value]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)
