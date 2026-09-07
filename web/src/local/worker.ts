/**
 * The engine, running in this tab.
 *
 * A Web Worker rather than the main thread, because Pyodide's first load is
 * seconds of WebAssembly compilation and a page that freezes while it starts
 * is a page people close. Everything here is off the main thread; the only
 * things that cross back are JSON frames, which are the same frames the HTTP
 * service sends.
 *
 * The Python half is `mace.browser`, in the package, so it is linted, typed
 * and tested with the rest of the engine rather than living as a string in a
 * JavaScript file. This worker's whole job is: fetch two files, unzip one,
 * put it on `sys.path`, and pass messages.
 */

import type { PyodideInterface } from "pyodide";

import type { Action, Frame, SaveRecord } from "../protocol";

/** What the main thread asks for. The request types are the service's routes. */
export type Body =
  | { type: "boot" }
  | { type: "games" }
  | { type: "creation"; pack: string; background?: string }
  | { type: "open"; request: Record<string, unknown> }
  | { type: "act"; action: Action }
  | { type: "look" }
  | { type: "save" };

/** One of those, with something to answer it against. */
export type Ask = Body & { id: number };

/** What it gets back. `progress` arrives unsolicited while booting. */
export type Reply =
  | { id: number; ok: true; body: unknown }
  | { id: number; ok: false; error: string }
  | { id: -1; progress: string };

/**
 * Where the runtime and the bundle are served from.
 *
 * Resolved against the *app's* base rather than this file's own location: a
 * bundled worker lives in `assets/`, and a build under `/<repo>/` on Pages
 * would otherwise go looking for `/<repo>/assets/pyodide/`.
 */
const BASE = new URL(import.meta.env.BASE_URL, self.location.origin).href;
const RUNTIME = new URL("pyodide/", BASE).href;
const BUNDLE = new URL("mace-bundle.zip", BASE).href;

let engine: PyodideInterface | null = null;

function say(progress: string): void {
  self.postMessage({ id: -1, progress } satisfies Reply);
}

/**
 * Start Python, install the engine, and load the worlds.
 *
 * Done once, on the first ask. The steps are announced as they happen because
 * this is the multi-megabyte first load ADR-0005 warned about, and a progress
 * line is the difference between "slow" and "broken".
 */
async function boot(): Promise<string> {
  if (engine !== null) return "already running";

  say("starting Python…");
  const { loadPyodide } = (await import(
    /* @vite-ignore */ `${RUNTIME}pyodide.mjs`
  )) as typeof import("pyodide");

  const py = await loadPyodide({ indexURL: RUNTIME });

  say("loading pydantic…");
  await py.loadPackage(["pydantic", "pyyaml"]);

  say("unpacking the engine…");
  const archive = await fetch(BUNDLE);
  if (!archive.ok) throw new Error(`no bundle at ${BUNDLE}`);
  py.FS.writeFile("/bundle.zip", new Uint8Array(await archive.arrayBuffer()));

  // `mace` has to be importable before `mace.browser` can do anything, so the
  // extracting is done here with stdlib and nothing else.
  py.runPython(`
import sys, zipfile
with zipfile.ZipFile("/bundle.zip") as archive:
    archive.extractall("/mace")
sys.path.insert(0, "/mace")
`);

  say("loading the worlds…");
  py.runPython(`
from mace.browser import Runtime
_mace = Runtime.load("/mace")
`);

  engine = py;
  return "ready";
}

/**
 * Hand one request to the Python runtime and bring the JSON back.
 *
 * JSON in and JSON out rather than Pyodide's object proxies, deliberately.
 * The dispatch is `Runtime.handle`, in the package, where it is typed and
 * tested; this side stays glue, and nothing crosses the boundary that a
 * `postMessage` could not have carried anyway.
 */
function ask(request: Record<string, unknown>): unknown {
  if (engine === null) throw new Error("the engine is not running");
  engine.globals.set("_request", JSON.stringify(request));
  return JSON.parse(
    engine.runPython(`
import json
json.dumps(_mace.handle(json.loads(_request)))
`) as string,
  );
}

self.onmessage = async (message: MessageEvent<Ask>) => {
  const { id, ...request } = message.data;
  try {
    const body =
      request.type === "boot" ? await boot() : ask(request as Record<string, unknown>);
    self.postMessage({ id, ok: true, body } satisfies Reply);
  } catch (error) {
    self.postMessage({
      id,
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    } satisfies Reply);
  }
};

export type { Frame, SaveRecord };
