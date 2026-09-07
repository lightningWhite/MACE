"""Query-backed selection: every reference is picked, never typed.

This is the fix for the single biggest hole in the v0 wizard, which asked
authors to type references as free strings and therefore made a dangling
reference the *default* outcome of using the tool. A `Query` asks the open
project and its libraries what exists, and the author picks `Bridge Troll` off
a list while the wizard writes `fantasy.core:bridge-troll`.

Two rules the implementation follows and the doc does not spell out.

**The project side reads raw mappings, not models.** A half-written location
with a misspelled field is still a location the author should be able to
reference from somewhere else — the whole point of the project model is that
content is allowed to be wrong for a while, and a picker that only offered
things that compile would go empty exactly when an author needs it most.

**A local id is written bare.** `troll-bridge` inside its own pack resolves to
that pack first, so writing it qualified would be noise in the author's own
file and would break the moment they renamed their pack. Things from a library
are written qualified, because that is the only form that means anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from mace.content.library import COLLECTION_MODELS, SINGULAR
from mace.model.base import RESERVED_ACTORS

if TYPE_CHECKING:  # pragma: no cover — import cycle, types only
    from mace.wizard.project import Project

__all__ = ["Catalog", "Option", "Query", "Scope"]

Scope = Literal["project", "libraries", "project+libraries"]

#: Options offered for a reference field that also accepts a reserved name.
#: `player` is not an entity anybody defined; it is whichever entity the game
#: names, and an author picking "the player" should not have to know that.
RESERVED_OPTIONS: tuple[tuple[str, str], ...] = (("player", "the player"),)


@dataclass(frozen=True, slots=True)
class Option:
    """One thing an author can pick.

    Attributes
    ----------
    value : str
        What gets written into the content — a bare local id for something in
        this pack, a qualified one for anything else.
    label : str
        What the author sees. The definition's `name` where it has one.
    note : str
        Where it came from: `this pack`, or the library's id.
    """

    value: str
    label: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class Query:
    """A request for everything of some kind that exists.

    Attributes
    ----------
    collection : str
        Which collection to offer — `entities`, `locations`, `scenes`.
    scope : str
        Where to look: the open project, its libraries, or both.
    where : mapping
        Field equality filters applied to each candidate — `{"kind": "item"}`
        to offer only items. Compared against the raw authored value on the
        project side and the model attribute on the library side, which agree
        for the flat scalar fields anybody filters on.
    reserved : bool
        Whether to offer the reserved names — `player` — ahead of the real
        definitions. Only meaningful for `entities`.
    """

    collection: str
    scope: Scope = "project+libraries"
    where: Mapping[str, Any] = field(default_factory=dict)
    reserved: bool = False

    def options(self, catalog: Catalog) -> tuple[Option, ...]:
        """Everything this query offers, project first.

        Parameters
        ----------
        catalog : Catalog
            What exists.

        Returns
        -------
        tuple of Option
            The options, the author's own things first because those are what
            they are usually reaching for.
        """
        return catalog.options(self)

    @property
    def noun(self) -> str:
        """What one of these is called, for a prompt.

        Returns
        -------
        str
            `entity`, `location`, `weather condition`.
        """
        return SINGULAR.get(self.collection, self.collection)


@dataclass(frozen=True, slots=True)
class Catalog:
    """Everything the open project and its libraries have to offer.

    Attributes
    ----------
    project : Project
        The pack being authored. Its own objects are read as raw mappings, so
        content that does not compile is still content that can be pointed at.
    """

    project: Project

    def options(self, query: Query) -> tuple[Option, ...]:
        """Answer one query.

        Parameters
        ----------
        query : Query
            What is being asked for.

        Returns
        -------
        tuple of Option
            The options, in offer order.
        """
        found: list[Option] = []
        if query.reserved:
            found.extend(
                Option(value=name, label=label, note="built in")
                for name, label in RESERVED_OPTIONS
                if name in RESERVED_ACTORS
            )
        if query.scope in {"project", "project+libraries"}:
            found.extend(self._mine(query))
        if query.scope in {"libraries", "project+libraries"}:
            found.extend(self._theirs(query))
        return tuple(found)

    def label(self, reference: str, collection: str) -> str:
        """What an already-chosen reference should read as.

        Parameters
        ----------
        reference : str
            As it is written in the content.
        collection : str
            Which collection it points into.

        Returns
        -------
        str
            The matching option's label, or the reference itself when nothing
            matches — a reference to something that no longer exists must stay
            visible rather than being quietly prettified away.
        """
        for option in self.options(Query(collection, reserved=True)):
            if option.value == reference:
                return option.label
        return reference

    def exists(self, reference: str, collection: str) -> bool:
        """Whether something with this reference is on offer.

        Parameters
        ----------
        reference : str
            As it would be written.
        collection : str
            Which collection.

        Returns
        -------
        bool
            True when a picker would have offered it.
        """
        return any(
            option.value == reference
            for option in self.options(Query(collection, reserved=True))
        )

    def _mine(self, query: Query) -> list[Option]:
        """The project's own objects, read as the author wrote them.

        Parameters
        ----------
        query : Query
            What is being asked for.

        Returns
        -------
        list of Option
            Options with bare local ids.
        """
        held = self.project.objects.get(query.collection, {})
        offered = []
        for local_id in sorted(held):
            authored = held[local_id].data
            if not _matches(query.where, self._reader(query.collection, authored)):
                continue
            name = authored.get("name")
            offered.append(
                Option(
                    value=local_id,
                    label=str(name) if name else _readable(local_id),
                    note="this pack",
                )
            )
        return offered

    def _reader(self, collection: str, authored: Mapping[str, Any]) -> Any:
        """Read a field off a raw authored object, the way the loader would.

        Three fallbacks, in order: what the author wrote, what it inherits
        through `extends`, and what the model defaults to. All three matter to
        a picker. An entity that extends `fantasy.core:soldier` and never says
        `kind` is an actor, and a picker offering only the objects that spell
        it out would hide most of a well-factored pack.

        Parameters
        ----------
        collection : str
            Which collection the object belongs to.
        authored : mapping
            The object as written.

        Returns
        -------
        callable
            Reads one field name.
        """
        model = COLLECTION_MODELS.get(collection)

        def default(name: str) -> Any:
            field = None if model is None else model.model_fields.get(name)
            if field is None or field.is_required():
                return None
            return field.get_default(call_default_factory=True)

        def read(name: str) -> Any:
            data: Mapping[str, Any] | None = authored
            seen: set[int] = set()
            while data is not None and id(data) not in seen:
                if name in data:
                    return data[name]
                seen.add(id(data))
                parent = data.get("extends")
                if not isinstance(parent, str):
                    break
                inherited = self._parent(collection, parent)
                if isinstance(inherited, Mapping):
                    data = inherited
                    continue
                # A dependency's definitions are already compiled, so their
                # own inheritance is resolved and the walk ends here.
                return (
                    default(name)
                    if inherited is None
                    else getattr(inherited, name, default(name))
                )
            return default(name)

        return read

    def _parent(self, collection: str, reference: str) -> Any:
        """Find what an object extends, wherever it lives.

        Parameters
        ----------
        collection : str
            The collection both objects belong to.
        reference : str
            The `extends` reference.

        Returns
        -------
        object or None
            A raw mapping for something in this project, a compiled definition
            for something in a library, or None when it names nothing.
        """
        pack_id, _, local_id = reference.rpartition(":")
        if pack_id in {"", self.project.manifest.id}:
            held = self.project.objects.get(collection, {}).get(local_id)
            if held is not None:
                return held.data
        for pack in self.project.dependencies.packs:
            if pack_id in {"", pack.id}:
                found = pack.collection(collection).get(local_id)
                if found is not None:
                    return found
        return None

    def _theirs(self, query: Query) -> list[Option]:
        """What the libraries this pack builds on offer.

        Parameters
        ----------
        query : Query
            What is being asked for.

        Returns
        -------
        list of Option
            Options with qualified ids.
        """
        offered = []
        for pack in self.project.dependencies.packs:
            try:
                collected = pack.collection(query.collection)
            except KeyError:  # pragma: no cover — collections are checked upstream
                continue
            for local_id in sorted(collected):
                definition = collected[local_id]
                if not _matches(query.where, _model_reader(definition)):
                    continue
                name = getattr(definition, "name", None)
                offered.append(
                    Option(
                        value=f"{pack.id}:{local_id}",
                        label=str(name) if name else _readable(local_id),
                        note=pack.id,
                    )
                )
        return offered


def _model_reader(definition: object) -> Any:
    """Read a field off a compiled definition.

    Parameters
    ----------
    definition : object
        A loaded content model.

    Returns
    -------
    callable
        Reads one field name, returning None when the model has no such field.
    """

    def read(name: str) -> Any:
        return getattr(definition, name, None)

    return read


def _matches(where: Mapping[str, Any], read: Any) -> bool:
    """Whether one candidate satisfies a query's filters.

    Parameters
    ----------
    where : mapping
        Field to required value. A tuple or list of values matches any of them.
    read : callable
        Reads one field off the candidate, returning None when it is absent.

    Returns
    -------
    bool
        Whether every filter holds.
    """
    for name, wanted in where.items():
        value = read(name)
        if isinstance(wanted, tuple | list | set):
            if value not in wanted:
                return False
        elif value != wanted:
            return False
    return True


def _readable(local_id: str) -> str:
    """A kebab-case id as words, for something with no `name`.

    Parameters
    ----------
    local_id : str
        The id.

    Returns
    -------
    str
        `troll bridge`.
    """
    return local_id.replace("-", " ")
