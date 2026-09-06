# 8. Economy

A living market, built on the systems that already exist. Regions have climates
and produce different things; routes have length and danger; events close passes
and besiege castles. All of that should show up in the price of grain.

The design goal matches the weather system's: **prices should be something a
player can read and act on.** Noticing that iron is dear in the mountains because
the pass is shut, and that you happen to be going that way, should feel like the
same kind of insight as noticing a storm front and leaving early.

---

## Goods

The unit of trade is a **good** — an item with market behavior. Most items aren't
goods; a quest token has no market.

```yaml
goods:
  - id: grain
    name: "Grain"
    baseValue: 4
    category: food
    weight: 1
    perishable: {ticksToSpoil: 480}
    elasticity: 0.4        # necessity: demand barely falls as price rises
    producedBy: [farmland]
    consumedBy: [settlement]

  - id: iron-ingot
    name: "Iron Ingot"
    baseValue: 30
    category: metal
    weight: 8
    elasticity: 1.3        # luxury-ish: demand collapses when it gets dear
    producedBy: [mine]
    consumedBy: [smithy, garrison]
```

`elasticity` is the single most important number: it decides whether a shortage
means *expensive* (food) or *absent* (luxuries). Getting these right is most of
economic balance.

---

## Markets

Every settlement with trade has a **market**: a stock level and a price per good.
Both move.

```yaml
markets:
  - id: fenmoor-market
    location: fenmoor
    size: hamlet                    # hamlet | village | town | city
    wealth: 0.3                     # 0-1, scales stock depth and price floors
    produces:
      - {good: grain, perTick: 0.8}
      - {good: wool,  perTick: 0.3}
    consumes:
      - {good: iron-ingot, perTick: 0.1}
      - {good: salt,       perTick: 0.2}
    stock:
      grain: {initial: 400, capacity: 800}
      iron-ingot: {initial: 6, capacity: 20}
```

### Price formation

One formula, applied per good per market. Deliberately simple enough that a
player can build an intuition for it:

```
scarcity  = clamp(target_stock / max(current_stock, 1), 0.25, 4.0)
price     = baseValue
            × scarcity ^ elasticity          # supply and demand
            × (1 + transport_cost)           # distance from a producer
            × market_wealth_factor           # a city pays more than a hamlet
            × event_pressure                 # sieges, closed passes, disasters
            × haggle_factor                  # the player's charisma and skill
```

Stock moves each tick: production adds, consumption removes, and stock drifts
toward its target through **trade flow** with connected markets. That last part is
what makes the map matter — a market's price depends on the routes reaching it.

### Trade flow is the reason routes exist

Connected markets equalize, slowly, limited by the route between them:

```
flow = price_gap × route_capacity / (route.ticks × danger_factor)
```

So:

- A long road means prices stay different at the two ends — and a profit for
  whoever makes the trip.
- A **dangerous** road throttles flow, so bandit country is expensive country.
- A **closed** route (blizzard, landslide, the Ashfell erupting) cuts flow to
  zero, and prices on both sides diverge within days.

That last one is the payoff for building weather and events first. When the pass
shuts, iron in the mountain towns gets dear and grain rots in the lowlands, and
the player who noticed the omens and stocked up is *rewarded for reading the
world*. No special-case code — it falls out of the flow equation.

---

## Events move prices

The event system feeds the economy directly, which is where a market simulation
earns its cost:

| Event | Economic consequence |
|---|---|
| Pass closes (landslide, blizzard) | Trade flow → 0; prices diverge across the break |
| Eruption / ash-fall | Farmland production drops for a season; food prices climb everywhere downwind |
| Siege | A settlement's inflow stops and consumption continues; food spirals |
| Eclipse / celestial | Usually nothing mechanical — but a `panic` modifier is available for a superstitious world |
| Plague | Consumption drops, production drops harder, luxuries collapse |

```yaml
# Inside a pressure event's aftermath
aftermath:
  - {closeRoute: {route: mountain-pass, permanent: true}}
  - {marketShock: {region: the-range, category: food, mult: 2.5, decayTicks: 600}}
```

Shocks decay, so the world recovers — on a timescale the player can watch.

---

## Merchants and haggling

A merchant is an actor with a `merchant` block, buying and selling against its
market's prices with a spread.

```yaml
- id: peddler
  kind: actor
  merchant:
    market: traders-post-market      # or `mobile: true` to carry its own prices
    spread: 0.25                     # buys at 0.875×, sells at 1.125×
    buys: [category: food, category: metal]
    sells: [grain, salt, rope, dagger]
    capital: 200                     # can't buy what it can't afford
    restockTicks: 48
```

**Haggling** is where charisma finally does something. It's a small,
skill-adjacent negotiation rather than a stat check:

- Charisma sets how far the price *can* move (`maxSwing`).
- The player makes an offer; the merchant accepts, counters, or takes offense.
- Pushing too hard risks souring the merchant — worse prices, or refusal to trade
  for a while. Knowing when to stop is the skill.
- Local knowledge helps: if you know grain is cheap two towns over, that becomes
  a dialog option with real leverage.

This reuses the scene system entirely. `mace.core` ships a generic haggle scene
that any merchant can point at.

---

## Cost and containment

A market simulation is a real subsystem, and it needs the same guard rails as the
weather model:

**Lazy evaluation.** Markets aren't stepped every tick. A market's state is a pure
function of `(seed, last_evaluated_tick, current_tick, connected route states)`,
so it's fast-forwarded when the player arrives or when something queries it. A
hundred markets cost nothing until they're looked at.

**Deterministic.** All market randomness — production jitter, merchant restock,
caravan arrivals — draws from the `economy` stream. See ADR-0004.

**Bounded.** Hard floors and ceilings per good (`0.25×` to `4×` base) so no
feedback loop can run away and no exploit can print money. The scarcity clamp in
the price formula is that bound.

**Optional.** `game.rules.economy: simple` gives fixed item values and plain
buy/sell scenes with no simulation at all. A tight 45-minute story game shouldn't
have to think about grain. Full simulation is `economy: market`.

**Not required for play.** A player who ignores trade entirely should never be
blocked. Money is a lever, not a gate — quest-critical items are never purchasable
only.

---

## What the player sees

Same principle as weather and omens: no numbers, no dashboards.

- Merchants comment on their own prices. *"Grain? You'll pay for grain this week.
  Nothing's come over the pass since the mountain went."*
- The journal records prices you've personally seen, so you can compare towns
  without taking notes.
- News and rumor carry economic information the same way they carry event
  news — a trader on the road tells you what's dear where.
- The map can optionally shade regions by the price of a chosen good, for players
  who want to trade seriously.

The intended experience is that a player who pays attention discovers, on their
own, that there's money in carrying salt north — and that a player who doesn't
never feels they were required to.

---

## Phasing

Economy is **not** phase 1. Order matters:

1. **Phase 1** — items have `baseValue`; `mace.core` ships buy/sell scenes.
   `economy: simple`. Enough for a merchant to be worth talking to.
2. **Phase 5** — goods, markets, stock, price formation, trade flow between
   connected markets. `economy: market`.
3. **Phase 6** — event shocks, haggling as a real negotiation, merchant capital,
   caravans as moving markets, the map's price overlay.

Building it before travel, weather, and events exist would mean simulating an
economy with nothing to react to. The whole appeal is the coupling.
