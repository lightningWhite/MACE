# 6. Travel & Encounters

> "If they travel from one village to another and have to pass through a forest,
> there may be a chance that sometimes when they travel that path, they encounter
> an Ogre. Sometimes they don't. And maybe 5% of the time they might run into a
> troll."

This is the feature that makes the map feel like distance instead of a menu.

## Travel is a process, not a transition

In v0, a `link` moved you. Here, a **route** is traversed leg by leg:

```
Player chooses "Travel the North Road to Hagan's Castle"  (route: 6 ticks)
  │
  ├─ leg 1  world tick advances → weather applied → encounter roll → flavor line
  ├─ leg 2  ...
  ├─ leg 3  waypoint: Troll Bridge  → waypoint's own encounter table
  ├─ leg 4  ...
  ├─ leg 5  ... encounter fires! → combat → player flees back the way they came
  └─ (journey interrupted; player is between Troll Bridge and the castle)
```

Consequences that fall out for free:

- **Distance is felt.** A six-tick road at 30 minutes a tick is three hours; a
  long journey crosses nightfall and the player has to decide whether to push on
  in the dark.
- **Weather bites.** `travelMultiplier` in rain turns 6 ticks into 9.
- **Journeys are interruptible.** Fleeing mid-route leaves you partway, not
  teleported. Resting mid-route is a choice with a cost.
- **Waypoints have identity.** The Troll Bridge is a real location — it has
  entities, scenes, and its own encounters — but it isn't a destination the
  player picks. That's exactly the v0 "intermediary location" idea, made
  first-class.

### How a leg resolves

Progress along a route is measured in **route ticks** and is fractional. Each
world tick of walking adds `1 / travelMultiplier` of progress, so a storm makes
a tick of walking worth half a tick of road without anyone computing a total in
advance — and the weather is free to change halfway along. A leg boundary is
crossed whenever the whole part of the progress increases, and that's when the
leg flavour and the encounter roll happen.

`blocksTravel` bites at the moment of **setting out**, not partway along. Being
told you can't leave is a decision — shelter here and lose the day — whereas
being stopped three ticks down a road you already committed to is a punishment.
Weather met mid-journey slows you instead, which a blizzard's `travelMultiplier`
does hard enough to hurt.

### Terrain and elevation multiply on top

A road's own `terrain` (docs/07's neighbor, `mace.model.terrain.Terrain`) adds
its own multiplier — a paved highway shrugs off rain that turns a forest track
to mud — and elevation adds a third, on top of both: a route gains
`1.0 + max(0, destinationElevation − originElevation) / 1000` for the whole
road, once, the same granularity `terrain` resolves at. Coming down costs
nothing extra. So a storm on a muddy mountain road stacks all three — weather,
surface, and the climb — and none of it needs an author to compute a total in
advance. See [World Simulation](05-world-simulation.md#layer-4--local-weather-and-its-consequences)
for where `elevation` comes from and what else it already does to the weather
itself.

### Being stopped

A waypoint's `stopIf` ends the journey where it stands. The player is *at* the
waypoint — it's a real location, so its entities, scenes and description all
work — and the engine offers two ways out that no exit provides: **carry on**
and **turn back**. The middle of a bridge is not a place with roads leading off
it, and without those the player would be stranded.

A waypoint that stopped you is deliberately not recorded as passed. Carrying on
while the condition still holds costs nothing and gets nowhere: the troll is
still owed, and you're told so without burning an hour. Once the condition
lifts, the waypoint counts as passed and the journey resumes from exactly where
it stood. Turning back walks the road already walked — a decision with a cost,
not an undo.

```yaml
- id: north-road
  name: "The North Road"
  from: fenmoor
  to: hagans-castle
  ticks: 6
  terrain: forest-track
  dangerLevel: 5
  waypoints:
    - {location: troll-bridge, atTick: 3, encounters: bridge-encounters}
  encounters: forest-road-encounters
  description:
    - {text: "You set out on the rutted track north, under dripping oaks.",
       when: {weatherTag: [wet]}}
    - {text: "You set out on the rutted track north."}
  legDescriptions:
    - {text: "Crows argue in the branches overhead.", when: {dayPart: [day]}}
    - {text: "Something moves in the undergrowth, then doesn't.", when: {dayPart: [night]}}
    - {text: "The rain finds every gap in your cloak.", when: {weatherTag: [wet]}}
```

## Encounter tables

Two-stage resolution, deliberately. It separates "how dangerous is this road"
from "what lives on it" — which is what makes tables tunable and reusable.

**Stage 1 — does anything happen?**
`chance` is rolled once per leg. This is the road's danger dial. An author (or
the wizard) tunes one number.

**Stage 2 — what happens?**
Every entry whose `when` passes is eligible. Weights are normalized *among the
eligible set* and one is drawn.

```yaml
- id: forest-road-encounters
  chance: 0.30            # ~30% of legs have something
  minGapTicks: 4          # never two in a row
  entries:
    - id: ogre-ambush
      weight: 20
      when: [{dayPart: [dusk, night]}]
      cooldownTicks: 60
      scene: ogre-ambush

    - id: troll-toll
      weight: 5           # the "5% troll" — 5/(sum of eligible weights)
      once: true
      scene: troll-demands-toll

    - id: merchant-caravan
      weight: 30
      when: [{dayPart: [dawn, day]}, {not: {weatherTag: [severe]}}]
      scene: caravan-offers-ride

    - id: wolves
      weight: 25
      when: [{any: [{weatherTag: [cold]}, {dayPart: [night]}]}]
      combat: {against: [wolf, wolf, wolf]}

    - id: strange-quiet
      weight: 40
      scene: nothing-much-happens     # atmosphere, not threat
```

### Why normalize among eligible entries

Because it lets authors write `when` conditions without silently changing the
overall danger of a road. At night the caravan drops out and the ogre becomes
proportionally more likely — the road doesn't get *quieter*, it gets *worse*.
That's the intuitive behavior, and it means `chance` remains the single honest
danger dial.

### Anti-clumping

Pure independent rolls produce bad-feeling streaks — three ambushes in a row, or
a long empty road. Two mechanisms, both content-controlled:

- **`minGapTicks`** — a hard floor between encounters on a journey.
- **Pity/pressure** — an internal `pressure` counter per table rises each leg
  nothing happens and adds to `chance`, resetting on a hit. This keeps the
  *average* rate at the authored `chance` while tightening the variance, so roads
  feel consistent in danger without becoming predictable.

Both are deterministic, both are part of state, both replay identically.

### Where tables attach

| Attach point | Rolled when | Typical use |
|---|---|---|
| `route.encounters` | Each travel leg | Ambushes, travelers, hazards |
| `waypoint.encounters` | On reaching the waypoint | The bridge troll specifically |
| `location.encounters` | Each tick spent at the location | Wandering monsters in a dungeon |
| `region.encounters` | Any leg or tick within the region | Region-wide flavor: "you hear wolves" |

`location.safe: true` suppresses all of it. Towns are safe; the wilderness is not.

## Beyond monsters

An encounter table is a general "something happens" mechanism, and worlds feel
much richer when most entries are not fights. Encourage authors (and default the
wizard's suggestions) toward a mix:

- **Threats** — the ogre, the wolves, bandits.
- **People** — a caravan, a pilgrim, a messenger with news of the war.
- **Opportunities** — an abandoned camp, a shrine, a body with a letter on it.
- **Hazards** — a washed-out ford, a rockfall, a wrong turn that costs two ticks.
- **Atmosphere** — nothing happens, but the world says something. These should be
  the *heaviest* weights; they're what makes the dangerous entries land.

A road where 30% of legs produce something and two thirds of that something is
weather, wildlife, and strangers reads as *alive*. A road where 30% of legs
produce a fight reads as a grind.

## Difficulty scaling without a level treadmill

Encounter `when` conditions can read anything, including player state, so an
author who wants scaling can write it explicitly:

```yaml
- id: ogre-pair
  weight: 15
  when: [{expr: "player.stats.strength > 55"}]
```

MACE deliberately does **not** auto-scale encounters to the player. Auto-scaling
undermines the whole premise — if the world levels with you, exploring somewhere
dangerous early has no meaning and getting stronger has no payoff. Regions have
fixed danger; the player is expected to learn where they can survive. The wizard
should show authors a "danger map" of their world so they can shape that
progression on purpose.

## Tuning guidance for authors

The wizard offers these as presets rather than making authors guess at floats:

| Road feel | `chance` | Threat share of weight |
|---|---|---|
| Safe king's highway | 0.10 | 10% |
| Ordinary country road | 0.25 | 25% |
| Wild forest track | 0.35 | 45% |
| Bandit country | 0.45 | 65% |
| The Dark Mountain pass | 0.60 | 80% |

With a 6-tick road at 0.35, a player meets something roughly twice per crossing —
which in play feels like a real journey without becoming tedious.
