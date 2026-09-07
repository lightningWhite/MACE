/**
 * Copy the Pyodide runtime out of node_modules and into `public/`.
 *
 * Self-hosted rather than loaded from a CDN, for two reasons. The service
 * worker only caches same-origin requests, and offline play is the whole
 * point of the static build — a game that needs a CDN to start is not offline
 * play. And a pinned copy beside the app cannot change under a player who
 * installed it.
 *
 * The files are copied at build time and never committed: `node_modules`
 * already has them, and 15 MB of WebAssembly does not belong in a hobby
 * project's git history.
 *
 * Only what the engine actually needs is copied. Pyodide's full distribution
 * carries hundreds of packages; MACE uses pydantic and a YAML reader, and the
 * lock file is what lets `loadPackage` resolve them by name.
 */

import { cp, mkdir, readdir, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "..", "node_modules", "pyodide");
const into = join(here, "..", "public", "pyodide");

/** The interpreter itself, and the manifest that finds packages by name. */
const RUNTIME = [
  "pyodide.asm.mjs",
  "pyodide.asm.wasm",
  "pyodide.mjs",
  "pyodide-lock.json",
  "python_stdlib.zip",
];

/** Everything `loadPackage(["pydantic", "pyyaml"])` pulls in. */
const WHEELS = [
  "annotated_types-",
  "pydantic-",
  "pydantic_core-",
  "pyyaml-",
  "typing_extensions-",
  "typing_inspection-",
];

async function main() {
  await mkdir(into, { recursive: true });

  const available = await readdir(from);
  const wanted = [
    ...RUNTIME.filter((name) => available.includes(name)),
    ...available.filter((name) => WHEELS.some((prefix) => name.startsWith(prefix))),
  ];

  let bytes = 0;
  for (const name of wanted) {
    await cp(join(from, name), join(into, name));
    bytes += (await stat(join(into, name))).size;
  }

  const missing = RUNTIME.filter((name) => !available.includes(name));
  if (missing.length > 0) {
    console.warn(`pyodide: could not find ${missing.join(", ")}`);
  }
  console.log(
    `pyodide: ${wanted.length} files, ${(bytes / 1024 / 1024).toFixed(1)} MB → public/pyodide/`,
  );
}

await main();
