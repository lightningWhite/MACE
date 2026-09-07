/**
 * Which key answers which move.
 *
 * The same rule as `keys_for` in `mace/cli/play.py`, and it has to be: a
 * player who learns the fight in the terminal and finishes it in a browser
 * should not have to learn the keys twice.
 *
 * Content does not name a key. A move's `key` would be presentation leaking
 * into content — a browser binds a button, a screen reader binds nothing — so
 * the front-end picks: first free alphanumeric of the *label*, and failing
 * that a digit.
 */

import type { CombatResponse } from "../protocol";

export interface Bound {
  key: string;
  response: string;
  label: string;
}

const ALPHANUMERIC = /[a-z0-9]/;

/**
 * Bind a key to each response, in the order they were offered.
 *
 * @param options - the responses on offer.
 * @returns one binding per option, in the same order.
 */
export function keysFor(options: CombatResponse[]): Bound[] {
  const taken = new Set<string>();
  return options.map((option, index) => {
    const letters = [...option.label.toLowerCase()];
    const free = letters.find(
      (letter) => ALPHANUMERIC.test(letter) && !taken.has(letter),
    );
    const key = free ?? String(index + 1).slice(-1);
    taken.add(key);
    return { key, response: option.response, label: option.label };
  });
}
