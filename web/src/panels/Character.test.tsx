/**
 * The character panel.
 *
 * Ability stats used to render as a 3-letter abbreviation with no cap shown
 * at all — easy to miss, and no way to see growth happen even once it was
 * possible. These check the fuller rendering: the stat's real name, and its
 * cap only when there's one worth showing.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { Character } from "./Character";
import type { Gauge, Sheet } from "../protocol";

function gauge(overrides: Partial<Gauge> = {}): Gauge {
  return { stat: "strength", value: 50, maximum: null, role: "ability", ...overrides };
}

function sheet(stats: Gauge[]): Sheet {
  return { entity: "hero", name: "Hero", background: null, stats, exposure: 0 };
}

afterEach(cleanup);

it("shows an ability stat by its full name, not a 3-letter abbreviation", () => {
  render(<Character sheet={sheet([gauge({ stat: "strength", value: 72 })])} />);
  expect(screen.getByText("strength")).toBeTruthy();
  expect(screen.queryByText("str")).toBeNull();
});

it("shows a cap once there is one to show", () => {
  render(
    <Character
      sheet={sheet([gauge({ stat: "stamina", value: 8, maximum: 100 })])}
    />,
  );
  expect(screen.getByText("8")).toBeTruthy();
  expect(screen.getByText("/100")).toBeTruthy();
});

it("shows no cap when the projection reports none", () => {
  render(<Character sheet={sheet([gauge({ stat: "speed", maximum: null })])} />);
  expect(screen.queryByText(/\//)).toBeNull();
});
