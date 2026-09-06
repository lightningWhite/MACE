"""The content layer: packs on disk to an immutable compiled Library.

Discovery, namespaced id resolution, `extends` inheritance, dependency ordering,
and schema validation. Reads `packs/`; never reads session state.
See docs/03-content-model.md and docs/04-schema-reference.md.
"""

from mace.content.discovery import MANIFEST_NAME, content_files, find_packs, read_yaml
from mace.content.errors import ContentError
from mace.content.ids import QUALIFIER, is_qualified, qualify, split
from mace.content.library import COLLECTION_MODELS, SINGULAR, Library, LoadedPack
from mace.content.loader import load_library, load_pack_manifest
from mace.content.merge import APPEND, REMOVE, find_sentinels, merge

__all__ = [
    "APPEND",
    "COLLECTION_MODELS",
    "ContentError",
    "Library",
    "LoadedPack",
    "MANIFEST_NAME",
    "QUALIFIER",
    "REMOVE",
    "SINGULAR",
    "content_files",
    "find_packs",
    "find_sentinels",
    "is_qualified",
    "load_library",
    "load_pack_manifest",
    "merge",
    "qualify",
    "read_yaml",
    "split",
]
