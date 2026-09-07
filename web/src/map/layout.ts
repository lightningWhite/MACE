/**
 * Where the places go.
 *
 * Two layouts, as docs/10 asks for: authored `mapPosition` when an author set
 * one, and force-directed otherwise, "so authors get a decent map for free
 * and a beautiful one if they care".
 *
 * The force layout is where **edge length reflects `ticks`** literally: a
 * road's rest length is proportional to how long it takes to walk, so a
 * six-tick road settles three times as long as a two-tick one and distance on
 * the map means distance in the world. With authored positions that is the
 * author's business, and the number is written on the road instead.
 *
 * It is deterministic. Seeded by the place ids rather than by `Math.random`,
 * so the same world lays out the same way every time it is opened — a map
 * that rearranged itself on reload would be unreadable in a different way
 * each time.
 */

import type { Atlas, Place, Road } from "../protocol";

export interface Point {
  x: number;
  y: number;
}

export type Positions = Record<string, Point>;

/** How many pixels one tick of road is worth in the force layout. */
const PIXELS_PER_TICK = 26;

/** How far apart to ring places that no road connects. */
const APART = 150;

const ITERATIONS = 400;

// Repulsion is only here to stop two places sitting on top of each other, so
// it is weak: strong repulsion reaches an equilibrium at its own preferred
// distance and drowns out the rest lengths, which would make every road come
// out roughly the same length and take the meaning out of the picture.
const REPULSION = 1200;
const SPRING = 0.06;
const DAMPING = 0.85;

/**
 * A small deterministic generator, seeded from a string.
 *
 * Not the engine's RNG and not pretending to be: nothing here affects the
 * simulation. It exists so a layout is stable across reloads.
 */
function seeded(seed: string): () => number {
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return () => {
    hash += 0x6d2b79f5;
    let value = Math.imul(hash ^ (hash >>> 15), 1 | hash);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/** Whether the author laid this map out themselves. */
export function isAuthored(places: Place[]): boolean {
  return places.length > 0 && places.every((place) => place.x !== null);
}

/**
 * Lay the atlas out.
 *
 * @param atlas - the projection.
 * @returns a position per place, in arbitrary units. The view box is fitted
 *   around them afterwards, so the scale does not matter.
 */
export function layout(atlas: Atlas): Positions {
  if (isAuthored(atlas.places)) {
    const placed: Positions = {};
    for (const place of atlas.places) {
      placed[place.location] = { x: place.x ?? 0, y: place.y ?? 0 };
    }
    return placed;
  }
  return relaxed(atlas.places, atlas.roads);
}

function relaxed(places: Place[], roads: Road[]): Positions {
  const random = seeded(places.map((place) => place.location).join("|"));
  const nodes = places.map((place) => ({
    id: place.location,
    x: random() * 400 - 200,
    y: random() * 400 - 200,
    dx: 0,
    dy: 0,
  }));
  const index = new Map(nodes.map((node) => [node.id, node]));

  const springs = roads.flatMap((road) => {
    const a = index.get(road.from);
    const b = index.get(road.to);
    if (a === undefined || b === undefined) return [];
    return [{ a, b, rest: Math.max(PIXELS_PER_TICK, road.ticks * PIXELS_PER_TICK) }];
  });

  for (let pass = 0; pass < ITERATIONS; pass += 1) {
    for (const node of nodes) {
      node.dx *= DAMPING;
      node.dy *= DAMPING;
    }

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const one = nodes[i];
        const other = nodes[j];
        if (one === undefined || other === undefined) continue;
        let across = other.x - one.x;
        let down = other.y - one.y;
        let apart = Math.hypot(across, down);
        if (apart < 0.01) {
          across = random() - 0.5;
          down = random() - 0.5;
          apart = 0.01;
        }
        const push = REPULSION / (apart * apart);
        const unitX = (across / apart) * push;
        const unitY = (down / apart) * push;
        one.dx -= unitX;
        one.dy -= unitY;
        other.dx += unitX;
        other.dy += unitY;
      }
    }

    for (const { a, b, rest } of springs) {
      const across = b.x - a.x;
      const down = b.y - a.y;
      const apart = Math.hypot(across, down) || 0.01;
      const pull = (apart - rest) * SPRING;
      const unitX = (across / apart) * pull;
      const unitY = (down / apart) * pull;
      a.dx += unitX;
      a.dy += unitY;
      b.dx -= unitX;
      b.dy -= unitY;
    }

    for (const node of nodes) {
      node.x += Math.max(-20, Math.min(20, node.dx));
      node.y += Math.max(-20, Math.min(20, node.dy));
    }
  }

  const settled: Positions = {};
  for (const node of nodes) settled[node.id] = { x: node.x, y: node.y };

  // No road connects anything, so the springs did nothing and repulsion blew
  // the nodes apart into a cloud. A ring is more honest and far more readable.
  if (springs.length === 0 && nodes.length > 1) {
    nodes.forEach((node, at) => {
      const angle = (at / nodes.length) * Math.PI * 2;
      settled[node.id] = {
        x: Math.cos(angle) * APART,
        y: Math.sin(angle) * APART,
      };
    });
  }
  return settled;
}

export interface Box {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

/**
 * Fit a view box around the laid-out places, with room for their labels.
 *
 * @param positions - where the places ended up.
 * @param pad - space to leave around the outermost node.
 */
export function fit(positions: Positions, pad: number): Box {
  const points = Object.values(positions);
  if (points.length === 0) {
    return { minX: -pad, minY: -pad, width: pad * 2, height: pad * 2 };
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  return {
    minX,
    minY,
    width: Math.max(...xs) + pad - minX,
    height: Math.max(...ys) + pad - minY,
  };
}
