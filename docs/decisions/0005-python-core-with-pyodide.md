# ADR-0005 — Python engine core, browser via Pyodide

**Status:** Accepted, explicitly revisitable

## Context

The engine exists in Python today. The goal includes a browser-based PWA for
playing and authoring, and eventually a hosted site where anyone can play with no
install. Something has to decide where the simulation actually runs.

Constraints that matter:

- This is a hobby project maintained in scattered time. Two implementations of
  the same engine is a real risk of neither being finished.
- "A GitHub repo full of worlds anyone can play" argues strongly for a deployment
  with no server to run or pay for.
- The engine is not performance-critical. It's a text game — a tick is a handful
  of table lookups and a few random draws.

## Decision

**The engine core stays Python**, constrained to **stdlib + pydantic**, so it can
run under Pyodide in a browser tab.

Three deployment targets, in roadmap order:

1. **Terminal** — Python directly. Available now.
2. **Hosted** (phase 5) — FastAPI serves sessions over WebSocket; the browser is
   a thin renderer.
3. **Static** (phase 5) — the same engine compiled to WASM via Pyodide, running
   entirely client-side, deployable to GitHub Pages, playable offline.

## Alternatives considered

**Rewrite the core in TypeScript.** One language across engine and web client, a
small fast bundle, and the obvious choice if the web app were the only target.
Rejected for now: it throws away working Python, makes the CLI and any Python
tooling a second implementation, and — most importantly — costs weeks up front
that would be better spent making the game good. Revisit if Pyodide's payload
proves to be a real barrier.

**Two implementations, Python and TypeScript, kept in sync.** Best of both, in
theory. Rejected: keeping two simulations behaviorally identical is a serious
ongoing tax, and this project has one maintainer working in bits of time.

**Server-only, thin client forever.** Simple and small. Rejected as the *only*
option because it requires hosting to exist before anyone can play in a browser,
and it makes offline play impossible. Kept as one of the two web targets, since
it's also the path multiplayer would take.

## Consequences

- **One implementation.** Every front-end runs identical logic; no drift.
- **No backend required** for single-player web. Static hosting is free and
  effectively unkillable — good for a community project's longevity.
- **Offline play** falls out of the PWA + Pyodide combination.
- **Payload cost.** Pyodide's runtime is a multi-megabyte first load.
  Mitigations: aggressive service-worker caching (paid once per version), a
  slim build with unused stdlib modules stripped, and a fast-loading shell
  that streams the runtime behind a splash. Still, first load on a phone over
  cellular is the real risk and the thing to measure.

  **Measured** (phase 5, Pyodide 314.0.6 / CPython 3.14):

  | | |
  |---|---|
  | `pyodide.asm.wasm` | 9.2 MB |
  | `python_stdlib.zip` | 2.4 MB |
  | pydantic, pydantic-core, pyyaml and their deps | 2.0 MB |
  | `mace-bundle.zip` — the engine *and* every world | 0.35 MB |
  | the client itself | 0.23 MB (68 KB gzipped) |
  | **total** | **~16 MB**, cached by the service worker after the first visit |

  The engine and its content are a rounding error against the interpreter,
  which is worth knowing: adding worlds is nearly free, and the cost is
  Python's, not MACE's. Time from a cold start to a playable first frame is
  about 3.6s on a laptop — 2.0s of that is Pyodide starting, the rest is
  unzipping the bundle, importing the engine and loading three packs.

  The runtime is served from the same origin rather than a CDN, because a
  service worker cannot cache cross-origin requests and offline play is the
  whole point. It is copied out of `node_modules` at build time and never
  committed.

- **The claim is checked, not assumed.** `npm run check:pyodide` boots the real
  runtime, plays the recorded playthrough through `mace.browser`, and compares
  every frame against the ones CPython produced. It runs before the site is
  published. "One implementation" is a property this project can lose by
  accident, so it is a test.
- **Dependency discipline.** The core cannot use anything that doesn't run under
  Pyodide. This is a genuine constraint on the engine, and a healthy one.
- **The escape hatch is kept open deliberately.** The engine is specified in these
  docs and covered by golden replay tests, so a TypeScript port could be verified
  against the Python one rather than reimplemented on faith. That's what makes
  this decision safe to make now and cheap to revisit with real numbers.
