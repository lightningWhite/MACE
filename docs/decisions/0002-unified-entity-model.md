# ADR-0002 — One Entity type replaces player / interactiveElement

**Status:** Accepted

## Context

The v0 templates define `player.yml` and `interactiveElement.yml` as separate
types. They are ~90% identical — the same seven stats with the same four-field
shape, the same possessions, skills, combat actions, and environment responses.
`player` adds `creationPoints` and `location`; `interactiveElement` adds
`visible`, `locked`, and `actions`.

The duplication is already causing drift. `interactiveElement.yml` has a stray
`temp` field on `strength` that the others don't. The comment blocks are copied
verbatim between the two files, so a fix to one won't reach the other. And the
name "interactive element" covers characters, monsters, swords, doors, and
chests — things with genuinely different needs — while excluding the player, who
is the most character-like thing in the game.

Separately, both templates mix static definition with runtime state: `max` is a
property of what a troll *is*, `current` is a property of one troll *right now*.

## Decision

**One `Entity` type**, discriminated by `kind`:

`actor` · `item` · `fixture` · `container` · `portal`

The player is an entity with `playable: true`, referenced by `game.player.entity`.
`kind` selects which optional field groups apply and what verbs a front-end
offers — it does not branch engine logic.

Separately and consequently: **content is frozen, state is separate.** Entity
definitions carry `base`; a session holds instances with `pools`, `modifiers`,
and `flags`.

## Alternatives considered

**Keep them separate.** Simplest diff from today. Rejected: the drift already
happening will only get worse, and it makes the library unusable — you couldn't
`extends` a library NPC into a player character, or promote a companion.

**Deep type hierarchy** (`Entity` → `Actor` → `Character` → `Player`). Familiar
OO shape. Rejected: content isn't code, inheritance hierarchies in data get
rigid fast, and the interesting reuse is *horizontal* (this troll is like that
troll) not vertical. `extends` gives horizontal reuse without a type tree.

**Pure component/ECS model** — entities as bags of arbitrary components. Maximum
flexibility and genuinely the "right" answer for a big engine. Rejected as
overkill: it makes authoring harder (an author must know which components to
attach), makes validation and the wizard's UI much more complex, and buys
flexibility this project doesn't need yet. `kind` plus optional field groups is a
lightweight approximation, and `custom` covers the escape hatch.

## Consequences

- Roughly half the template text disappears, and stat definitions can't drift.
- Library reuse works properly: a game can `extends` a library NPC to make its
  protagonist.
- Companions, mounts, and player-switching become possible with no model change.
- `kind` must not become a switch statement in the engine. Every behavioral
  difference belongs in optional field groups. This needs watching during review.
- `custom: {str: any}` is an intentional loophole for author-defined attributes.
  It's unvalidated by design; the wizard should steer authors to real fields
  first and treat `custom` as advanced.
