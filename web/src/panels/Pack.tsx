/**
 * What the player is carrying.
 *
 * Names and prices come from the projection. Only the engine knows that
 * `fantasy.core:bread` is called Bread, and a client that worked it out from
 * the id would be reading content.
 */

import type { Carried } from "../protocol";

export function Pack({ carried }: { carried: Carried[] }) {
  return (
    <section className="panel" aria-labelledby="pack-heading">
      <h2 id="pack-heading">Pack</h2>
      {carried.length === 0 ? (
        <p className="empty">Nothing but your hands.</p>
      ) : (
        <ul className="stacks">
          {carried.map((stack) => (
            <li key={stack.item}>
              <span>{stack.name}</span>
              {stack.qty > 1 && <span className="dim"> ×{stack.qty}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
