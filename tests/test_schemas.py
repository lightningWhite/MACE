"""The checked-in JSON Schemas must match the models and accept real content.

`schemas/` is what CI runs against `packs/` and what an author's editor reads.
Two ways it can rot: the models change and the schemas don't, or the schemas
drift into describing content nobody writes. Both are checked here.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from jsonschema import Draft202012Validator

from mace.model.base import ContentModel
from mace.model.jsonschema import (
    CONTENT_COLLECTIONS,
    SCHEMA_FILES,
    UNMODELLED_COLLECTIONS,
    content_schema,
    pack_schema,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_ROOT = REPO_ROOT / "schemas"
EXAMPLE_PACK = REPO_ROOT / "docs" / "examples" / "peasants-quest"


@pytest.mark.parametrize("filename", sorted(SCHEMA_FILES))
def test_checked_in_schema_matches_the_models(filename: str) -> None:
    """Regenerating must be a no-op, or `schemas/` is lying about the models."""
    on_disk = json.loads((SCHEMA_ROOT / filename).read_text())
    assert on_disk == SCHEMA_FILES[filename](), (
        f"{filename} is out of date — "
        "regenerate it with `python -m mace.model.jsonschema`"
    )


@pytest.mark.parametrize("filename", sorted(SCHEMA_FILES))
def test_schema_is_valid_json_schema(filename: str) -> None:
    Draft202012Validator.check_schema(json.loads((SCHEMA_ROOT / filename).read_text()))


def example_files() -> list[Path]:
    """Every YAML file in the worked example.

    Returns
    -------
    list of Path
        Sorted paths, so the parametrization is stable.
    """
    return sorted(EXAMPLE_PACK.glob("*.yml"))


@pytest.mark.parametrize("path", example_files(), ids=lambda p: p.name)
def test_the_worked_example_validates(path: Path) -> None:
    """The example is the specification by example; the schemas must accept it.

    Unlike the model tests, nothing is stripped first: this is the authoring
    shape, `extends` and `$append` and all.
    """
    schema = pack_schema() if path.name == "pack.yml" else content_schema()
    document: Any = yaml.safe_load(path.read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document), key=lambda e: e.path
    )
    assert not errors, "\n".join(
        f"{'/'.join(str(part) for part in error.path)}: {error.message}"
        for error in errors[:5]
    )


def test_a_child_may_inherit_the_fields_it_leaves_out() -> None:
    validator = Draft202012Validator(content_schema())
    inheriting = {"entities": [{"id": "gorm", "extends": "fantasy.core:troll"}]}
    assert not list(validator.iter_errors(inheriting))

    standalone = {"entities": [{"id": "gorm"}]}
    assert list(validator.iter_errors(standalone)), "a name is required without extends"


def test_merge_sentinels_are_allowed_where_inheritance_puts_them() -> None:
    validator = Draft202012Validator(content_schema())
    document = {
        "entities": [
            {
                "id": "gorm",
                "extends": "fantasy.core:troll",
                "tags": ["$append", "named"],
                "$remove": ["combat"],
            }
        ]
    }
    assert not list(validator.iter_errors(document))


def test_a_misspelled_collection_is_caught() -> None:
    validator = Draft202012Validator(content_schema())
    assert list(validator.iter_errors({"entites": []}))


def test_every_collection_the_docs_describe_is_accounted_for() -> None:
    """Modelled or not, a documented collection must be a known key."""
    known = set(CONTENT_COLLECTIONS) | set(UNMODELLED_COLLECTIONS) | {"game"}
    used_by_the_example = {
        key
        for path in example_files()
        if path.name != "pack.yml"
        for key in yaml.safe_load(path.read_text())
    }
    assert used_by_the_example <= known, sorted(used_by_the_example - known)


def test_two_models_may_not_share_a_name() -> None:
    """`$defs` is keyed by class name, so a collision would drop one schema.

    It happened once: the `move` *effect* payload and the combat `Move` content
    type were both called `Move`, and the effect's definition quietly vanished
    from the generated schema — which showed up as an authored `{move: ...}`
    effect failing to validate, three files away from the cause. Generating
    the schemas at all now proves there is no collision; this checks that the
    refusal is real rather than assumed.
    """
    with pytest.raises(ValueError, match="two models are called `Effect`"):
        with patch.dict(CONTENT_COLLECTIONS, {"impostors": _Impostor}):
            content_schema()


class _Impostor(ContentModel):
    """A model that claims a name another model already has."""

    id: str


_Impostor.__name__ = "Effect"
