"""Using what you are carrying, in a room and in a fight.

`item.use` has been in the model, in the schema, and in `fantasy.core` since
phase 1, and until now the engine ignored it: bread declared six stamina and
gave none, because the only way to spend an item was an authored scene applying
the effects by hand. These tests are that block finally meaning what it says.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.content import Library, load_library
from mace.engine.actions import Choose, Respond, Travel, Use
from mace.engine.conditions import RuleError
from mace.engine.step import StepResult, begin, step, usable

REPO_ROOT = Path(__file__).resolve().parent.parent


def pack_with_a_potion(root: Path, **overrides: Any) -> Library:
    """A game whose hero carries something worth drinking.

    Parameters
    ----------
    root : Path
        Where to write it.
    **overrides
        Fields to merge into the potion's `item:` block.

    Returns
    -------
    Library
        The loaded library.
    """
    potion: dict[str, Any] = {
        "baseValue": 5,
        "use": {
            "consumed": True,
            "effects": [
                {
                    "adjustStat": {
                        "actor": "player",
                        "stat": "hitpoints",
                        "delta": 6,
                        "reason": "the draught",
                    }
                }
            ],
        },
    }
    potion.update(overrides)
    game_pack(
        root,
        world={
            "entities": [
                {
                    "id": "hero",
                    "kind": "actor",
                    "name": "Hero",
                    "playable": True,
                    "stats": {
                        "hitpoints": {"base": 20, "max": 20},
                        "stamina": {"base": 10, "max": 10},
                    },
                    "inventory": [
                        {"item": "draught", "qty": 2},
                        {"item": "rock", "qty": 1},
                    ],
                },
                {"id": "draught", "kind": "item", "name": "Draught", "item": potion},
                {"id": "rock", "kind": "item", "name": "Rock", "item": {}},
            ],
            "locations": [
                {"id": "home", "name": "Home", "exits": [{"to": "castle"}]},
                {"id": "castle", "name": "The Castle", "exits": [{"to": "home"}]},
            ],
            "routes": [{"id": "road", "from": "home", "to": "castle", "ticks": 2}],
            "scenes": [],
        },
    )
    return load_library(root / "tiny")


def prompts(result: StepResult) -> list[str]:
    """The options a step left on offer.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    list of str
        Option prompts, in order.
    """
    pending = result.state.pending
    return [] if pending is None else [option.prompt for option in pending.options]


def test_using_something_applies_its_effects(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    result.state.protagonist.pools["hitpoints"] = 10.0

    result = step(result.state, Use("draught"), library)
    assert result.state.protagonist.pools["hitpoints"] == 16.0


def test_a_consumed_item_is_spent(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    result = step(result.state, Use("draught"), library)
    assert result.state.protagonist.inventory["tiny:draught"] == 1
    result = step(result.state, Use("draught"), library)
    assert "tiny:draught" not in result.state.protagonist.inventory


def test_an_item_that_is_not_consumed_stays(tmp_path: Path) -> None:
    library = pack_with_a_potion(
        tmp_path,
        use={
            "consumed": False,
            "effects": [{"setFlag": {"entity": "hero", "flag": "rubbed"}}],
        },
    )
    result = begin(library, "tiny", seed="lamp")
    result = step(result.state, Use("draught"), library)
    assert result.state.protagonist.inventory["tiny:draught"] == 2
    assert "rubbed" in result.state.protagonist.flags


def test_using_what_you_do_not_have_is_refused(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    result.state.protagonist.inventory.pop("tiny:draught")
    result = step(result.state, Use("draught"), library)
    assert any(
        "you have no Draught" in e.payload().get("message", "")
        for e in result.events
        if e.kind == "engine.rule-failed"
    )


def test_using_something_with_no_use_block_is_refused(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    result = step(result.state, Use("rock"), library)
    assert any(
        "not something you can use" in e.payload().get("message", "")
        for e in result.events
        if e.kind == "engine.rule-failed"
    )


def test_the_menu_offers_what_you_can_use(tmp_path: Path) -> None:
    """A terminal has no inventory panel, so the menu is where this lives."""
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    assert "Use Draught" in prompts(result)
    assert "Use Rock" not in prompts(result)


def test_usable_options_come_after_the_roads(tmp_path: Path) -> None:
    """Talking and walking is what a player came for; eating the bread is not."""
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    offered = prompts(result)
    assert offered.index("Use Draught") > offered.index("Travel to The Castle")


def test_taking_the_menu_option_uses_it(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    result.state.protagonist.pools["hitpoints"] = 10.0
    result = step(result.state, Choose(prompts(result).index("Use Draught")), library)
    assert result.state.protagonist.pools["hitpoints"] == 16.0


def test_an_option_disappears_once_the_last_one_is_drunk(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    for _ in range(2):
        result = step(result.state, Use("draught"), library)
    assert "Use Draught" not in prompts(result)


def test_usable_lists_only_what_is_carried_and_usable(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    from mace.engine.step import _context  # noqa: PLC0415

    game = library.pack("tiny").game
    assert game is not None
    context = _context(library, result.state, game)
    assert [item for item, _found in usable(context)] == ["tiny:draught"]


def test_using_something_costs_no_time_unless_it_says_so(tmp_path: Path) -> None:
    """A bandage that takes ten minutes says so with `advanceTime`."""
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    before = result.state.tick
    result = step(result.state, Use("draught"), library)
    assert result.state.tick == before

    slow = pack_with_a_potion(
        tmp_path / "slow",
        use={
            "consumed": True,
            "effects": [{"advanceTime": {"ticks": 3}}],
        },
    )
    result = begin(slow, "tiny", seed="slow")
    before = result.state.tick
    result = step(result.state, Use("draught"), library=slow)
    assert result.state.tick == before + 3


# ── The bread that never fed anybody ──────────────────────────────────────────


def test_the_shipped_bread_finally_feeds_you() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = begin(library, "peasants-quest", seed="hungry")
    result.state.protagonist.pools["stamina"] = 10.0

    result = step(result.state, Use("fantasy.core:bread"), library)
    assert result.state.protagonist.pools["stamina"] == 16.0
    assert result.state.protagonist.inventory["fantasy.core:bread"] == 1


# ── Reaching for it mid-fight ─────────────────────────────────────────────────


def responses(result: StepResult) -> list[str]:
    """The response names on offer in a fight.

    Parameters
    ----------
    result : StepResult
        The step.

    Returns
    -------
    list of str
        Response names, in presentation order.
    """
    event = next(e for e in result.events if e.kind == "combat.responses")
    return [str(option["response"]) for option in event.payload()["options"]]


def picked(result: StepResult, prompt: str) -> Choose:
    """Choose an offered option by its prompt.

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
    return Choose(prompts(result).index(prompt))


def in_a_fight(library: Library, seed: str = "draught") -> StepResult:
    """Walk to the bridge and pick a fight with the troll.

    Parameters
    ----------
    library : Library
        The shipped packs.
    seed : str
        The session seed.

    Returns
    -------
    StepResult
        The step that started the fight.
    """
    result = begin(library, "peasants-quest", seed=seed, combat_mode="tactical")
    result = step(result.state, Travel("hagans-castle"), library)
    result = step(result.state, picked(result, "Speak to the troll"), library)
    return step(
        result.state, picked(result, "Refuse, and put a hand on your hook"), library
    )


def test_a_fight_offers_what_you_are_carrying() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    assert "use:fantasy.core:bread" in responses(result)


def test_an_option_is_labelled_with_the_items_name() -> None:
    """Only the engine knows what `use:fantasy.core:bread` is called."""
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    event = next(e for e in result.events if e.kind == "combat.responses")
    labels = {str(o["response"]): str(o["label"]) for o in event.payload()["options"]}
    assert labels["use:fantasy.core:bread"] == "Bread"
    assert labels["dodge"] == "dodge"


def test_reaching_for_it_costs_the_exchange() -> None:
    """You buy the stamina with a hit, which is what makes *when* a decision."""
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    result.state.protagonist.pools["stamina"] = 10.0
    before = result.state.protagonist.pools["hitpoints"]

    result = step(result.state, Respond("use:fantasy.core:bread"), library)
    player = result.state.protagonist
    assert player.pools["stamina"] > 10.0
    assert player.pools["hitpoints"] < before
    assert player.inventory["fantasy.core:bread"] == 1


def test_reaching_for_it_is_not_an_answer_to_the_move() -> None:
    """You spent the exchange on the pack, so the club lands square.

    It scored as a well-timed answer until this was noticed: the exchange had
    no elapsed time, and no elapsed time meant tactical precision rather than
    none at all.
    """
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    result = step(result.state, Respond("use:fantasy.core:bread"), library)
    resolved = next(e for e in result.events if e.kind == "combat.resolve")
    assert resolved.payload()["precision"] == 0.0
    assert resolved.payload()["result"] == "clean"


def test_the_fight_carries_on_afterwards() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    result = step(result.state, Respond("use:fantasy.core:bread"), library)
    assert result.state.combat is not None
    assert result.state.combat.tell is not None


def test_an_item_you_are_not_carrying_is_not_an_answer() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    result = step(result.state, Respond("use:fantasy.core:healing-draught"), library)
    assert any(e.kind == "engine.rule-failed" for e in result.events)


def test_using_the_last_one_takes_it_off_the_list() -> None:
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    for _ in range(2):
        result = step(result.state, Respond("use:fantasy.core:bread"), library)
    assert "use:fantasy.core:bread" not in responses(result)


def test_a_use_action_is_refused_mid_fight() -> None:
    """A fight collects answers, not actions. `use:` is how you reach for it."""
    library = load_library(REPO_ROOT / "packs")
    result = in_a_fight(library)
    result = step(result.state, Use("fantasy.core:bread"), library)
    assert any(
        "middle of a fight" in e.payload().get("message", "")
        for e in result.events
        if e.kind == "engine.rule-failed"
    )


def test_a_use_action_round_trips_through_its_record() -> None:
    from mace.engine.actions import decode  # noqa: PLC0415

    action = Use("fantasy.core:bread")
    assert decode(action.record()) == action


def test_using_something_that_is_not_there_raises(tmp_path: Path) -> None:
    library = pack_with_a_potion(tmp_path)
    result = begin(library, "tiny", seed="thirsty")
    from mace.engine.step import _context, spend_item  # noqa: PLC0415

    game = library.pack("tiny").game
    assert game is not None
    context = _context(library, result.state, game)
    with pytest.raises(RuleError, match="not an item any more"):
        spend_item("tiny:nothing-at-all", context, [])
