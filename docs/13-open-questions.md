# 13. Open Questions

Design questions that were deliberately left open at the end of the first design
pass, and how they were settled. Nearly all are now decided; the few that remain
are marked as such.

Larger forks in the road have their own [decision records](decisions/).

---

## 1. What does "MACE" stand for? — **RESOLVED**

**Decided:** MACE is the **Modular Adventure Creation Engine**.

"Magic and Combat Environment" was fantasy-specific, and the engine is explicitly
meant to run sci-fi, dystopia, and anything else. Same letters, same repo, no
rename — it just stops promising magic to someone building a generation ship.
The original expansion is kept as a footnote in the readme; it's the project's
history.

---

## 2. Party members, or a lone protagonist? — **RESOLVED**

**Decided:** one protagonist, with **temporary allies**.

Encounters and quests can attach an ally for a stretch — a caravan guard who
fights beside you through the wood, a guide who knows the pass, an NPC escorting
you as far as the castle. They fight on their own combat profiles in `auto` mode,
carry their own inventory, and can be lost.

This is cheap: combat already resolves M-vs-N, and `disposition` already exists.
It gets most of the emotional payoff of companions — someone to lose — without
the party management, shared inventory, formation tactics, and dialog complexity
that a permanent party demands.

**Consequences:**
- `{attachAlly: {entity: X, until: <condition>}}` and `{dismissAlly: ...}` effects.
- Allies are ordinary actor entities. No new type.
- The player may spend a combat exchange issuing an order instead of acting.
- Not building: recruitment screens, party inventory, member equipment management.

**Built in phase 3.** An ally is an entity with a flag: it follows the player,
races the action meter alongside the enemies, and whatever it swings at answers
on `auto` so nobody waits on a keypress for a fight they are watching. The one
order is `focus`, which moves the party's attention to the next enemy still
standing and costs the exchange it is given in. An ally attached `until` some
condition leaves the moment it comes true, wherever that happens to be.

---

## 3. How much economy? — **RESOLVED**

**Decided:** a **full market simulation** — supply, demand, stock, price
formation, trade flow between markets, and prices that move with world events.

This diverges from the original recommendation (which was simple item values), on
the grounds that the coupling is worth it: the region graph, route lengths, route
danger, and the event system already exist, and a market model built on top of
them makes all four *matter more*. When the Ashfell erupts and the pass closes,
iron gets dear in the mountain towns because trade flow actually stopped — not
because a script said so.

Full design in [Economy](08-economy.md). Key containment decisions:

- **Lazy evaluation** — markets are a pure function of tick and route state, so a
  hundred of them cost nothing until queried.
- **`economy: simple`** remains available per game, so a tight 45-minute story
  doesn't have to think about grain.
- **Hard price bounds** (0.25×–4× base) so no feedback loop runs away.
- **Never a gate** — a player who ignores trade is never blocked. Money is a
  lever, not a key.
- **Phased**: item values in phase 1, markets and trade flow in phase 5, event
  shocks and haggling in phase 6. Building it before there's a world to react to
  would be simulating in a vacuum.

---

## 4. Hunger, thirst, rest, and exposure? — **RESOLVED**

**Decided:** **rest and exposure** are built in. Hunger and thirst are optional
pools a game may enable.

Exposure is what makes weather bite. A blizzard that only slows you down is
scenery; a blizzard that costs you hitpoints while you're out in it turns
"shelter or push on" into a real decision, and gives the inn a reason to exist.
Rest is its counterpart — the way you recover, at the cost of days you may not
have.

Hunger and thirst are *content-defined pools* switched on in `game.rules`. Not
every world wants to be a survival game, and forcing rations on a story-driven
quest would be wrong.

**Consequences:**
- `exposure` accumulates while outdoors in a condition tagged `cold`, `wet`, or
  `severe`, scaled by intensity, reduced by clothing and endurance.
- Locations flagged `indoors: true` suppress it; resting there clears it.
- Resting advances the clock significantly — which interacts with quest
  deadlines, weather fronts, and event pressure. That's the point.
- `game.rules.survival: [exposure, rest]` by default; `[exposure, rest, hunger,
  thirst]` for a survival game; `[]` to disable.

---

## 5. Magic — engine feature or content? — **RESOLVED**

**Decided:** **content, not engine.**

A spell is a combat move with `wisdom` scaling and a mana cost — which pools,
moves, effects, and items already express. `fantasy.core` defines a `mana` pool
and a spell move family; the engine stays ignorant of magic entirely.

The alternative would bake fantasy assumptions into the core, which
[Vision](01-vision.md) explicitly forbids and which would make `scifi.core` a
second-class citizen. If authoring a rich magic system in content proves painful
after real use, the common parts can be promoted then — with evidence.

---

## 6. How does the player character get defined? — **RESOLVED**

**Decided:** the author defines a protagonist, marks which stats are
customizable, and optionally offers **backgrounds**.

A background ("farmhand", "poacher", "disgraced squire") grants different
starting stats, items, skills, and sometimes a different opening scene or an
extra dialog option later. It's cheap to author, adds real replay value, and
stays entirely in content — no class system, no engine involvement.

```yaml
backgrounds:
  - id: poacher
    name: "Poacher"
    description: "You know the wood better than its owner does."
    stats: {stealth: {add: 15}, speed: {add: 5}, charisma: {add: -5}}
    inventory: [{item: fantasy.core:snare, qty: 2}]
    skills: {fantasy.core:bow: 20}
    grantsFlag: knows-the-wood      # scenes can check this later
```

The v0 `creationPoints` idea survives intact: after picking a background, the
player spends points on stats marked `customizable`.

---

## 7. Procedural generation — how far? — **RESOLVED**

**Decided:** generation is an **authoring assist**, never a play-time feature.

The wizard can generate a starter map, suggest encounter tables, and propose
statblocks — all reviewed and edited by the author before anyone plays. Nothing
is generated during play.

The reasoning is that the variety players experience should come from
**simulation** — weather, fronts, events, encounters, markets — not from
generation. Simulated variety is consistent, learnable, and therefore something a
player can get good at reading. Generated variety is unaccountable, can't be
balanced, and undermines determinism. The whole design leans on the first kind.

---

## 8. Does the wizard write YAML, or a project file? — **RESOLVED**

**Decided:** the wizard **edits YAML packs directly**, with authoring metadata
(completion state, notes, map layout hints) in a `.mace/project.yml` sidecar
inside the pack.

Keeps the YAML canonical and hand-editable at all times, which matters for a
git-based community, and avoids a second format that can drift out of sync.

---

## 9. Modding an existing game vs. forking it — **RESOLVED (deferred)**

**Decided:** fork and edit. No patch/overlay mechanism for now.

`extends` already covers reusing *pieces* of another pack. A mechanism for
patching a whole published game is a lot of machinery for a problem nobody has
yet. Revisit if it actually comes up.

---

## 10. What is the multiplayer model? — **RESOLVED (direction only)**

**Decided:** **asynchronous shared persistent worlds.**

Several players run their own sessions on one persistent map. Your choices leave
traces others find — the bridge you burned, the troll you killed and the toll
nobody has to pay now, the message you left at the shrine, the market you emptied
of iron. Nobody waits on anybody.

This suits text pacing far better than real-time play, needs no netcode, and the
deterministic architecture already supports it. It also composes unusually well
with the rest of the design: the economy is shared state that many players can
move, and world events are shared history that everyone lives through.

Still phase 8, and the details are genuinely undesigned. What's settled is the
*direction*, which is enough to keep architectural decisions honest now.

---

## 11. Localization — **RESOLVED (deferred)**

**Decided:** no i18n machinery now, but the option stays cheap.

The rule that makes it cheap: **the engine never concatenates player-facing
strings.** It emits structured events; front-ends render them. Everything
player-facing lives in content, so translating a game means translating its pack.
Following that rule means a translation layer can be added later without touching
the engine.

---

## Still genuinely open

Not yet worth deciding, listed so they aren't forgotten:

- **Difficulty presets.** Should a game ship easy/normal/hard, and what should
  they change — enemy `tellClarity` and `feintChance`, timing window width,
  encounter rates, economy harshness? Needs real play to answer.
- **Save slots vs. a single autosave.** Interacts with `deathIsPermanent` and
  with how forgiving the game wants to be.
- **How much the map reveals.** Fog of war is decided; whether the player sees
  route danger, travel estimates, or weather in unvisited regions is a tuning
  question that needs playtesting.
- **Audio.** Ambient sound and music in the web client would do a lot for
  atmosphere. Entirely unexplored, and out of scope until phase 6.
- **Should a monster's pools have to match the player's?** `StatAllocator` is
  deliberately genre-neutral — free-form, with suggestions drawn from what the
  pack already uses, so a monster can invent `hull-integrity` beside
  `hitpoints`. Surfaced by an author (2026-09-07) trying to build a
  statblock and wondering whether pools should instead be a closed list
  matching the player's own, so `hitpoints` always means the same axis on
  both sides of a fight. Needs a decision, not a fix — the free-form shape is
  intentional as things stand.
- **What coordinate convention does the map editor use?** A `mapPosition` is
  two numbers with no stated origin, axis direction, or unit — an author
  dragging a place has no way to read back "how far" or "which way" beyond
  the picture. Worth picking one (top-left origin, x right, y down, unit
  roughly pixels-per-tick per `web/src/map/layout.ts`'s `PIXELS_PER_TICK`) and
  showing live coordinates while dragging.
- **Exposing tick length and the clock to authors.** `game.world.minutesPerTick`
  and `game.world.startTick` are answered blind — an author sets "thirty
  minutes" and "tick 40" with no display anywhere of what a day is in ticks or
  what time of day a tick number means. Needs a small readout (ticks per day,
  and the wall-clock time a given tick lands on) wherever ticks are set or
  shown, in both the wizard and play itself.
- **Editing an existing repeat entry.** An exit, a stage, an inventory stack —
  anything added through a `Repeat` field — can be added or removed but not
  reopened once it exists. Found while fixing the exit/stage condition bug
  (2026-09-07): the entry's own little form (`EntryForm` in
  `web/src/author/Field.tsx`) only ever composes a *new* entry locally, and
  there is no endpoint that hands back the English rendering of an
  already-authored condition/effect the way a fresh `POST /build` does, which
  is what an edit screen would need to redraw one. A real fix wants either
  that endpoint or a redesign of how repeat entries round-trip, not a quick
  patch.
- **An author-facing reachability view for locations, not just scenes.** The
  scene graph answers "is there any way in?" for scenes; there is nothing
  equivalent for the world map — no single screen answering "from here, where
  can you actually get to, and is anywhere unreachable?" for locations and
  their exits.
- **A full-screen, non-scrolling layout for play.** Raised by an author
  (2026-09-07): on a large screen the map, status (hitpoints, stamina, day,
  location, weather), and prompt currently fight for space rather than
  sitting in fixed regions of a grid, the status has to be scrolled to, the
  map has no way to hide itself, and the prompt behaves like a scrolling
  terminal instead of a fixed-size window that reveals new text each tick and
  labels what's location, what's description, and what's happening. This is a
  real redesign of the game client's layout, not a single change.
- **Mapping a validation error back to the step that causes it.** A raw
  message like `player.entity: Field required` names a model field, not a
  wizard step — an author has no way to tell that means "answer 'Who does the
  player play?'" without knowing the schema. Would need the problem list to
  carry (or look up) the step id a field belongs to, so the wizard could both
  say the human question and highlight its control.
- **Submaps for a single location — RESOLVED (2026-09-11).** `Location.submapOf`
  (a plain `LocationRef`, nothing else new in the content model) names the hub
  a room is inside. It never gets a pin of its own on the world map — engine,
  travel, and encounters are all completely unaffected, because exits, scenes,
  entities, and route resolution never cared whether a location had a map pin
  in the first place. This was purely a *projection* change: `mace.session.view`
  gained a second, small `Atlas` (`View.submap`) built by excluding
  `submapOf` locations from the world atlas and including them in their hub's
  instead, reusing `_place`/`_road`/`_underway` unchanged; the web client
  draws it with the same `MapView` component the world map uses. Full detail
  in [Travel & Encounters § "A hub's own small map"](06-travel-and-encounters.md#a-hubs-own-small-map).
  Wizard authoring is in scope too, not deferred: `location.submapOf` is an
  ordinary `Select`/`Query` wizard step (the same shape `entity.extends`
  already was), and the map editor's canvas gained a drill-down — a badge on
  a hub, a scoped small canvas, a way back — described in
  [Authoring & the Wizard § "The map editor"](09-authoring-and-wizard.md#the-map-editor).
  One level of nesting is what's built and tested; a room inside a room inside
  a room is undesigned, not guarded against.
- **Elevation on the map and in travel — RESOLVED (2026-09-11).** Turned out
  smaller than it looked. Rain
  converting to snow at altitude was **already built**: `WeatherCondition.freezes_to`
  plus `_settle()`'s per-region freezing-point check (`src/mace/engine/world/weather.py`)
  means two neighboring regions at different elevations, hit by the same
  front, already settle independently to rain and snow — no code needed,
  just a climate/elevation combination that pushes one region below
  freezing (`fantasy.core`'s `rain`/`light-snow` pair already demonstrates
  it). What was actually missing has been built: a route now costs
  `1.0 + max(0, gain) / 1000` extra for the elevation it climbs
  (`_climb_cost` in `src/mace/engine/step.py`, whole-route granularity —
  see [Travel & Encounters](06-travel-and-encounters.md#terrain-and-elevation-multiply-on-top)),
  and the map now tints and labels each region's blob by elevation
  (`Place.elevation` in `src/mace/session/view.py`, drawn in `web/src/map/Map.tsx`
  the same way weather already is — unconditionally, since elevation isn't a
  spoiler the way a price is). `elevation` stays on `Region`, not `Location`;
  nothing so far has needed finer granularity than that.
- **Switching equipped weapon or tool, mid-scene or mid-combat.** Equipment
  is set once at entity-definition load (`src/mace/engine/step.py`, populating
  `state.equipment` from the definition) and read when a combat roster is
  built (`src/mace/engine/combat/roster.py`); there's no runtime `equip`
  effect and no `EffectPayload` for it in `src/mace/model/effects.py`. Wanted
  for two different reasons that may want two different mechanisms: a tool
  swap outside combat (need an axe equipped to fell a tree — a condition plus
  maybe a use-effect, not really "combat gear") versus swapping weapons
  *during* a fight (bow to shortsword when the enemy closes — this one
  probably costs an exchange the same way the existing `focus` ally-order
  does, so it can't be a free action that trivializes the range question
  below).
- **Range in combat.** There is no range concept anywhere in combat today —
  `Move` (`src/mace/model/combat.py`) has no melee/ranged/optimal-range
  field, `ItemProps`' `damage` (`src/mace/model/entity.py`) has no range
  field either, and `docs/07-combat.md` doesn't mention distance. Proposed:
  weapons tagged ranged or melee, each with an optimal-range band and
  accuracy falling off (the author's suggestion was exponentially) outside
  it; a melee weapon simply can't connect outside its band at all; combatants
  have a distance between them that a "close the distance" / "back off"
  option changes during an exchange, at a rate scaled by a stat (`speed` or
  `dexterity` already exist and are the obvious candidates). This is the
  largest of the four items here — it touches the move model, the exchange
  resolver, and the tactical/reflex front-end input, not just one file — and
  probably deserves its own [decision record](decisions/) rather than being
  settled in this list, given how central [ADR-0006](decisions/0006-tempo-combat.md)'s
  tempo model already is to combat's shape.
