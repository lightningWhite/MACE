/**
 * Ask MACE for a bundle of itself and its worlds.
 *
 * The static build fetches `mace-bundle.zip` and runs the engine from it, so
 * a build without one produces a site that loads and then cannot play. A
 * hosted build does not need it — there is a server holding the engine — so a
 * missing Python is a loud warning rather than a failure, and the message
 * says which of the two you have just built.
 */

import { spawnSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const out = join(here, "..", "public", "mace-bundle.zip");

/** The project's virtualenv first, then whatever `mace` is on the path. */
const CANDIDATES = [
  join(repo, "env", "bin", "python"),
  join(repo, ".venv", "bin", "python"),
  "python3",
  "python",
];

function build() {
  for (const python of CANDIDATES) {
    if (python.includes("/") && !existsSync(python)) continue;
    const run = spawnSync(
      python,
      ["-m", "mace.cli", "bundle", "packs", "-o", out],
      { cwd: repo, encoding: "utf8" },
    );
    if (run.status === 0) {
      process.stdout.write(run.stdout);
      return true;
    }
  }
  return false;
}

if (build()) {
  console.log(`bundle: ${(statSync(out).size / 1024).toFixed(0)} KiB → public/`);
} else {
  console.warn(
    "bundle: no working `mace` found, so public/mace-bundle.zip was not " +
      "rebuilt.\n" +
      "        Fine for a build that will be served by `mace serve`; a static " +
      "deployment\n        needs it — run `mace bundle` and build again.",
  );
}
