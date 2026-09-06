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

## Phase 1 — The content pipeline *(current)*

**Playable at the end:** a linear, three-location game you can walk through in a
terminal, with scenes, choices, items, and win/lose.

- [x] Pydantic content models for pack, entity, location, route, scene, quest, game
- [x] JSON Schemas in `schemas/`, generated from the models
- [x] Pack loader: discovery, id resolution, `extends` inheritance, dependency order
- [ ] Validator with error/warning/note severities and file+id reporting
- [x] `mace.engine.expr` — the safe expression parser and evaluator
- [ ] Structured condition and effect evaluation
- [ ] `GameState`, `Action`, `Event`, and the `step()` function
- [ ] Seeded named RNG streams
- [ ] Minimal CLI player: `mace play <pack>`
- [ ] First golden replay test
- [ ] Items carry `baseValue`; `mace.core` buy/sell scenes (`economy: simple`)
- [ ] `packs/games/peasants-quest` — the first three locations

---

## Phase 2 — A world that moves

**Playable at the end:** the same game, but journeys take days, storms roll
through, and the road between towns is dangerous.

- [ ] Clock, calendar, day parts, seasons
- [ ] Climate model: seasonal weights + Markov transitions
- [ ] Regions and weather fronts propagating across the region graph
- [ ] Weather effects: visibility, travel multiplier, stat modifiers, tags
- [ ] Entity `env` responses
- [ ] World events: celestial (scheduled), pressure (building, with omens), triggered
- [ ] Event phases, aftermath world changes, and the news queue
- [ ] Routes, waypoints, leg-by-leg travel resolution, interruption and resumption
- [ ] Encounter tables: two-stage resolution, cooldowns, anti-clumping pressure
- [ ] Exposure and rest — the mechanics that make weather bite
- [ ] Conditional descriptions driven by weather and time
- [ ] Status line in the CLI
- [ ] `packs/fantasy.core` — first real library pack

---

## Phase 3 — Combat

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
