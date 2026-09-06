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
