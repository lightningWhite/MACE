/**
 * The engine in this tab, dressed as a service.
 *
 * The same interface the network one implements, so `App` cannot tell them
 * apart — which is what ADR-0005 buys: one implementation, three deployments,
 * and no client-side drift between them.
 *
 * There is no socket here because there is nothing to connect to. A "send"
 * is a `postMessage` to a worker and the frame comes back on the next tick,
 * which is faster than any network and is why combat's window is fair here
 * without anything special being done about it.
 */

import type { Handlers, Link, OpenRequest, Service } from "../api";
import type { CreationOffer, Frame, GameSummary, SaveRecord } from "../protocol";
import type { Ask, Body, Reply } from "./worker";

/** What the engine is doing while it starts. Empty once it has. */
export type Progress = string | null;

class Local implements Service {
  readonly where = "here" as const;

  private worker: Worker | null = null;
  private waiting = new Map<
    number,
    { resolve: (body: unknown) => void; reject: (error: Error) => void }
  >();
  private next = 0;
  private booted: Promise<void> | null = null;

  constructor(private readonly onProgress: (progress: Progress) => void) {}

  private start(): Worker {
    if (this.worker !== null) return this.worker;

    const worker = new Worker(new URL("./worker.ts", import.meta.url), {
      type: "module",
    });
    worker.onmessage = (message: MessageEvent<Reply>) => {
      const reply = message.data;
      if ("progress" in reply) {
        this.onProgress(reply.progress);
        return;
      }
      const waiting = this.waiting.get(reply.id);
      if (waiting === undefined) return;
      this.waiting.delete(reply.id);
      if (reply.ok) waiting.resolve(reply.body);
      else waiting.reject(new Error(reply.error));
    };
    this.worker = worker;
    return worker;
  }

  private send<T>(ask: Body): Promise<T> {
    const worker = this.start();
    const id = (this.next += 1);
    return new Promise<T>((resolve, reject) => {
      this.waiting.set(id, {
        resolve: (body) => resolve(body as T),
        reject,
      });
      worker.postMessage({ ...ask, id } as Ask);
    });
  }

  /** Start Python, once, and keep everyone else waiting on the same promise. */
  private ready(): Promise<void> {
    this.booted ??= this.send<string>({ type: "boot" }).then(() => {
      this.onProgress(null);
    });
    return this.booted;
  }

  async listGames(): Promise<{ games: GameSummary[] }> {
    await this.ready();
    return this.send({ type: "games" });
  }

  async creationFor(pack: string, background?: string): Promise<CreationOffer> {
    await this.ready();
    return this.send(
      background === undefined
        ? { type: "creation", pack }
        : { type: "creation", pack, background },
    );
  }

  async openSession(request: OpenRequest): Promise<Frame> {
    await this.ready();
    return this.send({ type: "open", request: { ...request } });
  }

  async resumeSession(save: SaveRecord): Promise<Frame> {
    await this.ready();
    return this.send({ type: "open", request: { save } });
  }

  async fetchSave(): Promise<SaveRecord> {
    await this.ready();
    return this.send({ type: "save" });
  }

  connect(_session: string, handlers: Handlers): Link {
    handlers.onTransport("local");
    return {
      send: async (action) => {
        try {
          handlers.onFrame(await this.send<Frame>({ type: "act", action }));
        } catch (error) {
          handlers.onRefusal(
            error instanceof Error ? error.message : String(error),
          );
        }
      },
      close: () => {
        this.worker?.terminate();
        this.worker = null;
        this.booted = null;
      },
    };
  }
}

/**
 * A service backed by the engine running in this tab.
 *
 * @param onProgress - called with what the engine is doing while it starts,
 *   and with null once it has. The first load is multi-megabyte, and a line
 *   saying which part is the difference between "slow" and "broken".
 */
export function local(onProgress: (progress: Progress) => void): Service {
  return new Local(onProgress);
}
