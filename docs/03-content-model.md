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

### Reserved names

`player` is not an id. Wherever content names an actor — `{actor: player}`,
`{hasItem: {actor: player, ...}}` — it means whichever entity
`game.player.entity` names, so a scene written once works for any protagonist
and any background. An entity with the id `player` is a validation error rather
than a shadowing surprise.

`player` and `world` are also the roots an expression reads from; see
[Schema Reference § Paths](04-schema-reference.md#paths).

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
- Merging happens on the **raw mappings**, before content is validated. So a
  child entity may leave out a `name` its parent supplies, and the `$append` and
  `$remove` sentinels never reach a model — by the time an `Entity` exists,
  inheritance is something that already happened. This is why the pydantic
  models in `mace.model` require the fields a *compiled* object must have, and
  why validating a hand-written file against them means resolving its
  inheritance first.

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
- `growth` — optional, how the *current* value improves toward its existing
  cap with use (see below). Raising the cap itself is a different thing —
  the `raiseMax` effect, session-only growth that never touches content —
  see [How-Tos § "Grow a stat's cap"](14-how-tos.md#grow-a-stats-cap).
- `customizable: true` — the player may spend creation points here at game start.
  Cannot be combined with a relative `base`/`max` (below) — a customizable
  stat is the player's own, and relative-to-itself is nonsense.

`base`/`max` may also be written relative to the player's own stat, instead
of a literal number:

```yaml
stats:
  hitpoints: {base: {relativeToPlayer: {stat: hitpoints, factor: 3}}, max: 200}
```

Resolved against the player's stat *cap*, once, at the moment this entity is
instantiated — it does not rescale later if the player's own stats change.
This is what makes a library monster's toughness read the same regardless of
whether a game's hitpoints run 0–10 or 0–10,000. `Damage.min`/`max` (a
weapon's or a move's damage bound) take the same shape, resolved fresh every
roll instead. See
[Schema Reference § RelativeValue](04-schema-reference.md#relativevalue).

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

Stat names are **mostly** not hard-coded. `mace.core` defines the seven above
as a convention, and a sci-fi pack can define `hacking`, `oxygen`, and
`hull-integrity` and the engine treats them identically — except three names
the engine reads directly, whatever pack wrote them:

| Name | What it does | Where |
|---|---|---|
| `strength` | Scales rolled weapon damage | `power()`, `src/mace/engine/combat/resolution.py` |
| `speed` | Widens/narrows the combat timing window, sets the action-meter fill rate, shifts flee odds | `window_ms()` and nearby, `src/mace/engine/combat/fight.py` |
| `charisma` | Sets haggling's odds and how fast a merchant sours | `src/mace/engine/economy/haggle.py` |

An entity that never declares `strength`/`speed` still fights on equal
footing — those two default to `50`, the engine's own neutral value, rather
than the `0` every other undeclared stat reads as (a real trap: `0` isn't a
no-op for either of them, it's roughly half damage or a badly skewed clock).
The wizard pre-fills both the moment a new character exists, for exactly
this reason — alongside whatever this game actually calls its `vitalPool`
and `effortPool` (`hitpoints`/`stamina` by default, but resolved against
this project's own `game.rules` rather than hard-coded, the same way the
engine itself treats those two names as configurable). The statblock editor
marks all five names the engine ever reads — those two plus `strength`,
`speed`, and `charisma` — with a "core" badge, so an author can tell them
apart from an ordinary free-form stat at a glance.

Every stat besides these three is genuinely inert until content gives it
meaning — nothing automatic happens just because it's declared. A
`{statAtLeast: ...}` condition gating a choice, an `{adjustStat: ...}` or
`{applyModifier: ...}` effect changing it, or an `env`/`modify` weather
response reacting to it are the only three ways a stat ever does anything.
Declaring `stealth: {base: 18}` and never referencing it anywhere is a number
that sits on the sheet, moved by nothing, read by nothing. See
[How-Tos § "Make a stat do something"](14-how-tos.md#make-a-stat-do-something)
for the recipe.

Only two roles are structural in the sense of being *declared per game*
rather than baked into the engine: the pool used for death (`vitalPool`,
default `hitpoints`) and the pool used for combat action costs
(`effortPool`, default `stamina`), both set in `game.yml`.

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

**A conversation hub.** A choice that answers a question does not need a scene
of its own — the `say` effect speaks a line inline, and `goto` can point right
back at the scene that offered the choice:

```yaml
- id: talk-to-the-elder
  prompt: "Talk to the elder"
  choices:
    - prompt: "Ask about the bridge"
      effects: [{say: "It washed out last spring, lad."}]
      goto: talk-to-the-elder
    - prompt: "Ask about the weather"
      effects: [{say: "Storms roll through mid-summer."}]
      goto: talk-to-the-elder
    - prompt: "Leave"
      goto: village-square
```

Each question re-offers the same hub, so a hand-full of questions costs one
scene and one `say` effect apiece, not a scene per answer.

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
  - {statAtMost: {actor: player, stat: stamina, value: 10}}
  - {weather: [rain, storm]}
  - {weatherTag: [wet, cold]}                       # matches a condition's tags
  - {dayPart: [dusk, night]}
  - {questStage: {quest: reach-the-castle, stage: travel}}
  - {questComplete: reach-the-castle}
  - {questFailed: reach-the-castle}
  - {chance: 0.15}                                  # rolls on a scene-local stream
  - {priceOf: {good: fantasy.core:grain, above: 1.5}}   # dear, where you stand
  - {expr: "player.pools.hitpoints.current < player.pools.hitpoints.max * 0.25"}
```

A list of conditions is ANDed. Use `{any: [...]}`, `{all: [...]}`, `{not: {...}}`
for other logic.

That list is the whole vocabulary. It is enforced by
`mace.model.conditions.CONDITION_PAYLOADS`, which is also where each condition's
arguments are typed, so a misspelled tag or field is a load-time error naming
the nearest thing you might have meant.

Several conditions take a bare value rather than a mapping, because the field
name would add nothing: `{chance: 0.15}`, `{weather: [rain]}`,
`{questComplete: some-quest}`, `{not: {...}}`. Where an `actor` is expected and
omitted, it is the player.

### Effects

```yaml
effects:
  - {adjustStat: {actor: player, stat: hitpoints, delta: -8, reason: "troll's club"}}
  - {setStat: {actor: player, stat: hitpoints, value: {expr: "player.pools.hitpoints.max"}}}
  - {giveItem: {actor: player, item: gold, qty: 1}}
  - {takeItem: {actor: player, item: gold, qty: 10}}
  - {move: {actor: player, to: hagans-castle}}
  - {setFlag: {entity: chest, flag: locked, value: false}}
  - {setDisposition: {actor: troll, to: hostile}}
  - {setVar: {name: kingWarned, value: true}}
  - {reveal: {location: secret-cave}}
  - {say: "The troll grunts and steps aside."}
  - {advanceQuest: {quest: reach-the-castle, stage: deliver}}
  - {startCombat: {against: [troll], canFlee: true, onFlee: you-ran}}
  - {transferContents: {from: treasure-chest, to: player}}
  - {attachAlly: {entity: caravan-guard, until: {atLocation: {actor: player, location: hagans-castle}}}}
  - {dismissAlly: {entity: caravan-guard}}
  - {applyModifier: {actor: player, stat: speed, add: 10, ticks: 6, label: "Elixir of Haste"}}
  - {advanceTime: {ticks: 4}}
  - {playScene: fantasy.core:generic-shop}
  - {restart: {}}
  - {endGame: {}}
```

As with conditions, that is the whole vocabulary, enforced by
`mace.model.effects.EFFECT_PAYLOADS`. Disposition is its own effect rather than
a stat: `friendly`, `neutral`, and `hostile` are not numbers, and pretending
otherwise was the kind of ambiguity ADR-0003 exists to remove.

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
    survival: [exposure, rest]    # the default; + hunger, thirst for a survival game, [] to disable
    economy: market               # market | simple
  quests: [reach-the-castle]
  winConditions:
    - {questComplete: reach-the-castle}
  loseConditions:
    - {expr: "player.pools.hitpoints.current <= 0"}
  onWin:  victory-scene
  onLose: defeat-scene
```

`onWin` / `onLose` point at ordinary scenes, so the v0 idea of a "retry with
your magic sword" fallback works with no special machinery — it's just a scene
with choices.
