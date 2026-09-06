# ADR-0003 — Structured conditions and effects, not magic strings

**Status:** Accepted

## Context

The v0 templates express game logic as strings:

```yaml
conditions:
  - "player.location == castle"
modifiers:
  - "player.possessions.gold: '+1'"
  - "player.hitpoints.current: player.hitpoints.max"
  - "_attack_"
```

Four problems, all serious:

1. **Quoting carries meaning invisibly.** `'+1'` is a literal and
   `player.hitpoints.max` is a reference, distinguished only by quotes — which
   YAML itself may add or strip, which vanish in a rendered diff, and which no
   author will remember reliably.
2. **Nothing can validate it.** A typo in `player.hitponts` is discovered at play
   time, three hours in, if at all.
3. **The wizard can't build it.** `defineConditions()` in `src/wizard.py` gives
   up and prints syntax instructions, with a TODO admitting it should present a
   list of attributes instead. That TODO is the whole problem.
4. **Magic keywords don't scale.** `_attack_` sitting inside a modifiers list is
   a sentinel that means something structurally different from everything around
   it. The second and third such keyword make it a language with no grammar.

## Decision

**Structured, typed conditions and effects**, with an explicit `expr` escape
hatch for the cases structure doesn't cover.

```yaml
when:
  - {hasItem: {actor: player, item: fantasy.core:gold, qty: 10}}
  - {weather: [rain, storm]}
  - {expr: "player.stats.hitpoints < player.stats.hitpoints.max * 0.25"}

effects:
  - {adjustStat: {actor: player, stat: hitpoints, delta: -8, reason: "troll's club"}}
  - {setStat: {actor: player, stat: hitpoints, value: {expr: "player.stats.hitpoints.max"}}}
  - {startCombat: {against: [troll]}}
```

Values are literals unless wrapped in `{expr: ...}`. There is no quoting
convention to remember.

The `expr` language is a **restricted, non-Turing-complete grammar**:
comparisons, arithmetic, boolean operators, dotted paths, and a whitelist of
functions (`min`, `max`, `abs`, `count`). It is parsed by a hand-written parser
in `mace.engine.expr`. **`eval` and `exec` are never used on content** — packs
are untrusted community input. The grammar as built is specified in
[Schema Reference § Expressions](../04-schema-reference.md#expressions-expr).

## Alternatives considered

**Keep strings, write a real parser for them.** One grammar to learn, terse to
write. Rejected: the wizard would have to *generate* correct syntax and
round-trip it back into UI controls, which is strictly harder than emitting
structured data. And the terseness is only a win for people who already know the
syntax — the exact people who aren't the target audience.

**Structured only, no `expr` at all.** Cleanest and fully validatable. Rejected:
there will always be one more comparison an author needs, and without an escape
hatch they'd be blocked entirely or the structured vocabulary would grow forever.
`expr` is the pressure valve — and its usage is a useful signal about what the
structured vocabulary is missing.

**A general scripting language (Lua, Starlark, sandboxed Python).** Maximum
power. Rejected: sandboxing is a security commitment nobody wants to maintain, it
breaks the "no code required" premise, it can't be represented in the wizard's
UI, and it makes determinism and validation much harder.

## Consequences

- Every condition and effect is schema-validated, so typos are caught at author
  time with a file, a line, and an id.
- The wizard can present a guided builder and render conditions back as English —
  the single biggest authoring usability win available.
- The web editor can display and edit logic as UI controls rather than a text box.
- More verbose YAML. Accepted: most authors will never write it by hand, and
  verbosity that can be validated beats terseness that can't.
- A vocabulary of effect types must be maintained, and it will grow. That's fine —
  growth is visible, reviewable, and documented, unlike a growing set of magic
  keywords.
- The expression parser is real work and needs its own test suite. Small, bounded,
  and worth it.
