/**
 * Keeping the save, because the server does not.
 *
 * [ADR-0009](../../docs/decisions/0009-the-save-is-the-durability.md): the
 * service holds sessions in one process's memory and the client's save file
 * is the only durability. That is a decision with a consequence, and this is
 * the consequence — a client that treated the session id as the playthrough
 * would lose the game on a restart.
 *
 * So the save is fetched after every action and written here. It is a few
 * hundred bytes of JSON: packs and versions, the seed, who the player is, and
 * everything they did.
 */

import type { SaveRecord } from "./protocol";

const KEY = "mace.save";

/** Put the playthrough somewhere it survives a reload. */
export function keep(save: SaveRecord): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(save));
  } catch {
    // A private window, or storage that is full. Losing the save is a worse
    // game, not a broken one, and there is nothing useful to say about it
    // in the middle of a playthrough.
  }
}

/** The playthrough this browser was last in, if it kept one. */
export function kept(): SaveRecord | null {
  try {
    const stored = window.localStorage.getItem(KEY);
    if (stored === null) return null;
    const save = JSON.parse(stored) as SaveRecord;
    return typeof save.pack === "string" ? save : null;
  } catch {
    return null;
  }
}

/** Forget it — a new game, or one the service would no longer replay. */
export function forget(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Nothing to do about it, and nothing depends on it having worked.
  }
}

/** Hand the player the save as a file they own. */
export function download(save: SaveRecord): void {
  const blob = new Blob([JSON.stringify(save, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${save.pack}.mace.json`;
  link.click();
  URL.revokeObjectURL(url);
}
