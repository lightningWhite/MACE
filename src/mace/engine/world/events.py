"""Layer 5: the world's punctuation, and the warnings that come before it.

Weather is what the world is doing. Events are the things that happen *to* it,
and the rule that governs every line here is that an event should be something
the player can see coming and make a decision about. A disaster that fires
without warning is a dice roll in a costume.

Two clocks. A **celestial** event's timing is a pure function of the calendar —
no randomness at all, not even a seed — which is exactly what makes it
knowable, and therefore plannable, and therefore worth building a quest around.
A **pressure** event carries a hidden accumulator that rises each tick, with
jitter, so that omens can narrow the window without ever closing it: you can
know it is close, never that it is Tuesday.

Both walk the same phases, and the third kind of event — triggered — is either
of these fired by an effect instead of by its own clock.

Two streams. `world.events` carries the pressure jitter and nothing else, so a
chatty omen cannot shift the eruption date; `world.omens` carries the omen
draws. That separation is what lets an author add omens to a finished event
without changing when it happens.

See docs/05-world-simulation.md § Layer 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mace.content import ContentError, Library
from mace.engine.conditions import all_hold
from mace.engine.context import RuleContext
from mace.engine.rng import RandomStream
from mace.engine.state import EventPhase, EventState, NewsItem
from mace.model import CelestialEvent, Effect, EventWhile, Omen, PressureEvent
from mace.model.text import Description

__all__ = [
    "EVENT_STREAM",
    "OMEN_STREAM",
    "Happening",
    "Standing",
    "fire",
    "queue_news",
    "set_pressure",
    "standing",
    "step",
]

#: The stream pressure jitter is drawn from. Nothing else touches it, so a
#: given seed always produces the same eruption tick however chatty the omens.
EVENT_STREAM = "world.events"

#: The stream omens are drawn from.
OMEN_STREAM = "world.omens"

#: The chance per tick that an omen shows at zero pressure, and how much
#: of the accumulator's *square* is added to it. Squared on purpose: a
#: linear ramp gives a steady drip that reads as background noise, while
#: this stays almost silent early and gets insistent near the end — which
#: is the shape of the signal the player is supposed to learn to read.
OMEN_FLOOR = 0.002
OMEN_SLOPE = 0.030

#: The smallest gap between two omens from one event. Six hours at thirty
#: minutes a tick: enough that each one is its own moment.
OMEN_GAP_TICKS = 12


@dataclass(slots=True)
class Happening:
    """One thing an event did this tick, for the caller to narrate.

    Attributes
    ----------
    event : str
        Qualified event id.
    phase : str
        Which beat of its life this was.
    announce : tuple
        Lines to narrate, if the player is somewhere they apply.
    effects : tuple
        Effects to apply.
    visible : bool
        Whether the player is somewhere this can be seen or heard. When it is
        not, the caller queues news instead of narrating.
    region : str or None
        Where it happened.
    """

    event: str
    phase: str
    announce: tuple[Any, ...] = ()
    effects: tuple[Effect, ...] = ()
    visible: bool = True
    region: str | None = None


@dataclass(slots=True)
class Standing:
    """The standing changes every active event is making, added together.

    Attributes
    ----------
    light : float or None
        An override on the sky's light. The lowest wins: two events that both
        darken the sky do not brighten it.
    weather_tags : set of str
        Added to whatever the weather already carries.
    travel_multiplier : float
        Multiplied into the roads' own.
    blocks_travel : bool
        Whether any of them has closed the roads.
    encounters : list of tuple
        Hazard tables, with the pack each was written in.
    """

    light: float | None = None
    weather_tags: set[str] = field(default_factory=set)
    travel_multiplier: float = 1.0
    blocks_travel: bool = False
    encounters: list[tuple[str, str]] = field(default_factory=list)


# ── Driving events forward ────────────────────────────────────────────────────


def step(context: RuleContext, ticks: int) -> list[Happening]:
    """Advance every world event by the ticks that just passed.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    ticks : int
        How many ticks went by. Pressure accumulates per tick; the celestial
        calendar is read once, because it is a function of the tick and not of
        how you got there.

    Returns
    -------
    list of Happening
        What happened, in the order it happened.
    """
    happenings: list[Happening] = []
    for event_id, scheduled in _celestial(context):
        happenings.extend(_step_celestial(context, event_id, scheduled))
    for event_id, building in _pressure(context):
        happenings.extend(_step_pressure(context, event_id, building, ticks))
    return happenings


def _step_celestial(
    context: RuleContext, event_id: str, definition: CelestialEvent
) -> list[Happening]:
    """Move one scheduled event to wherever the calendar says it should be.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.
    definition : CelestialEvent
        The event.

    Returns
    -------
    list of Happening
        What it did.
    """
    state = context.state
    record = state.events.setdefault(event_id, EventState(event=event_id))
    clock = context.clock
    ticks_per_day = clock.ticks_per_day

    first = (definition.phase.day - 1) * ticks_per_day
    period = definition.period.days * ticks_per_day
    since = state.tick - first
    onset = first + (since // period) * period if since >= 0 else first
    ends = onset + definition.duration_ticks

    wanted = EventPhase.DORMANT
    if onset <= state.tick < ends:
        wanted = EventPhase.ACTIVE
    elif definition.warn_ticks and 0 <= onset - state.tick <= definition.warn_ticks:
        wanted = EventPhase.BUILDING

    if wanted is record.phase:
        return []

    visible = _celestial_visible(context, definition)
    happenings: list[Happening] = []

    if wanted is EventPhase.BUILDING:
        line = _first_line(definition.warning, context)
        happenings.append(
            Happening(
                event_id,
                "building",
                announce=((line,) if line else ()),
                visible=visible,
            )
        )
    elif wanted is EventPhase.ACTIVE:
        record.onset_tick = state.tick
        record.ends_at_tick = ends
        record.fired += 1
        happenings.append(
            Happening(
                event_id,
                "onset",
                announce=definition.announce,
                effects=definition.effects,
                visible=visible,
            )
        )
    elif record.phase is EventPhase.ACTIVE:
        happenings.append(
            Happening(
                event_id,
                "aftermath",
                effects=definition.aftermath,
                visible=visible,
            )
        )

    record.phase = wanted
    return happenings


def _step_pressure(
    context: RuleContext, event_id: str, definition: PressureEvent, ticks: int
) -> list[Happening]:
    """Build one uncertain event toward its threshold, and fire it if it gets there.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.
    definition : PressureEvent
        The event.
    ticks : int
        How many ticks passed.

    Returns
    -------
    list of Happening
        What it did.
    """
    state = context.state
    record = state.events.get(event_id)
    if record is None:
        record = _seed(context, event_id, definition)
        state.events[event_id] = record

    if record.phase is EventPhase.ACTIVE:
        if record.ends_at_tick is not None and state.tick >= record.ends_at_tick:
            record.phase = EventPhase.SPENT
            return [
                Happening(
                    event_id,
                    "aftermath",
                    effects=definition.aftermath,
                    visible=_pressure_visible(context, definition),
                    region=_epicentre(context, definition),
                )
            ]
        return []

    if record.phase is EventPhase.SPENT:
        if record.fired < definition.max_per_game:
            record.phase = EventPhase.DORMANT
            record.pressure = 0.0
        return []

    if not _allowed(context, definition):
        return []

    stream = state.rng.stream(EVENT_STREAM)
    for _passing in range(ticks):
        record.pressure += _rate(context, definition, stream)
    record.pressure = min(record.pressure, definition.pressure.threshold * 1.5)

    share = record.pressure / definition.pressure.threshold
    forced = definition.latest_day is not None and (
        context.clock.day(state.tick) >= definition.latest_day
    )
    happenings: list[Happening] = []

    # The ladder, in order, at most one rung a tick. `latestDay` forces the
    # climb whatever the accumulator says, so an event bounded at both ends
    # still gets its warning beat before it happens — the player is never
    # ambushed by the backstop.
    if record.phase is EventPhase.DORMANT and (share > 0 or forced):
        record.phase = EventPhase.BUILDING

    if record.phase is EventPhase.BUILDING and (
        share >= definition.imminent_at_pressure or forced
    ):
        record.phase = EventPhase.IMMINENT
        body = definition.imminent
        happenings.append(
            Happening(
                event_id,
                "imminent",
                announce=body.announce if body else (),
                effects=body.effects if body else (),
                visible=_pressure_visible(context, definition),
                region=_epicentre(context, definition),
            )
        )
        return happenings

    if share >= 1.0 or (forced and record.phase is EventPhase.IMMINENT):
        happenings.append(_onset(context, event_id, definition, record))
        return happenings

    omen = _omen(context, definition, record, share, ticks)
    if omen is not None:
        happenings.append(
            Happening(
                event_id,
                "omen",
                announce=(omen.text,),
                visible=True,
                region=_epicentre(context, definition),
            )
        )
    return happenings


def _onset(
    context: RuleContext,
    event_id: str,
    definition: PressureEvent,
    record: EventState,
) -> Happening:
    """Fire a pressure event.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.
    definition : PressureEvent
        The event.
    record : EventState
        Its progress, updated in place.

    Returns
    -------
    Happening
        The onset beat.
    """
    state = context.state
    record.phase = EventPhase.ACTIVE
    record.pressure = 0.0
    record.onset_tick = state.tick
    record.ends_at_tick = state.tick + definition.active_ticks
    record.fired += 1
    return Happening(
        event_id,
        "onset",
        announce=definition.onset.announce,
        effects=definition.onset.effects,
        visible=_pressure_visible(context, definition),
        region=_epicentre(context, definition),
    )


def fire(context: RuleContext, event_id: str) -> list[Happening]:
    """Make an event happen now, whatever its own clock was doing.

    The third kind of event: one the story causes. Nothing else about it
    changes — it still has an active phase, still has an aftermath, and still
    leaves the world permanently different.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.

    Returns
    -------
    list of Happening
        The onset beat, or nothing if it has already fired as often as it may.
    """
    state = context.state
    definition = _find(context.library, event_id)
    if definition is None:
        return []

    record = state.events.setdefault(event_id, EventState(event=event_id))
    if isinstance(definition, CelestialEvent):
        record.phase = EventPhase.ACTIVE
        record.onset_tick = state.tick
        record.ends_at_tick = state.tick + definition.duration_ticks
        record.fired += 1
        return [
            Happening(
                event_id,
                "onset",
                announce=definition.announce,
                effects=definition.effects,
                visible=_celestial_visible(context, definition),
            )
        ]

    if record.fired >= definition.max_per_game:
        return []
    return [_onset(context, event_id, definition, record)]


def set_pressure(context: RuleContext, event_id: str, share: float) -> None:
    """Put a pressure event's accumulator where an author wants it.

    An act-two beat that leaves the simulation to deliver act three.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.
    share : float
        The new accumulator, as a share of the threshold.
    """
    definition = _find(context.library, event_id)
    if not isinstance(definition, PressureEvent):
        return
    record = context.state.events.setdefault(event_id, EventState(event=event_id))
    record.pressure = share * definition.pressure.threshold
    if record.phase is EventPhase.SPENT:
        record.phase = EventPhase.DORMANT


# ── What an active event is doing to the world ────────────────────────────────


def standing(context: RuleContext, region: str | None) -> Standing:
    """Add up every active event's standing changes where the player is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    region : str or None
        The region the player is in.

    Returns
    -------
    Standing
        The combined changes.
    """
    combined = Standing()
    for event_id, record in sorted(context.state.events.items()):
        if record.phase is not EventPhase.ACTIVE:
            continue
        definition = _find(context.library, event_id)
        if definition is None:
            continue
        block = definition.while_
        if block is None:
            continue
        if not _reaches(context, definition, region):
            continue
        _combine(combined, block, event_id)
    return combined


def _combine(into: Standing, block: EventWhile, event_id: str) -> None:
    """Fold one event's standing changes into the running total.

    Parameters
    ----------
    into : Standing
        The total, changed in place.
    block : EventWhile
        One event's changes.
    event_id : str
        Whose they are, for resolving its table's references.
    """
    if block.light is not None:
        into.light = block.light if into.light is None else min(into.light, block.light)
    into.weather_tags.update(block.weather_tags)
    into.travel_multiplier *= block.travel_multiplier
    into.blocks_travel = into.blocks_travel or block.blocks_travel
    if block.encounters is not None:
        into.encounters.append((block.encounters, event_id.split(":", 1)[0]))


# ── Which events exist, and where they reach ──────────────────────────────────


def _celestial(context: RuleContext) -> list[tuple[str, CelestialEvent]]:
    """Every celestial event in the loaded content, in a stable order.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    list of tuple
        Qualified id and definition.
    """
    found: list[tuple[str, CelestialEvent]] = []
    for pack in context.library.packs:
        for local_id in sorted(pack.celestial_events):
            found.append((f"{pack.id}:{local_id}", pack.celestial_events[local_id]))
    return found


def _pressure(context: RuleContext) -> list[tuple[str, PressureEvent]]:
    """Every pressure event in the loaded content, in a stable order.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    list of tuple
        Qualified id and definition.
    """
    found: list[tuple[str, PressureEvent]] = []
    for pack in context.library.packs:
        for local_id in sorted(pack.pressure_events):
            found.append((f"{pack.id}:{local_id}", pack.pressure_events[local_id]))
    return found


def _find(library: Library, event_id: str) -> CelestialEvent | PressureEvent | None:
    """Look up an event of either kind by qualified id.

    Parameters
    ----------
    library : Library
        The loaded content.
    event_id : str
        The qualified id.

    Returns
    -------
    CelestialEvent or PressureEvent or None
        The definition.
    """
    pack_id, local_id = event_id.split(":", 1)
    pack = library.pack(pack_id)
    return pack.celestial_events.get(local_id) or pack.pressure_events.get(local_id)


def _seed(context: RuleContext, event_id: str, definition: PressureEvent) -> EventState:
    """Draw a pressure event's starting accumulator.

    Some worlds begin closer to the edge than others, which is what makes two
    playthroughs of the same content different stories.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    event_id : str
        Qualified event id.
    definition : PressureEvent
        The event.

    Returns
    -------
    EventState
        Its opening state.
    """
    stream = context.state.rng.stream(EVENT_STREAM)
    band = definition.pressure.start
    share = band.min + stream.fraction() * (band.max - band.min)
    return EventState(event=event_id, pressure=share * definition.pressure.threshold)


def _allowed(context: RuleContext, definition: PressureEvent) -> bool:
    """Whether a pressure event may build at all right now.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.

    Returns
    -------
    bool
        Whether its window is open and its conditions hold.
    """
    day = context.clock.day(context.state.tick)
    if definition.earliest_day is not None and day < definition.earliest_day:
        return False
    return all_hold(definition.requires, context)


def _rate(
    context: RuleContext, definition: PressureEvent, stream: RandomStream
) -> float:
    """How much one tick adds to the accumulator.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.
    stream : RandomStream
        The event stream, for the jitter.

    Returns
    -------
    float
        This tick's contribution.
    """
    rate = definition.pressure.rate_per_tick
    for modifier in definition.pressure.modifiers:
        if all_hold(modifier.when, context):
            rate *= modifier.mult

    variance = definition.pressure.variance
    if variance <= 0:
        return rate
    jitter = (stream.fraction() * 2.0 - 1.0) * variance
    return max(0.0, rate * (1.0 + jitter))


def _omen(
    context: RuleContext,
    definition: PressureEvent,
    record: EventState,
    share: float,
    ticks: int,
) -> Omen | None:
    """Decide whether an omen shows this tick, and which.

    Frequency scales with the accumulator, so more omens genuinely does mean
    closer. That honesty is what makes reading them a skill rather than a
    guess — and it is why the player never sees a number.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.
    record : EventState
        Its progress.
    share : float
        How far along it is, 0 to 1.
    ticks : int
        How many ticks have gone by since the last look.

    Returns
    -------
    Omen or None
        The omen to show.
    """
    if ticks <= 0:
        return None
    if (
        record.last_omen_tick is not None
        and context.state.tick - record.last_omen_tick < OMEN_GAP_TICKS
    ):
        return None

    here = context.state.location
    region = _region_of(context, here)
    eligible = [
        omen
        for omen in definition.omens
        if share >= omen.at_pressure
        and not (omen.once and _omen_key(omen) in record.omens_seen)
        and _omen_reaches(context, definition, omen, region)
    ]
    if not eligible:
        return None

    stream = context.state.rng.stream(OMEN_STREAM)
    per_tick = OMEN_FLOOR + OMEN_SLOPE * share * share
    if not stream.chance(min(0.5, per_tick * ticks)):
        return None

    # An omen already shown weighs a quarter of what it did, so a long build
    # cycles through what the author wrote rather than repeating its favourite.
    chosen = stream.weighted(
        [
            (
                omen,
                omen.weight * (0.25 if _omen_key(omen) in record.omens_seen else 1.0),
            )
            for omen in eligible
        ]
    )
    record.omens_seen.add(_omen_key(chosen))
    record.last_omen_tick = context.state.tick
    return chosen


def _omen_key(omen: Omen) -> str:
    """A stable key for one omen, whether or not the author named it.

    Parameters
    ----------
    omen : Omen
        The omen.

    Returns
    -------
    str
        Its id, or its text.
    """
    return omen.id or omen.text


def _omen_reaches(
    context: RuleContext,
    definition: PressureEvent,
    omen: Omen,
    region: str | None,
) -> bool:
    """Whether an omen can be observed from where the player is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.
    omen : Omen
        The omen.
    region : str or None
        Where the player is.

    Returns
    -------
    bool
        Whether they can see it.
    """
    wanted = omen.regions or definition.regions
    if not wanted:
        return True
    return any(_same_region(context, name, region) for name in wanted)


def _reaches(
    context: RuleContext,
    definition: CelestialEvent | PressureEvent,
    region: str | None,
) -> bool:
    """Whether an event's standing changes apply where the player is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : CelestialEvent or PressureEvent
        The event.
    region : str or None
        Where the player is.

    Returns
    -------
    bool
        Whether it reaches them.
    """
    if isinstance(definition, CelestialEvent):
        if definition.everywhere or not definition.regions:
            return True
        return any(_same_region(context, name, region) for name in definition.regions)
    if not definition.regions:
        return True
    return any(_same_region(context, name, region) for name in definition.regions)


def _same_region(context: RuleContext, reference: str, region: str | None) -> bool:
    """Whether a region reference names the region the player is in.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    reference : str
        As the author wrote it.
    region : str or None
        The qualified region id the player is in.

    Returns
    -------
    bool
        Whether they match.
    """
    if region is None:
        return False
    try:
        return context.qualify(reference, "regions") == region
    except ContentError:
        return False


def _celestial_visible(context: RuleContext, definition: CelestialEvent) -> bool:
    """Whether a scheduled event can be seen from where the player is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : CelestialEvent
        The event.

    Returns
    -------
    bool
        Whether they would notice.
    """
    return _reaches(context, definition, _region_of(context, context.state.location))


def _pressure_visible(context: RuleContext, definition: PressureEvent) -> bool:
    """Whether an uncertain event can be seen from where the player is.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.

    Returns
    -------
    bool
        Whether they would notice.
    """
    return _reaches(context, definition, _region_of(context, context.state.location))


def _epicentre(context: RuleContext, definition: PressureEvent) -> str | None:
    """The region an event is centred on, for news and for the map.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    definition : PressureEvent
        The event.

    Returns
    -------
    str or None
        Qualified region id.
    """
    if not definition.regions:
        return None
    try:
        return context.qualify(definition.regions[0], "regions")
    except ContentError:
        return None


def _region_of(context: RuleContext, location: str | None) -> str | None:
    """Which region a location belongs to.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    location : str or None
        Qualified location id.

    Returns
    -------
    str or None
        Qualified region id.
    """
    from mace.engine.world.weather import region_of  # noqa: PLC0415

    del location
    return region_of(
        context.library,
        context.state.pack,
        context.here(),
        context.game.world.start_region,
    )


def _first_line(lines: Description | None, context: RuleContext) -> str | None:
    """The first description line whose conditions hold.

    Parameters
    ----------
    lines : Description or None
        The candidates.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str or None
        The line's text.
    """
    for line in lines or ():
        if all_hold(line.when, context):
            return str(line.text)
    return None


def queue_news(context: RuleContext, happening: Happening, text: str) -> None:
    """Put something that happened out of sight into the news queue.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    happening : Happening
        What happened.
    text : str
        The plainest telling of it.
    """
    context.state.news.append(
        NewsItem(
            event=happening.event,
            tick=context.state.tick,
            region=happening.region,
            text=text,
        )
    )
