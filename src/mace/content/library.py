"""The loaded result: packs in dependency order, and how to look things up.

A `Library` is what the content layer hands the engine. It is immutable, it
holds no session state, and it is the only thing that knows how a bare
reference in one pack finds its way to a definition in another.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mace.content.errors import ContentError
from mace.content.ids import qualify, split
from mace.model import (
    Calendar,
    Climate,
    EncounterTable,
    Entity,
    Game,
    Location,
    Pack,
    Quest,
    Region,
    Route,
    Scene,
    WeatherCondition,
    WeatherFront,
)
from mace.model.base import ContentModel

__all__ = ["COLLECTION_MODELS", "SINGULAR", "LoadedPack", "Library"]

#: The collection each modelled content type lives in. The loader and the
#: resolver both key off this, so adding a content type is one entry here plus
#: a field on `LoadedPack`.
COLLECTION_MODELS: dict[str, type[ContentModel]] = {
    "calendars": Calendar,
    "climates": Climate,
    "encounterTables": EncounterTable,
    "entities": Entity,
    "locations": Location,
    "regions": Region,
    "routes": Route,
    "weatherConditions": WeatherCondition,
    "weatherFronts": WeatherFront,
    "scenes": Scene,
    "quests": Quest,
}


#: What one member of each collection is called, for error messages. English
#: plurals are not a rule you can apply, and `entitie` in an error message
#: undermines everything else the message is trying to do.
SINGULAR: dict[str, str] = {
    "calendars": "calendar",
    "climates": "climate",
    "encounterTables": "encounter table",
    "entities": "entity",
    "locations": "location",
    "regions": "region",
    "routes": "route",
    "weatherConditions": "weather condition",
    "weatherFronts": "weather front",
    "scenes": "scene",
    "quests": "quest",
}


#: Collections whose Python field name differs from their content key, so
#: `weatherConditions:` in YAML stays camelCase and the attribute stays
#: snake_case like every other attribute in the codebase.
_FIELDS: dict[str, str] = {
    "encounterTables": "encounter_tables",
    "weatherConditions": "weather_conditions",
    "weatherFronts": "weather_fronts",
}


@dataclass(frozen=True, slots=True)
class LoadedPack:
    """One pack, loaded and validated.

    Attributes
    ----------
    manifest : Pack
        The pack's `pack.yml`.
    root : Path
        The directory it was read from.
    calendars, climates, encounterTables, entities, locations, regions, routes,
    scenes, quests,
    weatherConditions, weatherFronts : mapping
        Local id to definition, for each modelled collection.
    game : Game or None
        The game manifest, for `kind: game` packs.
    unmodelled : mapping
        Collections the docs describe but no model covers yet, kept as raw data
        so a later phase can model them without the loader changing.
    """

    manifest: Pack
    root: Path
    calendars: Mapping[str, Calendar]
    climates: Mapping[str, Climate]
    encounter_tables: Mapping[str, EncounterTable]
    entities: Mapping[str, Entity]
    locations: Mapping[str, Location]
    regions: Mapping[str, Region]
    routes: Mapping[str, Route]
    scenes: Mapping[str, Scene]
    quests: Mapping[str, Quest]
    weather_conditions: Mapping[str, WeatherCondition]
    weather_fronts: Mapping[str, WeatherFront]
    game: Game | None
    unmodelled: Mapping[str, tuple[Any, ...]]

    @property
    def id(self) -> str:
        """The pack's id.

        Returns
        -------
        str
            The manifest id.
        """
        return self.manifest.id

    def collection(self, name: str) -> Mapping[str, ContentModel]:
        """Look up one collection by name.

        Parameters
        ----------
        name : str
            A key of `COLLECTION_MODELS`.

        Returns
        -------
        mapping
            Local id to definition.

        Raises
        ------
        KeyError
            If the name is not a modelled collection.
        """
        if name not in COLLECTION_MODELS:
            raise KeyError(f"no such collection: {name}")
        collected: Mapping[str, ContentModel] = getattr(self, _FIELDS.get(name, name))
        return collected


@dataclass(frozen=True, slots=True)
class Library:
    """Every loaded pack, in dependency order.

    A pack always appears after everything it requires, so anything resolving a
    reference forward through this list is looking at definitions that already
    exist.

    Attributes
    ----------
    packs : tuple of LoadedPack
        The loaded packs, dependencies first.
    """

    packs: tuple[LoadedPack, ...]

    @property
    def by_id(self) -> Mapping[str, LoadedPack]:
        """The packs, keyed by id.

        Returns
        -------
        mapping
            Pack id to loaded pack.
        """
        return {pack.id: pack for pack in self.packs}

    @property
    def games(self) -> tuple[LoadedPack, ...]:
        """The playable packs.

        Returns
        -------
        tuple of LoadedPack
            Packs with `kind: game`, in dependency order.
        """
        return tuple(pack for pack in self.packs if pack.manifest.is_game)

    def pack(self, pack_id: str) -> LoadedPack:
        """Look up one pack.

        Parameters
        ----------
        pack_id : str
            The pack's id.

        Returns
        -------
        LoadedPack
            The loaded pack.

        Raises
        ------
        ContentError
            If no such pack is loaded.
        """
        try:
            return self.by_id[pack_id]
        except KeyError:
            known = ", ".join(sorted(self.by_id)) or "none"
            raise ContentError(
                f"no pack `{pack_id}` is loaded; loaded packs: {known}"
            ) from None

    def resolve(self, reference: str, collection: str, *, within: str) -> str:
        """Turn a reference written inside a pack into a fully qualified id.

        A qualified reference is checked and returned. A bare one is looked for
        in the referring pack, then in each of its direct dependencies in the
        order `requires` lists them — and if more than one dependency offers it,
        that is an error rather than a silent choice.

        Parameters
        ----------
        reference : str
            The reference as the author wrote it.
        collection : str
            Which collection to look in — `entities`, `scenes`, and so on.
        within : str
            The id of the pack the reference was written in.

        Returns
        -------
        str
            The fully qualified id.

        Raises
        ------
        ContentError
            If the reference names nothing, or names more than one thing.
        """
        home = self.pack(within)
        pack_id, local_id = split(reference)

        if pack_id is not None:
            if local_id in self.pack(pack_id).collection(collection):
                return reference
            raise ContentError(
                f"`{reference}` is not a {SINGULAR[collection]} in pack `{pack_id}`",
                pack=within,
                collection=collection,
            )

        if local_id in home.collection(collection):
            return qualify(within, local_id)

        matches = [
            requirement.id
            for requirement in home.manifest.requires
            if local_id in self.pack(requirement.id).collection(collection)
        ]
        if len(matches) == 1:
            return qualify(matches[0], local_id)
        if not matches:
            raise ContentError(
                f"nothing named `{local_id}` in {collection}, here or in "
                f"{self._dependency_summary(home)}",
                pack=within,
                collection=collection,
            )
        offered = ", ".join(f"`{qualify(match, local_id)}`" for match in matches)
        raise ContentError(
            f"`{local_id}` is ambiguous — {offered} both match. Write the "
            "qualified id.",
            pack=within,
            collection=collection,
        )

    def find(self, reference: str, collection: str, *, within: str) -> ContentModel:
        """Resolve a reference and return what it names.

        Parameters
        ----------
        reference : str
            The reference as the author wrote it.
        collection : str
            Which collection to look in.
        within : str
            The id of the pack the reference was written in.

        Returns
        -------
        ContentModel
            The definition referred to.

        Raises
        ------
        ContentError
            If the reference cannot be resolved.
        """
        qualified = self.resolve(reference, collection, within=within)
        pack_id, local_id = split(qualified)
        assert pack_id is not None
        return self.pack(pack_id).collection(collection)[local_id]

    @staticmethod
    def _dependency_summary(pack: LoadedPack) -> str:
        """Name a pack's dependencies for an error message.

        Parameters
        ----------
        pack : LoadedPack
            The pack whose dependencies to name.

        Returns
        -------
        str
            A readable list, or a note that it has none.
        """
        names = [requirement.id for requirement in pack.manifest.requires]
        if not names:
            return "no dependencies (this pack `requires` nothing)"
        return ", ".join(f"`{name}`" for name in names)
