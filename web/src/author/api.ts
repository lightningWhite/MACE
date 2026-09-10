/**
 * Talking to the authoring service.
 *
 * Thinner than `src/api.ts` on purpose. Authoring has no clock in it — nobody
 * is answering a troll inside a 700ms window — so there is no socket, no
 * fallback and no transport to report. Every call is a request that comes back
 * as one frame, and every frame carries the task list, which is what makes the
 * problem count in the header move as an author types.
 *
 * Paths resolve against the page's base for the same reason the game's do: one
 * build has to work at the root and under a project subpath.
 */

import type {
  Atlas,
  AuthorableGames,
  AuthorableLibraries,
  Built,
  Exported,
  Frame,
  Graph,
  NothingOpen,
  Preview,
  Problem,
  Rehearsal,
  Setup,
  Vocabulary,
} from "./protocol";

export const API = `${import.meta.env.BASE_URL}api/author`;

/** What the service said when it refused. */
export class StudioError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "StudioError";
  }
}

async function ask<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      headers: { "content-type": "application/json" },
      ...init,
    });
  } catch {
    throw new StudioError(
      "the wizard is not answering — is `mace author --web` running?",
      0,
    );
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) =>
        typeof body.detail === "string" ? body.detail : response.statusText,
      )
      .catch(() => response.statusText);
    throw new StudioError(detail, response.status);
  }
  return (await response.json()) as T;
}

function sending(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}

/**
 * The task list, and nothing else — or `{open: false}` before anyone has
 * picked a game to author. Check with `isOpen` before reading it as a frame.
 */
export function desk(): Promise<Frame | NothingOpen> {
  return ask<Frame | NothingOpen>("");
}

/** Every game a `mace dev` desk can open, switch to, or already has open. */
export function games(): Promise<AuthorableGames> {
  return ask<AuthorableGames>("/games");
}

/** Every library pack a new game could depend on. */
export function libraries(): Promise<AuthorableLibraries> {
  return ask<AuthorableLibraries>("/libraries");
}

/** Start a new game pack, from as little as its title, and open it. */
export function newGame(
  name: string,
  requires: Record<string, string> = {},
): Promise<Frame> {
  return ask<Frame>("/games", sending({ name, requires }));
}

/** Switch to an existing game pack. Refused while the open one is unsaved. */
export function openGame(pack: string): Promise<Frame> {
  return ask<Frame>("/open", sending({ pack }));
}

/** One section's contents. */
export function section(id: string): Promise<Frame> {
  return ask<Frame>(`/sections/${encodeURIComponent(id)}`);
}

/**
 * One object's steps.
 *
 * A collection with no object id is the game manifest, which is one object
 * rather than a list.
 */
export function object(collection: string, id?: string | null): Promise<Frame> {
  const where = encodeURIComponent(collection);
  return ask<Frame>(
    id === undefined || id === null
      ? `/objects/${where}`
      : `/objects/${where}/${encodeURIComponent(id)}`,
  );
}

/** Record one answer. The value is authored, not typed text. */
export function answer(
  collection: string,
  step: string,
  value: unknown,
  object?: string | null,
): Promise<Frame> {
  return ask<Frame>(
    "/answers",
    sending({ collection, step, value, object: object ?? null }),
  );
}

/** Make a new object from as little as its name, and open it. */
export function create(
  collection: string,
  name: string,
  section?: string | null,
): Promise<Frame> {
  return ask<Frame>(
    `/objects/${encodeURIComponent(collection)}`,
    sending({ name, section: section ?? null, answers: {} }),
  );
}

/** Remove an object. What it breaks shows up in the problem list. */
export function remove(collection: string, id: string): Promise<Frame> {
  return ask<Frame>(
    `/objects/${encodeURIComponent(collection)}/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

/** Write every changed file. */
export function save(): Promise<Frame> {
  return ask<Frame>("/save", sending({}));
}

/** Everything the validator found, worst first. */
export function problems(): Promise<{ problems: Problem[] }> {
  return ask<{ problems: Problem[] }>("/problems");
}

/** The world map as the author has drawn it. */
export function atlas(): Promise<Atlas> {
  return ask<Atlas>("/map");
}

/** One object as the engine will see it, not as the file writes it. */
export function preview(collection: string, id: string): Promise<Preview> {
  return ask<Preview>(
    `/preview/${encodeURIComponent(collection)}/${encodeURIComponent(id)}`,
  );
}

/** Every scene, what leads to it, and what it leads to. */
export function graph(): Promise<Graph> {
  return ask<Graph>("/graph");
}

/**
 * Draw a road between two places, and the ways onto it.
 *
 * One call rather than three, because drawing a road is one authoring
 * intention: a route is a road and an exit is the option to walk down it.
 */
export function link(
  origin: string,
  destination: string,
  ticks: number,
  name?: string,
): Promise<Frame> {
  return ask<Frame>(
    "/roads",
    sending({ origin, destination, ticks, name: name ?? null }),
  );
}

/** Rub out a road, and the ways onto it. */
export function unlink(route: string): Promise<Frame> {
  return ask<Frame>(`/roads/${encodeURIComponent(route)}`, { method: "DELETE" });
}

/** The cascades, with this pack's options on them. */
export function vocabulary(): Promise<Vocabulary> {
  return ask<Vocabulary>("/vocabulary");
}

/** The playtest form: the setup used last, and the pickers to change it. */
export function rehearsal(): Promise<Rehearsal> {
  return ask<Rehearsal>("/playtest");
}

/**
 * Open a playthrough of the pack as it stands, unsaved changes and all.
 *
 * What comes back is a session id, and the *game* client plays it from there
 * through the ordinary session routes. Two front-ends, one engine: a playtest
 * is a playthrough, not a special mode.
 */
export function playtest(setup: Setup): Promise<{ session: string }> {
  return ask<{ session: string }>("/playtest", sending(setup));
}

/** Write the pack out as one file somebody else can open. */
export function exportPack(into?: string | null): Promise<Exported> {
  return ask<Exported>("/export", sending({ into: into ?? null }));
}

/** Turn a cascade's answers into an authored condition or effect. */
export function build(
  kind: "conditions" | "effects",
  tag: string,
  answers: Record<string, unknown>,
): Promise<Built> {
  return ask<Built>("/build", sending({ kind, tag, answers }));
}
