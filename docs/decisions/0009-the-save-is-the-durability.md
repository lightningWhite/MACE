# ADR-0009 — The server holds no playthroughs; the save does

**Status:** Accepted

## Context

Phase 5 puts a browser in front of the engine, and
[ADR-0005](0005-python-core-with-pyodide.md) has the engine staying Python: a
FastAPI service holds the session and the browser is a thin renderer, until
Pyodide moves the engine into the tab and the server goes away entirely.

An HTTP request is stateless and a playthrough is not, so something has to
hold a session between calls. Deciding *what* is a fork, because the obvious
answer — a database — is also the answer [phase 8](../12-roadmap.md) will
eventually need for shared persistent worlds, and building it now would look
like getting ahead.

## Decision

**The service holds sessions in one process's memory, and the client's save
file is the only durability.** A session dies with the process, is invisible
to a second worker, and is evicted when the registry fills. `GET
/api/sessions/{id}/save` hands the client the recipe to reopen the same
playthrough anywhere running the same content, and `POST /api/sessions` with
that record in `save` is how it comes back.

This works because of [ADR-0004](0004-deterministic-seeded-simulation.md): a
session *is* its packs, its seed and its ordered action log. There is no
server-side state that the save does not already contain, so nothing is lost
by not storing it — only re-simulated.

## Alternatives considered

**A database of sessions.** Durable, multi-worker, and what phase 8 needs.
Rejected for now because it is the wrong shape for the thing that comes
*next*: Pyodide removes the server, and a persistence layer built in phase 5
would be written, deployed, and then have nothing to persist. It also adds an
operational dependency to a hobby project whose whole deployment story is
"static files on GitHub Pages".

**Server-side session files on disk.** Cheaper than a database and survives a
restart. Rejected because it makes the server the owner of a playthrough that
the player cannot take with them, which is backwards: the save is already
small, diffable and shareable, and the player holding it is the feature.

**Sticky sessions behind a load balancer.** Rejected as a solution to a
problem this project does not have, and one that would make the in-memory
registry look load-bearing when it is meant to be temporary.

## Consequences

- **A client that does not keep its save loses its game on a restart.** The
  web client must fetch the save and store it locally rather than treating the
  session id as the playthrough. The 404 for a missing session says so in as
  many words.
- **The registry is bounded and evicts.** A crawler opening sessions cannot
  exhaust memory, and an evicted session is a recoverable inconvenience rather
  than a lost game.
- **A session id is a bearer token.** Anybody holding one can play that
  playthrough, so it is 16 bytes of `secrets`, not a counter. There is no
  authentication beyond that, which is why `mace serve` binds to localhost by
  default and says what binding it wider means.
- **Phase 8 changes this decision rather than extending it.** Shared persistent
  worlds need server-owned state with a lifetime longer than a process, and
  that is a different design, not a bigger dictionary.
