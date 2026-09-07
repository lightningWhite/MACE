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
        }


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
