"""Weather that bites: blanket modifiers, entity responses, exposure and rest.

Weather that only reads nicely is scenery. What has to be true for it to be a
decision the player makes: standing out in it costs something, endurance and a
roof hold it off, resting clears it and costs hours, and an entity's own `env`
responses key off tags so a condition invented later still works.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Choose, Wait
from mace.engine.environment import ENVIRONMENT, EXPOSURE_THRESHOLD
from mace.engine.stats import effective
from mace.engine.step import StepResult, begin, step

REPO_ROOT = Path(__file__).resolve().parent.parent

CONDITIONS: list[dict[str, Any]] = [
    {"id": "clear", "name": "clear"},
    {
        "id": "blizzard",
        "name": "blizzard",
        "intensityRange": [1.0, 1.0],
        "tags": ["cold", "wet", "severe"],
        "modify": [{"stat": "speed", "add": -10}],
    },
    {
        "id": "gloom",
        "name": "gloom",
        "intensityRange": [0.5, 0.5],
        "tags": ["dark"],
        "modify": [{"stat": "speed", "add": -10}],
    },
]


def weather_pack(
    root: Path,
    *,
    condition: str = "blizzard",
    indoors: bool = False,
    endurance: int = 30,
    survival: list[str] | None = None,
    env: list[dict[str, Any]] | None = None,
) -> Any:
    """A pack whose starting location has one condition pinned over it.

    Parameters
    ----------
    root : Path
        Where to write it.
    condition : str
        The weather condition pinned over home.
    indoors : bool
        Whether home is under a roof.
    endurance : int
        The protagonist's endurance.
    survival : list or None
        `game.rules.survival`.
    env : list or None
        `env` responses for the bystander.

    Returns
    -------
    Library
        The loaded library.
    """
    rules: dict[str, Any] = {}
    if survival is not None:
        rules["survival"] = survival

    game_pack(
        root,
        game={
            "world": {"startRegion": "valley", "startTick": 20},
            "winConditions": [{"flag": {"entity": "hero", "flag": "done"}}],
            **({"rules": rules} if rules else {}),
        },
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {
                        "hitpoints": {"base": 40, "max": 40},
                        "stamina": {"base": 10, "max": 20},
                        "speed": {"base": 40},
                        "endurance": {"base": endurance},
                    },
                },
                {
                    "id": "gold",
                    "kind": "item",
                    "name": "Gold",
                    "item": {"baseValue": 1},
                },
                {
                    "id": "orc",
                    "kind": "actor",
                    "name": "Orc",
                    "stats": {"strength": {"base": 40}, "speed": {"base": 40}},
                    **({"env": env} if env else {}),
                },
            ],
            "weatherConditions": CONDITIONS,
            "climates": [
                {
                    "id": "still",
                    "seasons": {"spring": {"weights": {"clear": 1}}},
                    "transitions": {"clear": {"clear": 1}},
                }
            ],
            "regions": [{"id": "valley", "climate": "still"}],
            "routes": [{"id": "road", "from": "home", "to": "castle", "ticks": 2}],
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    "region": "valley",
                    "indoors": indoors,
                    "climate": {"condition": condition},
                    "entities": ["orc"],
                    "scenes": ["shelter"],
                    "exits": [{"to": "castle", "route": "road"}],
                },
                {"id": "castle", "name": "The Castle", "region": "valley"},
            ],
            "scenes": [
                {
                    "id": "shelter",
                    "prompt": "Sleep it off",
                    "say": ["You get what sleep you can."],
                    "effects": [{"rest": {"ticks": 8}}],
                }
            ],
        },
    )
    return load_library(root)


def status(result: StepResult) -> dict[str, Any]:
    """The last status projection of a step.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    dict
        Its payload.
    """
    return [e.payload() for e in result.events if e.kind == "world.status"][-1]


# ── Blanket effects ──────────────────────────────────────────────────────────


def test_the_weather_reaches_everyone_standing_out_in_it(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    state = begin(library, "tiny").state
    orc = state.entities["tiny:orc"]

    assert effective(library.pack("tiny").entities["orc"], orc, "speed") == 30.0
    assert [m.source for m in orc.modifiers] == [ENVIRONMENT]


def test_intensity_scales_what_the_weather_does(tmp_path: Path) -> None:
    """Half-strength gloom takes half of what a full-strength blizzard would."""
    library = weather_pack(tmp_path, condition="gloom")
    state = begin(library, "tiny").state
    orc = state.entities["tiny:orc"]
    assert effective(library.pack("tiny").entities["orc"], orc, "speed") == 35.0


def test_a_roof_suppresses_it(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, indoors=True)
    state = begin(library, "tiny").state
    orc = state.entities["tiny:orc"]
    assert effective(library.pack("tiny").entities["orc"], orc, "speed") == 40.0


def test_environment_modifiers_are_rebuilt_not_stacked(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    for _turn in range(5):
        result = step(result.state, Wait(1), library)
    orc = result.state.entities["tiny:orc"]
    assert len([m for m in orc.modifiers if m.source == ENVIRONMENT]) == 1


# ── Entity responses ─────────────────────────────────────────────────────────


def test_an_entity_answers_the_weather_by_tag(tmp_path: Path) -> None:
    """Tags, not named conditions: a snow type invented later still works."""
    library = weather_pack(
        tmp_path,
        condition="blizzard",
        env=[
            {
                "when": {"weatherTag": ["cold"]},
                "modify": [{"stat": "strength", "add": 15}],
            }
        ],
    )
    state = begin(library, "tiny").state
    orc = state.entities["tiny:orc"]
    assert effective(library.pack("tiny").entities["orc"], orc, "strength") == 55.0


def test_a_response_that_does_not_apply_does_nothing(tmp_path: Path) -> None:
    library = weather_pack(
        tmp_path,
        condition="clear",
        env=[
            {
                "when": {"weatherTag": ["cold"]},
                "modify": [{"stat": "strength", "add": 15}],
            }
        ],
    )
    state = begin(library, "tiny").state
    orc = state.entities["tiny:orc"]
    assert effective(library.pack("tiny").entities["orc"], orc, "strength") == 40.0


# ── Exposure ─────────────────────────────────────────────────────────────────


def test_standing_in_a_blizzard_costs_you(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    assert result.state.protagonist.exposure == 0.0

    result = step(result.state, Wait(4), library)
    assert result.state.protagonist.exposure > 0.0
    assert status(result)["exposure"] > 0.0


def test_past_the_threshold_it_starts_killing_you(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    for _turn in range(12):
        result = step(result.state, Wait(2), library)

    player = result.state.protagonist
    assert player.exposure > EXPOSURE_THRESHOLD
    assert player.pools["hitpoints"] < 40


def test_endurance_holds_it_off(tmp_path: Path) -> None:
    soft = weather_pack(tmp_path / "soft", endurance=0)
    hardy = weather_pack(tmp_path / "hardy", endurance=100)

    soft_state = step(begin(soft, "tiny").state, Wait(6), soft).state
    hardy_state = step(begin(hardy, "tiny").state, Wait(6), hardy).state
    assert hardy_state.protagonist.exposure < soft_state.protagonist.exposure


def test_a_roof_sheds_it(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, indoors=True)
    result = step(begin(library, "tiny").state, Wait(6), library)
    assert result.state.protagonist.exposure == 0.0


def test_exposure_can_be_turned_off(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, survival=[])
    result = step(begin(library, "tiny").state, Wait(8), library)
    assert result.state.protagonist.exposure == 0.0


# ── Rest ─────────────────────────────────────────────────────────────────────


def test_rest_costs_hours_and_gives_them_back_as_pools(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, condition="clear")
    result = begin(library, "tiny")
    at = result.state.tick
    assert result.state.protagonist.pools["stamina"] == 10.0

    sleep = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Sleep it off"
    ][0]
    result = step(result.state, Choose(sleep), library)

    assert result.state.tick == at + 8
    assert result.state.protagonist.pools["stamina"] == 20.0


def test_resting_out_in_it_does_not_help_much(tmp_path: Path) -> None:
    """The hours you sleep through are hours you spend in the blizzard."""
    library = weather_pack(tmp_path)
    result = begin(library, "tiny")
    sleep = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Sleep it off"
    ][0]
    result = step(result.state, Choose(sleep), library)
    assert result.state.protagonist.exposure > 0.0


def test_resting_under_a_roof_clears_it(tmp_path: Path) -> None:
    library = weather_pack(tmp_path, indoors=True)
    result = begin(library, "tiny")
    result.state.protagonist.exposure = 0.9

    sleep = [
        index
        for event in result.events
        if event.kind == "choices"
        for index, option in enumerate(event.payload()["options"])
        if option["prompt"] == "Sleep it off"
    ][0]
    result = step(result.state, Choose(sleep), library)
    assert result.state.protagonist.exposure == 0.0


# ── Expressions ──────────────────────────────────────────────────────────────


def test_content_can_read_how_cold_the_player_is(tmp_path: Path) -> None:
    library = weather_pack(tmp_path)
    result = step(begin(library, "tiny").state, Wait(6), library)
    from mace.engine.step import _context  # noqa: PLC0415

    context = _context(library, result.state, library.pack("tiny").game)
    assert context.expression_context()["player"]["exposure"] > 0.0


# ── The shipped packs ────────────────────────────────────────────────────────


def test_the_troll_is_stronger_in_the_wet() -> None:
    library = load_library(REPO_ROOT / "packs")
    troll = library.pack("fantasy.core").entities["bridge-troll"]
    assert any("wet" in _tags(response) for response in troll.env)


def _tags(response: Any) -> list[str]:
    """The weather tags one `env` response matches on.

    Parameters
    ----------
    response : EnvResponse
        The response.

    Returns
    -------
    list of str
        Its tags, flattened.
    """
    found: list[str] = []
    for condition in response.when:
        payload = condition.payload
        found.extend(getattr(payload, "tags", ()))
    return found
