# 11. Roadmap

Ordering principle: **every phase ends in something you can play.** This project
stalled once by designing in the abstract; the antidote is that no phase is
allowed to be pure infrastructure.

---

## Phase 0 — Foundation *(done)*

Design settled and written down. This document set.

- [x] Audit the v0 prototype and templates
- [x] Design docs and decision records
- [x] Package skeleton `src/mace/`, `pyproject.toml` with real packaging
- [x] Move `src/games/` → `packs/games/`
- [x] `pytest`, `ruff`, `mypy` wired into pre-commit

---

## Phase 1 — The content pipeline *(done)*

**Playable at the end:** a linear, three-location game you can walk through in a
terminal, with scenes, choices, items, and win/lose.

- [x] Pydantic content models for pack, entity, location, route, scene, quest, game
- [x] JSON Schemas in `schemas/`, generated from the models
- [x] Pack loader: discovery, id resolution, `extends` inheritance, dependency order
- [x] Validator with error/warning/note severities and file+id reporting
- [x] `mace.engine.expr` — the safe expression parser and evaluator
- [x] Structured condition and effect evaluation
- [x] `GameState`, `Action`, `Event`, and the `step()` function
- [x] Seeded named RNG streams
- [x] Minimal CLI player: `mace play <pack>`
- [x] First golden replay test
- [x] Items carry `baseValue`; authored buy/sell scenes (`economy: simple`)
      *A **parameterised** shop scene needs the merchant block to exist, so it
      moves to phase 5 with the rest of the economy. What phase 1 gives is a
      price anchor on every item and trades written as ordinary structured
      effects — enough for a merchant to be worth talking to.*
- [x] `packs/games/peasants-quest` — four locations and a winnable road north

---

## Phase 2 — A world that moves *(done)*

**Playable at the end:** the same game, but journeys take days, storms roll
through, and the road between towns is dangerous.

- [x] Clock, calendar, day parts, seasons
- [x] Climate model: seasonal weights + Markov transitions
- [x] Regions, per-region weather chains, lazily fast-forwarded
- [x] Weather fronts propagating across the region graph, with omens
- [x] Weather effects: visibility, travel multiplier, stat modifiers, tags
- [x] Entity `env` responses
- [x] World events: celestial (scheduled), pressure (building, with omens), triggered
- [x] Event phases, aftermath world changes, and the news queue
- [x] Routes, waypoints, leg-by-leg travel resolution, interruption and resumption
- [x] Encounter tables: two-stage resolution, cooldowns, anti-clumping pressure
- [x] Exposure and rest — the mechanics that make weather bite
- [x] Conditional descriptions driven by weather and time
- [x] Status line in the CLI
- [x] `packs/fantasy.core` — first real library pack: weather, climates,
      fronts, terrains, an encounter table, and the scenes it plays

---

## Phase 3 — Combat *(current)*

**Playable at the end:** you can fight a troll in the terminal, lose, learn its
pattern, and win.

- [ ] Moves, counter matrix, combat profiles, patterns, feints
- [ ] Exchange resolution: read × precision × stats × gear
- [ ] Stamina and momentum
- [ ] `auto` mode first (it's the testable one), then `tactical`, then `reflex`
- [ ] CLI timed input against a monotonic deadline
- [ ] Multi-combatant fights with per-combatant action meters
- [ ] Temporary allies — `attachAlly`/`dismissAlly`, allies fighting on `auto` profiles
- [ ] Fleeing, with route-aware consequences
- [ ] Skill growth and enemy familiarity
- [ ] Balance pass: verify the acceptance test with real play

---

## Phase 4 — The wizard, properly

**Usable at the end:** someone who isn't you can build a small game without
writing YAML.

- [ ] Declarative step/flow model and field types
- [ ] `Query`-backed selection so every reference is picked, never typed
- [ ] Condition and effect builders with plain-English rendering
- [ ] Project model, resumable task list, save/load round-trip through YAML
- [ ] Live validation with a problem list
- [ ] Playtest-from-anywhere with seed and start-state control
- [ ] Debug overlay: condition evaluation, encounter rolls, active modifiers
- [ ] World starter and encounter-table suggestions
- [ ] Backgrounds and creation-point allocation at character creation
- [ ] Retire `src/wizard.py`

---

## Phase 5 — The web client

**Playable at the end:** a browser tab, no install, with a real map.

- [ ] FastAPI session service; WebSocket event stream
- [ ] React + TS PWA: narrative pane, choices, character, inventory, journal
- [ ] SVG map with fog of war, route lengths, weather overlay
- [ ] Combat view with timing bar and momentum
- [ ] Offline-capable PWA shell
- [ ] Pyodide build: engine client-side, static deploy to GitHub Pages
- [ ] Accessibility pass — ARIA live regions, keyboard nav, reduced motion
- [ ] **Economy**: goods, markets, stock, price formation, trade flow between
      connected markets (`economy: market`)

---

## Phase 6 — Authoring in the browser

**Usable at the end:** build a world by dragging nodes on a map.

- [ ] Wizard flow graph rendered as web forms
- [ ] Visual map editor — drag locations, draw routes, set travel times
- [ ] Scene graph visualization with unreachable-node detection
- [ ] Entity/item editors with live preview
- [ ] Export a pack; import someone else's and remix it
- [ ] One-click playtest from any point in the editor
- [ ] Economy phase 2: event shocks, haggling as negotiation, merchant capital,
      caravans as mobile markets, the map's price overlay

---

## Phase 7 — Community

**True at the end:** a repo full of worlds anyone can play, that accepts
contributions safely.

- [ ] `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, PR template
- [ ] CI: schema validation, reference integrity, reachability
- [ ] Autoplay smoke tests over every pack
- [ ] Balance report as a PR comment
- [ ] Game gallery in the web client, driven by pack manifests
- [ ] `packs/scifi.core` — the genre-neutrality proof
- [ ] Hosted deployment

---

## Phase 8 — Shared worlds

Deliberately vague; revisit when phases 1–7 exist.

Direction settled ([open question 10](13-open-questions.md#10-what-is-the-multiplayer-model--resolved-direction-only)):
**asynchronous shared persistent worlds**, not real-time co-op.

- [ ] Persistent server-side worlds
- [ ] Asynchronous traces: other players' choices visible in your world — the
      bridge you burned, the troll someone else killed, the market emptied of iron
- [ ] Crossing quests — several players' objectives on one map
- [ ] Shared economy and shared world-event history across sessions

---

## Working notes

Kept from the v0 readme, since they're still the right instinct:

- Prefer small commits that leave the project playable.
- When a design question comes up, write the answer into `docs/` as part of the
  change. Undocumented decisions are how this stalled before.
- The templates in `templates/` are the v0 design. They stay until the schemas in
  `schemas/` replace them, then they go.
