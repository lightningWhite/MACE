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
| `combat.begin` | `combatants`, `mode`, `canFlee`, `matrix` | Switch to combat view; the matrix is the training wheels |
| `combat.tell` | `move`, `type`, `text`, `windowMs`, `clear` | The telegraph the player reacts to. `type` is empty when the tell was not legible |
| `combat.responses` | `options[]`, `stamina`, `momentum`, `streak` | What the player may answer with, and the resources they are spending. Each option is a `response` and a `label` |
| `combat.resolve` | `read`, `result`, `precision`, `damageTaken`, `damageDealt`, `momentum` | Hit feedback that says *why* |
| `combat.end` | `outcome`, `exchanges`, `spoils` | Return to exploration |
| `game.over` | `outcome`, `reason` | Win/lose sequence |

The CLI renders `combat.tell` as a line of text with a keypress deadline; the PWA
renders it as a shrinking timing bar. Same event, same engine, same fairness.

`combat.responses` is to a fight what `choices` is to a scene, and it exists for
the same reason: without it a front-end would have to reach into engine state to
find out what the player can do. It carries stamina and momentum because those
are the resources being managed and a UI has to show them somewhere permanent —
the same argument that produced `world.status`. Each option carries a `label`
for the same reason `choices` carries a `prompt`: only the engine knows that
`use:fantasy.core:healing-draught` is called "Healing Draught", and a front-end
that worked that out would be reading content.

`world.status` is the one event that is a projection rather than a happening.
A status line has to be *standing* — `Day 3 · dusk · Fenmoor · light rain` —
and the alternative to emitting it is letting the UI reach into engine state
for it, which is the boundary this protocol exists to hold. It is emitted last
in every step, so it describes the world the offered choices belong to.

#### The other half: the view-model

Events are things that happened, and a panel is a standing fact. The pack in
your hands, the quests in your journal, the map of what you know: a front-end
that rebuilt those by accumulating events would be keeping a second copy of
the world, and the first thing a second copy does is disagree with the first.

So a front-end renders events *and* reads `mace.session.view` — a read-only
projection of content and state into a character sheet, an inventory, a
journal, and an atlas of places and roads. Like the debug overlay it changes
nothing: the engine emits nothing extra because somebody is looking, and a
playthrough with the map open replays byte-identically to one without it.

Two rules keep it from becoming a hole in this boundary.

**Fog of war is applied in the projection, not in the client.** A place the
player has not heard of is not in the atlas at all, rather than being in it
with a flag the client is trusted to honour. `revealed` is what the player has
heard of and `visited` is where they have actually stood — kept apart, because
a map that cannot tell those two apart has thrown away the reward for going.

**Reading never draws.** A region's weather chain is advanced by `sync`, at
the points where time moves, so a region the player is nowhere near shows the
sky it had when they last looked at it. That is not a limitation of the
projection; on a fogged map it is the only honest thing to draw.

## Determinism and randomness

A session is fully described by:

```
(pack references + versions, seed, ordered action log)
```

Replaying that triple reproduces the playthrough exactly, and that triple *is*
the save file — `mace.session.saves`, one JSON object, small enough to paste
into a bug report. A periodic state snapshot alongside it, for fast loading,
is an optimization and never the source of truth. It is not written yet, which
has two consequences worth knowing: a long playthrough reloads by re-simulating
itself, and a save whose content has moved under it cannot be continued past
the divergence, only reported.

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
│   ├── session/                Session lifecycle, saves, view-model projection
│   ├── wizard/                 Declarative authoring flow graph
│   ├── cli/                    Terminal front-end
│   └── api/                    FastAPI service (phase 4+)
├── web/                        PWA client (phase 4+)
└── tests/
    ├── unit/
    ├── packs/                  Validation tests over every shipped pack
    └── golden/                 Replay conformance: seed + actions → expected events
```

### What became of the prototype

`src/wizard.py` and `src/modules/objects/` were v0. They are gone as of phase
4; this is where each part of them ended up.

| v0 | Became |
|---|---|
| `modules/objects/game.py` | `mace/model/game.py` (frozen) + `mace/engine/state.py` |
| `modules/objects/interaction.py` | `mace/model/scene.py` — with ids, so scenes are referenceable rather than only nested |
| `modules/objects/*` mutable state | `mace/wizard/project.py` — raw authored mappings, compiled on demand |
| `wizard.py` `create*` functions | `mace/wizard/flows.py` as declarative steps |
| `wizard.py` `defineConditions()` | `mace/wizard/builders.py` — a cascade, plus `language.py` to read it back in English |
| `wizard.py` prompt helpers | `mace/cli/author.py`, which is rendering and nothing else |
| `src/games/` | `packs/games/` |

Nothing in v0 was thrown away conceptually — the interaction model
(visible / description / conditions / dialog / modifiers / nextActions /
fallbacks) is a good design and survives nearly intact as the Scene. What
changed is that scenes got ids, conditions and effects got structure instead of
being free strings, the whole thing gets validated, and the questions became
data so a browser can ask them too.

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
