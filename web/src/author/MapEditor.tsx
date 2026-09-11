/**
 * The world map, editable.
 *
 * The thing a browser can do that a terminal cannot, and the reason docs/09
 * says a step type the terminal renders badly (`MapEditor`) still has to
 * declare a text fallback rather than being refused: a pair of numbers is a
 * position, and dragging is one way of choosing one.
 *
 * Everything here writes through the ordinary wizard. Dragging a place posts
 * the same `location.mapPosition` answer the terminal writes when an author
 * types `0 120`. Drawing a road posts to `/roads`, which is one call because
 * drawing a road is one authoring *intention* — a route is a road and an exit
 * is the option to walk down it, and a map editor that made the route and left
 * the author to write two exits would be a map editor whose maps open with a
 * validator note at every place.
 *
 * **A place nobody has positioned is drawn where the client guesses, and says
 * so.** The wizard sends `null` rather than a number, because the client
 * laying something out is not the same as the author having chosen, and an
 * editor that quietly turned a guess into an authored position the first time
 * somebody opened it would be an editor that wrote content nobody asked for.
 */

import { useEffect, useRef, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import { svgPoint, useSvgPanZoom } from "./panzoom";
import type { Atlas, Drawn } from "./protocol";

/** Room around the outermost place, for its label. */
const PAD = 60;

/** Where a place with no authored position is put, before anybody drags it. */
const GUESS_RADIUS = 140;

/** Room a region's oval leaves around its outermost member. */
const REGION_PAD = 55;

interface Placed {
  place: Drawn;
  x: number;
  y: number;
  /** Whether the author put it here, or the client did. */
  authored: boolean;
}

/**
 * Where to draw everything.
 *
 * Authored positions are used as written. The rest go round a circle, in id
 * order, so the layout is at least stable between renders — a guessed map that
 * reshuffled itself on every save would be unusable, and a force layout would
 * be a lie about content the author has not written.
 */
function positioned(places: Drawn[]): Placed[] {
  const guessed = places.filter((one) => one.x === null || one.y === null);
  let index = 0;
  return places.map((place) => {
    if (place.x !== null && place.y !== null) {
      return { place, x: place.x, y: place.y, authored: true };
    }
    const angle = (2 * Math.PI * index++) / Math.max(guessed.length, 1);
    return {
      place,
      x: Math.round(Math.cos(angle) * GUESS_RADIUS),
      y: Math.round(Math.sin(angle) * GUESS_RADIUS),
      authored: false,
    };
  });
}

function box(placed: Placed[]) {
  if (placed.length === 0) return { minX: -100, minY: -100, width: 200, height: 200 };
  const xs = placed.map((one) => one.x);
  const ys = placed.map((one) => one.y);
  const minX = Math.min(...xs) - PAD;
  const minY = Math.min(...ys) - PAD;
  return {
    minX,
    minY,
    width: Math.max(...xs) + PAD - minX,
    height: Math.max(...ys) + PAD - minY,
  };
}

/** Widen a fitted box so every region's oval fits inside it too. */
function withRegions(fitted: ReturnType<typeof box>, regions: RegionShape[]) {
  let minX = fitted.minX;
  let minY = fitted.minY;
  let maxX = fitted.minX + fitted.width;
  let maxY = fitted.minY + fitted.height;
  for (const one of regions) {
    minX = Math.min(minX, one.cx - one.rx);
    minY = Math.min(minY, one.cy - one.ry);
    maxX = Math.max(maxX, one.cx + one.rx);
    maxY = Math.max(maxY, one.cy + one.ry);
  }
  return { minX, minY, width: maxX - minX, height: maxY - minY };
}

/** What a road is called, for a label somebody has to read. */
function roadName(atlas: Atlas, id: string): string {
  const road = atlas.roads.find((one) => one.id === id);
  return road === undefined ? id : String(road.name ?? road.id);
}

interface RegionShape {
  id: string;
  name: string;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
}

/**
 * An oval around each region's own places.
 *
 * A region is a fact about a location, not a thing with a position of its
 * own, so it is drawn from wherever its members already are rather than
 * placed independently — the same reasoning `mapPosition` is per-place. A
 * region with one member still gets a real oval, padded the same as the
 * label would need, so it reads as a region rather than a ring drawn around
 * a dot for no reason a reader can see.
 */
function regionShapes(placed: Placed[], atlas: Atlas): RegionShape[] {
  const members = new Map<string, Placed[]>();
  for (const one of placed) {
    const region = one.place.region;
    if (region === null) continue;
    const list = members.get(region) ?? [];
    list.push(one);
    members.set(region, list);
  }
  const named = new Map(atlas.regions.map((one) => [one.id, one.name]));
  return [...members.entries()].map(([id, group]) => {
    const xs = group.map((one) => one.x);
    const ys = group.map((one) => one.y);
    const minX = Math.min(...xs) - REGION_PAD;
    const maxX = Math.max(...xs) + REGION_PAD;
    const minY = Math.min(...ys) - REGION_PAD;
    const maxY = Math.max(...ys) + REGION_PAD;
    return {
      id,
      name: named.get(id) ?? id,
      cx: (minX + maxX) / 2,
      cy: (minY + maxY) / 2,
      rx: (maxX - minX) / 2,
      ry: (maxY - minY) / 2,
    };
  });
}

export function MapEditor({
  onOpen,
  onChanged,
  busy,
}: {
  /** Open one place's or road's form — the map is a way in, not a
   * replacement. */
  onOpen: (id: string) => void;
  /** Something was written, so the desk and the problem list have moved. */
  onChanged: () => void;
  busy: boolean;
}) {
  const [atlas, setAtlas] = useState<Atlas | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<string | null>(null);
  const [ticks, setTicks] = useState(4);
  const [dragging, setDragging] = useState<{ id: string; x: number; y: number } | null>(
    null,
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const surface = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    void api
      .atlas()
      .then(setAtlas)
      .catch((error: unknown) => {
        setFailure(error instanceof StudioError ? error.message : "no map");
      });
  }, []);

  // Computed unconditionally, atlas or no atlas, because the pan/zoom hook
  // below has to be called on every render regardless of what this one
  // returns — an empty map still has a box to fit and a gesture to track.
  const placed = atlas === null ? [] : positioned(atlas.places);
  const regions = atlas === null ? [] : regionShapes(placed, atlas);
  const fitted = withRegions(box(placed), regions);
  const pan = useSvgPanZoom(surface, {
    x: fitted.minX,
    y: fitted.minY,
    w: fitted.width,
    h: fitted.height,
  });

  const refresh = async () => {
    setAtlas(await api.atlas());
    onChanged();
  };

  const run = async (call: () => Promise<unknown>) => {
    setFailure(null);
    try {
      await call();
      await refresh();
    } catch (error) {
      setFailure(error instanceof StudioError ? error.message : "that did not work");
    }
  };

  if (failure !== null && atlas === null) {
    return <p className="studio-failure">{failure}</p>;
  }
  if (atlas === null) return <p className="dim">Drawing the map…</p>;

  const at = new Map(placed.map((one) => [one.place.id, one]));

  /** Turn a pointer event into the coordinates the author is choosing. */
  const pointAt = (event: React.PointerEvent): { x: number; y: number } | null => {
    const svg = surface.current;
    if (svg === null) return null;
    const local = svgPoint(svg, event.clientX, event.clientY);
    return local === null ? null : { x: Math.round(local.x), y: Math.round(local.y) };
  };

  const drop = (id: string) => {
    if (dragging === null || dragging.id !== id) return;
    const { x, y } = dragging;
    setDragging(null);
    void run(() =>
      api.answer("locations", "location.mapPosition", { x, y }, id),
    );
  };

  const pick = (id: string) => {
    if (drawing === null) return setDrawing(id);
    if (drawing === id) return setDrawing(null);
    const [origin, destination] = [drawing, id];
    setDrawing(null);
    void run(() => api.link(origin, destination, ticks));
  };

  return (
    <div className="map-editor">
      <p className="dim">
        Drag a place to put it somewhere. Click two places to draw a road
        between them — {atlas.places.length < 2 ? "once there are two" : "in that order"}.
        Scroll to zoom; drag the empty map to pan.
      </p>

      {failure === null ? null : (
        <p className="studio-failure" role="alert">
          {failure}
        </p>
      )}

      <svg
        ref={surface}
        className="author-map"
        viewBox={pan.viewBox}
        role="img"
        aria-label={`A map of ${atlas.places.length} places and ${atlas.roads.length} roads`}
        onPointerDown={pan.background.onPointerDown}
        onPointerMove={(event) => {
          if (dragging !== null) {
            const point = pointAt(event);
            if (point !== null) setDragging({ id: dragging.id, ...point });
            return;
          }
          pan.background.onPointerMove(event);
        }}
        onPointerUp={(event) => {
          if (dragging !== null) {
            drop(dragging.id);
            return;
          }
          pan.background.onPointerUp(event);
        }}
        onPointerLeave={() => setDragging(null)}
      >
        {regions.map((region) => (
          <g key={region.id} className="author-region">
            <ellipse cx={region.cx} cy={region.cy} rx={region.rx} ry={region.ry} />
            <text x={region.cx - region.rx + 8} y={region.cy - region.ry + 14}>
              {region.name}
            </text>
          </g>
        ))}

        {atlas.roads.map((road) => {
          const from = at.get(String(road.from));
          const to = at.get(String(road.to));
          if (from === undefined || to === undefined) return null;
          const [x, y] = [(from.x + to.x) / 2, (from.y + to.y) / 2];
          return (
            <g
              key={road.id}
              className={
                chosen === road.id ? "author-road author-chosen" : "author-road"
              }
              onClick={() => setChosen(chosen === road.id ? null : road.id)}
            >
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
              {/* A fat invisible line, so a road is something a pointer can
                  actually hit. Non-scaling so the hit area stays a constant
                  screen size no matter how large the map is or how far the
                  viewBox has to zoom out to fit it. */}
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className="author-road-grab"
                vectorEffect="non-scaling-stroke"
              />
              <text x={x} y={y - 5}>
                {String(road.ticks ?? "?")}
              </text>
            </g>
          );
        })}

        {placed.map((one) => {
          const held =
            dragging !== null && dragging.id === one.place.id ? dragging : one;
          return (
            <g
              key={one.place.id}
              className={
                "author-place" +
                (one.authored ? "" : " author-guessed") +
                (drawing === one.place.id ? " author-drawing" : "")
              }
              onPointerDown={(event) => {
                if (busy) return;
                (event.target as Element).setPointerCapture?.(event.pointerId);
                setDragging({ id: one.place.id, x: held.x, y: held.y });
              }}
              onClick={() => {
                if (dragging === null) pick(one.place.id);
              }}
            >
              <circle cx={held.x} cy={held.y} r={7} />
              <text x={held.x + 11} y={held.y + 4}>
                {one.place.name}
              </text>
              {one.authored ? null : (
                <text x={held.x + 11} y={held.y + 15} className="author-unplaced">
                  not placed
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="map-tools">
        <label className="field-check">
          <span className="dim">a new road takes</span>
          <input
            className="field-input field-number"
            type="number"
            min={1}
            value={ticks}
            aria-label="How long a new road takes"
            onChange={(event) => setTicks(Math.max(1, Number(event.target.value)))}
          />
          <span className="dim">ticks</span>
        </label>
        {pan.zoomed ? (
          <button type="button" className="link-button" onClick={pan.reset}>
            reset view
          </button>
        ) : null}
        {drawing === null ? null : (
          <span className="dim">
            drawing from {at.get(drawing)?.place.name ?? drawing} — click where it
            goes
          </span>
        )}
      </div>

      {chosen === null ? null : (
        <div className="map-tools">
          <span>{roadName(atlas, chosen)}</span>
          <button type="button" onClick={() => onOpen(chosen)}>
            Open it
          </button>
          <button
            type="button"
            className="object-delete"
            disabled={busy}
            aria-label={`Rub out ${roadName(atlas, chosen)}`}
            onClick={() => {
              const which = chosen;
              setChosen(null);
              void run(() => api.unlink(which));
            }}
          >
            rub out
          </button>
        </div>
      )}

    </div>
  );
}
