# The MACE web client

A renderer for the engine's event stream. It holds no rules: every panel draws
`frame.view`, which the engine projected, and the transcript draws
`frame.events`, which the engine emitted. If a panel wants something that is
not on the wire, the fix is a field on the projection in
`src/mace/session/view.py` — never a computation in a component.

## Running it

Two processes in development, because Vite wants to own the reload:

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
src/
  protocol.ts     The wire, as TypeScript sees it. The only file that knows it.
  api.ts          Talking to the service: requests, and the socket
  transcript.ts   Events → lines to read (the job Renderer does in the CLI)
  storage.ts      Keeping the save, because the server does not (ADR-0009)
  App.tsx         The client: a transcript, a frame, and a connection
  panels/         Character, Pack, Journal, Choices, StatusLine, Opening
```
