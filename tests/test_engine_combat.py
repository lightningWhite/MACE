"""Tempo combat: the arithmetic, the loop, and the claim it all exists for.

The claim is in docs/07-combat.md and it is falsifiable:

> A player who has fought three trolls beats the fourth more reliably than a
> player who hasn't — with an identical character sheet.

Most of what follows is machinery, but `test_reading_an_enemy_wins_fights` is
the acceptance test. If it ever fails, the system has failed and the tuning
constants are the thing to argue about, not the test.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import write_pack
from mace.content import Library, load_library
from mace.engine.actions import Choose, Respond, Travel
from mace.engine.combat import fight as combat
from mace.engine.combat import resolution
from mace.engine.combat import roster
from mace.engine.combat.resolution import Outcome
from mace.engine.combat.roster import UNARMED, UNARMED_RANGE
from mace.engine.conditions import RuleError
from mace.engine.state import GameState
from mace.engine.step import StepResult, begin, context_for, spawn, step

# ── The arithmetic ────────────────────────────────────────────────────────────


def test_speed_widens_the_window_and_nothing_else() -> None:
    """Stats widen the door; the player still has to walk through it."""
    assert resolution.window_ms(1400, 50) == 1400
    assert resolution.window_ms(1400, 70) == 1540
    assert resolution.window_ms(1400, 30) == 1260


def test_speed_widens_the_step_the_same_way_it_widens_the_window() -> None:
    assert resolution.move_step(3.0, 50) == 3.0
    assert resolution.move_step(3.0, 70) == 3.3
    assert resolution.move_step(3.0, 30) == 2.7
    assert resolution.move_step(3.0, -150) == 0.0


def test_the_sweet_spot_sits_late() -> None:
    """The reflex asked for is holding your nerve, not twitching early."""
    window = 1000
    assert resolution.precision_of(750, window) == 1.0
    assert resolution.precision_of(0, window) == 0.0
    assert resolution.precision_of(375, window) < resolution.precision_of(700, window)


def test_a_move_cannot_connect_outside_its_band() -> None:
    assert resolution.range_factor(2.0, 3.0, 5.0, 3.5, 4.5) == 0.0
    assert resolution.range_factor(6.0, 3.0, 5.0, 3.5, 4.5) == 0.0


def test_the_sweet_spot_of_a_range_is_flat() -> None:
    """Inside `[sweetMin, sweetMax]` a move is equally good anywhere in it."""
    assert resolution.range_factor(3.5, 3.0, 5.0, 3.5, 4.5) == 1.0
    assert resolution.range_factor(4.0, 3.0, 5.0, 3.5, 4.5) == 1.0
    assert resolution.range_factor(4.5, 3.0, 5.0, 3.5, 4.5) == 1.0


def test_range_effectiveness_ramps_toward_the_edges() -> None:
    close = resolution.range_factor(3.2, 3.0, 5.0, 3.5, 4.5)
    closer_to_min = resolution.range_factor(3.05, 3.0, 5.0, 3.5, 4.5)
    assert 0.0 < closer_to_min < close < 1.0

    far = resolution.range_factor(4.8, 3.0, 5.0, 3.5, 4.5)
    closer_to_max = resolution.range_factor(4.95, 3.0, 5.0, 3.5, 4.5)
    assert 0.0 < closer_to_max < far < 1.0


def test_no_roll_decides_a_read_or_a_timing() -> None:
    """The guarantee that makes practice worth it, checked as a signature.

    There is nowhere to put a seed, which is the point: a player who reads and
    times perfectly cannot lose to dice.
    """
    for _ in range(2):
        assert resolution.outcome_of(correct=True, precision=1.0) is Outcome.COUNTER
        assert resolution.outcome_of(correct=True, precision=0.0) is Outcome.ABSORBED
        assert resolution.outcome_of(correct=False, precision=1.0) is Outcome.GLANCING
        assert resolution.outcome_of(correct=False, precision=0.0) is Outcome.CLEAN


def test_a_right_read_timed_late_beats_a_wrong_read_timed_well() -> None:
    """The ordering the four outcomes promise, at the worst defense there is."""
    worst_mitigation = 0.5
    absorbed = resolution.damage_taken(
        10.0, Outcome.ABSORBED, precision=0.0, mitigation=worst_mitigation
    )
    glancing = resolution.damage_taken(
        10.0, Outcome.GLANCING, precision=1.0, mitigation=0.0
    )
    assert absorbed < glancing


def test_a_counter_takes_nothing() -> None:
    assert (
        resolution.damage_taken(20.0, Outcome.COUNTER, precision=0.6, mitigation=0.0)
        == 0.0
    )


def test_guessing_costs_more_than_knowing() -> None:
    assert resolution.stamina_cost(8.0, correct=False) > resolution.stamina_cost(
        8.0, correct=True
    )


def test_momentum_builds_on_reads_and_a_clean_hit_takes_it_all() -> None:
    momentum = 0
    for _ in range(5):
        momentum = resolution.momentum_after(momentum, Outcome.COUNTER)
    assert resolution.multiplier(momentum) == max(resolution.MOMENTUM_LADDER)
    assert resolution.momentum_after(momentum, Outcome.CLEAN) == 0


def test_elapsed_times_are_quantized_for_replay() -> None:
    """Two machines that read 812 ms and 814 ms must resolve the same exchange."""
    assert resolution.quantize(812) == resolution.quantize(814)
    assert resolution.quantize(-5) == 0


def test_skill_lifts_a_sloppy_answer_but_never_to_a_clean_one() -> None:
    sloppy = 0.2
    assert resolution.eased(sloppy, 0.0) == sloppy
    assert sloppy < resolution.eased(sloppy, 100.0) < 1.0


# ── Time pressure ─────────────────────────────────────────────────────────────


def test_the_clock_can_be_asked_to_press_less_hard() -> None:
    """docs/10 § Accessibility: reflex mode for people who want it slower."""
    assert resolution.window_ms(1400, 50, 2.0) == 2800
    assert resolution.window_ms(1400, 50, 0.5) == 700


def test_a_wider_window_is_not_an_easier_one_to_aim_at() -> None:
    """The setting is a longer door, not a bigger target.

    Precision is measured against the window the player was actually given,
    so the sweet spot stays three quarters of the way through whatever they
    were given. Otherwise a slower clock would quietly be an easier fight.
    """
    for window in (700, 1400, 2800):
        assert resolution.precision_of(int(window * 0.75), window) == 1.0
        assert resolution.precision_of(int(window * 0.25), window) < 0.05


# ── A fight, end to end ───────────────────────────────────────────────────────


def brawl_pack(root: Path, *, mode: str = "reflex", **overrides: Any) -> Library:
    """A pack with one fighter, one enemy, and one move each way.

    Parameters
    ----------
    root : Path
        Where to write it.
    mode : str
        The game's default combat mode.
    **overrides
        Collections to replace wholesale.

    Returns
    -------
    Library
        The loaded library.
    """
    content: dict[str, Any] = {
        "moves": [
            {"id": "guard", "kind": "defense", "type": "block", "cost": 4},
            {"id": "duck", "kind": "defense", "type": "dodge", "cost": 3},
            {
                "id": "swing",
                "type": "slash",
                "tell": "He swings.",
                "vagueTell": "He moves.",
                "windupMs": 1000,
                "counters": ["block"],
                "damage": {"min": 6, "max": 6},
                "cost": 5,
            },
        ],
        "combatProfiles": [
            {"id": "hero-style", "moves": ["guard", "duck"]},
            {
                "id": "thug-style",
                "moves": ["guard", "swing"],
                "tellClarity": 0.6,
                "patterns": [{"sequence": ["swing"]}],
            },
        ],
        "entities": [
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Club",
                "item": {"equipSlot": "mainHand", "damage": {"min": 4, "max": 4}},
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
        "locations": [
            {
                "id": "yard",
                "name": "The Yard",
                "scenes": ["pick-a-fight"],
                "entities": ["thug"],
                "exits": [],
            }
        ],
        "scenes": [
            {
                "id": "pick-a-fight",
                "prompt": "Start something",
                "effects": [
                    {
                        "startCombat": {
                            "against": "thug",
                            "onWin": "you-won",
                            "onFlee": "you-ran",
                        }
                    }
                ],
            },
            {"id": "you-won", "visible": False, "say": "He stays down."},
            {"id": "you-ran", "visible": False, "say": "You run."},
        ],
    }
    content.update(overrides)
    manifest = {
        "name": "Brawl",
        "player": {"entity": "hero", "startLocation": "yard"},
        "rules": {"combatMode": mode},
        "winConditions": [{"flag": {"entity": "hero", "flag": "done"}}],
    }
    write_pack(
        root,
        "brawl",
        kind="game",
        files={"world.yml": content, "game.yml": {"game": manifest}},
    )
    return load_library(root / "brawl")


def start(library: Library, seed: str = "brawl") -> StepResult:
    """Begin a brawl and pick the fight.

    Parameters
    ----------
    library : Library
        The loaded pack.
    seed : str
        The session seed.

    Returns
    -------
    StepResult
        The step that started the fight.
    """
    result = begin(library, "brawl", seed=seed)
    return step(result.state, Choose(0), library)


def answer(
    state: GameState,
    library: Library,
    response: str,
    *,
    share: float = 0.75,
    move_by: float | None = None,
) -> StepResult:
    """Answer whatever is currently telegraphed.

    Parameters
    ----------
    state : GameState
        The playthrough.
    library : Library
        The loaded pack.
    response : str
        What to answer with.
    share : float
        Where in the window to commit, as a share of it. 0.75 is the sweet
        spot; anything else is deliberately worse.
    move_by : float or None
        Feet to close or open alongside the answer.

    Returns
    -------
    StepResult
        The step.
    """
    tell = state.combat.tell if state.combat else None
    assert tell is not None
    return step(
        state,
        Respond(response, int(tell.window_ms * share), move_by),
        library,
    )


def kinds(result: StepResult) -> list[str]:
    """The kinds of a step's events, in order.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    list of str
        Event kinds.
    """
    return [event.kind for event in result.events]


def resolved(result: StepResult) -> dict[str, Any]:
    """The payload of a step's `combat.resolve` event.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    dict
        The payload.
    """
    return next(e.payload() for e in result.events if e.kind == "combat.resolve")


def began(result: StepResult) -> dict[str, Any]:
    """The payload of a step's `combat.begin` event.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    dict
        The payload.
    """
    return next(e.payload() for e in result.events if e.kind == "combat.begin")


def reads_for(result: StepResult, actor: str) -> list[str]:
    """One combatant's `reads` lines out of a step's `combat.begin` event.

    Parameters
    ----------
    result : StepResult
        The step.
    actor : str
        Qualified instance id.

    Returns
    -------
    list of str
        Its reads, empty if there are none.
    """
    combatant = next(c for c in began(result)["combatants"] if c["actor"] == actor)
    reads: list[str] = combatant["reads"]
    return reads


def test_a_fight_telegraphs_before_it_asks(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    assert "combat.begin" in kinds(result)
    assert kinds(result).index("combat.tell") < kinds(result).index("combat.responses")


def test_the_menu_is_replaced_by_the_fight(tmp_path: Path) -> None:
    """A list of roads to walk down in the middle of a fight would be a lie."""
    library = brawl_pack(tmp_path)
    result = start(library)
    assert "choices" not in kinds(result)
    assert result.state.pending is None


def test_everything_but_looking_waits_until_the_fight_is_over(
    tmp_path: Path,
) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    refused = step(result.state, Choose(0), library)
    assert any(
        e.payload().get("message", "").startswith("you are in the middle")
        for e in refused.events
        if e.kind == "engine.rule-failed"
    )


def test_a_right_read_timed_well_takes_nothing_and_hits_back(
    tmp_path: Path,
) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    result = answer(result.state, library, "block")
    payload = resolved(result)
    assert payload["result"] == "counter"
    assert payload["damageTaken"] == 0.0
    assert payload["damageDealt"] > 0.0


def test_a_wrong_read_timed_well_still_hurts_less_than_a_bad_one(
    tmp_path: Path,
) -> None:
    library = brawl_pack(tmp_path)
    sharp = answer(start(library).state, library, "dodge")
    sloppy = answer(start(library).state, library, "dodge", share=0.05)
    assert resolved(sharp)["result"] == "glancing"
    assert resolved(sloppy)["result"] == "clean"
    assert resolved(sharp)["damageTaken"] < resolved(sloppy)["damageTaken"]


# ── Relative-to-player values ────────────────────────────────────────────────


def test_a_moves_relative_damage_resolves_against_the_players_own_hitpoints(
    tmp_path: Path,
) -> None:
    """A move's `damage` authored `relativeToPlayer` rolls off the player's cap.

    `swing` is authored to deal half the player's own max hitpoints, every
    time, regardless of who is wearing them. Hero opens at 40 hitpoints, so a
    fully unmitigated hit should land for exactly 20 — the `_incoming` path,
    which reads `move.damage`, not `defender.weapon_damage`.
    """
    library = brawl_pack(
        tmp_path,
        moves=[
            {"id": "guard", "kind": "defense", "type": "block", "cost": 4},
            {"id": "duck", "kind": "defense", "type": "dodge", "cost": 3},
            {
                "id": "swing",
                "type": "slash",
                "tell": "He swings.",
                "vagueTell": "He moves.",
                "windupMs": 1000,
                "counters": ["block"],
                "damage": {
                    "min": {"relativeToPlayer": {"stat": "hitpoints", "factor": 0.5}},
                    "max": {"relativeToPlayer": {"stat": "hitpoints", "factor": 0.5}},
                },
                "cost": 5,
            },
        ],
    )
    result = start(library)
    # "dodge" is not in `swing.counters`, and a rushed answer reads as CLEAN —
    # full, unmitigated damage.
    result = answer(result.state, library, "dodge", share=0.05)
    payload = resolved(result)
    assert payload["result"] == "clean"
    assert payload["damageTaken"] == 20.0


def test_a_weapons_relative_damage_resolves_against_the_players_own_hitpoints(
    tmp_path: Path,
) -> None:
    """An item's `damage` authored `relativeToPlayer` reaches the `_opening` path.

    The club is authored to deal a quarter of the player's own max hitpoints
    on a clean counter — a different read site (`defender.weapon_damage`)
    than a move's own damage.
    """
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Club",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {
                        "min": {
                            "relativeToPlayer": {"stat": "hitpoints", "factor": 0.25}
                        },
                        "max": {
                            "relativeToPlayer": {"stat": "hitpoints", "factor": 0.25}
                        },
                    },
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    result = answer(start(library).state, library, "block")
    payload = resolved(result)
    assert payload["result"] == "counter"
    assert payload["damageDealt"] > 0.0


def test_a_stat_base_relative_to_the_player_resolves_once_at_spawn(
    tmp_path: Path,
) -> None:
    """A monster's `hitpoints.base` set to 3x the player's own resolves once.

    A later change to the player's own hitpoints *cap* must not retroactively
    rescale an already-spawned monster — only a freshly spawned one should
    reflect the new number.
    """
    entities = [
        {
            "id": "hero",
            "kind": "actor",
            "name": "Hero",
            "playable": True,
            "stats": {
                "hitpoints": {"base": 40, "max": 40},
                "stamina": {"base": 30, "max": 30},
                "strength": {"base": 50},
                "speed": {"base": 50},
            },
            "combat": {"profile": "hero-style"},
            "equipment": {"mainHand": "club"},
        },
        {
            "id": "thug",
            "kind": "actor",
            "name": "Thug",
            "stats": {
                "hitpoints": {
                    "base": {"relativeToPlayer": {"stat": "hitpoints", "factor": 3}},
                    "max": 200,
                },
                "stamina": {"base": 30, "max": 30},
                "strength": {"base": 50},
                "speed": {"base": 50},
            },
            "combat": {"profile": "thug-style"},
            "inventory": [{"item": "purse", "qty": 3}],
        },
        {
            "id": "club",
            "kind": "item",
            "name": "Club",
            "item": {"equipSlot": "mainHand", "damage": {"min": 4, "max": 4}},
        },
        {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
    ]
    library = brawl_pack(tmp_path, entities=entities)
    opened = begin(library, "brawl", seed="brawl")
    state = opened.state
    context = context_for(library, state)
    location = state.protagonist.location

    first_id = spawn("thug", context, location)
    assert state.entities[first_id].pools["hitpoints"] == 120.0

    # Growing the player's own cap (the `raiseMax` mechanism) must not
    # rescale the monster already spawned against the old cap...
    state.protagonist.stat_caps["hitpoints"] = 360.0
    assert state.entities[first_id].pools["hitpoints"] == 120.0

    # ...but a monster spawned fresh afterward should reflect the new cap.
    second_id = spawn("thug", context, location)
    assert state.entities[second_id].pools["hitpoints"] == 1200.0


def test_committing_after_the_window_is_simply_too_late(tmp_path: Path) -> None:
    """Late is not slow. An answer that lands after the blow was never made."""
    library = brawl_pack(tmp_path)
    result = answer(start(library).state, library, "block", share=1.5)
    assert resolved(result)["precision"] == 0.0
    assert resolved(result)["result"] == "absorbed"


def test_an_answer_the_fighter_does_not_have_is_refused(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    refused = step(result.state, Respond("pirouette", 700), library)
    assert any(e.kind == "engine.rule-failed" for e in refused.events)


def test_winning_takes_what_the_loser_carried(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    for _ in range(40):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "block")
    ended = next(e for e in result.events if e.kind == "combat.end")
    assert ended.payload()["outcome"] == "won"
    assert result.state.protagonist.inventory["brawl:purse"] == 3


def test_the_winning_scene_plays_afterwards(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    for _ in range(40):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "block")
    assert "He stays down." in [
        e.payload()["text"] for e in result.events if e.kind == "narrate"
    ]


def test_a_players_time_pressure_widens_every_window(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)

    windows = {}
    for pressure in (0.5, 1.0, 2.0):
        opened = begin(library, "brawl", seed="brawl", time_pressure=pressure)
        result = step(opened.state, Choose(0), library)
        tell = result.state.combat.tell if result.state.combat else None
        assert tell is not None
        windows[pressure] = tell.window_ms

    assert windows[0.5] > windows[1.0] > windows[2.0]
    assert windows[0.5] == pytest.approx(windows[1.0] * 2, rel=0.01)
    assert windows[2.0] == pytest.approx(windows[1.0] / 2, rel=0.01)


def test_the_clock_cannot_be_pressed_out_of_existence(tmp_path: Path) -> None:
    """A setting that reached zero would divide the window away entirely."""
    library = brawl_pack(tmp_path)
    opened = begin(library, "brawl", seed="brawl", time_pressure=0.0)
    result = step(opened.state, Choose(0), library)
    tell = result.state.combat.tell if result.state.combat else None
    assert tell is not None
    assert tell.window_ms > 0


def test_leaving_the_clock_alone_changes_nothing(tmp_path: Path) -> None:
    """The default has to be inert, or every golden file is a lie."""
    library = brawl_pack(tmp_path)
    plain = step(begin(library, "brawl", seed="brawl").state, Choose(0), library)
    asked = step(
        begin(library, "brawl", seed="brawl", time_pressure=1.0).state,
        Choose(0),
        library,
    )
    assert [event.record() for event in plain.events] == [
        event.record() for event in asked.events
    ]


def test_a_fight_never_moves_the_world_clock(tmp_path: Path) -> None:
    """Combat happens inside a tick; its clock is milliseconds, not hours."""
    library = brawl_pack(tmp_path)
    result = start(library)
    before = result.state.tick
    for _ in range(40):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "block")
    assert result.state.tick == before


def test_a_defeated_enemy_that_the_fight_found_stays_where_it_was(
    tmp_path: Path,
) -> None:
    """A fight tidies away what it made and leaves alone what it found."""
    library = brawl_pack(tmp_path)
    result = start(library)
    assert "brawl:thug" in result.state.entities
    for _ in range(40):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "block")
    assert "brawl:thug" in result.state.entities


def test_fighting_something_standing_here_does_not_conjure_a_second_one(
    tmp_path: Path,
) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    thugs = [
        entity
        for entity in result.state.entities.values()
        if entity.definition == "brawl:thug"
    ]
    assert len(thugs) == 1


def test_repeating_a_reference_makes_another_of_it(tmp_path: Path) -> None:
    """`against: [wolf, wolf]` is two wolves, not one wolf twice."""
    library = brawl_pack(
        tmp_path,
        scenes=[
            {
                "id": "pick-a-fight",
                "prompt": "Start something",
                "effects": [{"startCombat": {"against": ["thug", "thug", "thug"]}}],
            }
        ],
    )
    result = start(library)
    assert result.state.combat is not None
    assert len(result.state.combat.standing("enemy")) == 3


def test_a_correct_read_teaches_the_weapon_and_the_enemy(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = answer(start(library).state, library, "block")
    player = result.state.protagonist
    assert player.skills["brawl:club"] > 0.0
    assert player.familiarity["brawl:thug-style"] == 1


# ── Gear and range ────────────────────────────────────────────────────────────


def fighter(library: Library, tmp_path: Path) -> roster.Fighter:
    """The player's `Fighter`, freshly resolved at the start of a brawl.

    Parameters
    ----------
    library : Library
        The loaded pack.
    tmp_path : Path
        Unused — present so callers read like every other test here.

    Returns
    -------
    Fighter
        The player's fighter, as `fighter_for` would build it for the first
        exchange.
    """
    del tmp_path
    result = start(library)
    context = context_for(library, result.state)
    assert context.state.combat is not None
    combatant = next(
        c for c in context.state.combat.combatants if c.actor == context.state.player
    )
    return roster.fighter_for(combatant, context, cache={})


def test_a_weapons_range_becomes_the_fighters_weapon_range(tmp_path: Path) -> None:
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Club",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {"min": 4, "max": 4},
                    "range": {"min": 3, "max": 5, "sweetMin": 3.5, "sweetMax": 4.5},
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    fought = fighter(library, tmp_path)
    assert fought.weapon == "brawl:club"
    assert fought.weapon_range.min == 3
    assert fought.weapon_range.max == 5


def test_a_fight_opens_at_the_edge_of_the_players_own_weapon(tmp_path: Path) -> None:
    """A fight's starting distance comes from whatever the player has armed.

    Not the weapon's hard `max` — that's the point at which it's already
    down to zero effectiveness, and starting a fight there would mean every
    fighter's first exchange opens with a useless weapon. `sweetMax`, the
    far edge of where it's still fully effective, is what "at range" means
    here (docs/07-combat.md § Range).
    """
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "bow"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "bow",
                "kind": "item",
                "name": "Bow",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {"min": 4, "max": 9},
                    "range": {"min": 10, "max": 80, "sweetMin": 20, "sweetMax": 40},
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    result = start(library)
    fight = result.state.combat
    assert fight is not None
    thug = next(c for c in fight.combatants if c.side == "enemy")
    hero = next(c for c in fight.combatants if c.side == "player")
    assert abs(thug.position - hero.position) == 40.0


def test_a_surprise_attack_opens_at_melee_regardless_of_the_players_weapon(
    tmp_path: Path,
) -> None:
    """`surprise: true` skips the player's own weapon entirely.

    Same bow-wielding hero as the fight-opens-at-range test, but the scene
    marks this one an ambush — there was no time to bring the bow up, so it
    opens at the melee default instead of the bow's own sweet spot.
    """
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "bow"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "bow",
                "kind": "item",
                "name": "Bow",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {"min": 4, "max": 9},
                    "range": {"min": 10, "max": 80, "sweetMin": 20, "sweetMax": 40},
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
        scenes=[
            {
                "id": "pick-a-fight",
                "prompt": "Start something",
                "effects": [
                    {
                        "startCombat": {
                            "against": "thug",
                            "surprise": True,
                            "onWin": "you-won",
                            "onFlee": "you-ran",
                        }
                    }
                ],
            },
            {"id": "you-won", "visible": False, "say": "He stays down."},
            {"id": "you-ran", "visible": False, "say": "You run."},
        ],
    )
    result = start(library)
    fight = result.state.combat
    assert fight is not None
    thug = next(c for c in fight.combatants if c.side == "enemy")
    hero = next(c for c in fight.combatants if c.side == "player")
    assert abs(thug.position - hero.position) == UNARMED_RANGE.sweet_max


def test_a_weapon_with_no_range_falls_back_to_the_unarmed_default(
    tmp_path: Path,
) -> None:
    """A club with no `range` authored is still a weapon — just melee by default."""
    library = brawl_pack(tmp_path)
    fought = fighter(library, tmp_path)
    assert fought.weapon == "brawl:club"
    assert fought.weapon_range == UNARMED_RANGE


def test_bare_hands_fall_back_to_the_unarmed_range(tmp_path: Path) -> None:
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    fought = fighter(library, tmp_path)
    assert fought.weapon is None
    assert fought.weapon_damage == UNARMED
    assert fought.weapon_range == UNARMED_RANGE


def test_an_exhausted_weapon_stops_counting_as_gear(tmp_path: Path) -> None:
    """`ammo: 0` left in state drops a weapon out of `_gear` entirely.

    The player is still holding the spent rock — nothing here unequips it —
    but it can no longer be `weapon`/`weapon_damage`/`weapon_range`, the same
    as if the slot were empty.
    """
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "rock"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "rock",
                "kind": "item",
                "name": "Rock",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {"min": 2, "max": 5},
                    "ammo": 1,
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    result = start(library)
    context = context_for(library, result.state)
    result.state.protagonist.ammo["brawl:rock"] = 0
    combatant = next(
        c
        for c in context.state.combat.combatants  # type: ignore[union-attr]
        if c.actor == context.state.player
    )
    fought = roster.fighter_for(combatant, context, cache={})
    assert fought.weapon is None
    assert fought.weapon_damage == UNARMED
    assert fought.weapon_range == UNARMED_RANGE


def test_an_attack_out_of_its_own_range_cannot_land(tmp_path: Path) -> None:
    """A `swing` authored as a ranged move can't reach at melee engagement.

    Nobody has moved — `MELEE_ENGAGEMENT` is the whole distance there is —
    so a move whose `range` excludes it is simply unusable, whatever the read
    was. `dodge` is deliberately the wrong answer here, which would normally
    mean full, unmitigated damage; range gates it to nothing regardless.
    """
    library = brawl_pack(
        tmp_path,
        moves=[
            {"id": "guard", "kind": "defense", "type": "block", "cost": 4},
            {"id": "duck", "kind": "defense", "type": "dodge", "cost": 3},
            {
                "id": "swing",
                "type": "slash",
                "tell": "He swings.",
                "vagueTell": "He moves.",
                "windupMs": 1000,
                "counters": ["block"],
                "damage": {"min": 6, "max": 6},
                "range": {"min": 10, "max": 20, "sweetMin": 12, "sweetMax": 18},
                "cost": 5,
            },
        ],
    )
    result = answer(start(library).state, library, "dodge", share=0.05)
    payload = resolved(result)
    assert payload["result"] == "clean"
    assert payload["damageTaken"] == 0.0


def test_a_weapon_out_of_its_own_range_cannot_open_a_counter(tmp_path: Path) -> None:
    """Distance moving past a weapon's reach still zeroes out its opening.

    A fight opens with the player's weapon already at the edge of its own
    sweet spot — that's what sets the starting distance in the first place —
    so a fresh fight can never start with your own weapon already out of its
    own range. To exercise the gate, this stands in for movement that
    doesn't exist yet (`moveBy`) by pushing the thug out past the pike's
    `max` by hand between the fight opening and the answer.

    `block` is `swing`'s correct counter, answered well, so this would
    ordinarily be a clean counter with an opening.
    """
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Pike",
                "item": {
                    "equipSlot": "mainHand",
                    "damage": {"min": 4, "max": 4},
                    "range": {"min": 6, "max": 10, "sweetMin": 7, "sweetMax": 9},
                },
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    state = start(library).state
    fight = state.combat
    assert fight is not None
    thug = next(c for c in fight.combatants if c.side == "enemy")
    thug.position += 50.0  # well past the pike's `max` of 10
    result = answer(state, library, "block")
    payload = resolved(result)
    assert payload["result"] == "counter"
    assert payload["damageDealt"] == 0.0


# ── Movement ──────────────────────────────────────────────────────────────────


def test_closing_shrinks_the_distance(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    state = start(library).state
    fight = state.combat
    assert fight is not None
    before = fight.combatants[0].position - fight.combatants[1].position
    answer(state, library, "block", move_by=1.0)
    after = fight.combatants[0].position - fight.combatants[1].position
    assert abs(after) < abs(before)


def test_opening_widens_the_distance(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    state = start(library).state
    fight = state.combat
    assert fight is not None
    before = fight.combatants[0].position - fight.combatants[1].position
    answer(state, library, "block", move_by=-1.0)
    after = fight.combatants[0].position - fight.combatants[1].position
    assert abs(after) > abs(before)


def test_movement_is_clamped_by_speed(tmp_path: Path) -> None:
    """`moveBy` beyond `BASE_MOVE_STEP` at neutral speed goes no further."""
    library = brawl_pack(tmp_path)
    state = start(library).state
    fight = state.combat
    assert fight is not None
    before = abs(fight.combatants[0].position - fight.combatants[1].position)
    answer(state, library, "block", move_by=1000.0)
    after = abs(fight.combatants[0].position - fight.combatants[1].position)
    assert before - after == pytest.approx(combat.BASE_MOVE_STEP)


def test_closing_cannot_walk_through_the_attacker(tmp_path: Path) -> None:
    """Distance floors at zero rather than crossing to the other side."""
    library = brawl_pack(tmp_path)
    state = start(library).state
    fight = state.combat
    assert fight is not None
    thug = next(c for c in fight.combatants if c.side == "enemy")
    hero = next(c for c in fight.combatants if c.side == "player")
    thug.position = hero.position + 1.0  # closer than one full step
    answer(state, library, "block", move_by=1000.0)
    assert abs(thug.position - hero.position) == 0.0


def test_no_move_by_leaves_the_distance_unchanged(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    state = start(library).state
    fight = state.combat
    assert fight is not None
    before = fight.combatants[0].position - fight.combatants[1].position
    answer(state, library, "block")
    after = fight.combatants[0].position - fight.combatants[1].position
    assert after == before


# ── What a fight tells you about the other side ─────────────────────────────


def test_a_stranger_gets_no_read(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    assert reads_for(result, "brawl:thug") == []


def test_full_familiarity_gives_exact_numbers(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    opened = begin(library, "brawl", seed="brawl")
    opened.state.protagonist.familiarity["brawl:thug-style"] = 40
    result = step(opened.state, Choose(0), library)
    assert reads_for(result, "brawl:thug") == ["Strength 50.", "Speed 50."]


def test_partial_familiarity_gives_a_qualitative_read(tmp_path: Path) -> None:
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 80},
                    "speed": {"base": 20},
                },
                "combat": {"profile": "thug-style"},
                "inventory": [{"item": "purse", "qty": 3}],
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Club",
                "item": {"equipSlot": "mainHand", "damage": {"min": 4, "max": 4}},
            },
            {"id": "purse", "kind": "item", "name": "Purse", "item": {}},
        ],
    )
    opened = begin(library, "brawl", seed="brawl")
    opened.state.protagonist.familiarity["brawl:thug-style"] = 1
    result = step(opened.state, Choose(0), library)
    assert reads_for(result, "brawl:thug") == ["Hits hard.", "Slow."]


def test_fleeing_costs_effort_whether_or_not_it_works(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    before = result.state.protagonist.pools["stamina"]
    result = step(result.state, Respond("flee", 700), library)
    assert result.state.protagonist.pools["stamina"] < before


def _offered(result: StepResult) -> list[str]:
    """The response names a step left on offer.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    list of str
        The `response` of each option, in presentation order.
    """
    event = next(e for e in result.events if e.kind == "combat.responses")
    return [str(option["response"]) for option in event.payload()["options"]]


def test_fleeing_is_not_offered_when_content_forbids_it(tmp_path: Path) -> None:
    library = brawl_pack(
        tmp_path,
        scenes=[
            {
                "id": "pick-a-fight",
                "prompt": "Start something",
                "effects": [{"startCombat": {"against": "thug", "canFlee": False}}],
            }
        ],
    )
    assert "flee" not in _offered(start(library))


def test_an_enemy_with_no_effort_left_still_gets_answered(tmp_path: Path) -> None:
    """At zero effort a defense fails automatically; it does not vanish."""
    library = brawl_pack(tmp_path)
    result = start(library)
    result.state.protagonist.pools["stamina"] = 0.0
    result = answer(result.state, library, "block")
    assert resolved(result)["result"] == "clean"


def test_recovering_gives_effort_back_and_takes_the_hit(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    result.state.protagonist.pools["stamina"] = 5.0
    result = answer(result.state, library, "recover")
    payload = resolved(result)
    assert payload["result"] == "clean"
    assert result.state.protagonist.pools["stamina"] > 5.0


# ── Modes ─────────────────────────────────────────────────────────────────────


def test_tactical_mode_needs_no_clock(tmp_path: Path) -> None:
    """No time is measured, and reading still decides the fight."""
    library = brawl_pack(tmp_path, mode="tactical")
    result = start(library)
    result = step(result.state, Respond("block"), library)
    assert resolved(result)["precision"] == pytest.approx(resolution.TACTICAL_PRECISION)
    assert resolved(result)["result"] == "counter"


def test_tactical_mode_reads_the_tells_less_legibly(tmp_path: Path) -> None:
    """It gives up the execution half of skill, so the reading half is harder."""
    timed = brawl_pack(tmp_path / "timed", mode="reflex")
    untimed = brawl_pack(tmp_path / "untimed", mode="tactical")

    def legible(library: Library) -> int:
        return sum(
            next(
                e.payload()["clear"]
                for e in start(library, seed=f"clarity{i}").events
                if e.kind == "combat.tell"
            )
            for i in range(60)
        )

    assert legible(untimed) < legible(timed)


def test_auto_mode_plays_the_whole_fight_in_one_step(tmp_path: Path) -> None:
    """Nobody is waiting for a keypress, so there is nothing to wait for."""
    library = brawl_pack(tmp_path, mode="auto")
    result = start(library)
    assert result.state.combat is None
    assert "combat.end" in kinds(result)
    assert "combat.responses" not in kinds(result)


def test_a_fight_that_never_ends_is_stopped(tmp_path: Path) -> None:
    """Content that cannot hurt anybody produces a draw rather than a hang."""
    library = brawl_pack(
        tmp_path,
        moves=[
            {"id": "guard", "kind": "defense", "type": "block", "cost": 0},
            {
                "id": "swing",
                "type": "slash",
                "tell": "He swings.",
                "counters": ["block"],
                "cost": 0,
            },
        ],
        combatProfiles=[
            {"id": "hero-style", "moves": ["guard"]},
            {
                "id": "thug-style",
                "moves": ["guard", "swing"],
                "patterns": [{"sequence": ["swing"]}],
            },
        ],
    )
    result = begin(library, "brawl", seed="stale")
    result = step(result.state, Choose(0), library)
    # Neither side can land anything, so neither side can end it: `recover`
    # never opens an opening, and `swing` carries no damage.
    for _ in range(combat.MAX_EXCHANGES + 5):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "recover")
    assert result.state.combat is None
    ended = next(e for e in result.events if e.kind == "combat.end")
    assert ended.payload()["outcome"] == "fled"


# ── The acceptance test ───────────────────────────────────────────────────────


COUNTERS = {
    "overhead": "dodge",
    "sweep": "jump",
    "grapple": "strike",
    "feint": "strike",
    "slash": "block",
    "thrust": "parry",
}


def play_a_troll(library: Library, seed: str, *, reads: float, aims: float) -> str:
    """Fight Gorm with a given amount of skill, and report how it went.

    Parameters
    ----------
    library : Library
        The shipped packs.
    seed : str
        The session seed, which also seeds the simulated player.
    reads : float
        The chance the player picks the right counter — what they *know*.
    aims : float
        How tightly they hit the sweet spot, 0 to 1 — what they can *do*.

    Returns
    -------
    str
        `won`, `lost`, or `fled`.
    """
    import random  # noqa: PLC0415 — a simulated player, never the engine

    dice = random.Random(seed)
    result = begin(library, "peasants-quest", seed=seed)
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)
    result = step(
        result.state, _named(result, "Refuse, and put a hand on your hook"), library
    )

    for _ in range(200):
        fight = result.state.combat
        if fight is None or fight.tell is None:
            break
        pack_id, local = fight.tell.move.split(":")
        move = library.pack(pack_id).moves[local]
        right = COUNTERS.get(move.type)
        if right is not None and dice.random() < reads:
            response = right
        else:
            response = dice.choice(["block", "parry", "jump", "dodge"])
        ideal = (3 * fight.tell.window_ms) // 4
        slop = int((1.0 - aims) * fight.tell.window_ms * 0.5)
        drift = dice.randint(-slop, slop) if slop else 0
        result = step(result.state, Respond(response, max(0, ideal + drift)), library)

    ended = [e for e in result.events if e.kind == "combat.end"]
    if ended:
        return str(ended[-1].payload()["outcome"])
    return "lost"


def _named(result: StepResult, prompt: str) -> Choose:
    """Choose the offered option with a given prompt.

    Parameters
    ----------
    result : StepResult
        The step that offered it.
    prompt : str
        The option's text.

    Returns
    -------
    Choose
        The action.
    """
    assert result.state.pending is not None
    prompts = [option.prompt for option in result.state.pending.options]
    return Choose(prompts.index(prompt))


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_reading_an_enemy_wins_fights() -> None:
    """The acceptance test for the whole system, on the shipped troll.

    Two simulated players with an *identical character sheet*: one who has
    learned what beats an overhead and one who has not. If knowing does not
    win more fights, tempo combat has failed and the constants in
    `mace.engine.combat.resolution` are the thing to argue about — not this
    test.
    """
    library = load_library(REPO_ROOT / "packs")
    rounds = 24
    novice = sum(
        play_a_troll(library, f"n{i}", reads=0.30, aims=0.25) == "won"
        for i in range(rounds)
    )
    veteran = sum(
        play_a_troll(library, f"n{i}", reads=0.90, aims=0.85) == "won"
        for i in range(rounds)
    )
    assert veteran > novice + rounds // 3, (
        f"knowing the troll won {veteran}/{rounds} and not knowing it won "
        f"{novice}/{rounds}; the gap is what the whole system is for"
    )


def test_perfect_play_takes_no_damage_at_all() -> None:
    """The guarantee, on real content: reads and timing beat dice outright."""
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="flawless")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)
    result = step(
        result.state, _named(result, "Refuse, and put a hand on your hook"), library
    )
    full = result.state.protagonist.pools["hitpoints"]

    for _ in range(60):
        fight = result.state.combat
        if fight is None or fight.tell is None:
            break
        pack_id, local = fight.tell.move.split(":")
        move = library.pack(pack_id).moves[local]
        result = step(
            result.state,
            Respond(move.counters[0], (3 * fight.tell.window_ms) // 4),
            library,
        )

    assert result.state.protagonist.pools["hitpoints"] == full


def test_the_shipped_troll_takes_about_eight_exchanges_to_beat() -> None:
    """The number docs/07-combat.md promises, checked against the real pack."""
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="eight")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)
    result = step(
        result.state, _named(result, "Refuse, and put a hand on your hook"), library
    )
    for _ in range(60):
        fight = result.state.combat
        if fight is None or fight.tell is None:
            break
        pack_id, local = fight.tell.move.split(":")
        move = library.pack(pack_id).moves[local]
        result = step(
            result.state,
            Respond(move.counters[0], (3 * fight.tell.window_ms) // 4),
            library,
        )
    ended = next(e for e in result.events if e.kind == "combat.end")
    assert ended.payload()["outcome"] == "won"
    assert 5 <= ended.payload()["exchanges"] <= 12


def test_a_fight_draws_only_from_its_own_stream() -> None:
    """A forty-exchange fight must not change which encounter comes later."""
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="streams")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)
    before = dict(result.state.rng.positions())
    result = step(
        result.state, _named(result, "Refuse, and put a hand on your hook"), library
    )
    for _ in range(20):
        fight = result.state.combat
        if fight is None or fight.tell is None:
            break
        result = answer(result.state, library, "dodge")

    after = result.state.rng.positions()
    moved = {name for name in after if after[name] != before.get(name, 0)}
    assert moved == {"combat.combat#1"}, moved


def test_a_fight_replays_identically() -> None:
    library = load_library(REPO_ROOT / "packs")

    def run() -> list[Any]:
        result = begin(library, "peasants-quest", seed="twice")
        result = step(result.state, Travel("hagans-castle"), library)
        result = step(result.state, _named(result, "Speak to the troll"), library)
        result = step(
            result.state,
            _named(result, "Refuse, and put a hand on your hook"),
            library,
        )
        stream = list(result.records())
        for _ in range(20):
            fight = result.state.combat
            if fight is None or fight.tell is None:
                break
            result = answer(result.state, library, "dodge")
            stream.extend(result.records())
        return stream

    assert run() == run()


def test_an_answer_with_no_fight_is_refused() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="nofight")
    result = step(result.state, Respond("dodge", 500), library)
    assert any(e.kind == "engine.rule-failed" for e in result.events)


def test_the_engine_never_calls_random_during_a_fight() -> None:
    """Every draw comes from the seeded source, or replay is a lie."""
    import random  # noqa: PLC0415

    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="pure")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)

    original = random.random
    random.random = _forbidden
    try:
        result = step(
            result.state,
            _named(result, "Refuse, and put a hand on your hook"),
            library,
        )
        for _ in range(10):
            if result.state.combat is None or result.state.combat.tell is None:
                break
            result = answer(result.state, library, "dodge")
    finally:
        random.random = original


def _forbidden(*_args: Any, **_kwargs: Any) -> float:
    """Stand in for `random.random` so a direct call is a test failure.

    Returns
    -------
    float
        Never; it always raises.

    Raises
    ------
    AssertionError
        Always.
    """
    raise AssertionError("the engine called `random` directly")


def test_combat_state_finds_and_counts_its_combatants(tmp_path: Path) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    fight = result.state.combat
    assert fight is not None
    assert fight.find("brawl:hero") is not None
    assert fight.find("nobody") is None
    assert len(fight.standing("player")) == 1


def test_a_fight_cannot_be_started_against_something_absent(
    tmp_path: Path,
) -> None:
    library = brawl_pack(tmp_path)
    result = start(library)
    fight = result.state.combat
    assert fight is not None
    from mace.engine.step import _context  # noqa: PLC0415

    game = library.pack("brawl").game
    assert game is not None
    context = _context(library, result.state, game)
    with pytest.raises(RuleError, match="cannot fight"):
        combat.begin(context, ["nobody-at-all"], [])


# ── Allies and orders ─────────────────────────────────────────────────────────


def escort_pack(root: Path) -> Library:
    """A pack with an escort you can take along and two things to fight.

    Parameters
    ----------
    root : Path
        Where to write it.

    Returns
    -------
    Library
        The loaded library.
    """
    return brawl_pack(
        root,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {
                    "hitpoints": {"base": 60, "max": 60},
                    "stamina": {"base": 40, "max": 40},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "hero-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "escort",
                "kind": "actor",
                "name": "Escort",
                "stats": {
                    "hitpoints": {"base": 40, "max": 40},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
                "equipment": {"mainHand": "club"},
            },
            {
                "id": "thug",
                "kind": "actor",
                "name": "Thug",
                "stats": {
                    "hitpoints": {"base": 30, "max": 30},
                    "stamina": {"base": 30, "max": 30},
                    "strength": {"base": 50},
                    "speed": {"base": 50},
                },
                "combat": {"profile": "thug-style"},
            },
            {
                "id": "club",
                "kind": "item",
                "name": "Club",
                "item": {"equipSlot": "mainHand", "damage": {"min": 4, "max": 4}},
            },
        ],
        locations=[
            {
                "id": "yard",
                "name": "The Yard",
                "scenes": ["hire", "pick-a-fight"],
                "entities": ["escort"],
                "exits": [],
            }
        ],
        scenes=[
            {
                "id": "hire",
                "prompt": "Hire the escort",
                "effects": [{"attachAlly": {"entity": "escort"}}],
            },
            {
                "id": "pick-a-fight",
                "prompt": "Start something",
                "effects": [{"startCombat": {"against": ["thug", "thug"]}}],
            },
        ],
    )


def test_an_ally_fights_on_the_players_side(tmp_path: Path) -> None:
    library = escort_pack(tmp_path)
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)  # hire
    result = step(result.state, Choose(1), library)  # fight
    fight = result.state.combat
    assert fight is not None
    assert {c.actor for c in fight.standing("player")} == {
        "brawl:hero",
        "brawl:escort",
    }


def test_an_ally_swings_without_the_player_being_asked(tmp_path: Path) -> None:
    """Allies act on their own profiles; nobody waits on a keypress for them."""
    library = escort_pack(tmp_path)
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    result = step(result.state, Choose(1), library)
    for _ in range(30):
        if result.state.combat is None:
            break
        result = answer(result.state, library, "block")
        attackers = {
            e.payload()["attacker"] for e in result.events if e.kind == "combat.resolve"
        }
        if "brawl:escort" in attackers:
            return
    raise AssertionError("the escort never took a swing of its own")


def test_an_ally_follows_the_player(tmp_path: Path) -> None:
    library = escort_pack(tmp_path)
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    result.state.protagonist.location = "brawl:elsewhere"
    result = step(result.state, Choose(0), library)
    assert result.state.entities["brawl:escort"].location == "brawl:elsewhere"


def test_an_order_is_offered_only_when_it_would_mean_something(
    tmp_path: Path,
) -> None:
    """Nobody to direct, or one thing to direct them at, is a button."""
    alone = start(brawl_pack(tmp_path / "alone"))
    assert "focus" not in _offered(alone)

    library = escort_pack(tmp_path / "escorted")
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    result = step(result.state, Choose(1), library)
    assert "focus" in _offered(result)


def test_an_order_costs_the_exchange_it_is_given_in(tmp_path: Path) -> None:
    library = escort_pack(tmp_path)
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    result = step(result.state, Choose(1), library)
    before = result.state.protagonist.pools["hitpoints"]

    result = step(result.state, Respond("focus", 700), library)
    assert result.state.combat is not None
    assert result.state.combat.focus is not None
    assert result.state.protagonist.pools["hitpoints"] < before
    # Giving an order is not an answer to the move, so it lands square.
    assert resolved(result)["precision"] == 0.0


def test_repeating_an_order_moves_along_the_line(tmp_path: Path) -> None:
    library = escort_pack(tmp_path)
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    result = step(result.state, Choose(1), library)

    result = step(result.state, Respond("focus", 700), library)
    first = result.state.combat.focus  # type: ignore[union-attr]
    result = step(result.state, Respond("focus", 700), library)
    assert result.state.combat is not None
    assert result.state.combat.focus != first


# ── Fleeing a road ────────────────────────────────────────────────────────────


def test_running_mid_journey_costs_the_road_you_ran_back_down() -> None:
    """Running away is a decision with a story attached, so it costs position."""
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="runaway")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, _named(result, "Speak to the troll"), library)
    result = step(
        result.state, _named(result, "Refuse, and put a hand on your hook"), library
    )
    assert result.state.journey is not None
    before = result.state.journey.progress

    for _ in range(30):
        if result.state.combat is None:
            break
        result = step(result.state, Respond("flee", 700), library)

    ended = next(e for e in result.events if e.kind == "combat.end")
    if ended.payload()["outcome"] != "fled":
        pytest.skip("the troll caught them every time on this seed")
    assert result.state.journey is not None
    assert result.state.journey.progress < before
    assert result.state.journey.blocked_at is None


def test_an_ally_attached_until_something_leaves_when_it_happens(
    tmp_path: Path,
) -> None:
    """ "As far as the castle" has to be able to end at the castle."""
    library = brawl_pack(
        tmp_path,
        entities=[
            {
                "id": "hero",
                "kind": "actor",
                "name": "Hero",
                "playable": True,
                "stats": {"hitpoints": {"base": 40, "max": 40}},
                "combat": {"profile": "hero-style"},
            },
            {
                "id": "escort",
                "kind": "actor",
                "name": "Escort",
                "stats": {"hitpoints": {"base": 40, "max": 40}},
            },
        ],
        locations=[
            {
                "id": "yard",
                "name": "The Yard",
                "scenes": ["hire", "arrive"],
                "entities": ["escort"],
                "exits": [],
            }
        ],
        scenes=[
            {
                "id": "hire",
                "prompt": "Hire the escort",
                "effects": [
                    {
                        "attachAlly": {
                            "entity": "escort",
                            "until": {"flag": {"entity": "hero", "flag": "arrived"}},
                        }
                    }
                ],
            },
            {
                "id": "arrive",
                "prompt": "Arrive",
                "effects": [{"setFlag": {"entity": "hero", "flag": "arrived"}}],
            },
        ],
    )
    result = begin(library, "brawl", seed="escort")
    result = step(result.state, Choose(0), library)
    assert result.state.entities["brawl:escort"].ally is True

    result = step(result.state, Choose(1), library)
    assert result.state.entities["brawl:escort"].ally is False
