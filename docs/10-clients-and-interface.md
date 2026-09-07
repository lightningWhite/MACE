# 9. Clients & Interface

Every front-end is a renderer for the same event stream. Nothing below is a
feature of "the web version" — it's a presentation of engine data that the CLI
also has access to.

## The player interface

The target layout for the web client. Four regions, all driven by events:

```
┌──────────────────────────────────────────┬───────────────────────────────┐
│                                          │  ▣ MAP                        │
│  The troll unfolds itself from beneath   │        ○ Dark Mtn             │
│  the bridge, and the bridge seems glad   │        │                      │
│  to be rid of the weight.                │   ●────┼──── ○ Hagan's Castle │
│                                          │  Fenmoor│                     │
│  "Toll," it says. "Ten gold, or swim."   │        ◌ Troll Bridge         │
│                                          │  ● here ◍ visited ○ known     │
│  ▸ Pay the toll (10 gold)                ├───────────────────────────────┤
│  ▸ Try to talk it down                   │  ▣ LETHOLIN                   │
│  ▸ Draw your sword                       │  ♥ 38/50   ⚡ 26/40           │
│  ▸ Back away slowly                      │  STR 32  SPD 41  WIS 12       │
│                                          ├───────────────────────────────┤
│                                          │  ▣ PACK   ▣ JOURNAL           │
│                                          │  gold ×15    ▸ The King's     │
│                                          │  dagger        Summons        │
│                                          │  bread ×2      day 3 of 7     │
├──────────────────────────────────────────┴───────────────────────────────┤
│  Day 3 · dusk · Troll Bridge · light rain, easing · 4 days remain        │
└──────────────────────────────────────────────────────────────────────────┘
```

The status bar is the simulation made visible, and it should never be absent.
It's what tells the player the world is running whether they act or not.

### The map

The single highest-value graphical element, and the reason a web client is worth
building at all.

- Nodes are locations, edges are routes. Edge length reflects `ticks`, so
  distance is legible at a glance.
- Fog of war: unknown / heard-of / visited / current, each visually distinct —
  and distinct by *shape*, not only by color. Discovery is a reward, and the
  scale runs from hollow to solid as the player learns a place: `○` heard of,
  `◍` been there, `●` here.
- Routes show what the player has learned about them — a road they've been
  ambushed on twice should look like it.
- Weather overlay per region, so an approaching front is something you can *see*
  and plan around.
- Click a known location to travel; the route preview shows estimated ticks under
  current weather and the waypoints you'd pass.
- Layout from authored `mapPosition` when present, force-directed otherwise, so
  authors get a decent map for free and a beautiful one if they care.

Click-to-travel works because the projection says so. `Place.choice` is the
index of the option currently on offer that goes there — only the engine knows
that "Take the north road" is the one that walks to Hagan's Castle, and a
client that matched prompts to place names by their wording would be guessing
at content and would break on the first author who wrote "Head north". An
option the player cannot afford is not a way out: it stays on the menu, where
the author's hint says why, and the map does not pretend the place is
reachable.

In the force layout a road's rest length is proportional to its `ticks`, which
is where "edge length reflects `ticks`" is literally true — a six-tick road
settles about three times as long as a two-tick one. The layout is seeded from
the place ids rather than `Math.random`, so a world lays out the same way
every time it is opened; a map that rearranged itself on reload would be
unreadable in a different way each time.

What is not done yet: the route preview, and roads showing what the player has
learned about them. Both want the projection to carry more than it does.

### Combat view

Takes over the narrative pane during a fight. From
[Combat](07-combat.md), what needs rendering:

- The **tell**, prominently, in words — this is a text game and the tell is prose.
- A **timing bar** that drains over `windowMs`, with the sweet zone marked.
- Defense choices as keys/buttons, with the counter matrix visible until the
  player turns the training wheels off.
- Stamina and momentum, always visible, since they're the resources being managed.
- Per-exchange feedback that names *why*: "Clean parry — you read the thrust."
  Attribution is what turns outcomes into learning.

In `tactical` mode the timing bar is absent and everything else is identical.

Two things the web client had to get right, and they are the same thing twice.
The bar marks the spot the engine actually rewards: `precision_of` puts the
sweet spot three quarters of the way through the window and falls off linearly
half a window either side, so the bar marks three quarters and shades the band
worth answering in. A bar that marked somewhere else would be worse than no
bar. And **a window that runs out spends itself** — the browser sends
`recover` with the whole window gone, exactly as the terminal does on a wrong
key or no key, because a front-end whose window is kinder than the other's is
a different game with the same content.

The keys are the terminal's keys too, by the same rule (`keys_for`): first
free alphanumeric of the label, then a digit. A player who learns a fight in
one front-end and finishes it in the other should not have to learn them
twice, and `tests/test_web_wire.py` records the terminal's bindings so the
client's tests can prove the two agree — including the case nobody would
guess, where `Bread` walks past `b` and `r` to land on `e`.

Momentum is shown as the multiplier `combat.responses` carries, in words,
rather than as a bar: the wire states the value and not its ceiling, and a bar
would have to invent one.

### The CLI

Not a fallback — a real client, and the one that keeps the project honest, since
anything the terminal can render is provably engine data rather than UI logic.

- Same event stream, rendered as text with ANSI color.
- An ASCII map view on demand — `m` at the prompt. It draws the same atlas the
  web client will draw as SVG, plotted from `mapPosition` where an author set
  one and listed where they did not, so fog of war, route lengths and the
  weather overlay are all provably engine data before a browser is involved.
- Combat via single keypress against a monotonic deadline.
- The status line as a persistent bottom row.
- `mace author` — the whole wizard, rendering the same declarative steps the
  web client will. It is the proof that the flow graph is data: the terminal
  contains no questions.

## Technology

**Web client:** React + TypeScript, Vite, installable PWA (offline manifest +
service worker). No heavy game framework — this is a text UI with a graph view.
The map is SVG, which is cheap, accessible, themeable, and prints.

It lives in `web/` and holds no rules. Panels render `frame.view`, the
transcript renders `frame.events`, and `web/src/protocol.ts` is the only file
that knows the wire — a panel that wants something not on it gets a field on
`mace/session/view.py`, not a computation of its own. Its tests replay frames
recorded from a real playthrough, and `tests/test_web_wire.py` fails when the
engine stops sending what was recorded, so the client cannot keep passing
against a protocol that has moved.

**Where the engine runs:** the engine is Python and stays Python.

- **Phase 4** — FastAPI serves sessions over HTTP/WebSocket; the browser is a
  thin renderer. Simplest path to something playable in a browser.
- **Phase 5** — the same engine compiled to WASM via Pyodide, running entirely
  client-side. A static build deployable to GitHub Pages, playable offline, with
  no server to run or pay for. This matters a great deal for a hobby community
  project.
- **Later, if needed** — a TypeScript port of the engine, verified against the
  Python one by the golden replay tests. Only worth doing if Pyodide's download
  size proves to be a real barrier; the decision can wait for data.

See [ADR-0005](decisions/0005-python-core-with-pyodide.md).

### The offline shell

The client is installable: a manifest, an icon, and a service worker written
by hand rather than generated, because what it has to do is small and a
build-time precache manifest is a dependency and a moving part between a
player and a page that loads. It caches what the page asks for as the page
asks for it, so the first online visit fills the cache and a later visit
without a network gets the shell back out of it.

The API is deliberately never cached. A stale frame is a stale world: it would
show a player a menu the session has already moved past, and they would click
it and be told no.

So what an installed client can do with no network is load, say exactly that,
and point at the save — which is local, and is the whole playthrough. That is
the honest shape of it until the engine moves into the tab
([ADR-0005](decisions/0005-python-core-with-pyodide.md)), at which point there
is no server to be offline from.

### The session service

`mace serve packs/` runs it. It is a front-end like the terminal is a
front-end: it drives a `mace.session.Session`, hands out the ordered event
stream and the view-model, and holds no rules, no balance and no prose of its
own. A bug that shows up here is a bug in the engine, or it is a bug in the
JSON.

| | |
|---|---|
| `GET /api/games` | What there is to play |
| `GET /api/games/{pack}/creation` | The character-creation question, or `asksAnything: false` |
| `POST /api/sessions` | Open one. `{pack, seed, combatMode, character}`, or `{save}` to carry one on |
| `GET /api/sessions/{id}` | Where it stands, and what it last said |
| `POST /api/sessions/{id}/actions` | Do one thing |
| `GET /api/sessions/{id}/save` | The save record |
| `DELETE /api/sessions/{id}` | Stop holding it open |
| `WS /api/sessions/{id}/stream` | The same exchange, held open |

Every reply is one **frame** — `{session, playing, events, choices, view}` —
so a client has one renderer rather than one per endpoint. `events` is what
happened, `view` is what stands, and `choices` is what may be done next, named
the way a save names it. A reconnecting client is handed the last step's
events again rather than being told to work out what it missed.

The socket carries exactly the same frames, and exists because combat has a
clock in it: a `combat.tell` opens a window measured in milliseconds, and
spending a chunk of it on connection setup would make the fight unfair in a
way the player would feel and could not name. An action the engine refuses
comes back as an error frame and the connection stays open — a mistyped action
is not a reason to reconnect mid-fight.

**Sessions live in one process and die with it**, and the client's save is the
only durability. That is [ADR-0009](decisions/0009-the-save-is-the-durability.md),
and it is why the 404 for a missing session tells the client to post the save
it was given. There is no authentication: a session id is a bearer token, so
`mace serve` binds to localhost by default.

## Saves

A save is `(pack ids + versions, seed, character, action log)`, and one day a
periodic snapshot beside it. Tiny, diffable, shareable. Sharing a save shares an
exact playthrough, which makes bug reports trivially reproducible and makes
"watch how I beat the troll" a thing that works — a save is a golden recording
missing only its expected events.

If content changes under a save (an author updates the pack), the loader compares
versions and warns before it replays anything. Replaying an action log against
changed content may then diverge. **Today a divergence stops the load**, naming
the action it stopped at and the menu that was on offer instead. The snapshot
that would let the session continue anyway, with the divergence flagged, is the
half of this that is designed and not yet built.

A log meant to survive that should record its choices by **prompt** rather than
by index — see [Architecture § Determinism](02-architecture.md#determinism-and-randomness).
An index quietly points at a different option once the menu changes; a prompt
either finds what it meant or says what it could not find.

## Accessibility

Not an afterthought, because the reflex layer in combat is exactly the kind of
thing that excludes people by default.

- `tactical` combat mode removes all time pressure with no loss of depth.
- A global "time pressure" multiplier for players who want reflex mode but
  slower. `--time-pressure` on the CLI, `timePressure` when a session opens,
  and a row of choices on the web client's opening screen. It divides into the
  same `ease` that familiarity multiplies, so "give me more time" and "I have
  fought trolls before" widen the same door rather than two.

  It is a **session** setting, kept in the save beside the seed, for the same
  reason `combatMode` is: a recorded `elapsedMs` only means anything against
  the window it was answered inside, so it cannot move mid-playthrough. And it
  scales the window and nothing else — precision is still measured against the
  window the player was actually given, so a slower clock is a longer door and
  not an easier one to aim at.
- Full keyboard navigation; the terminal client is inherently screen-reader
  friendly and the web client must be too — combat tells are announced in an ARIA
  live region, and the fight's answers are bound to the same keys the terminal
  binds. After a turn the web client moves focus to the next thing to press:
  the button the player just used is gone by then, and without it a keyboard
  player would tab back in from the top of the page every single turn.
- Never encode information in color alone: weather, danger, and map states carry
  a shape or label as well. On the map, the three fog states are three shapes,
  a closed road is dashed *and* says "shut", and each region's sky is named.
- Respect `prefers-reduced-motion`; the timing bar degrades to a numeric countdown.
