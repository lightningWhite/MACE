"""The arithmetic of one exchange: window, precision, outcome, damage.

Pure functions over numbers. Nothing here touches state, content, or the
random source, which is what makes the two claims this system rests on
checkable rather than asserted:

**Nothing rolls to decide whether a read was correct or timing was good.**
`outcome_of` takes a response and an elapsed time and returns an outcome. There
is no seed in the signature because there is nowhere for one to go. A player
who reads and times perfectly cannot lose to dice, and that guarantee is the
whole reason practising feels worth it (ADR-0006).

**Stats widen the door; the player still has to walk through it.** A defender's
speed scales the window and a weapon skill lifts a sloppy answer part of the
way toward a clean one, but neither ever decides the outcome. The target is
stats accounting for about a third of outcome variance and player decisions two
thirds — see docs/07-combat.md § Timing.

Timing is integer milliseconds throughout, and precision is derived from one
division of integers. Wall-clock floats never reach a golden file: ADR-0004
requires elapsed times to be quantized so a replay resolves against the number
that was recorded rather than a number that was re-measured.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "CRITICAL_CHANCE",
    "GOOD_TIMING",
    "MOMENTUM_LADDER",
    "Outcome",
    "TIMING_GRANULARITY_MS",
    "damage_taken",
    "growth_step",
    "momentum_after",
    "power",
    "precision_of",
    "quantize",
    "skill_factor",
    "stamina_cost",
    "tactical_precision",
    "window_ms",
]

#: Elapsed times are rounded to this before anything looks at them. Two
#: machines that measure 812 ms and 814 ms must resolve the same exchange, or
#: a replay is not a replay (ADR-0004).
TIMING_GRANULARITY_MS = 10

#: Where in the window the sweet spot sits, as a share of it. Late on purpose:
#: the reflex being asked for is holding your nerve through the windup, not
#: hitting a key the instant you see one.
IDEAL_POINT = 0.75

#: The precision at or above which timing counts as *good* rather than merely
#: made. Spans roughly the middle two fifths of the window.
GOOD_TIMING = 0.6

#: Damage multipliers for consecutive successful reads. A fight builds, and a
#: skilled player finishes a troll in eight exchanges where a novice takes
#: twenty-five and loses.
MOMENTUM_LADDER: tuple[float, ...] = (1.0, 1.15, 1.3, 1.5)

#: How much of a hit good reflexes salvage from a bad read, at perfect timing.
#: Below the worst defense's `mitigation`, so a right read answered late still
#: beats a wrong read answered well — which is the ordering the four outcomes
#: in docs/07-combat.md promise.
GLANCE_RELIEF = 0.45

#: What a wrong defense costs, as a multiple of the move's own cost. Guessing
#: is not free, and this is what stops a player cycling defenses at random.
WRONG_DEFENSE_SURCHARGE = 1.5

#: The chance of a critical opening, before momentum scales it.
CRITICAL_CHANCE = 0.05

#: What a critical opening multiplies damage by.
CRITICAL_MULTIPLIER = 2.0

#: `precision` in tactical mode, where no time is measured. High enough that
#: reads decide the fight — which is the point of the mode — and short of
#: perfect, so a reflex player still has something to gain.
TACTICAL_PRECISION = 0.8

#: The stat value at which a stat neither helps nor hurts. Everything scales
#: around this rather than around zero, so an author writing `speed: 41` is
#: writing "a bit below average" without having to know the formula.
NEUTRAL_STAT = 50.0

#: How much of the gap to perfect timing a fully skilled weapon closes. A
#: master's sloppy parry still works; it is never a *clean* one.
MAX_SKILL_EASE = 0.35

#: How much a fully skilled weapon adds to its own damage.
MAX_SKILL_DAMAGE = 0.25

#: The skill value counted as mastery.
SKILL_CAP = 100.0

#: How much a stat with `growth` moves per use, before its growth rate scales
#: it. Small on purpose: growth is capped low enough that a skilled player with
#: a weak character still wins and a strong character cannot autopilot.
GROWTH_STEP = 0.08

#: What each declared growth rate multiplies `GROWTH_STEP` by.
GROWTH_RATES: dict[str, float] = {
    "none": 0.0,
    "slow": 0.5,
    "normal": 1.0,
    "fast": 2.0,
}

#: How fast a skill approaches its cap. Diminishing returns: the first ten
#: points of billhook come quickly and the last ten never quite arrive.
SKILL_STEP = 1.5


class Outcome(Enum):
    """How one exchange went, as a pair of answers.

    The two axes are genuinely independent — knowing what beats an overhead is
    learnable and permanent, executing it under a deadline is practised — and
    the four outcomes are their product.

    - `COUNTER` — right read, good timing. No damage taken, momentum up, and
      an opening.
    - `ABSORBED` — right read, poor timing. Reduced damage, effort spent, no
      opening.
    - `GLANCING` — wrong read, good timing. Partial damage: good reflexes
      salvage a bad read.
    - `CLEAN` — wrong read, poor timing. Full damage, momentum lost.
    """

    COUNTER = "counter"
    ABSORBED = "absorbed"
    GLANCING = "glancing"
    CLEAN = "clean"


def quantize(elapsed_ms: int) -> int:
    """Round an elapsed time to the granularity a replay can reproduce.

    Parameters
    ----------
    elapsed_ms : int
        Milliseconds as measured, or as recorded in an action log.

    Returns
    -------
    int
        The same time, rounded to `TIMING_GRANULARITY_MS`, never negative.
    """
    if elapsed_ms <= 0:
        return 0
    half = TIMING_GRANULARITY_MS // 2
    return ((elapsed_ms + half) // TIMING_GRANULARITY_MS) * TIMING_GRANULARITY_MS


def window_ms(windup_ms: int, speed: float, ease: float = 1.0) -> int:
    """How long a defender gets to answer a move.

    A speed-70 defender facing a 1400 ms overhead gets 1540 ms. Stats widen
    the door and nothing more; what happens inside it is the player's.

    Parameters
    ----------
    windup_ms : int
        The move's own windup.
    speed : float
        The defender's effective speed.
    ease : float
        A difficulty scale. Familiarity with an enemy's profile raises it,
        because a character who has fought trolls reads this one sooner.

    Returns
    -------
    int
        The window, in whole milliseconds, never below one granule.
    """
    scaled = windup_ms * (1.0 + (speed - NEUTRAL_STAT) / 200.0) * ease
    return max(TIMING_GRANULARITY_MS, int(round(scaled)))


def precision_of(elapsed_ms: int, window: int) -> float:
    """How close to the sweet spot a response landed.

    Integer arithmetic down to one division, because an encounter that
    resolves one way in Python and another in a browser is not an encounter
    anybody can balance.

    Parameters
    ----------
    elapsed_ms : int
        When the response was committed, quantized.
    window : int
        The window it was committed inside.

    Returns
    -------
    float
        0 to 1. Early is hesitant, late is too late, and 1 sits at three
        quarters of the way through.
    """
    if window <= 0:  # pragma: no cover — `window_ms` floors it
        return 0.0
    ideal = (3 * window) // 4
    reached = 1.0 - (2 * abs(elapsed_ms - ideal)) / window
    return round(min(max(reached, 0.0), 1.0), 4)


def tactical_precision() -> float:
    """The precision an untimed response is given.

    Returns
    -------
    float
        `TACTICAL_PRECISION`. Named rather than inlined because it is a
        design commitment: tactical mode keeps the whole knowledge half of
        skill and gives up only the execution half.
    """
    return TACTICAL_PRECISION


def skill_factor(skill: float) -> float:
    """Turn a raw skill value into a 0-to-1 share of mastery.

    Parameters
    ----------
    skill : float
        The stored skill, 0 to `SKILL_CAP`.

    Returns
    -------
    float
        0 for untrained, 1 for mastery.
    """
    return min(max(skill, 0.0), SKILL_CAP) / SKILL_CAP


def eased(precision: float, skill: float) -> float:
    """Lift a response's precision by what the defender has practised.

    Weapon skill narrows the gap between poor and good timing rather than
    replacing it: at mastery a sloppy parry still works, and it is still never
    a clean one.

    Parameters
    ----------
    precision : float
        The raw precision.
    skill : float
        The defender's skill with what they are holding.

    Returns
    -------
    float
        The eased precision, 0 to 1.
    """
    lift = MAX_SKILL_EASE * skill_factor(skill)
    return round(precision + (1.0 - precision) * lift, 4)


def outcome_of(*, correct: bool, precision: float) -> Outcome:
    """Which of the four outcomes an exchange produced.

    No seed, no state, no content — the whole point. Deciding this with a die
    is the design this system exists to replace.

    Parameters
    ----------
    correct : bool
        Whether the response was one of the move's `counters`.
    precision : float
        How well it was timed, 0 to 1.

    Returns
    -------
    Outcome
        The outcome.
    """
    good = precision >= GOOD_TIMING
    if correct:
        return Outcome.COUNTER if good else Outcome.ABSORBED
    return Outcome.GLANCING if good else Outcome.CLEAN


def power(strength: float) -> float:
    """How much a fighter's strength multiplies what they hit with.

    Parameters
    ----------
    strength : float
        The attacker's effective strength.

    Returns
    -------
    float
        A multiplier, 1.0 at the neutral stat and never below a tenth.
    """
    return max(0.1, 1.0 + (strength - NEUTRAL_STAT) / 100.0)


def damage_taken(
    incoming: float, outcome: Outcome, *, precision: float, mitigation: float
) -> float:
    """How much of a landed move actually gets through.

    Parameters
    ----------
    incoming : float
        The damage after strength and armor, before the read is considered.
    outcome : Outcome
        How the exchange went.
    precision : float
        The response's timing, which is what salvages a bad read.
    mitigation : float
        The share the chosen defense stops, when it was the right one.

    Returns
    -------
    float
        Damage to apply to the defender, never negative.
    """
    if outcome is Outcome.COUNTER:
        return 0.0
    if outcome is Outcome.ABSORBED:
        return max(0.0, incoming * (1.0 - mitigation))
    if outcome is Outcome.GLANCING:
        return max(0.0, incoming * (1.0 - GLANCE_RELIEF * precision))
    return max(0.0, incoming)


def stamina_cost(cost: float, *, correct: bool) -> float:
    """What answering costs, right or wrong.

    Parameters
    ----------
    cost : float
        The defense move's own cost.
    correct : bool
        Whether it was the right answer.

    Returns
    -------
    float
        The effort spent.
    """
    return cost if correct else cost * WRONG_DEFENSE_SURCHARGE


def momentum_after(momentum: int, outcome: Outcome) -> int:
    """Where a streak stands after one exchange.

    Parameters
    ----------
    momentum : int
        The current index into `MOMENTUM_LADDER`.
    outcome : Outcome
        How the exchange went.

    Returns
    -------
    int
        The new index. A clean hit taken resets it; a glance costs one step.
    """
    if outcome is Outcome.COUNTER:
        return min(momentum + 1, len(MOMENTUM_LADDER) - 1)
    if outcome is Outcome.ABSORBED:
        return momentum
    if outcome is Outcome.GLANCING:
        return max(0, momentum - 1)
    return 0


def multiplier(momentum: int) -> float:
    """What a streak multiplies outgoing damage by.

    Parameters
    ----------
    momentum : int
        The index into `MOMENTUM_LADDER`.

    Returns
    -------
    float
        The multiplier.
    """
    return MOMENTUM_LADDER[min(max(momentum, 0), len(MOMENTUM_LADDER) - 1)]


def skill_damage(skill: float) -> float:
    """What practice with a weapon adds to its damage.

    Parameters
    ----------
    skill : float
        The stored skill.

    Returns
    -------
    float
        A multiplier, 1.0 untrained.
    """
    return 1.0 + MAX_SKILL_DAMAGE * skill_factor(skill)


def skill_gain(skill: float) -> float:
    """How much one use raises a skill, with diminishing returns.

    Parameters
    ----------
    skill : float
        The current value.

    Returns
    -------
    float
        What to add. The first ten points of billhook come quickly; the last
        ten never quite arrive.
    """
    return SKILL_STEP * (1.0 - skill_factor(skill))


def growth_step(rate: str) -> float:
    """How much a stat with a declared growth rate moves per use.

    Parameters
    ----------
    rate : str
        `none`, `slow`, `normal`, or `fast`.

    Returns
    -------
    float
        The increment, 0 for a stat that does not grow.
    """
    return GROWTH_STEP * GROWTH_RATES.get(rate, 0.0)
