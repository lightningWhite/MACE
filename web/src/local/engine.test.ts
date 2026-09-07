/**
 * Choosing where the game runs.
 *
 * One build serves two deployments: a hosted one with a session service, and
 * a static one with no server at all that runs the same engine in this tab.
 * The client asks rather than being told at build time, which is also what
 * lets an offline tab fall through to the engine it already has.
 *
 * Booting Pyodide is not tested here — jsdom has no WebAssembly worker, and a
 * renderer's test suite is the wrong place to spend thirty seconds on it.
 * `npm run check:pyodide` does that against the real runtime, and checks the
 * frames it produces against the ones recorded from CPython.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { remote, serviceIsUp } from "../api";
import { local } from "./engine";
import { fakeService } from "../test/wire";

afterEach(() => vi.unstubAllGlobals());

describe("serviceIsUp", () => {
  it("is true when a session service answers", async () => {
    vi.stubGlobal("fetch", fakeService().fetcher);
    expect(await serviceIsUp()).toBe(true);
  });

  it("is false when the files are served by something that is not one", async () => {
    vi.stubGlobal("fetch", fakeService({ absent: true }).fetcher);
    expect(await serviceIsUp()).toBe(false);
  });

  it("is false when there is nothing on the other end at all", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    expect(await serviceIsUp()).toBe(false);
  });
});

describe("the two services", () => {
  it("say where they are, so the player can be told", () => {
    expect(remote.where).toBe("server");
    expect(local(() => {}).where).toBe("here");
  });

  it("are the same shape, so nothing above them can tell them apart", () => {
    const here = local(() => {});
    for (const method of [
      "listGames",
      "creationFor",
      "openSession",
      "resumeSession",
      "fetchSave",
      "connect",
    ] as const) {
      expect(typeof here[method]).toBe("function");
      expect(typeof remote[method]).toBe("function");
    }
  });
});
