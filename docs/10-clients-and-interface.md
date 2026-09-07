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
- A global "time pressure" multiplier for players who want reflex mode but slower.
- Full keyboard navigation; the terminal client is inherently screen-reader
  friendly and the web client must be too — combat tells are announced in an ARIA
  live region.
- Never encode information in color alone: weather, danger, and map states carry
  a shape or label as well.
- Respect `prefers-reduced-motion`; the timing bar degrades to a numeric countdown.
