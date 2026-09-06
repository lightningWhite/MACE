"""Checking a loaded library, and saying what is wrong in an author's terms.

The loader answers "can this be built at all". This answers the harder and more
useful question: is it any good? A reference that points at nothing, a scene no
path reaches, a quest the game never starts — none of these stop a pack loading
and all of them ruin a playthrough.

Three severities, because they need three different reactions:

- **error** — the game is broken. CI fails.
- **warning** — almost certainly a mistake, but the game runs. A scene nothing
  reaches is content the author wrote and no player will ever see.
- **note** — worth a look. Often deliberate.

Every problem carries the pack, the file, the id, and the field, because
"something is wrong somewhere in your world" helps nobody.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from mace.content.errors import ContentError
from mace.content.ids import qualify
from mace.content.library import COLLECTION_MODELS, Library, LoadedPack
from mace.content.loader import load_best_effort
from mace.model import (
    Calendar,
    ClimateOverride,
    Condition,
    Entity,
    Location,
    Move,
    Scene,
)
from mace.model.base import RESERVED_ACTORS, ContentModel, Reference
from mace.model.calendar import STANDARD_YEAR
from mace.model.conditions import DayPartIs
from mace.model.effects import FireEvent, SetPressure

__all__ = [
    "Problem",
    "Report",
    "Severity",
    "as_problem",
    "references",
    "validate_library",
    "validate_paths",
]


class Severity(Enum):
    """How much a problem matters."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class Problem:
    """One thing wrong with a pack.

    Attributes
    ----------
    severity : Severity
        How much it matters.
    message : str
        What is wrong, phrased for the author.
    pack : str
        The pack it is in.
    path : Path or None
        The file, where one object is at fault.
    collection : str or None
        The collection the object belongs to.
    object_id : str or None
        The object's local id.
    field : str or None
        The field within the object.
    """

    severity: Severity
    message: str
    pack: str
    path: Path | None = None
    collection: str | None = None
    object_id: str | None = None
    field: str | None = None

    def __str__(self) -> str:
        """Render the problem as one line, location first.

        Returns
        -------
        str
            `severity  pack → collection/id.field: message`.
        """
        where = [self.pack]
        if self.collection and self.object_id:
            where.append(f"{self.collection}/{self.object_id}")
        elif self.collection:
            where.append(self.collection)
        location = " → ".join(where)
        if self.field:
            location = f"{location}.{self.field}"
        return f"{self.severity.value:<7} {location}: {self.message}"


@dataclass(frozen=True, slots=True)
class Report:
    """Everything found while validating.

    Attributes
    ----------
    problems : tuple of Problem
        Every problem, in the order found.
    """

    problems: tuple[Problem, ...] = ()

    @property
    def errors(self) -> tuple[Problem, ...]:
        """The problems that break the game.

        Returns
        -------
        tuple of Problem
            Problems at error severity.
        """
        return self._at(Severity.ERROR)

    @property
    def warnings(self) -> tuple[Problem, ...]:
        """The problems that are probably mistakes.

        Returns
        -------
        tuple of Problem
            Problems at warning severity.
        """
        return self._at(Severity.WARNING)

    @property
    def notes(self) -> tuple[Problem, ...]:
        """The observations worth a look.

        Returns
        -------
        tuple of Problem
            Problems at note severity.
        """
        return self._at(Severity.NOTE)

    @property
    def ok(self) -> bool:
        """Whether the content is usable.

        Returns
        -------
        bool
            True when nothing is at error severity.
        """
        return not self.errors

    def _at(self, severity: Severity) -> tuple[Problem, ...]:
        """Filter by severity.

        Parameters
        ----------
        severity : Severity
            The severity to keep.

        Returns
        -------
        tuple of Problem
            Matching problems.
        """
        return tuple(p for p in self.problems if p.severity is severity)

    def summary(self) -> str:
        """One line counting what was found.

        Returns
        -------
        str
            A human-readable tally.
        """
        if not self.problems:
            return "no problems found"
        parts = [
            f"{len(self.errors)} error{'s' if len(self.errors) != 1 else ''}",
            f"{len(self.warnings)} warning{'s' if len(self.warnings) != 1 else ''}",
            f"{len(self.notes)} note{'s' if len(self.notes) != 1 else ''}",
        ]
        return ", ".join(parts)

    def format(self, *, include: Severity | None = None) -> str:
        """Render the whole report.

        Parameters
        ----------
        include : Severity or None
            Show only this severity, or everything when None.

        Returns
        -------
        str
            One problem per line, then a summary.
        """
        shown = self.problems if include is None else self._at(include)
        lines = [str(problem) for problem in shown]
        lines.append(self.summary())
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Found:
    """One reference found inside a definition.

    Attributes
    ----------
    field : str
        The dotted path to the field, in authoring names.
    reference : str
        What the author wrote.
    collection : str
        The collection it should resolve against.
    """

    field: str
    reference: str
    collection: str


def references(model: ContentModel, path: str = "") -> Iterator[Found]:
    """Find every reference inside a definition, however deeply nested.

    Reference fields say what they point at (`mace.model.base.Reference`), so
    this walks the annotations rather than keeping a second list of which field
    means what — the two could not then disagree.

    Parameters
    ----------
    model : ContentModel
        The definition to search.
    path : str
        The dotted path walked so far.

    Yields
    ------
    Found
        Each reference, with the field it came from.
    """
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        here = f"{path}.{field.alias or name}" if path else (field.alias or name)
        marker = next((m for m in field.metadata if isinstance(m, Reference)), None)
        if marker is not None and isinstance(value, str):
            yield Found(here, value, marker.collection)
            continue
        yield from _walk(field.annotation, value, here)


def _walk(annotation: Any, value: Any, path: str) -> Iterator[Found]:
    """Walk one value alongside its annotation, yielding references.

    Parameters
    ----------
    annotation : object
        The declared type of the value.
    value : object
        The value itself.
    path : str
        The dotted path walked so far.

    Yields
    ------
    Found
        Each reference found.
    """
    if value is None:
        return

    if isinstance(value, ContentModel):
        # The declared type may be a base class — `Condition.payload` is one —
        # so trust the instance over the annotation.
        yield from references(value, path)
        return

    marker = _marker_of(annotation)
    if marker is not None and isinstance(value, str):
        yield Found(path, value, marker.collection)
        return

    # Unwrap in structure order: an annotation's own wrappers, then a union's
    # arms, and only then the shape of the value. Reading the value first would
    # take a union's arguments for a mapping's key and value types.
    if _is_annotated(annotation):
        yield from _walk(get_args(annotation)[0], value, path)
        return

    origin, args = get_origin(annotation), get_args(annotation)

    if origin in (Union, UnionType):
        for arm in args:
            yield from _walk(arm, value, path)
        return

    if isinstance(value, Mapping):
        key_type, value_type = (*args, Any, Any)[:2]
        for key, item in value.items():
            yield from _walk(key_type, key, f"{path}.{key}")
            yield from _walk(value_type, item, f"{path}.{key}")
        return

    if isinstance(value, Sequence) and not isinstance(value, str):
        item_type = args[0] if args else Any
        for index, item in enumerate(value):
            yield from _walk(item_type, item, f"{path}[{index}]")


def _is_annotated(annotation: Any) -> bool:
    """Whether an annotation is an `Annotated[...]`.

    Parameters
    ----------
    annotation : object
        The annotation to test.

    Returns
    -------
    bool
        True for `Annotated`.
    """
    return get_origin(annotation) is Annotated or hasattr(annotation, "__metadata__")


def _marker_of(annotation: Any) -> Reference | None:
    """Read the reference marker off an annotation, if it carries one.

    Parameters
    ----------
    annotation : object
        The annotation to inspect.

    Returns
    -------
    Reference or None
        The marker, or None.
    """
    metadata = getattr(annotation, "__metadata__", ())
    return next((m for m in metadata if isinstance(m, Reference)), None)


def validate_paths(*roots: Path) -> Report:
    """Load and validate everything under the given roots.

    The load is best-effort: an object that will not compile becomes an error
    in the report and the rest of the pack is checked anyway. Stopping at the
    first one meant a single misspelled field hid every other problem behind
    it, so a world got fixed one invisible error at a time — which is bad for
    an author and no better for CI.

    Parameters
    ----------
    *roots : Path
        Directories to search for packs.

    Returns
    -------
    Report
        Everything found, load failures first.
    """
    try:
        loaded = load_best_effort(*roots)
    except ContentError as error:
        # Discovery itself failed — a root that is not there. Nothing was
        # loaded, so there is nothing further to check.
        return Report((as_problem(error),))

    problems = [as_problem(error) for error in loaded.problems]
    problems.extend(validate_library(loaded.library).problems)
    return Report(tuple(problems))


def as_problem(error: ContentError) -> Problem:
    """Render a load failure as a report entry.

    Parameters
    ----------
    error : ContentError
        What would not build.

    Returns
    -------
    Problem
        The same thing, at error severity.
    """
    return Problem(
        severity=Severity.ERROR,
        message=error.message,
        pack=error.pack or "?",
        path=error.path,
        collection=error.collection,
        object_id=error.object_id,
    )


def validate_library(library: Library) -> Report:
    """Check every pack in a loaded library.

    Parameters
    ----------
    library : Library
        The loaded packs.

    Returns
    -------
    Report
        Everything found, worst first within each pack.
    """
    problems: list[Problem] = []
    for pack in library.packs:
        problems.extend(_check_references(library, pack))
        problems.extend(_check_reserved_names(pack))
        problems.extend(_check_game(library, pack))
        problems.extend(_check_calendar(library, pack))
        problems.extend(_check_event_references(library, pack))
        problems.extend(_check_reachable_scenes(library, pack))
        problems.extend(_check_combat(library, pack))
        problems.extend(_check_notes(library, pack))
    return Report(tuple(problems))


def _each_definition(
    pack: LoadedPack,
) -> Iterator[tuple[str, str, ContentModel]]:
    """Every modelled definition in a pack.

    Parameters
    ----------
    pack : LoadedPack
        The pack to walk.

    Yields
    ------
    tuple of (str, str, ContentModel)
        Collection, local id, and definition.
    """
    for collection in COLLECTION_MODELS:
        for local_id, definition in pack.collection(collection).items():
            yield collection, local_id, definition


def _check_references(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """Every reference in a pack must name something that exists.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        One error per reference that resolves to nothing.
    """
    sources: list[tuple[str | None, str | None, ContentModel]] = [
        (collection, local_id, definition)
        for collection, local_id, definition in _each_definition(pack)
    ]
    if pack.game is not None:
        sources.append(("game", None, pack.game))

    for collection, local_id, definition in sources:
        for found in references(definition):
            if found.collection not in COLLECTION_MODELS:
                continue
            if found.collection == "entities" and found.reference in RESERVED_ACTORS:
                continue
            try:
                library.resolve(found.reference, found.collection, within=pack.id)
            except ContentError as error:
                yield Problem(
                    severity=Severity.ERROR,
                    message=error.message,
                    pack=pack.id,
                    collection=collection,
                    object_id=local_id,
                    field=found.field,
                )


def _check_reserved_names(pack: LoadedPack) -> Iterator[Problem]:
    """An entity may not take a name the engine reserves.

    Parameters
    ----------
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        One error per collision.
    """
    for reserved in sorted(RESERVED_ACTORS & set(pack.entities)):
        yield Problem(
            severity=Severity.ERROR,
            message=(
                f"`{reserved}` is reserved — content uses it to mean whichever "
                "entity `game.player.entity` names. Give this one another id."
            ),
            pack=pack.id,
            collection="entities",
            object_id=reserved,
        )


def _check_game(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """The game manifest must describe a game that can start.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        Errors for a protagonist who cannot act, warnings for loose ends.
    """
    game = pack.game
    if game is None:
        return

    protagonist: Entity | None = None
    try:
        found = library.find(game.player.entity, "entities", within=pack.id)
        protagonist = found if isinstance(found, Entity) else None
    except ContentError:
        return  # Already reported by the reference check.

    if protagonist is None:
        return

    if not protagonist.playable:
        yield Problem(
            severity=Severity.ERROR,
            message=(
                f"`{game.player.entity}` is the protagonist but is not marked "
                "`playable: true`"
            ),
            pack=pack.id,
            collection="game",
            field="player.entity",
        )

    stats = protagonist.stats or {}
    for role, stat in (
        ("vitalPool", game.rules.vital_pool),
        ("effortPool", game.rules.effort_pool),
    ):
        if stat not in stats:
            yield Problem(
                severity=Severity.ERROR,
                message=(
                    f"`{stat}` is the {role} but `{protagonist.id}` has no such "
                    f"stat; it has {', '.join(sorted(stats)) or 'none'}"
                ),
                pack=pack.id,
                collection="game",
                field=f"rules.{role}",
            )
        elif stats[stat].max is None:
            yield Problem(
                severity=Severity.NOTE,
                message=(
                    f"`{stat}` is a pool with no `max`, so it has nothing to "
                    "refill to"
                ),
                pack=pack.id,
                collection="entities",
                object_id=protagonist.id,
                field=f"stats.{stat}",
            )

    if not game.win_conditions and not game.quests:
        yield Problem(
            severity=Severity.WARNING,
            message="has no win conditions and no quests, so it cannot be won",
            pack=pack.id,
            collection="game",
        )

    for local_id in sorted(pack.quests):
        if local_id not in game.quests:
            yield Problem(
                severity=Severity.WARNING,
                message=(
                    "is never started — add it to `game.quests`, or start it "
                    "from a scene"
                ),
                pack=pack.id,
                collection="quests",
                object_id=local_id,
            )


def _check_event_references(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """`fireEvent` and `setPressure` must name an event of one kind or the other.

    The generic reference check works off a field's `Reference` marker, which
    names exactly one collection. These two fields name either, so they are
    checked here rather than being left as a runtime surprise.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        One error per reference that names nothing.
    """
    for collection, local_id, definition in _each_definition(pack):
        for path, reference in _events_named(definition):
            if any(
                _resolves(library, pack, reference, target)
                for target in ("celestialEvents", "pressureEvents")
            ):
                continue
            yield Problem(
                severity=Severity.ERROR,
                message=(
                    f"`{reference}` is not a celestial or pressure event, "
                    "here or in this pack's dependencies"
                ),
                pack=pack.id,
                collection=collection,
                object_id=local_id,
                field=path,
            )


def _resolves(
    library: Library, pack: LoadedPack, reference: str, collection: str
) -> bool:
    """Whether a reference names something in one collection.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack : LoadedPack
        The pack the reference was written in.
    reference : str
        As the author wrote it.
    collection : str
        Where to look.

    Returns
    -------
    bool
        Whether it resolves.
    """
    try:
        library.resolve(reference, collection, within=pack.id)
    except ContentError:
        return False
    return True


def _events_named(
    definition: ContentModel, path: str = ""
) -> Iterator[tuple[str, str]]:
    """Every world event a definition names, and where it named it.

    Parameters
    ----------
    definition : ContentModel
        The definition to walk.
    path : str
        The field path reached so far.

    Yields
    ------
    tuple of (str, str)
        The field path, and the event named there.
    """
    for name, field in type(definition).model_fields.items():
        yield from _events_in(
            getattr(definition, name), f"{path}.{field.alias or name}".lstrip(".")
        )


def _events_in(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Find world-event references in a validated value.

    Parameters
    ----------
    value : object
        A model, collection, or scalar.
    path : str
        The field path it was reached by.

    Yields
    ------
    tuple of (str, str)
        The field path, and the event named there.
    """
    if isinstance(value, FireEvent | SetPressure):
        yield f"{path}.event", value.event
        return
    if isinstance(value, ContentModel):
        yield from _events_named(value, path)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _events_in(item, f"{path}.{key}")
        return
    if isinstance(value, tuple | list):
        for index, item in enumerate(value):
            yield from _events_in(item, f"{path}[{index}]")


def _check_calendar(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """The day parts and seasons content names must exist in the calendar.

    A `{dayPart: [evening]}` condition on a calendar that has no `evening` is
    a condition that can never hold — silently, forever. It is the kind of
    mistake that only shows up as "that description never appears", so it is
    worth an error at load time rather than a shrug at runtime.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolving the game's calendar.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        Errors for names the calendar does not declare.
    """
    game = pack.game
    if game is None:
        return

    calendar = STANDARD_YEAR
    if game.world.calendar is not None:
        try:
            found = library.find(game.world.calendar, "calendars", within=pack.id)
        except ContentError:
            return  # Already reported by the reference check.
        assert isinstance(found, Calendar)
        calendar = found

    parts = {part.id for part in calendar.day_parts}
    seasons = {season.id for season in calendar.seasons}

    if game.world.start_season is not None and game.world.start_season not in seasons:
        yield Problem(
            severity=Severity.ERROR,
            message=(
                f"starts in season `{game.world.start_season}`, which "
                f"`{calendar.id}` does not have; it has "
                f"{', '.join(sorted(seasons))}"
            ),
            pack=pack.id,
            collection="game",
            field="world.startSeason",
        )

    for collection, local_id, definition in _each_definition(pack):
        for path, named in _day_parts_named(definition):
            if named in parts:
                continue
            yield Problem(
                severity=Severity.ERROR,
                message=(
                    f"names day part `{named}`, which `{calendar.id}` does not "
                    f"have; it has {', '.join(sorted(parts))}"
                ),
                pack=pack.id,
                collection=collection,
                object_id=local_id,
                field=path,
            )


def _day_parts_named(
    definition: ContentModel, path: str = ""
) -> Iterator[tuple[str, str]]:
    """Every day part a definition names, and where it named it.

    Parameters
    ----------
    definition : ContentModel
        The definition to walk.
    path : str
        The field path reached so far.

    Yields
    ------
    tuple of (str, str)
        The field path, and the day part named there.
    """
    for name, field in type(definition).model_fields.items():
        value = getattr(definition, name)
        here = f"{path}.{field.alias or name}".lstrip(".")
        yield from _day_parts_in(value, here)


def _day_parts_in(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Find day-part names in a validated value.

    Parameters
    ----------
    value : object
        A model, collection, or scalar.
    path : str
        The field path it was reached by.

    Yields
    ------
    tuple of (str, str)
        The field path, and the day part named there.
    """
    if isinstance(value, Condition):
        if isinstance(value.payload, DayPartIs):
            for named in value.payload.parts:
                yield path, named
        yield from _day_parts_named(value.payload, path)
        return
    if isinstance(value, ClimateOverride):
        if value.day_part is not None:
            yield f"{path}.dayPart", value.day_part
        return
    if isinstance(value, ContentModel):
        yield from _day_parts_named(value, path)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _day_parts_in(item, f"{path}.{key}")
        return
    if isinstance(value, tuple | list):
        for index, item in enumerate(value):
            yield from _day_parts_in(item, f"{path}[{index}]")


def _check_reachable_scenes(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """A scene nothing points at is content no player will ever see.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolving references into this pack.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        One warning per unreachable scene.
    """
    if not pack.manifest.is_game:
        # A library pack's scenes are meant to be reached from packs that
        # depend on it, which this pack cannot see. Warning about them would
        # make every library noisy and teach people to ignore the warning.
        return

    reached: set[str] = set()
    for _collection, _local_id, definition in _each_definition(pack):
        reached.update(_scene_targets(library, pack, definition))
    if pack.game is not None:
        reached.update(_scene_targets(library, pack, pack.game))

    for local_id in sorted(pack.scenes):
        if qualify(pack.id, local_id) not in reached:
            yield Problem(
                severity=Severity.WARNING,
                message=(
                    "is not reached from anywhere — no entity, location, "
                    "scene, or effect leads to it"
                ),
                pack=pack.id,
                collection="scenes",
                object_id=local_id,
            )


def _scene_targets(
    library: Library, pack: LoadedPack, definition: ContentModel
) -> set[str]:
    """Qualified ids of every scene a definition can lead to.

    A scene does not count as reaching itself, so a scene whose only inbound
    reference is its own `goto` is still reported as unreachable.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack the definition belongs to.
    definition : ContentModel
        The definition to search.

    Returns
    -------
    set of str
        Qualified scene ids.
    """
    targets: set[str] = set()
    for found in references(definition):
        if found.collection != "scenes":
            continue
        try:
            qualified = library.resolve(found.reference, "scenes", within=pack.id)
        except ContentError:
            continue
        if isinstance(definition, Scene) and qualified == qualify(
            pack.id, definition.id
        ):
            continue
        targets.add(qualified)
    return targets


def _check_dead_ends(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """A place with no way out is a place a playthrough can end in by accident.

    "No exits" on its own is not the problem, and saying it was produced a
    permanent false positive on every route waypoint in the repo — the middle
    of a bridge is not a place with roads leading off it, and the journey menu
    is how you leave. A note nobody can act on teaches people to ignore notes.

    So the question asked here is the useful one: **can the player get out?**
    Three answers count — an exit, being a waypoint on some route, or a scene
    reachable from here that moves them, restarts, or ends the game.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        One note per place with no way out of it.
    """
    if not pack.manifest.is_game:
        # A library's locations are meant to be built on, and the pack that
        # builds on them is the one that adds the exits and lays the roads —
        # which this pack cannot see. The same reason `_check_reachable_scenes`
        # skips libraries.
        return

    waypoints = {
        _resolve(library, pack, stop.location, "locations")
        for route in pack.routes.values()
        for stop in route.waypoints
    }
    for local_id, location in pack.locations.items():
        if location.exits or qualify(pack.id, local_id) in waypoints:
            continue
        if _leads_away(library, pack, location):
            continue
        yield Problem(
            severity=Severity.NOTE,
            message=(
                "has no exits, is on no route, and nothing here moves the "
                "player on — a playthrough that arrives cannot leave"
            ),
            pack=pack.id,
            collection="locations",
            object_id=local_id,
        )


def _leads_away(library: Library, pack: LoadedPack, location: Location) -> bool:
    """Whether any scene reachable from a location gets the player out of it.

    Deliberately generous: it follows every scene reference out of every scene
    it reaches, which over-approximates reachability. Over-approximating means
    fewer false notes, and a false note is the thing this check exists to stop
    producing.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack the location belongs to.
    location : Location
        The place in question.

    Returns
    -------
    bool
        Whether a `move`, `restart`, or `endGame` is reachable from here.
    """
    seeds = [*location.scenes]
    if location.on_arrive is not None:
        seeds.append(location.on_arrive)
    for reference in location.entities:
        qualified = _resolve(library, pack, reference, "entities")
        if qualified is None:
            continue
        found = library.find(qualified, "entities", within=pack.id)
        if isinstance(found, Entity):
            seeds.extend(found.scenes)

    seen: set[str] = set()
    frontier = [
        resolved
        for reference in seeds
        if (resolved := _resolve(library, pack, reference, "scenes")) is not None
    ]
    while frontier:
        scene_id = frontier.pop()
        if scene_id in seen:
            continue
        seen.add(scene_id)
        pack_id, local_id = scene_id.split(":", 1)
        scene = library.pack(pack_id).scenes.get(local_id)
        if scene is None:  # pragma: no cover — the reference resolved
            continue
        if _gets_out(scene):
            return True
        frontier.extend(
            resolved
            for found in references(scene)
            if found.collection == "scenes"
            and (resolved := _resolve(library, pack, found.reference, "scenes"))
            is not None
        )
    return False


#: Effect tags that take the player out of wherever they are standing.
WAYS_OUT = frozenset({"move", "restart", "endGame"})


def _gets_out(scene: Scene) -> bool:
    """Whether a scene contains an effect that leaves the location.

    Parameters
    ----------
    scene : Scene
        The scene to search.

    Returns
    -------
    bool
        Whether anything in it moves the player, restarts, or ends the game.
    """
    effects = [*scene.effects]
    for choice in scene.choices:
        effects.extend(choice.effects)
    return any(effect.tag in WAYS_OUT for effect in effects)


def _check_combat(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """A fighter must be able to fight, and a pattern must be playable.

    Three mistakes are worth catching before a fight starts rather than in the
    middle of one: a pattern naming a move its profile does not know, an attack
    no defense in the pack can beat, and a fighter with nothing to answer with.
    All three produce a fight rather than a crash, which is exactly why they
    would otherwise go unnoticed until a playtester lost one.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        Errors for unplayable patterns, warnings for unanswerable attacks.
    """
    for local_id, profile in pack.combat_profiles.items():
        known = {
            resolved
            for reference in profile.moves
            if (resolved := _resolve(library, pack, reference, "moves")) is not None
        }
        for index, pattern in enumerate(profile.patterns):
            for step, reference in enumerate(pattern.sequence):
                resolved = _resolve(library, pack, reference, "moves")
                if resolved is None or resolved in known:
                    continue
                yield Problem(
                    severity=Severity.ERROR,
                    message=(
                        f"plays `{reference}`, which is not in this profile's "
                        "`moves`, so the fighter does not know it"
                    ),
                    pack=pack.id,
                    collection="combatProfiles",
                    object_id=local_id,
                    field=f"patterns[{index}].sequence[{step}]",
                )

        if known and not any(
            _move(library, resolved).kind == "defense" for resolved in sorted(known)
        ):
            yield Problem(
                severity=Severity.NOTE,
                message=(
                    "knows no defense moves, so a fighter using it can only "
                    "take the hit. Deliberate for a thing that never blocks."
                ),
                pack=pack.id,
                collection="combatProfiles",
                object_id=local_id,
                field="moves",
            )

    answers = _defense_types(library, pack)
    for local_id, move in pack.moves.items():
        if move.kind != "attack":
            continue
        if not move.counters:
            yield Problem(
                severity=Severity.WARNING,
                message=(
                    "has no `counters`, so no read is ever the right one and "
                    "the move is pure damage"
                ),
                pack=pack.id,
                collection="moves",
                object_id=local_id,
                field="counters",
            )
            continue
        unanswered = [name for name in move.counters if name not in answers]
        if unanswered:
            yield Problem(
                severity=Severity.WARNING,
                message=(
                    f"is beaten by {', '.join(f'`{name}`' for name in unanswered)}, "
                    "which no defense move here or in this pack's dependencies "
                    "has as its `type`"
                ),
                pack=pack.id,
                collection="moves",
                object_id=local_id,
                field="counters",
            )


def _defense_types(library: Library, pack: LoadedPack) -> set[str]:
    """Every defense type a pack can see, its dependencies included.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack : LoadedPack
        The pack whose view to take.

    Returns
    -------
    set of str
        The `type` of every defense move in scope.
    """
    visible = [pack, *(library.pack(r.id) for r in pack.manifest.requires)]
    return {
        move.type
        for source in visible
        for move in source.moves.values()
        if move.kind == "defense"
    }


def _resolve(
    library: Library, pack: LoadedPack, reference: str, collection: str
) -> str | None:
    """Qualify a reference, or None when it names nothing.

    Parameters
    ----------
    library : Library
        The loaded packs.
    pack : LoadedPack
        The pack the reference was written in.
    reference : str
        As the author wrote it.
    collection : str
        Where to look.

    Returns
    -------
    str or None
        The qualified id, or None. A dangling reference is already reported by
        the reference check, so it is skipped rather than reported twice.
    """
    try:
        return library.resolve(reference, collection, within=pack.id)
    except ContentError:
        return None


def _move(library: Library, qualified: str) -> Move:
    """Look up a move by qualified id.

    Parameters
    ----------
    library : Library
        The loaded packs.
    qualified : str
        The qualified id.

    Returns
    -------
    Move
        The move.
    """
    pack_id, local_id = qualified.split(":", 1)
    found = library.pack(pack_id).moves[local_id]
    return found


def _check_notes(library: Library, pack: LoadedPack) -> Iterator[Problem]:
    """Observations that are usually worth a look and sometimes deliberate.

    Parameters
    ----------
    library : Library
        The loaded packs, for resolution.
    pack : LoadedPack
        The pack to check.

    Yields
    ------
    Problem
        Notes and low-severity warnings.
    """
    for local_id, route in pack.routes.items():
        if route.danger_level and route.encounters is None:
            yield Problem(
                severity=Severity.NOTE,
                message=(
                    f"has `dangerLevel: {route.danger_level}` but no encounter "
                    "table, so nothing will ever happen on it"
                ),
                pack=pack.id,
                collection="routes",
                object_id=local_id,
                field="encounters",
            )

    for local_id, scene in pack.scenes.items():
        if not (scene.say or scene.effects or scene.choices or scene.goto):
            yield Problem(
                severity=Severity.WARNING,
                message="says nothing, changes nothing, and leads nowhere",
                pack=pack.id,
                collection="scenes",
                object_id=local_id,
            )

    yield from _check_dead_ends(library, pack)
