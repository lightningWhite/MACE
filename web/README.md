# The MACE web client

A renderer for the engine's event stream. It holds no rules: every panel draws
`frame.view`, which the engine projected, and the transcript draws
`frame.events`, which the engine emitted. If a panel wants something that is
not on the wire, the fix is a field on the projection in
`src/mace/session/view.py` — never a computation in a component.

The same build is also the **wizard**, at `#author`. It renders screens
`mace.wizard.studio` projects and holds no questions of its own: a step type
is added in `src/mace/wizard/fields.py` and appears here, and a condition tag
added to `builders.py` appears here without anybody touching this directory.
A fragment rather than a path or a router — a path would need the server to
serve `index.html` for a URL it has no file for, which a static host will not
do, and a router is a dependency for one decision.

## Running it

The easy way — one process, rebuilds the client first if it looks stale, and
serves every game under `packs/` to play or author, picked in the browser:

```bash
mace dev
# then open http://127.0.0.1:8000/
```

What that's actually doing, for when you want the pieces apart — two
processes in development, because Vite wants to own the reload:

```bash
mace serve packs/          # the session service on :8000
npm --prefix web run dev   # the client on :5173, proxying /api to it
```

The client's own code only ever says `/api/...`. In development Vite proxies
that; in a deployment the service serves the built files itself:

```bash
npm --prefix web run build
mace serve packs/ --client web/dist   # one origin, nothing to configure
```

The wizard is a different process, because it writes to your disk and the
session service never does — and this form of it opens exactly one pack,
chosen when the process starts, rather than picked in the browser:

```bash
mace author packs/games/peasants-quest --web --client web/dist
# then open http://127.0.0.1:8000/#author
```

`/api/author` only exists when something asked for it, so a hosted game is a
game and nothing else — and `#author` in a deployment without it just says the
wizard is not answering.

## Checking it

```bash
npm --prefix web run check   # tsc, strict
npm --prefix web test        # vitest
```

Both run on `git push` via pre-commit.

The tests replay **real frames**. `src/test/frames.json` is generated from an
actual playthrough of `packs/games/peasants-quest` by
`tests/test_web_wire.py`, and that Python test fails the moment the engine
stops sending what is recorded there. A client test that invented its own JSON
would pass forever, including after the protocol moved underneath it.

Regenerate the recording — and read the diff, because it is a change to the
contract every front-end is written against — with:

```bash
MACE_UPDATE_FIXTURES=1 pytest tests/test_web_wire.py
```

The wizard's screens are recorded the same way, in `src/test/author.json` by
`tests/test_web_author_wire.py`, from a copy of the same pack. Both
regenerate with `MACE_UPDATE_FIXTURES=1`.

## Two deployments, one build

**Hosted** — `mace serve` holds the sessions, the client is a renderer:

```bash
mace serve packs/ --client web/dist
```

**Static** — no server at all. The engine is compiled to WebAssembly and runs
in a worker in the tab:

```bash
npm --prefix web run build     # copies Pyodide, writes the bundle, builds
# then serve web/dist with anything at all
```

The client does not know which it is until it asks: it probes `/api/games` and
falls through to the local engine when nothing answers. That is also what lets
an offline tab in a static deployment keep playing.

`npm run check:pyodide` boots the real runtime, plays the recorded playthrough
through it, and compares every frame against the ones CPython produced. It
takes about half a minute, so it is not part of `npm test` — but it is what
makes "one implementation" a fact rather than a hope, and CI runs it before
publishing.

## Offline

`public/sw.js` is a hand-written service worker: it caches the shell as the
page asks for it, and never caches `/api` — a stale frame is a stale world.
It is registered only in production builds, because a worker caching Vite's
module graph makes every reload a lie.

An installed client with no network loads, says the game needs its server for
now, and points at the save in `localStorage`. That is the whole of it until
the Pyodide build, when there will be no server to be offline from.

## Layout

```
scripts/
  pyodide.mjs       Copy the runtime out of node_modules (build step)
  bundle.mjs        Ask MACE for a zip of itself and its worlds (build step)
  pyodide-check.mjs Play it under WebAssembly, compare against CPython
src/
  protocol.ts     The wire, as TypeScript sees it. The only file that knows it.
  api.ts          The Service interface, and the one that talks over a network
  local/          The other one: Pyodide in a worker, same interface
  transcript.ts   Events → lines to read (the job Renderer does in the CLI)
  storage.ts      Keeping the save, because the server does not (ADR-0009)
  App.tsx         The client: a transcript, a frame, and a connection
  map/            The SVG map and its layout
  combat/         The tell, the window, and the answers
  panels/         Character, Pack, Journal, Choices, StatusLine, Opening
  author/         The wizard: the task list, a section, one object, one field
```
