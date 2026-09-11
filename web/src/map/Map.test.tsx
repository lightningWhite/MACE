/**
 * The map, drawn.
 *
 * The atlas it is given is the one the real engine projected, so what these
 * check is that the picture says what MACE said.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Atlas } from "../protocol";
import { MapView } from "./Map";
import { opening } from "../test/wire";

afterEach(cleanup);

const REAL: Atlas = opening.view.atlas;

function draw(atlas: Atlas, busy = false) {
  const onTravel = vi.fn();
  const { container } = render(
    <MapView atlas={atlas} onTravel={onTravel} busy={busy} />,
  );
  return { onTravel, container };
}

describe("what is on it", () => {
  it("names every place the player knows about", () => {
    draw(REAL);
    for (const place of REAL.places) {
      expect(screen.getByText(place.name)).toBeTruthy();
    }
  });

  it("writes each road's length on it", () => {
    const { container } = draw(REAL);
    const written = [...container.querySelectorAll(".road-ticks")].map(
      (node) => node.textContent,
    );
    expect(written.sort()).toEqual(
      REAL.roads.map((road) => String(road.ticks)).sort(),
    );
  });

  it("names the sky over each region", () => {
    draw(REAL);
    const skies = new Set(
      REAL.places.map((place) => place.sky).filter((sky) => sky !== null),
    );
    expect(skies.size).toBeGreaterThan(0);
    for (const sky of skies) expect(screen.getAllByText(sky).length).toBeGreaterThan(0);
  });

  it("tells the three states apart by shape, not by colour alone", () => {
    const { container } = draw({
      ...REAL,
      places: REAL.places.map((place, at) => ({
        ...place,
        standing: (["here", "visited", "known"] as const)[at] ?? "known",
      })),
    });
    expect(container.querySelector(".node-halo")).toBeTruthy();
    expect(container.querySelectorAll(".node-ring").length).toBe(2);
    expect(container.querySelectorAll(".node-here").length).toBe(2);
  });

  it("describes itself for a reader who cannot see it", () => {
    draw(REAL);
    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(label).toContain("Fenmoor");
    expect(label).toContain("heard of");
  });

  it("says so when the player knows nowhere at all", () => {
    draw({ here: null, places: [], roads: [], journey: null });
    expect(screen.getByText(/no idea where you are/)).toBeTruthy();
  });
});

describe("panning and zooming it", () => {
  it("offers no reset control until the reader has moved away from the fit view", () => {
    draw(REAL);
    expect(screen.queryByRole("button", { name: "reset view" })).toBeNull();
  });
});

describe("travelling by it", () => {
  it("sends the option the engine said goes there", async () => {
    const user = userEvent.setup();
    const { onTravel, container } = draw(REAL);

    const castle = REAL.places.find((place) => place.choice !== null);
    expect(castle).toBeDefined();
    const node = container.querySelector(".place-reachable");
    expect(node).toBeTruthy();

    await user.click(node!);
    expect(onTravel).toHaveBeenCalledWith(castle!.choice);
  });

  it("does not offer a place nothing on the menu goes to", () => {
    const { container } = draw({
      ...REAL,
      places: REAL.places.map((place) => ({ ...place, choice: null })),
    });
    expect(container.querySelector(".place-reachable")).toBeNull();
  });

  it("stops offering travel while an action is in flight", () => {
    const { container } = draw(REAL, true);
    expect(container.querySelector(".place-reachable")).toBeNull();
  });
});

describe("roads worth a second look", () => {
  it("marks a road that is shut", () => {
    const shut = REAL.roads[0];
    expect(shut).toBeDefined();
    const { container } = draw({
      ...REAL,
      roads: REAL.roads.map((road) =>
        road.route === shut!.route ? { ...road, closed: true } : road,
      ),
    });
    expect(container.querySelectorAll(".road-shut").length).toBe(1);
    // And says so in a word, because dashes and red are not enough on their own.
    expect(screen.getByText("shut")).toBeTruthy();
  });

  it("draws a journey as far along as the player has got", () => {
    const [from, to] = [REAL.places[0], REAL.places[1]];
    expect(from).toBeDefined();
    expect(to).toBeDefined();
    const { container } = draw({
      ...REAL,
      journey: {
        route: "peasants-quest:north-road",
        from: from!.location,
        to: to!.location,
        walked: 3,
        ticks: 6,
        blockedAt: null,
      },
    });

    // Authored positions are used as drawn, so half a journey puts the
    // marker exactly halfway between the two places.
    const marker = container.querySelector(".journey circle");
    expect(marker).toBeTruthy();
    expect(Number(marker!.getAttribute("cx"))).toBeCloseTo(
      (from!.x! + to!.x!) / 2,
      5,
    );
    expect(Number(marker!.getAttribute("cy"))).toBeCloseTo(
      (from!.y! + to!.y!) / 2,
      5,
    );
  });
});

// ── The price overlay ─────────────────────────────────────────────────────────

describe("prices the player has seen", () => {
  /** The real atlas, with a couple of quoted prices written into it. */
  function quoted(): Atlas {
    const [first, second, ...rest] = REAL.places;
    if (first === undefined || second === undefined) throw new Error("no places");
    return {
      ...REAL,
      places: [
        { ...first, prices: { "fantasy.core:grain": 4 } },
        { ...second, prices: { "fantasy.core:grain": 9 } },
        ...rest,
      ],
    };
  }

  it("offers nothing to shade by until a price has been seen", () => {
    draw(REAL);
    expect(screen.queryByLabelText(/Shade the map by/)).toBeNull();
  });

  it("offers the goods the player has been quoted, by name", () => {
    render(
      <MapView
        atlas={quoted()}
        carried={[
          { item: "fantasy.core:grain", name: "Grain", qty: 0, value: 4 },
        ]}
        onTravel={vi.fn()}
        busy={false}
      />,
    );
    const picker = screen.getByLabelText(/Shade the map by/);
    expect(
      within(picker as HTMLSelectElement).getByRole("option", { name: "Grain" }),
    ).toBeTruthy();
  });

  it("draws nothing until one is picked", () => {
    const { container } = draw(quoted());
    expect(container.querySelectorAll(".price-mark")).toHaveLength(0);
  });

  it("writes the number as well as shading, and marks both ends", async () => {
    const user = userEvent.setup();
    const { container } = draw(quoted());
    await user.selectOptions(
      screen.getByLabelText(/Shade the map by/),
      "fantasy.core:grain",
    );

    const written = [...container.querySelectorAll(".price-mark")].map(
      (node) => node.textContent,
    );
    expect(written).toEqual(["4", "9"]);
    expect(container.querySelectorAll(".price-cheap")).toHaveLength(1);
    expect(container.querySelectorAll(".price-dear")).toHaveLength(1);
  });

  it("shades only the places the player has actually been quoted at", async () => {
    const user = userEvent.setup();
    const { container } = draw(quoted());
    await user.selectOptions(
      screen.getByLabelText(/Shade the map by/),
      "fantasy.core:grain",
    );
    // Two of the places carry a price; the rest are unshaded, because a map
    // that filled them in would be telling the player what they have not seen.
    expect(container.querySelectorAll(".price-blob")).toHaveLength(2);
    expect(REAL.places.length).toBeGreaterThan(2);
  });
});
