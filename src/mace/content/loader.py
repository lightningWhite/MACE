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
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
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
from mace.model import Game, Pack
from mace.model.base import ContentModel
from mace.model.jsonschema import UNMODELLED_COLLECTIONS

__all__ = ["load_library", "load_pack_manifest"]

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


def load_library(*roots: Path) -> Library:
    """Load every pack under the given roots.

    Parameters
    ----------
    *roots : Path
        Directories to search. A root that is itself a pack loads just that one.

    Returns
    -------
    Library
        The loaded packs, in dependency order.

    Raises
    ------
    ContentError
        If discovery, ordering, inheritance, or validation fails.
    """
    directories: dict[str, Path] = {}
    manifests: dict[str, Pack] = {}
    for root in roots:
        for pack_root in find_packs(root):
            manifest = load_pack_manifest(pack_root)
            if manifest.id in manifests:
                raise ContentError(
                    f"pack id `{manifest.id}` is claimed twice: "
                    f"{directories[manifest.id]} and {pack_root}",
                    path=pack_root,
                )
            manifests[manifest.id] = manifest
            directories[manifest.id] = pack_root

    loaded: dict[str, LoadedPack] = {}
    for pack_id in _dependency_order(manifests):
        loaded[pack_id] = _load_pack(
            manifests[pack_id], directories[pack_id], Library(tuple(loaded.values()))
        )
    return Library(tuple(loaded.values()))


def _dependency_order(manifests: Mapping[str, Pack]) -> list[str]:
    """Order packs so each comes after everything it requires.

    Parameters
    ----------
    manifests : mapping
        Pack id to manifest.

    Returns
    -------
    list of str
        Pack ids, dependencies first.

    Raises
    ------
    ContentError
        If a dependency is missing, or the graph has a cycle.
    """
    ordered: list[str] = []
    settled: set[str] = set()
    visiting: list[str] = []

    def visit(pack_id: str) -> None:
        if pack_id in settled:
            return
        if pack_id in visiting:
            cycle = " → ".join([*visiting[visiting.index(pack_id) :], pack_id])
            raise ContentError(f"packs depend on each other in a cycle: {cycle}")

        visiting.append(pack_id)
        for requirement in manifests[pack_id].requires:
            if requirement.id not in manifests:
                raise ContentError(
                    f"requires `{requirement.id}`, which was not found. Is it "
                    "in one of the pack directories being loaded?",
                    pack=pack_id,
                )
            visit(requirement.id)
        visiting.pop()

        settled.add(pack_id)
        ordered.append(pack_id)

    for pack_id in sorted(manifests):
        visit(pack_id)
    return ordered


def _load_pack(manifest: Pack, root: Path, dependencies: Library) -> LoadedPack:
    """Load one pack, given everything it depends on.

    Parameters
    ----------
    manifest : Pack
        The pack's validated manifest.
    root : Path
        The pack directory.
    dependencies : Library
        The already-loaded packs this one may reference.

    Returns
    -------
    LoadedPack
        The loaded pack.

    Raises
    ------
    ContentError
        If any of the pack's content is invalid.
    """
    raw, unmodelled, game_data, game_path = _gather(manifest, root)

    built: dict[str, dict[str, ContentModel]] = {
        collection: _build_collection(
            manifest, collection, raw.get(collection, {}), dependencies
        )
        for collection in COLLECTION_MODELS
    }

    game = None
    if game_data is not None:
        try:
            game = Game.model_validate(game_data)
        except ValidationError as error:
            raise ContentError(
                _readable(error), pack=manifest.id, path=game_path, collection=GAME_KEY
            ) from error
    elif manifest.is_game:
        raise ContentError(
            "is a game pack but has no `game:` manifest", pack=manifest.id, path=root
        )

    return LoadedPack(
        manifest=manifest,
        root=root,
        calendars=built["calendars"],  # type: ignore[arg-type]
        celestial_events=built["celestialEvents"],  # type: ignore[arg-type]
        climates=built["climates"],  # type: ignore[arg-type]
        combat_profiles=built["combatProfiles"],  # type: ignore[arg-type]
        encounter_tables=built["encounterTables"],  # type: ignore[arg-type]
        entities=built["entities"],  # type: ignore[arg-type]
        locations=built["locations"],  # type: ignore[arg-type]
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
        unmodelled=unmodelled,
    )


def _gather(manifest: Pack, root: Path) -> tuple[
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

    Returns
    -------
    tuple
        Raw objects by collection and local id, raw unmodelled collections, the
        game manifest data, and the file the game manifest came from.

    Raises
    ------
    ContentError
        If a file is shaped wrong, or two objects claim the same id.
    """
    raw: dict[str, dict[str, _RawObject]] = {}
    unmodelled: dict[str, list[Any]] = {}
    game_data: Any = None
    game_path: Path | None = None

    for path in content_files(root):
        document = read_yaml(path)
        if document is None:
            continue
        if not isinstance(document, Mapping):
            raise ContentError(
                "a content file must be a mapping of collection names to "
                f"their objects; this one is a {type(document).__name__}",
                pack=manifest.id,
                path=path,
            )

        for collection, body in document.items():
            if collection == GAME_KEY:
                if game_data is not None:
                    raise ContentError(
                        f"a second `game:` manifest; the first was in {game_path}",
                        pack=manifest.id,
                        path=path,
                    )
                game_data, game_path = body, path
                continue

            if collection in UNMODELLED_COLLECTIONS:
                unmodelled.setdefault(collection, []).extend(body or ())
                continue

            if collection not in COLLECTION_MODELS:
                raise ContentError(
                    _unknown_collection(str(collection)),
                    pack=manifest.id,
                    path=path,
                )

            _index(raw.setdefault(collection, {}), collection, body, path, manifest)

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

    Raises
    ------
    ContentError
        If the body is not a list of objects with ids, or an id repeats.
    """
    if body is None:
        return
    if not isinstance(body, list):
        raise ContentError(
            f"`{collection}:` must be a list of definitions, not a "
            f"{type(body).__name__}",
            pack=manifest.id,
            path=path,
            collection=collection,
        )

    for entry in body:
        if not isinstance(entry, Mapping) or "id" not in entry:
            raise ContentError(
                "every definition needs an `id`",
                pack=manifest.id,
                path=path,
                collection=collection,
            )
        local_id = str(entry["id"])
        if local_id in target:
            raise ContentError(
                f"is defined twice — also in {target[local_id].path}. Ids are "
                "unique within a pack, however the files are organized.",
                pack=manifest.id,
                path=path,
                collection=collection,
                object_id=local_id,
            )
        target[local_id] = _RawObject(entry, path)


def _build_collection(
    manifest: Pack,
    collection: str,
    raw: Mapping[str, _RawObject],
    dependencies: Library,
) -> dict[str, ContentModel]:
    """Resolve inheritance and validate every object in one collection.

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

    Returns
    -------
    dict
        Local id to validated definition.

    Raises
    ------
    ContentError
        If inheritance or validation fails.
    """
    model = COLLECTION_MODELS[collection]
    resolved: dict[str, ContentModel] = {}
    merged: dict[str, Mapping[str, Any]] = {}

    def build(local_id: str, chain: tuple[str, ...]) -> Mapping[str, Any]:
        if local_id in merged:
            return merged[local_id]
        if local_id in chain:
            trail = " → ".join([*chain[chain.index(local_id) :], local_id])
            raise ContentError(
                f"extends itself in a cycle: {trail}",
                pack=manifest.id,
                collection=collection,
                object_id=local_id,
            )

        entry = raw[local_id]
        data: Mapping[str, Any] = entry.data
        parent_reference = data.get("extends")

        if parent_reference is None:
            stray = find_sentinels(data)
            if stray:
                raise ContentError(
                    f"uses the merge sentinel at {stray[0]} but extends "
                    "nothing. Sentinels only mean something against an "
                    "inherited definition.",
                    pack=manifest.id,
                    path=entry.path,
                    collection=collection,
                    object_id=local_id,
                )
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
            )
            data = merge(parent, data)

        merged[local_id] = data
        try:
            resolved[local_id] = model.model_validate(data)
        except ValidationError as error:
            raise ContentError(
                _readable(error),
                pack=manifest.id,
                path=entry.path,
                collection=collection,
                object_id=local_id,
            ) from error
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
) -> Mapping[str, Any]:
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
        Builds and returns a same-pack parent's merged mapping.

    Returns
    -------
    mapping
        The parent's definition, in authoring shape.

    Raises
    ------
    ContentError
        If the parent cannot be found, or is in a pack this one does not require.
    """
    pack_id, parent_local = split(reference)

    if pack_id in (None, manifest.id) and parent_local in raw:
        parent: Mapping[str, Any] = build_local(parent_local)
        return parent

    if pack_id is None:
        candidates = [requirement.id for requirement in manifest.requires]
    else:
        if pack_id not in {requirement.id for requirement in manifest.requires}:
            raise ContentError(
                f"extends `{reference}`, but this pack does not `require` "
                f"`{pack_id}`",
                pack=manifest.id,
                path=path,
                collection=collection,
                object_id=local_id,
            )
        candidates = [pack_id]

    for candidate in candidates:
        definitions = dependencies.pack(candidate).collection(collection)
        if parent_local in definitions:
            return dict(definitions[parent_local].authored())

    raise ContentError(
        f"extends `{reference}`, which is not a {SINGULAR[collection]} here or in "
        f"{', '.join(f'`{name}`' for name in candidates) or 'any dependency'}",
        pack=manifest.id,
        path=path,
        collection=collection,
        object_id=local_id,
    )


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
