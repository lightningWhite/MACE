"""The content layer: packs on disk to an immutable compiled Library.

Discovery, namespaced id resolution, `extends` inheritance, dependency ordering,
and schema validation. Reads `packs/`; never reads session state.
See docs/03-content-model.md and docs/04-schema-reference.md.
"""

from mace.content.discovery import MANIFEST_NAME, content_files, find_packs, read_yaml
from mace.content.errors import ContentError
from mace.content.ids import QUALIFIER, is_qualified, qualify, split
from mace.content.library import COLLECTION_MODELS, SINGULAR, Library, LoadedPack
from mace.content.loader import (
    Loaded,
    load_best_effort,
    load_library,
    load_pack_manifest,
)
from mace.content.merge import APPEND, REMOVE, find_sentinels, merge
from mace.content.tolerance import STRICT, Tolerance, collecting
from mace.content.validation import (
    Problem,
    Report,
    Severity,
    as_problem,
    validate_library,
    validate_paths,
)
from mace.content.writing import dump, write_document

__all__ = [
    "APPEND",
    "COLLECTION_MODELS",
    "ContentError",
    "Library",
    "Loaded",
    "LoadedPack",
    "MANIFEST_NAME",
    "Problem",
    "QUALIFIER",
    "REMOVE",
    "Report",
    "SINGULAR",
    "STRICT",
    "Severity",
    "Tolerance",
    "as_problem",
    "collecting",
    "content_files",
    "dump",
    "find_packs",
    "find_sentinels",
    "is_qualified",
    "load_best_effort",
    "load_library",
    "load_pack_manifest",
    "merge",
    "qualify",
    "read_yaml",
    "split",
    "validate_library",
    "validate_paths",
    "write_document",
]
