# ADR-0006 — Tempo combat over dice rolls

**Status:** Accepted

## Context

The v0 design has `combatActions: {punch: 3}` — an action name and a maximum
damage — with the implication that hit probability derives from strength and
speed. That's the standard text-game approach: roll, compare, apply damage.

The stated goal is different:

> "I'd like combat interactions to be somewhat skill-based instead of pure chance
> ... some way to make it feel like they're really doing good because they
> actually are good or improving."

Pure dice can't deliver that. If outcomes are determined by stats and rolls, a
player's improvement is indistinguishable from their character's, and "I'm
getting better" is an illusion the system can't actually support.

## Decision

**Tempo combat**: a sequence of exchanges in which the enemy telegraphs a move
and the player responds with a counter, within a timing window.

Two independent axes of player skill:

- **Reads** — knowing which defense beats which move type, and learning each
  enemy's behavioral patterns. Knowledge. Permanent. Transfers between fights.
- **Timing** — committing near the ideal moment in the windup. Execution.
  Practiced.

Resolution is `read correctness × timing precision × stats × gear`, modulated by
stamina and momentum. Randomness is confined to pattern selection, feints, ±10%
damage variance, and rare criticals. **Nothing rolls to decide whether a read was
correct or timing was good** — those are pure functions of player input.

Stats set the *width of the window* and the *damage bounds*; the player decides
what happens inside them. Target: stats account for roughly a third of outcome
variance, player decisions two thirds.

Three modes — `reflex`, `tactical`, `auto` — share all mechanics and differ only
in how the response is collected.

Full design in [Combat](../07-combat.md).

## Alternatives considered

**Classic dice/stat resolution.** Simple, familiar, trivially balanced, and
completely automatable for testing. Rejected as the primary system because it
fails the stated goal outright. Retained as `auto` mode, where it's genuinely
useful for testing, replay verification, and NPC-vs-NPC fights.

**Rock-paper-scissors only, no timing.** Real decisions, no reflex requirement,
works in any medium. Rejected as the *only* system — with a small move set it
becomes solvable, and once solved it's a formality. Retained as `tactical` mode,
where the enemy pattern layer keeps it from being trivial and the accessibility
benefit is decisive.

**Timing only, no reads.** A quick-time-event game. Rejected: reflex without
knowledge has no depth and no ceiling, and it excludes people for no gain.

**Tactical grid combat** (positions, facing, zones of control). Deep and
excellent. Rejected: it's a different game, it doesn't fit a text medium well, it
would dominate the project's remaining effort, and it makes authoring an enemy
much more expensive.

**Real-time with pause.** Rejected: unclear what the player's skill expression
even is, and it fits text pacing poorly.

## Consequences

- **The goal is testable.** "A player who has fought three trolls beats the
  fourth more reliably with the same character sheet" is a falsifiable claim, and
  it's the acceptance criterion for the whole system.
- **Enemies need patterns to be worth authoring.** An enemy with random move
  selection is noise, and noise can't be learned. Library combat profiles must
  ship good patterns, and the wizard should require or strongly suggest them.
- **Balance is harder.** Outcome depends on player skill, so difficulty isn't a
  single number. `auto` mode gives a stats-only baseline to balance against, and
  the player-skill multiplier has to be measured through real play.
- **Front-ends carry real responsibility.** The tell must be legible and the
  window must be fair in both the terminal and the browser. A laggy or unclear
  presentation makes the system feel arbitrary — the exact failure it exists to
  avoid.
- **Accessibility is a first-class requirement**, not a nice-to-have, because the
  reflex layer excludes people by default. `tactical` mode is part of the design,
  not an afterthought, and it preserves the larger (knowledge) half of skill.
- **Determinism needs care.** Input timings are recorded into the action log and
  quantized, so replays use recorded values rather than re-measuring. See
  ADR-0004.
