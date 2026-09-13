/**
 * Which files `loadPackage(WANTED)` needs, per the lock file.
 *
 * Shared by `pyodide.mjs`, which has to fetch what node_modules doesn't ship,
 * and `pyodide-check.mjs`, which has to prove the build it is about to boot
 * did not silently skip any of them — Pyodide's own loader will fetch a
 * missing wheel from jsdelivr without complaint, which is exactly the bug
 * this file exists to keep either script from hiding again.
 */

/** What `mace.browser` asks `loadPackage` for. */
export const WANTED = ["pydantic", "pyyaml"];

/** `WANTED`, followed through the lock file to everything it depends on. */
export function packageFiles(lock) {
  const seen = new Set();
  const queue = [...WANTED];
  const files = [];
  while (queue.length > 0) {
    const name = queue.shift();
    if (seen.has(name)) continue;
    seen.add(name);
    // The lock file normalizes its own keys to hyphens but is not always
    // consistent about how it spells a *dependency*, so try both.
    const info = lock.packages[name] ?? lock.packages[name.replaceAll("_", "-")];
    if (info === undefined) {
      throw new Error(`pyodide-lock.json has no package named "${name}"`);
    }
    files.push(info);
    queue.push(...info.depends);
  }
  return files;
}
