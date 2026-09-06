# ADR-0007 — A simulated market economy

**Status:** Accepted

## Context

The first design pass recommended a minimal economy: items carry a `value`,
merchants buy and sell at fixed prices, done. That's the conventional choice for
a text adventure, and it's cheap.

The counter-argument is coupling. By the time phases 2 and 3 are built, MACE
already has:

- a **region graph** with distinct climates and therefore distinct produce,
- **routes** with real length and real danger,
- **weather** that can close a road,
- **events** that can close one permanently, besiege a settlement, or ruin a
  harvest.

Every one of those is an input a market model wants, and none of them costs
anything extra to reuse. A fixed-price economy leaves all of it on the floor.

## Decision

**Build a simulated market economy** — goods with elasticity, per-settlement
stock, price formation from scarcity, and trade flow between connected markets
throttled by route length and danger.

The decisive property: when the Ashfell erupts and the pass closes, iron gets
dear in the mountain towns **because trade flow actually stopped**, not because a
script fired. A player who read the omens, understood what a closed pass means,
and bought iron beforehand is rewarded for reading the world — which is the same
loop the weather and combat systems are built around.

Full design in [Economy](../08-economy.md).

## Alternatives considered

**Fixed item values with buy/sell scenes.** The original recommendation. Cheap,
predictable, trivially balanced, and enough for a merchant to be worth talking
to. Rejected as the ceiling, **retained as `economy: simple`** — a per-game mode
so short story-driven games don't have to think about grain. Nothing is lost by
having both.

**Regional price variation only** (no stock, no flow — just a multiplier per
region per good). A middle path that gets "grain is dear in the mountains" for
almost nothing. Rejected because it can't react to events: a closed pass has no
effect on a static multiplier, and reacting to events is the entire reason to
build this.

**Full agent-based economy** with individual merchants holding inventory and
making decisions. More emergent, considerably more expensive, and much harder to
keep deterministic and debuggable. Rejected as more simulation than the game can
express — the player only ever sees prices and stock, so simulating below that
level buys nothing they can perceive.

## Consequences

- **Events gain economic teeth**, which makes them matter even to a player who
  wasn't in the region. That's a large gain in world coherence for a small amount
  of coupling.
- **Routes gain a second purpose.** Length and danger already shaped travel; now
  they shape prices, and a dangerous road is expensive country in a way the
  player can feel.
- **Charisma finally does something**, via haggling as a small negotiation rather
  than a stat check.
- **Cost.** This is a real subsystem, comparable in size to the weather model.
  It's scheduled for phase 5, after the world it reacts to exists — building it
  earlier would mean simulating in a vacuum.
- **Performance is handled by laziness.** A market's state is a pure function of
  `(seed, last evaluated tick, current tick, connected route states)`, so markets
  are fast-forwarded on query rather than stepped every tick.
- **Runaway loops are bounded** by a hard scarcity clamp (0.25×–4× base value).
  This is a deliberate cap on realism in exchange for never having to debug a
  hyperinflation bug in someone else's game.
- **It must never gate play.** Quest-critical items are never purchase-only, and
  a player who ignores trade entirely must be able to finish. Economy is a lever,
  not a key. This needs enforcing in review of community packs.
