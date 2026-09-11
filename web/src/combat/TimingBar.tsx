/**
 * The window, draining.
 *
 * The numbers are the engine's, not this component's. `precision_of` in
 * `mace/engine/combat/resolution.py` puts the sweet spot three quarters of
 * the way through the window and falls off linearly to nothing half a window
 * either side of it, so the bar marks three quarters and shades the band
 * where an answer is worth anything. A bar that marked a different spot from
 * the one the engine rewards would be worse than no bar.
 *
 * It reads the clock, and it says so out loud for anyone who cannot watch it:
 * an ARIA live region announces the window opening, and `prefers-reduced-
 * motion` turns the sweep into a numeric countdown, which docs/10 asks for by
 * name.
 */

import { useEffect, useRef, useState } from "react";

/** The sweet spot, as a fraction of the window. Mirrors `precision_of`. */
export const IDEAL = 0.75;

/** Where an answer starts being worth anything: half a window before ideal. */
export const OPENS = IDEAL - 0.5;

export function reducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function TimingBar({
  windowMs,
  startedAt,
  onExpire,
}: {
  windowMs: number;
  /** When the window opened, on the same clock `elapsed` is measured against. */
  startedAt: number;
  onExpire: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const expired = useRef(false);
  const quiet = reducedMotion();

  useEffect(() => {
    expired.current = false;
    let frame = 0;

    const tick = () => {
      const gone = performance.now() - startedAt;
      setElapsed(gone);
      if (gone >= windowMs) {
        if (!expired.current) {
          expired.current = true;
          onExpire();
        }
        return;
      }
      frame = window.requestAnimationFrame(tick);
    };

    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [windowMs, startedAt, onExpire]);

  const through = Math.min(1, elapsed / windowMs);
  const left = Math.max(0, windowMs - elapsed);

  if (quiet) {
    return (
      <p className="countdown" role="timer" aria-live="assertive">
        {(left / 1000).toFixed(1)}s
      </p>
    );
  }

  return (
    <div
      className="timing"
      role="timer"
      aria-label={`${Math.round(windowMs)} millisecond window`}
    >
      {/* The drain first, so it sits *under* the sweet band and the ideal
          mark rather than covering them — an opaque bar drawn on top of its
          own target would hide the one thing a player is watching it for
          until the drain had shrunk past that point, which for three
          quarters of every window is the whole bar. */}
      <div className="timing-drain" style={{ inlineSize: `${(1 - through) * 100}%` }} />
      <div
        className="timing-sweet"
        style={{
          insetInlineStart: `${OPENS * 100}%`,
          inlineSize: `${(1 - OPENS) * 100}%`,
        }}
      />
      <div className="timing-ideal" style={{ insetInlineStart: `${IDEAL * 100}%` }} />
    </div>
  );
}
