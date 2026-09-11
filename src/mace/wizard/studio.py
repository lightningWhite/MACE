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
from mace.content.discovery import MANIFEST_NAME, find_packs, read_yaml
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
from mace.wizard.flow import Flow, Step, answered, dig, slug
from mace.wizard.flows import FLOWS, GAME
from mace.wizard.language import Names, say_conditions, say_effects
from mace.wizard.notes import PlaytestSetup, ProjectNotes
from mace.wizard.project import Project
from mace.wizard.query import Catalog, Option, Query
from mace.wizard.tasks import SECTIONS, Section, TaskList, review

__all__ = ["Desk", "Studio", "Unknown", "frame", "vocabulary"]

#: The binding target that stands for the game manifest rather than an object.
GAME_COLLECTION = "game"

#: The shape a newly-seeded pool or ability starts at. `50` for an ability is
#: the engine's own neutral value — the same one an undeclared `strength`/
#: `speed` now falls back to (`Fighter.stat`) — so picking it here is a
#: no-op until the author changes it.
_STARTER_POOL: dict[str, float] = {"base": 10, "max": 10}
_STARTER_ABILITY: dict[str, float] = {"base": 50}

#: What a preview says about each kind of object, in the order it says it.
#: Deliberately short: a preview that listed every field would be the file
#: again, and the file is the thing an author already has.
_PREVIEW_FACTS: dict[str, tuple[tuple[str, str], ...]] = {
    "entities": (
        ("kind", "kind"),
        ("tags", "tags"),
        ("disposition", "disposition"),
        ("combat", "fights as"),
        ("scenes", "offers"),
        ("merchant", "keeps a stall"),
        ("item", "as an item"),
    ),
    "locations": (
        ("type", "type"),
        ("region", "region"),
        ("indoors", "indoors"),
        ("safe", "safe"),
        ("entities", "here"),
        ("scenes", "offers"),
        ("on_arrive", "on arrival"),
        ("encounters", "rolls"),
    ),
    "routes": (
        ("origin", "from"),
        ("destination", "to"),
        ("ticks", "ticks"),
        ("terrain", "terrain"),
        ("danger_level", "danger"),
        ("encounters", "rolls"),
    ),
    "scenes": (
        ("prompt", "offered as"),
        ("once", "once only"),
        ("goto", "leads to"),
        ("otherwise", "else"),
    ),
}


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
            JSON-safe: `places`, `roads`, and `regions`.
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
                "region": _plain(self._read("locations", local_id, "region")),
                "submapOf": _plain(self._read("locations", local_id, "submapOf")),
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
        regions = [
            {
                "id": local_id,
                "name": str(self._read("regions", local_id, "name") or local_id),
            }
            for local_id in self.project.ids("regions")
        ]
        return {"places": places, "roads": roads, "regions": regions}

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

    def preview(self, collection: str, object_id: str) -> dict[str, Any]:
        """One object as the engine will see it, not as the file writes it.

        This is the gap a form cannot close on its own. `extends` means the
        file is *not* the object: a troll that inherits from
        `fantasy.core:bridge-troll` and writes only `strength: 85` has eighty
        hitpoints, a combat profile, and an `env` response to the dark, none
        of which appear anywhere an author can see. Neither does a conditional
        description, which is three lines in a file and one line in play.

        So the preview is built from the **compiled** pack, and it says what
        was inherited rather than quietly presenting it as written. An author
        who cannot tell what they typed from what they got is an author who
        will retype it.

        Parameters
        ----------
        collection : str
            Which collection.
        object_id : str
            The object's local id.

        Returns
        -------
        dict
            JSON-safe. `built` is False for an object the models will not
            accept yet, and everything else is what could still be said about
            it — a preview that went blank exactly when an author broke
            something would be a preview nobody trusted.
        """
        held = self.project.get(collection, object_id)
        if held is None:
            raise Unknown(f"there is no `{object_id}` in `{collection}`")

        inherits = held.get("extends")
        loaded = self.project.compile()
        pack = loaded.library.pack(self.project.manifest.id)
        built = pack.collection(collection).get(object_id) if collection else None

        if built is None:
            return {
                "collection": collection,
                "id": object_id,
                "name": str(held.get("name") or object_id),
                "built": False,
                "inherits": _plain(inherits),
                "why": [
                    str(one) for one in loaded.problems if one.object_id == object_id
                ],
                "lines": [],
                "facts": [],
                "stats": [],
                "carries": [],
            }

        return {
            "collection": collection,
            "id": object_id,
            "name": str(getattr(built, "name", None) or object_id),
            "built": True,
            "inherits": _plain(inherits),
            "why": [],
            "lines": self._lines(built),
            "facts": self._facts(collection, built, held),
            "stats": _stats(built),
            "carries": self._carried(built),
        }

    def _lines(self, built: Any) -> list[dict[str, Any]]:
        """An object's description, with its conditions in English.

        Parameters
        ----------
        built : ContentModel
            The compiled object.

        Returns
        -------
        list of dict
            One entry per variant, in the order the engine tries them — first
            match wins, which is the thing a file does not make obvious.
        """
        described = getattr(built, "description", None) or ()
        if isinstance(described, str):
            # A background's description is a plain pitch, not conditional
            # text — the only collection where `description` is not the
            # usual tuple of `DescriptionLine`.
            return [{"text": described, "when": "always"}]
        return [
            {
                "text": line.text,
                "when": (
                    "always"
                    if not line.when
                    else self.say("conditions", [one.authored() for one in line.when])
                ),
            }
            for line in described
        ]

    def _facts(
        self, collection: str, built: Any, held: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        """The short answers about an object, and where each came from.

        Parameters
        ----------
        collection : str
            Which collection.
        built : ContentModel
            The compiled object.
        held : mapping
            What the author actually wrote, so an inherited value can say so.

        Returns
        -------
        list of dict
            Label, value, and whether the author wrote it themselves.
        """
        wanted = _PREVIEW_FACTS.get(collection, ())
        facts: list[dict[str, Any]] = []
        for field, label in wanted:
            value = getattr(built, field, None)
            if value in (None, (), [], {}, ""):
                continue
            facts.append(
                {
                    "label": label,
                    "value": _said(value),
                    "own": _camel(field) in held,
                }
            )
        return facts

    def _carried(self, built: Any) -> list[dict[str, Any]]:
        """What an object starts with, named rather than referenced.

        Parameters
        ----------
        built : ContentModel
            The compiled object.

        Returns
        -------
        list of dict
            Item, name, and quantity.
        """
        names = self.names
        return [
            {
                "item": entry.item,
                "name": names.of(entry.item, "entities"),
                "qty": entry.qty,
            }
            for entry in getattr(built, "inventory", None) or ()
        ]

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

        seeded = dict(answers or {})
        if body.get("kind") == "actor" and "entity.stats" not in seeded:
            vital, effort = self._pool_names()
            seeded["entity.stats"] = {
                vital: dict(_STARTER_POOL),
                effort: dict(_STARTER_POOL),
                "strength": dict(_STARTER_ABILITY),
                "speed": dict(_STARTER_ABILITY),
            }
        for step_id, value in seeded.items():
            if answered(value):
                flow.step(step_id).write(self.project, value, local_id)
        return local_id

    def _pool_names(self) -> tuple[str, str]:
        """This game's vital and effort pool names, in this project right now.

        Defaults the same way `GameRules` itself does, so a pack with no
        manifest yet — or one that hasn't touched `rules` — reads the same
        `hitpoints`/`stamina` the engine would fall back to.

        Returns
        -------
        tuple of str
            `(vitalPool, effortPool)`.
        """
        manifest = self.project.game or {}
        rules = manifest.get("rules")
        rules = rules if isinstance(rules, Mapping) else {}
        vital = rules.get("vitalPool")
        effort = rules.get("effortPool")
        return (
            str(vital) if vital else "hitpoints",
            str(effort) if effort else "stamina",
        )

    def _core_stats(self) -> dict[str, str]:
        """Stats the engine reads by name in this game, and what each does.

        Named dynamically against this project's own `vitalPool`/`effortPool`
        rather than hard-coding `hitpoints`/`stamina` — a sci-fi pack that
        renamed its vital pool to `hull-integrity` should see *that* marked,
        not a `hitpoints` it never declared. `strength`, `speed`, and
        `charisma` are the same name in every game, since the engine reads
        those three literally regardless of what a pack calls anything else.

        Returns
        -------
        dict
            Stat name to a one-line explanation of what it does.
        """
        vital, effort = self._pool_names()
        return {
            vital: "The pool that ends the game when it runs out.",
            effort: "Spent making moves in a fight.",
            "strength": "Scales the damage a hit lands.",
            "speed": "Widens or narrows your timing window in a fight.",
            "charisma": "Sets the odds when haggling over a price.",
        }

    def _player_stat_names(self) -> tuple[str, ...]:
        """Every stat this game's player entity declares.

        Offered to a relative-value picker as "the player's own stat" to
        reference — the full list, not just the two pool roles
        `_core_stats` names, since a relative value can point at any of the
        player's own stats.

        Returns
        -------
        tuple of str
            Names, sorted. Empty if the game names no player entity yet, or
            that entity declares no stats.
        """
        manifest = self.project.game or {}
        player = manifest.get("player")
        entity = player.get("entity") if isinstance(player, Mapping) else None
        if not entity:
            return ()
        stats = self.project.effective("entities", str(entity), "stats")
        return tuple(sorted(stats)) if isinstance(stats, Mapping) else ()

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

    # ── The playtest ──────────────────────────────────────────────────────

    def rehearsal(self) -> dict[str, Any]:
        """The playtest setup, and the pickers a client needs to change it.

        Resolved here for the same reason a `Select` is: a browser cannot ask
        the catalog what locations exist in the middle of drawing a form.

        The setup that comes back is the one the author used last, because
        iterating means running the same awkward corner twenty times and
        retyping "the bridge, at midnight, in a blizzard" twenty times is how
        people stop iterating.

        Returns
        -------
        dict
            The remembered setup, and the options for each of its pickers.
        """
        catalog = self.catalog
        return {
            "setup": _setup(self.project.notes.playtest),
            "locations": [
                _option(one)
                for one in Query("locations", scope="project").options(catalog)
            ],
            "weather": [
                _option(one) for one in Query("weatherConditions").options(catalog)
            ],
            "items": [
                _option(one)
                for one in Query("entities", where={"kind": "item"}).options(catalog)
            ],
        }

    def rehearse(self, setup: PlaytestSetup) -> PlaytestSetup:
        """Remember a playtest setup, so the next one opens with it.

        Parameters
        ----------
        setup : PlaytestSetup
            What the author asked for.

        Returns
        -------
        PlaytestSetup
            The same setup, now remembered.
        """
        notes = self.project.notes
        self.project.remember(
            ProjectNotes(
                format_version=notes.format_version,
                completed=notes.completed,
                notes=notes.notes,
                playtest=setup,
            )
        )
        return setup

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
            "field": _field(
                one.field, catalog, self._core_stats(), self._player_stat_names()
            ),
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
                {
                    "values": _plain(one),
                    "summary": _summarise(one),
                    "pieces": self._entry_pieces(field, one),
                }
                for one in _sequence(value)
            ]

        if isinstance(field, StatAllocator):
            spread = value if isinstance(value, Mapping) else {}
            return [
                {
                    "stat": name,
                    "base": _number_of(spread[name], "base"),
                    "max": _number_of(spread[name], "max"),
                    "relativeBase": _relative_of(spread[name], "base"),
                    "relativeMax": _relative_of(spread[name], "max"),
                }
                for name in sorted(spread)
            ]

        return None

    def _entry_pieces(
        self, field: Repeat, entry: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Said in English, per condition/effect sub-field of one entry.

        An entry's `values` already carries the authored half of a
        `choice.when` or `choice.effects` — this is the English half, keyed
        the same way the client keys its own local form state, so reopening
        an entry to edit it can seed `PiecesEditor` correctly instead of
        showing an existing condition as if it were never there.

        Parameters
        ----------
        field : Repeat
            The field, whose `steps` describe one entry.
        entry : object
            One authored entry.

        Returns
        -------
        dict
            Sub-step key to its pieces, for the condition/effect sub-steps
            only.
        """
        pieces: dict[str, list[dict[str, Any]]] = {}
        for sub in field.steps:
            if not isinstance(sub, Step) or not isinstance(
                sub.field, ConditionBuilder | EffectBuilder
            ):
                continue
            kind = (
                "conditions" if isinstance(sub.field, ConditionBuilder) else "effects"
            )
            single = isinstance(sub.field, ConditionBuilder) and sub.field.single
            found = dig(entry, sub.binding.path) if isinstance(entry, Mapping) else None
            authored = [found] if single and found is not None else _sequence(found)
            key = ".".join(sub.binding.path)
            pieces[key] = [
                {"authored": _plain(one), "said": self.say(kind, [one])}
                for one in authored
            ]
        return pieces


@dataclass(slots=True)
class Desk:
    """The one pack open for authoring right now, or none yet.

    `Studio` has no notion of "no pack" — a project is a directory on disk,
    and there is always exactly one. `Desk` is the thing that can be empty:
    it is what lets a process offer authoring before anyone has picked what
    to author, and switch what it holds without restarting — one pack open
    at a time, same as `mace author` always meant, just not fixed at
    process-start any more.

    Attributes
    ----------
    studio : Studio or None
        The open pack, or None before one is chosen.
    root : Path or None
        Where authorable game packs live — `games()` looks here. None means
        there is nothing to list or create, which is what a `Desk` wrapping
        the old one-pack-per-process shape means.
    search : Path or None
        Where those packs' dependencies live.
    """

    studio: Studio | None
    root: Path | None = None
    search: Path | None = None

    def games(self) -> list[dict[str, str]]:
        """Every authorable game pack under `root`.

        Reads each `pack.yml` raw rather than loading a `Library`, so a pack
        that does not validate yet is still listed and still openable — the
        same tolerance `Project` gives half-written content everywhere else.

        Returns
        -------
        list of dict
            `{id, name, path}` per game pack, sorted by id.

        Raises
        ------
        ContentError
            If no games directory is configured, or it cannot be read.
        """
        if self.root is None:
            raise ContentError("no games directory is configured")
        return self._packs_of_kind(self.root, "game")

    def libraries(self) -> list[dict[str, str]]:
        """Every library pack under `search`, for a new game to depend on.

        Returns
        -------
        list of dict
            `{id, name, path}` per library pack, sorted by id.

        Raises
        ------
        ContentError
            If no dependency directory is configured, or it cannot be read.
        """
        if self.search is None:
            raise ContentError("no dependency directory is configured")
        return self._packs_of_kind(self.search, "library")

    def _packs_of_kind(self, root: Path, kind: str) -> list[dict[str, str]]:
        """Every pack of one kind under a directory, tolerant of bad content.

        Reads each `pack.yml` raw rather than loading a `Library`, so a pack
        that does not validate yet is still listed and still openable — the
        same tolerance `Project` gives half-written content everywhere else.

        Parameters
        ----------
        root : Path
            Where to look.
        kind : str
            `game` or `library`.

        Returns
        -------
        list of dict
            `{id, name, path}` per matching pack, sorted by id.
        """
        found: list[dict[str, str]] = []
        for pack_root in find_packs(root):
            try:
                manifest = read_yaml(pack_root / MANIFEST_NAME)
            except (ContentError, OSError):
                continue
            if not isinstance(manifest, Mapping) or manifest.get("kind") != kind:
                continue
            pack_id = str(manifest.get("id") or pack_root.name)
            found.append(
                {
                    "id": pack_id,
                    "name": str(manifest.get("name") or pack_id),
                    "path": str(pack_root),
                }
            )
        return sorted(found, key=lambda one: one["id"])

    def open(self, pack_id: str, *, discard: bool = False) -> Studio:
        """Switch to an existing game pack.

        Parameters
        ----------
        pack_id : str
            The pack's id, as `games()` lists it.
        discard : bool
            Switch even though the current pack has unsaved edits, and lose
            them. They were never written to disk, so "discarding" them is
            nothing more than not stopping the switch that abandons them.

        Returns
        -------
        Studio
            The newly open pack.

        Raises
        ------
        ContentError
            If the current pack has unsaved edits and `discard` was not
            asked for, or there is no such game.
        """
        if not discard:
            self._refuse_if_dirty()
        match = next((one for one in self.games() if one["id"] == pack_id), None)
        if match is None:
            raise ContentError(f"no game `{pack_id}` here")
        search = () if self.search is None else (self.search,)
        self.studio = Studio.open(Path(match["path"]), *search)
        return self.studio

    def create(
        self,
        name: str,
        requires: Mapping[str, str] | None = None,
        *,
        discard: bool = False,
    ) -> Studio:
        """Start a new game pack and open it.

        Parameters
        ----------
        name : str
            Its title. The id and directory are derived from it, the same
            way `Studio.create` derives an object's id from its name.
        requires : mapping or None
            Pack id to version range.
        discard : bool
            Start the new pack even though the current one has unsaved
            edits, and lose them — see `open`.

        Returns
        -------
        Studio
            The newly created, open pack.

        Raises
        ------
        ContentError
            If no games directory is configured, the current pack has
            unsaved edits and `discard` was not asked for, or a pack already
            exists at the derived path.
        """
        if self.root is None:
            raise ContentError("no games directory is configured")
        if not discard:
            self._refuse_if_dirty()
        local_id = slug(name)
        search = () if self.search is None else (self.search,)
        project = Project.create(
            self.root / local_id,
            *search,
            pack_id=local_id,
            name=name,
            kind="game",
            requires=requires,
        )
        self.studio = Studio(project)
        return self.studio

    def _refuse_if_dirty(self) -> None:
        """Stop a switch that would lose unsaved edits silently.

        Raises
        ------
        ContentError
            If the currently open pack has unsaved changes.
        """
        if self.studio is not None and self.studio.project.dirty:
            raise ContentError(
                "this pack has unsaved changes — save them first, or they will be lost"
            )


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
        "dependsOn": ask.depends_on,
        "field": _field(ask.field, catalog),
    }


def _field(
    one: Field,
    catalog: Catalog | None,
    core: Mapping[str, str] | None = None,
    player_stats: Sequence[str] = (),
) -> dict[str, Any]:
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
    core : mapping or None
        Stat name to what it does, for a `StatAllocator` — resolved by the
        caller against *this* game's own `vitalPool`/`effortPool`, since a
        recipe's ask has no project to ask and never carries one.
    player_stats : sequence of str
        Every stat the player entity declares, for a `StatAllocator`'s
        relative-value picker to offer — "3x the player's own `strength`"
        needs a name to pick from that isn't limited to `core`'s two pool
        roles.

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
            body["freeText"] = one.free_text
    elif isinstance(one, StatAllocator):
        body["points"] = one.points
        body["stats"] = list(one.stats)
        body["core"] = dict(core or {})
        body["playerStats"] = list(player_stats)
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
                "field": _field(step.field, catalog, core, player_stats),
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


def _setup(setup: PlaytestSetup) -> dict[str, Any]:
    """One playtest setup, every field on it.

    Written out rather than dumped: a content model serializes through
    `authored()`, which writes the *smallest* content that reproduces it, and
    a form needs the seed on it even when the seed is the one it started with.

    Parameters
    ----------
    setup : PlaytestSetup
        The remembered setup.

    Returns
    -------
    dict
        JSON-safe, keyed the way the wire is.
    """
    return {
        "seed": setup.seed,
        "startLocation": setup.start_location,
        "startTick": setup.start_tick,
        "weather": setup.weather,
        "items": dict(setup.items),
        "background": setup.background,
        "spend": dict(setup.spend),
        "combatMode": setup.combat_mode,
    }


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
    return {
        "value": option.value,
        "label": option.label,
        "note": option.note,
        "scope": option.scope,
    }


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


def _stats(built: Any) -> list[dict[str, Any]]:
    """An object's statblock as the engine reads it, inheritance included.

    Parameters
    ----------
    built : ContentModel
        The compiled object.

    Returns
    -------
    list of dict
        Stat, base, and cap, in name order. JSON-safe — a `base`/`max`
        authored `relativeToPlayer` comes back compiled into a `RelativeStat`
        model, not a plain number, so it is rendered back to the same
        wrapper shape an author would write.
    """
    from mace.model.entity import RelativeStat

    def value(raw: Any) -> Any:
        if isinstance(raw, RelativeStat):
            return {"relativeToPlayer": raw.authored()}
        return raw

    declared = getattr(built, "stats", None) or {}
    return [
        {
            "stat": name,
            "base": value(declared[name].base),
            "max": value(declared[name].max),
            "customizable": declared[name].customizable,
        }
        for name in sorted(declared)
    ]


def _said(value: Any) -> str:
    """One field of a preview, as a line somebody reads.

    Parameters
    ----------
    value : object
        The compiled value.

    Returns
    -------
    str
        A phrase.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, Sequence):
        return ", ".join(_said(one) for one in value)
    named = getattr(value, "profile", None) or getattr(value, "id", None)
    return str(named) if named else "yes"


def _camel(field: str) -> str:
    """The name an author writes for a model field.

    Parameters
    ----------
    field : str
        The snake_case attribute.

    Returns
    -------
    str
        Its camelCase authored spelling.
    """
    head, *rest = field.split("_")
    return head + "".join(part.title() for part in rest)


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
        The number, or None where the author set none — including where
        they set a `{relativeToPlayer: {...}}` reference instead of a
        literal; `_relative_of` is what reads that half.
    """
    if isinstance(stat, Mapping):
        found = stat.get(key)
        if found is None or isinstance(found, Mapping):
            return None
        return float(found)
    return float(stat) if key == "base" else None


def _relative_of(stat: Any, key: str) -> dict[str, Any] | None:
    """A stat entry's `base`/`max`, as a relative-to-player reference.

    Parameters
    ----------
    stat : object
        `{base: {relativeToPlayer: {stat, factor}}, max: 40}`, or a bare
        value.
    key : str
        `base` or `max`.

    Returns
    -------
    dict or None
        `{stat, factor}`, or None where the author set a plain number (or
        nothing at all) instead.
    """
    if not isinstance(stat, Mapping):
        return None
    found = stat.get(key)
    if not isinstance(found, Mapping):
        return None
    relative = found.get("relativeToPlayer")
    if not isinstance(relative, Mapping):
        return None
    return {"stat": relative.get("stat"), "factor": relative.get("factor", 1.0)}


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
