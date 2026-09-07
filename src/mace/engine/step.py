"""The step function: one action in, an ordered list of events out.

Everything a front-end knows comes through here. The engine offers options, the
front-end renders them and sends back which one was taken, and the cycle
repeats — a terminal, a browser tab, and eventually a server all doing exactly
the same thing with the same events.

The scene runner in the middle is the piece that makes a pack playable: check
the scene's conditions, say its lines, apply its effects, and then either jump
onward or stop and offer a choice. Flat scenes and `goto` mean that loop is a
loop rather than the recursive descent through anonymous fallbacks that made
the v0 model unreadable.
"""

from __future__ import annotations

from collections.abc import Container
from dataclasses import dataclass
from typing import Any

from mace.content import ContentError, Library
from mace.engine import environment
from mace.engine.actions import (
    Action,
    Choose,
    Haggle,
    Interact,
    Look,
    Respond,
    Trade,
    Travel,
    Use,
    Wait,
)
from mace.engine.combat import fight as combat
from mace.engine.conditions import RuleError, all_hold, holds
from mace.engine.context import RuleContext
from mace.engine.creation import Character, check
from mace.engine.creation import offer as creation_offer
from mace.engine.economy import haggle as bargaining
from mace.engine.economy import trade as market_trade
from mace.engine.effects import EffectOutcome, apply_all
from mace.engine.encounter import Rolled, roll, table_for
from mace.engine.events import (
    CharacterCreated,
    ChoiceOffered,
    ChoicesOffered,
    EncounterFired,
    Event,
    FlagChanged,
    FrontMoved,
    GameOver,
    Haggled,
    InventoryChanged,
    Moved,
    Narrated,
    QuestUpdated,
    RuleFailed,
    SceneEntered,
    StallOpened,
    StatChanged,
    TimePassed,
    Traded,
    TravelInterrupted,
    TravelLeg,
    WeatherChanged,
    WorldEvent,
    WorldStatus,
)
from mace.engine.rng import RandomSource
from mace.engine.state import (
    CombatState,
    EntityState,
    GameState,
    Journey,
    Outcome,
    PendingChoice,
    PendingChoices,
    QuestState,
    QuestStatus,
)
from mace.engine.stats import pool_bounds, starting_pools
from mace.engine.world import Clock, advance, region_of
from mace.engine.world import events as world_events
from mace.model import (
    Background,
    Calendar,
    Entity,
    Game,
    Location,
    Quest,
    Route,
    Scene,
    Terrain,
    WeatherFront,
)
from mace.model.calendar import STANDARD_YEAR
from mace.model.effects import Rest
from mace.model.text import DescriptionLine, SayLine

__all__ = ["StepResult", "begin", "context_for", "step"]

#: How many scenes may follow one another through `goto` before the engine
#: decides the content is looping. Generous enough that no honest chain hits it.
MAX_SCENE_CHAIN = 128

#: The menu that is offered when nothing else is pending.
OPTIONS_MENU = ""

#: How much of a rest's exposure relief a player gets with no roof over
#: them. Sleeping in a blizzard is still sleeping in a blizzard.
OPEN_REST_RELIEF = 0.25

#: The instance id that means "stop trading" rather than "start trading with".
#: An empty id can never name an entity, so the two readings cannot collide.
CLOSE_STALL = ""

#: The bulk lot a stall menu offers beside a single unit, so a terminal can
#: trade at a scale worth travelling for. A front-end with a quantity control
#: sends a `trade` action and is not limited to these two.
LOT = 10

#: How much road running away costs, in route ticks, when the author has not
#: said where fleeing puts you. Running is always available and never free, and
#: on a journey the price is the road you have to walk up again.
FLED_ROUTE_TICKS = 2


@dataclass(frozen=True, slots=True)
class StepResult:
    """What one action did.

    Attributes
    ----------
    state : GameState
        The playthrough, which the step mutated in place. Returned so callers
        can chain, and so a future immutable implementation would not change
        the signature.
    events : tuple of Event
        Everything that happened, in order.
    """

    state: GameState
    events: tuple[Event, ...]

    def records(self) -> list[dict[str, Any]]:
        """The events as they appear in a golden file.

        Returns
        -------
        list of dict
            One JSON-safe record per event.
        """
        return [event.record() for event in self.events]


def begin(
    library: Library,
    pack_id: str,
    seed: str = "mace",
    *,
    combat_mode: str | None = None,
    time_pressure: float = 1.0,
    character: Character | None = None,
    start_at: str | None = None,
    start_tick: int | None = None,
) -> StepResult:
    """Start a playthrough.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        Which game pack to play.
    seed : str
        The session seed. The same seed and actions replay identically.
    time_pressure : float
        How hard the clock presses in `reflex` combat. 1.0 is the fight as
        authored, below 1.0 gives more of the window. See
        `GameState.time_pressure`.
    combat_mode : str or None
        The player's choice of combat presentation, overriding the game's
        default. Part of what a session opens with, like the seed, because
        changing it midway would change what a recorded elapsed time means.
    character : Character or None
        What the player answered at character creation — which background,
        and where the creation points went. None takes the protagonist as the
        author wrote them, which is what a game offering neither of those has
        always meant. Setup rather than a turn, so a seed replays a poacher as
        exactly as it replays a farmhand (`mace.engine.creation`).
    start_at : str or None
        Open somewhere other than the game's own start location. This is what
        "start me at the Troll Bridge" is made of — a session parameter, so a
        playtest is still a replayable session rather than a special mode.
    start_tick : int or None
        Open at some other tick. "At midnight" is the other half of it.

    Returns
    -------
    StepResult
        The opening state, and everything the player sees before their first
        decision.

    Raises
    ------
    ContentError
        If the pack is not a playable game, or the allocation is not one the
        game offers.
    """
    pack = library.pack(pack_id)
    if pack.game is None:
        raise ContentError("is not a playable game pack", pack=pack_id)

    if character is not None:
        problems = check(creation_offer(library, pack_id), character)
        if problems:
            raise ContentError("; ".join(problems), pack=pack_id)

    state = _initial_state(
        library, pack_id, pack.game, seed, start_at=start_at, start_tick=start_tick
    )
    state.combat_mode = combat_mode
    state.time_pressure = time_pressure
    opening = _create_character(library, pack_id, state, character)
    context = _context(library, state, pack.game)
    events: list[Event] = []

    if character is not None and (character.background or character.spend):
        events.append(
            CharacterCreated(background=state.background, spend=dict(character.spend))
        )

    for line in pack.game.introduction:
        events.append(Narrated(line.text, line.pause))

    where = state.location
    assert where is not None
    events.append(Moved(None, where))
    _arrive(where, context, events, instead=opening)
    _after_action(context, events)
    return StepResult(state, tuple(events))


def step(state: GameState, action: Action, library: Library) -> StepResult:
    """Apply one player action.

    The library is a parameter rather than a field on the state because content
    is shared and immutable while state is per-session and mutable; keeping
    them apart is architecture boundary 1, and a save file that dragged a copy
    of every pack along with it would not be a save file.

    Parameters
    ----------
    state : GameState
        The playthrough. Mutated in place.
    action : Action
        What the player did.
    library : Library
        The loaded content.

    Returns
    -------
    StepResult
        The state and everything that happened.
    """
    game = library.pack(state.pack).game
    assert game is not None
    context = _context(library, state, game)
    events: list[Event] = []

    if state.outcome is not Outcome.PLAYING:
        return StepResult(state, ())

    try:
        restart = _perform(action, context, events)
    except RuleError as error:
        events.append(RuleFailed(error.message))
        return StepResult(state, tuple(events))
    except ContentError as error:
        # Validation catches dangling references before play, so reaching one
        # here means content changed under a save. Report it rather than
        # crashing the front-end out of the player's session.
        events.append(RuleFailed(error.message))
        return StepResult(state, tuple(events))

    if restart:
        fresh = begin(
            library,
            state.pack,
            state.seed,
            combat_mode=state.combat_mode,
            time_pressure=state.time_pressure,
        )
        return StepResult(fresh.state, tuple([*events, *fresh.events]))

    _after_action(context, events)
    return StepResult(state, tuple(events))


# ── Doing the thing the player asked for ──────────────────────────────────────


def _perform(action: Action, context: RuleContext, events: list[Event]) -> bool:
    """Carry out one action.

    Parameters
    ----------
    action : Action
        What the player did.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    state = context.state

    if isinstance(action, Respond):
        combat.respond(context, action.response, events, elapsed_ms=action.elapsed_ms)
        return _after_combat(context, events)

    if state.combat is not None and state.combat.outcome is None:
        # A fight is the one situation where the world stops offering options.
        # Looking around is free; everything else has to wait until it is over.
        if not isinstance(action, Look):
            raise RuleError("you are in the middle of a fight")

    if isinstance(action, Look):
        state.pending = None
        _describe_here(context, events)
        return False

    if isinstance(action, Wait):
        # Cleared first: `_advance` stops the wait short if something asks the
        # player a question, and last turn's menu is not that question.
        state.pending = None
        _advance(context, action.ticks, events)
        return False

    if isinstance(action, Interact):
        state.pending = None
        return _run_scene(context.qualify(action.scene, "scenes"), context, events)

    if isinstance(action, Use):
        state.pending = None
        return _use(context.qualify(action.item, "entities"), context, events)

    if isinstance(action, Travel):
        state.pending = None
        return _travel(context.qualify(action.to, "locations"), context, events)

    if isinstance(action, Haggle):
        _haggle(context, events)
        state.pending = None
        return False

    if isinstance(action, Trade):
        # Cleared only once the deal is made, so a refused trade leaves the
        # stall's menu where it was — being told you cannot afford something
        # should not close the shop.
        _trade(action.good, action.qty, context, events, sell=action.sell)
        state.pending = None
        return False

    return _choose(action, context, events)


def _choose(action: Choose, context: RuleContext, events: list[Event]) -> bool:
    """Take one of the options last offered.

    Parameters
    ----------
    action : Choose
        Which option.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.

    Raises
    ------
    RuleError
        If nothing was on offer, or the option does not exist.
    """
    state = context.state
    pending = state.pending
    if pending is None:
        raise RuleError("there is nothing to choose from right now")
    if not 0 <= action.option < len(pending.options):
        raise RuleError(
            f"there is no option {action.option}; "
            f"{len(pending.options)} were offered"
        )

    option = pending.options[action.option]
    if not option.available:
        raise RuleError(f"`{option.prompt}` is not available")

    state.pending = None

    if option.journey is not None:
        return _resume(context, events, onward=option.journey == "onward")

    if option.use is not None:
        return _use(option.use, context, events)

    if option.travel is not None:
        return _travel(option.travel, context, events)

    if option.haggle:
        _haggle(context, events)
        return False

    if option.trade is not None:
        if option.trade == CLOSE_STALL:
            state.trading = None
        else:
            _open_stall(option.trade, context, events)
        return False

    if option.deal is not None:
        good, qty, selling = option.deal
        _trade(good, qty, context, events, sell=selling)
        return False

    if option.effects:
        outcome = apply_all(option.effects, context, source=pending.scene)
        events.extend(outcome.events)
        if _settle(outcome, context, events):
            return outcome.restart

    if option.goto is not None:
        return _run_scene(option.goto, context, events)
    return False


def _start_combat(
    context: RuleContext,
    against: list[str],
    events: list[Event],
    *,
    spawned: set[str] | None = None,
    can_flee: bool = True,
    after: dict[str, str] | None = None,
    flee_to: str | None = None,
) -> bool:
    """Hand control to the combat system, and pick it back up when it lets go.

    A fight is not a scene and does not nest inside one: it takes over until
    it ends. In `auto` mode it ends inside this call, which is why the same
    function has to handle both a fight that is waiting for a keypress and a
    fight that is already over.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    against : list of str
        Instance ids of the opponents.
    events : list of Event
        Accumulator.
    spawned : set of str or None
        Which of them this fight put there.
    can_flee : bool
        Whether running is allowed.
    after : dict or None
        Outcome name to the qualified scene played once the fight ends.
    flee_to : str or None
        Qualified location id to put them down at.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    combat.begin(
        context,
        against,
        events,
        spawned=spawned,
        can_flee=can_flee,
        after=after,
        flee_to=flee_to,
    )
    return _after_combat(context, events)


def _after_combat(context: RuleContext, events: list[Event]) -> bool:
    """Clear away a finished fight and do whatever its outcome asked for.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    state = context.state
    fight = state.combat
    if fight is None or fight.outcome is None:
        return False

    state.combat = None
    for combatant in fight.combatants:
        gone = state.entities.get(combatant.actor)
        if gone is None or not (combatant.defeated or combatant.routed):
            continue
        if combatant.spawned:
            # A fight tidies away what it made. What it *found* stays where it
            # was: the troll who lives under the bridge is still under the
            # bridge afterwards, and `onWin` decides what it says now.
            del state.entities[combatant.actor]
        elif combatant.defeated:
            gone.location = None

    if fight.outcome == "fled" and _fled(fight, context, events):
        return True
    scene = fight.after.get(fight.outcome)
    if scene is not None:
        return _run_scene(scene, context, events)
    return False


def _fled(fight: CombatState, context: RuleContext, events: list[Event]) -> bool:
    """Put the player down somewhere after they have run.

    Running away should be a decision with a story attached, so it costs
    position rather than only effort. An explicit `fleeTo` says where; without
    one, running mid-journey drops the player back down the road they came up,
    with the ticks and the weather that implies. Running in a room leaves them
    in it, because there is nowhere for the room to put them.

    Parameters
    ----------
    fight : CombatState
        The finished fight.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    state = context.state
    if fight.flee_to is not None:
        origin = state.location
        _stand_at(state, fight.flee_to)
        state.journey = None
        events.append(Moved(origin, fight.flee_to))
        return False

    journey = state.journey
    if journey is None:
        return False

    lost = min(journey.progress, float(FLED_ROUTE_TICKS))
    journey.progress = max(0.0, journey.progress - lost)
    # Whatever stopped you is behind you now, and so is any waypoint you have
    # been driven back past: the road has to be walked up again to meet them.
    journey.blocked_at = None
    events.append(
        TravelInterrupted(
            route=journey.route,
            at=state.location or journey.origin,
            destination=journey.destination,
            remaining=round(lost, 3),
            reason="you ran back the way you came",
        )
    )
    return False


def _use(item_id: str, context: RuleContext, events: list[Event]) -> bool:
    """Use something the player is carrying.

    An item's `use` block has been in the model and in `fantasy.core` since
    phase 1 and has never done anything: bread declared six stamina and gave
    none, because the only way to spend an item was an authored scene applying
    the effects by hand. This is that block finally meaning what it says.

    Time is the author's to charge. Using something costs no tick by default,
    the way looking around does; a bandage that takes ten minutes says so with
    `advanceTime` in its own effects.

    Parameters
    ----------
    item_id : str
        Qualified entity id of the item.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.

    Raises
    ------
    RuleError
        If the player has none of it, or it is not a thing that can be used.
    """
    outcome = spend_item(item_id, context, events)
    if _settle(outcome, context, events):
        return outcome.restart
    for queued in outcome.play:
        if _run_scene(queued, context, events):
            return True
    return False


def spend_item(
    item_id: str, context: RuleContext, events: list[Event]
) -> EffectOutcome:
    """Apply an item's `use` effects and consume it if it says to.

    Public because a fight reaches for it too: `use:` as a combat response
    spends the same item the same way, and having two implementations of
    "drink the draught" is how they come to disagree.

    Parameters
    ----------
    item_id : str
        Qualified entity id of the item.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    EffectOutcome
        What the effects asked the runner for.

    Raises
    ------
    RuleError
        If the player has none of it, or it is not a thing that can be used.
    """
    state = context.state
    player = state.protagonist
    definition = _item(item_id, context)
    if definition.item is None or definition.item.use is None:
        raise RuleError(f"`{definition.name}` is not something you can use")
    if player.inventory.get(item_id, 0) < 1:
        raise RuleError(f"you have no {definition.name}")

    outcome = apply_all(definition.item.use.effects, context, source=item_id)
    events.extend(outcome.events)

    if definition.item.use.consumed:
        left = player.inventory.get(item_id, 0) - 1
        if left > 0:
            player.inventory[item_id] = left
        else:
            player.inventory.pop(item_id, None)
        events.append(
            InventoryChanged(
                actor=player.instance_id, item=item_id, delta=-1, quantity=max(left, 0)
            )
        )
    return outcome


def _item(item_id: str, context: RuleContext) -> Entity:
    """Look up an item definition by qualified id.

    Parameters
    ----------
    item_id : str
        The qualified id.
    context : RuleContext
        The playthrough.

    Returns
    -------
    Entity
        The definition.

    Raises
    ------
    RuleError
        If the content is no longer there.
    """
    pack_id, local_id = item_id.split(":", 1)
    found = context.library.pack(pack_id).entities.get(local_id)
    if found is None:
        raise RuleError(f"`{item_id}` is not an item any more")
    return found


def usable(context: RuleContext) -> list[tuple[str, Entity]]:
    """Everything in the player's pack that has a `use` block.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    list of tuple
        Qualified item id and definition, in inventory order so a menu and a
        combat response list agree with each other.
    """
    found: list[tuple[str, Entity]] = []
    for item_id, quantity in sorted(context.state.protagonist.inventory.items()):
        if quantity < 1:
            continue
        try:
            definition = _item(item_id, context)
        except RuleError:  # pragma: no cover — inventory ids come from content
            continue
        if definition.item is not None and definition.item.use is not None:
            found.append((item_id, definition))
    return found


# ── Trading ───────────────────────────────────────────────────────────────────


def _merchant(context: RuleContext, instance: str | None = None) -> EntityState | None:
    """The merchant the player is dealing with, or one standing here.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    instance : str or None
        A specific instance id. None takes whoever the stall is open with.

    Returns
    -------
    EntityState or None
        The merchant's instance, if it is a merchant and it is still here.
    """
    state = context.state
    wanted = state.trading if instance is None else instance
    if wanted is None:
        return None
    found = state.entities.get(wanted)
    if found is None or found.location != state.location:
        return None
    return found if market_trade.merchant_at(context, found) is not None else None


def _open_stall(instance: str, context: RuleContext, events: list[Event]) -> None:
    """Start dealing with a merchant: their remark, then their prices.

    The remark is ordinary conditional description, so what a merchant says
    about grain being dear is content and the choice of line is the only part
    the engine has an opinion about.

    Parameters
    ----------
    instance : str
        The merchant's instance id.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Raises
    ------
    RuleError
        If there is nobody there to deal with.
    """
    entity = _merchant(context, instance)
    if entity is None:
        raise RuleError("there is nobody here to trade with")
    block = market_trade.merchant_at(context, entity)
    assert block is not None

    context.state.trading = instance
    line = _first_matching(block.remarks, context)
    if line is not None:
        events.append(Narrated(line.text))
    # The prices themselves come from `_show_stall`, which runs with the menu
    # every turn the stall is open — including this one.


def _show_stall(context: RuleContext, events: list[Event]) -> None:
    """Lay the current prices out, if a stall is open.

    Emitted every time the menu is rebuilt rather than once on opening: a
    price moves when the player buys, and a front-end holding the first list
    would be quoting a market that no longer exists.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    stall = _stall(context)
    if stall is None:
        return
    _remember_prices(context, stall)
    events.append(
        StallOpened(
            merchant=stall.merchant,
            name=stall.name,
            market=stall.market,
            currency=stall.currency,
            purse=stall.purse,
            goods=tuple(row.record() for row in stall.goods),
        )
    )


def _stall(context: RuleContext) -> market_trade.Stall | None:
    """What the open stall is offering, or None when none is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    Stall or None
        The offer.
    """
    entity = _merchant(context)
    return None if entity is None else market_trade.look(context, entity)


def _haggle(context: RuleContext, events: list[Event]) -> None:
    """Press the open stall on its price.

    Whether the player has something to point at is worked out here rather
    than asked for, because "I know what this costs two towns over" is a fact
    about the journal, not a thing a front-end should be allowed to claim.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Raises
    ------
    RuleError
        If there is nobody to argue with, or they will not argue.
    """
    entity = _merchant(context)
    stall = _stall(context)
    if entity is None or stall is None:
        raise RuleError("you are not trading with anybody")
    block = market_trade.merchant_at(context, entity)
    assert block is not None

    knowing = bargaining.leverage(
        context,
        stall.market,
        tuple(row.good for row in stall.goods),
        {row.good: row.buy for row in stall.goods if row.buy is not None},
    )
    outcome = bargaining.push(context, entity, block, knowing=knowing)
    events.append(
        Haggled(
            merchant=entity.instance_id,
            name=stall.name,
            result=outcome.result,
            swing=outcome.swing,
            pushes=outcome.pushes,
            leverage=outcome.leverage,
        )
    )


def _remember_prices(context: RuleContext, stall: market_trade.Stall) -> None:
    """Write down what the player was just quoted, market by market.

    Only prices they were personally shown, which is what makes the journal
    worth reading and what gives "it is cheaper in Fenmoor" something honest
    to stand on. Recorded where the stall is *offered* rather than where it is
    read, so a projection never writes.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    stall : Stall
        What is on the counter.
    """
    seen = context.state.prices.setdefault(stall.market, {})
    for row in stall.goods:
        if row.buy is not None:
            seen[row.good] = row.buy


def _trade(
    good: str, qty: int, context: RuleContext, events: list[Event], *, sell: bool
) -> None:
    """Buy or sell, against whoever the player has a stall open with.

    Parameters
    ----------
    good : str
        The good reference.
    qty : int
        How many units.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    sell : bool
        Whether the player is handing the goods over.

    Raises
    ------
    RuleError
        If there is nobody to deal with, or the deal cannot be made.
    """
    entity = _merchant(context)
    if entity is None:
        raise RuleError("you are not trading with anybody")

    sale = market_trade.deal(context, entity, good, qty, sell=sell)
    player = context.state.protagonist
    stall = market_trade.look(context, entity)
    assert stall is not None

    for item, delta in (
        (sale.item, -sale.qty if sale.sell else sale.qty),
        (stall.currency, sale.coin if sale.sell else -sale.coin),
    ):
        events.append(
            InventoryChanged(
                actor=player.instance_id,
                item=item,
                delta=delta,
                quantity=player.inventory.get(item, 0),
            )
        )
    events.append(
        Traded(
            merchant=entity.instance_id,
            market=stall.market,
            good=sale.good,
            item=sale.item,
            qty=sale.qty,
            sell=sale.sell,
            coin=sale.coin,
        )
    )


def _offer_stall(context: RuleContext, options: list[PendingChoice]) -> None:
    """Build the menu of trades an open stall offers.

    One and ten of everything, in both directions. A front-end with a
    quantity control sends a `trade` action instead and is not limited to
    these two.

    A single unit the player cannot afford is still listed, greyed out with
    what they have: in a terminal this menu *is* the price list, and a stall
    that showed nothing because everything was out of reach would be a stall
    that would not tell you what anything cost. The bulk row is dropped
    instead of greyed, because ten of everything you cannot afford one of is
    a screen of noise.

    A sale the merchant cannot pay for is dropped rather than greyed, because
    the reason is not about this good — it is that they are out of money, and
    the line above the menu says so once instead of on every row.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    options : list of PendingChoice
        The menu being built.
    """
    stall = _stall(context)
    if stall is None:
        return

    for row in stall.goods:
        for lot in (1, LOT):
            if row.buy is not None and row.available >= lot:
                cost = _lot_price(context, stall.merchant, row.good, lot, sell=False)
                afford = cost is not None and stall.coin >= cost
                if cost is not None and (afford or lot == 1):
                    options.append(
                        PendingChoice(
                            prompt=f"Buy {_lot_of(lot, row.name)} ({cost} coin)",
                            deal=(row.good, lot, False),
                            available=afford,
                            hint=None if afford else f"you have {stall.coin}",
                        )
                    )
            if row.sell is not None and row.carried >= lot:
                paid = _lot_price(context, stall.merchant, row.good, lot, sell=True)
                # A price the merchant cannot cover is not an offer. Their
                # purse is the reason, and the line above the menu says so.
                if paid and (stall.purse is None or stall.purse >= paid):
                    options.append(
                        PendingChoice(
                            prompt=f"Sell {_lot_of(lot, row.name)} ({paid} coin)",
                            deal=(row.good, lot, True),
                        )
                    )
    if stall.haggles and not stall.soured:
        options.append(
            PendingChoice(
                prompt=f"Argue about the price with {stall.name}", haggle=True
            )
        )
    options.append(PendingChoice(prompt=f"Done with {stall.name}", trade=CLOSE_STALL))


def _lot_price(
    context: RuleContext, instance: str, good: str, qty: int, *, sell: bool
) -> int | None:
    """What a whole lot would come to, for the menu.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    instance : str
        The merchant's instance id.
    good : str
        Qualified good id.
    qty : int
        How many units.
    sell : bool
        Whether the player would be handing them over.

    Returns
    -------
    int or None
        The total, or None when the merchant cannot price it.
    """
    entity = context.state.entities.get(instance)
    if entity is None:  # pragma: no cover — the stall named it a line ago
        return None
    return market_trade.quote(context, entity, good, qty, sell=sell)


def _lot_of(qty: int, name: str) -> str:
    """Name a quantity of something the way a person would.

    Parameters
    ----------
    qty : int
        How many.
    name : str
        The item's name.

    Returns
    -------
    str
        `Grain`, or `ten Grain`.
    """
    return name if qty == 1 else f"{qty} {name}"


def _travel(destination: str, context: RuleContext, events: list[Event]) -> bool:
    """Set out for another location, and walk the road there.

    Parameters
    ----------
    destination : str
        Qualified location id.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.

    Raises
    ------
    RuleError
        If there is no way from here to there, or the weather has closed it.
    """
    state = context.state
    origin = state.location
    assert origin is not None
    exit_taken, route = _find_exit(destination, context)
    if exit_taken is None:
        raise RuleError(f"there is no way from here to `{destination}`")

    state.journey = None
    if route is None:
        # An exit with no route is a doorway, not a road: one tick, no legs.
        _stand_at(state, destination)
        _advance(context, 1, events)
        events.append(Moved(origin, destination, None, 1))
        return _arrive(destination, context, events)

    route_id = context.qualify(exit_taken.route or route.id, "routes")
    _refuse_if_shut(context, route_id)
    _refuse_if_closed(context)

    line = _first_matching(route.description, context)
    if line is not None:
        events.append(Narrated(line.text))

    state.journey = Journey(route=route_id, origin=origin, destination=destination)
    return _walk(route, context, events)


def _refuse_if_closed(context: RuleContext) -> None:
    """Stop a journey from starting when the weather has closed the road.

    `blocksTravel` bites at the moment of setting out, not partway along it.
    Being told you cannot leave is a decision — shelter here, and lose the
    day — whereas being stopped three ticks down a road you have already
    committed to is just a punishment. Weather met mid-journey slows the
    player down through `travelMultiplier` instead, which a blizzard sets
    high enough to hurt.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Raises
    ------
    RuleError
        If the road is closed.
    """
    observed = context.weather()
    if not observed.blocks_travel:
        return
    raise RuleError(
        f"the road is closed — nobody is travelling in this {observed.label}"
    )


def _refuse_if_shut(context: RuleContext, route_id: str) -> None:
    """Stop a journey down a road something has closed.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    route_id : str
        Qualified route id.

    Raises
    ------
    RuleError
        If the road is shut.
    """
    road = context.state.routes.get(route_id)
    if road is None or not road.closed:
        return
    raise RuleError(road.reason or "that road is closed")


def _length(route: Route, context: RuleContext) -> int:
    """How long a road is now, which is not always how it was written.

    Parameters
    ----------
    route : Route
        The road.
    context : RuleContext
        The playthrough.

    Returns
    -------
    int
        Its length in route ticks.
    """
    pack_id = context.state.pack
    try:
        route_id = context.library.resolve(route.id, "routes", within=pack_id)
    except ContentError:
        return route.ticks
    road = context.state.routes.get(route_id)
    if road is not None and road.ticks is not None:
        return road.ticks
    return route.ticks


def _walk(route: Route, context: RuleContext, events: list[Event]) -> bool:
    """Resolve a journey leg by leg until it ends or something stops it.

    One world tick at a time, because that is what makes distance felt: the
    weather can change under you, a journey that starts at dusk finishes in
    the dark, and bad going costs you real hours. `travelMultiplier` scales
    how much road a tick of walking is worth, so a storm turns a three-tick
    road into a five-tick slog without anybody computing a total in advance.

    The road's terrain multiplies on top of the weather's own, because rain on
    a paved highway is an inconvenience and rain on a forest track is mud to
    the ankles. That is what makes the long way round on a good road worth
    considering — but only when it is wet.

    Parameters
    ----------
    route : Route
        The road being walked.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    state = context.state
    journey = state.journey
    assert journey is not None

    length = _length(route, context)
    stops = _waypoints(route, journey, context)
    began_at = state.tick
    leg = int(journey.progress)

    if _still_barred(stops, journey, context):
        _interrupt(route, context, events, "the way is still barred")
        return False

    surface = _terrain(route, context)

    while journey.progress < length:
        leg_before = int(journey.progress)
        _tick(context, events)
        observed = context.weather()
        going = observed.travel_multiplier
        if surface is not None:
            going *= surface.cost(observed.tags)
        journey.progress += 1.0 / max(0.01, going)

        reached = _next_waypoint(stops, journey)
        crossed = min(int(journey.progress), length)
        if crossed > leg or reached is not None:
            leg = crossed
            events.append(
                TravelLeg(
                    route=journey.route,
                    leg=min(leg, length),
                    of=length,
                    waypoint=reached[0] if reached is not None else None,
                    text=_leg_line(route, context),
                )
            )

        if crossed > leg_before and _encounters(context, events, on=route):
            return True
        if state.combat is not None:
            _interrupt(route, context, events, "something on the road")
            return False
        if state.pending is not None:
            _interrupt(route, context, events, "something on the road")
            return False

        if reached is None:
            continue

        where, stop_if, table = reached
        _stand_at(state, where)
        if _arrive(where, context, events):
            return True

        found = table_for(context, table)
        if found is not None:
            hit = roll(context, found[0], found[1])
            if hit is not None and _happens(hit, where, context, events):
                return True

        barred = bool(stop_if) and all_hold(stop_if, context)
        if barred:
            journey.blocked_at = where
            _interrupt(route, context, events, "the way is barred")
            return False

        journey.passed = (*journey.passed, where)
        if state.combat is not None:
            _interrupt(route, context, events, "something here wants a fight")
            return False
        if state.pending is not None:
            # The waypoint's own scene is asking the player something. The
            # journey waits on the answer rather than walking through it.
            _interrupt(route, context, events, "something here wants an answer")
            return False

    _finish(route, began_at, context, events)
    return _arrive(journey.destination, context, events)


def _still_barred(
    stops: list[tuple[float, str, Any, str | None]],
    journey: Journey,
    context: RuleContext,
) -> bool:
    """Whether the waypoint that stopped this journey is still stopping it.

    Checked before a tick is spent, so trying the bridge again while the troll
    is still owed costs nothing but the answer. Once the condition lifts the
    waypoint counts as passed and the journey carries on from where it stood.

    Parameters
    ----------
    stops : list of tuple
        The waypoints, from `_waypoints`.
    journey : Journey
        The journey, whose `blocked_at` is being reconsidered.
    context : RuleContext
        The playthrough.

    Returns
    -------
    bool
        Whether the road is still shut.
    """
    if journey.blocked_at is None:
        return False
    for _at, where, stop_if, _table in stops:
        if where != journey.blocked_at:
            continue
        if stop_if and all_hold(stop_if, context):
            return True
        break
    journey.passed = (*journey.passed, journey.blocked_at)
    journey.blocked_at = None
    return False


def _terrain(route: Route, context: RuleContext) -> Terrain | None:
    """The surface a road is made of, if the author said.

    Parameters
    ----------
    route : Route
        The road.
    context : RuleContext
        The playthrough.

    Returns
    -------
    Terrain or None
        Its terrain.
    """
    if route.terrain is None:
        return None
    try:
        found = context.library.find(
            route.terrain, "terrains", within=context.state.pack
        )
    except ContentError:
        return None
    return found if isinstance(found, Terrain) else None


def _finish(
    route: Route, began_at: int, context: RuleContext, events: list[Event]
) -> None:
    """Put the player down at the far end of a road.

    Parameters
    ----------
    route : Route
        The road walked.
    began_at : int
        The tick the journey started on.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    journey = state.journey
    assert journey is not None
    origin = state.location

    _stand_at(state, journey.destination)
    state.journey = None
    _announce_time(context, state.tick - began_at, events)
    events.append(
        Moved(origin, journey.destination, journey.route, state.tick - began_at)
    )
    del route


def _interrupt(
    route: Route, context: RuleContext, events: list[Event], reason: str
) -> None:
    """Stop a journey where it stands, leaving it to be carried on later.

    Parameters
    ----------
    route : Route
        The road being walked.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    reason : str
        What stopped it.
    """
    state = context.state
    journey = state.journey
    assert journey is not None
    where = state.location
    assert where is not None
    events.append(
        TravelInterrupted(
            route=journey.route,
            at=where,
            destination=journey.destination,
            remaining=round(_length(route, context) - journey.progress, 3),
            reason=reason,
        )
    )


def _resume(context: RuleContext, events: list[Event], *, onward: bool) -> bool:
    """Carry on an interrupted journey, or turn round and walk it back.

    Turning back is not free and not instant: the road already walked has to
    be walked again, which is what makes "push on or turn round" a decision
    rather than an undo. Waypoints already passed are not met a second time.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    onward : bool
        Whether to carry on rather than turn back.

    Returns
    -------
    bool
        Whether the game should restart.

    Raises
    ------
    RuleError
        If there is no journey to carry on, or the weather has closed the road.
    """
    state = context.state
    journey = state.journey
    if journey is None:
        raise RuleError("there is no journey to carry on")
    _refuse_if_closed(context)

    pack_id, local_id = journey.route.split(":", 1)
    route = context.library.pack(pack_id).routes.get(local_id)
    if route is None:
        state.journey = None
        raise RuleError(f"the route `{journey.route}` is no longer there")

    if not onward:
        # Walking back past whatever stopped you is always allowed: a troll who
        # will not let you north has no opinion about you going home.
        behind = journey.passed
        if journey.blocked_at is not None:
            behind = (*behind, journey.blocked_at)
        state.journey = Journey(
            route=journey.route,
            origin=journey.destination,
            destination=journey.origin,
            progress=_length(route, context) - journey.progress,
            passed=behind,
        )
    return _walk(route, context, events)


def _waypoints(
    route: Route, journey: Journey, context: RuleContext
) -> list[tuple[float, str, Any, str | None]]:
    """Where the waypoints of a route fall, in the direction being walked.

    A waypoint with no `atTick` is spaced evenly along the road, and the whole
    list is mirrored when the road is walked the other way — the bridge is
    three ticks from Fenmoor whichever end you started at.

    Parameters
    ----------
    route : Route
        The road.
    journey : Journey
        The journey, for which way round it is being walked.
    context : RuleContext
        The playthrough.

    Returns
    -------
    list of tuple
        Progress, qualified location id, the conditions that force a stop, and
        the waypoint's own encounter table, in the order they are met.
    """
    backwards = context.qualify(route.origin, "locations") != journey.origin
    count = len(route.waypoints)
    stops: list[tuple[float, str, Any, str | None]] = []

    for index, waypoint in enumerate(route.waypoints, start=1):
        at = (
            float(waypoint.at_tick)
            if waypoint.at_tick is not None
            else route.ticks * index / (count + 1)
        )
        if backwards:
            at = route.ticks - at
        stops.append(
            (
                at,
                context.qualify(waypoint.location, "locations"),
                waypoint.stop_if,
                waypoint.encounters,
            )
        )
    stops.sort(key=lambda entry: entry[0])
    return stops


def _next_waypoint(
    stops: list[tuple[float, str, Any, str | None]], journey: Journey
) -> tuple[str, Any, str | None] | None:
    """The waypoint this leg reached, if it reached one.

    Parameters
    ----------
    stops : list of tuple
        The waypoints, from `_waypoints`.
    journey : Journey
        The journey.

    Returns
    -------
    tuple or None
        The location, its `stopIf` conditions, and its own table, or None.
    """
    for at, where, stop_if, table in stops:
        if where in journey.passed:
            continue
        if journey.progress >= at:
            return where, stop_if, table
    return None


def _encounters(
    context: RuleContext, events: list[Event], *, on: Route | None = None
) -> bool:
    """Roll every table that applies where the player is, and act on a hit.

    The tables that apply are the region's, then the road's or the place's —
    region first, so a road's own entries are the more specific answer and get
    to be the last word when both fire in the same breath.

    `safe: true` on a location suppresses all of it. Towns are safe; the
    wilderness is not.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    on : Route or None
        The road being walked, if the player is on one.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    state = context.state
    here = context.here()
    if here is not None and here.safe and on is None:
        return False

    for reference, home, where in _tables_here(context, here, on):
        found = table_for(context, reference, within=home)
        if found is None:
            continue
        table_id, table = found
        fired = roll(context, table_id, table)
        if fired is None:
            continue
        if _happens(fired, where, context, events):
            return True
        if state.pending is not None:
            # The encounter is asking the player something. Nothing else rolls
            # until they have answered it.
            return False
    return False


def _tables_here(
    context: RuleContext, here: Location | None, on: Route | None
) -> list[tuple[str | None, str, str | None]]:
    """Which tables to roll, in order, and the pack each was written in.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    here : Location or None
        Where the player is.
    on : Route or None
        The road being walked, if any.

    Returns
    -------
    list of tuple
        Reference, the pack it was written in, and where it would happen.
    """
    tables: list[tuple[str | None, str, str | None]] = []
    region = region_of(
        context.library, context.state.pack, here, context.game.world.start_region
    )
    if region is not None:
        pack_id, local_id = region.split(":", 1)
        definition = context.library.pack(pack_id).regions.get(local_id)
        if definition is not None:
            tables.append((definition.encounters, pack_id, region))

    if on is not None:
        tables.append(
            (
                on.encounters,
                context.state.pack,
                (
                    context.state.journey.route
                    if context.state.journey is not None
                    else None
                ),
            )
        )
    elif here is not None:
        tables.append((here.encounters, context.state.pack, context.state.location))
    return [entry for entry in tables if entry[0] is not None]


def _happens(
    fired: Rolled, where: str | None, context: RuleContext, events: list[Event]
) -> bool:
    """Turn a rolled entry into the thing it stands for.

    Parameters
    ----------
    fired : Rolled
        What the table produced.
    where : str or None
        Where it happened.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    events.append(
        EncounterFired(
            table=fired.table,
            entry=fired.entry.id,
            chance=round(fired.chance, 4),
            where=where,
        )
    )
    if fired.entry.scene is not None:
        return _run_scene(context.qualify(fired.entry.scene, "scenes"), context, events)

    assert fired.entry.combat is not None
    spawned = [
        _spawn(reference, context, context.state.location)
        for reference in fired.entry.combat.against
    ]
    flee_to = fired.entry.combat.flee_to
    return _start_combat(
        context,
        spawned,
        events,
        flee_to=(None if flee_to is None else context.qualify(flee_to, "locations")),
    )


def _leg_line(route: Route, context: RuleContext) -> str | None:
    """A line of road flavor for this leg, chosen for the hour and the sky.

    Unlike a location's description, which takes the *first* line that fits so
    an author can order their variants by specificity, a leg line is drawn at
    random from all of them. A place should read the same way twice; a road
    should not, or six legs of it is the same sentence six times.

    Parameters
    ----------
    route : Route
        The road.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str or None
        The line, or None when the author wrote none that fit.
    """
    eligible = [
        line for line in route.leg_descriptions or () if all_hold(line.when, context)
    ]
    if not eligible:
        return None
    stream = context.state.rng.stream(f"travel.{route.id}")
    return stream.choice(eligible).text


def _find_exit(
    destination: str, context: RuleContext
) -> tuple[Any | None, Route | None]:
    """Find the exit that leads to a destination, if the player may take it.

    Parameters
    ----------
    destination : str
        Qualified location id.
    context : RuleContext
        The playthrough.

    Returns
    -------
    tuple
        The exit and its route, or (None, None).
    """
    here = _location(context.state.location, context)
    if here is None:
        return None, None
    for way in here.exits:
        if context.qualify(way.to, "locations") != destination:
            continue
        if not all_hold(way.when, context):
            continue
        route = None
        if way.route is not None:
            found = context.library.find(way.route, "routes", within=context.state.pack)
            route = found if isinstance(found, Route) else None
        return way, route
    return None, None


def _follow(context: RuleContext, events: list[Event]) -> None:
    """Bring the player's allies along, and let go of the ones who are done.

    An escort that stayed in Fenmoor while you walked to the castle would not
    be an escort. Kept as its own step rather than folded into movement so
    that every way of moving — walking a road, a `move` effect, fleeing a
    fight — brings them without each remembering to.

    An ally attached `until` some condition leaves the moment it comes true,
    wherever that happens to be. "As far as the castle" has to be able to end
    at the castle, and the scene that said it is long gone by then.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    where = context.state.location
    for _key, entity in sorted(context.state.entities.items()):
        if not entity.ally:
            continue
        if entity.ally_until is not None and holds(entity.ally_until, context):
            entity.ally = False
            entity.ally_until = None
            events.append(
                FlagChanged(entity=entity.instance_id, flag="ally", value=False)
            )
            continue
        entity.location = where


def _stand_at(state: GameState, where: str) -> None:
    """Put the player in a place, and remember that they have been there.

    Every way of arriving somewhere goes through here — a doorway, a road, a
    waypoint on one, a fight run from — so that knowing a place and having
    been to it never come apart. See `GameState.visited`.

    Parameters
    ----------
    state : GameState
        The playthrough.
    where : str
        Qualified location id.
    """
    state.protagonist.location = where
    state.revealed.add(where)
    state.visited.add(where)
    # Every way of leaving somewhere comes through here, so a stall cannot
    # follow the player down the road.
    state.trading = None


def _arrive(
    location_id: str,
    context: RuleContext,
    events: list[Event],
    *,
    instead: str | None = None,
) -> bool:
    """Describe a place and run its arrival scene.

    Parameters
    ----------
    location_id : str
        Qualified location id.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    instead : str or None
        A scene to run in place of the location's own `onArrive`. This is how
        a background overrides the game's opening: the old soldier still walks
        into Fenmoor and still sees it, and what happens next is his.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    _sync_weather(context, events)
    _describe_here(context, events)
    here = _location(location_id, context)
    arrival = (
        instead if instead is not None else (None if here is None else here.on_arrive)
    )
    if arrival is not None:
        return _run_scene(context.qualify(arrival, "scenes"), context, events)
    return False


def _describe_here(context: RuleContext, events: list[Event]) -> None:
    """Narrate the current location.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    here = _location(context.state.location, context)
    if here is None:
        return
    events.append(Narrated(here.name))
    line = _first_matching(here.description, context)
    if line is not None:
        events.append(Narrated(line.text))


# ── Running a scene ───────────────────────────────────────────────────────────


def _run_scene(scene_id: str, context: RuleContext, events: list[Event]) -> bool:
    """Play a scene, following `goto` until it stops or offers a choice.

    Parameters
    ----------
    scene_id : str
        Qualified scene id.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.

    Raises
    ------
    RuleError
        If the scenes lead into each other forever.
    """
    state = context.state
    current: str | None = scene_id

    for _hop in range(MAX_SCENE_CHAIN):
        if current is None:
            return False
        scene = _scene(current, context)

        if scene.once and current in state.played:
            return False
        if not all_hold(scene.when, context):
            current = (
                context.qualify(scene.otherwise, "scenes")
                if scene.otherwise is not None
                else None
            )
            continue

        state.played.add(current)
        events.append(SceneEntered(current))

        for line in scene.say:
            if all_hold(line.when, context):
                events.append(Narrated(line.text, line.pause))

        outcome = apply_all(scene.effects, context, source=current)
        events.extend(outcome.events)
        if _settle(outcome, context, events):
            return outcome.restart

        for queued in outcome.play:
            if _run_scene(queued, context, events):
                return True
            if state.pending is not None:
                return False

        if scene.choices:
            _offer_scene_choices(current, scene, context, events)
            return False

        current = (
            context.qualify(scene.goto, "scenes") if scene.goto is not None else None
        )

    raise RuleError(
        f"scenes lead into each other without stopping, starting at `{scene_id}`"
    )


def _settle(outcome: EffectOutcome, context: RuleContext, events: list[Event]) -> bool:
    """Act on an effect outcome: the time it asked for, and the game it ended.

    Effects request time rather than take it, because moving the clock means
    moving the *world* — weather, fronts, encounters — and an effect that bumped
    the tick counter itself would skip all of that. Time is spent here, once,
    after the effects in a block have all run.

    Parameters
    ----------
    outcome : EffectOutcome
        What the effects asked for.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the caller should stop what it was doing.
    """
    if outcome.restart:
        return True
    if outcome.ended is not None:
        _end(context, outcome.ended, "the story ended", events)
        return True

    for event_id, share in outcome.pressure:
        world_events.set_pressure(context, event_id, share)
    for event_id in outcome.fire:
        for happening in world_events.fire(context, event_id):
            _happened(context, happening, events)

    if outcome.elapsed:
        _advance(context, outcome.elapsed, events)
    if outcome.rest is not None:
        _recover(outcome.rest, context, events)

    if outcome.combat is not None:
        asked = outcome.combat
        actors, spawned = _opponents(asked.against, context)
        if _start_combat(
            context,
            actors,
            events,
            spawned=spawned,
            can_flee=asked.can_flee,
            after={
                name: context.qualify(scene, "scenes")
                for name, scene in (
                    ("won", asked.on_win),
                    ("lost", asked.on_lose),
                    ("fled", asked.on_flee),
                )
                if scene is not None
            },
        ):
            return True
        # A fight that is still waiting for an answer stops the scene it came
        # from: there is nothing to say while somebody is swinging at you.
        if context.state.combat is not None:
            return True

    return context.state.outcome is not Outcome.PLAYING


def _recover(rest: Rest, context: RuleContext, events: list[Event]) -> None:
    """Refill what a rest was for, once its hours have actually passed.

    After the time, not before, so a player who sits out a blizzard in the
    open finds it has not helped very much: the hours they slept through are
    hours they spent in the blizzard, and only a roof lets a rest shed all of
    the exposure it took. Pools come back either way — sleep is sleep — which
    is what makes the inn worth the detour rather than the only option.

    Parameters
    ----------
    rest : Rest
        What was asked for.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    player = context.state.protagonist
    definition = context.definition(player)
    shelter = 1.0 if context.weather().sheltered else OPEN_REST_RELIEF
    player.exposure = max(0.0, player.exposure - rest.fraction * shelter)

    wanted = rest.pools or tuple(definition.stats or {})
    for name in wanted:
        low, high = pool_bounds(definition, name)
        if high is None:
            continue
        current = player.pools.get(name)
        if current is None or current >= high:
            continue
        restored = min(high, current + (high - low) * rest.fraction)
        player.pools[name] = restored
        events.append(
            StatChanged(
                actor=player.instance_id,
                stat=name,
                delta=round(restored - current, 3),
                value=round(restored, 3),
                reason="rest",
            )
        )


def _offer_scene_choices(
    scene_id: str, scene: Scene, context: RuleContext, events: list[Event]
) -> None:
    """Present a scene's choices and wait.

    A choice whose conditions fail is hidden, unless the author asked for it to
    be shown greyed out — seeing what you are missing is motivation, and only
    the author knows which it should be.

    Parameters
    ----------
    scene_id : str
        Qualified scene id.
    scene : Scene
        The scene.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    options: list[PendingChoice] = []
    for choice in scene.choices:
        available = all_hold(choice.when, context)
        if not available and not choice.show_when_unavailable:
            continue
        options.append(
            PendingChoice(
                prompt=choice.prompt,
                goto=(
                    context.qualify(choice.goto, "scenes")
                    if choice.goto is not None
                    else None
                ),
                effects=tuple(choice.effects),
                available=available,
                hint=choice.unavailable_hint,
            )
        )

    context.state.pending = PendingChoices(scene_id, tuple(options))
    events.append(
        ChoicesOffered(
            scene_id,
            tuple(
                ChoiceOffered(option.prompt, option.available, option.hint)
                for option in options
            ),
        )
    )


# ── After every action ────────────────────────────────────────────────────────


def _after_action(context: RuleContext, events: list[Event]) -> None:
    """Run everything that happens between one action and the next.

    The order is fixed and part of the contract: quests settle before win and
    lose conditions are judged, so a quest completing on this action can be the
    thing that wins the game, and the status projection comes last so it
    describes the world the offered choices belong to.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    if state.outcome is not Outcome.PLAYING:
        return

    _follow(context, events)
    _sync_weather(context, events)
    _expire_modifiers(context)
    _advance_quests(context, events)
    if _judge(context, events):
        return
    # A fight offers its own options through `combat.responses`, and a menu of
    # roads to walk down in the middle of one would be a lie.
    if state.pending is None and state.combat is None:
        _offer_options(context, events)
    # Last, always: the status line sits above the prompt, and computing it
    # after the menu means it describes the world the menu belongs to.
    events.append(_status(context))


def _status(context: RuleContext) -> WorldStatus:
    """Project where and when the player is, for the front-end's status line.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    WorldStatus
        The projection.
    """
    state = context.state
    clock = context.clock
    here = context.here()
    observed = context.weather()

    return WorldStatus(
        tick=state.tick,
        day=clock.day(state.tick),
        day_part=clock.day_part(state.tick),
        season=clock.season(state.tick).id,
        time=clock.clock_time(state.tick),
        location=state.location,
        place=here.name if here is not None else "",
        region=observed.region,
        weather=observed.qualified,
        sky=observed.label,
        temperature=(
            None if observed.temperature is None else round(observed.temperature, 2)
        ),
        light=round(context.light(), 4),
        indoors=observed.sheltered,
        exposure=round(state.protagonist.exposure, 4),
    )


def _expire_modifiers(context: RuleContext) -> None:
    """Drop temporary modifiers whose time has run out.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    """
    tick = context.state.tick
    for entity in context.state.entities.values():
        entity.modifiers = [
            modifier
            for modifier in entity.modifiers
            if modifier.expires_at_tick is None or modifier.expires_at_tick > tick
        ]


def _advance_quests(context: RuleContext, events: list[Event]) -> None:
    """Move every active quest along, and fail the ones that have run out.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    for quest_id in sorted(state.quests):
        progress = state.quests[quest_id]
        if progress.status is not QuestStatus.ACTIVE or progress.stage is None:
            continue
        quest = _quest(quest_id, context)
        stages = {stage.id: stage for stage in quest.stages}
        stage = stages.get(progress.stage)
        if stage is None:
            continue

        if stage.fail and all_hold(stage.fail, context):
            progress.status = QuestStatus.FAILED
            events.append(QuestUpdated(quest_id, "failed", progress.stage))
            outcome = apply_all(quest.on_fail, context, source=quest_id)
            events.extend(outcome.events)
            if _settle(outcome, context, events):
                return
            for queued in outcome.play:
                _run_scene(queued, context, events)
            continue

        if not all_hold(stage.complete, context):
            continue

        order = [entry.id for entry in quest.stages]
        position = order.index(progress.stage)
        if position + 1 < len(order):
            progress.stage = order[position + 1]
            journal = stages[progress.stage].journal
            events.append(QuestUpdated(quest_id, "active", progress.stage, journal))
            entered = apply_all(
                stages[progress.stage].on_enter, context, source=quest_id
            )
            events.extend(entered.events)
            if _settle(entered, context, events):
                return
        else:
            progress.status = QuestStatus.COMPLETE
            events.append(QuestUpdated(quest_id, "complete", progress.stage))
            outcome = apply_all(quest.on_complete, context, source=quest_id)
            events.extend(outcome.events)
            if _settle(outcome, context, events):
                return
            for queued in outcome.play:
                _run_scene(queued, context, events)


def _judge(context: RuleContext, events: list[Event]) -> bool:
    """Decide whether the game has been won or lost.

    Lose conditions are judged first: a game that is simultaneously won and
    lost is a content bug, and dying on the doorstep of victory is the reading
    a player will expect.

    The two lists are combined differently, and deliberately. **Winning needs
    all of them** — a list of win conditions is a list of objectives, and a
    game you win having done one of three things is not what an author writing
    three of them meant. **Losing needs any of them** — a list of lose
    conditions is a list of ways to fail, and requiring a player to run out of
    hitpoints *and* miss the deadline simultaneously makes both of them
    decorative.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game ended.
    """
    game = context.game
    if game.lose_conditions and any(
        holds(condition, context) for condition in game.lose_conditions
    ):
        _end(context, "lost", "lost on the conditions the game sets", events)
        return True
    if game.win_conditions and all(
        holds(condition, context) for condition in game.win_conditions
    ):
        _end(context, "won", "won on the conditions the game sets", events)
        return True
    return False


def _end(context: RuleContext, outcome: str, reason: str, events: list[Event]) -> None:
    """End the playthrough and play its closing scene.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    outcome : str
        `won` or `lost`.
    reason : str
        What ended it.
    events : list of Event
        Accumulator.
    """
    state = context.state
    state.outcome = Outcome.WON if outcome == "won" else Outcome.LOST
    state.ended_because = reason
    events.append(GameOver(outcome, reason))

    closing = context.game.on_win if outcome == "won" else context.game.on_lose
    if closing is not None:
        _run_scene(context.qualify(closing, "scenes"), context, events)


def _offer_options(context: RuleContext, events: list[Event]) -> None:
    """Offer everything the player can do from here.

    Scenes attached to this place and the things in it, then the ways out. The
    engine builds the menu rather than the front-end, so a terminal and a
    browser offer the same things in the same order — and so a replay of an
    action log means the same thing in both.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    here = _location(state.location, context)
    if here is None:
        return

    options: list[PendingChoice] = []
    if _merchant(context) is not None:
        # A stall takes the whole menu over. Standing at a counter and being
        # offered the north road in the same list is not what haggling over
        # grain feels like, and the way out of it is the last option.
        _show_stall(context, events)
        _offer_stall(context, options)
    else:
        for scene_ref in here.scenes:
            _offer_scene(scene_ref, context, options)
        for entity in state.here():
            for scene_ref in context.definition(entity).scenes:
                _offer_scene(scene_ref, context, options)
            _offer_stallholder(entity, context, options)

        _offer_journey(context, options)

        for way in here.exits:
            if not all_hold(way.when, context):
                continue
            if way.hidden_until and not all_hold(way.hidden_until, context):
                continue
            destination = context.qualify(way.to, "locations")
            target = _location(destination, context)
            label = way.label or f"Travel to {target.name if target else destination}"
            options.append(PendingChoice(prompt=label, travel=destination))

        # Last, because talking to people and walking down roads is what a
        # player came here to do and eating the bread is not. A UI with an
        # inventory panel will show these somewhere else entirely; the menu
        # is what a terminal has.
        for item_id, definition in usable(context):
            options.append(PendingChoice(prompt=f"Use {definition.name}", use=item_id))

    state.pending = PendingChoices(OPTIONS_MENU, tuple(options))
    events.append(
        ChoicesOffered(
            OPTIONS_MENU,
            tuple(
                ChoiceOffered(option.prompt, option.available, option.hint)
                for option in options
            ),
        )
    )


def _offer_stallholder(
    entity: EntityState, context: RuleContext, options: list[PendingChoice]
) -> None:
    """Offer to deal with somebody here who keeps a market.

    Only where the market model is on. A `simple` economy prices from an
    item's `baseValue` and buys and sells through authored scenes, and a
    stall offering supply-and-demand prices beside them would be two
    economies in one game.

    Parameters
    ----------
    entity : EntityState
        Somebody standing here.
    context : RuleContext
        The playthrough.
    options : list of PendingChoice
        The menu being built.
    """
    if context.game.rules.economy != "market":
        return
    block = market_trade.merchant_at(context, entity)
    if block is None or market_trade.look(context, entity) is None:
        return
    name = context.definition(entity).name
    options.append(
        PendingChoice(
            prompt=block.prompt or f"Trade with {name}",
            trade=entity.instance_id,
        )
    )


def _offer_journey(context: RuleContext, options: list[PendingChoice]) -> None:
    """Offer to carry on, or turn round, when a journey was interrupted.

    Both are ways out of a waypoint, and a waypoint usually has no exits of
    its own — the middle of a bridge is not a place with roads leading off it.
    Without these the player would be stranded on the road they stopped on.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    options : list of PendingChoice
        The menu being built.
    """
    journey = context.state.journey
    if journey is None:
        return
    for way, where in (("onward", journey.destination), ("back", journey.origin)):
        target = _location(where, context)
        name = target.name if target is not None else where
        options.append(
            PendingChoice(
                prompt=("Carry on to " if way == "onward" else "Turn back to ") + name,
                journey=way,
            )
        )


def _offer_scene(
    reference: str, context: RuleContext, options: list[PendingChoice]
) -> None:
    """Add a scene to the menu, if it is on offer at all.

    Parameters
    ----------
    reference : str
        The scene reference.
    context : RuleContext
        The playthrough.
    options : list of PendingChoice
        The menu being built.
    """
    scene_id = context.qualify(reference, "scenes")
    scene = _scene(scene_id, context)
    if not scene.visible or scene.prompt is None:
        return
    if scene.once and scene_id in context.state.played:
        return
    # `when` is deliberately not consulted here. Whether an option appears is
    # `visible`; `when` decides what happens when it is taken, and a scene with
    # an `else` is written precisely so that taking it while the condition
    # fails does something. Filtering here would make `else` unreachable.
    options.append(PendingChoice(prompt=scene.prompt, goto=scene_id))


# ── Setting up ────────────────────────────────────────────────────────────────


def _initial_state(
    library: Library,
    pack_id: str,
    game: Game,
    seed: str,
    *,
    start_at: str | None = None,
    start_tick: int | None = None,
) -> GameState:
    """Build the state a playthrough starts from.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack.
    game : Game
        Its manifest.
    seed : str
        The session seed.
    start_at : str or None
        Where to open, overriding the game's own start location.
    start_tick : int or None
        When to open, overriding the game's own start tick.

    Returns
    -------
    GameState
        A world with the protagonist standing in it.
    """
    protagonist_id = library.resolve(game.player.entity, "entities", within=pack_id)
    start = library.resolve(
        start_at or game.player.start_location, "locations", within=pack_id
    )
    opens_at = game.world.start_tick if start_tick is None else start_tick

    state = GameState(
        pack=pack_id,
        seed=seed,
        rng=RandomSource(seed),
        player=_instance_id(protagonist_id),
        tick=opens_at,
        world_tick=opens_at,
        start_tick=opens_at,
    )

    coin = _currency_of(library, game, pack_id)
    state.entities[state.player] = _instantiate(
        library, protagonist_id, start, pack_id, currency=coin
    )
    for pack in library.packs:
        for local_id, location in sorted(pack.locations.items()):
            qualified_location = f"{pack.id}:{local_id}"
            for entity_ref in location.entities:
                qualified = library.resolve(entity_ref, "entities", within=pack.id)
                instance = _instantiate(
                    library,
                    qualified,
                    qualified_location,
                    pack.id,
                    currency=coin,
                )
                state.entities[instance.instance_id] = instance
            if location.starts_discovered:
                state.revealed.add(qualified_location)
    state.revealed.add(start)
    state.visited.add(start)

    for quest_ref in game.quests:
        quest_id = library.resolve(quest_ref, "quests", within=pack_id)
        state.quests[quest_id] = QuestState(
            quest=quest_id,
            status=QuestStatus.ACTIVE,
            stage=_first_stage(library, quest_id),
            started_at_tick=state.tick,
        )
    return state


def _create_character(
    library: Library,
    pack_id: str,
    state: GameState,
    character: Character | None,
) -> str | None:
    """Make the protagonist the person the player asked for.

    Everything here writes into *state*, never into content: a background's
    `strength +8` moves the stored value the stat pipeline starts from, so the
    poacher and the farmhand share one authored protagonist and differ only in
    this playthrough (architecture boundary 1).

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack.
    state : GameState
        The opening state, mutated in place.
    character : Character or None
        What the player answered, or None to take the protagonist as authored.

    Returns
    -------
    str or None
        The qualified scene the chosen background opens on, if it names one.
        Qualified here because it is written inside the *background's* pack,
        which need not be the game's.
    """
    if character is None:
        return None

    player = state.protagonist
    definition = library.find(player.definition, "entities", within=pack_id)
    assert isinstance(definition, Entity)
    declared = definition.stats or {}

    opening: str | None = None
    background = None
    if character.background is not None:
        state.background = library.resolve(
            character.background, "backgrounds", within=pack_id
        )
        found = library.find(character.background, "backgrounds", within=pack_id)
        assert isinstance(found, Background)
        background = found
        home = state.background.split(":", 1)[0]

        for name, grant in background.stats.items():
            if name not in declared:
                # Validation reports this; play should not also crash over it.
                continue
            player.pools[name] = grant.apply(player.pools.get(name, 0.0))
        for entry in background.inventory:
            item = library.resolve(entry.item, "entities", within=home)
            player.inventory[item] = player.inventory.get(item, 0) + entry.qty
        for item, level in background.skills.items():
            player.skills[library.resolve(item, "entities", within=home)] = float(level)
        if background.grants_flag is not None:
            player.flags.add(background.grants_flag)
        if background.opening_scene is not None:
            opening = library.resolve(background.opening_scene, "scenes", within=home)

    for name, points in character.spend.items():
        if name not in declared:
            continue
        _low, high = pool_bounds(definition, name)
        player.pools[name] = min(player.pools.get(name, 0.0) + points, high)

    return opening


def _instantiate(
    library: Library,
    definition_id: str,
    location: str | None,
    within: str,
    *,
    taken: Container[str] = (),
    currency: str | None = None,
) -> EntityState:
    """Make a session instance of a content entity.

    Parameters
    ----------
    library : Library
        The loaded content.
    definition_id : str
        Qualified entity id.
    location : str or None
        Where it starts.
    within : str
        The pack whose references its inventory resolves against.
    taken : container of str
        Instance ids already in use, so a second wolf gets its own.
    currency : str or None
        Qualified id of the item trade is settled in, so a merchant with
        `capital` and no coin written into its inventory opens holding its
        capital. The same rule a market's `initial` follows against its
        `target`: a world should not open in a shortage nobody asked for, and
        a quartermaster with an empty chest on day one is one.

    Returns
    -------
    EntityState
        The instance.
    """
    definition = library.find(definition_id, "entities", within=within)
    assert isinstance(definition, Entity)

    inventory: dict[str, int] = {}
    for entry in definition.inventory:
        item = library.resolve(entry.item, "entities", within=within)
        inventory[item] = inventory.get(item, 0) + entry.qty

    merchant = definition.merchant
    if (
        currency is not None
        and merchant is not None
        and merchant.capital is not None
        and currency not in inventory
    ):
        inventory[currency] = int(merchant.capital)

    return EntityState(
        instance_id=_instance_id(definition_id, taken),
        definition=definition_id,
        location=location,
        pools=starting_pools(definition),
        inventory=inventory,
        equipment={
            slot: library.resolve(item, "entities", within=within)
            for slot, item in (definition.equipment or {}).items()
        },
        flags=set(definition.flags),
        disposition=definition.disposition,
        skills={
            library.resolve(item, "entities", within=within): float(level)
            for item, level in (definition.skills or {}).items()
        },
    )


def _currency_of(library: Library, game: Game, pack_id: str) -> str | None:
    """The item this game settles trade in, qualified.

    Parameters
    ----------
    library : Library
        The loaded content.
    game : Game
        The manifest.
    pack_id : str
        The game pack, for resolving a bare reference.

    Returns
    -------
    str or None
        The qualified item id, or None when the game names none.
    """
    named = game.rules.currency
    if named is None:
        return None
    try:
        return library.resolve(named, "entities", within=pack_id)
    except ContentError:  # pragma: no cover — validation catches these
        return None


def _instance_id(definition_id: str, taken: Container[str] = ()) -> str:
    """Name an instance after its definition, disambiguating repeats.

    The first of a kind takes its definition's id, which is what content that
    says `gorm` means and what keeps a one-of-each world readable. A second
    appends `#2` — an encounter with three wolves is three instances of one
    definition, and they need to be told apart.

    Parameters
    ----------
    definition_id : str
        Qualified entity id.
    taken : container of str
        Instance ids already in use.

    Returns
    -------
    str
        An unused instance id.
    """
    if definition_id not in taken:
        return definition_id
    number = 2
    while f"{definition_id}#{number}" in taken:
        number += 1
    return f"{definition_id}#{number}"


def _spawn(reference: str, context: RuleContext, location: str | None) -> str:
    """Put a new instance of an entity into the session.

    Parameters
    ----------
    reference : str
        The entity reference, as content wrote it.
    context : RuleContext
        The playthrough.
    location : str or None
        Where it appears.

    Returns
    -------
    str
        The new instance's id.
    """
    state = context.state
    qualified = context.qualify(reference, "entities")
    instance = _instantiate(
        context.library, qualified, location, state.pack, taken=state.entities
    )
    state.entities[instance.instance_id] = instance
    return instance.instance_id


def _opponents(
    against: tuple[str, ...], context: RuleContext
) -> tuple[list[str], set[str]]:
    """Find or make the entities a fight is against.

    An opponent already standing where the player is fights as *itself*:
    `startCombat: {against: gorm}` in the scene where Gorm has just refused
    you means that troll, with the hitpoints this playthrough has given it and
    the hundred and twenty gold in its pocket. Spawning a second Gorm instead
    would leave two of him on the bridge, which is a bug you notice in the
    menu rather than in the fight.

    Anything not already here is made, which is what an encounter on an empty
    road wants — and repeating a reference makes another, so
    `against: [wolf, wolf]` is two wolves.

    Parameters
    ----------
    against : tuple of str
        Entity references, as content wrote them.
    context : RuleContext
        The playthrough.

    Returns
    -------
    tuple
        The instance ids to fight, and which of them were newly made.
    """
    state = context.state
    actors: list[str] = []
    spawned: set[str] = set()
    for reference in against:
        standing = context.actor(reference)
        if (
            standing is not None
            and standing.location == state.location
            and standing.instance_id != state.player
            and standing.instance_id not in actors
        ):
            actors.append(standing.instance_id)
            continue
        made = _spawn(reference, context, state.location)
        actors.append(made)
        spawned.add(made)
    return actors, spawned


def _first_stage(library: Library, quest_id: str) -> str | None:
    """The stage a quest begins at.

    Parameters
    ----------
    library : Library
        The loaded content.
    quest_id : str
        Qualified quest id.

    Returns
    -------
    str or None
        The first stage's id.
    """
    pack_id, local_id = quest_id.split(":", 1)
    quest = library.pack(pack_id).quests[local_id]
    return quest.stages[0].id if quest.stages else None


# ── Small lookups ─────────────────────────────────────────────────────────────


def context_for(library: Library, state: GameState) -> RuleContext:
    """Build the context a playthrough's rules are evaluated against.

    Public because a front-end's debug overlay has to be able to ask the same
    questions the engine asks — "would this choice be available, and why not"
    — without reaching into the engine to do it. It is read-only: a context
    resolves references and reads state, and evaluating a condition through
    one changes nothing.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.

    Returns
    -------
    RuleContext
        The context.

    Raises
    ------
    ContentError
        If the state names a pack that is not a playable game.
    """
    game = library.pack(state.pack).game
    if game is None:
        raise ContentError("is not a playable game pack", pack=state.pack)
    return _context(library, state, game)


def _context(library: Library, state: GameState, game: Game) -> RuleContext:
    """Build the context rules are evaluated against.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    game : Game
        The game manifest.

    Returns
    -------
    RuleContext
        The context.
    """
    return RuleContext(
        library=library,
        state=state,
        clock=_clock(library, state.pack, game),
        game=game,
    )


def _clock(library: Library, pack_id: str, game: Game) -> Clock:
    """Build the world clock a game runs on.

    A game that names no calendar gets `standard-year`: twenty-four hours,
    four seasons, and long summer evenings. That is the same calendar
    `mace.core` ships, so naming it explicitly changes nothing.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        The game pack, for resolving the calendar reference.
    game : Game
        The game manifest.

    Returns
    -------
    Clock
        The clock.
    """
    calendar = STANDARD_YEAR
    if game.world.calendar is not None:
        found = library.find(game.world.calendar, "calendars", within=pack_id)
        assert isinstance(found, Calendar)
        calendar = found
    return Clock.for_season(
        game.world.minutes_per_tick, calendar, game.world.start_season
    )


def _advance(context: RuleContext, ticks: int, events: list[Event]) -> None:
    """Move the world clock forward, a tick at a time, and say so.

    A tick at a time because a place can have an encounter table too: a
    dungeon corridor the player waits in is as good a place to be found as a
    road. Something turning up cuts the wait short — an ambush is not
    something you sleep through — and the elapsed time reported is what
    actually elapsed.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    ticks : int
        How far to move.
    events : list of Event
        Accumulator.
    """
    if ticks <= 0:
        return
    state = context.state
    for passing in range(1, ticks + 1):
        state.tick += 1
        _sync_weather(context, events)
        if _encounters(context, events) or state.pending is not None:
            # Something found the player standing still. The rest of the wait
            # does not happen: an ambush is not something you sleep through.
            _announce_time(context, passing, events)
            return
    _announce_time(context, ticks, events)


def _tick(context: RuleContext, events: list[Event]) -> None:
    """Advance the world exactly one tick, without announcing it.

    A journey walks tick by tick so the weather can change under the player,
    but a `world.time` event per leg is noise: the front-end wants to know
    that three hours went by, not six times that half an hour did.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    context.state.tick += 1
    _sync_weather(context, events)


def _announce_time(context: RuleContext, ticks: int, events: list[Event]) -> None:
    """Report that the clock moved.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    ticks : int
        How far it moved.
    events : list of Event
        Accumulator.
    """
    state = context.state
    events.append(
        TimePassed(
            tick=state.tick,
            day=context.clock.day(state.tick),
            day_part=context.clock.day_part(state.tick),
            season=context.clock.season(state.tick).id,
            elapsed=ticks,
        )
    )


def _sync_weather(context: RuleContext, events: list[Event]) -> None:
    """Bring the whole world up to now, and report what the player can see.

    The one place the world is stepped. Conditions and descriptions only ever
    read, so a question about the world cannot change it — which is what lets
    the same action log replay to the same events.

    What is narrated is deliberately narrower than what happened. Fronts move
    across the whole map; the player learns about the one heading their way,
    once, as an omen, and about the weather it eventually brings. There is no
    system message and no pressure bar.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    changes = advance(context.library, state, context.clock, state.pack)
    _world_events(context, events, changes.ticks)
    _expire_modifiers(context)
    environment.apply(context, events, ticks=changes.ticks)

    region = region_of(
        context.library,
        state.pack,
        context.here(),
        context.game.world.start_region,
    )
    for front in [*changes.formed, *changes.faded]:
        events.append(
            FrontMoved(
                front=front.id,
                definition=front.kind,
                phase="formed" if front in changes.formed else "faded",
                at=front.at,
                ahead=front.ahead,
                intensity=round(front.intensity, 4),
            )
        )

    if region is None:
        return

    _read_the_sky(context, region, events)

    if region not in changes.weather:
        return
    observed = context.weather()
    if observed.condition is None:
        return

    line = _first_matching(observed.condition.description, context)
    events.append(
        WeatherChanged(
            region=region,
            condition=observed.qualified or state.weather[region].condition,
            name=observed.condition.label,
            intensity=round(observed.intensity, 4),
            tags=tuple(observed.condition.tags),
            visibility=observed.condition.visibility,
            temperature=(
                None if observed.temperature is None else round(observed.temperature, 2)
            ),
            text=line.text if line is not None else None,
        )
    )


def _world_events(context: RuleContext, events: list[Event], ticks: int) -> None:
    """Move every world event along, and surface what the player can perceive.

    What is narrated is deliberately narrower than what happened. An event that
    fires two regions away does not interrupt the player; it goes into the news
    queue and arrives later, garbled, through somebody's mouth. An omen is
    ordinary narration and never a system message, because a pressure bar would
    destroy the only thing pressure events are for.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    ticks : int
        How many ticks just passed. Zero still lets a fired event resolve, but
        nothing accumulates.
    """
    for happening in world_events.step(context, ticks):
        _happened(context, happening, events)


def _happened(
    context: RuleContext, happening: world_events.Happening, events: list[Event]
) -> None:
    """Narrate one beat of a world event, or queue it as news.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    happening : Happening
        What the event did.
    events : list of Event
        Accumulator.
    """
    events.append(
        WorldEvent(
            event=happening.event,
            phase=happening.phase,
            region=happening.region,
            visible=happening.visible,
        )
    )

    lines = [_text(line) for line in happening.announce]
    if happening.visible:
        for line in lines:
            events.append(Narrated(line))
    elif happening.phase == "onset" and lines:
        # It happened whether or not anyone was watching. A world where things
        # only happen in your presence is not a world.
        world_events.queue_news(context, happening, lines[0])

    if not happening.effects:
        return
    outcome = apply_all(happening.effects, context, source=happening.event)
    events.extend(outcome.events)
    _settle(outcome, context, events)


def _text(line: Any) -> str:
    """The text of an announcement line, however the author wrote it.

    Parameters
    ----------
    line : SayLine or str
        The line.

    Returns
    -------
    str
        Its text.
    """
    return str(getattr(line, "text", line))


def _read_the_sky(context: RuleContext, region: str, events: list[Event]) -> None:
    """Narrate the omen of any front heading for the player's region.

    This is the payoff of the whole layer: a line of ordinary prose, early
    enough to act on, that lets a player decide to leave now and beat the
    storm — or wait a day and lose one. Once per front, because a warning
    repeated every tick is a notification, not an omen.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    region : str
        The region the player is in.
    events : list of Event
        Accumulator.
    """
    state = context.state
    spoken = False
    for front in state.fronts:
        if front.announced:
            continue
        if front.at == region:
            # It is already here. The weather itself is the news now.
            front.announced = True
            continue
        if front.ahead != region:
            continue
        if spoken:
            # One omen a step. Two warnings in a row read as a weather report,
            # and the front that did not get its line keeps it for next tick.
            continue

        front.announced = True
        pack_id, local_id = front.kind.split(":", 1)
        definition = context.library.pack(pack_id).weather_fronts.get(local_id)
        if not isinstance(definition, WeatherFront):
            continue
        line = _first_matching(definition.omen, context)
        if line is not None:
            events.append(Narrated(line.text))
            spoken = True


def _location(location_id: str | None, context: RuleContext) -> Location | None:
    """Look up a location by qualified id.

    Parameters
    ----------
    location_id : str or None
        The qualified id.
    context : RuleContext
        The playthrough.

    Returns
    -------
    Location or None
        The definition, or None if there is nowhere to look up.
    """
    if location_id is None:
        return None
    pack_id, local_id = location_id.split(":", 1)
    return context.library.pack(pack_id).locations.get(local_id)


def _scene(scene_id: str, context: RuleContext) -> Scene:
    """Look up a scene by qualified id.

    Parameters
    ----------
    scene_id : str
        The qualified id.
    context : RuleContext
        The playthrough.

    Returns
    -------
    Scene
        The definition.

    Raises
    ------
    RuleError
        If there is no such scene.
    """
    pack_id, local_id = scene_id.split(":", 1)
    scene = context.library.pack(pack_id).scenes.get(local_id)
    if scene is None:
        raise RuleError(f"there is no scene `{scene_id}`")
    return scene


def _quest(quest_id: str, context: RuleContext) -> Quest:
    """Look up a quest by qualified id.

    Parameters
    ----------
    quest_id : str
        The qualified id.
    context : RuleContext
        The playthrough.

    Returns
    -------
    Quest
        The definition.
    """
    pack_id, local_id = quest_id.split(":", 1)
    return context.library.pack(pack_id).quests[local_id]


def _first_matching(
    lines: tuple[DescriptionLine, ...] | None, context: RuleContext
) -> DescriptionLine | SayLine | None:
    """Pick the first description line whose conditions hold.

    Parameters
    ----------
    lines : tuple or None
        The candidate lines, in author order.
    context : RuleContext
        The playthrough.

    Returns
    -------
    DescriptionLine or None
        The line to show, or None if there are none.
    """
    for line in lines or ():
        if all_hold(line.when, context):
            return line
    return None
