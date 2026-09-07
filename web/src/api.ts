/**
 * Talking to the session service.
 *
 * Two ways in, as the service offers two. `Connection` holds a WebSocket open
 * because combat has a clock in it — a tell's window is measured in
 * milliseconds, and paying for connection setup inside it would make a fight
 * unfair in a way the player would feel and could not name. When the socket
 * cannot be had, the same actions go by `POST`, the same frames come back,
 * and the only difference the player sees is the word in the corner.
 *
 * Every path here is same-origin and resolved against the page's base. The
 * dev server proxies `/api`, a hosted deployment serves the client from the
 * same origin as the service, and a static one has no service at all — so
 * there is nothing to configure and no build that is wrong in one of them.
 */

import type {
  Action,
  CreationOffer,
  Frame,
  GameSummary,
  Made,
  Refusal,
  SaveRecord,
} from "./protocol";
import { isRefusal } from "./protocol";

/**
 * Where the service is, if there is one.
 *
 * Relative to the page's base rather than to `/`, because a project site on
 * GitHub Pages lives under `/<repo>/` and a build that hard-coded a leading
 * slash would be wrong in exactly one of the two deployments.
 */
export const API = `${import.meta.env.BASE_URL}api`;

/** What the service said when it refused. */
export class ServiceError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ServiceError";
  }
}

async function ask<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "content-type": "application/json" },
      ...init,
    });
  } catch {
    throw new ServiceError(
      "the service is not answering — is `mace serve` running?",
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
    throw new ServiceError(detail, response.status);
  }
  return (await response.json()) as T;
}

export function listGames(): Promise<{ games: GameSummary[] }> {
  return ask(`${API}/games`);
}

export function creationFor(
  pack: string,
  background?: string,
): Promise<CreationOffer> {
  const query = background ? `?background=${encodeURIComponent(background)}` : "";
  return ask(`${API}/games/${encodeURIComponent(pack)}/creation${query}`);
}

export function openSession(request: OpenRequest): Promise<Frame> {
  return ask(`${API}/sessions`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function resumeSession(save: SaveRecord): Promise<Frame> {
  return ask(`${API}/sessions`, {
    method: "POST",
    body: JSON.stringify({ save }),
  });
}

/**
 * The current frame of a playthrough somebody else opened.
 *
 * The one caller is the wizard's playtest, which opens a session on the
 * server and hands the game client its id. There is no local equivalent and
 * there should not be: a playtest of unsaved work only exists where the
 * half-finished pack is, which is the process the wizard is running in.
 */
export function lookSession(session: string): Promise<Frame> {
  return ask(`${API}/sessions/${encodeURIComponent(session)}`);
}

export function fetchSave(session: string): Promise<SaveRecord> {
  return ask(`${API}/sessions/${encodeURIComponent(session)}/save`);
}

export function closeSession(session: string): Promise<void> {
  return fetch(`${API}/sessions/${encodeURIComponent(session)}`, {
    method: "DELETE",
  }).then(() => undefined);
}

/** How the client is currently reaching the engine. */
export type Transport = "connecting" | "socket" | "polling" | "local";

export interface Handlers {
  onFrame: (frame: Frame) => void;
  onRefusal: (message: string) => void;
  onTransport: (transport: Transport) => void;
}

/**
 * Somewhere a game can be played.
 *
 * Two of these exist and the client cannot tell them apart, which is the
 * whole point: `remote` is the FastAPI service over HTTP and a socket, and
 * `local` (`./local/engine`) is the same Python engine compiled to WebAssembly
 * and running in a worker in this tab. Both hand back the frame
 * `mace.session.frame` builds.
 */
export interface Service {
  /** What to call this when telling the player where their game is running. */
  readonly where: "server" | "here";
  listGames(): Promise<{ games: GameSummary[] }>;
  creationFor(pack: string, background?: string): Promise<CreationOffer>;
  openSession(request: OpenRequest): Promise<Frame>;
  resumeSession(save: SaveRecord): Promise<Frame>;
  fetchSave(session: string): Promise<SaveRecord>;
  connect(session: string, handlers: Handlers): Link;
}

/** A playthrough held open, however it is being held. */
export interface Link {
  send(action: Action): Promise<void>;
  close(): void;
}

export interface OpenRequest {
  pack?: string;
  seed?: string;
  combatMode?: string;
  timePressure?: number;
  character?: Made;
}

/** The service reachable over the network, when there is one. */
export const remote: Service = {
  where: "server",
  listGames,
  creationFor,
  openSession,
  resumeSession,
  fetchSave,
  connect: (session, handlers) => {
    const held = new Connection(session, handlers);
    held.open();
    return held;
  },
};

/**
 * Whether a session service is answering here.
 *
 * The static build has no server at all, and the hosted one has nothing else,
 * so the client asks rather than being told at build time. One build, both
 * deployments, and an offline tab falls through to the engine it already has.
 */
export async function serviceIsUp(): Promise<boolean> {
  try {
    const response = await fetch(`${API}/games`, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * A playthrough, held open.
 *
 * Opens a socket and sends actions down it. If the socket will not open or
 * drops, actions go by `POST` instead and the caller is told, because a
 * degraded connection is a thing a player in a timed fight deserves to know
 * about rather than discover.
 */
export class Connection {
  private socket: WebSocket | null = null;
  private closed = false;
  /** The socket sends the current frame on connect; the caller has it. */
  private greeted = false;

  constructor(
    readonly session: string,
    private readonly handlers: Handlers,
  ) {}

  open(): void {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${window.location.host}${API}/sessions/${encodeURIComponent(
      this.session,
    )}/stream`;

    this.handlers.onTransport("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      this.handlers.onTransport("polling");
      return;
    }
    this.socket = socket;

    socket.onopen = () => this.handlers.onTransport("socket");
    socket.onmessage = (message: MessageEvent<string>) => {
      const body = JSON.parse(message.data) as Frame | Refusal;
      if (isRefusal(body)) {
        this.handlers.onRefusal(body.error);
        return;
      }
      // The greeting frame is the one the caller already rendered from the
      // POST that opened the session. Rendering it again would repeat the
      // opening prose into the transcript.
      if (!this.greeted) {
        this.greeted = true;
        return;
      }
      this.handlers.onFrame(body);
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      this.socket = null;
      if (!this.closed) this.handlers.onTransport("polling");
    };
  }

  /**
   * Do one thing.
   *
   * Down the socket when there is one, by `POST` when there is not. Either
   * way the caller gets a frame or a refusal through the same handlers.
   */
  async send(action: Action): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(action));
      return;
    }
    try {
      this.handlers.onFrame(
        await ask<Frame>(
          `${API}/sessions/${encodeURIComponent(this.session)}/actions`,
          { method: "POST", body: JSON.stringify(action) },
        ),
      );
    } catch (error) {
      this.handlers.onRefusal(
        error instanceof Error ? error.message : String(error),
      );
    }
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
    this.socket = null;
  }
}
