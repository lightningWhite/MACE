"""Turning directories of YAML into a validated, immutable `Library`.

The order matters and is the whole job:

1. **Discover** every pack under the given roots and read its manifest.
2. **Order** the packs so a pack is loaded after everything it `requires`.
3. **Gather** each pack's raw objects by collection and local id.
4. **Resolve `extends`**, merging raw mappings so a child may inherit anything
   and the merge sentinels never reach a model.
5. **Validate**, building the pydantic models.

Steps 4 and 5 are in that order on purpose — see docs/03-content-model.md
§ Inheritance. Everything here is at the content layer: it reads the
filesystem, which the engine may never do.

Every step takes a `Tolerance`, which decides whether a thing that cannot be
built stops the load or is recorded and stepped over. Playing wants the former;
authoring wants the latter, because a half-written pack is the normal state of
a pack being written. See `mace.content.tolerance`.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mace.content.discovery import (
    MANIFEST_NAME,
    content_files,
    find_packs,
    read_yaml,
)
from mace.content.errors import ContentError
from mace.content.ids import split
from mace.content.library import COLLECTION_MODELS, SINGULAR, Library, LoadedPack
from mace.content.merge import find_sentinels, merge
from mace.content.tolerance import STRICT, Tolerance, collecting
from mace.model import Game, Pack
from mace.model.base import ContentModel
from mace.model.jsonschema import UNMODELLED_COLLECTIONS

__all__ = ["Loaded", "load_best_effort", "load_library", "load_pack_manifest"]

#: A content file's top-level key for the game manifest.
GAME_KEY = "game"


class _RawObject:
    """One authored definition, with the file it came from.

    Parameters
    ----------
    data : mapping
        The raw definition.
    path : Path
        The file it was read from, kept for error messages.
    """

    __slots__ = ("data", "path")

    def __init__(self, data: Mapping[str, Any], path: Path) -> None:
        self.data = data
        self.path = path


def load_pack_manifest(pack_root: Path) -> Pack:
    """Read and validate one pack's manifest.

    Parameters
    ----------
    pack_root : Path
        The pack directory.

    Returns
    -------
    Pack
        The validated manifest.

    Raises
    ------
    ContentError
        If the manifest is missing or invalid.
    """
    path = pack_root / MANIFEST_NAME
    if not path.is_file():
        raise ContentError(f"no {MANIFEST_NAME} here", path=pack_root)
    data = read_yaml(path)
    if not isinstance(data, Mapping):
        raise ContentError("a manifest must be a mapping of fields", path=path)
    try:
        return Pack.model_validate(data)
    except ValidationError as error:
        raise ContentError(_readable(error), path=path) from error


def load_library(*roots: Path, tolerance: Tolerance = STRICT) -> Library:
    """Load every pack under the given roots.

    Parameters
    ----------
    *roots : Path
        Directories to search. A root that is itself a pack loads just that one.
    tolerance : Tolerance
        Whether to stop at the first thing that cannot be built. Defaults to
        stopping; `load_best_effort` is the other way round.

    Returns
    -------
    Library
        The loaded packs, in dependency order. Under a collecting tolerance,
        packs and objects that failed are simply absent.

    Raises
    ------
    ContentError
        If discovery, ordering, inheritance, or validation fails and the
        tolerance is strict.
    """
    directories: dict[str, Path] = {}
    manifests: dict[str, Pack] = {}
    for root in roots:
        for pack_root in find_packs(root):
            try:
                manifest = load_pack_manifest(pack_root)
            except ContentError as error:
                tolerance.fail(error)
                continue
            if manifest.id in manifests:
                tolerance.fail(
                    ContentError(
                        f"pack id `{manifest.id}` is claimed twice: "
                        f"{directories[manifest.id]} and {pack_root}",
                        path=pack_root,
                    )
                )
                continue
            manifests[manifest.id] = manifest
            directories[manifest.id] = pack_root

    loaded: dict[str, LoadedPack] = {}
    for pack_id in _dependency_order(manifests, tolerance):
        loaded[pack_id] = _load_pack(
            manifests[pack_id],
            directories[pack_id],
            Library(tuple(loaded.values())),
            tolerance,
        )
    return Library(tuple(loaded.values()))


@dataclass(frozen=True, slots=True)
class Loaded:
    """A best-effort load: what compiled, and what did not.

    Attributes
    ----------
    library : Library
        Everything that built. Objects that failed are absent from it, so what
        is here is as usable as any strictly-loaded library.
    problems : tuple of ContentError
        Everything that did not, in the order it was found.
    """

    library: Library
    problems: tuple[ContentError, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether everything built.

        Returns
        -------
        bool
            True when nothing was skipped.
        """
        return not self.problems


def load_best_effort(*roots: Path) -> Loaded:
    """Load everything that can be loaded, and report what could not.

    What the wizard opens a project with. One misspelled field on one location
    should cost the author that location, not the rest of their world.

    Parameters
    ----------
    *roots : Path
        Directories to search.

    Returns
    -------
    Loaded
        The library, and every failure found building it.
    """
    tolerance = collecting()
    library = load_library(*roots, tolerance=tolerance)
    return Loaded(library, tuple(tolerance.problems))


def _dependency_order(
    manifests: Mapping[str, Pack], tolerance: Tolerance = STRICT
) -> list[str]:
    """Order packs so each comes after everything it requires.

    A pack whose dependency is missing, or which is caught in a cycle, is left
    out of the order entirely rather than loaded without it. Loading it anyway
    would make every bare reference into that dependency resolve to nothing,
    and bury the one real problem — "this pack requires `fantasy.core`, which
    is not here" — under a hundred consequences of it.

    Parameters
    ----------
    manifests : mapping
        Pack id to manifest.
    tolerance : Tolerance
        Whether a missing dependency or a cycle stops the load.

    Returns
    -------
    list of str
        Pack ids, dependencies first. Packs that could not be ordered are
        absent.

    Raises
    ------
    ContentError
        If a dependency is missing or the graph has a cycle, and the tolerance
        is strict.
    """
    ordered: list[str] = []
    settled: set[str] = set()
    unusable: set[str] = set()
    visiting: list[str] = []

    def visit(pack_id: str) -> bool:
        if pack_id in settled:
            return True
        if pack_id in unusable:
            return False
        if pack_id in visiting:
            cycle = " → ".join([*visiting[visiting.index(pack_id) :], pack_id])
            tolerance.fail(
                ContentError(f"packs depend on each other in a cycle: {cycle}")
            )
            unusable.update(visiting[visiting.index(pack_id) :])
            return False

        visiting.append(pack_id)
        try:
            for requirement in manifests[pack_id].requires:
                if requirement.id not in manifests:
                    tolerance.fail(
                        ContentError(
                            f"requires `{requirement.id}`, which was not found. "
                            "Is it in one of the pack directories being loaded?",
                            pack=pack_id,
                        )
                    )
                    unusable.add(pack_id)
                    return False
                if not visit(requirement.id):
                    unusable.add(pack_id)
                    return False
        finally:
            visiting.pop()

        if pack_id in unusable:
            return False
        settled.add(pack_id)
        ordered.append(pack_id)
        return True

    for pack_id in sorted(manifests):
        visit(pack_id)
    return ordered


def _load_pack(
    manifest: Pack,
    root: Path,
    dependencies: Library,
    tolerance: Tolerance = STRICT,
) -> LoadedPack:
    """Load one pack, given everything it depends on.

    Parameters
    ----------
    manifest : Pack
        The pack's validated manifest.
    root : Path
        The pack directory.
    dependencies : Library
        The already-loaded packs this one may reference.
    tolerance : Tolerance
        Whether one bad object stops the pack.

    Returns
    -------
    LoadedPack
        The loaded pack. Under a collecting tolerance, objects that failed are
        absent from it.

    Raises
    ------
    ContentError
        If any of the pack's content is invalid and the tolerance is strict.
    """
    raw, unmodelled, game_data, game_path = _gather(manifest, root, tolerance)
    return compile_pack(
        manifest,
        root,
        {
            collection: {name: entry.data for name, entry in objects.items()}
            for collection, objects in raw.items()
        },
        unmodelled,
        game_data,
        dependencies,
        tolerance,
        homes={
            name: entry.path
            for objects in raw.values()
            for name, entry in objects.items()
        },
        game_path=game_path,
    )


def compile_pack(
    manifest: Pack,
    root: Path,
    raw: Mapping[str, Mapping[str, Mapping[str, Any]]],
    unmodelled: Mapping[str, tuple[Any, ...]],
    game_data: Any,
    dependencies: Library,
    tolerance: Tolerance = STRICT,
    *,
    homes: Mapping[str, Path] | None = None,
    game_path: Path | None = None,
) -> LoadedPack:
    """Turn already-gathered raw objects into a loaded pack.

    Split out from reading the filesystem so the wizard can compile what it is
    holding rather than what is on disk. "Playtest from anywhere, unsaved
    changes included" is the single feature that keeps authors iterating, and
    a compile step that could only see saved files would make it a lie.

    Parameters
    ----------
    manifest : Pack
        The pack's validated manifest.
    root : Path
        The pack directory, for error messages.
    raw : mapping
        Collection name to local id to authored mapping.
    unmodelled : mapping
        Collections no model covers yet, kept as they were written.
    game_data : object
        The `game:` manifest's raw body, or None.
    dependencies : Library
        The already-loaded packs this one may reference.
    tolerance : Tolerance
        Whether one bad object stops the pack.
    homes : mapping or None
        Local id to the file it came from, for error messages.
    game_path : Path or None
        The file the game manifest came from.

    Returns
    -------
    LoadedPack
        The loaded pack.

    Raises
    ------
    ContentError
        If any of the content is invalid and the tolerance is strict.
    """
    indexed: dict[str, dict[str, _RawObject]] = {
        collection: {
            name: _RawObject(data, (homes or {}).get(name, root))
            for name, data in objects.items()
        }
        for collection, objects in raw.items()
    }

    built: dict[str, dict[str, ContentModel]] = {
        collection: _build_collection(
            manifest, collection, indexed.get(collection, {}), dependencies, tolerance
        )
        for collection in COLLECTION_MODELS
    }

    game = None
    if game_data is not None:
        try:
            game = Game.model_validate(game_data)
        except ValidationError as error:
            tolerance.fail(
                ContentError(
                    _readable(error),
                    pack=manifest.id,
                    path=game_path,
                    collection=GAME_KEY,
                )
            )
    elif manifest.is_game:
        tolerance.fail(
            ContentError(
                "is a game pack but has no `game:` manifest",
                pack=manifest.id,
                path=root,
            )
        )

    return LoadedPack(
        manifest=manifest,
        root=root,
        backgrounds=built["backgrounds"],  # type: ignore[arg-type]
        calendars=built["calendars"],  # type: ignore[arg-type]
        celestial_events=built["celestialEvents"],  # type: ignore[arg-type]
        climates=built["climates"],  # type: ignore[arg-type]
        combat_profiles=built["combatProfiles"],  # type: ignore[arg-type]
        encounter_tables=built["encounterTables"],  # type: ignore[arg-type]
        entities=built["entities"],  # type: ignore[arg-type]
        goods=built["goods"],  # type: ignore[arg-type]
        locations=built["locations"],  # type: ignore[arg-type]
        markets=built["markets"],  # type: ignore[arg-type]
        moves=built["moves"],  # type: ignore[arg-type]
        pressure_events=built["pressureEvents"],  # type: ignore[arg-type]
        regions=built["regions"],  # type: ignore[arg-type]
        routes=built["routes"],  # type: ignore[arg-type]
        scenes=built["scenes"],  # type: ignore[arg-type]
        terrains=built["terrains"],  # type: ignore[arg-type]
        quests=built["quests"],  # type: ignore[arg-type]
        weather_conditions=built["weatherConditions"],  # type: ignore[arg-type]
        weather_fronts=built["weatherFronts"],  # type: ignore[arg-type]
        game=game,
        unmodelled=dict(unmodelled),
    )


def _gather(manifest: Pack, root: Path, tolerance: Tolerance = STRICT) -> tuple[
    dict[str, dict[str, _RawObject]],
    dict[str, tuple[Any, ...]],
    Any,
    Path | None,
]:
    """Read every content file in a pack and index it by collection and id.

    Parameters
    ----------
    manifest : Pack
        The pack's manifest, for error messages.
    root : Path
        The pack directory.
    tolerance : Tolerance
        Whether one malformed file stops the pack.

    Returns
    -------
    tuple
        Raw objects by collection and local id, raw unmodelled collections, the
        game manifest data, and the file the game manifest came from.

    Raises
    ------
    ContentError
        If a file is shaped wrong or two objects claim the same id, and the
        tolerance is strict.
    """
    raw: dict[str, dict[str, _RawObject]] = {}
    unmodelled: dict[str, list[Any]] = {}
    game_data: Any = None
    game_path: Path | None = None

    for path in content_files(root):
        try:
            document = read_yaml(path)
        except ContentError as error:
            tolerance.fail(error)
            continue
        if document is None:
            continue
        if not isinstance(document, Mapping):
            tolerance.fail(
                ContentError(
                    "a content file must be a mapping of collection names to "
                    f"their objects; this one is a {type(document).__name__}",
                    pack=manifest.id,
                    path=path,
                )
            )
            continue

        for collection, body in document.items():
            if collection == GAME_KEY:
                if game_data is not None:
                    tolerance.fail(
                        ContentError(
                            f"a second `game:` manifest; the first was in "
                            f"{game_path}",
                            pack=manifest.id,
                            path=path,
                        )
                    )
                    continue
                game_data, game_path = body, path
                continue

            if collection in UNMODELLED_COLLECTIONS:
                unmodelled.setdefault(collection, []).extend(body or ())
                continue

            if collection not in COLLECTION_MODELS:
                tolerance.fail(
                    ContentError(
                        _unknown_collection(str(collection)),
                        pack=manifest.id,
                        path=path,
                    )
                )
                continue

            _index(
                raw.setdefault(collection, {}),
                collection,
                body,
                path,
                manifest,
                tolerance,
            )

    return (
        raw,
        {key: tuple(value) for key, value in unmodelled.items()},
        game_data,
        game_path,
    )


def _index(
    target: dict[str, _RawObject],
    collection: str,
    body: Any,
    path: Path,
    manifest: Pack,
    tolerance: Tolerance = STRICT,
) -> None:
    """Add one file's objects for a collection to the pack-wide index.

    Parameters
    ----------
    target : dict
        Local id to raw object, modified in place.
    collection : str
        The collection being indexed.
    body : object
        The file's value for that collection.
    path : Path
        The file, for error messages.
    manifest : Pack
        The pack, for error messages.
    tolerance : Tolerance
        Whether one malformed entry stops the file.

    Raises
    ------
    ContentError
        If the body is not a list of objects with ids or an id repeats, and
        the tolerance is strict.
    """
    if body is None:
        return
    if not isinstance(body, list):
        tolerance.fail(
            ContentError(
                f"`{collection}:` must be a list of definitions, not a "
                f"{type(body).__name__}",
                pack=manifest.id,
                path=path,
                collection=collection,
            )
        )
        return

    for entry in body:
        if not isinstance(entry, Mapping) or "id" not in entry:
            tolerance.fail(
                ContentError(
                    "every definition needs an `id`",
                    pack=manifest.id,
                    path=path,
                    collection=collection,
                )
            )
            continue
        local_id = str(entry["id"])
        if local_id in target:
            tolerance.fail(
                ContentError(
                    f"is defined twice — also in {target[local_id].path}. Ids "
                    "are unique within a pack, however the files are organized.",
                    pack=manifest.id,
                    path=path,
                    collection=collection,
                    object_id=local_id,
                )
            )
            continue
        target[local_id] = _RawObject(entry, path)


def _build_collection(
    manifest: Pack,
    collection: str,
    raw: Mapping[str, _RawObject],
    dependencies: Library,
    tolerance: Tolerance = STRICT,
) -> dict[str, ContentModel]:
    """Resolve inheritance and validate every object in one collection.

    Under a collecting tolerance an object that fails is left out and the next
    one is tried, so an author gets their whole problem list rather than its
    first entry. A child of a failed object fails in its turn and is reported
    separately — a consequence, but an honest one, and saying "the parent you
    extend did not build" is more use than silence.

    Parameters
    ----------
    manifest : Pack
        The pack being loaded.
    collection : str
        Which collection to build.
    raw : mapping
        Local id to raw object.
    dependencies : Library
        Already-loaded packs, for cross-pack `extends`.
    tolerance : Tolerance
        Whether one bad object stops the collection.

    Returns
    -------
    dict
        Local id to validated definition. Objects that failed are absent.

    Raises
    ------
    ContentError
        If inheritance or validation fails and the tolerance is strict.
    """
    model = COLLECTION_MODELS[collection]
    resolved: dict[str, ContentModel] = {}
    merged: dict[str, Mapping[str, Any]] = {}
    failed: set[str] = set()

    def build(local_id: str, chain: tuple[str, ...]) -> Mapping[str, Any] | None:
        if local_id in merged:
            return merged[local_id]
        if local_id in failed:
            return None
        if local_id in chain:
            trail = " → ".join([*chain[chain.index(local_id) :], local_id])
            failed.add(local_id)
            tolerance.fail(
                ContentError(
                    f"extends itself in a cycle: {trail}",
                    pack=manifest.id,
                    collection=collection,
                    object_id=local_id,
                )
            )
            return None

        entry = raw[local_id]
        data: Mapping[str, Any] = entry.data
        parent_reference = data.get("extends")

        if parent_reference is None:
            stray = find_sentinels(data)
            if stray:
                failed.add(local_id)
                tolerance.fail(
                    ContentError(
                        f"uses the merge sentinel at {stray[0]} but extends "
                        "nothing. Sentinels only mean something against an "
                        "inherited definition.",
                        pack=manifest.id,
                        path=entry.path,
                        collection=collection,
                        object_id=local_id,
                    )
                )
                return None
        else:
            parent = _parent_definition(
                manifest,
                collection,
                local_id,
                str(parent_reference),
                entry.path,
                raw,
                dependencies,
                lambda parent_id: build(parent_id, (*chain, local_id)),
                tolerance,
            )
            if parent is None:
                failed.add(local_id)
                return None
            data = merge(parent, data)

        try:
            resolved[local_id] = model.model_validate(data)
        except ValidationError as error:
            failed.add(local_id)
            tolerance.fail(
                ContentError(
                    _readable(error),
                    pack=manifest.id,
                    path=entry.path,
                    collection=collection,
                    object_id=local_id,
                )
            )
            return None

        merged[local_id] = data
        return data

    for local_id in raw:
        build(local_id, ())
    return resolved


def _parent_definition(
    manifest: Pack,
    collection: str,
    local_id: str,
    reference: str,
    path: Path,
    raw: Mapping[str, _RawObject],
    dependencies: Library,
    build_local: Any,
    tolerance: Tolerance = STRICT,
) -> Mapping[str, Any] | None:
    """Find the definition an object extends, wherever it lives.

    A parent in the same pack is resolved first — and built first, so a child
    may appear above its parent in a file. A parent in another pack must come
    from a pack this one `requires`.

    Parameters
    ----------
    manifest : Pack
        The pack being loaded.
    collection : str
        The collection both objects belong to.
    local_id : str
        The extending object, for error messages.
    reference : str
        What the author wrote after `extends`.
    path : Path
        The file, for error messages.
    raw : mapping
        This pack's raw objects for the collection.
    dependencies : Library
        The already-loaded packs.
    build_local : callable
        Builds and returns a same-pack parent's merged mapping, or None when
        the parent itself could not be built.
    tolerance : Tolerance
        Whether a missing parent stops the load.

    Returns
    -------
    mapping or None
        The parent's definition in authoring shape, or None when it could not
        be found and the tolerance is collecting.

    Raises
    ------
    ContentError
        If the parent cannot be found, or is in a pack this one does not
        require, and the tolerance is strict.
    """
    pack_id, parent_local = split(reference)

    if pack_id in (None, manifest.id) and parent_local in raw:
        parent: Mapping[str, Any] | None = build_local(parent_local)
        if parent is None:
            tolerance.fail(
                ContentError(
                    f"extends `{reference}`, which did not build",
                    pack=manifest.id,
                    path=path,
                    collection=collection,
                    object_id=local_id,
                )
            )
        return parent

    if pack_id is None:
        candidates = [requirement.id for requirement in manifest.requires]
    else:
        if pack_id not in {requirement.id for requirement in manifest.requires}:
            tolerance.fail(
                ContentError(
                    f"extends `{reference}`, but this pack does not `require` "
                    f"`{pack_id}`",
                    pack=manifest.id,
                    path=path,
                    collection=collection,
                    object_id=local_id,
                )
            )
            return None
        candidates = [pack_id]

    for candidate in candidates:
        definitions = dependencies.pack(candidate).collection(collection)
        if parent_local in definitions:
            return dict(definitions[parent_local].authored())

    tolerance.fail(
        ContentError(
            f"extends `{reference}`, which is not a {SINGULAR[collection]} here "
            f"or in {', '.join(f'`{n}`' for n in candidates) or 'any dependency'}",
            pack=manifest.id,
            path=path,
            collection=collection,
            object_id=local_id,
        )
    )
    return None


def _unknown_collection(collection: str) -> str:
    """Explain an unrecognized top-level key.

    Parameters
    ----------
    collection : str
        The key the author wrote.

    Returns
    -------
    str
        A message naming the nearest known collection, if there is one.
    """
    known = sorted({*COLLECTION_MODELS, *UNMODELLED_COLLECTIONS, GAME_KEY})
    near = difflib.get_close_matches(collection, known, n=1)
    hint = f"; did you mean `{near[0]}`?" if near else ""
    return f"`{collection}:` is not a content collection{hint}"


def _readable(error: ValidationError) -> str:
    """Render a pydantic failure the way an author needs to read it.

    Parameters
    ----------
    error : ValidationError
        The failure.

    Returns
    -------
    str
        One line per problem, each naming the field it came from.
    """
    lines = []
    for problem in error.errors():
        location = ".".join(str(part) for part in problem["loc"]) or "(root)"
        lines.append(f"{location}: {problem['msg']}")
    return "\n  ".join(lines)
