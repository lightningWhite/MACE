# 14. How-Tos

The other docs describe what the engine can do; this one is the missing
middle step — given a scene you want to build, which fields do you actually
touch, and do you touch them in the wizard or in a YAML file? Each recipe
below says so explicitly, because the honest answer today is sometimes "the
wizard doesn't build this part yet." Docs/09 § "The condition and effect
builders" is why every condition and effect *is* covered; climates, weather
fronts, pressure events, and a few others still aren't (`mace.wizard.flows`
says so at `flow_for`, and the task list says so on screen), and stay
hand-written YAML for now.

If you haven't yet, read "How the pieces fit together" below first — the
recipes assume you know what a scene, a choice, and an effect are.

## How the pieces fit together

A game is a graph of **scenes**. A scene says some things (`say`), maybe
changes something (`effects`), and then either jumps straight to another
scene (`goto`) or offers the player a menu (`choices`) — never both, because
those are two answers to the same question: *what happens next?*

A **choice** is the same question asked one level down: it can jump to a
scene (`goto`), do something without going anywhere (`effects`), or both at
once. That last combination is what makes a scene reusable as a *hub* — see
the conversation recipe below.

Locations, entities, and routes all point *into* this graph rather than
containing it: a location's `scenes` list is "what's on offer when you're
here," not a scene of its own. So building a game is mostly:

1. Make the places (locations, routes between them).
2. Make the things and people in those places (entities).
3. Write the scenes those things offer, wiring `goto`/`choices`/`effects`
   until the graph reaches everywhere it should. The **Scenes** section's
   graph view tells you what's unreachable — check it as you go, not just at
   the end.
4. Come back and fill in quests, encounters, and economy once the shape of
   the game exists — they hang decisions and consequences off a graph that
   already has somewhere to attach them. Building them first, before there
   is a game to attach them to, is usually wasted work.

It's fine to leave a scene half-written and come back later. Nothing in the
wizard blocks you from saving with gaps; the task list's ○/◐/✓ marks and the
problem list are how you find your way back to them.

## Recipes

### A conversation with more than one thing to ask about

**Wizard only.**

The naive way costs one scene per question: a hub scene with a choice per
question, each choice's `goto` pointing at a whole separate scene that just
holds one line of dialogue and then dead-ends. It works, but five questions
is five throwaway scenes.

Instead, give each choice a `say` effect and a `goto` back to the *same* hub
scene:

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

In the wizard: open the scene, add a choice, and under "Or does it just do
something?" pick **Say something** — that's the `say` effect — then set
"Which scene does it lead to?" back to the hub scene itself. Repeat per
question; "Leave" is the one choice that goes somewhere else.

### Someone shows up because the player did something

**Wizard only.**

There's no special "noise" mechanism — this is just a scene effect, the same
as any other. Give the player a choice (or a fixture's scene) whose effect is
`spawnEntity`:

```yaml
choices:
  - prompt: "Shout for help"
    effects:
      - {spawnEntity: {entity: passing-guard}}
```

Leaving `at` unset means "wherever the player is," which is what "shows up"
usually means. `transient: true` (the default) means the guard goes away once
the player leaves; set it `false` for someone who should stick around.

In the wizard: this is **Put somebody, or something, here**, on any scene or
choice — under a choice's "Or does it just do something?", or a scene's own
"What does it change?"

### Gate a choice on the weather or the season

**Wizard only.**

A choice (or a whole scene) can require the world to be in some state before
it's offered:

```yaml
choices:
  - prompt: "Cross the frozen lake"
    when: [{season: [winter]}, {weather: [clear, overcast]}]
    goto: cross-the-lake
```

Conditions in a list are ANDed, so this needs winter *and* no storm. In the
wizard: on the choice's "When can they take it?" step, add both conditions
from **The weather** and **The season**. Turn on "Show it greyed out when
they cannot?" if the player should see the option exists before they've
earned it — usually better than hiding it outright.

### Close a road when a world event fires

**Mixed — the trigger is hand-written, your reaction to it isn't.**

`closeRoute` is an ordinary effect, buildable from any scene or choice the
same way as `spawnEntity` above. What's *not* wizard-built yet is the thing
that decides *when* to fire it on its own, with no player action involved: a
**weather front** or a **pressure event** (docs/05 § "Layer 3 — Fronts" and
§ "Pressure events — the volcano that might go"). Those two collections —
plus climates and terrains — are still written directly into a pack's YAML;
the wizard's task list says as much on its own "Weather & climate" section.

So there are two honest ways to get "the pass closes on its own":

- **If a library already defines the front or event you want** (check what
  your pack depends on), reference it from wherever you're already working —
  a pressure event's own `imminent.effects` is exactly where `closeRoute`
  goes, and that part is just YAML you write once:

  ```yaml
  # in a pressureEvents entry, hand-written
  imminent:
    effects:
      - {closeRoute: {route: mountain-pass, reason: "The pass is shaking itself apart."}}
  ```

- **If you want the player's own actions to close it** — no world event
  needed — put `closeRoute` on a scene effect the same as any other, gated
  by whatever condition you like (a flag, a quest stage, the weather). This
  part *is* fully wizard-built today.

`openRoute` is the same effect vocabulary in reverse, for reopening it later.

### Revealing the map as the player explores, instead of showing it all at once

**Fully wizard-built today** — this isn't a missing feature, it's a content
choice most first drafts skip because every location defaults to visible.

A location starts known to the player if its `visible` field is true (the
default) — or, if `discovered` is set, whatever that says instead (see
`Location.starts_discovered`). Set `visible: false` on any location you don't
want on the map or in travel menus at the start of the game:

```yaml
# in locations.yml
- id: dark-mountain
  name: "The Dark Mountain"
  visible: false
  ...
```

Then put a `reveal` effect wherever the discovery should happen — a scene
`say` beat, a choice, a quest stage, a pressure event's `aftermath`, anywhere
an effect list is accepted:

```yaml
effects:
  - {giveItem: {actor: player, item: kings-token, qty: 1}}
  - {reveal: {location: dark-mountain}}
```

`packs/games/peasants-quest`'s `report-to-orin` scene does exactly this: the
captain hands over a token *and* the mountain appears on the map in the same
effect list. `reveal` can appear more than once in the same list to unlock
several places at once — "you find a map and a chest that marks three ruins"
is just three `reveal` effects.

The atlas the front-end draws from tracks three states per location, not two:
*here* (current), *visited* (been there), and *known* (revealed but never
visited) — so a revealed-but-unvisited ruin can be drawn differently from one
the player has actually walked into, without any extra authoring.

### Make a stat do something

**Fully wizard-built today**, in the sense that nothing here needs new
machinery — the gap is knowing which three tools to reach for. Declaring a
stat (`stats: {stealth: {base: 18}}`) does nothing by itself. `strength`,
`speed`, and `charisma` are the only names the engine reads on its own
(docs/03 § Stats); every other name — `stealth` included — only ever matters
because content says so, through exactly one of three mechanisms:

- **A condition gates something on it.** `{statAtLeast: {stat: stealth,
  value: 50}}` on a choice's `when` — the option to slip past the guard only
  appears once the stat clears the bar.
- **An effect changes it.** `{adjustStat: {stat: stealth, delta: -10}}` after
  a botched attempt, or `{setStat: ...}` to pin it outright.
- **Weather reacts to it**, the same `env`/`modify` mechanism any other stat
  uses — `{when: {weatherTag: [dark]}, modify: [{stat: stealth, add: 20}]}`
  on the entity, if darkness should help.

A minimal worked example — a guard who can be slipped past if the player is
stealthy enough, and who gets harder to fool once already noticed:

```yaml
- id: slip-past-the-guard
  prompt: "Slip past while he's distracted"
  when: [{statAtLeast: {actor: player, stat: stealth, value: 50}}]
  effects:
    - {move: {to: courtyard}}

- id: caught-trying
  prompt: "Try anyway"
  effects:
    - {adjustStat: {stat: stealth, delta: -10, reason: "he's watching for it now"}}
  say: "He clocks the movement. Twice as sharp-eyed the next time."
```

If a pack never writes any of those three around a stat, that stat is inert
— present on the sheet, changed by nothing, read by nothing. That's not a
bug to route around; it's the whole reason a sci-fi pack can invent
`hull-integrity` next to a fantasy pack's `hitpoints` and neither engine nor
author has to reconcile the two.

### Grow a stat's cap

**Fully wizard-built today.** `growth` (on the stat itself) already raises a
stat's *current* value toward its *existing* ceiling through combat use —
what makes a well-worn strength stat sharper without becoming a different
number outright. Raising the ceiling itself is a separate effect,
`raiseMax`, for real progression: more fights, more travel, a season of
chopping wood — whatever a game wants to reward:

```yaml
effects:
  - {raiseMax: {actor: player, stat: stamina, amount: 5}}
```

The engine doesn't know or reward any particular activity — it only knows
how to raise a cap when told to. The simplest way to reward something
repeated is a small `raiseMax` every time, so the cap creeps up as a side
effect of play rather than a level-up screen:

```yaml
- id: fell-a-tree
  prompt: "Fell a tree"
  effects:
    - {raiseMax: {actor: player, stat: stamina, amount: 0.5}}
  say: "The axe bites clean. Your arms ache in a way that feels earned."
```

Forty trees in, that's twenty more stamina capacity than the player started
with, with no counter to maintain. A distinct milestone instead of a steady
creep — "the fortieth troll, specifically, toughens you" — is an ordinary
`when`-gated choice built the way [Travel & Encounters](06-travel-and-encounters.md)
already gates anything else on a tally kept in `vars`: increment a variable
with `setVar`, and offer a second choice whose `when` only clears once that
tally reaches the threshold, with `raiseMax` in *that* choice's own effects.

Either way, the player's current stamina doesn't move — only the cap does,
reported by a `stat.max-raised` event a front-end can turn into "Your
stamina capacity has grown!" the same way `stat.changed` becomes an
ordinary heal or hit.

## A complete example

`packs/games/peasants-quest` is a real, playable, fully wizard-editable game —
not a fragment. Open it in the wizard itself to see these patterns (and the
ones the wizard doesn't reach yet) in a finished pack, rather than reading
them in isolation:

```bash
mace author packs/games/peasants-quest --web --client web/dist
# then open http://127.0.0.1:8000/#author
```

(There's no in-app way yet to pick a game to open without the command line —
that's a separate, smaller piece of work than this doc.)
