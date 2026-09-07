# 8. Authoring & the Wizard

The wizard is not a convenience wrapper around YAML. It is the primary way games
get made, and its quality determines whether anyone but the author of the engine
ever builds a world.

## The problem with the v0 wizard

The prototype at `src/wizard.py` established the right *tone* — patient,
explanatory, walking you through nested interactions — and its tone is the one
thing about it that survived into `mace.wizard`. Its limits were structural, and
this table is what phase 4 was built against. It is now history: the prototype
was removed once every row of it had a replacement.

| Problem | Fix |
|---|---|
| Prompts, validation, and flow control are tangled with `print`/`input` | Steps become **declarative data**; front-ends render them |
| References are typed by hand as free strings (`defineConditions` literally asks the user to type `player.location == castle`) | Every reference is **picked from a list** of things that exist |
| Recursion (`createInteraction` calling itself) means you can't back out, skip, or come back later | Flat, resumable **task list** over a project model |
| No validation until (never) | Validate on every save; a live problem list |
| Nothing is playable until everything is done | **Playtest from anywhere, at any time** |
| Only works in a terminal | Same flow graph drives CLI and web |

## The flow graph

An authoring flow is a list of **steps** described as data. `mace.wizard` owns
them; `mace.cli` and the web app are renderers.

```python
Step(
    id="game.intro",
    title="Write the introduction",
    help=(
        "These lines set the stage. The player presses enter between each one, "
        "so break them where you want a beat."
    ),
    field=TextList(min_items=1, placeholder="One morning the king's riders come..."),
    binds="game.introduction",
)

Step(
    id="location.entities",
    title="What's here?",
    help="Pick anything that should be at this location when the game begins.",
    field=MultiSelect(
        options=Query("entities", scope="project+libraries"),
        allow_create="entity",          # "+ Create a new one" inline
    ),
    binds="locations[{id}].entities",
)
```

Field types (`mace.wizard.fields`): `Text`, `TextList`, `Number`, `Bool`,
`Select`, `MultiSelect`, `StatAllocator`, `ConditionBuilder`, `EffectBuilder`,
`MapEditor`, `Repeat`. Each one answers two questions — `describe`, what the
current value is in English, and `parse`, how to read one typed line — which is
what keeps the terminal renderer thin and the field types testable without a
terminal. The ones a builder drives instead say so with `interactive`.

`Query` is the piece that fixes the biggest v0 gap: it asks the loaded project
and its libraries for valid options, so the author picks `Bridge Troll` from a
list and the wizard writes `fantasy.core:bridge-troll`. Dangling references stop
being possible to create. Two details the implementation adds: it reads the
project's **raw mappings** rather than compiled models, so a half-written
location is still something you can point at; and it resolves `extends`, so an
entity that inherits from `fantasy.core:soldier` and never writes `kind` is
still offered as an actor.

A step's **binding** says where the answer goes — `locations[{id}].entities`,
`game.player.startLocation`. Bindings read through `extends` as well, so the
wizard does not ask again about a field an object already has from its parent.

## The condition and effect builders

`defineConditions()` in v0 prints a syntax explanation and hopes. Its replacement
is a guided cascade, and it's the single highest-value piece of the wizard:

```
  What should this depend on?
    — The player
     1. Something somebody is carrying     — The story
     2. Where somebody is                 10. A quest is finished
     3. A character's stat is high enough 11. A quest has failed
     4. A character's stat is low enough  12. A quest has reached a stage
    — The world                            — Chance and combinations
     5. Something you flagged earlier     13. Random chance
     6. The weather                       14. All of several things
     7. The kind of weather — wet, cold   15. Any of several things
     8. The season                        16. The opposite of something
     9. The time of day                   17. Advanced: write an expression

  > 1

  Which item?
     1. The King's Token        (this pack)
     2. Reaping Hook            (this pack)
     3. Bread                   (fantasy.core)
     4. Gold                    (fantasy.core)
     ...
  > 4

  How many, at least?  > 10
  Who is carrying it?  (blank for player)  >

  ✓  the player is carrying at least 10 Gold
```

It emits `{hasItem: {item: fantasy.core:gold, qty: 10}}` and shows the
plain-English rendering back. Note what is *not* in that mapping: the cascade
filled `actor: player` in on the author's behalf and the round-trip through the
model dropped it again, so the file carries the smallest content that means what
the author said.

Both vocabularies are covered completely — every condition tag and every effect
tag has a recipe (`mace.wizard.builders`) and a phrasing
(`mace.wizard.language`), each guarded by a test that fails when a tag is added
without one. A tag the builder cannot produce is a tag an author has to
hand-write YAML for, and a tag the renderer cannot phrase is a line of YAML they
have to read. The same renderer displays existing conditions everywhere in the
UI, which is why an author can build a whole game and only see YAML if they go
looking. The `expr` option exists for power users and is never required.

## The authoring model

The wizard edits a **Project** — an in-memory pack plus authoring metadata
(completion state, notes, TODOs). Saving writes YAML; loading reads it. An author
can hand-edit files between sessions and the wizard picks up the changes, because
the project model is just the content model plus annotations.

The top level is a resumable task list, not a linear interview:

```
  A PEASANT'S QUEST                            ▸ 4 problems   ▸ 62% complete

    ✓  Game setup            name, intro, win/lose         complete
    ◐  World map             6 locations, 5 routes         2 locations have no exits
    ◐  Characters            4 defined                     'captain' has no scenes
    ✓  Items                 9 defined
    ○  Weather & climate     using fantasy.core defaults
    ◐  Encounters            2 tables                      north-road has no table
    ○  Quests                1 defined
    ✓  Player setup          Letholin, 20 creation points

    [ Playtest ]   [ Validate ]   [ Save ]   [ Export pack ]
```

You can work on anything in any order, leave things half-done, and come back.
That's how hobby projects actually get built.

Sections are groupings of **work**, not of collections: the world map is places,
roads, and regions together, and "characters" and "items" are two halves of one
collection. Completion is advisory in both directions — a section counts as done
when it holds something and has no errors, and an author can also mark one done
themselves and the wizard believes them. Nothing blocks anything, ever.

The terminal renders this as `mace author <pack>`, four screens deep — the task
list, a section, one object, one step — and you can leave any of them.

## The project, and loading content that is still wrong

A `Library` is finished content: immutable, validated, and useless to an author
halfway through a sentence. A **Project** is the other thing — the raw authored
mappings, editable, compiled on demand, and perfectly willing to be wrong for a
while.

Three rules shape it:

- **The YAML is canonical.** Objects are held as the mappings the author wrote,
  not as validated models, so an object the models would reject is still
  something the wizard can hold, show, and let you fix.
- **Every object stays in its file, in its place, with its comments.** The
  project holds the loaded *documents*, not detached copies of the objects in
  them, so an edit mutates the document and everything around it is untouched.
  Saving rewrites only files that actually changed, and a new object joins its
  collection wherever the author already keeps it.
- **Compiling never touches the disk**, so "playtest with unsaved changes" is
  true rather than approximately true.

This needed a change underneath. The loader used to stop at the first object it
could not build, which meant one misspelled field hid every other problem in the
pack — a world got fixed one invisible error at a time. Loading now carries a
**tolerance**: playing still stops at the first failure, because content that
will not compile cannot be played, while authoring collects failures, drops the
objects that caused them, and carries on. `mace validate` uses the collecting
form too, since reporting one error and hiding the rest is no better for CI than
it is for an author.

**Comments survive.** A content pack is mostly *explanation* —
`fantasy.core/combat.yml` opens with nine lines on why the counter matrix is
content rather than engine code — and a tool that ate that the first time it
touched a file would be a tool people stopped opening. So reading and writing
both go through `ruamel.yaml` in round-trip mode (`mace.content.writing`), and
the objects the wizard holds are the same objects it read, comments attached.
Editing one in place and dumping its document leaves the rest of the file
exactly as it was, down to the byte.

Three things do normalise, all cosmetic: hand-aligned columns collapse to one
space, redundant braces inside a flow sequence go away (`[{hasItem: ...}]`
becomes `[hasItem: ...]`), and a flow mapping the author wrapped by hand comes
back on one line. Across every file in `packs/` that is about a tenth of the
lines, no comments, and — checked by a test — no change of meaning anywhere.

This is the one place MACE takes a dependency it could have done without.
Neither `mace.engine` nor `mace.model` imports a YAML library at all, so the
Pyodide constraint is untouched; `ruamel.yaml` sits in the content layer beside
the `pyyaml` that was already there.

## Validation

Runs on save and on demand. Three severities:

- **Error** — the game cannot run. Dangling reference, unreachable start
  location, a quest that can never complete, a cycle in `extends`, a scene that
  `goto`s itself with no exit.
- **Warning** — probably a mistake. An entity nothing references, a scene nothing
  reaches, a location with no exits, an encounter entry whose `when` can never be
  true, a route with `ticks: 0`.
- **Note** — design advice. "This road has no encounters — journeys along it will
  feel empty." "This game has no safe locations, so the player can never rest."

Every message names the file, the id, and offers a fix where one is obvious.
Errors block export but never block saving — an author must be able to stop
mid-thought.

## Playtest from anywhere

The single most important feature for keeping authors engaged. From any point in
the wizard: **`[ Playtest ]`** launches a session with

- the current in-memory project (unsaved changes included)
- a fixed seed by default, so behavior is reproducible while iterating
- the ability to start at any location, with any items, at any tick, in any
  weather, as any background
- a debug overlay: current conditions being evaluated, encounter rolls with their
  results, active modifiers and their sources, the RNG stream positions

Being able to say "start me at the Troll Bridge at midnight in a blizzard with a
magic sword" and immediately see it is what turns authoring from a chore into
play. Every part of that is a **session-opening parameter**, the way the seed is
— `begin()` takes `start_at` and `start_tick`, and the weather and the extra kit
are set on the opening state — so a playtest is still an ordinary replayable
session rather than a special mode. The weather is *set* and then left to the
simulation, because watching a blizzard lift is half of why you asked for one.

The setup is remembered in `.mace/project.yml`, because iterating means running
the same awkward corner twenty times and retyping "the bridge, at midnight, in a
blizzard" twenty times is how people stop iterating.

The overlay (`mace.engine.debug`) is a **projection**, not a second event
channel: it reads state and content and returns a description, and the engine
emits nothing extra when somebody is watching. A test asserts that a playthrough
with it open records the same events as one without, because otherwise the
overlay would be a second engine. It hands conditions back unrendered and the
front-end puts them into English, which is how the engine avoids importing the
wizard.

## Generators and assists

For authors staring at an empty world, the wizard offers scaffolding — always
editable, never mandatory:

- **World starter** *(built)* — pick a flavour and a size, get a hub, some
  settlements, one dangerous place at the far end, roads between them with
  sensible travel times, and a region per band. A skeleton to rearrange rather
  than a blank page. It writes exits as well as routes, because a route is a
  road and an exit is the option to walk down it, and a starter map that opened
  with five "cannot leave" notes would be a worse start than an empty file.
- **Encounter table suggestions** *(built)* — from the route's `dangerLevel`,
  propose a table drawn from the loaded libraries, with the tuning presets from
  [Travel & Encounters](06-travel-and-encounters.md#tuning-guidance-for-authors).
  The entries are borrowed, never invented, so every reference in the result is
  real — the same rule the pickers follow.
- **Statblock assistant** *(partly)* — the `StatAllocator` field takes a budget
  and spreads it, which is the shape of it. What is still missing is the part
  that reads the player's expected state at that point in the game and proposes
  a number, which needs the balance report below to exist first.
- **Balance report** *(not yet)* — walk the quest graph and report the expected
  player power curve against encounter difficulty by region, flagging spikes.

These are the difference between "I have an idea for a world" and "I have a
world."

A flavour is a **naming palette and nothing else**. The shape of the map is
identical in all of them, checked by a test, because "a road between two
settlements" is not a fantasy idea and a generator that assumed otherwise would
make `scifi.core` a second-class citizen ([Vision](01-vision.md)). Generation
goes through the seeded RNG service, so "give me another one" is a different
seed rather than a dice roll and the one you liked is still there.

**Generation is an authoring assist and never a play-time feature.** Everything
above produces content the author reviews and edits before anyone plays it.
Nothing is generated during a session — the variety players experience comes from
simulation (weather, events, encounters, markets), which is consistent and
learnable, rather than from generation, which can't be balanced and undermines
determinism.

## CLI and web parity

Because steps are data, the CLI and the web app render the same flow. The CLI
stays the fast path for authors who like a terminal (and for the maintainers,
since it's testable end to end); the web app adds direct manipulation the
terminal can't do — dragging map nodes, drawing routes, seeing the scene graph.

Neither is a second-class citizen. A step type that can't render usefully in the
terminal (`MapEditor`) must declare a text fallback.

### The authoring session

Phase 4 made the *questions* data and left the screens around them inside the
terminal loop, which meant "the same flow graph drives CLI and web" was true of
the steps and untrue of everything holding them. `mace.wizard.studio` is the
other half, and `mace.session` is its twin: a session holds a playthrough open
and hands out frames, a studio holds a **project** open and hands out screens.

One shape for every reply — the pack, which files are unsaved, the task list,
and whatever was asked for — so a client has one renderer, and so the problem
count in the header moves on every answer without anybody asking for it.

Three things it adds over the flow graph, and none of them is a rule:

- **Options are resolved.** A `Select` reaches a browser as the list a `Query`
  produced, because a browser cannot ask the catalog a question in the middle
  of a render. This is the piece that makes a web form possible at all; without
  it a form would go straight back to typing references by hand, which is the
  exact hole `Query` exists to close.
- **Screens are described.** The task list, a section's contents, one object's
  steps — the same three the terminal walks, as JSON.
- **The cascade is data too.** Both vocabularies ship with their questions, so
  a tag added to `mace.wizard.builders` appears in the browser without anybody
  touching the browser. `build` round-trips through the model on the Python
  side, which is what stops a browser writing content the loader would reject.

`mace.api.author` is the HTTP surface and **it is off unless asked for**.
Authoring writes to the author's disk and the session service never does, so
the routes are a separate router that `create_app` mounts only when handed an
open studio. `mace author --web` is the way in: one pack, bound to localhost,
the same questions and the same validator as the terminal. One pack per
process, the way the terminal is one pack per window — a project holds unsaved
edits in memory, and two behind one process would be two authors overwriting
each other.

The client lives at `#author` in the same build as the game. It renders the
three screens and every field type that can be answered with a control; a
field a builder drives — a condition, a repeat, a statblock — is shown as its
English description and says the terminal can change it, because rendering
nothing would lose an author's content silently. Its tests replay frames
recorded from a real project by `tests/test_web_author_wire.py`, the same
arrangement the game client has and for the same reason.
