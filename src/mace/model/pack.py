"""The pack manifest — the unit of distribution.

A pack is a directory with a `pack.yml`. Everything else in it is content the
loader globs and merges by id, so authors can organize files however the world
makes sense: one file per location, or one file for all of them.
"""

from __future__ import annotations

from typing import Literal

from mace.model.base import (
    ContentModel,
    PackId,
    Tag,
    Version,
    VersionRange,
)

__all__ = [
    "Pack",
    "PackKind",
    "PackRequirement",
]

PackKind = Literal["library", "game"]


class PackRequirement(ContentModel):
    """A dependency on another pack.

    Attributes
    ----------
    id : str
        The pack depended on.
    version : str
        The version range this pack was written against.
    """

    id: PackId
    version: VersionRange


class Pack(ContentModel):
    """A pack's manifest.

    Attributes
    ----------
    id : str
        Dotted namespace, globally unique — `fantasy.core`, `peasants-quest`.
    name : str
        Human-readable title.
    version : str
        Semantic version. Minor for additions, major for breaking id changes.
    kind : {'library', 'game'}
        Games appear in the play menu; libraries are there to be built on.
    mace_version : str
        The engine version range this pack works with.
    requires : tuple of PackRequirement
        Dependency packs, in the order bare references resolve against them.
    """

    id: PackId
    name: str
    version: Version
    kind: PackKind
    mace_version: VersionRange
    authors: tuple[str, ...] = ()
    license: str | None = None
    description: str | None = None
    tags: tuple[Tag, ...] = ()
    requires: tuple[PackRequirement, ...] = ()

    @property
    def is_game(self) -> bool:
        """Whether this pack is playable rather than a library.

        Returns
        -------
        bool
            True for `kind: game`.
        """
        return self.kind == "game"
