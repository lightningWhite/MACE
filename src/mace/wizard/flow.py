"""The flow graph: authoring described as data, so any front-end can render it.

A `Step` is a question — a title, some help, a field, and where the answer
goes. A `Flow` is an ordered list of them that builds one kind of thing. The
CLI walks a flow and prints it; the web client will lay the same flow out as a
form. Neither knows what a location is.

The other half of a step is its **binding**: `locations[{id}].entities` says
which object the answer belongs to and which field of it. Bindings read and
write the project's raw authored mappings rather than models, so a step can
fill in one field of an object whose other fields are still wrong — which is
the whole reason the project holds raw mappings in the first place.

Flows are flat and resumable on purpose. The v0 wizard's `createInteraction`
called itself, so an author could not back out, skip ahead, or come back
tomorrow; nothing here recurses, every step can be left unanswered, and the
task list on top is free to visit them in any order.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mace.content import ContentError
from mace.wizard.fields import Field, Text
from mace.wizard.project import Project

__all__ = ["Binding", "Flow", "Step", "answered", "dig", "plant", "slug"]

#: The binding target that means the `game:` manifest rather than a collection.
GAME_TARGET = "game"


@dataclass(frozen=True, slots=True)
class Binding:
    """Where a step's answer lives in the project.

    Written as `collection[{id}].field.sub`, or `game.field` for the manifest.
    The `{id}` is filled in by whichever object the flow is editing, which is
    what lets one flow definition build every location in a pack.

    Attributes
    ----------
    collection : str or None
        The collection the object belongs to, or None for the game manifest.
    path : tuple of str
        The dotted field path inside the object.
    """

    collection: str | None
    path: tuple[str, ...]

    @classmethod
    def parse(cls, text: str) -> Binding:
        """Read a binding written the way a step declares it.

        Parameters
        ----------
        text : str
            `locations[{id}].entities`, or `game.player.startLocation`.

        Returns
        -------
        Binding
            The parsed binding.

        Raises
        ------
        ValueError
            If the binding names no field.
        """
        head, _, tail = text.partition(".")
        if head == GAME_TARGET:
            collection: str | None = None
        else:
            collection = head.partition("[")[0]
        if not tail:
            raise ValueError(f"`{text}` binds to no field")
        return cls(collection=collection, path=tuple(tail.split(".")))

    @property
    def leaf(self) -> str:
        """The last segment of the path — the field's own name.

        Returns
        -------
        str
            `entities`, `startLocation`.
        """
        return self.path[-1]

    def read(self, project: Project, object_id: str | None) -> Any:
        """What the project currently holds here.

        Parameters
        ----------
        project : Project
            The open pack.
        object_id : str or None
            Which object, for a collection binding.

        Returns
        -------
        object
            The authored value, or None when nothing is set.
        """
        if self.collection is None:
            game = project.game
            return None if game is None else dig(game, self.path)
        if object_id is None:
            return None
        # Through `extends`, so a step is not asked again about a field the
        # object already has from its parent. What an author still has to fill
        # in is what the *object* is missing, not what its file is missing.
        top = project.effective(self.collection, object_id, self.path[0])
        if len(self.path) == 1 or not isinstance(top, Mapping):
            return top
        return dig(top, self.path[1:])

    def write(self, project: Project, object_id: str | None, value: Any) -> None:
        """Put an answer into the project.

        Writes through the object that is already in its document, so a
        comment beside a key the author did not touch is still there
        afterwards, and only the file that changed is marked dirty.

        Parameters
        ----------
        project : Project
            The open pack.
        object_id : str or None
            Which object, for a collection binding.
        value : object
            The authored value. None removes the key rather than writing a
            null, because a field an author cleared should read as absent.

        Raises
        ------
        ContentError
            If the object this binds to does not exist yet.
        """
        if self.collection is None:
            body = dict(project.game or {})
            plant(body, self.path, value)
            project.set_game(body)
            return

        if object_id is None:
            raise ContentError(
                f"`{self.collection}` binding needs to know which object",
                collection=self.collection,
            )
        existing = project.get(self.collection, object_id)
        if existing is None:
            raise ContentError(
                f"there is no `{object_id}` to write to",
                collection=self.collection,
            )
        body = dict(existing)
        plant(body, self.path, value)
        project.put(self.collection, body)


@dataclass(frozen=True, slots=True)
class Step:
    """One question in a flow.

    Attributes
    ----------
    id : str
        Stable across renames of the title, so the sidecar can remember that
        this one is done.
    title : str
        The question, as a person would ask it.
    binds : str
        Where the answer goes.
    field : Field
        What kind of answer it is.
    help : str
        A sentence or two of context. Worth writing — the v0 wizard's tone was
        the one thing about it that was right, and the tone lives here now.
    optional : bool
        Whether leaving it blank is a finished state rather than an unfinished
        one. Nothing ever *blocks* on a step; this only changes the count.
    visible_when : tuple of (str, object) or None
        Another step's id in the same flow, and the value it must currently
        hold for this one to make sense — `("entity.kind", "item")` for a
        step that only applies to an item. None for a step that always
        applies. Checked by `Flow.visible`, since answering the sibling is
        what this step's own visibility depends on, not anything `Step`
        alone can resolve.
    """

    id: str
    title: str
    binds: str
    field: Field = field(default_factory=Text)
    help: str = ""
    optional: bool = False
    visible_when: tuple[str, Any] | None = None

    @property
    def binding(self) -> Binding:
        """Where this step writes.

        Returns
        -------
        Binding
            The parsed binding.
        """
        return Binding.parse(self.binds)

    def read(self, project: Project, object_id: str | None = None) -> Any:
        """The answer this step currently has.

        Parameters
        ----------
        project : Project
            The open pack.
        object_id : str or None
            Which object the flow is editing.

        Returns
        -------
        object
            The authored value, or None.
        """
        return self.binding.read(project, object_id)

    def write(self, project: Project, value: Any, object_id: str | None = None) -> None:
        """Record an answer.

        Parameters
        ----------
        project : Project
            The open pack.
        value : object
            The authored value.
        object_id : str or None
            Which object the flow is editing.
        """
        self.binding.write(project, object_id, value)


@dataclass(frozen=True, slots=True)
class Flow:
    """An ordered set of steps that builds one kind of thing.

    Attributes
    ----------
    id : str
        The flow's name — `location`, `game`.
    title : str
        What it is called on screen.
    steps : tuple of Step
        The questions, in the order they are best asked. Order is a suggestion:
        every step is independently addressable and any of them can be left.
    collection : str or None
        Which collection it authors, or None for the game manifest.
    noun : str
        What one of these is called mid-sentence. `title` is a heading and
        reads like one ("A place"); this is the word that goes in "what is
        the new ___ called".
    identity : tuple of str
        The steps that must be answered before the object exists at all —
        an id and a name. Everything else can wait.
    """

    id: str
    title: str
    steps: tuple[Step, ...]
    collection: str | None = None
    noun: str = "thing"
    identity: tuple[str, ...] = ()

    def step(self, step_id: str) -> Step:
        """Look one step up by id.

        Parameters
        ----------
        step_id : str
            The step's id.

        Returns
        -------
        Step
            The step.

        Raises
        ------
        KeyError
            If this flow has no such step.
        """
        for found in self.steps:
            if found.id == step_id:
                return found
        raise KeyError(f"{self.id} has no step `{step_id}`")

    def visible(
        self, step: Step, project: Project, object_id: str | None = None
    ) -> bool:
        """Whether a step makes sense to show right now.

        Parameters
        ----------
        step : Step
            The step in question — its own `visible_when` names the sibling
            to check, if it has one.
        project : Project
            The open pack.
        object_id : str or None
            Which object.

        Returns
        -------
        bool
            True unless `visible_when` names a sibling step whose current
            answer does not match.
        """
        if step.visible_when is None:
            return True
        sibling_id, expected = step.visible_when
        sibling = self.step(sibling_id)
        return bool(sibling.read(project, object_id) == expected)

    def unanswered(
        self, project: Project, object_id: str | None = None
    ) -> tuple[Step, ...]:
        """The steps still waiting for an answer.

        Parameters
        ----------
        project : Project
            The open pack.
        object_id : str or None
            Which object.

        Returns
        -------
        tuple of Step
            The required, currently visible steps with nothing in them, in
            flow order.
        """
        return tuple(
            step
            for step in self.steps
            if not step.optional
            and self.visible(step, project, object_id)
            and not answered(step.read(project, object_id))
        )

    def each(
        self, project: Project, object_id: str | None = None
    ) -> Iterator[tuple[Step, Any]]:
        """Every step with the answer it currently has.

        Parameters
        ----------
        project : Project
            The open pack.
        object_id : str or None
            Which object.

        Yields
        ------
        tuple of (Step, object)
            The step and its value.
        """
        for step in self.steps:
            yield step, step.read(project, object_id)


def answered(value: Any) -> bool:
    """Whether a value counts as an answer.

    An empty string, an empty list, and an absent key are all "not yet".
    `False` and `0` are answers, which is why this is not just truthiness.

    Parameters
    ----------
    value : object
        The authored value.

    Returns
    -------
    bool
        Whether the author has said something here.
    """
    if value is None:
        return False
    if isinstance(value, str | list | tuple | dict):
        return bool(value)
    return True


def slug(name: str) -> str:
    """Turn a name into a content id.

    Both front-ends make an object the same way — the author says what it is
    called and the wizard derives the id — so this lives here rather than in
    either of them, or a browser and a terminal would name the same place
    differently.

    Parameters
    ----------
    name : str
        What the author typed.

    Returns
    -------
    str
        `the-old-bridge`.
    """
    kept = [one.lower() if one.isalnum() else "-" for one in name]
    return "-".join(part for part in "".join(kept).split("-") if part) or "untitled"


def dig(holder: Mapping[str, Any], path: Sequence[str]) -> Any:
    """Follow a dotted path into an authored mapping.

    Public so a repeat entry can be read the same way a binding reads one —
    editing `choices.combat.against` needs to find what is already at
    `{combat: {against: [...]}}` inside the entry before it can offer it back.

    Parameters
    ----------
    holder : mapping
        The object.
    path : sequence of str
        The path.

    Returns
    -------
    object
        The value, or None when any step of the path is absent.
    """
    current: Any = holder
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def plant(holder: MutableMapping[str, Any], path: Sequence[str], value: Any) -> None:
    """Set a dotted path in an authored mapping, making the way as it goes.

    Public so a repeat entry can be built the same way a binding writes one —
    `entries.combat.against` should land at `{combat: {against: [...]}}`
    inside an entry exactly as `entities[{id}].combat.profile` would inside an
    object.

    Parameters
    ----------
    holder : mutable mapping
        The object.
    path : sequence of str
        The path.
    value : object
        The value. None deletes rather than writing a null.
    """
    current: MutableMapping[str, Any] = holder
    for key in path[:-1]:
        nested = current.get(key)
        if not isinstance(nested, MutableMapping):
            nested = {}
            current[key] = nested
        current = nested

    leaf = path[-1]
    if value is None:
        current.pop(leaf, None)
    else:
        current[leaf] = value
