/**
 * How far apart you and whatever you're facing are, against your own reach.
 *
 * A static counterpart to TimingBar: the band a weapon works in doesn't
 * drain, distance does — the marker moves as `moveBy` is spent, not the
 * bar itself. `range` comes straight off `combat.responses`' `weaponRange`,
 * the same number `strike` itself reads server-side, so this bar can't drift
 * from what the engine actually rewards (the same discipline TimingBar's own
 * comment states for the timing door).
 */

import type { Reach } from "../protocol";

export function RangeBar({ range, distance }: { range: Reach; distance: number }) {
  const scale = Math.max(range.max, distance, 1) * 1.15;
  const pct = (value: number) => `${Math.min(100, Math.max(0, (value / scale) * 100))}%`;
  const reachable = distance >= range.min && distance <= range.max;

  return (
    <div
      className="range"
      role="meter"
      aria-label="distance"
      aria-valuenow={Math.round(distance * 10) / 10}
      aria-valuemin={0}
      aria-valuemax={Math.round(scale)}
    >
      <div
        className="range-band"
        style={{
          insetInlineStart: pct(range.min),
          inlineSize: `calc(${pct(range.max)} - ${pct(range.min)})`,
        }}
      />
      <div
        className="range-sweet"
        style={{
          insetInlineStart: pct(range.sweetMin),
          inlineSize: `calc(${pct(range.sweetMax)} - ${pct(range.sweetMin)})`,
        }}
      />
      <div
        className={reachable ? "range-marker" : "range-marker range-marker-out"}
        style={{ insetInlineStart: pct(distance) }}
      />
    </div>
  );
}
