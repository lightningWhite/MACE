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
 * Every path here is relative. The dev server proxies `/api` and a deployment
 * serves the client from the same origin as the service, so there is no base
 * URL to configure and no build that is wrong in one environment.
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
  return ask("/api/games");
}

export function creationFor(
  pack: string,
  background?: string,
): Promise<CreationOffer> {
  const query = background ? `?background=${encodeURIComponent(background)}` : "";
  return ask(`/api/games/${encodeURIComponent(pack)}/creation${query}`);
}

export function openSession(request: {
  pack?: string;
  seed?: string;
  combatMode?: string;
  timePressure?: number;
  character?: Made;
}): Promise<Frame> {
  return ask("/api/sessions", { method: "POST", body: JSON.stringify(request) });
}

export function resumeSession(save: SaveRecord): Promise<Frame> {
  return ask("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ save }),
  });
}

export function fetchSave(session: string): Promise<SaveRecord> {
  return ask(`/api/sessions/${encodeURIComponent(session)}/save`);
}

export function closeSession(session: string): Promise<void> {
  return fetch(`/api/sessions/${encodeURIComponent(session)}`, {
    method: "DELETE",
  }).then(() => undefined);
}

/** How the client is currently reaching the service. */
export type Transport = "connecting" | "socket" | "polling";

interface Handlers {
  onFrame: (frame: Frame) => void;
  onRefusal: (message: string) => void;
  onTransport: (transport: Transport) => void;
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
    const url = `${scheme}://${window.location.host}/api/sessions/${encodeURIComponent(
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
          `/api/sessions/${encodeURIComponent(this.session)}/actions`,
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
