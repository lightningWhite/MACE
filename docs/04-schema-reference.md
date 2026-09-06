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
| `value` | number? | Base trade value. |

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

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `climate` | Ref | The climate model governing it. |
| `neighbors` | [Ref]? | Adjacency for weather-front propagation. |
| `elevation` | int? | Modifies temperature and precipitation type. |

### Climate

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | |
| `seasons` | {season: SeasonProfile} | Per-season weather weights and temperature range. |
| `transitions` | {weather: {weather: weight}} | Markov transition weights between conditions. |
| `sequences` | [[Ref]]? | Optional hand-authored condition sequences, for scripted feel. |
| `frontFrequency` | number? | How often weather fronts spawn in this climate. |

### WeatherCondition

| Field | Type | Notes |
|---|---|---|
| `id`, `name` | | e.g. `blizzard`, `ash-fall`, `ion-storm` |
| `description` | [Descr]? | Emitted when it begins. |
| `intensityRange` | [min, max]? | 0–1. Scales all effects. |
| `visibility` | number? | 0–1 multiplier. Affects stealth, ranged combat, encounter detection. |
| `travelMultiplier` | number? | >1 slows travel. |
| `modify` | [{stat, add?, mult?}]? | Blanket stat effects on everyone exposed. |
| `blocksTravel` | bool? | Hurricanes close the roads. |
| `tags` | [str]? | `wet`, `cold`, `dark` — for entity `env` responses by group. |

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

| Field | Type | Notes |
|---|---|---|
| `ticksPerDay` | int | |
| `dayParts` | [{id, name, startTick}] | `dawn`, `day`, `dusk`, `night`. Light level derives from this. |
| `seasons` | [{id, name, days}] | |
| `monthNames` / `dayNames` | [str]? | Flavor for the journal. |

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
  - {expr: "player.stats.hitpoints < player.pools.hitpoints.max * 0.25"}
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
