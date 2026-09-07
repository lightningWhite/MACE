/**
 * The standing line: where and when the player is.
 *
 * docs/10 says it "is the simulation made visible, and it should never be
 * absent" — it is what tells the player the world is running whether they act
 * or not. So it renders from the last `world.status` event and stays put.
 */

import type { WorldStatus } from "../protocol";

export function StatusLine({ status }: { status: WorldStatus | null }) {
  if (status === null) {
    return <footer className="status" aria-live="polite" />;
  }

  const parts = [
    `Day ${status.day}`,
    status.dayPart,
    status.place,
    status.sky || (status.indoors ? "indoors" : "clear"),
  ];
  return (
    <footer className="status" aria-live="polite">
      {parts.join(" · ")}
      {status.temperature !== null && (
        <span className="dim"> · {Math.round(status.temperature)}°</span>
      )}
    </footer>
  );
}
