"""Layer 2: what the sky is doing over each region, and how it changes.

Two mechanisms multiplied together, which is the whole design. The climate's
**seasonal weights** say what a region is *like* — an autumn lowland is mostly
overcast, with some drizzle. Its **transition matrix** says how the sky
actually *moves* — clear does not become blizzard, it becomes overcast, then
drizzle, then rain. Weights alone are a slot machine; transitions alone are a
world without seasons.

Everything here is pure and deterministic. Each region walks its own chain on
its own named stream (`weather.<region>`), so a storm over the mountains does
not shift what the lowlands were going to get, and adding a region to a map
does not change what a recorded playthrough saw anywhere else.

A region the player is not standing in is not stepped every tick — it is
fast-forwarded when something needs to look at it. That is an optimization
rather than a change of behavior: replaying the same steps from the same
stream position gives the same weather either way.

See docs/05-world-simulation.md § Layer 2 and § Layer 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from mace.content import ContentError, Library
from mace.engine.rng import RandomStream
from mace.engine.state import GameState, RegionWeather
from mace.engine.world import fronts
from mace.engine.world.clock import Clock
from mace.model import Climate, Location, Region, WeatherCondition

__all__ = [
    "DEFAULT_LAPSE_RATE",
    "Prepared",
    "Observation",
    "climate_of",
    "observe",
    "region_of",
    "sync",
]

#: Degrees lost per hundred units of elevation, unless a climate says otherwise.
DEFAULT_LAPSE_RATE = 0.65


@dataclass(frozen=True, slots=True)
class Observation:
    """The weather as it is where the player is standing.

    This is the one thing conditions, descriptions, travel, and the status
    line all read, so the awkward parts — a location's hard override, being
    indoors, a region with no climate at all — are resolved once, here, rather
    than in five places that would drift.

    Attributes
    ----------
    region : str or None
        The region observed, or None where there is no weather at all.
    condition : WeatherCondition or None
        What is happening. None where nothing is.
    qualified : str or None
        The condition's qualified content id. Carried rather than derived,
        because a location's `climate` override means what is in force is not
        always what the region's chain holds.
    intensity : float
        0 to 1. Scales `modify` and how a front-end phrases it.
    temperature : float or None
        Now, at this elevation and this hour.
    sheltered : bool
        Whether the player is indoors. Shelter suppresses the weather's stat
        effects and its bite on visibility, but not the fact of it — you can
        still hear the rain on the inn roof.
    """

    region: str | None = None
    condition: WeatherCondition | None = None
    qualified: str | None = None
    intensity: float = 0.0
    temperature: float | None = None
    sheltered: bool = False

    @property
    def id(self) -> str | None:
        """The condition's local id, as content refers to it.

        Returns
        -------
        str or None
            The id, or None when there is no weather.
        """
        return self.condition.id if self.condition is not None else None

    @property
    def label(self) -> str:
        """What to call the weather in prose.

        Returns
        -------
        str
            The condition's name, or an empty string when there is none.
        """
        return self.condition.label if self.condition is not None else ""

    @property
    def tags(self) -> tuple[str, ...]:
        """The tags in force — `wet`, `cold`, `dark`.

        Indoors suppresses them: an entity that fights better in the rain does
        not get the bonus while sitting in the inn.

        Returns
        -------
        tuple of str
            The tags, or empty when there is no weather or the player is
            under a roof.
        """
        if self.condition is None or self.sheltered:
            return ()
        return tuple(self.condition.tags)

    @property
    def visibility(self) -> float:
        """How much of the light gets through.

        Returns
        -------
        float
            0 to 1. Indoors, the sky's business is not the player's.
        """
        if self.condition is None or self.sheltered:
            return 1.0
        return self.condition.visibility

    @property
    def travel_multiplier(self) -> float:
        """How much longer a road takes in this.

        Shelter does not apply: you cannot be indoors and travelling.

        Returns
        -------
        float
            A multiplier on route ticks.
        """
        if self.condition is None:
            return 1.0
        return self.condition.travel_multiplier

    @property
    def blocks_travel(self) -> bool:
        """Whether the roads are closed.

        Returns
        -------
        bool
            True when a hurricane or a blizzard means the player must shelter.
        """
        return self.condition is not None and self.condition.blocks_travel


# ── Finding the region and climate a place belongs to ─────────────────────────


def region_of(
    library: Library, pack: str, location: Location | None, fallback: str | None
) -> str | None:
    """Which region a location's weather comes from.

    Parameters
    ----------
    library : Library
        The loaded content.
    pack : str
        The pack references resolve against.
    location : Location or None
        Where the player is.
    fallback : str or None
        `game.world.startRegion`, used by every location that names none. A
        small game gets one region's weather everywhere without saying so
        four times.

    Returns
    -------
    str or None
        Qualified region id, or None where nothing names one.
    """
    named = location.region if location is not None else None
    if named is None:
        named = fallback
    if named is None:
        return None
    try:
        return library.resolve(named, "regions", within=pack)
    except ContentError:
        return None


def climate_of(library: Library, region_id: str) -> tuple[Region, Climate | None, str]:
    """A region, the climate governing it, and the pack that climate lives in.

    The pack matters: a climate written in `fantasy.core` names its conditions
    bare, and those bare names resolve against `fantasy.core` however far
    downstream the region using it happens to be.

    Parameters
    ----------
    library : Library
        The loaded content.
    home : str
        The pack the climate was written in.

    Returns
    -------
    tuple
        The region, its climate or None when it has none — an undercity and a
        station interior are places where the sky does not apply — and the
        pack the climate was written in.
    """
    pack_id, local_id = region_id.split(":", 1)
    region = library.pack(pack_id).regions[local_id]
    if region.climate is None:
        return region, None, pack_id
    qualified = library.resolve(region.climate, "climates", within=pack_id)
    climate_pack = qualified.split(":", 1)[0]
    found = library.find(region.climate, "climates", within=pack_id)
    assert isinstance(found, Climate)
    return region, found, climate_pack


# ── Reading the weather ───────────────────────────────────────────────────────


def observe(
    library: Library,
    state: GameState,
    clock: Clock,
    pack: str,
    location: Location | None,
    fallback_region: str | None,
) -> Observation:
    """What the weather is where the player is standing.

    A location's `climate` override wins outright — it is always winter on the
    Dark Mountain — and otherwise the region's current condition holds.
    Reading never draws: the chain is advanced by `sync`, at the points where
    time moves, so that asking a condition twice cannot change the answer.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    clock : Clock
        World time, for the hour's share of today's temperature band.
    pack : str
        The pack references resolve against.
    location : Location or None
        Where the player is.
    fallback_region : str or None
        `game.world.startRegion`.

    Returns
    -------
    Observation
        The weather, resolved.
    """
    sheltered = bool(location is not None and location.indoors)
    override = location.climate if location is not None else None

    if override is not None and override.condition is not None:
        condition = _condition(library, override.condition, pack)
        if condition is not None:
            region = region_of(library, pack, location, fallback_region)
            here = state.weather.get(region or "")
            return Observation(
                region=region,
                condition=condition,
                qualified=library.resolve(
                    override.condition, "weatherConditions", within=pack
                ),
                intensity=condition.intensity_range[1],
                temperature=(
                    None if here is None else _temperature_now(here, clock, state.tick)
                ),
                sheltered=sheltered,
            )

    region_id = region_of(library, pack, location, fallback_region)
    if region_id is None:
        return Observation(sheltered=sheltered)

    here = state.weather.get(region_id)
    if here is None:
        return Observation(region=region_id, sheltered=sheltered)

    pack_id, local_id = here.condition.split(":", 1)
    return Observation(
        region=region_id,
        condition=library.pack(pack_id).weather_conditions.get(local_id),
        qualified=here.condition,
        intensity=here.intensity,
        temperature=_temperature_now(here, clock, state.tick),
        sheltered=sheltered,
    )


def _temperature_now(here: RegionWeather, clock: Clock, tick: int) -> float:
    """Interpolate today's temperature band by how much light there is.

    Coldest before dawn, warmest at noon — one line, no model of where the sun
    is, and because it falls out of the day part's own light level a world
    with a strange day gets a strange temperature curve for free.

    Parameters
    ----------
    here : RegionWeather
        The region's weather, carrying today's floor and ceiling.
    clock : Clock
        World time.
    tick : int
        Now.

    Returns
    -------
    float
        The temperature now.
    """
    return here.low + (here.high - here.low) * clock.light(tick)


def _condition(library: Library, reference: str, pack: str) -> WeatherCondition | None:
    """Resolve a weather condition reference.

    Parameters
    ----------
    library : Library
        The loaded content.
    reference : str
        As the author wrote it.
    pack : str
        The pack it was written in.

    Returns
    -------
    WeatherCondition or None
        The condition, or None if it names nothing.
    """
    try:
        found = library.find(reference, "weatherConditions", within=pack)
    except ContentError:
        return None
    assert isinstance(found, WeatherCondition)
    return found


# ── Stepping the chain ────────────────────────────────────────────────────────


#: A region resolved once: itself, its climate, and the pack that climate was
#: written in. The driver builds these at the top of a tick and hands them back
#: down, because resolving a climate reference per region per tick is the one
#: cost in this layer that would actually add up.
Prepared = tuple[Region, "Climate | None", str]


def sync(
    library: Library,
    state: GameState,
    clock: Clock,
    pack: str,
    region_id: str,
    prepared: Prepared | None = None,
) -> bool:
    """Bring one region's weather up to the current tick.

    Called where time moves and where the player arrives somewhere, never from
    a condition — a question about the world must not change it, or asking
    twice would give two answers and replay would stop working.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough. The region's weather is created or advanced in place.
    clock : Clock
        World time.
    pack : str
        The pack references resolve against.
    region_id : str
        Qualified region id.
    prepared : tuple or None
        The region, its climate, and the climate's pack, already resolved.

    Returns
    -------
    bool
        Whether the condition in force changed. The caller narrates a change;
        weather that is doing what it was doing is not news.
    """
    region, climate, home = prepared or climate_of(library, region_id)
    if climate is None:
        return False

    here = state.weather.get(region_id)
    if here is None:
        here = _begin(library, state, clock, region, climate, region_id, home)
        state.weather[region_id] = here
        before = ""
    else:
        before = here.condition
    step = climate.step_ticks
    stream = state.rng.stream(f"weather.{region_id}")

    while here.stepped_to + step <= state.tick:
        here.stepped_to += step
        _refresh_temperature(here, stream, clock, region, climate)
        _step(here, stream, clock, home, climate, library, state, region_id)

    return here.condition != before


def _begin(
    library: Library,
    state: GameState,
    clock: Clock,
    region: Region,
    climate: Climate,
    region_id: str,
    home: str,
) -> RegionWeather:
    """Draw a region's opening weather.

    The first condition comes from the season's weights alone: there is no
    previous condition to transition from, and "what is this place like in
    autumn" is exactly the question the weights answer.

    It is drawn for the tick the *playthrough* opened on, not for now, so that
    a region first looked at on day nine gets the weather it would have had if
    it had been stepped all along. Lazy evaluation is an optimization and must
    not be a different world.

    Parameters
    ----------
    library : Library
        The loaded content.
    state : GameState
        The playthrough.
    clock : Clock
        World time.
    region : Region
        The region.
    climate : Climate
        Its climate.
    region_id : str
        Qualified region id.
    home : str
        The pack the climate was written in, which its condition references
        resolve against.

    Returns
    -------
    RegionWeather
        The region's opening weather.
    """
    stream = state.rng.stream(f"weather.{region_id}")
    season = clock.season(state.start_tick).id
    profile = climate.seasons.get(season)

    weights = dict(profile.weights) if profile is not None else {}
    if not weights:
        weights = {name: 1.0 for name in sorted(climate.transitions)}

    drawn = _pick(stream, weights)
    here = RegionWeather(
        region=region_id,
        condition="",
        stepped_to=state.start_tick,
        began_at_tick=state.start_tick,
        temperature_day=-1,
    )
    _refresh_temperature(here, stream, clock, region, climate)
    _settle(here, stream, clock, climate, home, drawn, library)
    return here


def _step(
    here: RegionWeather,
    stream: RandomStream,
    clock: Clock,
    home: str,
    climate: Climate,
    library: Library,
    state: GameState,
    region_id: str,
) -> None:
    """Take one step of the chain, or one step of a running sequence.

    Parameters
    ----------
    here : RegionWeather
        The region's weather, advanced in place.
    stream : RandomStream
        The region's stream.
    clock : Clock
        World time.
    home : str
        The pack the climate was written in.
    climate : Climate
        The climate.
    library : Library
        The loaded content.
    state : GameState
        The playthrough, for the fronts crossing the map.
    region_id : str
        Qualified region id.
    """
    if here.sequence is not None:
        _advance_sequence(here, stream, clock, climate, library, home)
        return

    started = _maybe_start_sequence(here, stream, clock, climate, library, home)
    if started:
        return

    season = clock.season(here.stepped_to).id
    bias = fronts.biases_for(library, state, region_id, here.stepped_to)
    chosen = _next_condition(here, stream, climate, season, bias, library, home)
    _settle(here, stream, clock, climate, home, chosen, library)


def _next_condition(
    here: RegionWeather,
    stream: RandomStream,
    climate: Climate,
    season: str,
    bias: dict[str, float],
    library: Library,
    home: str,
) -> str:
    """Draw what the sky becomes next.

    Three multiplications, in one place. The transition row supplies
    coherence, the season's weights supply character, and any front nearby
    supplies direction. A season that lists any weights is treated as a
    whitelist: a condition it does not mention weighs nothing, which is how a
    lowland climate keeps blizzards out of summer without a second matrix.

    Parameters
    ----------
    here : RegionWeather
        The region's weather.
    stream : RandomStream
        The region's stream.
    climate : Climate
        The climate.
    season : str
        The season now.
    bias : mapping
        Qualified condition id to the multiplier the fronts near this region
        are offering. A front over the region is what makes its storm likely;
        a front one region away is the foreshadowing.
    library : Library
        The loaded content.
    home : str
        The pack the climate was written in.

    Returns
    -------
    str
        The chosen condition's local reference, as the climate wrote it.
    """
    _pack, current = here.condition.split(":", 1)
    row = climate.transitions.get(current)
    if not row:
        return current

    profile = climate.seasons.get(season)
    seasonal = profile.weights if profile is not None else {}

    weights = {
        candidate: weight
        * (seasonal.get(candidate, 0.0) if seasonal else 1.0)
        * bias.get(_qualify(library, home, candidate), 1.0)
        for candidate, weight in row.items()
    }
    if not any(value > 0 for value in weights.values()):
        # The season rules out everything this condition could become. Staying
        # put is the honest answer, and it is what a becalmed sky does anyway.
        return current
    return _pick(stream, weights)


def _settle(
    here: RegionWeather,
    stream: RandomStream,
    clock: Clock,
    climate: Climate,
    home: str,
    reference: str,
    library: Library,
) -> None:
    """Put a drawn condition in force, freezing it first if it is cold enough.

    The same wet draw is rain above freezing and snow below, which is how one
    transition matrix covers a whole year.

    Parameters
    ----------
    here : RegionWeather
        The region's weather, changed in place.
    stream : RandomStream
        The region's stream.
    clock : Clock
        World time, for the hour's share of today's temperature band.
    climate : Climate
        The climate, for its freezing point.
    home : str
        The pack the climate was written in.
    reference : str
        The condition drawn, as the climate wrote it.
    library : Library
        The loaded content.
    """
    qualified = _qualify(library, home, reference)
    condition = _look_up(qualified, library)

    temperature = _temperature_now(here, clock, here.stepped_to)
    if (
        condition is not None
        and condition.freezes_to is not None
        and temperature < climate.freezing_point
    ):
        qualified = _qualify(library, home, condition.freezes_to)
        condition = _look_up(qualified, library)

    if qualified == here.condition:
        return
    here.condition = qualified
    here.began_at_tick = here.stepped_to
    here.intensity = _draw_intensity(stream, condition)


def _maybe_start_sequence(
    here: RegionWeather,
    stream: RandomStream,
    clock: Clock,
    climate: Climate,
    library: Library,
    home: str,
) -> bool:
    """Decide whether an authored sequence takes over this step.

    A sequence's `weight` is its chance per step, not a share of anything, so
    an author writing 0.002 gets roughly one in five hundred steps and does
    not have to reason about what else is competing.

    Parameters
    ----------
    here : RegionWeather
        The region's weather.
    stream : RandomStream
        The region's stream.
    clock : Clock
        World time.
    climate : Climate
        The climate.
    library : Library
        The loaded content.
    home : str
        The pack the climate was written in.

    Returns
    -------
    bool
        Whether a sequence started.
    """
    eligible = [sequence for sequence in climate.sequences if sequence.weight > 0]
    if not eligible:
        return False

    total = min(1.0, sum(sequence.weight for sequence in eligible))
    if not stream.chance(total):
        return False

    chosen = stream.weighted([(sequence, sequence.weight) for sequence in eligible])
    here.sequence = chosen.id
    here.sequence_step = -1
    here.sequence_until = here.stepped_to
    _advance_sequence(here, stream, clock, climate, library, home)
    return True


def _advance_sequence(
    here: RegionWeather,
    stream: RandomStream,
    clock: Clock,
    climate: Climate,
    library: Library,
    home: str,
) -> None:
    """Move a running sequence along, ending it when it runs out.

    Parameters
    ----------
    here : RegionWeather
        The region's weather, changed in place.
    stream : RandomStream
        The region's stream.
    clock : Clock
        World time.
    climate : Climate
        The climate.
    library : Library
        The loaded content.
    home : str
        The pack the climate was written in.
    """
    if here.stepped_to < here.sequence_until:
        return

    sequence = next(
        (item for item in climate.sequences if item.id == here.sequence), None
    )
    if sequence is None:
        here.sequence = None
        return

    here.sequence_step += 1
    if here.sequence_step >= len(sequence.steps):
        here.sequence = None
        here.sequence_step = 0
        return

    step = sequence.steps[here.sequence_step]
    here.sequence_until = here.stepped_to + step.ticks
    _settle(here, stream, clock, climate, home, step.condition, library)


def _refresh_temperature(
    here: RegionWeather,
    stream: RandomStream,
    clock: Clock,
    region: Region,
    climate: Climate,
) -> None:
    """Draw today's temperature band, once a day, per region.

    Parameters
    ----------
    here : RegionWeather
        The region's weather, changed in place.
    stream : RandomStream
        The region's stream.
    clock : Clock
        World time.
    region : Region
        The region, for its elevation.
    climate : Climate
        The climate, for the season's band and its lapse rate.
    """
    day = clock.day(here.stepped_to)
    if day == here.temperature_day:
        return
    here.temperature_day = day

    profile = climate.seasons.get(clock.season(here.stepped_to).id)
    band = profile.temperature if profile is not None else None
    if band is None:
        here.low = here.high = 0.0
        return

    span = band.max - band.min
    first = band.min + stream.fraction() * span
    second = band.min + stream.fraction() * span
    lapse = region.elevation / 100.0 * climate.lapse_rate
    here.low = min(first, second) - lapse
    here.high = max(first, second) - lapse


def _draw_intensity(stream: RandomStream, condition: WeatherCondition | None) -> float:
    """Draw how hard it is doing whatever it is doing.

    Parameters
    ----------
    stream : RandomStream
        The region's stream.
    condition : WeatherCondition or None
        The condition, for its band.

    Returns
    -------
    float
        0 to 1.
    """
    low, high = (0.0, 1.0) if condition is None else condition.intensity_range
    return low + stream.fraction() * (high - low)


def _pick(stream: RandomStream, weights: dict[str, float]) -> str:
    """Choose one option in proportion to its weight, in a stable order.

    Parameters
    ----------
    stream : RandomStream
        The stream to draw from.
    weights : mapping
        Option to weight.

    Returns
    -------
    str
        The chosen option.
    """
    options = sorted((name, weight) for name, weight in weights.items() if weight > 0)
    if not options:
        return sorted(weights)[0]
    if len(options) == 1:
        return options[0][0]
    return stream.weighted(options)


def _qualify(library: Library, home: str, reference: str) -> str:
    """Qualify a condition reference against the pack the climate lives in.

    Parameters
    ----------
    library : Library
        The loaded content.
    home : str
        The pack the climate was written in.
    reference : str
        The reference, as the climate wrote it.

    Returns
    -------
    str
        The qualified id. A reference that names nothing is returned qualified
        against `home` anyway, so the lookup that follows can miss cleanly
        rather than raising in the middle of a tick.
    """
    try:
        return library.resolve(reference, "weatherConditions", within=home)
    except ContentError:
        return reference if ":" in reference else f"{home}:{reference}"


def _look_up(qualified: str, library: Library) -> WeatherCondition | None:
    """Find a weather condition by qualified id.

    Parameters
    ----------
    qualified : str
        The qualified id.
    library : Library
        The loaded content.

    Returns
    -------
    WeatherCondition or None
        The condition, or None when there is no such thing.
    """
    pack_id, local_id = qualified.split(":", 1)
    return library.pack(pack_id).weather_conditions.get(local_id)
