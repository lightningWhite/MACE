/**
 * Where the places go.
 *
 * The interesting claim is that a force-laid map means something: a road that
 * takes three times as long should come out about three times as long.
 */

import { describe, expect, it } from "vitest";

import type { Atlas, Place, Road } from "../protocol";
import { fit, isAuthored, layout } from "./layout";
import { opening } from "../test/wire";

function place(id: string, extra: Partial<Place> = {}): Place {
  return {
    location: id,
    name: id,
    standing: "known",
    region: null,
    weather: null,
    sky: null,
    indoors: false,
    choice: null,
    prices: {},
    x: null,
    y: null,
    elevation: null,
    ...extra,
  };
}

function road(id: string, from: string, to: string, ticks: number): Road {
  return {
    route: id,
    name: null,
    from,
    to,
    bidirectional: true,
    ticks,
    closed: false,
    reason: null,
  };
}

function atlas(places: Place[], roads: Road[]): Atlas {
  return { here: places[0]?.location ?? null, places, roads, journey: null };
}

describe("authored maps", () => {
  it("are used exactly as the author drew them", () => {
    const drawn = atlas(
      [place("a", { x: 10, y: 20 }), place("b", { x: -5, y: 7 })],
      [],
    );
    expect(layout(drawn)).toEqual({ a: { x: 10, y: 20 }, b: { x: -5, y: 7 } });
  });

  it("are recognised from the real game's map positions", () => {
    expect(isAuthored(opening.view.atlas.places)).toBe(true);
  });

  it("are not claimed when only some places carry a position", () => {
    expect(isAuthored([place("a", { x: 1, y: 1 }), place("b")])).toBe(false);
  });
});

describe("a map nobody laid out", () => {
  const places = [place("home"), place("near"), place("far")];
  const roads = [
    road("short", "home", "near", 2),
    road("long", "home", "far", 6),
  ];

  function apart(positions: Record<string, { x: number; y: number }>, a: string, b: string) {
    const one = positions[a]!;
    const other = positions[b]!;
    return Math.hypot(one.x - other.x, one.y - other.y);
  }

  it("makes a road's length mean how long it takes to walk", () => {
    // Six ticks against two, so the long road should come out somewhere near
    // three times the short one. Not exactly: places also push each other
    // apart, and a graph cannot always satisfy every road at once.
    const settled = layout(atlas(places, roads));
    const ratio = apart(settled, "home", "far") / apart(settled, "home", "near");
    expect(ratio).toBeGreaterThan(2);
    expect(ratio).toBeLessThan(3.6);
  });

  it("lays out the same way every time it is opened", () => {
    // A map that rearranged itself on reload would be unreadable in a
    // different way each time.
    expect(layout(atlas(places, roads))).toEqual(layout(atlas(places, roads)));
  });

  it("rings places that no road connects, rather than scattering them", () => {
    const settled = layout(atlas([place("a"), place("b"), place("c")], []));
    const distances = [
      Math.hypot(settled.a!.x, settled.a!.y),
      Math.hypot(settled.b!.x, settled.b!.y),
      Math.hypot(settled.c!.x, settled.c!.y),
    ];
    for (const distance of distances) expect(distance).toBeCloseTo(150, 5);
  });

  it("does not put two places on top of each other", () => {
    const settled = layout(atlas(places, roads));
    expect(apart(settled, "near", "far")).toBeGreaterThan(10);
  });
});

describe("fit", () => {
  it("leaves room around the outermost place for its label", () => {
    const box = fit({ a: { x: 0, y: 0 }, b: { x: 100, y: 40 } }, 20);
    expect(box).toEqual({ minX: -20, minY: -20, width: 140, height: 80 });
  });

  it("still gives a box when there is nothing to fit around", () => {
    expect(fit({}, 10)).toEqual({ minX: -10, minY: -10, width: 20, height: 20 });
  });
});
