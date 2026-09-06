"""Encounter tables: two-stage resolution, gating, and anti-clumping.

The properties that matter are the ones that let an author tune a road with
one number. `chance` has to stay the honest danger dial however many `when`
conditions the entries carry; the anti-clumping has to stop streaks without
quietly making the road more dangerous than it says it is; and a `once` entry
has to mean once.
"""

from pathlib import Path
from typing import Any

from conftest import game_pack
from mace.content import load_library
from mace.engine.actions import Choose, Wait
from mace.engine.encounter import roll
from mace.engine.step import begin, step

REPO_ROOT = Path(__file__).resolve().parent.parent


def table_pack(
    root: Path,
    *,
    table: dict[str, Any] | None = None,
    on_route: bool = True,
    region_table: dict[str, Any] | None = None,
    safe: bool = False,
) -> Any:
    """A pack with an encounter table attached to a road or a place.

    Parameters
    ----------
    root : Path
        Where to write it.
    table : dict or None
        Fields to replace on the table.
    on_route : bool
        Whether to attach it to the road rather than to the starting location.
    region_table : dict or None
        A second table, attached to the region.
    safe : bool
        Whether the starting location is safe.

    Returns
    -------
    Library
        The loaded library.
    """
    definition: dict[str, Any] = {
        "id": "road-table",
        "chance": 1.0,
        "entries": [
            {"id": "quiet", "weight": 1, "scene": "quiet"},
        ],
    }
    definition.update(table or {})

    tables = [definition]
    if region_table is not None:
        tables.append(region_table)

    home: dict[str, Any] = {
        "id": "home",
        "name": "Home",
        "region": "valley",
        "safe": safe,
        "exits": [{"to": "castle", "route": "road"}],
    }
    if not on_route:
        home["encounters"] = "road-table"

    road: dict[str, Any] = {
        "id": "road",
        "from": "home",
        "to": "castle",
        "ticks": 4,
    }
    if on_route:
        road["encounters"] = "road-table"

    game_pack(
        root,
        game={
            "world": {"startRegion": "valley", "startTick": 20},
            "winConditions": [{"flag": {"entity": "hero", "flag": "done"}}],
        },
        world={
            "climates": [
                {
                    "id": "still",
                    "seasons": {"spring": {"weights": {"clear": 1}}},
                    "transitions": {"clear": {"clear": 1}},
                }
            ],
            "weatherConditions": [{"id": "clear", "name": "clear"}],
            "regions": [
                {
                    "id": "valley",
                    "climate": "still",
                    **(
                        {"encounters": region_table["id"]}
                        if region_table is not None
                        else {}
                    ),
                }
            ],
            "encounterTables": tables,
            "routes": [road],
            "locations": [
                home,
                {"id": "castle", "name": "The Castle", "region": "valley"},
            ],
            "scenes": [
                {"id": "quiet", "visible": False, "say": ["Nothing much."]},
                {"id": "wolves", "visible": False, "say": ["Wolves."]},
                {
                    "id": "regional",
                    "visible": False,
                    "say": ["You hear wolves, far off."],
                },
                {
                    "id": "asks",
                    "visible": False,
                    "say": ["Someone blocks the way."],
                    "choices": [{"prompt": "Push past", "goto": "quiet"}],
                },
            ],
        },
    )
    return load_library(root)


def fired(result: Any) -> list[str]:
    """The entry ids that fired in one step.

    Parameters
    ----------
    result : StepResult
        A step.

    Returns
    -------
    list of str
        Entry ids, in order.
    """
    return [
        event.payload()["entry"] for event in result.events if event.kind == "encounter"
    ]


# ── Stage one: does anything happen ──────────────────────────────────────────


def test_a_table_rolls_once_per_leg(tmp_path: Path) -> None:
    library = table_pack(tmp_path)
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert fired(result) == ["quiet"] * 4


def test_a_chance_of_zero_never_fires(tmp_path: Path) -> None:
    library = table_pack(tmp_path, table={"id": "road-table", "chance": 0.0})
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert fired(result) == []


def test_a_safe_place_suppresses_its_own_table(tmp_path: Path) -> None:
    library = table_pack(tmp_path, on_route=False, safe=True)
    result = step(begin(library, "tiny").state, Wait(3), library)
    assert fired(result) == []


def test_a_place_rolls_while_the_player_lingers(tmp_path: Path) -> None:
    """A dungeon corridor waited in is as good a place to be found as a road."""
    library = table_pack(tmp_path, on_route=False)
    result = step(begin(library, "tiny").state, Wait(3), library)
    assert fired(result) == ["quiet"] * 3


def test_the_region_rolls_alongside_the_road(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        region_table={
            "id": "region-table",
            "chance": 1.0,
            "entries": [{"id": "far-off", "weight": 1, "scene": "regional"}],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    # Region first, so the road's own entries get the last word.
    assert fired(result)[:2] == ["far-off", "quiet"]


# ── Stage two: what happens ──────────────────────────────────────────────────


def test_weights_are_normalised_among_the_eligible_set(tmp_path: Path) -> None:
    """An entry that is not eligible does not make the road quieter."""
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [
                {
                    "id": "daytime",
                    "weight": 90,
                    "when": [{"dayPart": ["day"]}],
                    "scene": "quiet",
                },
                {
                    "id": "nighttime",
                    "weight": 10,
                    "when": [{"dayPart": ["night"]}],
                    "scene": "wolves",
                },
            ],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    # Mid-morning, so only the daytime entry is eligible — and it fires every
    # leg, rather than a tenth of the road going quiet.
    assert fired(result) == ["daytime"] * 4


def test_an_entry_can_only_fire_once(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [
                {"id": "riders", "weight": 100, "once": True, "scene": "quiet"},
                {"id": "quiet", "weight": 1, "scene": "quiet"},
            ],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert fired(result).count("riders") == 1


def test_a_cooldown_keeps_an_entry_off_the_table(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [
                {
                    "id": "wolves",
                    "weight": 100,
                    "cooldownTicks": 3,
                    "scene": "wolves",
                },
                {"id": "quiet", "weight": 1, "scene": "quiet"},
            ],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert fired(result)[:2] == ["wolves", "quiet"]


def test_max_per_game_caps_an_entry(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [
                {"id": "wolves", "weight": 100, "maxPerGame": 2, "scene": "wolves"},
                {"id": "quiet", "weight": 1, "scene": "quiet"},
            ],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert fired(result).count("wolves") == 2


# ── Anti-clumping ────────────────────────────────────────────────────────────


def test_min_gap_ticks_stops_two_in_a_row(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "minGapTicks": 3,
            "entries": [{"id": "quiet", "weight": 1, "scene": "quiet"}],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    # Four legs at a certainty, but a three-tick floor between them: the first
    # leg and the fourth, not all four.
    assert fired(result) == ["quiet", "quiet"]


def test_pity_pressure_leaves_the_long_run_rate_alone(tmp_path: Path) -> None:
    """The whole point: tighter variance, same danger.

    A pity counter that only ever rises makes a road quietly more dangerous
    than its author wrote. This one is paid back on a hit in proportion, so
    the mean stays where it was put.
    """
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 0.25,
            "pressureStep": 0.05,
            "entries": [{"id": "quiet", "weight": 1, "scene": "quiet"}],
        },
    )
    state = begin(library, "tiny", seed="rate").state
    table = library.pack("tiny").encounter_tables["road-table"]
    from mace.engine.step import _context  # noqa: PLC0415

    context = _context(library, state, library.pack("tiny").game)  # type: ignore[arg-type]

    hits = 0
    rolls = 4000
    for tick in range(rolls):
        state.tick = tick
        if roll(context, "tiny:road-table", table) is not None:
            hits += 1
    assert 0.22 < hits / rolls < 0.28


# ── Interruption ─────────────────────────────────────────────────────────────


def test_an_encounter_that_asks_a_question_stops_the_journey(
    tmp_path: Path,
) -> None:
    library = table_pack(
        tmp_path,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [{"id": "blocked", "weight": 1, "scene": "asks"}],
        },
    )
    result = step(begin(library, "tiny").state, Choose(0), library)
    assert "travel.interrupted" in [event.kind for event in result.events]
    assert result.state.journey is not None
    assert result.state.location == "tiny:home"


def test_an_encounter_cuts_a_wait_short(tmp_path: Path) -> None:
    library = table_pack(
        tmp_path,
        on_route=False,
        table={
            "id": "road-table",
            "chance": 1.0,
            "entries": [{"id": "blocked", "weight": 1, "scene": "asks"}],
        },
    )
    state = begin(library, "tiny").state
    at = state.tick
    result = step(state, Wait(6), library)
    assert result.state.tick == at + 1


# ── The shipped game ─────────────────────────────────────────────────────────


def test_the_north_road_inherits_the_quiet_road_and_makes_it_worse() -> None:
    library = load_library(REPO_ROOT / "packs")
    table = library.pack("peasants-quest").encounter_tables["forest-road"]
    ids = [entry.id for entry in table.entries]

    assert table.chance == 0.30
    assert "nothing-much" in ids  # inherited atmosphere
    assert "wolves-in-the-wood" in ids  # the road's own danger


def test_most_of_the_north_roads_weight_is_not_a_threat() -> None:
    """A road where a third of legs produce a fight reads as a grind."""
    library = load_library(REPO_ROOT / "packs")
    table = library.pack("peasants-quest").encounter_tables["forest-road"]
    threats = {"wolves-in-the-wood"}
    dangerous = sum(e.weight for e in table.entries if e.id in threats)
    total = sum(e.weight for e in table.entries)
    assert dangerous / total < 0.25
