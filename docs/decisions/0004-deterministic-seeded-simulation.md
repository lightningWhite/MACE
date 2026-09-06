# ADR-0004 — Deterministic simulation with named RNG streams

**Status:** Accepted

## Context

MACE is a game about variability: weather that differs every playthrough,
encounters that may or may not happen, combat with bounded randomness. The naive
implementation is to call `random.random()` wherever a decision is needed.

That choice, made casually early, forecloses a surprising number of things later.

## Decision

**The engine is deterministic.** A playthrough is fully described by:

```
(pack ids + versions, root seed, ordered action log)
```

Replaying that triple reproduces the session exactly, event for event.

**All randomness comes from named streams.** Each stream is derived
`PCG64(hash(root_seed, stream_name))`, and each stream's position is part of the
game state.

```python
rng = state.rng.stream("encounters.north-road")
```

`random` is never called directly in `mace.engine`; an import lint enforces it.

Naming convention: `weather`, `weather.fronts`, `world.events`,
`encounters.<routeId>`, `combat.<combatId>`, `loot`, `ambient`, and per-entity
streams keyed by instance id.

## Alternatives considered

**Global `random` with a seed.** One line, works for reproducing a run. Rejected:
a single global sequence means every consumer shifts every other consumer. Adding
a subsystem, changing the number of exchanges a fight takes, or reordering two
independent operations all silently change unrelated outcomes. Golden tests
become impossible to maintain, and multiplayer becomes impossible outright.

**Non-deterministic, snapshot-only saves.** Simplest. Rejected: it costs replay,
shareable playthroughs, reproducible bug reports, cheap saves, and any future
server-authoritative mode. All for the sake of not passing a seed around.

**Deterministic but with a single stream per session.** Halfway. Rejected for the
same reason as global `random` — cross-subsystem interference is the actual
problem, and one stream doesn't solve it.

## Consequences

Things this buys:

- **Golden replay tests.** A seed and an action log produce an expected event
  stream. This is the contract that would let a TypeScript port of the engine be
  verified against the Python one (see ADR-0005).
- **Tiny saves.** Seed plus action log, with snapshots as an optimization.
- **Reproducible bug reports.** "Here's my save" is a complete repro.
- **Shareable playthroughs.** Replay someone's run exactly.
- **Author iteration.** Fixed-seed playtesting means a change in the pack is the
  only variable that changed.
- **A path to multiplayer.** Server-authoritative simulation with client
  prediction needs exactly this property.

Things it costs:

- **Discipline.** No wall clock, no `set` iteration order, no dict ordering
  assumptions across versions, no floating-point drift across platforms. Money
  and stat math should use integers or fixed-point where feasible.
- **Ordering is now semantics.** The tick pipeline's step order is part of the
  contract; reordering it is a breaking change that invalidates golden files.
- **New subsystems must claim a stream** and document it, or they'll disturb
  existing sequences.
- **Combat timing input must be quantized.** Wall-clock milliseconds go into the
  action log as recorded values, so replay uses the recorded number rather than
  re-measuring. Elapsed times are rounded to a fixed granularity so floating-point
  differences across platforms can't diverge a replay.
