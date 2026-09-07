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

import type { Built, Frame, Problem, Vocabulary } from "./protocol";

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

/** The task list, and nothing else. */
export function desk(): Promise<Frame> {
  return ask<Frame>("");
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

/** The cascades, with this pack's options on them. */
export function vocabulary(): Promise<Vocabulary> {
  return ask<Vocabulary>("/vocabulary");
}

/** Turn a cascade's answers into an authored condition or effect. */
export function build(
  kind: "conditions" | "effects",
  tag: string,
  answers: Record<string, unknown>,
): Promise<Built> {
  return ask<Built>("/build", sending({ kind, tag, answers }));
}
