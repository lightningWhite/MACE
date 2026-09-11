/**
 * A 2x2 grid, and the two dividers a player can drag to reshape it.
 *
 * The play screen's four quadrants share one column split (between
 * narrative/action and map/info) and one row split (between the top row and
 * the bottom row) — the ordinary shape of a four-pane layout, and simpler
 * than letting every quadrant resize independently would be. Both are
 * percentages of the shell's own box, so they hold their proportions across
 * a window resize the same way the rest of the layout already does.
 *
 * Remembered per browser, not per game: a reader who widens the map once
 * almost certainly wants it wide next time too, whatever they are playing.
 */

import { useEffect, useRef, useState } from "react";

/** How far either divider may travel, so dragging one to an edge still
 * leaves every quadrant a usable sliver rather than nothing at all. */
const MIN_PERCENT = 20;
const MAX_PERCENT = 80;

const DEFAULTS = { col: 72, row: 55 };

const STORAGE_KEY = "mace.play.split";

function clamp(value: number): number {
  return Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, value));
}

function loadStored(): { col: number; row: number } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return DEFAULTS;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      typeof (parsed as { col?: unknown }).col !== "number" ||
      typeof (parsed as { row?: unknown }).row !== "number"
    ) {
      return DEFAULTS;
    }
    const found = parsed as { col: number; row: number };
    return { col: clamp(found.col), row: clamp(found.row) };
  } catch {
    return DEFAULTS;
  }
}

type Axis = "col" | "row";

export interface SplitGrid {
  /** Where the column divider sits, as a percent of the shell's width. */
  colPercent: number;
  /** Where the row divider sits, as a percent of the shell's height. */
  rowPercent: number;
  /** Spread onto the vertical divider between the two columns. */
  columnHandle: {
    onPointerDown: (event: React.PointerEvent) => void;
    onKeyDown: (event: React.KeyboardEvent) => void;
  };
  /** Spread onto the horizontal divider between the two rows. */
  rowHandle: {
    onPointerDown: (event: React.PointerEvent) => void;
    onKeyDown: (event: React.KeyboardEvent) => void;
  };
}

/**
 * Track the split and the drag that is changing it, if one is under way.
 *
 * @param container - the shell the percentages are measured against. A ref
 *   rather than an element, so this can be called before the shell has
 *   mounted.
 */
export function useSplitGrid(container: React.RefObject<HTMLElement | null>): SplitGrid {
  const [percents, setPercents] = useState(loadStored);
  const [dragging, setDragging] = useState<Axis | null>(null);

  useEffect(() => {
    if (dragging === null) return;
    const onMove = (event: PointerEvent) => {
      const box = container.current?.getBoundingClientRect();
      if (box === undefined) return;
      setPercents((current) => ({
        ...current,
        [dragging]:
          dragging === "col"
            ? clamp(((event.clientX - box.left) / box.width) * 100)
            : clamp(((event.clientY - box.top) / box.height) * 100),
      }));
    };
    const onUp = () => setDragging(null);
    // On the window, not the divider: a fast drag outsteps the pointer's own
    // hit-test, and losing the gesture the instant the cursor leaves a
    // ten-pixel-wide strip would make this unusable rather than merely
    // imprecise.
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging, container]);

  // Skips the render this mounts with: a reader who never touches either
  // divider should never gain a `localStorage` entry over it, the same as
  // one who never does anything worth remembering leaves none behind
  // anywhere else in this app.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(percents));
    } catch {
      // A private window or a full storage quota loses the preference, not
      // the layout — it just falls back to the default next time.
    }
  }, [percents]);

  const nudge = (axis: Axis, delta: number) =>
    setPercents((current) => ({ ...current, [axis]: clamp(current[axis] + delta) }));

  const handle = (axis: Axis, keys: [string, string]) => ({
    onPointerDown: (event: React.PointerEvent) => {
      event.preventDefault();
      setDragging(axis);
    },
    onKeyDown: (event: React.KeyboardEvent) => {
      const step = event.shiftKey ? 10 : 2;
      if (event.key === keys[0]) nudge(axis, -step);
      else if (event.key === keys[1]) nudge(axis, step);
      else if (event.key === "Home") setPercents((c) => ({ ...c, [axis]: DEFAULTS[axis] }));
      else return;
      event.preventDefault();
    },
  });

  return {
    colPercent: percents.col,
    rowPercent: percents.row,
    columnHandle: handle("col", ["ArrowLeft", "ArrowRight"]),
    rowHandle: handle("row", ["ArrowUp", "ArrowDown"]),
  };
}
