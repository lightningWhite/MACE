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

from dataclasses import dataclass
from typing import Any

from mace.content import ContentError, Library
from mace.engine.actions import Action, Choose, Interact, Look, Travel, Wait
from mace.engine.conditions import RuleError, all_hold, holds
from mace.engine.context import RuleContext
from mace.engine.effects import EffectOutcome, apply_all
from mace.engine.events import (
    ChoiceOffered,
    ChoicesOffered,
    Event,
    GameOver,
    Moved,
    Narrated,
    QuestUpdated,
    RuleFailed,
    SceneEntered,
    TimePassed,
)
from mace.engine.rng import RandomSource
from mace.engine.state import (
    EntityState,
    GameState,
    Outcome,
    PendingChoice,
    PendingChoices,
    QuestState,
    QuestStatus,
)
from mace.engine.stats import starting_pools
from mace.engine.world import Clock
from mace.model import Calendar, Entity, Game, Location, Quest, Route, Scene
from mace.model.calendar import STANDARD_YEAR
from mace.model.text import DescriptionLine, SayLine

__all__ = ["StepResult", "begin", "step"]

#: How many scenes may follow one another through `goto` before the engine
#: decides the content is looping. Generous enough that no honest chain hits it.
MAX_SCENE_CHAIN = 128

#: The menu that is offered when nothing else is pending.
OPTIONS_MENU = ""


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


def begin(library: Library, pack_id: str, seed: str = "mace") -> StepResult:
    """Start a playthrough.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack_id : str
        Which game pack to play.
    seed : str
        The session seed. The same seed and actions replay identically.

    Returns
    -------
    StepResult
        The opening state, and everything the player sees before their first
        decision.

    Raises
    ------
    ContentError
        If the pack is not a playable game.
    """
    pack = library.pack(pack_id)
    if pack.game is None:
        raise ContentError("is not a playable game pack", pack=pack_id)

    state = _initial_state(library, pack_id, pack.game, seed)
    context = _context(library, state, pack.game)
    events: list[Event] = []

    for line in pack.game.introduction:
        events.append(Narrated(line.text, line.pause))

    where = state.location
    assert where is not None
    events.append(Moved(None, where))
    _arrive(where, context, events)
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
        fresh = begin(library, state.pack, state.seed)
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

    if isinstance(action, Look):
        state.pending = None
        _describe_here(context, events)
        return False

    if isinstance(action, Wait):
        _advance(context, action.ticks, events)
        state.pending = None
        return False

    if isinstance(action, Interact):
        state.pending = None
        return _run_scene(context.qualify(action.scene, "scenes"), context, events)

    if isinstance(action, Travel):
        state.pending = None
        return _travel(context.qualify(action.to, "locations"), context, events)

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

    if option.travel is not None:
        return _travel(option.travel, context, events)

    if option.effects:
        outcome = apply_all(option.effects, context, source=pending.scene)
        events.extend(outcome.events)
        if _settle(outcome, context, events):
            return outcome.restart

    if option.goto is not None:
        return _run_scene(option.goto, context, events)
    return False


def _travel(destination: str, context: RuleContext, events: list[Event]) -> bool:
    """Move the player along a route to another location.

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
        If there is no way from here to there.
    """
    state = context.state
    origin = state.location
    exit_taken, route = _find_exit(destination, context)
    if exit_taken is None:
        raise RuleError(f"there is no way from here to `{destination}`")

    ticks = route.ticks if route is not None else 1
    route_id = context.qualify(exit_taken.route, "routes") if exit_taken.route else None

    state.protagonist.location = destination
    state.revealed.add(destination)
    _advance(context, ticks, events)
    events.append(Moved(origin, destination, route_id, ticks))
    return _arrive(destination, context, events)


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


def _arrive(location_id: str, context: RuleContext, events: list[Event]) -> bool:
    """Describe a place and run its arrival scene.

    Parameters
    ----------
    location_id : str
        Qualified location id.
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the game should restart.
    """
    _describe_here(context, events)
    here = _location(location_id, context)
    if here is not None and here.on_arrive is not None:
        return _run_scene(context.qualify(here.on_arrive, "scenes"), context, events)
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
    """Act on an effect outcome that ends or restarts the game.

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
    return False


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
    thing that wins the game.

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

    _expire_modifiers(context)
    _advance_quests(context, events)
    if _judge(context, events):
        return
    if state.pending is None:
        _offer_options(context, events)


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
        else:
            progress.status = QuestStatus.COMPLETE
            events.append(QuestUpdated(quest_id, "complete", progress.stage))
            outcome = apply_all(quest.on_complete, context, source=quest_id)
            events.extend(outcome.events)
            for queued in outcome.play:
                _run_scene(queued, context, events)


def _judge(context: RuleContext, events: list[Event]) -> bool:
    """Decide whether the game has been won or lost.

    Lose conditions are judged first: a game that is simultaneously won and
    lost is a content bug, and dying on the doorstep of victory is the reading
    a player will expect.

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
    for conditions, outcome in (
        (game.lose_conditions, "lost"),
        (game.win_conditions, "won"),
    ):
        if conditions and all(holds(condition, context) for condition in conditions):
            _end(context, outcome, f"{outcome} on the conditions the game sets", events)
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
    for scene_ref in here.scenes:
        _offer_scene(scene_ref, context, options)
    for entity in state.here():
        for scene_ref in context.definition(entity).scenes:
            _offer_scene(scene_ref, context, options)

    for way in here.exits:
        if not all_hold(way.when, context):
            continue
        if way.hidden_until and not all_hold(way.hidden_until, context):
            continue
        destination = context.qualify(way.to, "locations")
        target = _location(destination, context)
        label = way.label or f"Travel to {target.name if target else destination}"
        options.append(PendingChoice(prompt=label, travel=destination))

    state.pending = PendingChoices(OPTIONS_MENU, tuple(options))
    events.append(
        ChoicesOffered(
            OPTIONS_MENU,
            tuple(ChoiceOffered(option.prompt) for option in options),
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


def _initial_state(library: Library, pack_id: str, game: Game, seed: str) -> GameState:
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

    Returns
    -------
    GameState
        A world with the protagonist standing in it.
    """
    protagonist_id = library.resolve(game.player.entity, "entities", within=pack_id)
    start = library.resolve(game.player.start_location, "locations", within=pack_id)

    state = GameState(
        pack=pack_id,
        seed=seed,
        rng=RandomSource(seed),
        player=_instance_id(protagonist_id),
        tick=game.world.start_tick,
    )

    state.entities[state.player] = _instantiate(library, protagonist_id, start, pack_id)
    for pack in library.packs:
        for local_id, location in sorted(pack.locations.items()):
            qualified_location = f"{pack.id}:{local_id}"
            for entity_ref in location.entities:
                qualified = library.resolve(entity_ref, "entities", within=pack.id)
                instance = _instantiate(library, qualified, qualified_location, pack.id)
                state.entities[instance.instance_id] = instance
            if location.starts_discovered:
                state.revealed.add(qualified_location)
    state.revealed.add(start)

    for quest_ref in game.quests:
        quest_id = library.resolve(quest_ref, "quests", within=pack_id)
        state.quests[quest_id] = QuestState(
            quest=quest_id,
            status=QuestStatus.ACTIVE,
            stage=_first_stage(library, quest_id),
            started_at_tick=state.tick,
        )
    return state


def _instantiate(
    library: Library, definition_id: str, location: str | None, within: str
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

    return EntityState(
        instance_id=_instance_id(definition_id),
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
    )


def _instance_id(definition_id: str) -> str:
    """Name an instance after its definition.

    Phase 1 places one of each entity, so an instance's id is its definition's.
    Spawning several — an encounter with three wolves — appends `#n`, which is
    why this is a function rather than an assumption spread through the code.

    Parameters
    ----------
    definition_id : str
        Qualified entity id.

    Returns
    -------
    str
        The instance id.
    """
    return definition_id


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
    """Move the world clock forward.

    Phase 2 turns this into the full tick pipeline — weather, fronts, world
    events, exposure — in the fixed order documented in the architecture. For
    now it moves the clock and says so.

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
    state.tick += ticks
    events.append(
        TimePassed(
            tick=state.tick,
            day=context.clock.day(state.tick),
            day_part=context.clock.day_part(state.tick),
            season=context.clock.season(state.tick).id,
            elapsed=ticks,
        )
    )


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
