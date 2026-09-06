# 3. Content Model

## Is YAML the right choice?

**Yes, for authoring — with three changes.** See
[ADR-0001](decisions/0001-yaml-as-authoring-format.md) for the full comparison
against JSON, TOML, a custom DSL, and SQLite.

The short version: YAML is human-readable, diffable, reviewable in a GitHub pull
request, and commentable — and a community of people sharing worlds through git
needs all four. A binary or database format kills the "clone the repo and read
someone's world" property that makes this project fun.

But the v0 templates have three real problems, and all three are fixable without
leaving YAML:

**Problem 1: untyped, ambiguous expression strings.**

```yaml
# v0 — what does this mean?
modifiers:
  - "player.hitpoints.current: player.hitpoints.max"   # reference
  - "player.location: 'trollBridge1'"                  # literal, because quotes
```

Quoting-as-semantics is invisible in a diff, impossible to validate, and a
nightmare to generate correctly from a wizard. Replaced with structured effects
plus an explicit `expr` wrapper — see [Conditions and effects](#conditions-and-effects)
below.

**Problem 2: deep anonymous nesting.**

A scene's `fallbacks` contain scenes whose `fallbacks` contain scenes. By the
third level the YAML is unreadable and nothing can be reused or linked to.
Replaced with **named scenes and `goto`**, which flattens the file and makes
interaction graphs reusable and visualizable.

**Problem 3: no namespacing or inheritance.**

Two authors both define `troll` and the library breaks. Replaced with
`pack:id` namespacing and `extends`.

**Authoring format is YAML. Runtime format is a compiled JSON bundle.** The
loader resolves inheritance, namespaces, and defaults once, then hands the engine
a flat immutable structure. The browser ships the compiled bundle; nobody parses
YAML at play time.

## Packs

A pack is the unit of distribution. It's a directory with a manifest.

```yaml
# packs/fantasy.core/pack.yml
id: fantasy.core
name: Core Fantasy Library
version: 0.3.0
kind: library                # library | game
maceVersion: "^0.1"
authors: ["lightningWhite"]
license: CC-BY-4.0
description: >
  Trolls, taverns, temperate climates, and the other furniture of a
  medieval-fantasy world.
requires:
  - id: mace.core
    version: "^0.1"
tags: [fantasy, medieval]
```

```
packs/fantasy.core/
├── pack.yml
├── entities/
│   ├── monsters.yml
│   ├── npcs.yml
│   └── items.yml
├── climates/
│   └── temperate.yml
├── encounters/
│   └── roads.yml
└── scenes/
    └── common.yml
```

File organization inside a pack is free — the loader globs and merges by `id`.
Split however makes sense for the world; one file per location is fine, one file
for all locations is fine.

A **game pack** (`kind: game`) adds a `game.yml` with the start conditions, and
is the thing that appears in the "play a game" list.

## Ids and namespacing

Every content object has an `id` that is `kebab-case` within its pack. Its fully
qualified id is `pack-id:local-id` — `fantasy.core:bridge-troll`.

Resolution order for a bare reference inside a pack:

1. This pack
2. Direct dependencies, in the order listed in `requires`
3. Error — ambiguous or missing references are hard validation failures

Always write the qualified form when referring to another pack. The wizard emits
qualified ids automatically.

## Inheritance (`extends`)

This is the reuse mechanism that makes the library worth having.

```yaml
# In a game pack that requires fantasy.core
- id: gorm
  extends: fantasy.core:bridge-troll
  name: "Gorm the Toll-Taker"
  stats:
    strength: {base: 85}       # deep-merged over the parent's stats
  inventory:
    - {item: fantasy.core:gold, qty: 120}
  tags: [$append, named, quest-giver]
```

Rules:

- Merge is **deep** for maps, **replace** for lists — with two sentinels:
  - `$append` as a list's first element appends to the parent's list instead.
  - `$remove: [key, ...]` deletes inherited keys.
- `extends` chains are allowed; cycles are a validation error.
- A pack may extend from any pack it `requires`.
- Inheritance is resolved at load time. The engine never sees an `extends`.

## The content/state split

Content declares what a thing *is*. State tracks what a particular instance of
it is *doing right now*. This split is a hard rule — see
[Architecture, boundary 1](02-architecture.md#boundary-1--content-is-immutable-state-is-not).

```yaml
# CONTENT — packs/fantasy.core/entities/monsters.yml
- id: bridge-troll
  kind: actor
  name: "Bridge Troll"
  stats:
    hitpoints: {base: 80}
    strength: {base: 70}
    speed: {base: 25}
```

```jsonc
// STATE — inside a save file
{
  "instanceId": "bridge-troll#3",
  "def": "fantasy.core:bridge-troll",
  "pools": { "hitpoints": 31, "stamina": 44 },
  "modifiers": [
    {"stat": "speed", "add": -8, "source": "weather:blizzard", "expiresAtTick": 412}
  ],
  "flags": ["afraid", "has-been-paid"],
  "location": "troll-bridge"
}
```

Authors never write `current`. The engine derives it.

## Stats

One consistent stat shape replaces the v0 `max`/`current`/`temp`/`modifier`
tangle:

```yaml
stats:
  hitpoints: {base: 50, max: 50}
  strength:  {base: 32}
  speed:     {base: 41}
  wisdom:    {base: 12}
  endurance: {base: 30}
  charisma:  {base: 60}
  stealth:   {base: 18}
```

- `base` — the value with nothing acting on it.
- `max` — optional cap; defaults to 100 for ability stats.
- `growth` — optional, how the stat improves with use (see below).
- `customizable: true` — the player may spend creation points here at game start.

At runtime, the **effective value** of a stat is computed through a fixed
pipeline. Order is fixed so results are reproducible and explainable to the
player:

```
base
  → + permanent progression (earned through play)
  → + equipment bonuses
  → + environmental responses  (blizzard: speed -8)
  → + status effects           (poisoned: strength -10)
  → + scene/consumable modifiers (potion: strength +15 for 6 ticks)
  → clamp to [0, max]
= effective
```

**Pools** (hitpoints, stamina) are different from **abilities** (strength,
stealth): pools have a current value that persists and depletes; abilities are
recomputed from the pipeline every time they're read. The engine tracks pools in
state and abilities as derived values.

Stat names are **not hard-coded**. `mace.core` defines the seven above as a
convention, but a sci-fi pack can define `hacking`, `oxygen`, and `hull-integrity`
and the engine treats them identically. Only two roles are structural: the pool
used for death (`vitalPool`, default `hitpoints`) and the pool used for combat
action costs (`effortPool`, default `stamina`), both declared in `game.yml`.

## Entities

One type replaces the v0 `player` / `interactiveElement` duplication. The player
is an actor with `playable: true`.

```yaml
- id: peddler
  kind: actor              # actor | item | fixture | container | portal
  name: "Wandering Peddler"
  description: "A stooped man with a pack twice his size."
  tags: [merchant, human, friendly]
  disposition: friendly    # friendly | neutral | hostile
  stats:
    hitpoints: {base: 50}
    charisma:  {base: 60}
  inventory:
    - {item: gold, qty: 15}
    - {item: dagger, qty: 1}
  equipment:
    mainHand: dagger
  skills:
    dagger: 25
  combat:
    profile: fantasy.core:timid-fighter
  env:
    - when: {weather: [blizzard]}
      modify: [{stat: speed, add: -5}]
  scenes: [talk-to-peddler, attack-peddler]
```

`kind` drives defaults and available verbs, not special-case engine logic:

| kind | Means | Gets |
|---|---|---|
| `actor` | Can act, fight, carry | stats, inventory, combat, disposition |
| `item` | Can be carried, used, equipped | weight, stack, equipSlot, use effects |
| `fixture` | Part of the scenery, interactive | scenes, flags (`locked`, `lit`) |
| `container` | A fixture that holds items | contents, capacity, `locked` |
| `portal` | A door/gate gating a route | `locked`, `requiresItem`, target route |

## Scenes (interactions)

The v0 `Interaction` model — visible, description, conditions, dialog, modifiers,
nextActions, fallbacks — is good and survives. Three changes: scenes are named,
branching is by `goto`, and conditions/effects are structured.

```yaml
- id: talk-to-troll
  prompt: "Speak to the troll"          # what the player sees as an option
  visible: true                          # is the option offered at all
  when:                                  # must be true, else `else:` runs
    - {expr: "troll.disposition != 'hostile'"}
  say:
    - "The troll unfolds itself from beneath the bridge."
    - {text: "'Toll,' it says. 'Ten gold, or swim.'", pause: true}
  effects:
    - {setFlag: {entity: troll, flag: has-spoken}}
  choices:
    - prompt: "Pay the toll (10 gold)"
      when: [{hasItem: {actor: player, item: gold, qty: 10}}]
      goto: pay-the-toll
    - prompt: "Try to talk it down"
      goto: haggle-with-troll
    - prompt: "Draw your sword"
      goto: fight-the-troll
  else: troll-ignores-you                # the v0 "fallbacks", now a reference
```

- `say` entries are strings or `{text, pause, when}` objects. Conditional lines
  let one scene read differently at night or in the rain.
- `choices` are presented after `say`. A choice with a failed `when` is hidden by
  default, or shown greyed with `showWhenUnavailable: true` (so players can see
  what they're missing — good for motivation).
- `goto` moves to another scene by id. `goto` may be qualified, so a game can
  jump into a library scene.
- `else` is the v0 `fallbacks`, as a single scene reference. That scene may
  itself branch.
- Special effects like the v0 `_attack_` keyword become real effect types:
  `{startCombat: {against: troll}}`.

Because scenes have ids, the wizard and the future web editor can draw the
interaction graph, detect unreachable scenes, and let authors reuse a "shopkeeper
haggling" scene across twelve merchants.

## Conditions and effects

The replacement for v0's magic strings. Both have a **structured canonical form**
and both accept `{expr: "..."}` for anything the structured form doesn't cover.

### Conditions

```yaml
when:
  - {hasItem: {actor: player, item: fantasy.core:magic-sword}}
  - {atLocation: {actor: player, location: hagans-castle}}
  - {flag: {entity: troll, flag: has-been-paid, is: false}}
  - {statAtLeast: {actor: player, stat: charisma, value: 40}}
  - {weather: [rain, storm]}
  - {dayPart: [dusk, night]}
  - {questStage: {quest: reach-the-castle, stage: travel}}
  - {chance: 0.15}                                  # rolls on a scene-local stream
  - {expr: "player.stats.hitpoints < player.stats.hitpoints.max * 0.25"}
```

A list of conditions is ANDed. Use `{any: [...]}`, `{all: [...]}`, `{not: {...}}`
for other logic.

### Effects

```yaml
effects:
  - {adjustStat: {actor: player, stat: hitpoints, delta: -8, reason: "troll's club"}}
  - {setStat: {actor: player, stat: hitpoints, value: {expr: "player.stats.hitpoints.max"}}}
  - {giveItem: {actor: player, item: gold, qty: 1}}
  - {takeItem: {actor: player, item: gold, qty: 10}}
  - {move: {actor: player, to: hagans-castle}}
  - {setFlag: {entity: chest, flag: locked, value: false}}
  - {setVar: {name: kingWarned, value: true}}
  - {reveal: {location: secret-cave}}
  - {advanceQuest: {quest: reach-the-castle, stage: deliver}}
  - {startCombat: {against: [troll], canFlee: true}}
  - {attachAlly: {entity: caravan-guard, until: {atLocation: {actor: player, location: hagans-castle}}}}
  - {dismissAlly: {entity: caravan-guard}}
  - {applyModifier: {actor: player, stat: speed, add: 10, ticks: 6, label: "Elixir of Haste"}}
  - {advanceTime: {ticks: 4}}
  - {playScene: fantasy.core:generic-shop}
```

The `expr` mini-language is a **restricted, non-Turing-complete expression
grammar** — comparisons, arithmetic, boolean logic, dotted attribute paths, and a
short whitelist of functions (`min`, `max`, `abs`, `count`). It is parsed by hand
in `mace.engine.expr`, never by `eval`. The grammar, the truthiness rules, and
what is deliberately left out are specified in
[Schema Reference § Expressions](04-schema-reference.md#expressions-expr); the
reasoning is in [ADR-0003](decisions/0003-structured-conditions-and-effects.md).

## Quests

The v0 design has only game-wide win/lose conditions. Quests are the missing
middle layer, and they're what makes a game feel like it has a plot.

```yaml
- id: reach-the-castle
  name: "The King's Summons"
  summary: "Report to Hagan's Castle within seven days."
  hiddenUntil: [{flag: {entity: player, flag: conscripted}}]
  stages:
    - id: travel
      journal: "Reach Hagan's Castle before the seventh day is out."
      complete: [{atLocation: {actor: player, location: hagans-castle}}]
      fail:     [{expr: "world.day > 7"}]
    - id: report
      journal: "Find the captain of the guard."
      complete: [{flag: {entity: captain, flag: has-spoken}}]
  onComplete:
    - {giveItem: {actor: player, item: kings-token}}
  onFail:
    - {playScene: deserters-end}
```

Quests are optional. A tiny game can still use only `game.winConditions`.

## Game manifest

```yaml
# packs/games/peasants-quest/game.yml
game:
  name: "A Peasant's Quest"
  tagline: "You have seven days and no choice."
  authors: ["lightningWhite"]
  difficulty: standard
  estimatedMinutes: 45
  introduction:
    - "You are a peasant who has worked your friend's farm for twenty-five years."
    - "One morning the king's riders come through the barley."
  player:
    entity: letholin              # an entity with playable: true
    startLocation: fenmoor
    creationPoints: 20            # spendable on stats marked customizable
  world:
    minutesPerTick: 30
    startTick: 96                 # dawn of day 1
    calendar: mace.core:standard-year
    startSeason: autumn
  rules:
    vitalPool: hitpoints
    effortPool: stamina
    combatMode: reflex            # reflex | tactical | auto — player may override
    deathIsPermanent: false
    survival: [exposure, rest]    # + hunger, thirst for a survival game; [] to disable
    economy: market               # market | simple
  quests: [reach-the-castle]
  winConditions:
    - {questComplete: reach-the-castle}
  loseConditions:
    - {expr: "player.stats.hitpoints <= 0"}
  onWin:  victory-scene
  onLose: defeat-scene
```

`onWin` / `onLose` point at ordinary scenes, so the v0 idea of a "retry with
your magic sword" fallback works with no special machinery — it's just a scene
with choices.
