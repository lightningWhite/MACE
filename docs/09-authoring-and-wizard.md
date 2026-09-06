# 8. Authoring & the Wizard

The wizard is not a convenience wrapper around YAML. It is the primary way games
get made, and its quality determines whether anyone but the author of the engine
ever builds a world.

## The problem with the v0 wizard

The prototype in `src/wizard.py` establishes the right *tone* — patient,
explanatory, walks you through nested interactions. Its limits are structural:

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

Field types: `Text`, `TextList`, `Number`, `Bool`, `Select`, `MultiSelect`,
`StatAllocator`, `ConditionBuilder`, `EffectBuilder`, `MapEditor`, `Repeat`.

`Query` is the piece that fixes the biggest v0 gap: it asks the loaded project
and its libraries for valid options, so the author picks `Bridge Troll` from a
list and the wizard writes `fantasy.core:bridge-troll`. Dangling references stop
being possible to create.

## The condition and effect builders

`defineConditions()` in v0 prints a syntax explanation and hopes. Its replacement
is a guided cascade, and it's the single highest-value piece of the wizard:

```
  What should this depend on?
    1. Something the player has        5. The weather or time of day
    2. Where the player is             6. A quest's progress
    3. A character's stats             7. Something you flagged earlier
    4. A character's mood toward you   8. Random chance
    9. Advanced: write an expression

  > 1

  Which item?
    1. gold                    (fantasy.core)
    2. magic sword             (this game)
    3. king's token            (this game)
    ...
  > 1

  How many?  > 10

  ✓  Player is carrying at least 10 gold
```

It emits `{hasItem: {actor: player, item: fantasy.core:gold, qty: 10}}` and shows
the plain-English rendering back. The same renderer displays existing conditions
everywhere in the UI, so authors read English and only see YAML if they go
looking. Option 9 exists for power users and is never required.

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

## The project, and loading content that is still wrong

A `Library` is finished content: immutable, validated, and useless to an author
halfway through a sentence. A **Project** is the other thing — the raw authored
mappings, editable, compiled on demand, and perfectly willing to be wrong for a
while.

Three rules shape it:

- **The YAML is canonical.** Objects are held as the mappings the author wrote,
  not as validated models, so an object the models would reject is still
  something the wizard can hold, show, and let you fix.
- **Every object remembers its file.** An author who split their world into
  `locations.yml` and `people.yml` keeps that arrangement, and objects keep the
  position they were read in. Saving rewrites only files that actually changed.
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

**A known cost.** Saved files are written with `yaml.safe_dump`, which does not
preserve comments or an author's chosen layout: a file the wizard rewrites comes
back tidy and uncommented. Only rewriting changed files keeps that blast radius
small, and a pack the wizard created has no comments to lose — but editing a
hand-written pack like `fantasy.core` in the wizard *will* flatten the file it
touches. Fixing it properly means a round-tripping YAML library, which is a
dependency decision rather than an implementation detail;
`mace.content.writing` is the one-function seam where that change would happen.

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
  weather
- a debug overlay: current conditions being evaluated, encounter rolls with their
  results, active modifiers and their sources, the RNG stream positions

Being able to say "start me at the Troll Bridge at midnight in a blizzard with a
magic sword" and immediately see it is what turns authoring from a chore into
play.

## Generators and assists

For authors staring at an empty world, the wizard offers scaffolding — always
editable, never mandatory:

- **World starter** — pick a genre and a size, get a plausible map of regions,
  locations, routes with sensible travel times, and a climate. A skeleton to
  rearrange rather than a blank page.
- **Encounter table suggestions** — from the route's `dangerLevel` and terrain,
  propose a table drawn from the loaded libraries, with the tuning presets from
  [Travel & Encounters](06-travel-and-encounters.md#tuning-guidance-for-authors).
- **Statblock assistant** — "how hard should this fight be?" on a five-point
  scale, given the player's expected state at that point in the game, and it
  proposes stats and a combat profile.
- **Balance report** — walks the quest graph and reports the expected player
  power curve against encounter difficulty by region, flagging spikes.

These are the difference between "I have an idea for a world" and "I have a
world."

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
