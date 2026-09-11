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
- **Should a monster's pools have to match the player's? — RESOLVED
  (2026-09-11).** **Decided: no — `StatAllocator` stays free-form.** Surfaced
  by an author (2026-09-07) trying to build a statblock and wondering whether
  a monster's pools should instead be a closed list matching the player's
  own, so `hitpoints` always means the same axis on both sides of a fight.
  Genre neutrality wins: forcing a sci-fi drone to have `hitpoints` instead
  of `hull-integrity` would bake in a fantasy-RPG assumption, the same
  reasoning that keeps magic in content rather than the engine (see #5
  above). A monster naming a different axis than the player's own is
  accepted as intentional — nothing to fix. Distinct from the separate,
  already-resolved question of pool *magnitude* ("Damage and hitpoints as
  absolute numbers", below) — this one was always about pool *identity*,
  and stays free-form.
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
- **Editing an existing repeat entry — RESOLVED (2026-09-07).** An exit, a
  stage, an inventory stack — anything added through a `Repeat` field — used
  to be add-or-remove only, never reopened once it existed, because the
  entry's own little form only ever composed a *new* entry locally and
  nothing handed back the English rendering of an already-authored
  condition/effect the way a fresh `POST /build` does. Both closed, in the
  same pass that wired up encounter tables and narrowed quest-stage pickers:
  `Studio._entry_pieces` (`src/mace/wizard/studio.py`) now returns that
  English rendering, keyed the way the client's own local form state is, so
  reopening an entry seeds `PiecesEditor` correctly instead of showing an
  existing condition as if it had never been there. The CLI's `_repeat()`
  (`src/mace/cli/author.py`) gained `[e] edit` alongside `[a] add`/`[r]
  remove`; the web client's `EntryForm` (`web/src/author/Field.tsx`) opens
  seeded with the entry being edited and replaces it in place rather than
  appending a new one. Covered by `test_a_repeat_entry_can_be_edited_not_only_removed`
  (`tests/test_cli_author.py`) and the `"editing an existing entry"` suite in
  `web/src/author/Field.test.tsx`.
- **An author-facing reachability view for locations, not just scenes.** The
  scene graph answers "is there any way in?" for scenes; there is nothing
  equivalent for the world map — no single screen answering "from here, where
  can you actually get to, and is anywhere unreachable?" for locations and
  their exits.
- **A full-screen, non-scrolling layout for play — RESOLVED, with one gap
  (2026-09-10).** Raised by an author (2026-09-07): on a large screen the
  map, status (hitpoints, stamina, day, location, weather), and prompt fought
  for space rather than sitting in fixed regions of a grid, the status had to
  be scrolled to, the map had no way to hide itself, and the prompt behaved
  like a scrolling terminal instead of a fixed-size window that reveals new
  text each tick. `web/src/App.tsx` now lays the play view out as four fixed,
  independently resizable quadrants (map, action/status, story, and a
  stats/pack/journal sidebar) sharing one column split and one row split
  (`useSplitGrid.ts`) rather than one scrolling page — `StatusLine` sits
  inside the action quadrant, always in view rather than scrolled to, and the
  story panel got the memory/current-tick split this same pass asked for: a
  collapsible "memory" of everything so far, and a `current-tick` region
  (`role="log"`) that is always what just happened. **Not fully closed**: the
  map quadrant can be resized down but not actually hidden — `useSplitGrid`'s
  `MIN_PERCENT` floors every pane at 20% width, so "a way to hide the map"
  specifically remains unbuilt.
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
- **Damage and hitpoints as absolute numbers, not portable across games with
  different scales — RESOLVED (2026-09-11).** `Damage.min`/`max` and
  `Stat.base`/`max` (`src/mace/model/entity.py`) now accept either a
  literal number or `{relativeToPlayer: {stat, factor}}` — a new
  `RelativeStat`/`RelativeValue` type, coerced the same way `AuthoredValue`
  coerces `{expr: "..."}`, but as a dedicated structured type rather than a
  reuse of the expression evaluator (a raw expression would have been
  wizard-invisible, the same gap `AdjustStat.delta` already has — see
  `docs/09-authoring-and-wizard.md`).
  - Resolved against the player's stat *cap*, not their fluctuating current
    value. A `Damage` bound resolves fresh on every roll
    (`mace.engine.stats.resolve_relative`, called from
    `mace.engine.combat.fight._incoming`/`_opening`); a `Stat.base`/`max`
    resolves once, at instantiation (`EntityState.pools` /
    `EntityState.resolved_stats`), so a monster does not quietly rescale
    mid-playthrough if the player's own stats change afterward — the same
    answer this bullet's "current vs. authored baseline" question was
    asking.
  - A `customizable` stat cannot be relative to the player (self-referential
    — it *is* the player's own stat).
  - Fully wizard-native, in both the CLI and the browser: a stat's
    base/cap gets a fixed-or-relative toggle inside its `StatAllocator`
    entry; a damage bound gets its own field type,
    `mace.wizard.fields.RelativeNumber` (`3xhitpoints` in the CLI, a
    factor + a picker of the player's own stat names in the browser).
  - This closed a second, larger gap along the way: nothing in the wizard
    touched `moves`, `combatProfiles`, or any `ItemProps` field before this
    (independent of relative values — a pre-existing hole). New `MOVE`/
    `COMBAT_PROFILE` flows and the `entity.item.*`/`entity.combat.moves`
    steps close it, using a new `Step.visible_when` mechanism (resolved
    server-side, sent to the browser as a plain boolean) so an item-only
    field never shows — or gets answered — on an actor, and a move's
    `tell` only shows for an attack.
  - Left for later: `entity.equipment`/`entity.skills` (a
    `Mapping[str, ref]` shape with no existing wizard field-type precedent
    besides `StatAllocator`'s bespoke one); `Pattern.sequence` scoped to
    the owning profile's own `moves` rather than the whole collection
    (the model doesn't enforce that subset relationship either).
- **The play map has no pan or zoom — RESOLVED (2026-09-11).** It was exactly
  the small, low-risk lift this bullet predicted: `useSvgPanZoom` — moved
  from `web/src/author/panzoom.ts` to the shared `web/src/panzoom.ts`, since
  it now has a caller outside `author/` — is layered onto `web/src/map/Map.tsx`
  the same way `MapEditor.tsx` and `SceneGraph.tsx` already used it. Nothing
  about fog-of-war or click-to-travel changed; only how the `viewBox` is
  computed and touched, plus a "reset view" link that appears once the
  reader has moved away from the fitted view. Applies to both the world map
  and a hub's own small map (`heading="Close by"` in `App.tsx`) — each
  `MapView` instance gets independent pan/zoom state, since the hook is
  called once per component instance. (The related ask — "and scenes too" —
  still doesn't correspond to anything on the player's side: `SceneGraph.tsx`
  is an author-only tool for visualizing the branching structure while
  building a game; nothing shows a player a graph of scenes, nor should it —
  they read prose and choices, not a diagram of the story.)
- **Stats that mean something — RESOLVED (2026-09-11).** Raised by the user
  wondering whether `strength`/`speed`/etc. do anything besides look nice on
  a sheet, and whether growth beyond the current fight was possible. Four
  things landed together:
  - **The authoring trap is closed.** An entity that never declared
    `strength`/`speed` used to read as `0.0` to combat — not neutral, a real
    penalty (`power() = 1.0 + (0-50)/100 = 0.5`, half damage, for a stat
    nobody knew was special). `Fighter.stat()`
    (`src/mace/engine/combat/roster.py`) now falls back to `NEUTRAL_STAT`
    for exactly those two undeclared names. Belt-and-suspenders: the wizard
    now pre-seeds every new character with all four starter stats
    (`Studio.create`, `src/mace/wizard/studio.py`) the moment it exists, so
    an author sees them rather than discovering the trap. `hitpoints`/
    `stamina` there are resolved dynamically against this project's own
    `game.rules.vitalPool`/`effortPool` (`Studio._pool_names`) rather than
    hard-coded, the same way the engine itself treats those two names as
    configurable — a sci-fi pack that renamed its vital pool to
    `hull-integrity` gets *that* pre-seeded, not an orphan `hitpoints`. The
    statblock editor marks all five names the engine ever reads (those two
    plus `strength`/`speed`/`charisma`) with a "core" badge and an
    explanation (`Studio._core_stats`, `web/src/author/Field.tsx`), so an
    author can tell "the engine reads this by name" from an ordinary
    free-form stat at a glance.
  - **Documented where an author would actually find it.**
    `docs/03-content-model.md`'s Stats section now names all three
    engine-wired stats (`strength`, `speed`, and `charisma` — haggling odds,
    `src/mace/engine/economy/haggle.py`, found while answering this) and
    points at the real formulas; `docs/14-how-tos.md` gained "Make a stat do
    something," the three real mechanisms (a `statAtLeast` condition, an
    `adjustStat`/`applyModifier` effect, an `env`/`modify` response) with a
    worked example.
  - **Growth beyond the current fight is real now.** `growth` only ever
    raised a stat's *current* value toward its *existing* ceiling; nothing
    could raise the ceiling itself. `EntityState.stat_caps` (session state,
    never written into content) plus a new `raiseMax` effect
    (`src/mace/model/effects.py`, handled in `src/mace/engine/effects.py`)
    do that generically — content decides what earns it (more fights, more
    travel, chopping wood twenty times), the engine only knows how to raise
    a cap when told to. `docs/14-how-tos.md` § "Grow a stat's cap" has the
    pattern.
  - **Enemy stats are shown, gated by the familiarity that already exists.**
    Asked the user directly, since flat exact numbers for every enemy would
    have cut against `docs/07-combat.md`'s whole "read the enemy" design
    (stats ~a third of outcome, skill the other two-thirds). Landed on
    reusing `familiarity_with()` (`src/mace/engine/combat/roster.py`,
    already there for widening timing windows and clearing tells): a
    stranger shows nothing new, a partly-known profile gets a qualitative
    read ("Hits hard.", "Quick."), a fully-known one gets exact numbers.
    Computed once at `CombatBegan` and rendered in `web/src/combat/Combat.tsx`.
