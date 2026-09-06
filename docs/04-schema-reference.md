# 4. Schema Reference

Field-by-field reference for every content type. This document is the
explanation; the enforcement is in two places, and they cover different moments.
`schemas/` validates a file **as authored** — `extends` present, inherited
fields absent, merge sentinels intact — and is what CI and an author's editor
read. The pydantic models in `src/mace/model/` validate the same content
**after** the loader has resolved all of that. Both are generated from the same
source: the models. See [`schemas/README.md`](../schemas/README.md).

Notation: `?` marks an optional field. `[T]` is a list of `T`. `Ref` is a content
id, bare or `pack:id` qualified.

---

## `pack.yml` — Pack manifest

| Field | Type | Notes |
|---|---|---|
| `id` | str | Dotted namespace, e.g. `fantasy.core`. Globally unique. |
| `name` | str | Human-readable. |
| `version` | semver | Bump minor for additions, major for breaking id/shape changes. |
| `kind` | `library` \| `game` | Games appear in the play menu; libraries don't. |
| `maceVersion` | range | Engine versions this pack works with, e.g. `^0.1`. |
| `authors` | [str] | |
| `license` | str? | SPDX id. Content packs default to CC-BY-4.0. |
| `description` | str? | |
| `tags` | [str]? | Genre and theme tags for the gallery. |
| `requires` | [{id, version}]? | Dependency packs. Resolution order matters. |

---

## Entity

The universal noun. Files under `entities/`.

| Field | Type | Notes |
|---|---|---|
| `id` | str | kebab-case, unique in pack. |
| `extends` | Ref? | Inherit from another entity. |
| `kind` | `actor`\|`item`\|`fixture`\|`container`\|`portal` | Default `fixture`. |
| `name` | str | Displayed name. |
| `description` | str \| [Descr]? | See [conditional description](#conditional-description). |
| `tags` | [str]? | Free-form. Used by encounter tables and effects for group targeting. |
| `playable` | bool? | Marks a player-controllable actor. Exactly one per game is chosen in `game.yml`. |
| `visible` | bool? | Default `true`. Hidden entities exist but aren't listed. |
| `stats` | {name: Stat}? | actors only. |
| `pools` | {name: int}? | Starting pool values; defaults to the stat's `base`. |
| `inventory` | [{item: Ref, qty: int}]? | |
| `equipment` | {slot: Ref}? | Slots are declared by the game (`mainHand`, `armor`, ...). |
| `skills` | {Ref: int}? | Proficiency 0–100 with a given item/technique. Grows with use. |
| `disposition` | `friendly`\|`neutral`\|`hostile`? | Starting stance toward the player. |
| `combat` | Combat? | See [Combat profile](#combat-profile). |
| `env` | [EnvResponse]? | How environment conditions modify this entity. |
| `scenes` | [Ref]? | Interactions offered when the player engages this entity. |
| `flags` | [str]? | Initial boolean flags, e.g. `locked`, `lit`, `talked-to`. |
| `item` | ItemProps? | `kind: item` only. |
| `container` | {capacity?: int, contents?: [{item, qty}]} | `kind: container` only. |
| `portal` | {route: Ref, requiresItem?: Ref} | `kind: portal` only. |
| `custom` | {str: any}? | Author-defined attributes, readable from `expr`. |

### Stat

| Field | Type | Notes |
|---|---|---|
| `base` | number | Value before any modifier. |
| `max` | number? | Cap. Defaults to 100 for abilities; required for pools. |
| `min` | number? | Default 0. |
| `customizable` | bool? | Player may spend creation points here. |
| `growth` | `none`\|`slow`\|`normal`\|`fast`? | How fast it improves through use. Default `none`. |

### ItemProps

| Field | Type | Notes |
|---|---|---|
| `weight` | number? | |
| `stackable` | bool? | Default true for items with no state. |
| `equipSlot` | str? | Which slot it occupies when equipped. |
| `damage` | {min, max, type}? | For weapons. `type` is author-defined (`slash`, `pierce`, `plasma`). |
| `armor` | number? | Damage reduction. |
| `moves` | [Ref]? | Combat moves this weapon grants its wielder. |
| `use` | {effects: [Effect], consumed?: bool}? | What happens when used from inventory. |
| `baseValue` | number? | The price anchor. A `simple` economy uses it as the price; a `market` one prices around it. |

### EnvResponse

| Field | Type | Notes |
|---|---|---|
| `when` | Condition | Usually `{weather: [...]}` or `{dayPart: [...]}`. |
| `modify` | [{stat, add? , mult?}] | Applied while the condition holds. |
| `effects` | [Effect]? | One-shot effects fired on entering the condition. |

### Conditional description

```yaml
description:
  - {text: "A stone bridge over black water.", when: {dayPart: [day, dawn]}}
  - {text: "You can hear the river more than see it.", when: {dayPart: [night]}}
  - {text: "A stone bridge, slick with rain."}      # no `when` = default
```

First match wins; the unconditioned entry is the fallback.

---

## Location

Files under `locations/`.

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `extends` | Ref? | |
| `name` | str | |
| `type` | str? | Author-defined: `settlement`, `wilderness`, `dungeon`, `station`. |
| `description` | str \| [Descr]? | |
| `region` | Ref? | Which region (and therefore climate) this belongs to. |
| `biome` | Ref? | Overrides the region's biome for this spot. |
| `climate` | ClimateOverride? | Hard override — always snowing on Dark Mountain. |
| `indoors` | bool? | Shelters the player from weather and exposure. Default false. |
| `visible` | bool? | Undiscovered locations aren't shown on the map. Default true. |
| `discovered` | bool? | Whether the player starts knowing about it. Default follows `visible`. |
| `entities` | [Ref]? | What's here at game start. |
| `scenes` | [Ref]? | Interactions available at the place itself (not an entity). |
| `onArrive` | Ref? | Scene played when the player arrives. |
| `encounters` | Ref? | Encounter table rolled while the player lingers here. |
| `safe` | bool? | Suppresses encounters. Good for towns and inns. |
| `exits` | [Exit] | Where you can go. |
| `mapPosition` | {x, y}? | For the map view. Optional — the layout engine can infer it. |
| `flags` | [str]? | |

### Exit

| Field | Type | Notes |
|---|---|---|
| `to` | Ref | Destination location. |
| `route` | Ref? | The route taken. If omitted, a default 1-tick route is synthesized. |
| `label` | str? | Overrides the default "Travel to X". |
| `when` | [Condition]? | Gate the exit — a locked gate, a quest requirement. |
| `hiddenUntil` | [Condition]? | Secret passages. |

### ClimateOverride

Bypasses the climate model for one place rather than biasing it. Every field is
optional; the ones you set are the ones that stop moving.

| Field | Type | Notes |
|---|---|---|
| `condition` | Ref? | The weather condition that always holds here. |
| `dayPart` | Ref? | A day part that always holds here — caves, deep forest. |
| `locked` | bool? | Whether the override resists fronts moving through. Default false. |

---

## Route

The connection between two locations, and the most important upgrade over v0's
`links` + `subLocation`. Files under `routes/`.

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `name` | str? | "The North Road" |
| `from` / `to` | Ref | Endpoints. |
| `bidirectional` | bool? | Default true. |
| `ticks` | int | Travel time in ticks. This is what makes journeys feel long. |
| `terrain` | Ref? | A terrain definition — affects travel time under weather. |
| `waypoints` | [Waypoint]? | Places passed through en route. The v0 "subLocations". |
| `encounters` | Ref? | Encounter table rolled per leg. |
| `description` | str \| [Descr]? | Framing text at the start of the journey. |
| `legDescriptions` | [Descr]? | Flavor emitted per leg — weather- and time-aware. |
| `when` | [Condition]? | Conditions required to use the route at all. |
| `dangerLevel` | int? | 0–10, a hint used by the wizard to suggest encounter rates. |

### Waypoint

| Field | Type | Notes |
|---|---|---|
| `location` | Ref | A real location definition — waypoints are locations. |
| `atTick` | int? | How far into the journey it's reached. Defaults to even spacing. |
| `stopIf` | [Condition]? | Force a stop here (e.g. a bridge you must cross). |
| `encounters` | Ref? | Waypoint-specific table, in addition to the route's. |

Travel is resolved leg by leg: for each tick of the journey the world advances,
weather is applied, and the route's encounter table is rolled. A journey can be
interrupted mid-route, and the player resumes from where they stopped.

---

## Climate, weather, and time

Detailed in [World Simulation](05-world-simulation.md). Schema summary:

### Region

Files under `regions/`. Weather runs per region, so a world with one region has
one sky and a world with five has five.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | |
| `description` | str \| [Descr]? | How the region reads when named at distance. |
| `climate` | Ref? | The climate governing it. Without one the region has no weather — right for an undercity or a station interior. |
| `neighbors` | [Ref]? | Adjacency for weather-front propagation. Not made symmetric automatically: a front that crosses a range one way and not the other is a thing an author may want. |
| `elevation` | number? | Height above the map's baseline. Colder with altitude, at the climate's `lapseRate`. |
| `biome` | Ref? | The region's default biome, which a location may override. |
| `encounters` | Ref? | A table rolled anywhere in the region, on top of the route's or the location's. |

A location with no `region` falls back to `game.world.startRegion`, so a small
game gets one sky everywhere without saying so four times.

### Climate

Files under `climates/`. Two halves multiplied: `seasons` says what a place is
*like*, `transitions` says how the sky *moves*.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | The high country is the lowlands with colder seasons. |
| `seasons` | {season: SeasonProfile} | Per-season weather weights and temperature band. |
| `transitions` | {weather: {weather: weight}} | Markov transition weights between conditions. A condition with no row holds until something else moves it. |
| `stepTicks` | int? | Ticks between chain steps. Default 1; at thirty minutes a tick that twitches, and 2 reads like weather. |
| `sequences` | [ClimateSequence]? | Hand-authored progressions, for drama a chain will not reliably produce. |
| `frontFrequency` | number? | Chance per tick that a front spawns in a region with this climate. |
| `freezingPoint` | number? | Below this, a condition becomes its `freezesTo`. Default 0. |
| `lapseRate` | number? | Degrees lost per hundred units of a region's `elevation`. Default 0.65. |

**How a step resolves.** The transition row from the current condition is
multiplied by the season's weights and one entry is drawn. A season that lists
*any* weights is a whitelist — a condition it does not mention weighs nothing —
which is how a lowland climate keeps blizzards out of summer without a second
matrix. If the season rules out everything the current condition could become,
the sky stays as it is. The draw is then frozen if the hour's temperature is
below `freezingPoint` and the condition has a `freezesTo`.

The frozen conditions usually borrow the transition rows of their unfrozen
twins — `light-snow` transitions exactly as `rain` does — so one matrix covers
a whole year and a thaw turns snow back into rain on its own.

#### SeasonProfile

| Field | Type | Notes |
|---|---|---|
| `temperature` | {min, max}? | The band days are drawn from. Without one, nothing here ever freezes. |
| `weights` | {weather: number}? | Relative preference this season. |

Each day, per region, a floor and a ceiling are drawn within the band and
lowered by elevation; the temperature *now* interpolates between them by the
day part's `light`. Coldest before dawn, warmest at noon, no sun model.

#### ClimateSequence

| Field | Type | Notes |
|---|---|---|
| `id` | str | So an effect can call for it directly. |
| `weight` | number? | Its chance **per step**, not a share of anything. `0.002` is roughly one step in five hundred. Default 0 — only an effect can start it. |
| `when` | [Condition]? | Extra gating. |
| `steps` | [{condition, ticks}] | The conditions, in order, with how long each holds. |

While a sequence runs, the chain does not interfere. When it ends, the chain
resumes from wherever the sequence left the sky.

### WeatherFront

Files under `weatherFronts/`. This is the *kind* of front; where one actually
is lives in session state. A climate lists the kinds that can form in it and
how often, with `fronts` and `frontFrequency`.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | `name` is a phrase read inside a sentence — "a storm out of the west". |
| `extends` | Ref? | |
| `weight` | number? | Relative likelihood among the kinds a climate offers, once one is forming. Default 1. |
| `when` | [Condition]? | Extra gating. |
| `seasons` | [str]? | Seasons this front can form in. Empty means any. |
| `intensityRange` | [min, max]? | 0–1, default [0.4, 1.0]. Drawn at birth; scales the bias and decays with age. |
| `speedTicks` | int? | Ticks over each region before hopping to the next. Default 6. |
| `lifespanTicks` | int? | How long it lives, whatever its heading has left. Default 54. |
| `hops` | [fewest, most]? | How many regions a heading may cross. Default [2, 4]. |
| `biases` | {weather: number}? | Multipliers on the transition weights of the region the front is over. Above 1 makes a condition likelier, below 1 rarer. |
| `aheadBias` | number? | 0–1, default 0.3. The share of the bias the region *ahead* receives — the foreshadowing dial. 0 means a front arrives without warning. |
| `omen` | str \| [Descr]? | Shown once, as ordinary narration, when the front is one region away and coming this way. |

**How a front resolves.** One roll per tick is made across the whole map, at
the largest `frontFrequency` any region's climate offers — one roll, not one
per region, so adding regions to a map does not silently make a game stormier.
The kind is drawn by `weight` among the eligible kinds, the origin among the
regions whose climate offers that kind, and the heading by walking the
`neighbors` graph without revisiting. A region with no unvisited neighbours
ends the heading, and a front whose heading runs out dies there.

While it lives, a front over a region multiplies that region's transition
weights by its `biases`, scaled by its current strength — its birth intensity
decayed linearly toward nothing at the end of its lifespan. The region ahead
gets `aheadBias` of the same. So a storm approaches, arrives, sits, and eases,
rather than switching on and off.

---

### WeatherCondition

Files under `weatherConditions/`.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | e.g. `blizzard`, `ash-fall`, `ion-storm`. `name` is what the player reads and defaults to the id. |
| `extends` | Ref? | |
| `description` | str \| [Descr]? | Narrated when it begins — conditional, so the same rain reads differently at night. |
| `intensityRange` | [min, max]? | 0–1, default the whole range. Drawn when the condition starts; scales all effects. |
| `visibility` | number? | 0–1 multiplier on the day part's light. Feeds stealth, ranged accuracy, encounter detection, and description selection. |
| `travelMultiplier` | number? | >1 slows travel. |
| `modify` | [{stat, add?, mult?}]? | Blanket stat effects on everyone exposed. |
| `blocksTravel` | bool? | Hurricanes close the roads. |
| `tags` | [str]? | `wet`, `cold`, `dark`, `windy`, `severe` — what `weatherTag`, entity `env` responses, and encounter tables match on. |
| `freezesTo` | Ref? | What this becomes below the climate's `freezingPoint`. |

`location.indoors: true` suppresses the tags, the `modify`, and the visibility
cut — but not the fact of the weather. You can still hear the rain on the inn
roof, and `travelMultiplier` still applies because you cannot be indoors and
on the road.

### CelestialEvent

Scheduled by the calendar. Fully deterministic — the player can learn the date.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `period` | {days} | Recurrence cycle. Long periods make it a once-a-campaign wonder. |
| `phase` | {day} | Day of the first occurrence. |
| `durationTicks` | int | |
| `warnTicks` | int? | How far ahead omens and forecasts start. |
| `global` | bool? | Visible everywhere, vs. `regions`-limited. |
| `regions` | [Ref]? | |
| `announce` | [str]? | Narration at onset. |
| `while` | [Effect]? | Applied for the duration (`setLight`, weather tags, modifiers). |
| `effects` | [Effect]? | One-shot at onset. |
| `aftermath` | [Effect]? | On completion. |
| `forecastable` | bool? | Default true. Whether almanacs and NPCs can name the date. |

### PressureEvent

Uncertain timing. Builds toward a threshold and telegraphs itself through omens.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `scope` | `region`\|`route`\|`location`? | What it affects. Default `region`. |
| `regions` / `route` / `location` | Ref(s) | Per `scope`. |
| `epicenter` | Ref? | Where it visibly originates. |
| `pressure` | Pressure | See below. |
| `omens` | [Omen] | The player's only information channel while building. |
| `imminentAtPressure` | number? | Threshold for the `imminent` phase. Default 0.9. |
| `imminent` | Phase? | `announce` + `effects` for the last-warning phase. |
| `onset` | Phase | `announce` + `effects` for the moment itself. |
| `activeTicks` | int? | How long the world stays disrupted. |
| `while` | {encounters?, travelMultiplier?, effects?}? | Applied during `active`. |
| `aftermath` | [Effect]? | **Permanent** world change. Required in practice — see the budget guidance. |
| `earliestDay` / `latestDay` | int? | Bound the window without scheduling it. |
| `requires` | [Condition]? | Gate the event on story state. |
| `maxPerGame` | int? | Default 1. |

#### Pressure

| Field | Type | Notes |
|---|---|---|
| `start` | {min, max}? | Seeded starting value — some worlds begin closer to the edge. |
| `ratePerTick` | number | Baseline accumulation. |
| `variance` | number? | Per-tick jitter, 0–1. Without it the player can count ticks and derive the date. |
| `threshold` | number? | Default 1.0. |
| `modifiers` | [{when: Condition, mult: number}]? | Season, weather, and game vars can accelerate or hold it off. |

#### Omen

| Field | Type | Notes |
|---|---|---|
| `atPressure` | number | Minimum pressure before this omen is eligible. |
| `weight` | number | Relative frequency among eligible omens. |
| `regions` | [Ref]? | Where it can be observed. Defaults to the event's regions. |
| `text` | str | |
| `once` | bool? | |

Omen frequency scales with current pressure, so more omens genuinely means
closer. That honesty is what makes reading them a skill rather than a guess.

### Calendar

Files under `calendars/`. A game that names none runs on
`mace.core:standard-year` — forty-eight ticks to the day, four thirty-day
seasons.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `ticksPerDay` | int? | Default 48. With `world.minutesPerTick: 30` that is twenty-four hours. |
| `dayParts` | [DayPart] | At least one, written in the order the day runs through them. |
| `seasons` | [Season] | At least one. Their lengths add up to the year. |
| `dayNames` | [str]? | A repeating weekday cycle, for the journal and status line. |
| `monthNames` | [str]? | Naming only — the year is split evenly between them and nothing reads the result. |

#### DayPart

A part runs from its `startTick` until the next begins, and the last wraps
midnight: `night` starting at tick 40 of 48 also covers ticks 0–9.

| Field | Type | Notes |
|---|---|---|
| `id` | str | What `{dayPart: [...]}` matches. |
| `name` | str? | What the player reads. Defaults to the id. |
| `startTick` | int | Tick of the day this part begins on. Must be after the part before it. |
| `light` | number? | 0–1, default 1. Multiplied by the weather's `visibility` to give the one light number stealth, ranged accuracy, encounter detection, and description selection all read. |

#### Season

| Field | Type | Notes |
|---|---|---|
| `id` | str | How a climate keys its weather profile. |
| `name` | str? | Defaults to the id. |
| `days` | int | |
| `dayPartShift` | {dayPart: int}? | Ticks to move each part by this season. `{dawn: -3, night: +3}` is a long summer evening, with no model of where the sun is. |

`game.world.startSeason` puts day 1 at the start of that season rather than at
the start of the year.

---

## Encounter table

Detailed in [Travel & Encounters](06-travel-and-encounters.md).

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `chance` | number | 0–1, probability that *anything* happens per roll. |
| `minGapTicks` | int? | Anti-clumping: no second encounter within N ticks. |
| `entries` | [Entry] | |

### Entry

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `weight` | number | Relative weight among *eligible* entries. |
| `when` | [Condition]? | Eligibility — time, weather, quest state, party strength. |
| `scene` | Ref? | The scene played. |
| `combat` | {against: [Ref]}? | Shortcut for a straight fight. |
| `once` | bool? | Never repeats in a playthrough. |
| `cooldownTicks` | int? | Can't recur within N ticks. |
| `maxPerGame` | int? | |

---

## Scene

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `prompt` | str? | The choice text. Empty means "just run it". |
| `visible` | bool? | Whether the option is offered. Default true. |
| `when` | [Condition]? | Must pass, or `else` runs. |
| `say` | [str \| Descr]? | Narration, in order. `pause: true` waits for the player. |
| `effects` | [Effect]? | State changes, applied after `say`. |
| `choices` | [Choice]? | Presented after effects. |
| `goto` | Ref? | Unconditional jump after this scene. Mutually exclusive with `choices`. |
| `else` | Ref? | Scene to run when `when` fails. |
| `once` | bool? | The scene can only fire once per playthrough. |
| `tags` | [str]? | |

### Choice

| Field | Type | Notes |
|---|---|---|
| `prompt` | str | |
| `when` | [Condition]? | |
| `showWhenUnavailable` | bool? | Show greyed out rather than hidden. |
| `unavailableHint` | str? | "(You'd need 10 gold.)" |
| `goto` | Ref? | |
| `effects` | [Effect]? | Inline effects, for one-liners not worth their own scene. |

---

## Quest

| Field | Type | Notes |
|---|---|---|
| `id`, `name`, `summary` | | |
| `hiddenUntil` | [Condition]? | |
| `stages` | [Stage] | Ordered. |
| `onComplete` / `onFail` | [Effect]? | |

### Stage

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `journal` | str | What the player reads in the quest log. |
| `complete` | [Condition] | Advances to the next stage. |
| `fail` | [Condition]? | Fails the whole quest. |
| `onEnter` | [Effect]? | |
| `deadlineTicks` | int? | Shorthand for a tick-count fail condition. |

---

## Background

Optional starting variants for the protagonist. Listed in `game.player.backgrounds`.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `description` | str | Shown at character creation. |
| `stats` | {stat: {add?: number, set?: number}}? | Applied to the protagonist's base stats. |
| `inventory` | [{item, qty}]? | Extra starting items. |
| `skills` | {Ref: int}? | Starting proficiencies. |
| `grantsFlag` | str? | A flag scenes can check later, for background-specific dialog. |
| `openingScene` | Ref? | Overrides the game's opening scene. |

---

## Good

An item with market behavior. Most items are not goods. See [Economy](08-economy.md).

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `baseValue` | number | The price anchor. |
| `category` | str | `food`, `metal`, `cloth`, ... author-defined. Shocks target categories. |
| `weight` | number? | |
| `elasticity` | number | How sharply demand falls as price rises. <1 = necessity, >1 = luxury. The most important balance number. |
| `perishable` | {ticksToSpoil}? | |
| `producedBy` / `consumedBy` | [str]? | Market tags that produce or consume it. |

## Market

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `location` | Ref | |
| `size` | `hamlet`\|`village`\|`town`\|`city` | Scales stock depth. |
| `wealth` | number | 0–1. Scales price floors and capital. |
| `produces` / `consumes` | [{good: Ref, perTick: number}]? | |
| `stock` | {Ref: {initial, capacity}}? | |
| `tags` | [str]? | `farmland`, `mine`, `smithy` — matched against goods' `producedBy`. |

## Merchant

A block on an `actor` entity.

| Field | Type | Notes |
|---|---|---|
| `market` | Ref? | The market it trades against. |
| `mobile` | bool? | Carries its own prices instead — for caravans and peddlers. |
| `spread` | number | Buy/sell margin. 0.25 means buys at 0.875×, sells at 1.125×. |
| `buys` / `sells` | [Ref \| {category: str}]? | |
| `capital` | number? | It can't buy what it can't afford. |
| `restockTicks` | int? | |
| `maxSwing` | number? | How far haggling can move the price, before charisma. |

---

## Combat profile

Detailed in [Combat](07-combat.md).

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `moves` | [Ref] | Moves this fighter can use. |
| `patterns` | [{sequence: [Ref], weight: number}]? | Learnable behavior. Absent = random selection. |
| `aggression` | number? | 0–1. Biases attack vs. defend. |
| `feintChance` | number? | 0–1. Higher = harder to read. |
| `tellClarity` | number? | 0–1. How obvious the telegraph is. Lowers with difficulty. |
| `fleeThreshold` | number? | Fraction of vital pool at which it tries to run. |

### Move

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `type` | str | `thrust`, `slash`, `overhead`, `sweep`, `grapple`, ... author-defined. |
| `tell` | str | The telegraph text: "The troll winds up, club over its head." |
| `windupMs` | int | How long the player has to respond. Scaled by stats. |
| `counters` | [str] | Which defense types beat it. |
| `damage` | {min, max} | |
| `cost` | int | Effort-pool cost. |
| `effects` | [Effect]? | Status effects on hit. |

---

## Expressions (`expr`)

Conditions and effects are structured (see
[Content Model](03-content-model.md#conditions-and-effects)). Where the
structured vocabulary doesn't reach, an author writes `{expr: "..."}` — and this
section is the whole of what may go inside those quotes.

It is parsed by a hand-written parser in `mace.engine.expr`. **`eval` and `exec`
are never used**: packs are untrusted community input.

```yaml
when:
  - {expr: "player.pools.hitpoints.current < player.pools.hitpoints.max * 0.25"}
  - {expr: "world.day > 7 and 'rain' in world.weather"}
effects:
  - {setStat: {actor: player, stat: hitpoints, value: {expr: "player.pools.hitpoints.max"}}}
```

### Values

| Kind | Written | Notes |
|---|---|---|
| Number | `3`, `1.5`, `2.5e-2` | Integers and decimals. `/` always produces a decimal. |
| String | `'rain'`, `"rain"` | Escapes: `\\`, `\'`, `\"`, `\n`, `\t`. |
| Boolean | `true`, `false` | YAML's spelling, not Python's. |
| Nothing | `null` | |
| List | `['rain', 'storm']` | Used with `in`, `count`, `min`, `max`. |
| Path | `player.stats.speed` | A dotted lookup into the world (see below). |

### Operators

Loosest binding first. Everything on a row binds equally and reads left to right.

| Precedence | Operators | Notes |
|---|---|---|
| 1 | `or` | Short-circuits; the right side is not evaluated if the left is true. |
| 2 | `and` | Short-circuits. |
| 3 | `not` | |
| 4 | `==` `!=` `<` `<=` `>` `>=` `in` `not in` | Cannot be chained — write `a < b and b < c`. |
| 5 | `+` `-` | Numbers only. |
| 6 | `*` `/` `%` | Numbers only. Dividing by zero is an error. |
| 7 | `-x` `+x` | |

- `<` `<=` `>` `>=` compare **numbers only**. Comparing a string to a number is
  an error, not `false` — it is always a content mistake.
- `==` and `!=` work on any two values, and **types do not cross**: `true == 1`
  is `false`, because an author who wrote that meant something else.
- `in` tests membership of a **list**, or of a **mapping's keys**. It does not do
  substring search: "is this an element" and "is this inside this text" are
  different questions and should not share a spelling.
- `and`, `or`, and `not` return `true`/`false`, never one of their operands.

### Truthiness

`and`, `or`, `not`, and any expression used as a condition reduce their value to
a boolean this way:

| Value | Truth |
|---|---|
| `true` / `false` | itself |
| `null` | false |
| number | true when non-zero |
| string | true when non-empty |
| list, mapping | true when non-empty |

### Paths

A path is one or more names joined by dots: `player.stats.hitpoints`,
`world.day`, `troll.disposition`. The first name is a **root** the engine puts in
scope for that evaluation — `player`, `world`, and the entities the surrounding
content refers to.

- A name that isn't there is an **error**, not `null`. A condition that cannot be
  answered is a content bug; silently answering `false` is how a game ends up
  quietly unplayable three hours in.
- Names may not start with `_`, and a path may not end on a function or an engine
  object — only on a number, string, boolean, `null`, list, or mapping. Together
  these mean content cannot reach engine internals through a path.
- Every path an expression reads is available as `Expression.references`, which
  is how the validator catches `player.hitponts` at author time rather than at
  play time.

#### What the roots hold

| Path | Holds |
|---|---|
| `world.tick` | The world clock, in ticks since the game began. |
| `world.day` | Which day that is, counting from 1. |
| `world.dayPart` | `dawn`, `day`, `dusk`, or `night`. |
| `world.time` | The wall-clock time as `HH:MM`. |
| `world.minutesPerTick` | How much world time one tick is worth. |
| `world.weather` | Conditions in force. Empty until phase 2. |
| `world.weatherTags` | Their tags. Empty until phase 2. |
| `vars.<name>` | Whatever `setVar` last put there. |

Entity roots — `player`, and every entity with exactly one instance in play,
under its local id — hold:

| Path | Holds |
|---|---|
| `.id`, `.name`, `.kind` | From the content definition. |
| `.tags` | Its tags, as a list. |
| `.flags` | The flags currently set on it, as a list. |
| `.disposition` | `friendly`, `neutral`, `hostile`, or `null`. |
| `.location` | The local id of where it is. |
| `.stats.<name>` | The **effective** value, after modifiers and clamping. |
| `.pools.<name>.current` | What the pool is at now. |
| `.pools.<name>.max` / `.min` | Its bounds. |
| `.inventory.<itemId>` | How many it holds. |
| `.equipment.<slot>` | The local id of what is in that slot. |
| `.custom.<key>` | Whatever the author put in `custom`. |

A pool's *current* value is `pools.<name>.current`, not `pools.<name>` — the
latter is the mapping, and comparing a mapping to a number is an error rather
than a silent surprise. An entity whose definition has several instances in
play is deliberately **not** in scope: a name that could mean two things is
better as an error than as a guess about which one you meant.

### Functions

The complete list. There are no author-defined functions, and no way to call
anything a path reaches.

| Function | Takes | Gives |
|---|---|---|
| `abs(n)` | a number | its magnitude |
| `count(x)` | a list, mapping, or string | how many entries (or characters) |
| `min(a, b, ...)` / `min(list)` | numbers | the smallest |
| `max(a, b, ...)` / `max(list)` | numbers | the largest |

Growing this list is a deliberate, reviewable act — see
[ADR-0003](decisions/0003-structured-conditions-and-effects.md).

### Deliberately absent

Not oversights. Each one is either an ambiguity, a determinism risk, or an
attack surface:

- No assignment, loops, or function definitions. An expression asks a question
  about a world it is handed; it never changes one. Changes are `effects`.
- No `**`. `9 ** 9 ** 9` is a denial-of-service in three characters.
- No string concatenation. `+` means arithmetic and nothing else; text with
  values in it belongs in `say` templates, not in expressions.
- No indexing (`list[0]`) and no method calls. Both are ways to reach further
  than an author needs to.
- No `&&`, `||`, `!`, or `=`. Writing one gets an error naming the word to use
  instead.

Two limits keep untrusted content bounded: an expression may be at most **2000
characters** long and **32 levels** deep. Depth is measured on the parsed shape,
so a long chain counts too — `a + b + c + ...` nests one level per step. If you
hit either limit, the expression is doing work that belongs in several
conditions, or in the structured vocabulary.

### Errors

Every failure names the problem and points at the character, because the person
reading it is an author, not a programmer:

```
`player.stats` has no `hitponts`; available: hitpoints, speed, strength
  player.stats.hitponts < 10
  ^
```

Syntax errors are raised when a pack loads, so a typo never waits until play.
