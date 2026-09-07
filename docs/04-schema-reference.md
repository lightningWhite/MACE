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

### Terrain

Files under `terrains/`. What a road is made of, and how badly the weather
ruins it.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | |
| `travelMultiplier` | number? | How slow this surface is in fair weather. Default 1. |
| `inWeather` | {tag: number}? | An extra multiplier per weather tag, on top of the weather's own. |
| `tags` | [str]? | Free-form labels for encounter tables and content to match on. |

Only the **largest** matching `inWeather` entry applies, not the product: a
wet, cold, windy night on a forest track should be bad, not impossible.

The split between a condition's `travelMultiplier` and a terrain's `inWeather`
is what makes a detour worth considering. Rain on a paved highway is an
inconvenience; rain on a forest track is mud to the ankles. The long way round
on a good road can genuinely beat the short way through the wood — but only
when it is wet, which is a decision rather than a fixed answer.

---

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

Files under `celestialEvents/`. Scheduled by the calendar and **fully
deterministic** — the same seed is not even required. That is the point: a
date that can be known can be planned around, which is what makes an almanac
worth gold and an astronomer worth finding.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | |
| `period` | int \| {days} | Recurrence cycle in days. Long periods make an event a once-a-campaign wonder most playthroughs never see. |
| `phase` | int \| {day} | Day of the first occurrence. Default 1. |
| `durationTicks` | int? | Default 1. |
| `warnTicks` | int? | How far ahead the world starts saying so. |
| `global` | bool? | Visible everywhere, vs. `regions`-limited. |
| `regions` | [Ref]? | |
| `forecastable` | bool? | Default true. Whether almanacs and NPCs can name the date. |
| `warning` | str \| [Descr]? | Narrated once when the warning window opens. |
| `announce` | [str \| Say]? | Narrated at onset. |
| `while` | EventWhile? | How the world is different while it runs. Reverts on its own when it ends. |
| `effects` | [Effect]? | One-shot at onset. |
| `aftermath` | [Effect]? | One-shot on completion. |

### PressureEvent

Files under `pressureEvents/`. Timing is uncertain, builds toward a threshold,
and telegraphs itself through omens. A flat per-tick probability is memoryless —
the volcano is exactly as likely to erupt on day one as day thirty, nothing can
foreshadow it honestly, and the player never learns anything. A rising
accumulator gives the event a *direction*, and direction is what makes the omens
truthful.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | |
| `scope` | `region`\|`route`\|`location`? | Default `region`. |
| `regions` / `route` / `location` | Ref(s) | Per `scope`. `regions` also decides where the event can be seen and where its omens show. |
| `epicenter` | Ref? | Where it visibly originates. |
| `pressure` | Pressure | See below. |
| `omens` | [Omen]? | The player's only information channel while building. |
| `imminentAtPressure` | number? | Default 0.9. Should be *late*: the tension lives between "probably" and "certainly". |
| `imminent` | {announce?, effects?}? | The last-warning beat. |
| `onset` | {announce?, effects?} | The moment itself. |
| `activeTicks` | int? | How long the world stays disrupted. |
| `while` | EventWhile? | How it stays disrupted. |
| `aftermath` | [Effect]? | **Permanent** world change, and the thing that separates an event from a weather condition. If you can't name what's different afterward, cut it. |
| `earliestDay` / `latestDay` | int? | Bound the window without scheduling it. `latestDay` forces the climb through `imminent` first, so the backstop never ambushes anyone. |
| `requires` | [Condition]? | Gate on story state, so the payoff always lands. |
| `maxPerGame` | int? | Default 1. |

#### Pressure

| Field | Type | Notes |
|---|---|---|
| `start` | {min, max}? | Seeded starting value — some worlds begin closer to the edge. |
| `ratePerTick` | number? | Baseline accumulation. |
| `variance` | number? | Per-tick jitter, 0–1, as a fraction of the rate. Without it a player could count ticks and derive the date, which turns the volcano back into a scheduled event. |
| `threshold` | number? | Default 1.0. |
| `modifiers` | [{when: [Condition], mult: number}]? | Season, weather, and game vars can accelerate or hold it off. A quest that multiplies the rate by 0.1 genuinely buys the valley years. |

#### Omen

| Field | Type | Notes |
|---|---|---|
| `id` | str? | For `once`. Defaults to the text. |
| `atPressure` | number | Share of the threshold before this omen is eligible. |
| `weight` | number | Relative frequency among eligible omens. An omen already shown weighs a quarter, so a long build cycles rather than repeating. |
| `regions` | [Ref]? | Where it can be observed. Defaults to the event's regions. |
| `text` | str | |
| `once` | bool? | |

Omen frequency rises with the **square** of the accumulator, and no two come
within six hours of each other. A linear ramp gives a steady drip that reads as
background noise; the squared curve stays almost silent early and gets
insistent near the end, which is the shape of the signal the player learns to
read. A whole game should see two or three, escalating.

#### EventWhile

Standing changes, held for as long as the event is active and undone when it
ends. A typed block rather than a list of effects, because an effect list is
one-way and these have to be reverted.

| Field | Type | Notes |
|---|---|---|
| `light` | number? | Overrides the sky's light entirely. Night, at noon. |
| `weatherTags` | [str]? | Added to whatever the weather already carries, so `env` responses and encounter conditions see them. |
| `travelMultiplier` | number? | Multiplied into the roads' own. |
| `blocksTravel` | bool? | |
| `encounters` | Ref? | A hazard table rolled on top of the ordinary ones. |

#### The phases

    dormant ──► building ──► imminent ──► onset ──► active ──► aftermath
                (omens)      (announce,   (the      (hazards,   (permanent
                              last         moment)   modified    world
                              chance)                weather)    change)

Each beat emits a `world.event` with the phase name. Its narration arrives as
ordinary `narrate` events on purpose: an omen surfaced as a system message is
not an omen, and there is no pressure bar anywhere in the design.

#### News

An event that reaches onset somewhere the player is not goes into a **news
queue** instead of being narrated. `world.news` reads how many items are
waiting, so an encounter entry can be eligible only when there is something to
tell, and the `tellNews` effect passes items on with their age. That is how a
world where things happen out of sight tells you about them: through a
traveller on the road, not a notification.

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

Files under `encounterTables/`. Detailed in
[Travel & Encounters](06-travel-and-encounters.md).

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | A bandit-country road is a country road with worse entries. |
| `chance` | number | 0–1, the probability that *anything* happens per roll. The one danger dial. |
| `minGapTicks` | int? | A hard floor between encounters from this table. |
| `pressureStep` | number? | Anti-clumping. See below. Default 0, which turns the pity system off. |
| `entries` | [Entry] | |

### Entry

| Field | Type | Notes |
|---|---|---|
| `id` | str | How cooldowns and caps are tracked; unique within the table. |
| `weight` | number | Relative weight among *eligible* entries. Not a probability: `5` against a total of 100 is the five-percent troll. |
| `when` | [Condition]? | Eligibility — time, weather, quest state, what the player is carrying. |
| `scene` | Ref? | The scene played. |
| `combat` | {against: [Ref], fleeTo?: Ref}? | A straight fight, for when a scene would be ceremony. Arrives with phase 3. |
| `once` | bool? | Never repeats in a playthrough. |
| `cooldownTicks` | int? | Can't recur within N ticks. |
| `maxPerGame` | int? | A cap looser than `once`. |

An entry with neither `scene` nor `combat` is a load-time error: it would fire
and nothing would happen.

### Where tables attach, and in what order

| Attach point | Rolled when |
|---|---|
| `region.encounters` | Every leg, and every tick spent standing in the region |
| `route.encounters` | Every travel leg |
| `waypoint.encounters` | On reaching the waypoint, in addition to the route's |
| `location.encounters` | Every tick the player spends there |

The region rolls first and the road or the place second, so the more specific
table gets the last word when both fire in the same breath. `location.safe:
true` suppresses the location's own table and the region's while standing
there — towns are safe, the wilderness is not — but a road running through a
region is still a road.

An encounter that offers the player a choice interrupts what they were doing:
a journey stops where it stands and can be carried on, and a wait is cut short
at the tick it happened, because an ambush is not something you sleep through.

### Anti-clumping, honestly

`minGapTicks` is the blunt instrument: no second encounter from this table
within N ticks. It lowers the observed rate below `chance` on short roads,
which is the intended trade.

`pressureStep` is the pity system, and it is written so it does *not* quietly
make a road more dangerous than its author asked for. An empty roll adds
`pressureStep` to the next roll's chance; a roll that fires subtracts
`pressureStep × (1/chance − 1)`. Over a long run at the authored rate, misses
outnumber hits by exactly `(1 − chance) : chance`, so the two terms cancel and
the mean stays put. What changes is the variance: long empty stretches get
likelier to end, and streaks get likelier to stop.

A roll that fires but finds every entry ineligible resets the pressure to
zero rather than banking it, so a table whose entries are all on cooldown does
not build up a debt it pays off all at once later.

---

## Effects, and the ones that cost time

Two effects ask the runner for time rather than taking it themselves, because
moving the clock means moving the *world* — weather, fronts, encounters — and
an effect that bumped the tick counter on its own would skip all of it. The
time is spent after every effect in the block has run.

| Effect | Body | Notes |
|---|---|---|
| `advanceTime` | `{ticks}` | A long conversation, a detour, a wait. |
| `rest` | `{ticks?, pools?, fraction?}` | Clears exposure and refills pools, and costs the hours. `ticks` defaults to 8, `pools` to every pool the actor has a maximum for, `fraction` to 1. |

Rest recovery happens *after* the hours pass, not before, so a player who
sits out a blizzard in the open finds the hours they slept through were hours
they spent in the blizzard. Only a roof lets a rest shed all the exposure it
took; in the open it sheds a quarter. Pools come back either way — sleep is
sleep — which is what makes the inn worth the detour rather than the only
option. `rest` needs `rest` in `game.rules.survival`, and reports
`engine.unsupported` when a game has turned it off.

### Using what you are carrying

An item's `use` block is what makes it worth carrying rather than worth selling:

```yaml
- id: bread
  kind: item
  name: "Bread"
  item:
    stackable: true
    baseValue: 2
    use:
      consumed: true
      effects:
        - {adjustStat: {actor: player, stat: stamina, delta: 6, reason: "bread"}}
```

The engine offers every usable thing in the player's pack as a menu option, and
as a `use:<item>` response inside a fight. Using something costs no tick by
default, the way looking around does; a bandage that takes ten minutes says so
with `advanceTime` among its own effects. Mid-fight it costs the *exchange* —
the move that was coming lands unanswered — which is what makes a healing
draught a decision about when.

### The ones that hand over the loop

| Effect | Body | Notes |
|---|---|---|
| `startCombat` | `{against, canFlee?, onWin?, onLose?, onFlee?}` | Takes over until the fight ends, then plays whichever `on…` applies. |
| `attachAlly` | `{entity, until?}` | They follow the player and fight on their own profile. `until` releases them the moment it comes true, wherever that happens. |
| `dismissAlly` | `{entity}` | |

`against` takes one reference or a list, and **repeating one makes another of
it**: `[wolf, wolf]` is two wolves. A reference that names something already
standing where the player is fights as *itself* — `{against: gorm}` in the
scene where Gorm has just refused you means that troll, with this
playthrough's hitpoints and the gold in its pocket. A fight tidies away what
it made and leaves alone what it found.

Only one fight may be asked for in a block of effects; a second would start
before the first had finished, and that is a load-time-shaped mistake caught at
runtime rather than a silent one.

Writing all three `on…` scenes is how a fight has consequences rather than just
an outcome — the bridge you can now cross, the twenty yards of road you gave up
running. Without `onLose` the vital pool is simply left empty and the game's own
`loseConditions` decide what that means.

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
| `extends` | Ref? | A background to inherit from. |
| `description` | str | Shown at character creation. |
| `stats` | {stat: {add?: number, set?: number}}? | Applied to the protagonist's base stats. A bare number is `add`. |
| `inventory` | [{item, qty}]? | Extra starting items. |
| `skills` | {Ref: int}? | Starting proficiencies. |
| `grantsFlag` | str? | A flag scenes can check later, for background-specific dialog. |
| `openingScene` | Ref? | Played instead of the start location's `onArrive`. |

A background is a variation on the protagonist rather than a replacement for
them, which is why `add` is the ordinary form: raising the protagonist's own
base raises every background's with it. `set` fixes a value outright, and where
both appear `set` lands first.

Creation is **session setup**, not a turn. Which background and where the
creation points went are passed in when a playthrough opens, alongside the seed
— so a golden replay covers a poacher as exactly as it covers a farmhand, and
`mace play --background poacher --spend stealth=10` starts without a menu.

---

## Good

The **market behavior of an item**. Most items are not goods — a quest token has
no market. A good names the item it is the behavior of rather than describing one
of its own: the price anchor is that item's `baseValue` and a cartload weighs its
`weight`, so the sack of grain the player carries and the sack the market prices
are the same sack. See [Economy](08-economy.md).

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `extends` | Ref? | A good to inherit from. |
| `item` | Ref | The item this is the market behavior of. Its `baseValue` anchors the price. |
| `category` | str? | `food`, `metal`, `cloth`, ... author-defined. Shocks target categories. |
| `elasticity` | number | How sharply demand falls as price rises. <1 = necessity, >1 = luxury. The most important balance number. Default 1. |
| `perishable` | {ticksToSpoil}? | What spoils, and how fast. Perishability is what stops a player buying out a harvest and sitting on it. |
| `producedBy` / `consumedBy` | [str]? | Market tags that produce or consume it. A market tagged `farmland` grows every good naming `farmland` here, without listing them one by one. |

## Market

A settlement's shelves and what it charges for what is on them.

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `extends` | Ref? | A market to inherit from. |
| `location` | Ref | Where it is. The player has to be standing here to trade. |
| `name` | str? | Defaults to the location's name. |
| `size` | `hamlet`\|`village`\|`town`\|`city` | Scales default stock depth (×0.35, ×1, ×3, ×9). Default `village`. |
| `wealth` | number | 0–1. What this place will pay: a city bids over the odds, a hamlet cannot. Default 0.5. |
| `produces` / `consumes` | [{good: Ref, perTick: number}]? | Spelled out, overriding whatever the tags imply. |
| `stock` | {Ref: {capacity, target?, initial?}}? | `target` defaults to half of `capacity` and is what scarcity is measured against; `initial` defaults to `target`, so a game opens at the ordinary price rather than in a shortage nobody wrote. A good this market trades but does not list gets a default depth from its `size`. |
| `trades` | [Ref]? | Goods it buys and sells without making or using them — a middleman's stock in trade. |
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

Collection: `combatProfiles`. Detailed in [Combat](07-combat.md).

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | A profile to inherit from. A veteran duelist is a duelist that feints more. |
| `moves` | [Ref] | Moves this fighter can use — attacks and defenses both. A fighter with no defense moves can only take the hit. |
| `patterns` | [Pattern]? | Learnable behavior. Absent = random selection. |
| `aggression` | number? | 0–1. How readily it presses an attack it cannot afford. |
| `feintChance` | number? | 0–1. Higher = harder to read. |
| `tellClarity` | number? | 0–1. How obvious the telegraph is. Lowers with difficulty. |
| `fleeThreshold` | number? | Fraction of vital pool at which it tries to run. 0 never runs. |
| `tags` | [Tag]? | |

### Pattern

| Field | Type | Notes |
|---|---|---|
| `sequence` | [Ref] | Moves in order, played to the end before another pattern is picked. Every move must also be in the profile's `moves`. |
| `weight` | number | Relative weight among the patterns currently eligible. |
| `when` | [Condition]? | Eligibility — a wolf pack hunts differently in the dark. |

### Move

Collection: `moves`.

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `extends` | Ref? | A move to inherit from. |
| `kind` | `attack` \| `defense` | Whether it is telegraphed or is the answer. Default `attack`. |
| `type` | str | `thrust`, `slash`, `overhead`, `sweep`, `grapple` for attacks; `parry`, `dodge`, `block` for defenses. Author-defined — an attack's `counters` names defense `type`s, which is the whole counter matrix. |
| `tell` | Description | Attacks only, required: "The troll winds up, club over its head." |
| `vagueTell` | Description? | What a low `tellClarity` shows instead. Without one, an unclear tell is withheld. |
| `windupMs` | int | How long the defender has, before their speed widens it. Default 1000. |
| `counters` | [str] | Defense types that beat this attack. |
| `damage` | {min, max, type?}? | What it does when it lands. A *defense* may carry damage too — that is what `strike` is. |
| `cost` | number | Effort-pool cost. |
| `mitigation` | number | Defenses only, 0–1. The share of damage stopped when the read was right but the timing was not. |
| `feint` | bool | A windup that means nothing. Its `counters` is the one right answer. |
| `effects` | [Effect]? | Applied to the defender when it lands. |
| `tags` | [Tag]? | |

An entity fights by naming a profile:

```yaml
combat:
  profile: fantasy.core:quick-duelist
  moves: [signature-riposte]     # optional extras, over and above the profile's
```

An item may grant moves too (`item.moves`): carrying a dagger is what makes
`parry` one of your options.

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
