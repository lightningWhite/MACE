"""The documented example pack must validate against the content models.

`docs/examples/peasants-quest/` is the worked example the design docs point
authors at. If it stops validating, either the models drifted from the docs or
the docs promised something the models don't deliver — and both are bugs.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from mace.model import Background, Entity, Game, Location, Pack, Quest, Route, Scene

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent / "docs" / "examples"
PACK_ROOT = EXAMPLE_ROOT / "peasants-quest"

#: File, the key its objects live under (None for the whole document), and the
#: model each object must validate against.
SECTIONS: list[tuple[str, str | None, type[BaseModel]]] = [
    ("pack.yml", None, Pack),
    ("game.yml", "game", Game),
    ("backgrounds.yml", "backgrounds", Background),
    ("entities.yml", "entities", Entity),
    ("locations.yml", "locations", Location),
    ("routes.yml", "routes", Route),
    ("scenes.yml", "scenes", Scene),
    ("quests.yml", "quests", Quest),
]


def resolve_merge_sentinels(value: Any) -> Any:
    """Stand in for the loader's `extends` merge.

    Inheritance is resolved on raw mappings before models are built, so a
    sentinel such as `$append` never reaches validation. Until the loader
    exists, drop them here rather than teaching the models about a syntax they
    should never see.

    Parameters
    ----------
    value : object
        Raw YAML data.

    Returns
    -------
    object
        The same data with merge sentinels removed.
    """
    if isinstance(value, dict):
        return {key: resolve_merge_sentinels(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_merge_sentinels(item) for item in value if item != "$append"]
    return value


def objects(filename: str, key: str | None) -> list[Any]:
    """Read one example file and return the objects it defines.

    Parameters
    ----------
    filename : str
        A file inside the example pack.
    key : str or None
        The top-level key the objects live under, or None for the document.

    Returns
    -------
    list
        The raw objects, with merge sentinels resolved.
    """
    document = resolve_merge_sentinels(
        yaml.safe_load((PACK_ROOT / filename).read_text())
    )
    body = document if key is None else document[key]
    return body if isinstance(body, list) else [body]


def cases() -> list[tuple[type[BaseModel], Any, str]]:
    """Build one parametrized case per object in the example pack.

    Returns
    -------
    list of (type, object, str)
        The model, the raw object, and a readable test id.
    """
    built = []
    for filename, key, model in SECTIONS:
        for index, raw in enumerate(objects(filename, key)):
            name = raw.get("id") or raw.get("name") or index
            built.append((model, raw, f"{filename}:{name}"))
    return built


PARAMS = cases()


@pytest.mark.parametrize(
    ("model", "raw"),
    [(model, raw) for model, raw, _ in PARAMS],
    ids=[test_id for _, _, test_id in PARAMS],
)
def test_example_object_validates(model: type[BaseModel], raw: Any) -> None:
    model.model_validate(raw)


@pytest.mark.parametrize(
    ("model", "raw"),
    [(model, raw) for model, raw, _ in PARAMS],
    ids=[test_id for _, _, test_id in PARAMS],
)
def test_example_object_round_trips(model: type[BaseModel], raw: Any) -> None:
    """Authoring shape in, authoring shape out, same model both times."""
    parsed = model.model_validate(raw)
    assert model.model_validate(parsed.authored()) == parsed  # type: ignore[attr-defined]


def test_the_example_pack_was_actually_found() -> None:
    """Guard against the parametrization silently covering nothing."""
    assert len(PARAMS) > 30, f"only {len(PARAMS)} example objects found"
