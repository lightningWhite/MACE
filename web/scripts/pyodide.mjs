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
 * lock file is what lets `loadPackage` resolve them by name — but the npm
 * package only ships the runtime, not every wheel it can name. A clean
 * `npm ci` has the lock file entry for "pyyaml" and no `pyyaml-*.whl` beside
 * it, so a wheel node_modules doesn't have is fetched from the same CDN
 * Pyodide itself resolves packages against, and checked against the hash the
 * lock file pins before it's trusted. Silently shipping without one is worse
 * than a slower build: the site loads and then cannot play.
 */

import { createHash } from "node:crypto";
import { cp, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { packageFiles } from "./pyodide-packages.mjs";

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

/** Get one package's wheel into `public/pyodide/`, from disk or the CDN. */
async function ensure(info, available, version) {
  const dest = join(into, info.file_name);
  if (available.includes(info.file_name)) {
    await cp(join(from, info.file_name), dest);
    return "local";
  }

  const url = `https://cdn.jsdelivr.net/pyodide/v${version}/full/${info.file_name}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`pyodide: could not fetch ${info.file_name} from ${url}: ${response.status}`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  if (sha256 !== info.sha256) {
    throw new Error(
      `pyodide: ${info.file_name} does not match the checksum pyodide-lock.json pins ` +
        `(got ${sha256}, expected ${info.sha256})`,
    );
  }
  await writeFile(dest, bytes);
  return "fetched";
}

async function main() {
  await mkdir(into, { recursive: true });
  const available = await readdir(from);

  const missingRuntime = RUNTIME.filter((name) => !available.includes(name));
  if (missingRuntime.length > 0) {
    throw new Error(`pyodide: node_modules/pyodide is missing ${missingRuntime.join(", ")}`);
  }
  let bytes = 0;
  for (const name of RUNTIME) {
    await cp(join(from, name), join(into, name));
    bytes += (await stat(join(into, name))).size;
  }

  const lock = JSON.parse(await readFile(join(from, "pyodide-lock.json"), "utf8"));
  const { version } = JSON.parse(await readFile(join(from, "package.json"), "utf8"));
  const files = packageFiles(lock);

  let fetched = 0;
  for (const info of files) {
    if ((await ensure(info, available, version)) === "fetched") fetched += 1;
    bytes += (await stat(join(into, info.file_name))).size;
  }

  const note = fetched > 0 ? ` (${fetched} fetched from the CDN)` : "";
  console.log(
    `pyodide: ${RUNTIME.length + files.length} files${note}, ` +
      `${(bytes / 1024 / 1024).toFixed(1)} MB → public/pyodide/`,
  );
}

await main();
