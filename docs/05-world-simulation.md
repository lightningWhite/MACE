# 5. World Simulation

The goal: a player who travels the same road twice should have two different
journeys, and both should feel like weather rather than like a random number
generator. That means the world needs **memory and momentum** — storms that
approach, linger, and pass; seasons that shift what's likely; nights that fall on
schedule.

Five layers, each built on the one below.

```
  ┌───────────────────────────────────────────────┐
  │ 5. World events     eclipses, eruptions, slides│  scheduled or building
  ├───────────────────────────────────────────────┤
  │ 4. Local weather    the condition you're in   │  what the player sees
  ├───────────────────────────────────────────────┤
  │ 3. Fronts           storms crossing the map   │  gives weather direction
  ├───────────────────────────────────────────────┤
  │ 2. Climate          what's likely, per season │  gives weather character
  ├───────────────────────────────────────────────┤
  │ 1. Clock & calendar tick → day part → season  │  the heartbeat
  └───────────────────────────────────────────────┘
```

Every layer is content-defined. `mace.core` ships sane defaults so a small game
can ignore all of this and still have day and night.

---

## Layer 1 — Clock and calendar

A **tick** is the atomic unit. `game.world.minutesPerTick` (default 30) gives it
real-world meaning; `calendar.ticksPerDay` (default 48) closes the loop.

Day parts are declared, not hard-coded, so a game on a tidally-locked planet or
in a lightless undercity can define its own:

```yaml
# packs/mace.core/calendars/standard-year.yml
- id: standard-year
  ticksPerDay: 48
  dayParts:
    - {id: dawn,  name: "dawn",      startTick: 10, light: 0.5}
    - {id: day,   name: "daylight",  startTick: 14, light: 1.0}
    - {id: dusk,  name: "dusk",      startTick: 36, light: 0.5}
    - {id: night, name: "night",     startTick: 40, light: 0.15}
  seasons:
    - {id: spring, name: "Spring", days: 30}
    - {id: summer, name: "Summer", days: 30, dayPartShift: {dawn: -3, night: +3}}
    - {id: autumn, name: "Autumn", days: 30}
    - {id: winter, name: "Winter", days: 30, dayPartShift: {dawn: +3, night: -3}}
```

`dayPartShift` gives long summer evenings and short winter days without a
sun-position model. Effective light level is
`dayPart.light × weather.visibility`, and that single number feeds stealth,
ranged combat accuracy, encounter detection, and description selection.

This replaces v0's `lightLevels` duration list. The v0 model rotated light levels
independently of everything else; anchoring day parts to a tick-of-day means
"you should reach the bridge by nightfall" is a statement the engine can make
truthfully.

---

## Layer 2 — Climate

A climate is a **weighted preference plus a transition matrix**, per season.
Preferences say what a place is like; transitions say how weather actually
changes.

```yaml
# packs/fantasy.core/climates/temperate.yml
- id: temperate
  name: "Temperate Lowlands"
  seasons:
    autumn:
      temperature: {min: 2, max: 16}
      weights: {clear: 25, overcast: 30, drizzle: 20, rain: 15, fog: 8, storm: 2}
    winter:
      temperature: {min: -12, max: 3}
      weights: {clear: 20, overcast: 30, light-snow: 25, blizzard: 5, fog: 10, sleet: 10}
  transitions:
    clear:      {clear: 60, overcast: 35, fog: 5}
    overcast:   {overcast: 45, clear: 20, drizzle: 25, rain: 10}
    drizzle:    {drizzle: 40, rain: 25, overcast: 35}
    rain:       {rain: 45, storm: 10, drizzle: 30, overcast: 15}
    storm:      {storm: 30, rain: 50, overcast: 20}
    blizzard:   {blizzard: 35, light-snow: 50, overcast: 15}
```

Each tick, the next condition is drawn from `transitions[current]`, reweighted by
`seasons[current_season].weights`. The transition matrix supplies coherence — you
don't jump from clear to blizzard — and the seasonal weights supply character.
Temperature also selects between physically-paired conditions: the same "wet"
draw becomes `rain` above freezing and `light-snow` below.

**Hand-authored sequences are still supported.** The v0 `conditionSequences` idea
is good for authored drama, so `climate.sequences` lets an author write an exact
progression that plays out uninterrupted once selected. The engine uses Markov
transitions by default and sequences when one is chosen, then returns to Markov.

Weather runs **per region**, not globally. Each location belongs to a region;
each region has a climate. A `location.climate` override pins a place
permanently — Dark Mountain is always snowing and dark regardless of the season,
which is exactly the v0 `envOverrides` intent.

---

## Layer 3 — Fronts

This is what makes the weather feel like a world rather than a slot machine.

A **front** is a weather system with a life of its own, moving across the region
graph:

```jsonc
{
  "kind": "storm",
  "intensity": 0.8,
  "at": "northern-range",
  "heading": ["northern-range", "greenfell", "fenmoor", "the-marches"],
  "speedTicks": 6,          // ticks per region hop
  "lifespanTicks": 54,
  "biases": {"storm": 5.0, "rain": 3.0, "clear": 0.1}
}
```

While a front occupies a region, its `biases` multiply that region's transition
weights, and its intensity decays as it ages. The region ahead of the front gets
a fraction of the bias — which is how a player gets **foreshadowing**:

> The wind has shifted. Away north, the sky over the range has gone the color of
> a bruise.

Fronts are generated on the `weather.fronts` stream, at a rate set by the
climate's `frontFrequency`, with the origin biased toward `climate.prevailing`
regions. Two or three fronts alive at once across a map is plenty.

This gives four properties that a per-region Markov chain alone can't:

1. **Correlation across space** — neighbors have related weather.
2. **Predictability** — a player can learn to read the sky and choose to wait a
   day. That's skill, which is the point.
3. **Direction and narrative** — "the storm came down out of the north."
4. **Cheap** — a handful of objects, one hop every few ticks.

---

## Layer 4 — Local weather and its consequences

The condition at a location is: its hard override, else its region's current
condition modulated by elevation and biome, at the front-adjusted intensity.

Weather has to *matter*, or none of the above is worth the code:

| Property | Effect |
|---|---|
| `visibility` | Multiplies effective light. Feeds stealth, ranged accuracy, encounter chance, and which description variant is shown. |
| `travelMultiplier` | Route `ticks` scale by it. A storm turns a 3-tick road into a 5-tick slog. |
| `blocksTravel` | Hurricanes and blizzards close routes entirely — the player must shelter. |
| `modify` | Blanket stat changes on anyone exposed (`speed -5` in deep snow). |
| `tags` | `wet`, `cold`, `dark`, `windy`. Entities respond to tags, not just to specific conditions, so a new snow type automatically affects everything that reacts to `cold`. |

And entities respond individually — the v0 `envResponses` idea, kept:

```yaml
# an orc, in fantasy.core
env:
  - when: {weatherTag: [dark]}
    modify: [{stat: strength, add: 15}, {stat: stealth, add: 20}]
  - when: {weatherTag: [wet]}
    modify: [{stat: speed, add: -5}]
```

Encounter tables also read weather, so the ogre that hunts the road in fog stays
home in the sun. See [Travel & Encounters](06-travel-and-encounters.md).

**Shelter** matters: locations flagged `indoors: true` suppress `modify` and
`visibility` effects. That gives the inn a reason to exist and makes "wait out
the storm" a real decision with a real cost in days.

### Exposure and rest

Weather that only slows you down is scenery. **Exposure** is what makes it bite.

While a character is outdoors in a condition tagged `cold`, `wet`, or `severe`,
an `exposure` pool accumulates, scaled by the condition's intensity and reduced
by clothing, shelter, and endurance. Past a threshold it begins draining the
vital pool and applying penalties — the blizzard is genuinely trying to kill you.

**Rest** is its counterpart, and its cost is time. Resting clears exposure and
restores pools, but advances the clock by hours — which runs down quest
deadlines, moves weather fronts, and lets event pressure keep rising. So the
decision "shelter here until it passes, or push on cold" is a real one with real
stakes on both sides, and neither answer is always right.

Hunger and thirst use the same machinery but are **optional**, enabled per game:

```yaml
rules:
  survival: [exposure, rest]                    # default
  # survival: [exposure, rest, hunger, thirst]  # a survival game
  # survival: []                                # disabled entirely
```

Not every world wants to be about rations. Exposure and rest are in by default
because they're what give the weather model teeth; the rest is a choice.

---

## Layer 5 — World events

Weather is the world's background hum. **Events** are its punctuation: the
volcano that has been smoking for a week, the comet nobody can explain, the
eclipse the priests have been counting down to, the hillside above the pass that
is going to come down eventually.

The design goal is the same one that makes the front system work: an event should
be **something the player can see coming and make a decision about**. A disaster
that fires without warning is a dice roll wearing a costume. A disaster you can
feel building is a story.

### Three kinds of event

They differ in *how their timing is determined*, which is what determines how the
player can relate to them.

| Kind | Timing | Player can | Examples |
|---|---|---|---|
| **Celestial** | Exactly scheduled by the calendar | *Know the date* | Eclipse, comet, conjunction, blood moon, meteor shower, spring tide |
| **Pressure** | Uncertain — builds toward a threshold | *Read the omens* | Eruption, landslide, avalanche, flood, dam break, plague, war |
| **Triggered** | Fired by story or player action | *Cause it* | The ritual that wakes the mountain, the dam you break yourself |

The distinction matters because it produces two genuinely different kinds of
play. A celestial event is a **deadline** — you know the eclipse is on day 12, so
you plan around it. A pressure event is a **risk assessment** — the tremors are
getting closer together, so how many more times do you dare take the pass?

---

### Celestial events — knowable, and therefore plannable

Computed from the calendar with a period and a phase. Fully deterministic, no
randomness at all; the same seed isn't even required.

```yaml
celestialEvents:
  - id: total-eclipse
    name: "The Swallowing"
    period: {days: 431}          # recurs on a fixed cycle
    phase: {day: 12}             # first occurrence
    durationTicks: 3
    warnTicks: 480               # omens start ten days out
    global: true                 # visible from everywhere
    announce:
      - "The sun goes out. Not dims — goes out, like a lamp under a cloth."
    while:
      - {setLight: 0.05}                       # night, at noon
      - {weatherTag: [$append, ominous]}
    effects:
      - {setVar: {name: eclipseHappening, value: true}}
    aftermath:
      - {setVar: {name: eclipseHappening, value: false}}
```

Because the timing is a pure function of the calendar, the world can **tell the
player about it**, which is the whole point:

- An **almanac** item or an **astronomer** NPC reports the exact date. That makes
  the almanac worth gold and the astronomer worth finding.
- The wizard shows the author a timeline of every celestial event across a
  typical playthrough, so they can build quests around one on purpose.
- A quest can require an event: *the ritual only works during the Swallowing*.
  Now the player has a hard date, a journey of known length, and a road with
  weather on it. That's a plot, generated by three systems agreeing with each
  other.

Some celestial events should be *rare enough to be unscheduled in practice* — a
comet with a 900-day period in a 40-day game is a once-in-a-campaign wonder that
a few playthroughs will see and most won't. Set `period` long and let the seed
decide whether this world's story includes it.

---

### Pressure events — the volcano that might go

This is the mechanism for "the volcano is about to blow up but I don't know
when." It's the most interesting of the three, and the most careful.

A pressure event carries a hidden accumulator. Each tick it rises; when it
crosses the threshold, the event fires. The rise rate can be modulated by
anything — season, weather, other events, the player's own actions.

```yaml
pressureEvents:
  - id: ashfell-eruption
    name: "The Ashfell"
    regions: [the-range, the-northwood]
    epicenter: dark-mountain

    pressure:
      start: {min: 0.0, max: 0.35}     # seeded: some worlds start closer to the edge
      ratePerTick: 0.0012              # ≈ baseline; threshold at 1.0
      variance: 0.4                    # ±40% jitter per tick, so it isn't a countdown
      threshold: 1.0
      modifiers:
        - {when: {season: [summer]}, mult: 1.4}
        - {when: {var: ritualPerformed}, mult: 4.0}   # the player can hasten it
        - {when: {var: mountainAppeased}, mult: 0.1}  # or hold it off

    omens:
      # Fired probabilistically, with frequency scaling to current pressure.
      # This is the honest signal: more omens genuinely means closer.
      - {atPressure: 0.3, weight: 30, regions: [the-range],
         text: "The snow on the Ashfell has a grey cast to it that it did not have."}
      - {atPressure: 0.5, weight: 40, regions: [the-range, the-northwood],
         text: "A tremor, small enough to doubt. The water in your flask disagrees."}
      - {atPressure: 0.7, weight: 60,
         text: "Birds are leaving the range. All of them, and all at once."}
      - {atPressure: 0.85, weight: 90,
         text: "The ground will not stop shaking. The mountain is lit from inside."}

    imminentAtPressure: 0.9
    imminent:
      announce:
        - "The Ashfell draws a long breath."
      effects:
        - {closeRoute: mountain-pass, reason: "The pass is shaking itself apart."}

    onset:
      announce:
        - "The mountain opens."
      effects:
        - {spawnFront: {kind: ash-fall, intensity: 0.9, at: the-range,
                        heading: [the-range, the-northwood, the-lowlands],
                        lifespanTicks: 400}}
        - {damage: {inRegion: the-range, amount: 40, reason: "the mountain"}}

    activeTicks: 60
    while:
      encounters: ashfall-hazards
      travelMultiplier: 1.8

    aftermath:
      - {closeRoute: {route: mountain-pass, permanent: true}}
      - {reveal: {location: the-new-caldera}}
      - {setVar: {name: ashfellErupted, value: true}}
      - {playScene: after-the-ashfell}     # only if the player is nearby
```

**Why pressure rather than a flat per-tick probability.** A flat probability is
memoryless: the volcano is exactly as likely to erupt on day one as on day thirty,
nothing can foreshadow it honestly, and the player can never learn anything. A
rising accumulator gives the event a *direction*, and direction is what makes the
omens truthful. The player reading "birds are leaving the range" and deciding to
take the long way round is doing the same thing as reading a storm front — and
that's the feeling this whole document exists to produce.

**Why the variance matters.** Without jitter, an attentive player could count
ticks and derive the exact eruption date, which turns the volcano back into a
scheduled event. With `variance`, omens narrow the window without ever closing
it. You can know it's *close*. You can't know it's *Tuesday*. That uncertainty is
the entire experience.

**The player can push.** `pressure.modifiers` reading game vars means the
eruption is something the story can accelerate or delay. A quest to appease the
mountain isn't flavor — it multiplies the rate by 0.1 and genuinely buys the
valley years. A player who performs the wrong ritual multiplies it by 4 and has
to live with that. This is the strongest reason to build events as a simulation
rather than as scripted cutscenes.

---

### Phases

Every event, of any kind, moves through the same lifecycle. Front-ends and
content hook the same names.

```
  dormant ──► building ──► imminent ──► onset ──► active ──► aftermath
             (omens)      (announce,   (the      (hazards,   (permanent
                           last        moment)    modified    world
                           chance)                weather)    change)
```

- **building** — omens fire. The player's only information channel.
- **imminent** — unambiguous. Routes may close, NPCs flee, the world reacts.
  This is the last exit, and it should be *late* — the tension lives in the gap
  between "probably" and "certainly."
- **onset** — the event happens. One dramatic beat.
- **active** — the world is different for a while: hazard encounter tables,
  travel multipliers, spawned weather fronts, blocked routes.
- **aftermath** — **permanent change**. This is what separates an event from a
  weather condition. A landslide closes a route *for the rest of the game*; an
  eruption redraws part of the map. If an event leaves nothing behind, it was a
  cutscene, and should be a scene instead.

### Small events too

Not everything needs a mountain. The same machinery, scaled down, is where most
of the value is — these are cheap to author and constantly change the texture of
a journey:

```yaml
pressureEvents:
  - id: hillside-slip
    name: "The Cutting"
    regions: [the-northwood]
    scope: route                     # affects one route, not a region
    route: north-road
    pressure:
      ratePerTick: 0.004
      modifiers:
        - {when: {weatherTag: [wet]}, mult: 3.0}   # rain is what brings it down
    omens:
      - {atPressure: 0.6, weight: 50,
         text: "The cutting above the road has shed a fan of loose stone since you last passed."}
    onset:
      announce: ["The hillside comes down behind you, unhurried and enormous."]
    aftermath:
      - {setRouteTicks: {route: north-road, ticks: 9}}   # the detour is longer now
```

A landslide made likelier by rain, foreshadowed by loose stone, that permanently
lengthens your main road. Twelve lines, and the world has a memory.

---

### News travels

Events fire whether or not the player is watching, and a world where things only
happen in your presence isn't a world. When an event reaches `onset` outside the
player's current region, it enters a **news queue** and surfaces later through
ordinary channels:

- Encounter entries tagged `news` (a traveller on the road, a rider, a refugee).
- NPC dialog in settlements, via a library scene that reads the queue.
- Visible at distance if `global` or if the epicenter is in view (a column of ash
  is a thing you can see from another region).

News carries **age and distortion**: a rumor three days old and two regions away
arrives garbled and possibly wrong. That's free atmosphere, and it means the
player's information is imperfect in a way that feels like a medieval world
rather than like a notification.

### Author control

Simulation shouldn't cost authors their story beats, so every event supports:

- `earliestDay` / `latestDay` — bound the window without scheduling it. A
  volcano that can't fire before day 5 (so the player has time to learn the
  world) and *must* fire by day 30 (so it can't be missed entirely) is still
  uncertain in the part that matters.
- `{fireEvent: ashfell-eruption}` as an effect — a quest can trigger it outright.
- `{setPressure: {event: ashfell-eruption, value: 0.8}}` — nudge it to the brink
  as an act two beat, and let the simulation deliver act three.
- `requires` conditions — an event that can only fire once the player has seen
  the mountain, so the payoff always lands.

### Budget

The failure mode is a world where a catastrophe happens every other day and none
of them matter. Guidance for authors, and a wizard warning when exceeded:

- At most **one or two major events** per playthrough. `earliestDay`/`latestDay`
  and rate tuning are how you get there.
- **Minor events** (a slip, a flood, a market fire) can be common — three or four
  a playthrough is fine.
- **Celestial events** should mostly be atmosphere; make at most one of them
  matter mechanically, or the calendar starts feeling like a bus timetable.
- Every major event must leave an aftermath. If you can't name what's permanently
  different afterward, cut it.
---

## Determinism

Every layer draws from its own stream: `weather`, `weather.fronts`,
`world.events`, `world.omens`. Adding an events system to a game does not change
the weather a previously-recorded playthrough experienced, and a chatty omen
does not shift the eruption date. See
[ADR-0004](decisions/0004-deterministic-seeded-simulation.md).

Pressure accumulation is deterministic: the jitter is drawn from `world.events`,
so a given seed always produces the same eruption tick. Celestial events need no
randomness at all — they're a pure function of the calendar, which is why they
can be forecast.

**Every region with a climate steps every tick.** The original design here was
to step only the player's region and fast-forward the rest on demand, and the
fast-forward is still in the code — a region that comes into existence
mid-game begins its chain at the playthrough's opening tick and catches up, so
looking at a place late gives the weather it would have had all along.

But it cannot be the normal path once fronts exist. A front's bias is a fact
about *when*: replaying a region's chain on day nine, under day nine's fronts,
would give a different world from having stepped it on days one through eight
under the fronts that were actually there. Stepping everything is a handful of
weighted draws per tick at any map size an author will actually build, and it
is correct. Determinism is worth more than the saving.

---

## What the player actually sees

The simulation is worthless if it's invisible. The front-end should surface it
constantly and cheaply:

- A status line: **`Day 3 · dusk · Fenmoor · light rain, easing`**
- Weather-change narration when it shifts, not every tick.
- Description variants that acknowledge conditions, so the same place reads
  differently in fog at night than in clear noon.
- Front foreshadowing, so a player can *plan*: leave now and beat the storm, or
  wait and lose a day.
- Omens surfaced as ordinary narration, never as a system message. "Birds are
  leaving the range" is the interface; there is no pressure bar.
- A journal that records what you've noticed — omens seen, events survived, dates
  learned from an almanac — so a long game doesn't rely on the player's memory.

The last two are the whole reason these systems exist: they turn weather and
disaster from flavor into decisions. The player should never see a number. They
should look at the sky, or at the birds, and choose.
