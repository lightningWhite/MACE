# ADR-0008 — The player answers; they do not take turns

**Status:** Accepted

## Context

[Tempo combat](0006-tempo-combat.md) says the enemy telegraphs and the player
responds, and [Combat](../07-combat.md) says multi-combatant fights work by
per-combatant action meters filling in proportion to speed. Implementing both
raised a question neither document answers: **is the player in the meter race?**

If they are, a fast player gets turns of their own — turns on which they
telegraph a move and the enemy answers it. That is symmetric and it is what a
turn-based game would do. It also turns out to be a different game.

The immediate symptom was smaller: the player archetype has no attack moves,
only defenses, so their meter turns produced nothing and quietly became free
stamina. The fix could have gone either way — give the player attacks, or take
them out of the race.

## Decision

**The player is not in the action-meter race.** Enemies and allies race; the
player answers.

Their aggression is expressed through the **opening** a clean counter buys, and
through `strike`, which is modelled as a defense that carries damage — the
interrupt that beats a grapple and the only right answer to a feint. Their
speed is spent widening the window rather than filling a bar.

Allies *are* in the race, and whatever they swing at answers on `auto`, so
nobody waits on a keypress for a fight they are watching.

## Alternatives considered

**The player races too, with their own attack moves and tells.** Symmetric,
familiar, and it makes `speed` do two jobs. Rejected because it makes a fight
two bars racing rather than a conversation about the enemy's habits — and
because it splits the player's attention between "what is coming" and "what am
I throwing", which halves the attention available for the thing the whole
system exists to reward: reading the enemy. It also doubles the authoring cost
of a playable character, who would now need attack moves, tells, and patterns
of their own.

**The player races, but their turn is a free swing with no tell.** Cheaper, and
it keeps the reading loop intact. Rejected because it makes speed strictly
better than every other stat — more turns is more damage with no decision
attached — and because a free hit nobody can answer is exactly the dice-roll
combat this design replaced.

**Nobody races; strict alternation.** Simplest. Rejected because it throws away
multi-combatant pressure, which is the one thing that makes three wolves feel
different from one wolf with more hitpoints.

## Consequences

- **A playable character needs defenses, not attacks.** `fantasy.core:adventurer`
  is five defense moves and nothing else, and that is a complete fighter. This
  makes authoring a protagonist much cheaper than authoring an enemy, which is
  the right way round.
- **The opening carries all of the player's damage**, so its multiplier is the
  single most load-bearing balance number in the system. It is named
  `OPENING_MULTIPLIER` and sits alone.
- **Speed is not a damage stat for the player.** It widens windows. A fast
  character survives more; a strong one hits harder through the openings a
  *read* buys. Neither substitutes for reading.
- **An order costs an exchange.** With no turn of their own, the only thing the
  player can spend to direct their allies is the answer they were about to
  give, which makes `focus` a real trade rather than a free button.
- **A future front-end must never offer the player an "attack" button.** There
  is nothing behind it. Front-ends offer responses.
