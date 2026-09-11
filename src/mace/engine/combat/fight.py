"""Running a fight: tells, answers, and the four ways an exchange can go.

The loop is the one in docs/07-combat.md, and it is small on purpose:

    tell → the player answers → resolve → tell

`begin` opens a fight and telegraphs the first move. `respond` takes one
answer, resolves the exchange it belongs to, and telegraphs the next — or ends
the fight. A fight in `auto` mode runs the whole thing inside `begin`, because
there is nobody to wait for.

Three modes, one loop. `reflex` and `tactical` differ only in whether the
response carries an elapsed time; `auto` differs only in who supplies the
response. Everything else — patterns, counters, stamina, momentum, feints,
familiarity — is shared, which is what makes tactical mode a real way to play
rather than a diminished one.

A fight happens inside a tick and never moves the world clock. That is what
keeps a forty-exchange fight from aging the world more than a twelve-exchange
one, and it is why nothing here calls into the world simulation.
"""

from __future__ import annotations

from dataclasses import dataclass

from mace.content import ContentError
from mace.content.ids import split
from mace.engine.combat import resolution
from mace.engine.combat.resolution import Outcome
from mace.engine.combat.roster import (
    FLEE,
    FOCUS,
    RECOVER,
    USE,
    Fighter,
    fighter_for,
)
from mace.engine.conditions import RuleError, all_hold
from mace.engine.context import RuleContext
from mace.engine.events import (
    CombatBegan,
    CombatEnded,
    CombatResolved,
    CombatTell,
    Event,
    Narrated,
    ResponseOffered,
    StatChanged,
)
from mace.engine.rng import RandomStream
from mace.engine.state import Combatant, CombatState, EntityState, PendingTell
from mace.engine.stats import pool_bounds
from mace.model import CombatProfile, Entity, Move

__all__ = ["begin", "respond", "responses_for"]

#: The response recorded when the defender never answered at all — a failed
#: break for it. Distinct from `recover`, which is a *choice* to breathe and
#: is paid for by taking the hit; being caught mid-turn earns nothing back.
CAUGHT = "caught"

#: What one exchange gives back, as a share of the effort pool's ceiling.
#: Enough that a careful fighter can hold a rhythm; not enough to spam.
PASSIVE_REGEN = 0.05

#: What spending a whole exchange catching your breath gives back. The pacing
#: half of the skill: pressure, recover, pressure.
RECOVER_REGEN = 0.28

#: What trying to run costs, as a share of the effort pool.
FLEE_COST = 0.15

#: The floor and ceiling on a flee attempt, whatever the speeds involved.
FLEE_FLOOR = 0.05
FLEE_CEILING = 0.90

#: The base chance of getting away from an evenly matched pursuer.
FLEE_BASE = 0.35

#: How much familiarity with a profile widens its windows, at full knowledge.
FAMILIARITY_WINDOW = 0.20

#: The hardest a player may set the clock. A floor rather than an assertion:
#: a session setting that could be zero would divide the window away entirely,
#: and an unanswerable fight is a crash with better manners.
MIN_TIME_PRESSURE = 0.05

#: How much of the way to a legible tell full familiarity carries a vague one.
FAMILIARITY_CLARITY = 0.5

#: How far above/below NEUTRAL_STAT a stat has to sit before a qualitative
#: read says anything about it at all — an opponent within this band of
#: neutral is unremarkable, and unremarkable is worth saying nothing about.
READ_MARGIN = 15.0

#: How much less legible a tell is when there is no clock running. Tactical
#: mode gives up the execution half of skill, so it keeps the reading half
#: harder — otherwise it would be the easy mode rather than the other one.
TACTICAL_CLARITY = 0.75

#: A hard stop on a fight's length. Content that cannot hurt anybody produces
#: a draw rather than an endless loop — and a draw counts as getting away,
#: because nobody won and the world has to move on.
MAX_EXCHANGES = 400

#: A hard stop on consecutive turns that produce no tell for the player. Only
#: reachable when nobody in a fight has an attack at all.
MAX_TURNS = 200

#: What an opening is worth over an ordinary swing. A counter catches an
#: opponent mid-commitment with their weight in the wrong place, and this is
#: the number that makes a clean read *feel* like the reward it is: eight good
#: exchanges should finish a troll that twenty-five bad ones lose to.
OPENING_MULTIPLIER = 1.9

#: How fast an action meter fills, per point of speed. A speed-50 fighter is
#: ready every other beat; a speed-65 wolf is ready more often than that, and
#: three of them are three windows overlapping.
METER_SCALE = 50.0

#: How many beats to advance before giving up on anyone becoming ready.
MAX_BEATS = 1000

#: The speed a fighter is treated as having when content gave it none. Slow,
#: but not so slow that a missing stat hangs the fight.
MIN_SPEED = 5.0

#: What the auto defender's read is worth before speed is added, and how much
#: speed moves it. Auto mode is the retained dice-and-stats resolution, which
#: is exactly what makes it a useful baseline to balance the real one against.
AUTO_READ_BASE = 0.35
AUTO_READ_SPEED = 0.004
AUTO_PRECISION_BASE = 0.30
AUTO_PRECISION_SPEED = 0.007


@dataclass(slots=True)
class _Exchange:
    """One resolved exchange, before it is turned into events.

    Attributes
    ----------
    outcome : Outcome
        How it went.
    correct : bool
        Whether the read was right.
    precision : float
        How well the answer was timed, after skill eased it.
    taken : float
        Damage the defender took.
    dealt : float
        Damage the defender dealt back through an opening.
    spent : float
        Effort the defender spent answering.
    critical : bool
        Whether the opening was a critical one.
    """

    outcome: Outcome
    correct: bool
    precision: float
    taken: float = 0.0
    dealt: float = 0.0
    spent: float = 0.0
    critical: bool = False


# ── Starting and ending ───────────────────────────────────────────────────────


def begin(
    context: RuleContext,
    against: list[str],
    events: list[Event],
    *,
    spawned: set[str] | None = None,
    can_flee: bool = True,
    after: dict[str, str] | None = None,
    flee_to: str | None = None,
    mode: str | None = None,
) -> None:
    """Open a fight against some entity instances.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    against : list of str
        Instance ids of the opponents, already in the session.
    events : list of Event
        Accumulator.
    spawned : set of str or None
        Which of them this fight put there, so it can tidy them away again.
    can_flee : bool
        Whether running is allowed.
    after : dict or None
        Outcome name to the qualified scene played once the fight ends.
    flee_to : str or None
        Qualified location id to put them down at.
    mode : str or None
        Override both the game's default and the player's session setting.
    """
    state = context.state
    state.combats_begun += 1
    fight = CombatState(
        id=f"combat#{state.combats_begun}",
        mode=mode or state.combat_mode or context.game.rules.combat_mode,
        can_flee=can_flee,
        after=dict(after or {}),
        flee_to=flee_to,
    )

    fight.combatants.append(
        Combatant(
            actor=state.player,
            side="player",
            profile=_profile_of(state.protagonist, context),
        )
    )
    for ally in _allies(context):
        fight.combatants.append(
            Combatant(
                actor=ally.instance_id,
                side="player",
                profile=_profile_of(ally, context),
            )
        )
    for actor in against:
        opponent = state.entities.get(actor)
        if opponent is None:
            raise RuleError(f"`{actor}` is not in this session, so it cannot fight")
        fight.combatants.append(
            Combatant(
                actor=actor,
                side="enemy",
                profile=_profile_of(opponent, context),
                spawned=actor in (spawned or ()),
            )
        )

    state.combat = fight
    roster = _roster(fight, context)
    vital = context.game.rules.vital_pool
    reader = roster.get(state.player)
    events.append(
        CombatBegan(
            combat=fight.id,
            mode=fight.mode,
            combatants=tuple(
                (
                    fighter.actor,
                    fighter.name,
                    fighter.combatant.side,
                    fighter.combatant.profile or "",
                    fighter.pool(vital),
                    fighter.pool_max(vital),
                    _reads(fighter, reader),
                )
                for fighter in roster.values()
            ),
            can_flee=fight.can_flee,
            matrix=_matrix(roster),
            vital_pool=vital,
        )
    )

    if fight.mode == "auto":
        _run_auto(context, events)
        return
    _next_tell(context, events)


def _matrix(roster: dict[str, Fighter]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """What beats what, among the moves this fight can actually produce.

    Parameters
    ----------
    roster : dict
        Instance id to fighter.

    Returns
    -------
    tuple of tuple
        Move type and the defense types that beat it, in a stable order.
    """
    beaten: dict[str, list[str]] = {}
    for fighter in roster.values():
        if fighter.combatant.side != "enemy":
            continue
        for _qualified, move in fighter.attacks:
            answers = beaten.setdefault(move.type, [])
            answers.extend(name for name in move.counters if name not in answers)
    return tuple((move, tuple(answers)) for move, answers in sorted(beaten.items()))


def _reads(fighter: Fighter, reader: Fighter | None) -> tuple[str, ...]:
    """What the player's own familiarity has earned them about one opponent.

    Nothing for a stranger — the same as combat shows today. A fuzzy read
    once the reader's fighter has faced this profile before, using only
    `strength`/`speed` since those are the only two names with universal
    meaning. The real numbers once the profile is fully known — the same
    threshold `FAMILIARITY_CLARITY` already treats as "knows it." Computed
    once, at the fight's start: this is what the player already knows
    walking in, not something that should shift mid-fight.

    Parameters
    ----------
    fighter : Fighter
        The opponent being read.
    reader : Fighter or None
        The player's own fighter, whose familiarity this is. None for the
        player's own entry, and for a fight with no player in it.

    Returns
    -------
    tuple of str
        Lines to show under the opponent's name. Empty for a stranger, an
        ally, or the player's own entry.
    """
    if reader is None or fighter is reader or fighter.combatant.side != "enemy":
        return ()
    familiarity = reader.familiarity_with(fighter.combatant.profile)
    if familiarity <= 0.0:
        return ()

    strength = fighter.stat("strength")
    speed = fighter.stat("speed")
    if familiarity >= 1.0:
        return (f"Strength {round(strength)}.", f"Speed {round(speed)}.")

    lines: list[str] = []
    if strength >= resolution.NEUTRAL_STAT + READ_MARGIN:
        lines.append("Hits hard.")
    elif strength <= resolution.NEUTRAL_STAT - READ_MARGIN:
        lines.append("Hits soft.")
    if speed >= resolution.NEUTRAL_STAT + READ_MARGIN:
        lines.append("Quick.")
    elif speed <= resolution.NEUTRAL_STAT - READ_MARGIN:
        lines.append("Slow.")
    return tuple(lines)


def _end(context: RuleContext, outcome: str, events: list[Event]) -> None:
    """Finish a fight and hand the spoils over.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    outcome : str
        `won`, `lost`, or `fled`.
    events : list of Event
        Accumulator.
    """
    state = context.state
    fight = state.combat
    assert fight is not None
    fight.outcome = outcome
    fight.tell = None

    if outcome == "won":
        _take_spoils(context, fight)

    events.append(
        CombatEnded(
            combat=fight.id,
            outcome=outcome,
            exchanges=fight.exchange,
            spoils=tuple(sorted(fight.spoils.items())),
        )
    )
    # The fight stays on the state until the step runner has read its outcome
    # and decided what happens next — a flee scene, a lost game, a road to
    # carry on down. `mace.engine.step` clears it.


def _take_spoils(context: RuleContext, fight: CombatState) -> None:
    """Move what the defeated were carrying onto the player.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The finished fight.
    """
    player = context.state.protagonist
    for combatant in fight.combatants:
        if combatant.side != "enemy" or not combatant.defeated:
            continue
        loser = context.state.entities.get(combatant.actor)
        if loser is None:  # pragma: no cover — combatants are session entities
            continue
        for item, quantity in sorted(loser.inventory.items()):
            fight.spoils[item] = fight.spoils.get(item, 0) + quantity
            player.inventory[item] = player.inventory.get(item, 0) + quantity
        loser.inventory.clear()


# ── The exchange ──────────────────────────────────────────────────────────────


def respond(
    context: RuleContext,
    response: str,
    events: list[Event],
    *,
    elapsed_ms: int | None = None,
) -> None:
    """Answer the move currently telegraphed, and resolve the exchange.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    response : str
        A defense type, `recover`, or `flee`.
    events : list of Event
        Accumulator.
    elapsed_ms : int or None
        When the answer was committed, in milliseconds from the tell. None in
        tactical mode, where no clock is running.

    Raises
    ------
    RuleError
        If there is no fight, nothing is telegraphed, or the response is not
        one this fighter has.
    """
    state = context.state
    fight = state.combat
    if fight is None or fight.outcome is not None:
        raise RuleError("there is no fight to answer")
    tell = fight.tell
    if tell is None:  # pragma: no cover — a live fight always has a tell
        raise RuleError("nothing is coming at you right now")

    roster = _roster(fight, context)
    defender = roster[tell.defender]
    allowed = responses_for(defender, fight, context)
    if response not in allowed:
        raise RuleError(
            f"`{response}` is not one of your answers; you have "
            f"{', '.join(allowed)}"
        )

    if response == FLEE:
        _attempt_flight(context, roster, events)
        return

    if response == FOCUS:
        _give_an_order(context, fight, roster, events)
        return

    if response.startswith(f"{USE}:"):
        _reach_for_it(context, fight, roster, response, events)
        return

    _resolve(context, roster, tell, response, elapsed_ms, events)
    if _settled(context, events):
        return
    _next_tell(context, events)


def _resolve(
    context: RuleContext,
    roster: dict[str, Fighter],
    tell: PendingTell,
    response: str,
    elapsed_ms: int | None,
    events: list[Event],
) -> None:
    """Work out what one answer did, and apply it.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    roster : dict
        Instance id to fighter.
    tell : PendingTell
        The move being answered.
    response : str
        The answer.
    elapsed_ms : int or None
        When it was committed.
    events : list of Event
        Accumulator.
    """
    state = context.state
    fight = state.combat
    assert fight is not None
    attacker = roster[tell.attacker]
    defender = roster[tell.defender]
    move = _move(context, tell.move)
    stream = state.rng.stream(f"combat.{fight.id}")

    effort = context.game.rules.effort_pool
    chosen = defender.defense(response)
    staggered = chosen is not None and defender.pool(effort) < chosen[1].cost

    correct = chosen is not None and not staggered and response in move.counters
    precision = _precision(defender, response, elapsed_ms, tell, staggered)
    outcome = resolution.outcome_of(correct=correct, precision=precision)

    incoming = _incoming(attacker, defender, move, stream)
    mitigation = chosen[1].mitigation if chosen is not None and not staggered else 0.0
    exchange = _Exchange(
        outcome=outcome,
        correct=correct,
        precision=precision,
        taken=round(
            resolution.damage_taken(
                incoming, outcome, precision=precision, mitigation=mitigation
            ),
            1,
        ),
    )

    if response == RECOVER:
        exchange.spent = -_share(defender, effort, RECOVER_REGEN)
    elif chosen is not None:
        exchange.spent = resolution.stamina_cost(chosen[1].cost, correct=correct)
    if response != CAUGHT:
        exchange.spent -= _share(defender, effort, PASSIVE_REGEN)

    if outcome is Outcome.COUNTER:
        exchange.dealt, exchange.critical = _opening(defender, attacker, chosen, stream)

    _apply(context, attacker, defender, exchange, move, events)
    _remember(defender, attacker, exchange)

    fight.exchange += 1
    defender.combatant.momentum = resolution.momentum_after(
        defender.combatant.momentum, outcome
    )
    defender.combatant.streak = defender.combatant.streak + 1 if exchange.correct else 0

    events.append(
        CombatResolved(
            combat=fight.id,
            exchange=fight.exchange,
            attacker=attacker.actor,
            defender=defender.actor,
            move=tell.move,
            response=response,
            read="correct" if exchange.correct else "wrong",
            result=outcome.value,
            precision=precision,
            damage_taken=exchange.taken,
            damage_dealt=exchange.dealt,
            critical=exchange.critical,
            momentum=resolution.multiplier(defender.combatant.momentum),
            stamina=round(defender.pool(effort), 2),
            feint=tell.feint,
        )
    )
    fight.tell = None


def _precision(
    defender: Fighter,
    response: str,
    elapsed_ms: int | None,
    tell: PendingTell,
    staggered: bool,
) -> float:
    """How well an answer was timed, after skill and staggering.

    Parameters
    ----------
    defender : Fighter
        Who answered.
    response : str
        What they answered with.
    elapsed_ms : int or None
        When, or None in tactical mode.
    tell : PendingTell
        The move being answered, for its window.
    staggered : bool
        Whether they had no effort left to spend, in which case the answer
        fails whatever the timing was.

    Returns
    -------
    float
        0 to 1.
    """
    if staggered or response in {RECOVER, CAUGHT}:
        # Neither is an answer to the move. `recover` is a deliberate choice to
        # be hit; `caught` is having spent the exchange on something else — an
        # order, a potion, a break for it that failed. Both take it square.
        return 0.0
    if elapsed_ms is None:
        raw = resolution.tactical_precision()
    else:
        quantized = resolution.quantize(elapsed_ms)
        # Past the window the answer was never made: too late is too late, and
        # a response that lands after the blow is not a slow response.
        raw = (
            0.0
            if quantized > tell.window_ms
            else resolution.precision_of(quantized, tell.window_ms)
        )
    return resolution.eased(raw, defender.skill_with(defender.weapon))


def _incoming(
    attacker: Fighter, defender: Fighter, move: Move, stream: RandomStream
) -> float:
    """What a move is worth before the read is taken into account.

    Randomness is confined to the roll inside the move's own damage band. That
    band *is* the variance, which is why nothing else here rolls.

    Parameters
    ----------
    attacker : Fighter
        Who is swinging.
    defender : Fighter
        Who is wearing the armor.
    move : Move
        The move.
    stream : RandomStream
        This fight's stream.

    Returns
    -------
    float
        Damage before the outcome scales it, never negative.
    """
    if move.damage is None:
        return 0.0
    span = move.damage.max - move.damage.min
    rolled = move.damage.min + stream.fraction() * span
    strength = resolution.power(attacker.stat("strength"))
    return max(0.0, rolled * strength - defender.armor)


def _opening(
    defender: Fighter,
    attacker: Fighter,
    chosen: tuple[str, Move] | None,
    stream: RandomStream,
) -> tuple[float, bool]:
    """What a clean counter gets back, and whether it was a critical one.

    Parameters
    ----------
    defender : Fighter
        Who read it right, and now has an opening.
    attacker : Fighter
        Who is about to be hit.
    chosen : tuple or None
        The defense used, whose own damage counts too — that is what makes
        `strike` worth the effort it costs.
    stream : RandomStream
        This fight's stream.

    Returns
    -------
    tuple
        The damage dealt and whether it was critical.
    """
    band = defender.weapon_damage
    rolled = band.min + stream.fraction() * (band.max - band.min)
    if chosen is not None and chosen[1].damage is not None:
        extra = chosen[1].damage
        rolled += extra.min + stream.fraction() * (extra.max - extra.min)

    dealt = (
        rolled
        * OPENING_MULTIPLIER
        * resolution.power(defender.stat("strength"))
        * resolution.skill_damage(defender.skill_with(defender.weapon))
        * resolution.multiplier(defender.combatant.momentum)
    )
    critical = stream.chance(
        resolution.CRITICAL_CHANCE * resolution.multiplier(defender.combatant.momentum)
    )
    if critical:
        dealt *= resolution.CRITICAL_MULTIPLIER
    return round(max(0.0, dealt - attacker.armor), 1), critical


def _apply(
    context: RuleContext,
    attacker: Fighter,
    defender: Fighter,
    exchange: _Exchange,
    move: Move,
    events: list[Event],
) -> None:
    """Write an exchange's damage and effort into the world.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    attacker, defender : Fighter
        The two sides of it.
    exchange : _Exchange
        What happened.
    move : Move
        The move, for the effects it carries.
    events : list of Event
        Accumulator.
    """
    vital = context.game.rules.vital_pool
    effort = context.game.rules.effort_pool

    if exchange.taken:
        _move_pool(defender, vital, -exchange.taken, move.label, events)
    if exchange.dealt:
        _move_pool(attacker, vital, -exchange.dealt, "your opening", events)
    if exchange.spent:
        _move_pool(defender, effort, -exchange.spent, None, events)

    if exchange.taken and move.effects:
        from mace.engine.effects import apply_all  # noqa: PLC0415

        applied = apply_all(move.effects, context, source=move.id)
        events.extend(applied.events)

    if exchange.outcome is Outcome.CLEAN:
        # Stats with `growth` improve from use, and taking a blow properly is
        # how endurance is used. Slow enough that it is a reward rather than a
        # strategy.
        _grow(defender, "endurance")

    for fighter in (attacker, defender):
        if fighter.pool(vital) <= 0.0:
            fighter.combatant.defeated = True


def _move_pool(
    fighter: Fighter,
    pool: str,
    delta: float,
    reason: str | None,
    events: list[Event],
) -> None:
    """Move one pool and report what actually landed.

    A heal that overflows the cap reports the healing that landed, not the
    healing that was asked for — the same rule the effect layer follows, for
    the same reason.

    Parameters
    ----------
    fighter : Fighter
        Whose pool.
    pool : str
        Which pool.
    delta : float
        How much to move it by.
    reason : str or None
        What did it.
    events : list of Event
        Accumulator.
    """
    low, high = pool_bounds(fighter.definition, fighter.state, pool)
    current = fighter.pool(pool)
    landed = round(min(max(current + delta, low), high), 3)
    if landed == current:
        return
    fighter.state.pools[pool] = landed
    events.append(
        StatChanged(
            actor=fighter.actor,
            stat=pool,
            delta=round(landed - current, 3),
            value=landed,
            reason=reason,
        )
    )


def _remember(defender: Fighter, attacker: Fighter, exchange: _Exchange) -> None:
    """Let a correct read teach the defender something durable.

    Two kinds of learning, both capped low. A weapon gets easier to time with
    and hits harder; an opponent's *profile* gets easier to read, which is the
    character learning trolls while the player learns them too.

    Parameters
    ----------
    defender : Fighter
        Who read it.
    attacker : Fighter
        Who they read, for whose profile to credit.
    exchange : _Exchange
        What happened.
    """
    if not exchange.correct:
        return
    if defender.weapon is not None:
        held = defender.state.skills.get(defender.weapon, 0.0)
        defender.state.skills[defender.weapon] = round(
            min(resolution.SKILL_CAP, held + resolution.skill_gain(held)), 3
        )
    profile = attacker.combatant.profile
    if profile is not None:
        seen = defender.state.familiarity.get(profile, 0)
        defender.state.familiarity[profile] = seen + 1


def _grow(fighter: Fighter, stat: str) -> None:
    """Train a stat a little, if its author said it grows.

    Parameters
    ----------
    fighter : Fighter
        Whose stat.
    stat : str
        Which one. Taking hits trains endurance; running trains speed.
    """
    declared = (fighter.definition.stats or {}).get(stat)
    if declared is None:
        return
    step = resolution.growth_step(declared.growth)
    if not step:
        return
    ceiling = declared.max if declared.max is not None else 100.0
    stored = fighter.state.pools.get(stat, declared.base)
    fighter.state.pools[stat] = round(min(float(ceiling), stored + step), 3)


def _reach_for_it(
    context: RuleContext,
    fight: CombatState,
    roster: dict[str, Fighter],
    response: str,
    events: list[Event],
) -> None:
    """Spend the exchange using something out of your pack.

    Priced the same way an order is: the move that was coming lands with
    nobody answering it. That is what makes the healing draught a decision
    about *when* rather than a button — you are buying the hitpoints with a
    hit, and taking one at the wrong moment is how a fight is lost.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight.
    roster : dict
        Instance id to fighter.
    response : str
        The response, `use:` and a qualified item id.
    events : list of Event
        Accumulator.
    """
    from mace.engine.step import spend_item  # noqa: PLC0415

    spend_item(response.split(":", 1)[1], context, events)

    tell = fight.tell
    assert tell is not None
    _resolve(context, roster, tell, CAUGHT, None, events)
    if _settled(context, events):
        return
    _next_tell(context, events)


def _give_an_order(
    context: RuleContext,
    fight: CombatState,
    roster: dict[str, Fighter],
    events: list[Event],
) -> None:
    """Spend the exchange telling your allies who to concentrate on.

    A real cost and a real tactical choice: the move that was coming still
    lands, unanswered, and what you buy is your escort turning on the wounded
    wolf rather than the nearest one. The order cycles through the standing
    enemies rather than naming one, so the protocol stays a flat response and
    a front-end needs no target picker — pressing it again moves along.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight.
    roster : dict
        Instance id to fighter.
    events : list of Event
        Accumulator.
    """
    standing = [c.actor for c in fight.standing("enemy")]
    if fight.focus in standing:
        fight.focus = standing[(standing.index(fight.focus) + 1) % len(standing)]
    else:
        fight.focus = standing[0]

    named = roster[fight.focus].name
    events.append(Narrated(f'"{named}!" you call. "That one!"', pause=False))

    tell = fight.tell
    assert tell is not None
    _resolve(context, roster, tell, CAUGHT, None, events)
    if _settled(context, events):
        return
    _next_tell(context, events)


# ── Fleeing ───────────────────────────────────────────────────────────────────


def _attempt_flight(
    context: RuleContext, roster: dict[str, Fighter], events: list[Event]
) -> None:
    """Try to get away, and pay for it if it fails.

    Always available, never free. It rolls against the fastest thing still
    chasing, costs effort whether or not it works, and a failed attempt gives
    the enemy the exchange for nothing.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    roster : dict
        Instance id to fighter.
    events : list of Event
        Accumulator.
    """
    state = context.state
    fight = state.combat
    assert fight is not None
    tell = fight.tell
    assert tell is not None

    runner = roster[tell.defender]
    effort = context.game.rules.effort_pool
    pursuers = [roster[c.actor].stat("speed") for c in fight.standing("enemy")]
    fastest = max(pursuers, default=0.0)
    chance = min(
        FLEE_CEILING,
        max(FLEE_FLOOR, FLEE_BASE + (runner.stat("speed") - fastest) / 100.0),
    )

    _move_pool(runner, effort, -_share(runner, effort, FLEE_COST), "running", events)
    _grow(runner, "speed")

    stream = state.rng.stream(f"combat.{fight.id}")
    if stream.chance(chance):
        events.append(Narrated("You break off and run.", pause=False))
        _end(context, "fled", events)
        return

    events.append(Narrated("You turn to run, and it is on you before you can.", False))
    # A failed break gives the enemy the exchange for nothing: the move that
    # was already coming lands with nobody answering it.
    _resolve(context, roster, tell, CAUGHT, None, events)
    if _settled(context, events):
        return
    _next_tell(context, events)


# ── Whose turn, and what they do ──────────────────────────────────────────────


def _next_tell(context: RuleContext, events: list[Event]) -> None:
    """Telegraph moves until one is aimed at the player, or the fight ends.

    Who acts is decided by action meters filling in proportion to speed, so
    facing three wolves means three windows arriving faster than one wolf's
    would. The pressure comes from parallelism rather than from bigger numbers.

    **The player is not in the meter race.** Their side of a fight is answering:
    a clean read is what buys them the opening they hit back through, and
    `strike` is a defense that answers by hurting. Their speed is spent
    widening the window rather than filling a bar, which is what keeps a fight
    a conversation about the enemy's habits rather than two bars racing. Allies
    *are* in the race — they act on their own profiles, and whatever they swing
    at answers on `auto` without the player being asked about it.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    fight = state.combat
    assert fight is not None

    for _turn in range(MAX_TURNS):
        if fight.outcome is not None:
            return
        roster = _roster(fight, context)
        ready = _advance_meters(fight, roster, skip=state.player)
        if ready is None:
            _end(context, "won" if not fight.standing("enemy") else "lost", events)
            return

        attacker = roster[ready.actor]
        target = _target(fight, roster, ready, state.player)
        if target is None:  # pragma: no cover — `_settled` catches an empty side
            _end(context, "lost" if ready.side == "enemy" else "won", events)
            return

        chosen = _choose_move(context, fight, attacker)
        if chosen is None:
            # Nothing to swing with. Rather than stall the fight, the fighter
            # catches its breath and the meters fill again.
            _catch_breath(context, attacker, events)
            continue

        _telegraph(context, fight, attacker, target, chosen, events)
        if target.actor == state.player and fight.mode != "auto":
            events.append(
                ResponseOffered(
                    combat=fight.id,
                    options=labelled(target, fight, context),
                    stamina=round(target.pool(context.game.rules.effort_pool), 2),
                    momentum=resolution.multiplier(target.combatant.momentum),
                    streak=target.combatant.streak,
                )
            )
            return

        # Nobody is waiting on a keypress for this one: whatever an ally swung
        # at, or whatever swung at an ally, answers from its own stats.
        tell = fight.tell
        assert tell is not None
        response, elapsed = _auto_answer(context, fight, roster[tell.defender], tell)
        _resolve(context, roster, tell, response, elapsed, events)
        if _settled(context, events):
            return
    _end(context, "fled", events)  # pragma: no cover — needs MAX_TURNS of nothing


def _telegraph(
    context: RuleContext,
    fight: CombatState,
    attacker: Fighter,
    target: Fighter,
    chosen: tuple[str, Move],
    events: list[Event],
) -> None:
    """Wind a move up, and say so.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight.
    attacker : Fighter
        Who is winding up.
    target : Fighter
        Who has to answer.
    chosen : tuple
        The qualified id and definition of the move.
    events : list of Event
        Accumulator.
    """
    qualified, move = chosen
    ease = 1.0 + FAMILIARITY_WINDOW * target.familiarity_with(
        attacker.combatant.profile
    )
    # The player's own time-pressure setting divides into the same ease that
    # familiarity multiplies, so "I want more time" and "I have fought trolls
    # before" widen the same door rather than two.
    ease /= max(context.state.time_pressure, MIN_TIME_PRESSURE)
    window = resolution.window_ms(move.windup_ms, target.stat("speed"), ease)
    clear = _is_clear(context, fight, attacker, target)
    fight.tell = PendingTell(
        attacker=attacker.actor,
        defender=target.actor,
        move=qualified,
        feint=move.feint,
        clear=clear,
        window_ms=window,
    )
    events.append(
        CombatTell(
            combat=fight.id,
            attacker=attacker.actor,
            defender=target.actor,
            move=qualified,
            type=move.type if clear else "",
            text=_tell_text(move, clear, context),
            window_ms=window,
            clear=clear,
        )
    )


def _advance_meters(
    fight: CombatState, roster: dict[str, Fighter], *, skip: str
) -> Combatant | None:
    """Fill every meter until one is ready, and return whoever is readiest.

    Parameters
    ----------
    fight : CombatState
        The fight.
    roster : dict
        Instance id to fighter.
    skip : str
        An instance id to leave out of the race — the player, who answers
        rather than acts.

    Returns
    -------
    Combatant or None
        The combatant who acts, or None when nobody is left to.
    """
    standing = [
        c
        for c in fight.combatants
        if not c.defeated and not c.routed and c.actor != skip
    ]
    if not standing:
        return None
    # A fighter with no speed still gets a turn, eventually. Otherwise content
    # that forgot to give a wolf a `speed` stat would hang the fight.
    rates = {
        c.actor: max(roster[c.actor].stat("speed"), MIN_SPEED) / METER_SCALE
        for c in standing
    }
    for _beat in range(MAX_BEATS):
        ready = [c for c in standing if c.meter >= 1.0]
        if ready:
            # Readiest first; ties break by roster order, which is stable and
            # therefore replayable.
            acting = max(ready, key=lambda c: (c.meter, -standing.index(c)))
            acting.meter -= 1.0
            return acting
        for combatant in standing:
            combatant.meter += rates[combatant.actor]
    return None  # pragma: no cover — unreachable while MIN_SPEED is positive


def _target(
    fight: CombatState, roster: dict[str, Fighter], acting: Combatant, player: str
) -> Fighter | None:
    """Who an acting combatant swings at.

    An enemy goes for the player while the player is standing. A fight where
    the wolves prefer your escort is a fight the player watches rather than
    fights, and watching is not what any of this is for.

    Parameters
    ----------
    fight : CombatState
        The fight.
    roster : dict
        Instance id to fighter.
    acting : Combatant
        Whoever is acting.
    player : str
        The protagonist's instance id.

    Returns
    -------
    Fighter or None
        The target, or None when the other side is empty.
    """
    other = "enemy" if acting.side == "player" else "player"
    candidates = fight.standing(other)
    if not candidates:
        return None
    if other == "player":
        chosen = next((c for c in candidates if c.actor == player), candidates[0])
    else:
        # An order the player paid an exchange for is what allies act on.
        chosen = next((c for c in candidates if c.actor == fight.focus), candidates[0])
    return roster[chosen.actor]


def _choose_move(
    context: RuleContext, fight: CombatState, attacker: Fighter
) -> tuple[str, Move] | None:
    """Pick the next move out of the attacker's patterns, or feint instead.

    Patterns are played to the end before another is drawn, which is the whole
    of what makes an enemy learnable: it really does like to swing twice high
    and then go low.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight, for its random stream.
    attacker : Fighter
        Who is acting.

    Returns
    -------
    tuple or None
        The qualified id and the move, or None when it has no attack.
    """
    if not attacker.attacks:
        return None
    stream = context.state.rng.stream(f"combat.{fight.id}")
    profile = attacker.profile

    if profile is not None and stream.chance(profile.feint_chance):
        feints = [pair for pair in attacker.attacks if pair[1].feint]
        if feints:
            return stream.choice(feints)

    combatant = attacker.combatant
    if combatant.pattern_step >= len(combatant.pattern):
        combatant.pattern = _draw_pattern(context, profile, attacker, stream)
        combatant.pattern_step = 0
    if not combatant.pattern:
        return stream.choice(attacker.attacks)

    reference = combatant.pattern[combatant.pattern_step]
    combatant.pattern_step += 1
    for qualified, move in attacker.attacks:
        if qualified == reference:
            return qualified, move
    return stream.choice(attacker.attacks)  # pragma: no cover — validation forbids it


def _draw_pattern(
    context: RuleContext,
    profile: CombatProfile | None,
    attacker: Fighter,
    stream: RandomStream,
) -> tuple[str, ...]:
    """Draw the next sequence a fighter will play.

    Parameters
    ----------
    context : RuleContext
        The playthrough, for the patterns' own conditions.
    profile : CombatProfile or None
        The profile whose patterns to draw from.
    attacker : Fighter
        Who is fighting, for resolving the pattern's references.
    stream : RandomStream
        This fight's stream.

    Returns
    -------
    tuple of str
        Qualified move ids, or empty when the profile has no eligible pattern
        and moves should be drawn at random instead.
    """
    if profile is None:
        return ()
    eligible = [
        pattern
        for pattern in profile.patterns
        if pattern.weight > 0 and all_hold(pattern.when, context)
    ]
    if not eligible:
        return ()
    chosen = stream.weighted([(pattern, pattern.weight) for pattern in eligible])
    known = {move.id: qualified for qualified, move in attacker.attacks}
    resolved: list[str] = []
    for reference in chosen.sequence:
        local = reference.split(":")[-1]
        if local in known:
            resolved.append(known[local])
    return tuple(resolved)


def _is_clear(
    context: RuleContext, fight: CombatState, attacker: Fighter, defender: Fighter
) -> bool:
    """Whether a telegraph was legible enough to name what is coming.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight, for its stream and its mode.
    attacker : Fighter
        Who is winding up.
    defender : Fighter
        Who is reading it.

    Returns
    -------
    bool
        Whether the move's type is shown.
    """
    profile = attacker.profile
    clarity = 1.0 if profile is None else profile.tell_clarity
    if fight.mode == "tactical":
        # No clock is running, so the reading has to carry more of the weight.
        clarity *= TACTICAL_CLARITY
    known = defender.familiarity_with(attacker.combatant.profile)
    clarity += (1.0 - clarity) * known * FAMILIARITY_CLARITY
    return context.state.rng.stream(f"combat.{fight.id}").chance(clarity)


def _tell_text(move: Move, clear: bool, context: RuleContext) -> str:
    """The prose a telegraph is shown as.

    Parameters
    ----------
    move : Move
        The move being played.
    clear : bool
        Whether it was read legibly.
    context : RuleContext
        The playthrough, for conditional tells.

    Returns
    -------
    str
        What the player reads.
    """
    lines = move.tell if clear else (move.vague_tell or move.tell)
    for line in lines or ():
        if all_hold(line.when, context):
            return line.text
    return ""


def _catch_breath(context: RuleContext, fighter: Fighter, events: list[Event]) -> None:
    """Spend a beat recovering rather than swinging.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fighter : Fighter
        Who is recovering.
    events : list of Event
        Accumulator.
    """
    effort = context.game.rules.effort_pool
    _move_pool(fighter, effort, _share(fighter, effort, RECOVER_REGEN), None, events)


# ── Auto mode ─────────────────────────────────────────────────────────────────


def _run_auto(context: RuleContext, events: list[Event]) -> None:
    """Play the player's side too, until the fight ends.

    This is the retained dice-and-stats resolution from ADR-0006, and it earns
    its place twice: it is the stats-only baseline the real system is balanced
    against, and it is what lets a golden replay test cover a whole fight
    without a hundred recorded keystrokes.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.
    """
    state = context.state
    fight = state.combat
    assert fight is not None
    while fight.outcome is None:
        _next_tell(context, events)
        if fight.outcome is not None:
            return
        tell = fight.tell
        if tell is None:  # pragma: no cover — `_next_tell` always leaves one
            break
        roster = _roster(fight, context)
        defender = roster[tell.defender]
        response, elapsed = _auto_answer(context, fight, defender, tell)
        _resolve(context, roster, tell, response, elapsed, events)
        if _settled(context, events):
            return


def _auto_answer(
    context: RuleContext, fight: CombatState, defender: Fighter, tell: PendingTell
) -> tuple[str, int | None]:
    """Decide what an engine-played fighter does about a telegraphed move.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight, for its stream.
    defender : Fighter
        Who is answering.
    tell : PendingTell
        The move.

    Returns
    -------
    tuple
        The response, and an elapsed time in milliseconds.
    """
    stream = context.state.rng.stream(f"combat.{fight.id}")
    move = _move(context, tell.move)
    available = responses_for(defender, fight)
    answers = [name for name in available if name in move.counters]
    others = [name for name in available if name not in move.counters and name != FLEE]

    speed = defender.stat("speed")
    facing = fight.find(tell.attacker)
    known = defender.familiarity_with(facing.profile if facing else None)
    reads = min(0.95, max(0.05, AUTO_READ_BASE + speed * AUTO_READ_SPEED + known * 0.1))
    if answers and stream.chance(reads):
        response = answers[0]
    elif others:
        response = stream.choice(others)
    elif answers:
        response = answers[0]
    else:
        response = RECOVER

    aim = min(
        1.0, max(0.0, AUTO_PRECISION_BASE + (speed - 50.0) * AUTO_PRECISION_SPEED)
    )
    ideal = (3 * tell.window_ms) // 4
    drift = int(round((1.0 - aim) * tell.window_ms * 0.5 * (stream.fraction() * 2 - 1)))
    return response, max(0, resolution.quantize(ideal + drift))


# ── Bookkeeping ───────────────────────────────────────────────────────────────


def responses_for(
    fighter: Fighter, fight: CombatState, context: RuleContext | None = None
) -> tuple[str, ...]:
    """Everything a fighter may answer with right now.

    Parameters
    ----------
    fighter : Fighter
        Who is answering.
    fight : CombatState
        The fight, for whether fleeing is allowed.
    context : RuleContext or None
        The playthrough. Needed only to offer what the player is carrying;
        without it the pack is left out, which is what every caller that only
        wants to check a defense wants.

    Returns
    -------
    tuple of str
        Defense types, then `recover`, then `flee`, `focus` and any usable
        item, where each would mean something. The order is presentation
        order, and it is the engine's rather than a front-end's so that a
        terminal and a browser bind the same keys to the same things.
    """
    options = [*fighter.responses, RECOVER]
    if fighter.combatant.side != "player":
        return tuple(options)

    if fight.can_flee:
        options.append(FLEE)
    allies = [c for c in fight.standing("player") if c.actor != fighter.actor]
    if allies and len(fight.standing("enemy")) > 1:
        options.append(FOCUS)
    if context is not None:
        from mace.engine.step import usable  # noqa: PLC0415

        options.extend(f"{USE}:{item_id}" for item_id, _found in usable(context))
    return tuple(options)


def labelled(
    fighter: Fighter, fight: CombatState, context: RuleContext
) -> tuple[tuple[str, str], ...]:
    """The offered responses, each with what to call it.

    Parameters
    ----------
    fighter : Fighter
        Who is answering.
    fight : CombatState
        The fight.
    context : RuleContext
        The playthrough.

    Returns
    -------
    tuple of tuple
        Response and label, in presentation order.
    """
    from mace.engine.step import usable  # noqa: PLC0415

    names = {f"{USE}:{item_id}": found.name for item_id, found in usable(context)}
    return tuple(
        (response, names.get(response, response))
        for response in responses_for(fighter, fight, context)
    )


def _settled(context: RuleContext, events: list[Event]) -> bool:
    """End the fight if one side has stopped standing.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    events : list of Event
        Accumulator.

    Returns
    -------
    bool
        Whether the fight is over.
    """
    state = context.state
    fight = state.combat
    assert fight is not None
    _rout(context, fight)

    if fight.exchange >= MAX_EXCHANGES:
        # Content that cannot hurt anybody would otherwise go round for ever.
        # A draw counts as getting away: nobody won, and the world moves on.
        _end(context, "fled", events)
        return True
    if not fight.standing("player"):
        _end(context, "lost", events)
        return True
    if not fight.standing("enemy"):
        _end(context, "won", events)
        return True
    return False


def _rout(context: RuleContext, fight: CombatState) -> None:
    """Let an enemy that has had enough leave.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    fight : CombatState
        The fight.
    """
    vital = context.game.rules.vital_pool
    cache: dict[str, Entity] = {}
    for combatant in fight.combatants:
        if combatant.side != "enemy" or combatant.defeated or combatant.routed:
            continue
        fighter = fighter_for(combatant, context, cache=cache)
        threshold = 0.0 if fighter.profile is None else fighter.profile.flee_threshold
        ceiling = fighter.pool_max(vital)
        if threshold > 0 and ceiling > 0 and fighter.pool(vital) / ceiling < threshold:
            combatant.routed = True


def _roster(fight: CombatState, context: RuleContext) -> dict[str, Fighter]:
    """Resolve every combatant against content, for one exchange.

    Rebuilt rather than cached: a fighter who drops a sword has different
    answers on the next exchange, and a cached roster would be lying.

    Parameters
    ----------
    fight : CombatState
        The fight.
    context : RuleContext
        The playthrough.

    Returns
    -------
    dict
        Instance id to fighter.
    """
    cache: dict[str, Entity] = {}
    return {
        combatant.actor: fighter_for(combatant, context, cache=cache)
        for combatant in fight.combatants
    }


def _share(fighter: Fighter, pool: str, fraction: float) -> float:
    """A fraction of a pool's ceiling, so costs scale with the fighter.

    Parameters
    ----------
    fighter : Fighter
        Whose pool.
    pool : str
        Which pool.
    fraction : float
        The share.

    Returns
    -------
    float
        The amount.
    """
    return round(fighter.pool_max(pool) * fraction, 3)


def _allies(context: RuleContext) -> list[EntityState]:
    """The entities travelling with the player, in a stable order.

    Parameters
    ----------
    context : RuleContext
        The playthrough.

    Returns
    -------
    list of EntityState
        Allies, by instance id.
    """
    return [
        entity for _key, entity in sorted(context.state.entities.items()) if entity.ally
    ]


def _profile_of(entity: EntityState, context: RuleContext) -> str | None:
    """The qualified combat profile an entity fights on.

    Parameters
    ----------
    entity : EntityState
        The instance.
    context : RuleContext
        The playthrough.

    Returns
    -------
    str or None
        The qualified profile id, or None when it has none.
    """
    definition = context.definition(entity)
    if definition.combat is None:
        return None
    home = split(entity.definition)[0] or context.state.pack
    try:
        return context.library.resolve(
            definition.combat.profile, "combatProfiles", within=home
        )
    except ContentError:
        # Validation catches a dangling profile before play, so reaching one
        # here means content moved under a save. The fighter simply has no
        # profile, which is a worse fight rather than a broken one.
        return None


def _move(context: RuleContext, qualified: str) -> Move:
    """Look a move up by qualified id.

    Parameters
    ----------
    context : RuleContext
        The playthrough.
    qualified : str
        The qualified id.

    Returns
    -------
    Move
        The move.
    """
    pack_id, local_id = split(qualified)
    assert pack_id is not None
    return context.library.pack(pack_id).moves[local_id]
