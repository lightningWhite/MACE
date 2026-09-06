# 2. Architecture

## The shape of the system

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONT-ENDS                                                          │
│                                                                      │
│   CLI player     CLI wizard     Web PWA (play + author)   HTTP API   │
│        │              │                    │                  │      │
└────────┼──────────────┼────────────────────┼──────────────────┼──────┘
         │              │                    │                  │
         │   actions ↓  │   events ↑         │                  │
         │              │                    │                  │
┌────────┴──────────────┴────────────────────┴──────────────────┴──────┐
│  SESSION LAYER          mace.session                                  │
│  Owns a running game. Applies actions, emits events, snapshots and    │
│  restores saves, projects a read-only view-model for UIs.             │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────┴──────────────────────────────────────┐
│  ENGINE CORE            mace.engine        (pure • deterministic)     │
│                                                                       │
│   state ──► rules ──► (state', events)                                │
│                                                                       │
│   world/      clock, calendar, climate, weather fronts, disasters     │
│   encounter/  route and location encounter rolls                      │
│   combat/     tempo combat resolution                                 │
│   expr/       safe evaluation of author conditions and effects        │
│   rng/        named, independently-seeded random streams              │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  reads (never writes)
┌───────────────────────────────┴──────────────────────────────────────┐
│  CONTENT LAYER          mace.content / mace.model                     │
│  Loads packs, resolves namespaced ids, applies `extends` inheritance, │
│  validates against schemas, produces an immutable compiled World.     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                     packs/  (YAML on disk, or a compiled .macepack)
```

Data flows **down** as reads and **up** as events. Nothing below the session
layer knows a user exists.

## The three hard boundaries

### Boundary 1 — content is immutable, state is not

This is the single most important correction to the v0 templates, which mix the
two. `templates/interactiveElement.yml` has both `strength.max` (a property of
what a troll *is*) and `strength.current` (a property of *this* troll right now,
in *this* playthrough).

| | Content | State |
|---|---|---|
| Lives in | `packs/**/*.yml` | The save file |
| Shared by | every playthrough, every player | one session |
| Example | "trolls have base strength 70" | "this troll is at 31 hp and afraid" |
| Mutability | frozen after load | mutated every tick |
| Model type | `mace.model.*` (pydantic, frozen) | `mace.engine.state.*` |

Instantiating an entity into a session copies the content template into a state
object with a session-local instance id. Ten goblins from one `goblin` definition
are ten state objects pointing at one content object.

Why it matters: without this split you cannot have two of anything, you cannot
save compactly, you cannot share libraries safely, and multiplayer is impossible.

### Boundary 2 — the engine is pure

`mace.engine` may not:

- print, prompt, or read stdin
- open files or sockets
- read the wall clock (`time.time()`, `datetime.now()`)
- call `random` directly
- mutate content models

Everything it needs is passed in. Everything it produces comes back as return
values. This is enforceable in CI with an import lint, and it is what makes
replay, testing, and browser execution work.

### Boundary 3 — front-ends see events, not state

The engine's step function is:

```python
def step(state: GameState, action: Action) -> StepResult:
    """Apply one player action. Returns the new state and everything that
    happened, in order."""
```

`StepResult.events` is an ordered list of typed messages. A front-end's entire
job is turning those into pixels or characters, and turning input into `Action`s.

Selected event types (the full list lives with the code):

| Event | Payload | Rendered as |
|---|---|---|
| `narrate` | `text`, `pause` | A line of prose, optionally waiting for enter |
| `choices` | `sceneId`, `options[]` | A numbered menu / buttons |
| `moved` | `from`, `to`, `viaRoute` | Map update, journey framing |
| `travel.leg` | `route`, `leg`, `of`, `waypoint`, `text` | "You ford the shallows at midday." |
| `travel.interrupted` | `route`, `at`, `destination`, `remaining`, `reason` | "The troll does not move." |
| `world.time` | `tick`, `dayPart`, `day`, `season` | Clock / sky in the UI chrome |
| `weather.changed` | `region`, `condition`, `intensity`, `tags`, `visibility` | "The rain thickens into sleet." |
| `world.status` | `day`, `dayPart`, `season`, `place`, `sky`, `light` | The standing status line, above the prompt |
| `encounter` | `table`, `entry`, `chance`, `where` | Nothing on its own — the scene that follows is the encounter |
| `world.event` | `event`, `phase`, `region`, `visible` | Map marker and journal entry; the prose comes as `narrate` |
| `world.news` | `event`, `daysOld`, `region` | Something that happened out of sight, arriving late |
| `route.changed` | `route`, `closed`, `ticks`, `reason` | The map is different now, and stays that way |
| `stat.changed` | `actor`, `stat`, `delta`, `reason` | Health bar animation, "(-8 hp)" |
| `inventory.changed` | `actor`, `item`, `delta` | Inventory panel |
| `quest.updated` | `questId`, `stage`, `status` | Journal entry |
| `combat.begin` | `combatants`, `arena` | Switch to combat view |
| `combat.tell` | `move`, `windowMs`, `cue` | The telegraph the player reacts to |
| `combat.resolve` | `precision`, `read`, `damage`, `momentum` | Hit feedback |
| `combat.end` | `outcome`, `spoils` | Return to exploration |
| `game.over` | `outcome`, `reason` | Win/lose sequence |

The CLI renders `combat.tell` as a line of text with a keypress deadline; the PWA
renders it as a shrinking timing bar. Same event, same engine, same fairness.

`world.status` is the one event that is a projection rather than a happening.
A status line has to be *standing* — `Day 3 · dusk · Fenmoor · light rain` —
and the alternative to emitting it is letting the UI reach into engine state
for it, which is the boundary this protocol exists to hold. It is emitted last
in every step, so it describes the world the offered choices belong to.

## Determinism and randomness

A session is fully described by:

```
(pack references + versions, seed, ordered action log)
```

Replaying that triple reproduces the playthrough exactly. Save files store the
triple plus a periodic state snapshot for fast loading; the snapshot is an
optimization, never the source of truth.

A logged choice may name its option two ways. `{"kind": "choose", "option": 2}`
is the protocol form — an index into the last `choices` event, which is what
the engine takes and what a live front-end sends. `{"kind": "choose", "prompt":
"Speak to the troll"}` is the **recorded** form, resolved against the options
that were actually offered.

The difference matters whenever a log outlives the content that produced it.
An index silently means something else the moment an author inserts a menu
entry above it: the log still replays, down a different road, and nothing says
so. A prompt walks the same road, or fails loudly with the menu that *was* on
offer in the message. Golden recordings use prompts for exactly that reason;
so should anything else written down for a human to read.

Randomness comes from **named streams**:

```python
rng = state.rng.stream("weather")        # independent of every other stream
front = rng.choice(candidate_fronts)
```

Each stream is derived as `PCG64(hash(root_seed, stream_name))` and its position
is part of the state. Consequences:

- Adding a new subsystem that rolls dice does not shift the weather sequence.
- A combat that lasts 40 exchanges instead of 12 does not change which encounter
  you meet an hour later.
- Two players in a future shared world can resolve independent events without
  desyncing.

**Stream naming convention:** `weather`, `weather.fronts`, `encounters.<routeId>`,
`combat.<combatId>`, `loot`, `ambient`, `authoring`. Per-entity streams are keyed
by instance id so an entity's behavior is stable regardless of turn order.

## Time

- A **tick** is the atomic world time unit. Its real-world meaning is set per
  game (`world.minutesPerTick`, default 30).
- A **turn** is one player action. Looking around costs 0 ticks; talking costs
  1; traveling costs the route's length in ticks; resting costs many.
- Combat happens *inside* a tick. Its internal clock is milliseconds of
  simulated exchange time and never advances the world clock beyond the tick
  the fight occupies.

Every tick, in fixed order (order matters for reproducibility):

1. Advance clock → day part, day, season
2. Advance weather (fronts move, local conditions transition)
3. Advance world events (pressure, omens, phase transitions)
4. Apply environmental effects to actors (stat modifiers, exposure)
5. Expire timed modifiers and status effects
6. Advance quest timers, evaluate quest stage transitions
7. Evaluate game win/lose conditions

## Repository layout

```
MACE/
├── readme.md
├── CLAUDE.md
├── docs/                       Design docs (you are here)
├── schemas/                    JSON Schema, one file per content type
│   ├── pack.schema.json
│   ├── entity.schema.json
│   └── ...
├── packs/
│   ├── mace.core/              Genre-neutral primitives (stats, day parts, base weather)
│   ├── fantasy.core/           Shared fantasy library — trolls, taverns, temperate climate
│   ├── scifi.core/             Later. Proves genre-neutrality.
│   └── games/
│       └── peasants-quest/     A complete playable game pack
├── src/mace/
│   ├── model/                  Frozen pydantic content models
│   ├── content/                Pack discovery, id resolution, inheritance, validation
│   ├── engine/
│   │   ├── state.py            GameState and friends
│   │   ├── actions.py          Player action types
│   │   ├── events.py           Event types
│   │   ├── step.py             The step function and tick pipeline
│   │   ├── expr/               Safe expression parser + evaluator
│   │   ├── rng/                Seeded named streams
│   │   ├── world/              Clock, climate, weather, world events
│   │   ├── encounter/          Encounter table resolution
│   │   ├── economy/            Goods, markets, price formation, trade flow
│   │   └── combat/             Tempo combat
│   ├── session.py              Session lifecycle, saves, view-model projection
│   ├── wizard/                 Declarative authoring flow graph
│   ├── cli/                    Terminal front-end
│   └── api/                    FastAPI service (phase 4+)
├── web/                        PWA client (phase 4+)
└── tests/
    ├── unit/
    ├── packs/                  Validation tests over every shipped pack
    └── golden/                 Replay conformance: seed + actions → expected events
```

### Migrating the prototype

`src/wizard.py` and `src/modules/objects/` are v0. The plan:

| v0 | Becomes |
|---|---|
| `modules/objects/game.py` | `mace/model/game.py` (frozen) + `mace/engine/state.py` |
| `modules/objects/interaction.py` | `mace/model/scene.py` — with ids, so scenes are referenceable rather than only nested |
| `wizard.py` prompt helpers | `mace/cli/prompt.py` |
| `wizard.py` `create*` functions | `mace/wizard/flows/*.py` as declarative steps |
| `src/games/` | `packs/games/` |

Nothing in v0 is thrown away conceptually — the interaction model
(visible / description / conditions / dialog / modifiers / nextActions /
fallbacks) is a good design and survives nearly intact as the Scene. What changes
is that scenes get ids, conditions and effects get structure instead of being
free strings, and the whole thing gets validated.

## Why Python for the core

The engine stays Python, with a hard constraint of **stdlib + pydantic only**, so
it can run under Pyodide in a browser tab with no server. That gives:

- terminal play today
- a static, GitHub-Pages-hostable PWA with no backend (phase 5)
- a server-authoritative deployment later by running the same code behind FastAPI

The escape hatch, if Pyodide's download size proves unacceptable: the engine is
specified precisely enough here, and covered by golden replay tests, that a
TypeScript port can be verified against the Python one. That is a real cost, but
it's a decision that can be made later with data rather than now on a guess. See
[ADR-0005](decisions/0005-python-core-with-pyodide.md).
