# CLAUDE.md

Guidance for Claude Code (and other AI assistants) working in this repository.

## What this project is

MACE is an engine and authoring toolkit for text-driven adventure games. A "game"
is **data, not code**: YAML content packs describing a world map, entities,
interactions, quests, climate, and encounter tables. The engine loads that data
and runs a deterministic simulation; front-ends (CLI today, web PWA later) render
it.

Two audiences, always keep both in mind:

1. **Authors** — people building games with the wizard. They should never have to
   write code or hand-edit fiddly YAML.
2. **Players** — people playing those games. The world should feel alive: weather
   moves, days pass, journeys have consequences, combat rewards skill.

Read `docs/README.md` before making design decisions. The docs are the source of
truth for intended design; the code is behind them and catching up.

## Non-negotiable architectural rules

These exist so the same engine can drive a terminal, a browser, and eventually a
multiplayer server. Breaking them is a design regression, not a shortcut.

1. **The engine core is pure and deterministic.** `mace.engine` must not print,
   read input, touch the filesystem, call the network, or read the wall clock.
   Same content + same seed + same action log = byte-identical outcome. Always.
2. **Never call `random` directly.** All randomness comes from the seeded RNG
   service via a named stream (`rng.stream("weather")`). New subsystem, new
   stream — this keeps subsystems from desyncing each other's sequences.
3. **Content and state are separate.** Content packs are static, versioned, and
   shared (a troll's `base` strength). Session state is per-playthrough and
   mutable (this troll's `current` hitpoints). Never write runtime values into
   content models.
4. **Front-ends consume events, not state.** The engine returns an ordered list of
   events (`say`, `choices`, `weather.changed`, `combat.tell`, ...). UIs render
   events and a read-only view-model projection. A UI that reaches into engine
   internals is a bug.
5. **No `eval`/`exec` on content.** Author-supplied expressions go through the
   restricted expression evaluator in `mace.engine.expr`. Content packs are
   untrusted community input; treat them that way.
6. **Everything an author writes is schema-validated.** If you add a content
   field, add it to the pydantic model *and* the JSON Schema in `schemas/`, and
   add an example to the docs.

## Layout

```
docs/            Design docs — read these first
schemas/         JSON Schema for every content type
packs/           Content: shared libraries + playable games
src/mace/
  model/         Pydantic content models (authoring-time shapes)
  content/       Pack loading, id resolution, inheritance, validation
  engine/        Pure simulation: state, actions, events, rules
    world/       Clock, calendar, climate, weather, world events
    encounter/   Encounter tables and rolls
    economy/     Goods, markets, price formation, trade flow
    combat/      Tempo combat resolution
    expr/        Safe condition/effect expression evaluation
  session/       A running game: actions in, events out, saves
  wizard/        Declarative authoring flow (shared by CLI and web)
  cli/           Terminal front-end (play + author)
  api/           FastAPI session service (needs the `api` extra)
web/             React + TS client (see web/README.md)
tests/           Unit tests + golden replay conformance tests
```

The v0 prototype (`src/wizard.py`, `src/modules/`) is gone as of phase 4 —
`mace.wizard` replaced it. Git history has it if you want to see what a
decision used to look like.

## Conventions

- **Python 3.12+**, formatted with `black` (pre-commit enforces it). Run
  `pre-commit run --all-files` before committing.
- **Naming:** Python code uses `snake_case`. The existing prototype uses
  `camelCase` for functions — new code should not follow it. YAML content keys
  use `camelCase` (this is deliberate and consistent across all packs).
- **Content ids** are `kebab-case` and namespaced `pack-id:local-id`. Inside a
  pack, bare local ids resolve to that pack first, then to its dependencies.
- **Docstrings** use numpy-style parameter blocks — a summary line, then
  `Parameters` / `Returns` / `Raises` / `Yields` / `Attributes` as they apply.
  `src/mace/wizard/project.py` is a representative example.

## The web client

`web/` is a front-end and is held to the same bar as the CLI: it renders
events and the view-model, and holds no rules. `npm --prefix web run check`
(tsc, strict) and `npm --prefix web test` (vitest) both run on `git push`.

Its tests replay `web/src/test/frames.json` — real frames generated from a
real playthrough by `tests/test_web_wire.py`. If you change the wire, that
Python test fails; regenerate with `MACE_UPDATE_FIXTURES=1 pytest
tests/test_web_wire.py` and say so in the commit message, because it is a
change to the contract every front-end is written against.

## Testing expectations

- Rules changes need a unit test.
- Any change to simulation behavior needs a **golden replay test**: a seed plus
  an action log with a recorded event stream. These are the contract that lets a
  second engine implementation (e.g. a TypeScript port) be verified. If a change
  legitimately alters a golden file, say so explicitly in the commit message.
- Every pack in `packs/` must validate. `mace validate packs/` runs in CI.

## Working style for this repo

- This is a hobby project built in scattered bits of time. Prefer small,
  self-contained, committable steps over sweeping refactors.
- When a design question comes up that the docs don't answer, write the answer
  into `docs/` (or `docs/decisions/` for a real fork in the road) as part of the
  change. Undocumented design decisions are how this project got stuck before.
- Don't add dependencies casually. The engine core should stay on stdlib +
  pydantic so it can run under Pyodide in the browser. FastAPI and uvicorn are
  an optional extra (`pip install 'mace[api]'`) for `mace.api` alone — nothing
  under `mace.engine` or `mace.content` may import them.
- Flavor matters. Prompts, dialog, and generated text should feel like an
  adventure, not a form. But keep flavor in content and presentation layers, not
  baked into engine logic.
