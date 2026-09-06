# 1. Vision & Principles

## The one-sentence version

MACE lets anyone build a living, text-driven adventure world by answering
questions instead of writing code — and lets anyone else play it, in a terminal
or a browser, where the weather moves, the roads are dangerous, and combat is
won by skill rather than dice.

## What it is not

- **Not a fantasy engine.** Fantasy is the first content library, not the engine.
  Nothing in the core mentions swords, magic, or orcs. A cyberpunk sprawl, a
  generation ship, a Dust-Bowl noir, and a Tolkien-shaped quest are all the same
  data structures with different packs.
- **Not a parser game.** No "GO NORTH / TAKE LAMP" guessing. Choices are
  presented; the interest comes from world simulation and consequence, not from
  guessing the verb.
- **Not a static gamebook.** The same game played twice should not play the same
  way. A branching story with fixed branches is not the goal.
- **Not a general programming environment.** Authors get a rich, declarative
  vocabulary. If a game needs real code, that's a signal the vocabulary is
  missing something — extend it rather than adding a scripting escape hatch.

## The four things that make it worth building

Everything in these docs serves one of these. If a feature doesn't, it's scope
creep.

### 1. The world is alive and different every time

A journey from the trader's post to the castle is not a menu transition. It takes
three days. A storm front rolls in off the northern range on day two, so you
arrive soaked, slow, and half a day late — and the ogre that would have ambushed
you in clear weather stayed in its cave. Next playthrough, none of that happens
and a merchant caravan offers you a ride instead.

Above the weather sit **events**. Some are on the calendar — an eclipse the
priests have been counting down to, a comet that comes once a century — and can
be looked up in an almanac, so they become deadlines to plan around. Others are
building without a schedule: the volcano whose pressure has been rising all
game, the hillside above the pass that the rain is working loose. You can't know
when those will go. You can only read the omens — the grey cast on the snow, the
tremor you could almost doubt, the birds leaving the range all at once — and
decide how many more times you dare take the pass.

This is achieved with a real (if small) simulation — a clock, a climate model,
weather fronts that propagate across regions, events that accumulate pressure and
telegraph it honestly, and probabilistic encounters keyed to place, time,
weather, and story state. See [World Simulation](05-world-simulation.md) and
[Travel & Encounters](06-travel-and-encounters.md).

### 2. Skill matters in combat

Combat is not "roll d20, add strength." It's a reading-and-timing game: enemies
telegraph moves, you learn their patterns, you counter in the right window, you
chain reads into momentum. Your character's stats set the *size of the windows
and the damage bounds*; you decide what happens inside them.

The test: **a player who has fought three trolls should beat the fourth one more
reliably than a player who hasn't, with an identical character sheet.** If that
isn't true, the combat system has failed. See [Combat](07-combat.md).

### 3. Authoring is answering questions

The wizard is the product, not a convenience wrapper. Someone with a good idea
for a world and no programming background should be able to build it. That means:
every reference the author types is picked from a list of things that exist;
every mistake is caught the moment it's made; and the author can always play what
they've built so far, right now, from any point.

### 4. Nothing gets built twice

A troll built for one game should be usable in every other game. Libraries of
entities, items, biomes, weather conditions, and encounter tables are first-class,
versioned, namespaced, and extendable — you import `fantasy.core:troll` and
override the two fields you want different. See
[Content Library & Community](11-library-and-community.md).

## Design principles

These are the tie-breakers.

**Data over code.** If an author might plausibly want it different, it belongs in
content, not in the engine.

**Deterministic by construction.** A seed plus an action log fully reproduces a
playthrough. This is not just for debugging — it's what makes save files small,
bug reports actionable, replays shareable, cheating detectable, and multiplayer
possible later. See [ADR-0004](decisions/0004-deterministic-seeded-simulation.md).

**One engine, many faces.** The terminal, the browser, and a future server all
run the same simulation and differ only in how they render events and collect
input. No feature may exist in one front-end that the engine doesn't expose to
all of them.

**Simulation in service of story.** The weather model exists to make arriving
somewhere feel like a journey, not because meteorology is interesting. When
realism and fun conflict, fun wins — but the fun should come from the world
behaving consistently, which is why the model needs to be real enough to be
predictable.

**Fail loudly at author time, gracefully at play time.** A dangling reference
should be a hard validation error when the author saves. It should never crash
somebody's game three hours in.

**Small pieces, committed often.** This project stalled once by being designed in
the abstract. Every phase in the [roadmap](12-roadmap.md) ends in something
playable.

## The long game

A GitHub repo full of worlds people made, that anyone can clone and play. Then a
hosted site where you can play them in a browser with no install. Then, much
later, shared worlds — several players' quests crossing paths on one map. The
architecture in these docs is chosen so that last step is a new front-end and a
server, not a rewrite.
