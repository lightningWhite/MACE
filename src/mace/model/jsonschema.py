"""JSON Schemas for the files an author actually writes.

`schemas/` is what CI runs against `packs/` and what an editor reads to offer
completion over the condition and effect vocabulary, so it describes content
**before** the loader has touched it — with `extends` still present, inherited
fields still absent, and the `$append` / `$remove` merge sentinels still in the
lists and mappings they will act on.

That is deliberately looser than the pydantic models, which describe compiled
content (see docs/03-content-model.md § Inheritance). The models are the
enforcement mechanism after loading; these schemas are the fast first line of
defence before it, and the one authors' tools can read.

Three things pydantic cannot derive on its own are patched in here:

- **Conditions and effects** are written as one-key mappings, `{hasItem: {...}}`,
  but modelled internally as a tag and a payload. Each becomes a `oneOf` over
  the vocabulary, so an editor can complete tag names and their arguments.
- **Shorthand forms** — `{chance: 0.15}`, a description line that is just its
  text — come from each model's `shorthand_field`.
- **Collections** name which top-level key in a content file holds what.

Regenerate the checked-in files with `python -m mace.model.jsonschema`; a test
fails if they drift from the models.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic.json_schema import models_json_schema

from mace.model.base import ContentModel
from mace.model.calendar import Calendar
from mace.model.conditions import CONDITION_PAYLOADS, Condition
from mace.model.effects import EFFECT_PAYLOADS, Effect
from mace.model.entity import Entity
from mace.model.game import Game
from mace.model.location import Location
from mace.model.pack import Pack
from mace.model.quest import Quest
from mace.model.route import Route
from mace.model.scene import Scene
from mace.model.text import DescriptionLine, SayLine

__all__ = [
    "CONTENT_COLLECTIONS",
    "SCHEMA_FILES",
    "UNMODELLED_COLLECTIONS",
    "content_schema",
    "pack_schema",
    "write",
]

BASE_URI = "https://raw.githubusercontent.com/lightningWhite/MACE/main/schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: The top-level key each modelled content type lives under in a pack file.
CONTENT_COLLECTIONS: dict[str, type[ContentModel]] = {
    "calendars": Calendar,
    "entities": Entity,
    "locations": Location,
    "routes": Route,
    "scenes": Scene,
    "quests": Quest,
}

#: Collections the docs describe but no model covers yet. Listing them keeps a
#: misspelled collection key an error while leaving room for the phase that
#: models them — see docs/12-roadmap.md.
UNMODELLED_COLLECTIONS: dict[str, str] = {
    "regions": "phase 2 — world simulation",
    "climates": "phase 2 — world simulation",
    "weatherConditions": "phase 2 — world simulation",
    "terrains": "phase 2 — travel",
    "celestialEvents": "phase 2 — world events",
    "pressureEvents": "phase 2 — world events",
    "encounterTables": "phase 2 — encounters",
    "combatProfiles": "phase 3 — combat",
    "moves": "phase 3 — combat",
    "backgrounds": "phase 4 — character creation",
    "goods": "phase 5 — economy",
    "markets": "phase 5 — economy",
}

#: Merge sentinels the loader resolves. They are legal in an authored file and
#: impossible in a compiled one.
APPEND_SENTINEL = "$append"
REMOVE_SENTINEL = "$remove"

_SHORTHAND_DESCRIPTION = (
    "May be written as the bare value shown, which is the same as the mapping "
    "form with every other field left out."
)


def _models() -> list[type[ContentModel]]:
    """Every model that needs a definition in the generated schemas.

    Payload models are included explicitly: nothing references them by type, so
    pydantic would not otherwise emit them.

    Returns
    -------
    list of type
        The models to generate definitions for.
    """
    models: list[type[ContentModel]] = [
        Pack,
        Game,
        Condition,
        Effect,
        DescriptionLine,
        SayLine,
        *CONTENT_COLLECTIONS.values(),
        *CONDITION_PAYLOADS.values(),
        *EFFECT_PAYLOADS.values(),
    ]
    seen: dict[str, type[ContentModel]] = {}
    for model in models:
        seen.setdefault(model.__name__, model)
    return list(seen.values())


def _tagged_union(
    payloads: Mapping[Any, type[ContentModel]], kind: str
) -> dict[str, Any]:
    """Describe a one-key tagged mapping such as `{hasItem: {...}}`.

    Parameters
    ----------
    payloads : dict
        Tag to payload model, in the order they should be offered.
    kind : str
        `condition` or `effect`, for the description.

    Returns
    -------
    dict
        A `oneOf` over the vocabulary.
    """
    return {
        "description": f"One {kind}, written as a single-key mapping.",
        "oneOf": [
            {
                "type": "object",
                "properties": {tag: {"$ref": f"#/$defs/{model.__name__}"}},
                "required": [tag],
                "additionalProperties": False,
            }
            for tag, model in payloads.items()
        ],
    }


def _apply_shorthands(defs: dict[str, Any]) -> None:
    """Rewrite every model that accepts a bare value in place of its mapping.

    A model whose only field is the shorthand field is *always* written bare —
    nobody writes `{chance: {probability: 0.15}}` — so its definition becomes
    the bare form outright. A model with other fields, such as a description
    line that may carry a `when`, keeps both forms.

    Parameters
    ----------
    defs : dict
        The generated definitions, modified in place.
    """
    for model in _models():
        field_name = model.shorthand_field
        if field_name is None or model.__name__ not in defs:
            continue
        definition = defs[model.__name__]
        alias = model.model_fields[field_name].alias or field_name
        bare = dict(definition["properties"][alias])
        bare.pop("title", None)
        bare["description"] = definition.get("description", _SHORTHAND_DESCRIPTION)

        if len(model.model_fields) == 1:
            defs[model.__name__] = bare
        else:
            defs[model.__name__] = {
                "description": definition.get("description", ""),
                "oneOf": [bare, {**definition, "description": _SHORTHAND_DESCRIPTION}],
            }


def _definitions() -> dict[str, Any]:
    """Generate the shared `$defs` block.

    Returns
    -------
    dict
        Definitions for every content type, with the authored shapes patched in.
    """
    _, generated = models_json_schema(
        [(model, "validation") for model in _models()],
        ref_template="#/$defs/{model}",
    )
    defs: dict[str, Any] = generated["$defs"]

    defs["Condition"] = _tagged_union(CONDITION_PAYLOADS, "condition")
    defs["Effect"] = _tagged_union(EFFECT_PAYLOADS, "effect")
    _apply_shorthands(defs)

    # The payload base classes carry no fields and are never written.
    defs.pop("ConditionPayload", None)
    defs.pop("EffectPayload", None)
    return defs


def _allow_merge_sentinels(definition: dict[str, Any]) -> None:
    """Let `$append` and `$remove` appear on a definition that can be extended.

    Merging happens before validation, so an authored object may append to a
    list it inherits or drop a key it does not want. A compiled object never
    can, which is why this relaxation belongs to the authoring schema alone.

    The sentinels are allowed on the extendable object's own properties, which
    is where authors put them. A sentinel nested deeper than that is resolved
    by the loader but not described here — the loader is the authority on the
    merge, and these schemas are the fast check that runs before it.

    Parameters
    ----------
    definition : dict
        An `Entity` or `Location` definition, modified in place.
    """
    for property_schema in definition.get("properties", {}).values():
        if property_schema.get("type") == "array" and "items" in property_schema:
            property_schema["items"] = {
                "anyOf": [property_schema["items"], {"const": APPEND_SENTINEL}]
            }

    definition.setdefault("properties", {})[REMOVE_SENTINEL] = {
        "type": "array",
        "items": {"type": "string"},
        "description": "Keys to drop from the inherited definition.",
    }


def _allow_inherited_fields(defs: dict[str, Any]) -> None:
    """Stop requiring what a child object inherits from its parent.

    A definition with `extends` may leave out anything but its own `id`; one
    without it must be complete. Expressed as a conditional so the schema still
    catches a genuinely incomplete object.

    Parameters
    ----------
    defs : dict
        The generated definitions, modified in place.
    """
    for name, definition in defs.items():
        if "extends" not in definition.get("properties", {}):
            continue
        required = definition.get("required", [])
        inheritable = [field for field in required if field != "id"]
        if not inheritable:
            continue
        definition["required"] = [field for field in required if field == "id"]
        definition["if"] = {"not": {"required": ["extends"]}}
        definition["then"] = {"required": inheritable}
        definition["description"] = (
            f"{definition.get('description', name)}\n\n"
            f"Extending another definition makes {', '.join(inheritable)} "
            "optional here — the parent supplies them."
        )


def _authoring_definitions() -> dict[str, Any]:
    """Generate `$defs` as an authored file may write them.

    Returns
    -------
    dict
        Definitions relaxed for inheritance and merge sentinels.
    """
    defs = copy.deepcopy(_definitions())
    _allow_inherited_fields(defs)
    for definition in defs.values():
        if "extends" in definition.get("properties", {}):
            _allow_merge_sentinels(definition)
    return defs


def _prune(document: dict[str, Any]) -> dict[str, Any]:
    """Drop definitions nothing in the document refers to.

    Pydantic emits a definition for every model it walks, including a few
    reached only through an annotation whose schema is supplied by hand. An
    unreferenced definition is dead weight in a file an editor loads on every
    keystroke.

    Parameters
    ----------
    document : dict
        A finished schema document with a `$defs` block.

    Returns
    -------
    dict
        The same document, with unreachable definitions removed.
    """
    defs = document["$defs"]
    reachable: set[str] = set()
    frontier = [{key: value for key, value in document.items() if key != "$defs"}]
    while frontier:
        node = frontier.pop()
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/$defs/"):
                name = reference.removeprefix("#/$defs/")
                if name not in reachable and name in defs:
                    reachable.add(name)
                    frontier.append(defs[name])
            frontier.extend(node.values())
        elif isinstance(node, list):
            frontier.extend(node)

    document["$defs"] = {
        name: definition for name, definition in defs.items() if name in reachable
    }
    return document


def content_schema() -> dict[str, Any]:
    """Build the schema for any content file in a pack.

    File organization inside a pack is free, so one schema covers them all: a
    mapping of collection name to the objects it holds, in any combination.

    Returns
    -------
    dict
        A JSON Schema document.
    """
    properties: dict[str, Any] = {
        collection: {
            "type": "array",
            "items": {"$ref": f"#/$defs/{model.__name__}"},
        }
        for collection, model in CONTENT_COLLECTIONS.items()
    }
    properties["game"] = {"$ref": "#/$defs/Game"}
    for collection, phase in UNMODELLED_COLLECTIONS.items():
        properties[collection] = {
            "type": "array",
            "description": f"Not yet modelled — {phase}.",
        }

    document = {
        "$schema": DIALECT,
        "$id": f"{BASE_URI}/content.schema.json",
        "title": "MACE content file",
        "description": (
            "Any file in a pack other than its manifest. Every key is optional "
            "and a file may mix collections freely; the loader merges by id."
        ),
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "$defs": _authoring_definitions(),
    }
    return _prune(document)


def pack_schema() -> dict[str, Any]:
    """Build the schema for a pack manifest.

    Returns
    -------
    dict
        A JSON Schema document.
    """
    defs = _authoring_definitions()
    manifest = defs.pop("Pack")
    document = {
        "$schema": DIALECT,
        "$id": f"{BASE_URI}/pack.schema.json",
        "title": "MACE pack manifest",
        **{key: value for key, value in manifest.items() if key != "title"},
        "$defs": defs,
    }
    return _prune(document)


#: The files `python -m mace.model.jsonschema` writes.
SCHEMA_FILES: dict[str, Any] = {
    "pack.schema.json": pack_schema,
    "content.schema.json": content_schema,
}


def write(directory: Path) -> list[Path]:
    """Write the generated schemas to disk.

    Parameters
    ----------
    directory : Path
        Where to write them. Created if it does not exist.

    Returns
    -------
    list of Path
        The files written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, build in SCHEMA_FILES.items():
        path = directory / filename
        path.write_text(json.dumps(build(), indent=2) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schemas")
    for written_path in write(target):
        print(written_path)
