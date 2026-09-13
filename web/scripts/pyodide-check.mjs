/**
 * Boot the real thing and play it.
 *
 * The client's own tests replay recorded frames, which is right for testing a
 * renderer and useless for testing whether the engine runs at all under
 * WebAssembly. This does what the worker does — start Pyodide, install the
 * bundle, drive `Runtime.handle` — and checks the frames against the ones
 * recorded from CPython.
 *
 * That is ADR-0005's claim made falsifiable: one implementation, and a
 * playthrough in a browser tab is the same playthrough as in a terminal. It
 * takes about half a minute, so it is `npm run check:pyodide` rather than
 * part of `npm test`.
 *
 * It has to boot against `public/pyodide/` specifically — the directory
 * `pyodide.mjs` wrote and the one a deployment actually ships — not against
 * whatever `loadPyodide()` defaults to. Pyodide's own loader will quietly
 * fetch a wheel it can't find from jsdelivr and cache it into node_modules
 * "for future use," which is exactly the bug that shipped a site missing
 * pydantic and pyyaml while this very check kept passing: it never looked at
 * the directory that got deployed, so a hole in it went unnoticed. Asserting
 * every wanted file is on disk *before* booting closes that gap even on a
 * runner with network access, where the fallback would otherwise succeed
 * quietly again.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { loadPyodide } from "pyodide";

import { packageFiles } from "./pyodide-packages.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const runtime = join(here, "..", "public", "pyodide");
const bundle = join(here, "..", "public", "mace-bundle.zip");
const recorded = JSON.parse(
  readFileSync(join(here, "..", "src", "test", "frames.json"), "utf8"),
);

function assert(ok, what) {
  if (!ok) {
    console.error(`✗ ${what}`);
    process.exitCode = 1;
    return false;
  }
  console.log(`✓ ${what}`);
  return true;
}

const lock = JSON.parse(readFileSync(join(runtime, "pyodide-lock.json"), "utf8"));
const missing = packageFiles(lock)
  .map((info) => info.file_name)
  .filter((name) => !existsSync(join(runtime, name)));
if (
  !assert(
    missing.length === 0,
    "public/pyodide/ has every wheel loadPackage needs, without fetching one",
  )
) {
  console.error(`  missing: ${missing.join(", ")}`);
  process.exit(1);
}

const started = Date.now();
const py = await loadPyodide({ indexURL: `${runtime}/` });
await py.loadPackage(["pydantic", "pyyaml"]);
const booted = Date.now() - started;

py.FS.writeFile("/bundle.zip", readFileSync(bundle));
py.runPython(`
import sys, zipfile
with zipfile.ZipFile("/bundle.zip") as archive:
    archive.extractall("/mace")
sys.path.insert(0, "/mace")
from mace.browser import Runtime
_mace = Runtime.load("/mace")
`);
const ready = Date.now() - started;

/** The worker's one call, exactly. */
function handle(request) {
  py.globals.set("_request", JSON.stringify(request));
  return JSON.parse(py.runPython(`
import json
json.dumps(_mace.handle(json.loads(_request)))
`));
}

const opened = handle({
  type: "open",
  request: {
    pack: "peasants-quest",
    seed: "mace",
    combatMode: "tactical",
    character: { background: "peasants-quest:farmhand", spend: {} },
  },
});

/**
 * Two frames, compared on everything a player would notice.
 *
 * The session id is the one thing that legitimately differs — a tab plays one
 * game and has nothing to address across a network — and `warnings` only ever
 * appears on the frame that opens a session, which is not what the recording
 * captured.
 */
const same = (a, b) => {
  const strip = ({ session: _s, warnings: _w, ...rest }) => JSON.stringify(rest);
  return strip(a) === strip(b);
};

assert(same(opened, recorded.opening), "the opening frame matches CPython's");
assert(
  Array.isArray(opened.warnings) && opened.warnings.length === 0,
  "the content it loaded is the content the save expects",
);

let step = 0;
for (const { action, frame } of recorded.steps) {
  step += 1;
  const here = handle({ type: "act", action });
  if (!assert(same(here, frame), `step ${step} (${action.prompt ?? action.kind}) matches`)) {
    console.error("  wasm:", JSON.stringify(here).slice(0, 400));
    console.error("  host:", JSON.stringify(frame).slice(0, 400));
    break;
  }
}

assert(
  handle({ type: "save" }).actions.length === recorded.steps.length,
  "the save it writes is the playthrough it played",
);

console.log(
  `\npyodide booted in ${(booted / 1000).toFixed(1)}s, engine ready in ${(ready / 1000).toFixed(1)}s`,
);
