/**
 * Pan and zoom for an SVG laid out in its own fixed coordinate space.
 *
 * The map editor and the scene graph both fit their content to a `viewBox`
 * computed from the data, then never touch it again — which is fine for a
 * handful of places, and useless once a pack has enough of them that reading
 * a label means leaning into the screen. This layers wheel-to-zoom and
 * drag-the-background-to-pan on top of that fitted box without either caller
 * changing how it computes one.
 *
 * Reading the pointer's position back out of the SVG goes through
 * `getScreenCTM()` rather than dividing by the element's bounding rect: the
 * default `preserveAspectRatio` letterboxes instead of stretching, so a
 * `viewBox` whose aspect ratio does not match the rendered box's leaves bars
 * that a naive ratio calculation would count as if they were content — every
 * click and drag would land off by however wide the bars are.
 */

import { useEffect, useRef, useState } from "react";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** How far the content may be zoomed in or out, in SVG user units. */
const MIN_SPAN = 40;
const MAX_SPAN = 20000;

/** Convert a client-space point into the SVG's own coordinate space. */
export function svgPoint(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const ctm = svg.getScreenCTM();
  if (ctm === null) return null;
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const local = point.matrixTransform(ctm.inverse());
  return { x: local.x, y: local.y };
}

interface PanState {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startView: Box;
  /** Screen pixels per user unit, frozen for the drag so a pan stays linear
   * even though the view it is computed from is what's being dragged. */
  scale: number;
}

/**
 * Wheel-to-zoom and drag-to-pan for one SVG, on top of a fitted base box.
 *
 * @param surface - the SVG the gesture applies to.
 * @param base - the box that fits the content, recomputed by the caller on
 *   every render; used until the reader zooms or pans, and to zoom or pan
 *   from when they do.
 * @returns `viewBox`, the string to render; `background`, pointer handlers to
 *   spread onto the SVG (they no-op for a pointer that started on a child
 *   element, so a caller's own click and drag handlers on places or nodes
 *   keep working untouched); `reset`, to return to `base`; and `zoomed`,
 *   whether the reader has moved away from it.
 */
export function useSvgPanZoom(surface: React.RefObject<SVGSVGElement | null>, base: Box) {
  const baseRef = useRef(base);
  baseRef.current = base;
  const [view, setView] = useState<Box | null>(null);
  const panRef = useRef<PanState | null>(null);

  useEffect(() => {
    const svg = surface.current;
    if (svg === null) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const local = svgPoint(svg, event.clientX, event.clientY);
      if (local === null) return;
      const factor = Math.exp(event.deltaY * 0.0015);
      setView((current) => {
        const from = current ?? baseRef.current;
        const w = Math.min(Math.max(from.w * factor, MIN_SPAN), MAX_SPAN);
        const applied = w / from.w;
        const h = from.h * applied;
        return {
          w,
          h,
          x: local.x - (local.x - from.x) * applied,
          y: local.y - (local.y - from.y) * applied,
        };
      });
    };
    // Not React's `onWheel`: React attaches it passively, so `preventDefault`
    // would be ignored and the page would scroll along with the zoom.
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [surface]);

  const current = view ?? base;

  return {
    viewBox: `${current.x} ${current.y} ${current.w} ${current.h}`,
    zoomed: view !== null,
    reset: () => setView(null),
    background: {
      onPointerDown: (event: React.PointerEvent<SVGSVGElement>) => {
        if (event.target !== event.currentTarget) return;
        const svg = surface.current;
        if (svg === null) return;
        const ctm = svg.getScreenCTM();
        if (ctm === null) return;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        panRef.current = {
          pointerId: event.pointerId,
          startClientX: event.clientX,
          startClientY: event.clientY,
          startView: current,
          scale: ctm.a,
        };
      },
      onPointerMove: (event: React.PointerEvent<SVGSVGElement>) => {
        const pan = panRef.current;
        if (pan === null || pan.pointerId !== event.pointerId || pan.scale === 0) {
          return;
        }
        const dx = (event.clientX - pan.startClientX) / pan.scale;
        const dy = (event.clientY - pan.startClientY) / pan.scale;
        setView({ ...pan.startView, x: pan.startView.x - dx, y: pan.startView.y - dy });
      },
      onPointerUp: (event: React.PointerEvent<SVGSVGElement>) => {
        if (panRef.current?.pointerId === event.pointerId) panRef.current = null;
      },
    },
  };
}
