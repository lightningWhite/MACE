/**
 * The player's preferred temperature scale.
 *
 * A climate's `temperatureUnit` is content, not a player preference — it says
 * what scale the author wrote in, not what a reader wants to see. This is the
 * other half: a per-browser choice, converted at render time, the same way
 * `mace play --units` is a per-invocation choice for the terminal. Neither
 * touches the number the engine actually simulated with.
 */

export type Unit = "celsius" | "fahrenheit";

const KEY = "mace.units";

/** What to show before the player has chosen — matches the CLI's own default. */
const DEFAULT_UNIT: Unit = "fahrenheit";

/** The scale the player last chose, or the default where nothing was kept. */
export function unitPreference(): Unit {
  try {
    const stored = window.localStorage.getItem(KEY);
    return stored === "celsius" || stored === "fahrenheit" ? stored : DEFAULT_UNIT;
  } catch {
    return DEFAULT_UNIT;
  }
}

/** Remember the player's choice for next time. */
export function setUnitPreference(unit: Unit): void {
  try {
    window.localStorage.setItem(KEY, unit);
  } catch {
    // A private window, or storage that is full. The player just sees their
    // choice hold for this tab and not the next one — no game state at risk.
  }
}

/** A reading, converted from the scale it was written in to the one asked for. */
export function convert(value: number, from: Unit, to: Unit): number {
  if (from === to) return value;
  return to === "fahrenheit" ? (value * 9) / 5 + 32 : ((value - 32) * 5) / 9;
}

/** A reading formatted for display: converted, rounded, and suffixed. */
export function formatTemperature(value: number, from: Unit, to: Unit): string {
  const suffix = to === "fahrenheit" ? "°F" : "°C";
  return `${Math.round(convert(value, from, to))}${suffix}`;
}
