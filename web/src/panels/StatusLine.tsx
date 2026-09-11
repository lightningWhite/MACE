/**
 * The standing line: where and when the player is.
 *
 * docs/10 says it "is the simulation made visible, and it should never be
 * absent" — it is what tells the player the world is running whether they act
 * or not. So it renders from the last `world.status` event and stays put.
 */

import { useState } from "react";

import type { WorldStatus } from "../protocol";
import { formatTemperature, setUnitPreference, unitPreference } from "../units";

export function StatusLine({ status }: { status: WorldStatus | null }) {
  const [unit, setUnit] = useState(unitPreference);

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
        <>
          {" · "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              const next = unit === "fahrenheit" ? "celsius" : "fahrenheit";
              setUnit(next);
              setUnitPreference(next);
            }}
            title="Click to switch °F/°C"
          >
            {formatTemperature(status.temperature, status.temperatureUnit, unit)}
          </button>
        </>
      )}
    </footer>
  );
}
