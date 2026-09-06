"""World events — the punctuation in the world's background hum.

Weather is what the world is doing. Events are the things that *happen* to it:
the eclipse the priests have been counting down to, the mountain that has been
smoking for a week, the hillside above the road that is going to come down
eventually.

The design goal is the one that makes weather fronts work. An event should be
something the player can **see coming and make a decision about**. A disaster
that fires without warning is a dice roll in a costume; a disaster you can feel
building is a story.

Two kinds, and they differ in *how their timing is decided*, which is what
decides how a player can relate to them:

- **Celestial** — exactly scheduled by the calendar, so the player can know the
  date and plan around it. A deadline.
- **Pressure** — uncertain, building toward a threshold, telegraphed by omens
  whose frequency rises with the hidden accumulator. A risk assessment.

Both move through the same lifecycle, and the third kind — triggered — is just
either of these fired by an effect instead of by its own clock.

See docs/05-world-simulation.md § Layer 5.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from mace.model.base import (
    ContentModel,
    EncounterRef,
    Id,
    LocationRef,
    RegionRef,
    RouteRef,
    Tag,
)
from mace.model.conditions import Conditions
from mace.model.effects import Effect
from mace.model.text import Description, Say

__all__ = [
    "CelestialEvent",
    "EventPhaseBody",
    "EventScope",
    "EventWhile",
    "Omen",
    "Period",
    "Phase",
    "Pressure",
    "PressureEvent",
    "PressureModifier",
    "PressureStart",
]

EventScope = Literal["region", "route", "location"]


class EventWhile(ContentModel):
    """How the world is different while an event is running.

    A typed block rather than a list of effects, because everything in it is a
    *standing* change that has to be undone when the event ends — and an
    effect list is a set of one-shot changes with no way back.

    Attributes
    ----------
    light : float or None
        Overrides the sky's light entirely. Night, at noon.
    weather_tags : tuple of str
        Added to whatever the weather is already tagged with, so `env`
        responses and encounter conditions see them.
    travel_multiplier : float
        Multiplied into the roads' own.
    blocks_travel : bool
        Whether the roads close.
    encounters : str or None
        A hazard table rolled on top of the ordinary ones.
    """

    light: float | None = Field(default=None, ge=0.0, le=1.0)
    weather_tags: tuple[Tag, ...] = ()
    travel_multiplier: float = Field(default=1.0, gt=0.0)
    blocks_travel: bool = False
    encounters: EncounterRef | None = None


class EventPhaseBody(ContentModel):
    """What an event says and does at one moment of its life.

    Attributes
    ----------
    announce : Say
        Narration, for a player who is somewhere it can be seen or heard.
    effects : tuple of Effect
        One-shot changes.
    """

    announce: Say = ()
    effects: tuple[Effect, ...] = ()


class Period(ContentModel):
    """How often a celestial event comes round.

    Attributes
    ----------
    days : int
        The cycle length. Long periods make an event a once-a-campaign
        wonder that most playthroughs never see, which is a legitimate thing
        to want: set the period long and let the seed decide whether this
        world's story includes the comet.
    """

    shorthand_field: ClassVar[str] = "days"

    days: int = Field(gt=0)


class Phase(ContentModel):
    """The day a celestial event's cycle is anchored to.

    Attributes
    ----------
    day : int
        The day of its first occurrence, counting from one.
    """

    shorthand_field: ClassVar[str] = "day"

    day: int = Field(default=1, ge=1)


class CelestialEvent(ContentModel):
    """An event the calendar decides, and therefore one the player can learn.

    Timing is a pure function of the calendar — no randomness at all, not even
    a seed — which is the whole point. An almanac is worth gold and an
    astronomer is worth finding because the date is *knowable*, and a quest
    that requires the eclipse gives the player a hard deadline, a journey of
    known length, and a road with weather on it. That is a plot, produced by
    three systems agreeing with each other.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        An event to inherit from.
    period : Period
        How often it recurs.
    phase : Phase
        The day of its first occurrence.
    duration_ticks : int
        How long it lasts.
    warn_ticks : int
        How far ahead the world starts saying so.
    everywhere : bool
        Visible from anywhere, rather than only from `regions`.
    regions : tuple of str
        Where it can be seen, when it is not global.
    forecastable : bool
        Whether almanacs and astronomers can name the date.
    warning : Description or None
        Narrated once when the warning window opens.
    announce : Say
        Narrated at onset.
    while_ : EventWhile or None
        How the world is different while it runs.
    effects : tuple of Effect
        One-shot changes at onset.
    aftermath : tuple of Effect
        One-shot changes when it ends.
    """

    id: Id
    extends: Id | None = None
    name: str | None = None

    period: Period
    phase: Phase = Phase()
    duration_ticks: int = Field(default=1, gt=0)
    warn_ticks: int = Field(default=0, ge=0)

    everywhere: bool = Field(default=False, alias="global")
    regions: tuple[RegionRef, ...] = ()
    forecastable: bool = True

    warning: Description | None = None
    announce: Say = ()
    while_: EventWhile | None = Field(default=None, alias="while")
    effects: tuple[Effect, ...] = ()
    aftermath: tuple[Effect, ...] = ()

    @property
    def label(self) -> str:
        """What to call this event in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id


class PressureStart(ContentModel):
    """The band a pressure event's hidden accumulator starts within.

    Attributes
    ----------
    min, max : float
        Some worlds begin closer to the edge than others, which is what makes
        two playthroughs of the same content different stories.
    """

    min: float = Field(default=0.0, ge=0.0)
    max: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_order(self) -> PressureStart:
        """Reject a band the wrong way round."""
        if self.min > self.max:
            raise ValueError(f"start.min {self.min} is above start.max {self.max}")
        return self


class PressureModifier(ContentModel):
    """Something that makes an event build faster or slower.

    This is the strongest reason to simulate an event rather than script it: a
    quest to appease the mountain that multiplies the rate by 0.1 genuinely
    buys the valley years, and a player who performs the wrong ritual has to
    live with a four-times multiplier.

    Attributes
    ----------
    when : tuple of Condition
        When it applies.
    mult : float
        What it multiplies the rate by.
    """

    when: Conditions
    mult: float = Field(gt=0.0)


class Pressure(ContentModel):
    """A hidden accumulator, and what makes it rise.

    A flat per-tick probability is memoryless: the volcano is exactly as likely
    to erupt on day one as on day thirty, nothing can foreshadow it honestly,
    and the player can never learn anything. A rising accumulator gives the
    event a *direction*, and direction is what makes omens truthful.

    `variance` is why it is not simply a countdown. Without jitter, an
    attentive player could count ticks and derive the date, which turns the
    volcano back into a scheduled event. With it, omens narrow the window
    without ever closing it: you can know it is close, never that it is
    Tuesday.

    Attributes
    ----------
    start : PressureStart
        The band the accumulator is seeded within.
    rate_per_tick : float
        Baseline accumulation.
    variance : float
        Per-tick jitter, 0 to 1, as a fraction of the rate.
    threshold : float
        What it has to reach.
    modifiers : tuple of PressureModifier
        Season, weather, and game vars, accelerating or holding it off.
    """

    start: PressureStart = PressureStart()
    rate_per_tick: float = Field(default=0.001, ge=0.0)
    variance: float = Field(default=0.0, ge=0.0, le=1.0)
    threshold: float = Field(default=1.0, gt=0.0)
    modifiers: tuple[PressureModifier, ...] = ()


class Omen(ContentModel):
    """A sign that something is coming, and how close it has to be to show.

    Omens are the player's only information channel while an event builds, and
    their frequency scales with the current pressure — so more omens genuinely
    does mean closer. That honesty is what makes reading them a skill rather
    than a guess, and it is why the player never sees a number.

    Attributes
    ----------
    id : str or None
        Names it, for `once`.
    at_pressure : float
        The share of the threshold this omen needs before it is eligible.
    weight : float
        Relative frequency among eligible omens.
    regions : tuple of str
        Where it can be observed. Empty means the event's own regions.
    text : str
        What the player reads. Ordinary narration, never a system message.
    once : bool
        Whether it shows only once in a playthrough.
    """

    id: Id | None = None
    at_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    weight: float = Field(default=1.0, gt=0.0)
    regions: tuple[RegionRef, ...] = ()
    text: str
    once: bool = False


class PressureEvent(ContentModel):
    """An event whose timing is uncertain, and which telegraphs itself.

    Attributes
    ----------
    id, name : str
        Identity.
    extends : str or None
        An event to inherit from.
    scope : {'region', 'route', 'location'}
        What it affects. A hillside that comes down on one road is the same
        machinery as a volcano, scaled down — and most of the value is there,
        because a landslide that permanently lengthens your main road is
        twelve lines and gives the world a memory.
    regions, route, location : ...
        What it affects, per `scope`.
    epicenter : str or None
        Where it visibly originates.
    pressure : Pressure
        The accumulator.
    omens : tuple of Omen
        The player's information channel.
    imminent_at_pressure : float
        The share of the threshold at which the last warning fires. It should
        be *late*: the tension lives in the gap between probably and
        certainly.
    imminent : EventPhaseBody or None
        The unambiguous last warning. Routes close, people flee.
    onset : EventPhaseBody
        The moment itself. One dramatic beat.
    active_ticks : int
        How long the world stays disrupted afterward.
    while_ : EventWhile or None
        How it stays disrupted.
    aftermath : tuple of Effect
        **Permanent** change, and the thing that separates an event from a
        weather condition. If an event leaves nothing behind it was a
        cutscene, and should have been a scene.
    earliest_day, latest_day : int or None
        Bound the window without scheduling it. A volcano that cannot fire
        before day five and must fire by day thirty is still uncertain in the
        part that matters.
    requires : tuple of Condition or None
        Gate it on story state, so the payoff always lands.
    max_per_game : int
        How many times it may fire.
    """

    id: Id
    extends: Id | None = None
    name: str | None = None

    scope: EventScope = "region"
    regions: tuple[RegionRef, ...] = ()
    route: RouteRef | None = None
    location: LocationRef | None = None
    epicenter: LocationRef | None = None

    pressure: Pressure = Pressure()
    omens: tuple[Omen, ...] = ()

    imminent_at_pressure: float = Field(default=0.9, ge=0.0, le=1.0)
    imminent: EventPhaseBody | None = None
    onset: EventPhaseBody = EventPhaseBody()

    active_ticks: int = Field(default=0, ge=0)
    while_: EventWhile | None = Field(default=None, alias="while")
    aftermath: tuple[Effect, ...] = ()

    earliest_day: int | None = Field(default=None, ge=1)
    latest_day: int | None = Field(default=None, ge=1)
    requires: Conditions | None = None
    max_per_game: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check_window(self) -> PressureEvent:
        """Reject a window that closes before it opens."""
        if (
            self.earliest_day is not None
            and self.latest_day is not None
            and self.earliest_day > self.latest_day
        ):
            raise ValueError(
                f"earliestDay {self.earliest_day} is after latestDay "
                f"{self.latest_day}, so it could never fire"
            )
        return self

    @property
    def label(self) -> str:
        """What to call this event in prose.

        Returns
        -------
        str
            The author's `name`, or the id when they did not give one.
        """
        return self.name or self.id
