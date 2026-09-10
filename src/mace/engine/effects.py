"""Making the changes content asks for, and saying what happened.

Every effect in the vocabulary is applied here. Applying one mutates the
playthrough and returns events describing the change — the events are the only
thing a front-end sees, so an effect that changes something silently is a bug.

Three effects do not finish here, because they change what the engine does next
rather than what the world contains: `playScene`, `restart`, and `endGame`.
They are collected on the outcome for the scene runner to act on.

See docs/03-content-model.md § Conditions and effects.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from mace.content import ContentError
from mace.engine import economy
from mace.engine.conditions import RuleError, all_hold
from mace.engine.context import RuleContext
from mace.engine.events import (
    Event,
    FlagChanged,
    InventoryChanged,
    LocationRevealed,
    Moved,
    Narrated,
    NewsHeard,
    PricesShocked,
    QuestUpdated,
    RouteChanged,
    StatChanged,
    Unsupported,
    VariableChanged,
)
from mace.engine.expr import Expression
from mace.engine.state import (
    EntityState,
    FrontState,
    Modifier,
    QuestState,
    QuestStatus,
    RouteState,
    Shock,
)
from mace.engine.stats import pool_bounds
from mace.model import Effect, Quest
from mace.model.effects import (
    AdjustStat,
    AdvanceQuest,
    AdvanceTime,
    ApplyModifier,
    AttachAlly,
    CloseRoute,
    DealDamage,
    DismissAlly,
    FireEvent,
    ItemTransfer,
    MarketShock,
    MoveActor,
    NoArguments,
    OpenRoute,
    PlayScene,
    Rest,
    Reveal,
    SayEffect,
    SetDisposition,
    SetFlag,
    SetLight,
    SetPressure,
    SetRouteTicks,
    SetStat,
    SetVar,
    SpawnEntity,
    SpawnFront,
    StartCombat,
    TellNews,
    TransferContents,
)

__all__ = ["EffectOutcome", "apply", "apply_all"]


@dataclass(slots=True)
class EffectOutcome:
    """What applying some effects did, and what it asked the runner to do next.

    Attributes
    ----------
    events : list of Event
        Everything that happened, in order.
    play : list of str
        Qualified ids of scenes to run once the current one finishes.
    ended : str or None
        `won` or `lost`, if an effect ended the game.
    restart : bool
        Whether an effect asked for a new playthrough.
    elapsed : int
        Ticks the effects asked the clock to move. Requested rather than done
        here, because moving the clock means moving the *world* — weather,
        fronts, encounters — and that machinery lives in the step runner. An
        effect that advanced the tick counter on its own would skip all of it.
    rest : Rest or None
        A rest to carry out once the time has passed. After, not before: a
        player who sits out a blizzard in the open should find it has not
        helped very much.
    fire : list of str
        World events an effect asked to happen now. Requested rather than
        done here for the same reason as time: firing one runs its own
        announcements and effects, and that is the step runner's loop.
    pressure : list of tuple
        Pressure events an effect nudged, and where to.
    combat : StartCombat or None
        A fight an effect asked for. Requested rather than started here for
        the same reason as time: a fight takes over the loop until it is
        over, and the loop belongs to the step runner.
    """

    events: list[Event] = field(default_factory=list)
    play: list[str] = field(default_factory=list)
    ended: str | None = None
    restart: bool = False
    elapsed: int = 0
    rest: Rest | None = None
    fire: list[str] = field(default_factory=list)
    pressure: list[tuple[str, float]] = field(default_factory=list)
    combat: StartCombat | None = None


def apply_all(
    effects: Sequence[Effect], context: RuleContext, *, source: str = ""
) -> EffectOutcome:
    """Apply a list of effects in order.

    Order is semantics: taking ten gold and then checking whether the player
    can afford something is a different scene from doing it the other way
    round, and replay depends on it staying fixed.

    Parameters
    ----------
    effects : sequence of Effect
        The effects to apply.
    context : RuleContext
        The playthrough.
    source : str
        What is applying them, for modifier bookkeeping.

    Returns
    -------
    EffectOutcome
        Events and any requests for the runner.
    """
    outcome = EffectOutcome()
    for effect in effects:
        apply(effect, context, outcome, source=source)
    return outcome


def apply(
    effect: Effect,
    context: RuleContext,
    outcome: EffectOutcome,
    *,
    source: str = "",
) -> None:
    """Apply one effect, adding to an outcome.

    Parameters
    ----------
    effect : Effect
        What to do.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator for events and runner requests.
    source : str
        What is applying it.

    Raises
    ------
    RuleError
        If the effect refers to something that is not there.
    """
    payload = effect.payload
    state = context.state

    if isinstance(payload, AdjustStat):
        actor = _actor(payload.actor, context)
        delta = _number(payload.delta, context, "adjustStat.delta")
        _write_stat(actor, payload.stat, delta, context, outcome, payload.reason)
        return

    if isinstance(payload, SetStat):
        actor = _actor(payload.actor, context)
        target = _number(payload.value, context, "setStat.value")
        current = actor.pools.get(payload.stat, 0.0)
        _write_stat(actor, payload.stat, target - current, context, outcome, None)
        return

    if isinstance(payload, ApplyModifier):
        actor = _actor(payload.actor, context)
        actor.modifiers.append(
            Modifier(
                stat=payload.stat,
                add=float(payload.add or 0.0),
                mult=float(payload.mult if payload.mult is not None else 1.0),
                label=payload.label or "",
                source=source,
                expires_at_tick=state.tick + payload.ticks,
            )
        )
        return

    if isinstance(payload, ItemTransfer):
        actor = _actor(payload.actor, context)
        item = _item(payload.item, context)
        delta = payload.qty if effect.tag == "giveItem" else -payload.qty
        _move_items(actor, item, delta, outcome)
        return

    if isinstance(payload, TransferContents):
        _transfer_all(
            _actor(payload.source, context), _actor(payload.target, context), outcome
        )
        return

    if isinstance(payload, MoveActor):
        actor = _actor(payload.actor, context)
        destination = _reference(payload.to, "locations", context)
        origin, actor.location = actor.location, destination
        state.revealed.add(destination)
        if actor.instance_id == state.player:
            outcome.events.append(Moved(origin, destination))
        return

    if isinstance(payload, SetFlag):
        actor = _actor(payload.entity, context)
        if payload.value:
            actor.flags.add(payload.flag)
        else:
            actor.flags.discard(payload.flag)
        outcome.events.append(
            FlagChanged(actor.instance_id, payload.flag, payload.value)
        )
        return

    if isinstance(payload, SetDisposition):
        actor = _actor(payload.actor, context)
        actor.disposition = payload.to
        return

    if isinstance(payload, SetVar):
        raw = payload.value
        value = (
            _evaluate(raw, context, "setVar.value")
            if isinstance(raw, Expression)
            else raw
        )
        state.variables[payload.name] = value
        outcome.events.append(VariableChanged(payload.name, value))
        return

    if isinstance(payload, Reveal):
        location = _reference(payload.location, "locations", context)
        if location not in state.revealed:
            state.revealed.add(location)
            outcome.events.append(LocationRevealed(location))
        return

    if isinstance(payload, SayEffect):
        for line in payload.lines:
            if all_hold(line.when, context):
                outcome.events.append(Narrated(line.text, line.pause))
        return

    if isinstance(payload, AdvanceQuest):
        _advance_quest(payload, context, outcome)
        return

    if isinstance(payload, AdvanceTime):
        outcome.elapsed += payload.ticks
        return

    if isinstance(payload, Rest):
        if "rest" not in context.game.rules.survival:
            outcome.events.append(Unsupported("resting", "this game has it off"))
            return
        outcome.elapsed += payload.ticks
        outcome.rest = payload
        return

    if isinstance(payload, SpawnEntity):
        from mace.engine.step import spawn  # noqa: PLC0415 — the runner owns it

        where = (
            state.location
            if payload.at is None
            else _reference(payload.at, "locations", context)
        )
        spawn(payload.entity, context, where, transient=payload.transient)
        return

    if isinstance(payload, MarketShock):
        _shock(payload, context, outcome)
        return

    if isinstance(payload, CloseRoute | OpenRoute):
        route = _reference(payload.route, "routes", context)
        _settle_trade(context, route)
        road = state.routes.setdefault(route, RouteState(route=route))
        if isinstance(payload, CloseRoute):
            road.closed = True
            road.permanent = payload.permanent
            road.reason = payload.reason
        else:
            road.closed = False
            road.permanent = False
            road.reason = None
        outcome.events.append(
            RouteChanged(
                route, closed=road.closed, ticks=road.ticks, reason=road.reason
            )
        )
        return

    if isinstance(payload, SetRouteTicks):
        route = _reference(payload.route, "routes", context)
        _settle_trade(context, route)
        road = state.routes.setdefault(route, RouteState(route=route))
        road.ticks = payload.ticks
        outcome.events.append(
            RouteChanged(
                route, closed=road.closed, ticks=road.ticks, reason=road.reason
            )
        )
        return

    if isinstance(payload, SetLight):
        state.light_override = payload.light
        return

    if isinstance(payload, SpawnFront):
        _spawn_front(payload, context)
        return

    if isinstance(payload, DealDamage):
        _damage(payload, context, outcome)
        return

    if isinstance(payload, FireEvent):
        outcome.fire.append(_event_reference(payload.event, context))
        return

    if isinstance(payload, SetPressure):
        outcome.pressure.append(
            (_event_reference(payload.event, context), payload.value)
        )
        return

    if isinstance(payload, TellNews):
        _tell_news(payload, context, outcome)
        return

    if isinstance(payload, PlayScene):
        outcome.play.append(_reference(payload.scene, "scenes", context))
        return

    if isinstance(payload, NoArguments):
        if effect.tag == "restart":
            outcome.restart = True
        else:
            outcome.ended = "lost" if state.outcome.value == "lost" else "won"
        return

    if isinstance(payload, StartCombat):
        if outcome.combat is not None:
            raise RuleError(
                "two fights were asked for in one list of effects; the second "
                "would start before the first had finished"
            )
        outcome.combat = payload
        return

    if isinstance(payload, AttachAlly | DismissAlly):
        _set_ally(payload, context, outcome, joining=isinstance(payload, AttachAlly))
        return

    raise RuleError(f"effect `{effect.tag}` is not applicable yet")


def _set_ally(
    payload: AttachAlly | DismissAlly,
    context: RuleContext,
    outcome: EffectOutcome,
    *,
    joining: bool,
) -> None:
    """Take somebody along, or send them home.

    An ally is an ordinary entity with a flag on it: they follow the player
    from place to place and fight on the player's side, on their own combat
    profile. That is deliberately cheap — combat already resolves M-vs-N and
    `disposition` already exists, so an escort needs no new machinery
    (docs/13-open-questions.md § 2).

    Parameters
    ----------
    payload : AttachAlly or DismissAlly
        Who, and until when.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator.
    joining : bool
        Whether they are joining rather than leaving.

    Raises
    ------
    RuleError
        If the entity named is not in the session.
    """
    entity = context.actor(payload.entity)
    if entity is None:
        raise RuleError(f"`{payload.entity}` is not here to travel with you")
    if entity.ally == joining:
        return
    entity.ally = joining
    entity.ally_until = payload.until if isinstance(payload, AttachAlly) else None
    if joining:
        entity.location = context.state.location
    outcome.events.append(
        FlagChanged(entity=entity.instance_id, flag="ally", value=joining)
    )


def _write_stat(
    actor: EntityState,
    stat: str,
    delta: float,
    context: RuleContext,
    outcome: EffectOutcome,
    reason: str | None,
) -> None:
    """Move a stat by a delta, clamped, and report what actually happened.

    A heal that overflows the cap reports the healing that landed, not the
    healing that was asked for — a front-end showing "+20" when 3 went in is
    lying to the player.

    Parameters
    ----------
    actor : EntityState
        Whose stat.
    stat : str
        Which stat.
    delta : float
        How much to move it.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator.
    reason : str or None
        What did it.

    Raises
    ------
    RuleError
        If the entity has no such stat.
    """
    definition = context.definition(actor)
    if stat not in (definition.stats or {}):
        raise RuleError(f"`{definition.id}` has no stat `{stat}`")

    low, high = pool_bounds(definition, stat)
    before = actor.pools.get(stat, 0.0)
    after = min(max(before + delta, low), high)
    actor.pools[stat] = after
    if after != before:
        outcome.events.append(
            StatChanged(actor.instance_id, stat, after - before, after, reason)
        )


def _move_items(
    actor: EntityState, item: str, delta: int, outcome: EffectOutcome
) -> None:
    """Add to or take from an inventory, never below zero.

    Parameters
    ----------
    actor : EntityState
        Whose inventory.
    item : str
        Qualified item id.
    delta : int
        How many to add, or remove as a negative.
    outcome : EffectOutcome
        Accumulator.
    """
    before = actor.inventory.get(item, 0)
    after = max(0, before + delta)
    if after:
        actor.inventory[item] = after
    else:
        actor.inventory.pop(item, None)
    if after != before:
        outcome.events.append(
            InventoryChanged(actor.instance_id, item, after - before, after)
        )


def _transfer_all(
    source: EntityState, target: EntityState, outcome: EffectOutcome
) -> None:
    """Move everything one entity holds into another.

    Parameters
    ----------
    source, target : EntityState
        Where the items come from and go to.
    outcome : EffectOutcome
        Accumulator.
    """
    for item, quantity in sorted(source.inventory.items()):
        _move_items(source, item, -quantity, outcome)
        _move_items(target, item, quantity, outcome)


def _advance_quest(
    payload: AdvanceQuest, context: RuleContext, outcome: EffectOutcome
) -> None:
    """Start a quest, or move it to a stage.

    Parameters
    ----------
    payload : AdvanceQuest
        Which quest, and optionally which stage.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator.

    Raises
    ------
    RuleError
        If the quest or stage does not exist.
    """
    quest_id = _reference(payload.quest, "quests", context)
    definition = context.library.find(
        payload.quest, "quests", within=context.state.pack
    )
    assert isinstance(definition, Quest)
    stages = definition.stages
    stage_ids = [stage.id for stage in stages]

    progress = context.state.quests.setdefault(quest_id, QuestState(quest=quest_id))
    if payload.stage is not None:
        if payload.stage not in stage_ids:
            raise RuleError(f"`{quest_id}` has no stage `{payload.stage}`")
        stage = payload.stage
    elif progress.stage is None:
        stage = stage_ids[0]
    else:
        position = stage_ids.index(progress.stage)
        if position + 1 >= len(stage_ids):
            progress.status = QuestStatus.COMPLETE
            outcome.events.append(QuestUpdated(quest_id, "complete", progress.stage))
            return
        stage = stage_ids[position + 1]

    if progress.started_at_tick is None:
        progress.started_at_tick = context.state.tick
    progress.stage = stage
    progress.status = QuestStatus.ACTIVE
    journal = next(entry.journal for entry in stages if entry.id == stage)
    outcome.events.append(QuestUpdated(quest_id, "active", stage, journal))


def _actor(reference: str, context: RuleContext) -> EntityState:
    """Find an entity, or say clearly that it is not here.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    EntityState
        The instance.

    Raises
    ------
    RuleError
        If nothing matches.
    """
    actor = context.actor(reference)
    if actor is None:
        raise RuleError(f"`{reference}` is not an entity in this playthrough")
    return actor


def _item(reference: str, context: RuleContext) -> str:
    """Qualify an item reference.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    return _reference(reference, "entities", context)


def _reference(reference: str, collection: str, context: RuleContext) -> str:
    """Qualify any reference, turning a content error into a rule error.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    collection : str
        Which collection it points into.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names nothing.
    """
    try:
        return context.qualify(reference, collection)
    except ContentError as error:
        raise RuleError(error.message) from error


def _shock(payload: MarketShock, context: RuleContext, outcome: EffectOutcome) -> None:
    """Put a pressure on prices somewhere, and start its clock.

    The same rule a road change follows, for the same reason: a shock changes
    what every crossed tick would have been worth, so the ticks *before* it
    have to be committed first. Otherwise a market nobody had looked at since
    the world began would find the siege had been on all along.

    Everything it touches is caught up rather than only the region it names,
    because a shock on one end of a road changes what crosses that road — and
    the group is the unit that moves together.

    Parameters
    ----------
    payload : MarketShock
        What the author asked for.
    context : RuleContext
        The playthrough. The shock is recorded and the markets caught up.
    outcome : EffectOutcome
        Accumulator, for the event.
    """
    state = context.state
    region = (
        None
        if payload.region is None
        else _reference(payload.region, "regions", context)
    )
    market = (
        None
        if payload.market is None
        else _reference(payload.market, "markets", context)
    )
    good = None if payload.good is None else _reference(payload.good, "goods", context)

    network = economy.prepare(context.library)
    touched = [
        group
        for group in network.groups
        if any(
            _shocked(network.markets[member], region, market)
            for member in group.markets
        )
    ]
    for group in touched:
        economy.sync(state, network, group.markets[0])

    state.shocks.append(
        Shock(
            mult=payload.mult,
            from_tick=state.tick,
            decay_ticks=payload.decay_ticks,
            region=region,
            market=market,
            category=payload.category,
            good=good,
            reason=payload.reason,
        )
    )
    outcome.events.append(
        PricesShocked(
            region=region,
            market=market,
            category=payload.category,
            good=good,
            mult=payload.mult,
            ticks=payload.decay_ticks,
            reason=payload.reason,
        )
    )


def _shocked(prepared: Any, region: str | None, market: str | None) -> bool:
    """Whether one market is inside a shock's reach.

    Parameters
    ----------
    prepared : Prepared
        The market.
    region : str or None
        Qualified region id, or None for anywhere.
    market : str or None
        Qualified market id, or None for any.

    Returns
    -------
    bool
        Whether both filters let it through.
    """
    if market is not None and market != prepared.id:
        return False
    return not (region is not None and region != prepared.region)


def _settle_trade(context: RuleContext, route: str) -> None:
    """Bring the markets a road serves up to date before the road changes.

    Markets are caught up lazily, and a catch-up applies *today's* route
    states to every tick it crosses. So a pass that shuts on day fifty would,
    to a market nobody had looked at since day one, have been shut all along —
    and the player who arrives on day sixty would find shelves that never
    existed. Committing the ticks before the change is what stops that: after
    this, the span the closure applies to starts here.

    Cheap in the way that matters. This is the only place that walks the whole
    content library for markets, and it runs when a landslide falls, not every
    tick.

    Parameters
    ----------
    context : RuleContext
        The playthrough. The groups the road runs inside are advanced in place.
    route : str
        Qualified id of the route about to change.
    """
    network = economy.prepare(context.library)
    for group in network.touching(route):
        economy.sync(context.state, network, group.markets[0])


def _number(value: object, context: RuleContext, where: str) -> float:
    """Read an authored value that has to be a number.

    Parameters
    ----------
    value : object
        A literal or a parsed expression.
    context : RuleContext
        The playthrough.
    where : str
        What is asking, for the error message.

    Returns
    -------
    float
        The number.

    Raises
    ------
    RuleError
        If it is not a number.
    """
    if isinstance(value, Expression):
        value = _evaluate(value, context, where)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RuleError(f"{where} must be a number, got {value!r}")
    return float(value)


def _evaluate(expression: Expression, context: RuleContext, where: str) -> object:
    """Evaluate an expression, turning its failure into a rule error.

    Parameters
    ----------
    expression : Expression
        The parsed expression.
    context : RuleContext
        The playthrough.
    where : str
        What is asking.

    Returns
    -------
    object
        The value.

    Raises
    ------
    RuleError
        If it cannot be evaluated.
    """
    from mace.engine.expr import ExprEvaluationError

    try:
        return expression.evaluate(context.expression_context())
    except ExprEvaluationError as error:
        raise RuleError(f"{where}: {error}") from error


def _spawn_front(payload: SpawnFront, context: RuleContext) -> None:
    """Put a weather front on the map because something made one.

    An eruption's ash cloud is a front like any other: it has an origin, a
    heading, and a life, and everything downwind gets the weather it brings.

    Parameters
    ----------
    payload : SpawnFront
        What to spawn.
    context : RuleContext
        The playthrough.
    """
    from mace.engine.world import fronts, prepare  # noqa: PLC0415

    state = context.state
    kind = _reference(payload.front, "weatherFronts", context)
    origin = _reference(payload.at, "regions", context)
    definition = context.library.pack(kind.split(":", 1)[0]).weather_fronts.get(
        kind.split(":", 1)[1]
    )
    if definition is None:
        return

    known = prepare(context.library)
    heading = tuple(
        _reference(name, "regions", context) for name in payload.heading
    ) or fronts.plot(
        context.library,
        state.rng.stream(fronts.FRONT_STREAM),
        origin,
        definition,
        known,
    )

    low, high = definition.intensity_range
    state.fronts_spawned += 1
    front = FrontState(
        id=f"{kind.split(':', 1)[1]}#{state.fronts_spawned}",
        kind=kind,
        heading=heading,
        intensity=(
            payload.intensity
            if payload.intensity is not None
            else low + state.rng.stream(fronts.FRONT_STREAM).fraction() * (high - low)
        ),
        born_at_tick=state.tick,
        expires_at_tick=state.tick
        + (payload.lifespan_ticks or definition.lifespan_ticks),
        hops_at_tick=state.tick + definition.speed_ticks,
    )
    state.fronts.append(front)


def _damage(payload: DealDamage, context: RuleContext, outcome: EffectOutcome) -> None:
    """Hurt whoever an effect said to hurt.

    Parameters
    ----------
    payload : DealDamage
        Who, and how much.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator.
    """
    from mace.engine.world import region_of  # noqa: PLC0415

    state = context.state
    pool = context.game.rules.vital_pool
    targets: list[EntityState] = []

    if payload.actor is not None:
        targets.append(_actor(payload.actor, context))
    elif payload.in_region is not None:
        where = region_of(
            context.library, state.pack, context.here(), context.game.world.start_region
        )
        if where == _reference(payload.in_region, "regions", context):
            targets.append(state.protagonist)
    else:
        targets.append(state.protagonist)

    for target in targets:
        _write_stat(target, pool, -payload.amount, context, outcome, payload.reason)


def _event_reference(reference: str, context: RuleContext) -> str:
    """Qualify a world-event reference, whichever kind of event it names.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str
        The qualified id.

    Raises
    ------
    RuleError
        If it names neither kind of event.
    """
    for collection in ("celestialEvents", "pressureEvents"):
        try:
            return context.qualify(reference, collection)
        except ContentError:
            continue
    raise RuleError(f"`{reference}` is not a world event")


def _tell_news(payload: TellNews, context: RuleContext, outcome: EffectOutcome) -> None:
    """Pass on what the queue is holding, oldest first.

    News carries its age deliberately. A rumour three days old and two regions
    away arriving imperfect is free atmosphere, and it makes the player's
    information feel like a medieval world's rather than like a notification.

    Parameters
    ----------
    payload : TellNews
        How much to pass on, and how stale is too stale.
    context : RuleContext
        The playthrough.
    outcome : EffectOutcome
        Accumulator.
    """
    state = context.state
    now = context.clock.day(state.tick)
    told = 0

    for item in state.news:
        if told >= payload.count:
            break
        if item.told:
            continue
        age = now - context.clock.day(item.tick)
        if payload.max_days_old is not None and age > payload.max_days_old:
            item.told = True
            continue
        item.told = True
        told += 1
        outcome.events.append(Narrated(item.text))
        outcome.events.append(
            NewsHeard(event=item.event, days_old=age, region=item.region)
        )
